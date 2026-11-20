#!/usr/bin/env python3
"""Independently recompute all CPU paired latency medians from raw sidecar.

This only checks arithmetic consistency; caller-supplied timing data are not
authenticated. The synthetic Qwen2 model has RANDOM weights; no LoRA or GPU.
"""
import argparse
import json
import math
from pathlib import Path
import statistics

EXPECTED = {"schema_version", "report_sha256", "pairs", "measurement_kind"}
PAIR_KEYS = {"order", "compact_elapsed_seconds", "verbose_elapsed_seconds",
             "compact_input_tokens", "verbose_input_tokens"}


def _num(value, *, positive=False):
    if type(value) not in (float, int) or not math.isfinite(value):
        raise ValueError("invalid raw numeric value")
    if value <= 0 if positive else value < 0:
        raise ValueError("negative or zero raw measurement")
    return value


def audit(report, sidecar):
    """Fail closed on missing raw samples and report/sidecar disagreement."""
    if type(report) is not dict or type(sidecar) is not dict:
        raise ValueError("invalid input object")
    if set(sidecar) != EXPECTED or sidecar["schema_version"] != 1:
        raise ValueError("invalid raw sidecar schema")
    if sidecar["measurement_kind"] != "synthetic_random_weight_qwen2_cpu_subprocess":
        raise ValueError("invalid experiment kind")
    n = report.get("n_pairs")
    if type(n) is not int or not 2 <= n <= 20:
        raise ValueError("invalid pair count")
    pairs = sidecar["pairs"]
    if type(pairs) is not list or len(pairs) != n:
        raise ValueError("missing raw paired samples")
    import hashlib
    digest = hashlib.sha256(json.dumps(report, sort_keys=True,
                                      ensure_ascii=False, separators=(",", ":"),
                                      allow_nan=False).encode("utf-8")).hexdigest()
    if type(sidecar["report_sha256"]) is not str or sidecar["report_sha256"] != digest:
        raise ValueError("report SHA mismatch")
    compact, verbose, diffs, orders, ct, vt = [], [], [], [], [], []
    for pair in pairs:
        if type(pair) is not dict or set(pair) != PAIR_KEYS:
            raise ValueError("invalid raw pair schema")
        order = pair["order"]
        if order not in ("compact_first", "verbose_first") or type(order) is not str:
            raise ValueError("invalid raw order")
        orders.append(order)
        a = _num(pair["compact_elapsed_seconds"])
        b = _num(pair["verbose_elapsed_seconds"])
        compact.append(a)
        verbose.append(b)
        diffs.append(b-a)
        c = pair["compact_input_tokens"]
        v = pair["verbose_input_tokens"]
        if type(c) is not int or type(v) is not int or c < 1 or c >= v:
            raise ValueError("invalid raw token counts")
        ct.append(c)
        vt.append(v)
    if report.get("pair_order_observed") is not True or report.get("pair_orders") != orders:
        raise ValueError("order differs from raw observations")
    if abs(orders.count("compact_first") - orders.count("verbose_first")) > 1:
        raise ValueError("unbalanced raw execution order")
    if report.get("compact_input_tokens") != ct or report.get("verbose_input_tokens") != vt:
        raise ValueError("token vectors differ from raw samples")
    saved_diffs = report.get("paired_elapsed_differences_seconds")
    if (type(saved_diffs) is not list or len(saved_diffs) != n or
            any(type(v) not in (int, float) or not math.isfinite(v) or
                not math.isclose(v, d, abs_tol=1e-8, rel_tol=1e-8)
                for v, d in zip(saved_diffs, diffs))):
        raise ValueError("paired latency differences inconsistent")
    for field, value in (
        ("compact_elapsed_seconds_median", round(statistics.median(compact), 3)),
        ("verbose_elapsed_seconds_median", round(statistics.median(verbose), 3)),
        ("paired_verbose_minus_compact_seconds_median",
         round(statistics.median(diffs), 3)),
        ("input_token_reduction_pct_median",
         round(statistics.median([100*(1-c/v) for c, v in zip(ct, vt)]), 2)),
    ):
        observed = report.get(field)
        if type(observed) not in (int, float) or not math.isfinite(observed) or observed != value:
            raise ValueError("arithmetic mismatch: " + field)
    for field, expected in (("pretrained_weights", False), ("gpu_used", False),
                            ("optimizer_steps", 0), ("lora_adapter_created", False),
                            ("independent_heldout_evaluation", False),
                            ("performance_gain_verified", False),
                            ("model_intelligence_gain", None)):
        if type(report.get(field)) is not type(expected) or report.get(field) != expected:
            raise ValueError("unsupported model improvement assertion")
    return {
        "raw_pair_count": n,
        "individual_latency_medians_arithmetic_verified": True,
        "paired_latency_median_arithmetic_verified": True,
        "token_count_arithmetic_verified": True,
        "provenance_attested": False,
        "independent_quality_verified": False,
        "gpu_lora_verified": False,
        "model_intelligence_gain": None,
        "warning": "Untrusted raw sidecar; no independent source or pretrained model evidence",
    }


def load_json(path):
    path = Path(path)
    if path.stat().st_size > 262144:
        raise ValueError("oversized report")
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("duplicate JSON key")
            obj[key] = value
        return obj
    def nonfinite(value):
        raise ValueError("nonfinite JSON value: " + value)
    return json.loads(path.read_text(encoding="utf-8"),
                      object_pairs_hook=unique, parse_constant=nonfinite)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("report")
    p.add_argument("sidecar")
    args = p.parse_args()
    print(json.dumps(audit(load_json(args.report), load_json(args.sidecar)),
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
