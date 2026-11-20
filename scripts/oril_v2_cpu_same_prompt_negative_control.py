#!/usr/bin/env python3
"""Real CPU same-prompt negative control for ORIL paired Qwen benchmark.

Random tiny Qwen2, independent cold-start subprocesses, no pretrained model,
GPU training, LoRA adapter, or quality evidence. A nonzero paired difference
when BOTH prompts are identical indicates measurement/order noise.
"""
import argparse
import json
import math
from pathlib import Path
import statistics
import tempfile

from oril_v2_tiny_qwen_cpu_forward_smoke import build_tiny_checkpoint, invoke
from oril_v2_tiny_qwen_cpu_paired_benchmark import SHORT


def summarize_negative_control(pairs):
    if type(pairs) is not list or len(pairs) < 4:
        raise ValueError("at least four pairs required")
    observed = {"a_first": [], "b_first": []}
    raw = []
    for p in pairs:
        if not isinstance(p, dict) or set(p) != {"order", "a", "b"}:
            raise ValueError("invalid negative control pair")
        if p["order"] not in observed:
            raise ValueError("invalid observed order")
        for label in ("a", "b"):
            v = p[label]
            if not isinstance(v, dict) or set(v) != {"input_tokens", "output_tokens", "elapsed_seconds"}:
                raise ValueError("invalid call record")
            if (type(v["input_tokens"]) is not int or v["input_tokens"] < 1 or
                type(v["output_tokens"]) is not int or v["output_tokens"] < 1 or
                type(v["elapsed_seconds"]) not in (int, float) or
                not math.isfinite(v["elapsed_seconds"]) or v["elapsed_seconds"] < 0):
                raise ValueError("invalid measured value")
        if p["a"]["input_tokens"] != p["b"]["input_tokens"]:
            raise ValueError("same prompt must have same tokenizer input length")
        difference = p["b"]["elapsed_seconds"] - p["a"]["elapsed_seconds"]
        observed[p["order"]].append(difference)
        raw.append({"order": p["order"], "a_elapsed_seconds": p["a"]["elapsed_seconds"],
                    "b_elapsed_seconds": p["b"]["elapsed_seconds"],
                    "input_tokens": p["a"]["input_tokens"]})
    if not all(len(v) >= 2 for v in observed.values()):
        raise ValueError("both orders need at least two replicates")
    return {
        "schema_version": 1,
        "experiment": "tiny_random_weight_qwen2_cpu_same_prompt_negative_control",
        "n_pairs": len(pairs), "n_real_generations": 2 * len(pairs),
        "same_prompt_both_conditions": True,
        "observed_orders": [p["order"] for p in pairs],
        "order_counts": {k: len(v) for k, v in observed.items()},
        "b_minus_a_seconds_median": statistics.median(
            observed["a_first"] + observed["b_first"]),
        "b_minus_a_seconds_median_by_order": {
            k: statistics.median(v) for k, v in observed.items()},
        "absolute_paired_difference_seconds_median": statistics.median(
            abs(v) for group in observed.values() for v in group),
        "raw_pairs": raw,
        "negative_control_passed": None,
        "speed_gain_verified": False,
        "pretrained_weights": False, "gpu_used": False,
        "optimizer_steps": 0, "lora_adapter_created": False,
        "heldout_quality_gain": None,
        "warning": "Same prompt A/B measures cold-start/order noise, not a model speed or intelligence gain."
    }


def run(n_pairs=6):
    if type(n_pairs) is not int or n_pairs < 4 or n_pairs > 20 or n_pairs % 2:
        raise ValueError("require even 4..20 pairs")
    with tempfile.TemporaryDirectory(prefix="oril-negative-control-") as temp:
        model_dir = Path(temp) / "random-qwen2"
        model_dir.mkdir()
        config_sha = build_tiny_checkpoint(model_dir)
        adapter = Path(__file__).resolve().parent / "oril_v2_local_qwen_adapter.py"
        pairs = []
        for i in range(n_pairs):
            order = ["a", "b"] if i % 2 == 0 else ["b", "a"]
            measurements = {}
            for label in order:
                measurements[label] = invoke(adapter, model_dir, SHORT)
            pairs.append({"order": order[0] + "_first", **measurements})
        result = summarize_negative_control(pairs)
        result["config_sha256"] = config_sha
        return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True)
    p.add_argument("--pairs", type=int, default=6)
    args = p.parse_args()
    dest = Path(args.output)
    if dest.exists():
        p.error("refuse to overwrite existing report")
    report = run(args.pairs)
    with dest.open("x", encoding="utf-8") as f:
        json.dump(report, f, sort_keys=True, ensure_ascii=False, allow_nan=False)
        f.write("\n")


if __name__ == "__main__":
    main()
