#!/usr/bin/env python3
"""Independent arithmetic auditor for the same-prompt CPU negative control.

Reads raw JSON, never invokes the candidate's summary function. This checks
internal consistency, not provenance, actual GPU use or model improvement.
"""
import argparse
import json
import math
from pathlib import Path
import statistics

KEYS = {"order", "a_elapsed_seconds", "b_elapsed_seconds", "input_tokens"}


def audit(report):
    if not isinstance(report, dict) or report.get("schema_version") != 1:
        raise ValueError("invalid report schema")
    if report.get("experiment") != "tiny_random_weight_qwen2_cpu_same_prompt_negative_control":
        raise ValueError("wrong experiment")
    raw = report.get("raw_pairs")
    if type(raw) is not list or not 4 <= len(raw) <= 20 or len(raw) % 2:
        raise ValueError("invalid raw pair count")
    orders = {"a_first": [], "b_first": []}
    observed = []
    for pair in raw:
        if not isinstance(pair, dict) or set(pair) != KEYS:
            raise ValueError("invalid raw pair fields")
        order = pair["order"]
        if order not in orders:
            raise ValueError("invalid order")
        for key in ("a_elapsed_seconds", "b_elapsed_seconds"):
            val = pair[key]
            if type(val) not in (float, int) or not math.isfinite(val) or val < 0:
                raise ValueError("invalid elapsed time")
        if type(pair["input_tokens"]) is not int or pair["input_tokens"] < 1:
            raise ValueError("invalid token count")
        orders[order].append(pair["b_elapsed_seconds"] - pair["a_elapsed_seconds"])
        observed.append(order)
    if len(orders["a_first"]) != len(orders["b_first"]):
        raise ValueError("unbalanced observed order")
    if report.get("observed_orders") != observed:
        raise ValueError("order summary mismatch")
    if report.get("order_counts") != {k: len(v) for k, v in orders.items()}:
        raise ValueError("order counts mismatch")
    if type(report.get("n_pairs")) is not int or report["n_pairs"] != len(raw):
        raise ValueError("n_pairs mismatch")
    if type(report.get("n_real_generations")) is not int or report["n_real_generations"] != 2 * len(raw):
        raise ValueError("generation count mismatch")
    pooled = orders["a_first"] + orders["b_first"]
    expected = {
        "b_minus_a_seconds_median": statistics.median(pooled),
        "absolute_paired_difference_seconds_median": statistics.median(abs(x) for x in pooled),
    }
    for k, v in expected.items():
        reported = report.get(k)
        if type(reported) not in (float, int) or not math.isfinite(reported) or not math.isclose(reported, v, rel_tol=1e-10, abs_tol=1e-10):
            raise ValueError(k + " mismatch")
    by_order = report.get("b_minus_a_seconds_median_by_order")
    if not isinstance(by_order, dict) or set(by_order) != set(orders):
        raise ValueError("order medians missing")
    for k, vals in orders.items():
        reported = by_order[k]
        if type(reported) not in (float, int) or not math.isfinite(reported) or not math.isclose(reported, statistics.median(vals), rel_tol=1e-10, abs_tol=1e-10):
            raise ValueError("order median mismatch")
    if report.get("same_prompt_both_conditions") is not True:
        raise ValueError("not a same-prompt control")
    required_false = ("speed_gain_verified", "pretrained_weights", "gpu_used", "lora_adapter_created")
    if any(report.get(k) is not False for k in required_false):
        raise ValueError("false positive model claim")
    if type(report.get("optimizer_steps")) is not int or report["optimizer_steps"] != 0:
        raise ValueError("optimizer steps claim")
    if report.get("heldout_quality_gain", "missing") is not None:
        raise ValueError("heldout quality claim")
    if report.get("negative_control_passed", "missing") is not None:
        raise ValueError("negative control cannot certify speed")
    return {
        "audited_pairs": len(raw), "audited_generations_claimed": len(raw) * 2,
        "recomputed_median_b_minus_a_seconds": expected["b_minus_a_seconds_median"],
        "recomputed_median_abs_noise_seconds": expected["absolute_paired_difference_seconds_median"],
        "recomputed_order_medians": {k: statistics.median(v) for k, v in orders.items()},
        "raw_arithmetic_consistent": True,
        "execution_provenance_independently_attested": False,
        "model_quality_improved": None,
        "model_speed_improved": None,
    }


def unique(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError("duplicate JSON key")
        out[k] = v
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    args = p.parse_args()
    src = Path(args.input)
    if src.stat().st_size > 250000:
        p.error("oversized report")
    data = json.loads(src.read_text(encoding="utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
    print(json.dumps(audit(data), sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
