#!/usr/bin/env python3
"""P3L W01: execute ONE allowlisted Qwen CPU call; preserve raw Markdown for human review.

Coordinator-authored execution adapter. This is NOT a model-authored W01 deliverable.
Output is an untrusted artifact only, not a repository commit, CI attestation or approval.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from p3l_w01_request import build_request, verified_head
from gguf_cpu_runtime import approved_model, sha256_file, verify_paths

MODEL = "7b"
EXPECTED_FILE = "qwen2.5-coder-7b-instruct-q4_k_m.gguf"
MODEL_TIMEOUT = 900
OUTPUT_MAX_BYTES = 24_000
CHATML_START = "<|im_start|>"
CHATML_END = "<|im_end|>"
TERMINATOR = "[end of text]"
REQUIRED_TERMS = ("fixes", "change", "W02", "W03", "128", "256", "12", "UTF-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def format_document_prompt(task):
    """Only the exact SHA-bound task is accepted; no external prompt or executable code."""
    if not isinstance(task, str) or not 1 <= len(task.encode("utf-8")) <= 5000:
        raise ValueError("invalid request prompt")
    if any(token in task for token in (CHATML_START, CHATML_END, "\x00", "\x1b", "\r")):
        raise ValueError("unsafe role/control marker in task")
    system = (
        "You are Harness-Ouroboros W01, a documentation worker. "
        "Write ONLY a Korean Markdown requirements document. "
        "Use a table of valid and invalid examples with all other fields fixed valid. "
        "Explain current Python validation versus proposed requirements without claiming "
        "that any test ran. Include W02 and W03 handoffs and unresolved policy questions. "
        "Do not output commands, Python code, JSON, or a fenced code block. "
        "Your output is untrusted and will receive independent GPT-6 review."
    )
    return (
        CHATML_START + "system\n" + system + CHATML_END + "\n"
        + CHATML_START + "user\n" + task + CHATML_END + "\n"
        + CHATML_START + "assistant\n"
    )


def extract_document(stdout):
    if not isinstance(stdout, str):
        raise ValueError("missing model text")
    raw = stdout.encode("utf-8", errors="strict")
    if not 100 <= len(raw) <= OUTPUT_MAX_BYTES:
        raise ValueError("model text outside documentation budget")
    if any(ch in stdout for ch in ("\x00", "\x1b", "\r")):
        raise ValueError("model text contains terminal control bytes")
    cleaned = stdout.strip()
    if cleaned.endswith(TERMINATOR):
        candidate = cleaned[:-len(TERMINATOR)]
        if candidate and candidate[-1].isspace():
            cleaned = candidate.strip()
    if not cleaned or CHATML_START in cleaned or CHATML_END in cleaned:
        raise ValueError("model output includes unexpected role token")
    if not all(x in cleaned for x in REQUIRED_TERMS):
        raise ValueError("model output misses required contract markers; preserve raw")
    return cleaned + "\n"


def read_model_provenance(root, gguf_path, meta_path):
    model_spec, cli, weights = verify_paths(MODEL, root / "vendor/llama.cpp/build/bin/llama-completion", gguf_path)
    if weights.name != EXPECTED_FILE or model_spec["license"] != "apache-2.0":
        raise ValueError("unauthorized model")
    if meta_path.is_symlink() or not meta_path.is_file():
        raise ValueError("missing model provenance")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    actual_sha = sha256_file(weights)
    if (meta.get("model") != MODEL or meta.get("filename") != EXPECTED_FILE
            or meta.get("license") != "apache-2.0"
            or meta.get("sha256") != actual_sha
            or meta.get("secret_or_paid_api_used") is not False
            or re.fullmatch("[a-f0-9]{40}", str(meta.get("revision"))) is None):
        raise ValueError("model provenance mismatch")
    return cli, weights, meta


def invoke_once(cli, weights, prompt):
    command = [
        str(cli), "--model", str(weights), "--prompt", prompt,
        "--n-predict", "2048", "--ctx-size", "8192", "--threads", "4",
        "--temp", "0", "--no-display-prompt", "--simple-io",
        "--single-turn", "--jinja", "--offline",
        "--log-verbosity", "1", "--color", "off",
    ]
    # No inherited credentials, shell, user-controlled executable, or model output execution.
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp",
           "LANG": "C.UTF-8", "OMP_NUM_THREADS": "4",
           "CUDA_VISIBLE_DEVICES": ""}
    started = time.monotonic()
    result = subprocess.run(command, shell=False, text=True,
                            capture_output=True, check=False,
                            timeout=MODEL_TIMEOUT, env=env, errors="replace")
    return result, round(time.monotonic() - started, 3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--request", type=Path, default=Path("artifacts/p3l-w01/request.json"))
    parser.add_argument("--model-provenance", type=Path,
                        default=Path("artifacts/p3l-w01/model-provenance.json"))
    opts = parser.parse_args()
    root = opts.root.resolve(strict=True)
    artifacts = root / "artifacts/p3l-w01"
    artifacts.mkdir(parents=True, exist_ok=True)
    summary = {"schema": "p3l-w01-model-execution-v1", "worker": "W01",
               "head_sha": opts.head_sha, "model": MODEL,
               "model_calls": 0, "candidate_verified": False,
               "merge_authorized": False, "repo_modified": False,
               "result": "BLOCKED_BEFORE_MODEL", "executor": "llama.cpp-CPU",
               "candidate_path": None, "response_sha256": None}
    try:
        verified_head(root, opts.head_sha)
        request = json.loads((root / opts.request).read_text(encoding="utf-8"))
        expected = build_request(root, opts.head_sha)
        if request != expected or request["allowed_output"] != ["docs/p3l/ledger-input-contract.ko.md"]:
            raise ValueError("W01 request must match reviewed original and task spec")
        summary["request_sha256"] = request["request_sha256"]
        prompt = format_document_prompt(request["prompt"])
        summary["formatted_prompt_sha256"] = sha(prompt.encode("utf-8"))
        cli, weights, meta = read_model_provenance(root, root / "models" / EXPECTED_FILE,
                                                   root / opts.model_provenance)
        summary["model_sha256"] = meta["sha256"]
        summary["model_revision"] = meta["revision"]
        # Count the attempted invocation even if the runner times out or errors.
        summary["model_calls"] = 1
        result, elapsed = invoke_once(cli, weights, prompt)
        summary["duration_seconds"] = elapsed
        summary["model_exit_code"] = result.returncode
        summary["stderr_sha256"] = sha(result.stderr.encode("utf-8"))
        raw_bytes = result.stdout.encode("utf-8")
        summary["response_sha256"] = sha(raw_bytes)
        summary["response_bytes"] = len(raw_bytes)
        if len(raw_bytes) > OUTPUT_MAX_BYTES:
            raise ValueError("raw output exceeded cap; do not write oversized artifact")
        (artifacts / "raw-model-response.txt").write_bytes(raw_bytes)
        if result.returncode:
            raise ValueError("model process returned nonzero")
        document = extract_document(result.stdout)
        doc_bytes = document.encode("utf-8")
        (artifacts / "ledger-input-contract.ko.md").write_bytes(doc_bytes)
        summary["document_sha256"] = sha(doc_bytes)
        summary["candidate_path"] = "docs/p3l/ledger-input-contract.ko.md"
        summary["result"] = "MODEL_GENERATED_UNVERIFIED"
        print("W01 model-generated document artifact created; NOT accepted until independent review")
        return_code = 0
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError,
            subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        summary["result"] = "BLOCKED_OR_GENERATION_FAILED"
        summary["error_type"] = type(exc).__name__
        summary["error"] = str(exc)[:300]
        print("W01 execution blocked:", str(exc), file=sys.stderr)
        return_code = 2
    (artifacts / "execution-evidence.json").write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    return return_code


if __name__ == "__main__":
    sys.exit(main())
