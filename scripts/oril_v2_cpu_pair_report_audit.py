#!/usr/bin/env python3
"""Independent arithmetic consistency check for *synthetic* CPU Qwen reports.

No source authenticity, pretrained-model quality, LoRA, or GPU attestation.
Only verify reported arithmetic and mandatory no-training assertions.
"""
import argparse
import json
import math
import statistics
from pathlib import Path

SHA256_HEX = set("0123456789abcdef")
REQUIRED = {
    "schema_version", "experiment", "n_pairs", "n_real_generations",
    "config_sha256", "compact_input_tokens", "verbose_input_tokens",
    "input_token_reduction_pct_median", "compact_elapsed_seconds_median",
    "verbose_elapsed_seconds_median",
    "paired_verbose_minus_compact_seconds_median",
    "paired_elapsed_differences_seconds", "pair_orders",
    "pair_order_observed", "pretrained_weights", "gpu_used",
    "optimizer_steps", "lora_adapter_created",
    "independent_heldout_evaluation", "model_intelligence_gain",
    "independent_quality_n", "training_cost", "inference_cost",
    "performance_gain_verified", "warning",
}


def _numbers(values, n, *, integral=False, positive=False):
    if type(values) is not list or len(values) != n:
        raise ValueError("invalid vector length")
    for value in values:
        if (type(value) not in ((int,) if integral else (int, float))
                or not math.isfinite(value) or
                (positive and value <= 0)):
            raise ValueError("invalid vector values")


def verify(report):
    if type(report) is not dict or set(report) != REQUIRED:
        raise ValueError("unexpected report schema")
    n = report["n_pairs"]
    if type(n) is not int or not 2 <= n <= 20:
        raise ValueError("invalid n_pairs")
    if type(report["n_real_generations"]) is not int or report["n_real_generations"] != 2*n:
        raise ValueError("generation count inconsistent")
    if report["schema_version"] != 1 or report["experiment"] != "synthetic_random_weight_qwen2_cpu_paired_inference":
        raise ValueError("invalid experiment")
    sha = report["config_sha256"]
    if type(sha) is not str or len(sha) != 64 or not set(sha) <= SHA256_HEX:
        raise ValueError("invalid checkpoint digest")
    short, long = report["compact_input_tokens"], report["verbose_input_tokens"]
    _numbers(short, n, integral=True, positive=True)
    _numbers(long, n, integral=True, positive=True)
    if any(s >= l for s, l in zip(short, long)):
        raise ValueError("not actually compact")
    differences = report["paired_elapsed_differences_seconds"]
    _numbers(differences, n)
    if not all(math.isfinite(v) for v in differences):
        raise ValueError("nonfinite difference")
    # Recompute directly from independently supplied token counts.
    saved = round(statistics.median([100 * (1-s/l) for s,l in zip(short,long)]), 2)
    if report["input_token_reduction_pct_median"] != saved:
        raise ValueError("token saving arithmetic mismatch")
    if report["paired_verbose_minus_compact_seconds_median"] != round(statistics.median(differences),3):
        raise ValueError("paired latency arithmetic mismatch")
    for name in ("compact_elapsed_seconds_median", "verbose_elapsed_seconds_median"):
        value = report[name]
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("invalid median latency")
    orders = report["pair_orders"]
    observed = report["pair_order_observed"]
    if type(observed) is not bool:
        raise ValueError("invalid observed flag")
    if observed:
        if (type(orders) is not list or len(orders) != n or
                any(type(x) is not str or x not in ("compact_first", "verbose_first") for x in orders)
                or abs(orders.count("compact_first") - orders.count("verbose_first")) > 1):
            raise ValueError("unbalanced or fabricated order metadata")
    elif orders is not None:
        raise ValueError("unobserved order must be null")
    expected_false = ("pretrained_weights", "gpu_used", "lora_adapter_created",
                      "independent_heldout_evaluation", "performance_gain_verified")
    if any(report[k] is not False for k in expected_false):
        raise ValueError("unsupported model or evaluation claim")
    if (type(report["optimizer_steps"]) is not int or report["optimizer_steps"] != 0 or
            type(report["independent_quality_n"]) is not int or report["independent_quality_n"] != 0 or
            any(report[k] is not None for k in ("model_intelligence_gain","training_cost","inference_cost"))):
        raise ValueError("unsupported learning or cost claim")
    if type(report["warning"]) is not str or not report["warning"].strip():
        raise ValueError("missing limitations warning")
    # Without per-invocation raw timings, independent reconstruction of the
    # individual variant latency medians is impossible. Do not certify them.
    return {
        "schema_valid": True,
        "token_median_arithmetic_verified": True,
        "paired_difference_median_arithmetic_verified": True,
        "individual_latency_medians_independently_verified": False,
        "model_quality_verified": False,
        "real_gpu_lora_verified": False,
        "provenance_attested": False,
        "n_pairs": n,
        "limitations": "Self-reported token vectors and differences; no signed runner provenance or raw per-call latencies.",
    }


def _unique(pairs):
    result = {}
    for k,v in pairs:
        if k in result:
            raise ValueError("duplicate JSON key")
        result[k]=v
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report")
    args = parser.parse_args()
    data = Path(args.report).read_bytes()
    if len(data) > 65536:
        raise ValueError("report exceeds 64 KiB")
    report = json.loads(data, object_pairs_hook=_unique,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
    print(json.dumps(verify(report), sort_keys=True))


if __name__ == "__main__":
    main()
