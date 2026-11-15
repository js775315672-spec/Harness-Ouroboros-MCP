#!/usr/bin/env python3
"""One-model, one-task GGUF benchmark sharing the Transformers AST/Docker gate.

A CI job is one isolated trial for one CPU model and runtime. Per-model
first-attempt and retry outcomes are indicators, not statistical success rates.
Never modifies source, creates PRs, merges, deploys, or places live orders.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import time

try:
    from .gguf_cpu_runtime import CPUInference, approved_model, sha256_file
    from .qwen_semantic_repair_loop import run_loop
    from .qwen_semantic_disposable_compare import compare_line
    from .qwen_source_guard import TARGET
except ImportError:
    from gguf_cpu_runtime import CPUInference, approved_model, sha256_file
    from qwen_semantic_repair_loop import run_loop
    from qwen_semantic_disposable_compare import compare_line
    from qwen_source_guard import TARGET


def benchmark(model, cli, gguf, metadata, root=Path("."), timeout=150):
    spec = approved_model(model)
    meta = json.loads(Path(metadata).read_text(encoding="utf-8"))
    if (not isinstance(meta, dict) or meta.get("model") != model or
            meta.get("repository") != spec["repo"] or
            meta.get("filename") != spec["filename"] or
            meta.get("license") != "apache-2.0" or
            meta.get("quantization") != "Q4_K_M"):
        raise ValueError("download provenance or license mismatch")
    expected_sha = meta.get("sha256")
    if (not isinstance(expected_sha, str) or len(expected_sha) != 64 or
            sha256_file(gguf) != expected_sha):
        raise ValueError("GGUF SHA256 provenance mismatch")
    root = Path(root).resolve(strict=True)
    source_file = root / TARGET
    if source_file.is_symlink() or not source_file.is_file():
        raise ValueError("unsafe trusted source file")
    original = source_file.read_bytes()
    source = original.decode("utf-8")
    inference = CPUInference(model, cli, gguf, timeout_seconds=timeout)
    start = time.perf_counter()
    result = run_loop(
        source,
        inference.generate,
        lambda proposed: compare_line(root, proposed),
        max_attempts=3)
    elapsed = round(time.perf_counter() - start, 3)
    if source_file.read_bytes() != original:
        raise ValueError("trusted checkout was unexpectedly modified")
    candidate = result.pop("candidate")
    attempts = result["attempts"]
    first = bool(attempts and attempts[0]["status"] == "isolated_source_repair_passed")
    passed = candidate is not None and result["status"] == "isolated_source_repair_passed"
    return {
        "schema_version": 1, "task": "feedback_cycle_guard",
        "engine": "llama.cpp", "model": model,
        "model_repo": spec["repo"], "gguf_quantization": "Q4_K_M",
        "gguf_sha256": expected_sha, "model_revision": meta.get("revision"),
        "llama_cli_sha256": sha256_file(cli),
        "source_sha256": hashlib.sha256(original).hexdigest(),
        "first_attempt_passed": first,
        "passed_within_retry_budget": passed,
        "passed_after_retry": passed and not first,
        "total_elapsed_seconds": elapsed,
        "peak_child_rss_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        "inference_calls": inference.calls,
        "model_calls": result["model_calls"],
        "docker_comparisons": result["docker_comparisons"],
        "attempts": attempts,
        "outcome": result["status"],
        "candidate": candidate,  # only present after full Docker pass
        "last_comparison": result["last_comparison"],
        "trial_count": 1, "statistical_success_rate_established": False,
        "source_checkout_modified": False, "merge_authorized": False,
        "paid_api_used": False, "user_secret_required": False,
        "not_a_live_trading_experiment": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, choices=["0.5b", "1.5b", "7b"])
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--gguf", type=Path, required=True)
    parser.add_argument("--download-metadata", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--timeout-seconds", type=int, default=150)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = {
        "outcome": "blocked", "engine": "llama.cpp", "model": args.model,
        "source_checkout_modified": False, "merge_authorized": False,
    }
    try:
        result = benchmark(args.model, args.cli, args.gguf, args.download_metadata,
                           root=args.root, timeout=args.timeout_seconds)
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        # Never put untrusted model output or external subprocess logs in output.
        result["error_code"] = "benchmark_execution_blocked"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in
        ("engine", "model", "outcome", "source_checkout_modified", "merge_authorized")
        if k in result}, sort_keys=True))
    # A completed, truthfully logged failure is a valid experiment outcome.
    return 2 if result["outcome"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
