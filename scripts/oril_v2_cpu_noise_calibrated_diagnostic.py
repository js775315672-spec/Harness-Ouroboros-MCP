#!/usr/bin/env python3
"""Cross-experiment *diagnostic* for random Qwen CPU latency confounding.

Never approves speed, accuracy, LoRA, provenance or deployment. Requires
independent arithmetic audits before comparing an observed prompt effect with
same-prompt cold-start noise. Different runners/times are NOT exchangeable.
"""
import argparse
import json
import math
import statistics
from pathlib import Path

from oril_v2_cpu_negative_control_independent_audit import audit as audit_null
from oril_v2_cpu_raw_latency_sidecar_audit import audit as audit_pair, load_json


def diagnose(pair_report, pair_sidecar, null_report):
    audit_pair(pair_report, pair_sidecar)
    audit_null(null_report)
    if pair_report.get("experiment") != "synthetic_random_weight_qwen2_cpu_paired_inference":
        raise ValueError("wrong paired experiment")
    if (pair_report.get("config_sha256") != null_report.get("config_sha256")
            or type(pair_report.get("config_sha256")) is not str
            or len(pair_report["config_sha256"]) != 64
            or any(x not in "0123456789abcdef" for x in pair_report["config_sha256"])):
        raise ValueError("checkpoint config hash differs or missing")
    raw = pair_sidecar["pairs"]
    null = null_report["raw_pairs"]
    if len(raw) < 4 or len(null) < 4:
        raise ValueError("at least four paired and null cases required")
    # Absolute null noise: deliberately conservative, not a p-value.
    null_diffs = [abs(p["b_elapsed_seconds"] - p["a_elapsed_seconds"]) for p in null]
    effect = [p["verbose_elapsed_seconds"] - p["compact_elapsed_seconds"] for p in raw]
    null_max = max(null_diffs)
    median_effect = statistics.median(effect)
    # Positive effects are compact-faster. Even exceeding the null range is
    # ONLY a diagnostic, not a statistical claim across distinct runs.
    exceeds = median_effect > null_max
    return {
        "schema_version": 1,
        "experiment": "random_weight_cpu_null_calibrated_diagnostic",
        "paired_n": len(raw), "null_n": len(null),
        "paired_median_verbose_minus_compact_seconds": median_effect,
        "null_max_absolute_difference_seconds": null_max,
        "null_median_absolute_difference_seconds": statistics.median(null_diffs),
        "effect_exceeds_observed_null_max": exceeds,
        "noise_could_explain_observed_effect": not exceeds,
        "paired_and_null_checkpoint_config_match": True,
        "independent_arithmetic_audits_passed": True,
        "speed_gain_verified": False,
        "model_intelligence_improved": None,
        "pretrained_model_evaluated": False,
        "gpu_lora_verified": False,
        "heldout_quality_verified": False,
        "causal_interpretation_permitted": False,
        "warning": ("Different experimental runs may have different machine load. "
                    "Even an effect larger than observed null noise cannot prove "
                    "speed improvement. Random weights and synthetic prompts only."),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--paired-report", required=True)
    p.add_argument("--paired-sidecar", required=True)
    p.add_argument("--null-report", required=True)
    args = p.parse_args()
    paths = [Path(args.paired_report), Path(args.paired_sidecar), Path(args.null_report)]
    if len({p.resolve() for p in paths}) != 3:
        p.error("input files must be distinct")
    report = diagnose(*(load_json(path) for path in paths))
    print(json.dumps(report, sort_keys=True, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
