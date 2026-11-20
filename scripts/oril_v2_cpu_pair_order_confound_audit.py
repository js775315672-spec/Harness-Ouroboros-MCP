#!/usr/bin/env python3
"""Read-only stratified order-confounding audit for actual raw CPU sidecars.

Never infers pretrained Qwen, LoRA, quality or performance improvement.
Requires the existing independent raw-sidecar arithmetic audit first.
"""
import argparse
import json
import math
from pathlib import Path
import statistics

from oril_v2_cpu_raw_latency_sidecar_audit import audit, load_json


def stratified_order_audit(report, sidecar):
    # Fail closed if report/sidecar integrity or arithmetic does not agree.
    audit(report, sidecar)
    groups = {"compact_first": [], "verbose_first": []}
    for row in sidecar["pairs"]:
        groups[row["order"]].append(
            row["verbose_elapsed_seconds"] - row["compact_elapsed_seconds"])
    result = {
        "schema_version": 1,
        "experiment": "synthetic_random_weight_qwen2_cpu_subprocess",
        "n_pairs": len(sidecar["pairs"]),
        "counts": {k: len(v) for k, v in groups.items()},
        "order_stratified_median_verbose_minus_compact_seconds": {
            k: round(statistics.median(v), 6) if v else None
            for k, v in groups.items()
        },
        "overall_median_verbose_minus_compact_seconds": round(
            statistics.median(groups["compact_first"] + groups["verbose_first"]), 6),
        "both_orders_replicated": all(len(v) >= 2 for v in groups.values()),
        "order_direction_consistent": None,
        "latency_gain_verified": False,
        "pretrained_model_quality_gain": None,
        "lora_training_verified": False,
        "provenance_attested": False,
        "warning": "Order-stratified synthetic cold-start CPU diagnostic only. "
                   "Not a causal speed, cost, or model quality claim.",
    }
    if result["both_orders_replicated"]:
        medians = [statistics.median(v) for v in groups.values()]
        # A zero difference is neutral, not a positive speed gain.
        result["order_direction_consistent"] = (
            all(v > 0 for v in medians) or all(v < 0 for v in medians))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report")
    parser.add_argument("sidecar")
    args = parser.parse_args()
    result = stratified_order_audit(load_json(args.report),
                                    load_json(args.sidecar))
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
