#!/usr/bin/env python3
"""Opt-in controlled CPU A/B: repeated llama-completion vs resident llama-server.

NOT a general autonomous coding test. Same pinned official 7B GGUF, ChatML
prompt, temperature 0, seed 42, max tokens 140, context 2048, 4 CPU threads.
No grammar, feedback retry or speculative decoding in either condition.
The only intended architectural difference is process/model residency.
The server's prompt cache is explicitly DISABLED (weights remain resident).

Only a numeric 127.0.0.1 origin can be contacted. No arbitrary shell/model
commands, no source writes, paid API, credentials, external network server,
PR merge, live trading or task queue advancement.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import statistics
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from gguf_cpu_runtime import CPUInference, approved_model, sha256_file
from gguf_output_boundary import extract_completion
from qwen_chatml_prompt import format_chatml
from bounded_qwen_autonomous_worker import TASKS, parse, request_prompt
from frozen_qwen_benchmark_20 import read_config
from qwen_evolve.llama_server import (
    LlamaServerClient, build_server_command, _require_loopback
)

LLAMA_CPP_SHA = "4e5116f47619dac4180c3007ef02a383f347554c"
SERVER_PORT = 18080
REPEATS = 2
SERVER_STARTUP_TIMEOUT = 150
RSS_LIMIT_KIB = 12 * 1024 * 1024
PROCESS_TIMEOUT_SECONDS = 150
MAX_REPORT_BYTES = 120_000


def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


def bounded_process_path(path, expected):
    path = Path(path)
    if (path.is_symlink() or not path.is_file() or path.name != expected
            or not path.stat().st_mode & stat.S_IXUSR):
        raise ValueError("unexpected non-executable llama.cpp binary")
    return path.resolve(strict=True)


def compare_config(root, cli, server, gguf, metadata):
    cfg, lock_sha = read_config(root)
    spec = approved_model("7b")
    meta = json.loads(Path(metadata).read_text(encoding="utf-8"))
    checksum = sha256_file(gguf)
    if (cfg["model"]["repository"] != spec["repo"]
            or cfg["model"]["file"] != spec["filename"]
            or cfg["model"]["sha256"] != checksum
            or meta.get("sha256") != checksum
            or meta.get("revision") != cfg["model"]["revision"]
            or meta.get("license") != "apache-2.0"
            or cfg["runtime"]["llama_cpp_commit"] != LLAMA_CPP_SHA
            or cfg["runtime"]["threads"] != 4
            or cfg["runtime"]["ctx_size"] != 2048
            or cfg["runtime"]["seed"] != 42
            or cfg["runtime"]["temperature"] != 0
            or cfg["runtime"]["n_predict"] != 140):
        raise ValueError("model provenance or fixed shared inference settings differ")
    cli_bin = bounded_process_path(cli, "llama-completion")
    server_bin = bounded_process_path(server, "llama-server")
    # They must be built from the same immutable llama.cpp checkout.
    if cli_bin.parent != server_bin.parent:
        raise ValueError("inference binaries not built in the same directory")
    return cfg, lock_sha, cli_bin, server_bin


def fixed_tasks():
    # Identical prompt sequence for both engines. Two distinct tasks *twice*.
    return [(i, request_prompt(i, 1)) for _ in range(REPEATS)
            for i in range(len(TASKS))]


def score_output(raw, point, canonical=True):
    if not isinstance(raw, str):
        return {"ast_accepted": False, "error": "invalid_nonstring_output",
                "response_sha256": None, "response": None}
    try:
        normalized, _ = extract_completion(raw)
    except ValueError as error:
        return {"ast_accepted": False, "error": type(error).__name__,
                "response_sha256": hash_bytes(raw.encode("utf-8")), "response": raw}
    try:
        expression = parse(normalized, point)
        return {"ast_accepted": True, "error": None,
                "response_sha256": hash_bytes(raw.encode("utf-8")),
                "response": raw, "accepted_expression": expression}
    except (ValueError, SyntaxError) as error:
        return {"ast_accepted": False, "error": type(error).__name__,
                "response_sha256": hash_bytes(raw.encode("utf-8")), "response": raw}


def _sample_stat(path, key):
    try:
        data = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    for line in data.splitlines():
        if line.startswith(key + ":"):
            bits = line.split()
            if len(bits) >= 2 and bits[1].isdigit():
                return int(bits[1])
    return None


def server_memory(proc):
    if proc is None:
        return None
    return {
        "rss_kib": _sample_stat(f"/proc/{proc.pid}/status", "VmRSS"),
        "peak_rss_kib": _sample_stat(f"/proc/{proc.pid}/status", "VmHWM"),
    }


def _public_loopback_health(client):
    # No access to arbitrary model-supplied host or URL.
    _require_loopback(client.base_url)
    request = urllib.request.Request(client.base_url + "/health")
    try:
        with client._opener.open(request, timeout=3) as response:
            return response.status == 200
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return False


def _wait_ready(proc, client, startup_timeout=SERVER_STARTUP_TIMEOUT):
    begun = time.monotonic()
    while time.monotonic() - begun < startup_timeout:
        if proc.poll() is not None:
            raise ValueError("pinned llama-server exited before ready")
        memory = server_memory(proc)
        if (memory and memory.get("rss_kib") is not None
                and memory["rss_kib"] > RSS_LIMIT_KIB):
            raise ValueError("llama-server exceeded resident memory budget")
        if _public_loopback_health(client):
            return round(time.monotonic() - begun, 3)
        time.sleep(0.5)
    raise ValueError("llama-server health timeout")


def required_server_flags(server_bin):
    # --cache-reuse and --model-draft intentionally excluded:
    # those options were not verified against the pinned binary.
    needed = ("--model", "--host", "--port", "--ctx-size", "--threads", "--parallel")
    result = subprocess.run([str(server_bin), "--help"], shell=False,
                            capture_output=True, text=True,
                            timeout=15, check=False, errors="replace")
    text = result.stdout + result.stderr
    missing = [flag for flag in needed if flag not in text]
    if missing:
        raise ValueError("pinned llama-server missing approved flags: " + ", ".join(missing))
    return {"approved_cli_flags": list(needed),
            "help_sha256": hash_bytes(text.encode("utf-8")),
            "help_exit_code": result.returncode}


def run_cli(cli_bin, weights, tasks):
    runner = CPUInference("7b", cli_bin, weights, timeout_seconds=PROCESS_TIMEOUT_SECONDS)
    calls = []
    start = time.monotonic()
    for index, prompt in tasks:
        started = time.monotonic()
        result = {"task_id": TASKS[index][0],
                  "prompt_sha256": hash_bytes(format_chatml(prompt).encode()),
                  "engine": "llama-completion", "response": None,
                  "ast_accepted": False}
        try:
            raw = runner.generate(prompt)
            result.update(score_output(raw, TASKS[index][1]))
            result["inference_audit"] = runner.calls[-1]
        except (ValueError, OSError) as error:
            result["error"] = type(error).__name__
            result["error_category"] = str(error)[:120]
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        calls.append(result)
    return {
        "mode": "cli_separate_process_per_request",
        "warm_model_residency": False,
        "call_results": calls,
        "four_calls_wall_seconds": round(time.monotonic() - start, 3),
        "peak_child_rss_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
    }


def _stop_server(proc):
    if proc is None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=5)


def run_server(server_bin, weights, tasks, log_path):
    client = LlamaServerClient("http://127.0.0.1:" + str(SERVER_PORT),
                               timeout=PROCESS_TIMEOUT_SECONDS)
    argv = build_server_command(server_bin, weights, port=SERVER_PORT,
                                ctx=2048, threads=4, cache_reuse=None)
    if ("--model-draft" in argv or "--cache-reuse" in argv or
            "--host" not in argv or argv[argv.index("--host")+1] != "127.0.0.1"):
        raise ValueError("server command not limited to approved local mode")
    env = dict(os.environ)
    env.update({"CUDA_VISIBLE_DEVICES": "", "OMP_NUM_THREADS": "4",
                "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1"})
    result = {
        "mode": "single_resident_local_server",
        "warm_model_residency": True, "cache_prompt": False,
        "server_argv_flags": [v for v in argv if v.startswith("--")],
        "call_results": [],
        "startup_seconds": None, "peak_server_rss_kib": None,
        "four_calls_wall_seconds": None,
    }
    proc = None
    start = time.monotonic()
    with open(log_path, "wb") as logfile:
        try:
            proc = subprocess.Popen(
                argv, stdin=subprocess.DEVNULL,
                stdout=logfile, stderr=subprocess.STDOUT,
                shell=False, start_new_session=True, env=env)
            result["startup_seconds"] = _wait_ready(proc, client)
            result["server_pid_not_exported"] = True
            begin_calls = time.monotonic()
            for index, prompt in tasks:
                started = time.monotonic()
                row = {"task_id": TASKS[index][0],
                       "prompt_sha256": hash_bytes(format_chatml(prompt).encode()),
                       "engine": "llama-server", "response": None,
                       "ast_accepted": False, "cache_prompt": False}
                try:
                    raw = client.complete(format_chatml(prompt), n_predict=140,
                                          temperature=0, seed=42, cache_prompt=False)
                    row.update(score_output(raw, TASKS[index][1]))
                    row["server_metadata"] = client.calls[-1]
                except (OSError, ValueError, urllib.error.URLError,
                        json.JSONDecodeError) as error:
                    row["error"] = type(error).__name__
                    row["error_category"] = str(error)[:120]
                row["elapsed_seconds"] = round(time.monotonic() - started, 3)
                result["call_results"].append(row)
                mem = server_memory(proc)
                if mem and mem.get("peak_rss_kib") is not None:
                    result["peak_server_rss_kib"] = max(
                        result["peak_server_rss_kib"] or 0, mem["peak_rss_kib"])
                if (mem and mem.get("rss_kib") is not None
                        and mem["rss_kib"] > RSS_LIMIT_KIB):
                    raise ValueError("server exceeded resident memory budget during request")
            result["four_calls_wall_seconds"] = round(
                time.monotonic() - begin_calls, 3)
        finally:
            _stop_server(proc)
    result["startup_plus_calls_wall_seconds"] = round(time.monotonic()-start, 3)
    # Bound persisted server logs; stdout is generated by a known pinned binary.
    data = Path(log_path).read_bytes()
    if len(data) > 100_000:
        Path(log_path).write_bytes(data[-100_000:])
    return result


def summarize(cli, server):
    left, right = cli.get("call_results", []), server.get("call_results", [])
    equal_prompts = (len(left) == len(right) == REPEATS*len(TASKS)
                     and all(a["prompt_sha256"] == b["prompt_sha256"]
                             and a["task_id"] == b["task_id"]
                             for a, b in zip(left, right)))
    def summarize_one(records):
        durations = [x["elapsed_seconds"] for x in records]
        return {
            "attempts": len(records),
            "ast_accepted": sum(x.get("ast_accepted") is True for x in records),
            "per_call_median_seconds": round(statistics.median(durations), 3)
                if durations else None,
            "first_call_seconds": durations[0] if durations else None,
            "remaining_calls_median_seconds": round(
                statistics.median(durations[1:]), 3) if len(durations) > 1 else None,
        }
    a, b = summarize_one(left), summarize_one(right)
    ratio = (round(a["per_call_median_seconds"] / b["per_call_median_seconds"], 3)
             if equal_prompts and b["per_call_median_seconds"] and
             a["per_call_median_seconds"] else None)
    return {
        "equal_prompt_sequence": equal_prompts,
        "cli": a, "server": b,
        "median_request_latency_speedup_if_greater_than_one": ratio,
        "server_startup_seconds": server.get("startup_seconds"),
        "cli_batch_wall_seconds": cli.get("four_calls_wall_seconds"),
        "server_startup_plus_batch_wall_seconds":
            server.get("startup_plus_calls_wall_seconds"),
        "cli_child_maxrss_kib_cumulative_highwater":
            cli.get("peak_child_rss_kib"),
        "server_process_vm_hwm_kib": server.get("peak_server_rss_kib"),
        "interpretation": ("Process residency affects latency. Memory counters "
            "have different scopes and are not a directly comparable measurement. "
            "Same fixed trivial code-completion prompts are not a coding skill benchmark."),
        "autonomous_coding_proven": False,
        "source_checkout_modified": False,
        "merge_authorized": False,
    }


def experiment(root, cli_path, server_path, gguf, provenance, output):
    root = Path(root).resolve(strict=True)
    output = Path(output).absolute()
    if output.exists() or output.is_symlink() or output.parent.is_symlink():
        raise ValueError("refusing to overwrite preexisting report")
    output.parent.mkdir(parents=True, exist_ok=True)
    cfg, lock_sha, cli_bin, server_bin = compare_config(
        root, cli_path, server_path, gguf, provenance)
    tasks = fixed_tasks()
    saved = {"schema_version": 1,
             "experiment": "qwen7b-resident-server-vs-cli-v1",
             "comparison_kind": "identical_model_prompt_sampling_no_grammar_no_retry",
             "benchmark_lock_sha256": lock_sha,
             "pinned_llama_cpp_sha": LLAMA_CPP_SHA,
             "weight_sha256": cfg["model"]["sha256"],
             "model_revision": cfg["model"]["revision"],
             "temperature": 0, "seed": 42, "threads": 4,
             "ctx_size": 2048, "n_predict": 140, "cache_prompt": False,
             "experimental_task_count": len(tasks),
             "cli": None, "server": None, "summary": None,
             "status": "infrastructure_blocked",
             "merge_authorized": False}
    try:
        saved["server_binary_compatible"] = required_server_flags(server_bin)
        saved["cli"] = run_cli(cli_bin, gguf, tasks)
        saved["server"] = run_server(
            server_bin, gguf, tasks, output.parent / "llama-server-last.log")
        saved["summary"] = summarize(saved["cli"], saved["server"])
        saved["status"] = ("comparison_measured" if
                           saved["summary"]["equal_prompt_sequence"] else
                           "invalid_mismatched_prompts")
    except (OSError, ValueError, subprocess.TimeoutExpired,
            urllib.error.URLError) as error:
        saved["error_type"] = type(error).__name__
        saved["error_category"] = str(error)[:170]
    raw = (json.dumps(saved, indent=2, ensure_ascii=False,
                      sort_keys=True) + "\n").encode("utf-8")
    if len(raw) > MAX_REPORT_BYTES:
        raise ValueError("comparison evidence exceeds bounded report size")
    output.write_bytes(raw)
    print(json.dumps({"status": saved["status"],
                      "summary": saved.get("summary"),
                      "merge_authorized": False}, ensure_ascii=False))
    return saved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--gguf", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = experiment(args.root, args.cli, args.server, args.gguf,
                        args.provenance, args.report)
    return 0 if report["status"] == "comparison_measured" else 2


if __name__ == "__main__":
    sys.exit(main())
