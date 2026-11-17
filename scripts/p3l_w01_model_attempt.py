#!/usr/bin/env python3
"""One bounded W01 CPU model attempt, artifact-only. Coordinator-owned transport.

This file DOES NOT contain a W01 model-authored ledger contract. It verifies
immutable inputs and records raw model evidence; it never writes repository
source, runs model-provided commands, commits, or creates pull requests.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from gguf_cpu_runtime import approved_model, sha256_file, verify_paths
from gguf_output_boundary import extract_completion
from p3l_w01_request import build_request, canonical, verified_head

UPSTREAM_SHA = "4e5116f47619dac4180c3007ef02a383f347554c"
MODEL_ID = "granite-code-8b"
MODEL_FILENAME = "granite-8b-code-instruct.Q4_K_M.gguf"
MAX_RAW_BYTES = 6000
MAX_PROMPT_BYTES = 5000


def digest(data):
    return hashlib.sha256(data).hexdigest()


def render(request):
    if not isinstance(request, dict):
        raise ValueError("worker request must be a JSON object")
    if (request.get("schema") != "p3l-worker-request-v1"
            or request.get("worker") != "W01"
            or request.get("issue") != 38
            or request.get("allowed_output") != ["docs/p3l/ledger-input-contract.ko.md"]
            or request.get("model_calls") != 0
            or request.get("executor_connected") is not False
            or request.get("merge_authorized") is not False
            or request.get("candidate_verified") is not False):
        raise ValueError("W01 request authorization boundary changed")
    copy = dict(request)
    expected_request_sha = copy.pop("request_sha256", None)
    if expected_request_sha != digest(canonical(copy)):
        raise ValueError("worker request bytes do not match its hash")
    prompt = request.get("prompt")
    if (not isinstance(prompt, str)
            or not 1 <= len(prompt.encode("utf-8")) <= MAX_PROMPT_BYTES
            or digest(prompt.encode("utf-8")) != request.get("prompt_sha256")
            or len(prompt.encode("utf-8")) != request.get("prompt_bytes")
            or any(mark in prompt for mark in ("\x00", "\x1b", "\r", "\nAnswer:\n", "\nQuestion:\n"))):
        raise ValueError("untrusted or altered W01 prompt")
    rendered = "Question:\n" + prompt + "\n\nAnswer:\n"
    if len(rendered.encode("utf-8")) > 5200:
        raise ValueError("Granite prompt exceeds bounded size")
    return rendered


def validate_assets(binary, weights, metadata_path, build_path, reviewed_sha):
    spec, checked_binary, checked_weights = verify_paths(MODEL_ID, binary, weights)
    if checked_weights.name != MODEL_FILENAME:
        raise ValueError("unexpected official Granite filename")
    meta = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    if (type(meta) is not dict or meta.get("model") != MODEL_ID
            or meta.get("repository") != spec["repo"]
            or meta.get("filename") != spec["filename"]
            or meta.get("license") != "apache-2.0"
            or meta.get("revision") != spec["revision"]
            or meta.get("sha256") != spec["sha256"]
            or meta.get("secret_or_paid_api_used") is not False
            or sha256_file(checked_weights) != spec["sha256"]):
        raise ValueError("official model provenance changed")
    record = json.loads(Path(build_path).read_text(encoding="utf-8"))
    binary_sha = sha256_file(checked_binary)
    expected = {
        "schema": "p3l-w01-pinned-binary-v1",
        "review_sha": reviewed_sha,
        "upstream_sha": UPSTREAM_SHA,
        "binary_sha256": binary_sha,
        "model_calls": 0,
        "merge_authorized": False,
    }
    if type(record) is not dict or record != expected:
        raise ValueError("same-run pinned binary provenance mismatch")
    return spec, binary_sha


def make_receipt(request, rendered, metadata, binary_sha, model_calls, status,
                 response=None, elapsed_seconds=None, error=None):
    if model_calls not in (0, 1):
        raise ValueError("invalid bounded call count")
    payload = {
        "schema": "p3l-w01-model-attempt-v1",
        "worker": "W01",
        "issue": 38,
        "review_sha": request["review_commit"],
        "request_sha256": request["request_sha256"],
        "original_source_sha256": request["source_sha256"],
        "spec_sha256": request["spec_sha256"],
        "prompt_sha256": request["prompt_sha256"],
        "rendered_prompt_sha256": digest(rendered.encode("utf-8")),
        "model_id": MODEL_ID,
        "model_revision": metadata["revision"],
        "model_weights_sha256": metadata["sha256"],
        "llama_binary_sha256": binary_sha,
        "llama_upstream_sha": UPSTREAM_SHA,
        "generation": {
            "n_predict": 900, "ctx_size": 3072, "threads": 4,
            "temperature": 0, "seed": 42,
        },
        "model_calls": model_calls,
        "response_sha256": digest(response.encode("utf-8")) if response is not None else None,
        "response_bytes": len(response.encode("utf-8")) if response is not None else None,
        "model_seconds": elapsed_seconds,
        "status": status,
        "allowed_output": request["allowed_output"],
        "model_authored_document_verified": False,
        "model_patch_applied": False,
        "merge_authorized": False,
        "secret_or_paid_api_used": False,
    }
    if error:
        payload["error"] = str(error)[:240]
    return payload


def fixed_command(binary, weights, prompt):
    return [
        str(binary), "--model", str(weights), "--prompt", prompt,
        "--n-predict", "900", "--ctx-size", "3072",
        "--threads", "4", "--temp", "0", "--seed", "42",
        "--no-display-prompt", "--simple-io", "--offline",
        "--log-verbosity", "1", "--color", "off", "-no-cnv", "--no-escape",
    ]


def execute(root, reviewed_sha, binary, weights, metadata_path, build_path, out_dir):
    root = Path(root).resolve(strict=True)
    verified_head(root, reviewed_sha)
    request = build_request(root, reviewed_sha)
    rendered = render(request)
    metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    _, binary_sha = validate_assets(binary, weights, metadata_path, build_path, reviewed_sha)
    output = Path(out_dir)
    if (output.is_symlink() or output.exists()
            or not output.resolve().is_relative_to(root / "artifacts")):
        raise ValueError("output must be a new directory underneath artifacts/")
    output.mkdir(parents=True, exist_ok=False)
    command = fixed_command(binary, weights, rendered)
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/tmp",
        "LANG": "C.UTF-8",
        "OMP_NUM_THREADS": "4",
        "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
    }
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command, shell=False, capture_output=True, text=True,
            errors="replace", timeout=1050, check=False, env=env,
        )
        duration = round(time.monotonic() - started, 3)
        if proc.returncode:
            receipt = make_receipt(request, rendered, metadata, binary_sha, 1,
                                   "MODEL_PROCESS_FAILED", elapsed_seconds=duration,
                                   error=f"exit_code={proc.returncode}")
            outcome = 3
        else:
            try:
                response, _ = extract_completion(proc.stdout, max_output_bytes=MAX_RAW_BYTES)
                if len(response.encode("utf-8")) < 100:
                    raise ValueError("model response too short for a ledger contract")
            except ValueError as exc:
                receipt = make_receipt(
                    request, rendered, metadata, binary_sha, 1,
                    "MODEL_TRANSPORT_REJECTED", elapsed_seconds=duration, error=exc)
                outcome = 3
            else:
                # Raw model text is evidence, NOT an approved repository file.
                (output / "raw_model_response.txt").write_text(response + "\n", encoding="utf-8")
                receipt = make_receipt(
                    request, rendered, metadata, binary_sha, 1,
                    "RAW_MODEL_RESPONSE_PENDING_REVIEW", response=response,
                    elapsed_seconds=duration)
                outcome = 0
    except subprocess.TimeoutExpired:
        receipt = make_receipt(request, rendered, metadata, binary_sha, 1,
                               "MODEL_TIMEOUT", elapsed_seconds=round(time.monotonic()-started, 3))
        outcome = 3
    (output / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps({
        "status": receipt["status"], "model_calls": receipt["model_calls"],
        "request_sha256": receipt["request_sha256"],
        "response_sha256": receipt["response_sha256"],
        "model_authored_document_verified": False,
    }, sort_keys=True))
    return outcome


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--cli", required=True, type=Path)
    parser.add_argument("--gguf", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--binary-manifest", required=True, type=Path)
    parser.add_argument("--out-dir", type=Path, default=Path("artifacts/p3l-w01-model"))
    options = parser.parse_args()
    try:
        return execute(options.root, options.head_sha, options.cli, options.gguf,
                       options.metadata, options.binary_manifest, options.out_dir)
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError) as exc:
        print(f"BLOCK: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
