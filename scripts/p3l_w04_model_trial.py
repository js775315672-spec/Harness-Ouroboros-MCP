#!/usr/bin/env python3
"""P3L W04: one real local Qwen CPU source proposal, never apply model output.

This file is supervisor-written EXECUTION SCAFFOLDING, not a model-authored fix.
The only model-authored material is the raw candidate saved as an artifact.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from gguf_cpu_runtime import sha256_file, verify_paths
from gguf_output_boundary import extract_completion

TARGET = "scripts/model_stagnation_gate.py"
EXPECTED_BASE_BLOB = "39e0a1e59eaf2bc04f83bee30fa00041d4d06ba0"
MODEL = "1.5b"
TASK = "p3l-w04-ast-fingerprint-helper-v1"
MAX_PROMPT = 4900

def digest(value):
    return hashlib.sha256(value).hexdigest()

def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\x00" + data).hexdigest()

def task_prompt(source):
    if type(source) is not str or not source:
        raise ValueError("trusted baseline source required")
    # The model sees real existing evaluate() code, not a synthetic task.
    scope = source[source.index("def evaluate("):]
    context = scope.split("\ndef main():", 1)[0][:2600]
    message = (
        "TASK: W04 retry-stagnation guard for the existing Python source below.\n"
        "Write a COMPLETE, STANDALONE Python function ONLY, named "
        "normalized_ast_sha256(source). It must accept Python source string, "
        "parse with ast.parse, canonicalize with ast.dump(include_attributes=False), "
        "return SHA-256 lowercase hex of the canonical AST UTF-8 encoding. "
        "Do NOT execute source, open files, run shell commands, use eval, "
        "change any tests, or output explanations or Markdown fences. "
        "Use local imports inside the function. Handle syntax errors by raising "
        "ValueError. The function must distinguish semantic changes but ignore "
        "whitespace-only formatting changes.\n"
        "Existing read-only source context (for understanding only):\n"
        + context
    )
    if len(message.encode("utf-8")) > MAX_PROMPT:
        raise ValueError("bounded prompt budget exceeded")
    return message

def render(prompt):
    if any(token in prompt for token in ("<|im_start|>", "<|im_end|>", "\x00", "\x1b", "\r")):
        raise ValueError("unsafe prompt control marker")
    return ("<|im_start|>system\nYou are a Python coding assistant. "
            "Return only one complete requested Python function, not Markdown."
            "<|im_end|>\n<|im_start|>user\n" + prompt +
            "<|im_end|>\n<|im_start|>assistant\n")

def inspect_candidate(raw):
    if type(raw) is not str or not raw or len(raw.encode("utf-8")) > 6000:
        return "model_response_rejected"
    try:
        tree = ast.parse(raw)
    except SyntaxError:
        return "model_response_rejected"
    if (len(tree.body) != 1 or type(tree.body[0]) is not ast.FunctionDef
            or tree.body[0].name != "normalized_ast_sha256"):
        return "model_response_rejected"
    # Parsing is not correctness, independence or execution attestation.
    return "untrusted_function_candidate_for_review"

def run(root, cli, gguf, metadata, output):
    root = Path(root)
    baseline = (root / TARGET).read_bytes()
    if git_blob(baseline) != EXPECTED_BASE_BLOB:
        raise ValueError("W04 original source blob changed; abort")
    source = baseline.decode("utf-8")
    prompt = task_prompt(source)
    meta = json.loads(Path(metadata).read_text(encoding="utf-8"))
    if meta.get("model") != MODEL or meta.get("license") != "apache-2.0":
        raise ValueError("not a verified license-approved 1.5B model")
    _, binary, weights = verify_paths(MODEL, cli, gguf)
    model_sha = sha256_file(weights)
    if meta.get("sha256") != model_sha:
        raise ValueError("download manifest digest mismatch")
    args = [str(binary), "--model", str(weights),
            "--prompt", render(prompt), "--n-predict", "400",
            "--ctx-size", "3072", "--threads", "4", "--temp", "0",
            "--seed", "42", "--no-display-prompt", "--simple-io",
            "--single-turn", "--jinja", "--offline",
            "--log-verbosity", "1", "--color", "off"]
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp",
           "LANG": "C.UTF-8", "OMP_NUM_THREADS": "4"}
    before = time.monotonic()
    result = subprocess.run(args, shell=False, text=True, errors="replace",
                            capture_output=True, check=False, timeout=220, env=env)
    if result.returncode != 0:
        raise ValueError("local Qwen CLI exited nonzero")
    raw, _ = extract_completion(result.stdout, max_output_bytes=6000)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # No model-generated Python is evaluated, run, or written to repository source.
    (output.parent / "model-source-candidate.txt").write_text(raw, encoding="utf-8")
    report = {
        "schema": "p3l-w04-model-trial-v1", "task": TASK,
        "trusted_baseline_git_blob": EXPECTED_BASE_BLOB,
        "baseline_sha256": digest(baseline), "prompt_sha256": digest(prompt.encode()),
        "model": MODEL, "official_model_revision": meta.get("revision"),
        "model_weights_sha256": model_sha,
        "model_called": True, "model_call_count": 1,
        "model_response_sha256": digest(raw.encode("utf-8")),
        "candidate_status": inspect_candidate(raw),
        "model_elapsed_seconds": round(time.monotonic() - before, 2),
        "model_code_executed": False, "source_checkout_modified": False,
        "external_ci_attested": False, "model_test_passed": False,
        "merge_authorized": False, "requires_human_review": True,
        "untrusted_candidate_file": "model-source-candidate.txt"
    }
    output.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--gguf", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.root, args.cli, args.gguf, args.metadata, args.output)

if __name__ == "__main__":
    main()
