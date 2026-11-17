#!/usr/bin/env python3
"""W06 coordinator bootstrap: one read-only model attempt for W01 contract.

This glue is GPT-6-authored infrastructure, NEVER model-authored output.
No source edits, shell commands, GitHub writes, auto-promotion or model retries.
Only a bounded generated Markdown artifact can be produced by the model.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from gguf_cpu_runtime import approved_model, sha256_file, verify_paths
from gguf_output_boundary import extract_completion
from p3l_w01_request import build_request, verified_head

MODEL = "1.5b"
MAX_RESPONSE = 6000
SYSTEM = ("You write a concise Korean Markdown validation contract using only "
          "the supplied task and original function. Give valid and invalid "
          "examples as a table. Do not execute code, invent test results, "
          "change source files, or include runnable shell commands.")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def verified_request(root, sha, request):
    if type(request) is not dict or request != build_request(root, sha):
        raise ValueError("W01 task request differs from exact source/spec/commit")
    if (request["worker"] != "W01" or request["model_calls"] != 0
            or request["executor_connected"] is not False
            or request["merge_authorized"] is not False):
        raise ValueError("W01 request already claims execution or promotion")
    return request


def format_w01(prompt):
    if type(prompt) is not str or not 1 <= len(prompt.encode("utf-8")) <= 5000:
        raise ValueError("invalid W01 prompt budget")
    if any(part in prompt for part in ("<|im_start|>", "<|im_end|>",
                                       "\x00", "\x1b", "\r")):
        raise ValueError("untrusted role/control marker in prompt")
    return ("<|im_start|>system\n" + SYSTEM + "<|im_end|>\n"
            "<|im_start|>user\n" + prompt + "<|im_end|>\n"
            "<|im_start|>assistant\n")


def verified_model(cli, gguf, meta):
    info = approved_model(MODEL)
    obj = json.loads(Path(meta).read_text(encoding="utf-8"))
    spec, binary, weights = verify_paths(MODEL, cli, gguf)
    if (obj.get("model") != MODEL or obj.get("repository") != spec["repo"]
            or obj.get("filename") != spec["filename"]
            or obj.get("license") != "apache-2.0"
            or obj.get("quantization") != "Q4_K_M"
            or obj.get("secret_or_paid_api_used") is not False
            or not isinstance(obj.get("revision"), str)
            or len(obj["revision"]) != 40
            or any(c not in "0123456789abcdef" for c in obj["revision"])
            or obj.get("sha256") != sha256_file(weights)):
        raise ValueError("unverified model weight provenance")
    return binary, weights, obj


def verify_candidate(response):
    if type(response) is not str:
        raise ValueError("missing model response")
    if not 40 <= len(response.encode("utf-8")) <= MAX_RESPONSE:
        raise ValueError("empty, truncated, or oversized document candidate")
    if any(c in response for c in ("\x00", "\x1b", "\r")):
        raise ValueError("unsafe model response controls")
    return response


def one_model_call(cli, gguf, rendered_prompt):
    command = [str(cli), "--model", str(gguf),
               "--prompt", rendered_prompt, "--n-predict", "960",
               "--ctx-size", "3072", "--threads", "4", "--temp", "0",
               "--seed", "42", "--no-display-prompt", "--simple-io",
               "--single-turn", "--jinja", "--offline",
               "--log-verbosity", "1", "--color", "off"]
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp",
           "LANG": "C.UTF-8", "OMP_NUM_THREADS": "4"}
    proc = subprocess.run(command, capture_output=True, text=True,
                          errors="replace", timeout=240, env=env,
                          shell=False, check=False)
    if proc.returncode:
        raise ValueError("bounded model process returned nonzero exit code")
    result, _ = extract_completion(proc.stdout, max_output_bytes=MAX_RESPONSE)
    return verify_candidate(result)


def output_dir(root, relative):
    p = Path(relative)
    if p.is_absolute() or ".." in p.parts or p.parts[:2] != ("artifacts", "p3l-w01-model"):
        raise ValueError("output must be artifacts/p3l-w01-model/")
    target = root / p
    if any(part.is_symlink() for part in (target, *target.parents) if part != root.parent):
        raise ValueError("symlink output path forbidden")
    target.mkdir(parents=True, exist_ok=True)
    if not target.resolve().is_relative_to(root):
        raise ValueError("output escaped checkout")
    if (target / "record.json").exists() or (target / "model_candidate.md").exists():
        raise ValueError("refusing overwrite of model evidence")
    return target


def run(root, sha, request_path, cli, gguf, metadata, out):
    verified_head(root, sha)
    request = json.loads(Path(request_path).read_text(encoding="utf-8"))
    verified_request(root, sha, request)
    binary, weights, model_record = verified_model(cli, gguf, metadata)
    rendered = format_w01(request["prompt"])
    out_dir = output_dir(root, out)
    record = {
        "schema": "p3l-w01-model-attempt-v1", "worker": "W01",
        "runner_role": "W06 bootstrap executor", "review_commit": sha,
        "request_sha256": request["request_sha256"],
        "source_sha256": request["source_sha256"],
        "spec_sha256": request["spec_sha256"],
        "prompt_sha256": request["prompt_sha256"],
        "rendered_prompt_sha256": digest(rendered.encode("utf-8")),
        "binary_sha256": sha256_file(binary),
        "model": MODEL, "model_revision": model_record["revision"],
        "weights_sha256": model_record["sha256"], "model_calls": 0,
        "candidate_sha256": None, "candidate_verified": False,
        "harness_25_tests_passed": False, "merge_authorized": False,
        "executor_code_origin": "GPT-6 coordinator bootstrap",
        "candidate_code_origin": "awaiting actual Qwen model call",
        "outcome": "blocked_before_model_call"
    }
    try:
        # Record a single invocation attempt BEFORE starting the subprocess.
        record["model_calls"] = 1
        record["outcome"] = "model_invocation_failed"
        response = one_model_call(binary, weights, rendered)
        candidate = out_dir / "model_candidate.md"
        with candidate.open("x", encoding="utf-8") as handle:
            handle.write(response + "\n")
        record["candidate_sha256"] = digest(response.encode("utf-8"))
        record["candidate_code_origin"] = "Qwen CPU inference; raw unreviewed Markdown"
        record["outcome"] = "generated_unreviewed"
    except (ValueError, subprocess.TimeoutExpired, OSError, UnicodeError) as exc:
        record["failure_reason"] = type(exc).__name__ + ": " + str(exc)[:180]
    with (out_dir / "record.json").open("x", encoding="utf-8") as handle:
        json.dump(record, handle, sort_keys=True, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(json.dumps({k: record[k] for k in
                      ("worker", "outcome", "model_calls", "candidate_verified",
                       "merge_authorized")}, sort_keys=True))
    return 0 if record["outcome"] == "generated_unreviewed" else 2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--gguf", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("artifacts/p3l-w01-model"))
    opts = parser.parse_args()
    try:
        return run(opts.root.resolve(strict=True), opts.head_sha, opts.request,
                   opts.cli, opts.gguf, opts.metadata, opts.out)
    except (ValueError, OSError, UnicodeError, subprocess.SubprocessError) as exc:
        print("BLOCK preflight: " + str(exc)[:180], file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
