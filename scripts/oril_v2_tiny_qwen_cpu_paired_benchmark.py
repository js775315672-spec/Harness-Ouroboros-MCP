#!/usr/bin/env python3
"""Repeat real tiny random Qwen2 CPU calls with balanced prompt order.

Benchmark execution overhead and actual tokenizer input counts, NOT model
quality, pretrained inference, GPU learning, or LoRA. Never claim gains in
intelligence from synthetic prompts and random weights.
"""
import hashlib
import json
import math
from pathlib import Path
import statistics
import tempfile

from oril_v2_tiny_qwen_cpu_forward_smoke import build_tiny_checkpoint, invoke

SHORT = "Question: fix a bug."
LONG = ("verbose explanation and clear steps and reason with safe test "
        "and fix a bug. Question: fix a bug.")


def summarize(pairs, config_sha, observed_orders=None):
    if not pairs:
        raise ValueError("at least one real pair required")
    for pair in pairs:
        if set(pair) != {"compact", "verbose"}:
            raise ValueError("missing prompt variant")
        for variant in ("compact", "verbose"):
            sample = pair[variant]
            if (not isinstance(sample, dict) or
                    set(sample) != {"input_tokens", "output_tokens", "elapsed_seconds"} or
                    type(sample["input_tokens"]) is not int or
                    type(sample["output_tokens"]) is not int or
                    sample["input_tokens"] < 1 or sample["output_tokens"] < 1 or
                    type(sample["elapsed_seconds"]) not in (int, float) or
                    not math.isfinite(sample["elapsed_seconds"]) or
                    sample["elapsed_seconds"] < 0):
                raise ValueError("invalid real model measurement")
        if pair["compact"]["input_tokens"] >= pair["verbose"]["input_tokens"]:
            raise ValueError("compact tokenizer input is not smaller")
    n = len(pairs)
    # Never fabricate execution order from an index: the order is a
    # measurement supplied by the caller, not a property of pair position.
    if observed_orders is not None:
        if (not isinstance(observed_orders, list) or
                len(observed_orders) != n or
                any(type(order) is not str or order not in
                    ("compact_first", "verbose_first") for order in observed_orders)):
            raise ValueError("invalid observed pair execution order")
        compact_first = observed_orders.count("compact_first")
        verbose_first = observed_orders.count("verbose_first")
        if abs(compact_first - verbose_first) > 1:
            raise ValueError("unbalanced observed pair execution order")
    token_savings = [
        100 * (1 - p["compact"]["input_tokens"] / p["verbose"]["input_tokens"])
        for p in pairs
    ]
    times = {kind: [p[kind]["elapsed_seconds"] for p in pairs]
             for kind in ("compact", "verbose")}
    paired_seconds = [p["verbose"]["elapsed_seconds"] -
                      p["compact"]["elapsed_seconds"] for p in pairs]
    return {
        "schema_version": 1,
        "experiment": "synthetic_random_weight_qwen2_cpu_paired_inference",
        "n_pairs": n, "n_real_generations": 2 * n,
        "config_sha256": config_sha,
        "compact_input_tokens": [p["compact"]["input_tokens"] for p in pairs],
        "verbose_input_tokens": [p["verbose"]["input_tokens"] for p in pairs],
        "input_token_reduction_pct_median": round(statistics.median(token_savings), 2),
        "compact_elapsed_seconds_median": round(statistics.median(times["compact"]), 3),
        "verbose_elapsed_seconds_median": round(statistics.median(times["verbose"]), 3),
        "paired_verbose_minus_compact_seconds_median":
            round(statistics.median(paired_seconds), 3),
        "paired_elapsed_differences_seconds": paired_seconds,
        "pair_orders": observed_orders,
        "pair_order_observed": observed_orders is not None,
        "pretrained_weights": False, "gpu_used": False,
        "optimizer_steps": 0, "lora_adapter_created": False,
        "independent_heldout_evaluation": False, "model_intelligence_gain": None,
        "independent_quality_n": 0, "training_cost": None,
        "inference_cost": None,
        "performance_gain_verified": False,
        "warning": ("Tiny random weights, toy tokenizer, synthetic prompts, "
                    "and separate cold-start subprocesses. Input token savings "
                    "are real for this toy tokenizer only; speed or quality "
                    "improvement on pretrained Qwen is NOT demonstrated."),
    }


def run(n_pairs=6):
    if type(n_pairs) is not int or not 2 <= n_pairs <= 20:
        raise ValueError("pair count outside bounded range")
    with tempfile.TemporaryDirectory(prefix="oril-cpu-paired-") as td:
        model_dir = Path(td) / "random-qwen2"
        model_dir.mkdir()
        config_sha = build_tiny_checkpoint(model_dir)
        adapter = Path(__file__).resolve().parent / "oril_v2_local_qwen_adapter.py"
        pairs = []
        observed_orders = []
        for i in range(n_pairs):
            order = [("compact", SHORT), ("verbose", LONG)]
            if i % 2:
                order.reverse()
            observed_orders.append(order[0][0] + "_first")
            pair = {}
            for label, question in order:
                pair[label] = invoke(adapter, model_dir, question)
            pairs.append(pair)
        return summarize(pairs, config_sha, observed_orders=observed_orders)


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
