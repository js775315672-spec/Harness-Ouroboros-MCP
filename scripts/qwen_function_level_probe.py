#!/usr/bin/env python3
"""First honest full-function coding probe for Qwen 7B, isolated from smoke tests.

One NEW model call, one strict function-only AST inspection, and immutable
held-out-from-prompt tests executed in disposable no-network non-root Docker.
No model source executes in the runner's Python process; code is staged only
as a data file for a read-only Docker mount. Never edits checkout or test files,
never grants Ouroboros task credit or merge approval. Failures are evidence.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from disposable_regression_compare import _docker_command
from qwen_server_cli_comparison import (
    compare_config, required_server_flags, _wait_ready, _stop_server, SERVER_PORT
)
from qwen_evolve.llama_server import LlamaServerClient, build_server_command

TASK_FILE = "benchmarks/qwen7b_function_tier_v1.lock.json"
TEST_FILE = "tests/heldout_merge_intervals.py"
EXPECTED_METHODS = 13
MAX_RESPONSE_BYTES = 6000
DOCKER_TIMEOUT_SECONDS = 90
MODEL_TIMEOUT_SECONDS = 240
ALLOWED_CALLS = frozenset({
    "ValueError", "len", "sorted", "isinstance", "int", "type",
    "list", "tuple", "min", "max", "range", "enumerate", "zip", "all", "any",
})
ALLOWED_METHODS = frozenset({"append", "sort", "extend"})
DISALLOWED_NODES = (
    ast.Import, ast.ImportFrom, ast.ClassDef, ast.AsyncFunctionDef,
    ast.With, ast.AsyncWith, ast.Global, ast.Nonlocal, ast.Delete,
    ast.Lambda, ast.Yield, ast.YieldFrom, ast.Await,
)
PROMPT = (
    "Write a complete Python function with the exact header "
    "def merge_intervals(intervals):\\n"
    "The input must be a list or tuple of pairs; each pair is a list or tuple "
    "of exactly two genuine Python integers (bool is invalid), start <= end. "
    "Raise ValueError on ANY invalid input (including an invalid outer "
    "container). Do not mutate the original input. For valid input return "
    "a NEW sorted list of (start,end) tuples that merges intervals that "
    "overlap or are adjacent as inclusive integer ranges (next start <= "
    "previous end + 1); handle negatives, duplicates, nested and empty "
    "ranges. No imports, external dependencies, helper functions, or classes. "
    "Output ONLY the source code of that one function; no Markdown, code "
    "fences, commentary, or test code."
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git_blob_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def task_lock(root):
    root = Path(root).resolve(strict=True)
    lock_file = root / TASK_FILE
    test_file = root / TEST_FILE
    for path in (lock_file, test_file):
        if (path.is_symlink() or not path.is_file()
                or not path.resolve(strict=True).is_relative_to(root)
                or path.stat().st_size > 16000):
            raise ValueError("trusted function benchmark source missing or unsafe")
    lock = json.loads(lock_file.read_text(encoding="utf-8"))
    spec = lock.get("model_parameters")
    safety = lock.get("sandbox")
    tests = test_file.read_bytes()
    if (lock.get("schema_version") != 1
            or lock.get("benchmark") != "qwen7b-function-merge-intervals-v1"
            or lock.get("function_name") != "merge_intervals"
            or lock.get("hidden_tests_file") != TEST_FILE
            or lock.get("trusted_tests_git_blob_sha") != git_blob_sha(tests)
            or lock.get("expected_heldout_test_methods") != EXPECTED_METHODS
            or lock.get("prompt_contains_tests") is not False
            or lock.get("max_model_calls") != 1
            or lock.get("retries_allowed") != 0
            or lock.get("no_merge_authority") is not True
            or spec.get("temperature") != 0 or spec.get("seed") != 42
            or spec.get("max_generated_tokens") != 480
            or any(safety.get(name) is not True for name in (
                "network_disabled", "filesystem_read_only",
                "unprivileged", "no_model_editable_tests",
                "no_model_source_checkout_writes"))):
        raise ValueError("preregistered full-function benchmark contract changed")
    return lock, digest(lock_file.read_bytes()), tests


def inspect_function(raw):
    if (not isinstance(raw, str)
            or not 20 <= len(raw.encode("utf-8")) <= MAX_RESPONSE_BYTES
            or len(raw.splitlines()) > 90
            or any(c in raw for c in ("\x00", "\x1b", "\r", chr(96)*3))):
        raise ValueError("source length, control byte or Markdown fence rejected")
    source = raw.strip() + "\n"
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as err:
        raise ValueError("model response is not a Python function") from err
    if (len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef)
            or tree.body[0].name != "merge_intervals"
            or tree.body[0].decorator_list
            or tree.body[0].args.posonlyargs
            or len(tree.body[0].args.args) != 1
            or tree.body[0].args.args[0].arg != "intervals"
            or tree.body[0].args.kwonlyargs
            or tree.body[0].args.vararg or tree.body[0].args.kwarg
            or tree.body[0].args.defaults or tree.body[0].args.kw_defaults):
        raise ValueError("only a single exact merge_intervals function is allowed")
    for node in ast.walk(tree):
        if isinstance(node, DISALLOWED_NODES):
            raise ValueError("forbidden source AST node: " + type(node).__name__)
        if (isinstance(node, (ast.Name, ast.Attribute))
                and (node.id if isinstance(node, ast.Name) else node.attr).startswith("__")):
            raise ValueError("dunder names/attributes are forbidden")
        if isinstance(node, ast.Attribute) and node.attr not in ALLOWED_METHODS:
            raise ValueError("attribute access outside narrow list methods")
        if isinstance(node, ast.Call):
            fun = node.func
            if (isinstance(fun, ast.Name) and fun.id in ALLOWED_CALLS):
                continue
            if isinstance(fun, ast.Attribute) and fun.attr in ALLOWED_METHODS:
                continue
            raise ValueError("function call outside preapproved builtins/list methods")
        if isinstance(node, ast.FunctionDef) and node is not tree.body[0]:
            raise ValueError("nested functions not in task scope")
    return source


def docker_test(workspace):
    command = _docker_command(
        workspace, "python:3.11-slim",
        ["-m", "unittest", "discover", "-s", "tests",
         "-p", "heldout_merge_intervals.py", "-v"])
    started = time.monotonic()
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                timeout=DOCKER_TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "passed": False, "tests_run": None,
                "elapsed_seconds": round(time.monotonic()-started, 3),
                "error_category": "docker_timeout", "log_tail": ""}
    output = (result.stdout + "\n" + result.stderr)[-6000:]
    m = re.search(r"Ran (\d+) tests?", output)
    count = int(m.group(1)) if m else None
    return {
        "status": "passed" if result.returncode == 0 and
                  count == EXPECTED_METHODS else "failed",
        "passed": result.returncode == 0 and count == EXPECTED_METHODS,
        "tests_run": count,
        "exit_code": result.returncode,
        "elapsed_seconds": round(time.monotonic()-started, 3),
        "log_tail": output[-1800:],
        "no_network": "--network=none" in command,
        "read_only": "--read-only" in command,
        "unprivileged": "--user=65534:65534" in command,
    }


def stage_and_compare(tests, candidate):
    with tempfile.TemporaryDirectory(prefix="qwen-7b-function-") as location:
        root = Path(location)
        os.chmod(root, 0o755)
        proof = []
        for label, code in (("baseline",
                            "def merge_intervals(intervals):\n"
                            "    raise NotImplementedError()\n"),
                            ("candidate", candidate)):
            stage = root / label
            (stage / "tests").mkdir(parents=True)
            (stage / "candidate.py").write_text(code, encoding="utf-8")
            (stage / "tests" / "heldout_merge_intervals.py").write_bytes(tests)
            for folder in (stage, stage / "tests"):
                os.chmod(folder, 0o755)
            for file in (stage / "candidate.py",
                         stage / "tests" / "heldout_merge_intervals.py"):
                os.chmod(file, 0o644)
            proof.append(docker_test(stage))
    base, proposed = proof
    success = (base.get("passed") is False
               and base.get("tests_run") == EXPECTED_METHODS
               and proposed.get("passed") is True
               and proposed.get("tests_run") == EXPECTED_METHODS
               and all(p.get(key) is True for p in (base, proposed)
                       for key in ("no_network", "read_only", "unprivileged")))
    return {"baseline_negative_control": base,
            "model_candidate": proposed,
            "status": "function_heldout_passed" if success else "function_heldout_failed",
            "model_code_executed_only_in_readonly_docker": True,
            "tests_source_unmodified": True, "merge_authorized": False}


def format_function_prompt():
    return (
        "<|im_start|>system\n"
        "You write Python functions for a code-review test. Output ONLY one "
        "Python function as source code; never Markdown, imports or tests."
        "<|im_end|>\n"
        "<|im_start|>user\n" + PROMPT + "<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


def real_probe(root, server_binary, weights, metadata, output):
    root = Path(root).resolve(strict=True)
    output = Path(output).absolute()
    if output.exists() or output.is_symlink() or output.parent.is_symlink():
        raise ValueError("do not overwrite function benchmark evidence")
    output.parent.mkdir(parents=True, exist_ok=True)
    lock, lock_hash, tests = task_lock(root)
    model = lock["model_parameters"]
    from gguf_cpu_runtime import approved_model, sha256_file
    spec = approved_model("7b")
    meta = json.loads(Path(metadata).read_text(encoding="utf-8"))
    if (meta.get("sha256") != model["weight_sha256"]
            or sha256_file(weights) != model["weight_sha256"]
            or meta.get("repository") != model["model_repository"]
            or meta.get("revision") != model["revision"]
            or spec["filename"] != Path(weights).name):
        raise ValueError("different model is not allowed in function probe")
    binary = Path(server_binary)
    if (binary.name != "llama-server" or binary.is_symlink()
            or not binary.is_file()
            or not binary.stat().st_mode & stat.S_IXUSR):
        raise ValueError("unapproved inference executable")
    required_server_flags(binary)
    client = LlamaServerClient("http://127.0.0.1:"+str(SERVER_PORT),
                               timeout=MODEL_TIMEOUT_SECONDS)
    argv = build_server_command(binary, weights, port=SERVER_PORT,
                                ctx=2048, threads=4, cache_reuse=None)
    result = {
        "benchmark": lock["benchmark"],
        "lock_sha256": lock_hash,
        "trusted_test_blob_sha": lock["trusted_tests_git_blob_sha"],
        "outcome": "model_inference_blocked",
        "model_calls": 0, "model_output": None,
        "response_sha256": None, "candidate_source_sha256": None,
        "model_output_modified_by_harness": False,
        "evaluation": None, "server_startup_seconds": None,
        "model_call_seconds": None, "merge_authorized": False,
        "ci_attested_task_completion": 0,
        "general_autonomous_coding_proven": False,
    }
    log_path = output.parent / "function-llama-server.log"
    started = time.monotonic()
    proc = None
    with open(log_path, "wb") as logs:
        try:
            proc = subprocess.Popen(
                argv, stdin=subprocess.DEVNULL, stdout=logs,
                stderr=subprocess.STDOUT, shell=False,
                start_new_session=True,
                env={**os.environ, "CUDA_VISIBLE_DEVICES": "",
                     "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1"})
            result["server_startup_seconds"] = _wait_ready(proc, client)
            prompt = format_function_prompt()
            result["prompt_sha256"] = digest(prompt.encode("utf-8"))
            call_start = time.monotonic()
            raw = client.complete(prompt, n_predict=model["max_generated_tokens"],
                                  temperature=0, seed=42, cache_prompt=False)
            result["model_calls"] = 1
            result["model_call_seconds"] = round(time.monotonic()-call_start, 3)
            result["model_output"] = raw
            result["response_sha256"] = digest(raw.encode("utf-8"))
            try:
                candidate = inspect_function(raw)
                result["candidate_source_sha256"] = digest(candidate.encode("utf-8"))
                result["evaluation"] = stage_and_compare(tests, candidate)
                result["outcome"] = result["evaluation"]["status"]
            except (ValueError, SyntaxError) as error:
                result["outcome"] = "static_ast_rejected"
                result["reason"] = type(error).__name__ + ": " + str(error)[:160]
        except (OSError, ValueError, subprocess.TimeoutExpired,
                Exception) as error:
            # Never claim model success on a model/server infrastructure failure.
            result["outcome"] = "model_or_infrastructure_failed"
            result["error_type"] = type(error).__name__
            result["error_category"] = str(error)[:160]
        finally:
            _stop_server(proc)
    result["total_elapsed_seconds"] = round(time.monotonic()-started, 3)
    raw_report = (json.dumps(result, ensure_ascii=False,
                             sort_keys=True, indent=2) + "\n").encode("utf-8")
    if len(raw_report) > 200_000:
        raise ValueError("function report exceeds evidence size")
    output.write_bytes(raw_report)
    payload = log_path.read_bytes()
    if len(payload) > 100_000:
        log_path.write_bytes(payload[-100_000:])
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--gguf", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = real_probe(args.root, args.server, args.gguf,
                            args.metadata, args.report)
        print(json.dumps({"outcome": report["outcome"],
                          "model_calls": report["model_calls"],
                          "candidate_sha256": report["candidate_source_sha256"],
                          "merge_authorized": False}, sort_keys=True))
        # Evaluation failure is a VALID negative benchmark observation,
        # not an infrastructure success claim.
        return 0 if report["outcome"] in (
            "function_heldout_passed", "function_heldout_failed",
            "static_ast_rejected") else 2
    except (OSError, ValueError, TypeError, KeyError,
            json.JSONDecodeError) as error:
        print(json.dumps({"outcome": "blocked",
                          "error_type": type(error).__name__,
                          "error_category": str(error)[:120]}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
