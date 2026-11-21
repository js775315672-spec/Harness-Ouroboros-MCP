#!/usr/bin/env python3
"""Cross-run public Qwen A/B versus A/A diagnostic, never a causal speed claim.

Requires raw reports to pass both separate independent auditors first.
Two GitHub Actions jobs are NOT a matched CPU session; A/A drift is a warning
baseline, not a valid confidence interval for cross-run A/B effects.
"""
import argparse
import json
import math
from pathlib import Path
import statistics

from oril_v2_slot2_public30_independent_audit import audit as audit_ab
from oril_v2_slot4_public30_aa_independent_audit import audit as audit_aa


def reconcile(ab, aa):
    ab_summary = audit_ab(ab)
    aa_summary = audit_aa(aa)
    for field in ("model_id", "resolved_revision", "public_tasks_sha256"):
        if ab[field] != aa[field]:
            raise ValueError("cross-run model/task mismatch: " + field)
    # Compare immutable content descriptors, not merely claimed revision.
    def canonical_weights(report):
        weights = report["weight_files"]
        names = [x["name"] for x in weights]
        if len(names) != len(set(names)):
            raise ValueError("duplicate weight names")
        return sorted((x["name"], x["bytes"], x["sha256"]) for x in weights)
    if canonical_weights(ab) != canonical_weights(aa):
        raise ValueError("cross-run weight hashes mismatch")
    ab_deltas = []
    aa_deltas = []
    ab_accuracy = {"compact": 0, "verbose": 0}
    for x, y in zip(ab["rows"], aa["rows"]):
        if x["group_id"] != y["group_id"] or x["question"] != y["question"] or x["expected"] != y["expected"]:
            raise ValueError("cross-run public group mismatch")
        variants = {v["variant"]: v for v in x["observations"]}
        if set(variants) != {"compact", "verbose"}:
            raise ValueError("invalid A/B variants")
        ab_deltas.append(variants["compact"]["elapsed_seconds"] -
                         variants["verbose"]["elapsed_seconds"])
        for k in ab_accuracy:
            ab_accuracy[k] += int(variants[k]["output"].strip() == x["expected"])
        obs = y["observations"]
        aa_deltas.append(obs[1]["elapsed_seconds"] - obs[0]["elapsed_seconds"])
        # Same compact prompt should tokenize identically across runs,
        # even though runtime conditions can vary.
        if variants["compact"]["input_tokens"] != obs[0]["input_tokens"]:
            raise ValueError("compact tokenization drift across runs")
    median_ab = statistics.median(ab_deltas)
    median_aa_abs = statistics.median(abs(x) for x in aa_deltas)
    return {
        "schema_version": 1,
        "model_id": ab["model_id"],
        "revision": ab["resolved_revision"],
        "task_sha256": ab["public_tasks_sha256"],
        "public_groups": len(ab_deltas),
        "ab_reported_calls": ab_summary["raw_calls"],
        "aa_reported_calls": aa_summary["reported_calls"],
        "public_exact_matches_ab": ab_accuracy,
        "ab_compact_minus_verbose_median_seconds": round(median_ab, 6),
        "aa_absolute_pair_drift_median_seconds": round(median_aa_abs, 6),
        "ab_delta_to_aa_drift_ratio_descriptive":
            round(abs(median_ab) / median_aa_abs, 4) if median_aa_abs > 0 else None,
        "ab_input_token_saving_pct_descriptive": ab_summary["token_saving_pct_descriptive"],
        "same_run_randomized_comparison": False,
        "raw_model_calls_independently_attested": False,
        "independent_heldout_quality_proven": False,
        "gpu_lora_training_proven": False,
        "causal_speed_gain_proven": False,
        "student_weights_updated": False,
        "decision": "판단불가",
        "next_hypothesis": "Same-session randomized public A/B+A/A reduces between-run CPU confounding; verify with frozen independent heldout groups before any model quality claim.",
    }


def read_unique(path):
    path = Path(path)
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("oversized report")
    def unique(pairs):
        d = {}
        for k, v in pairs:
            if k in d:
                raise ValueError("duplicate JSON key")
            d[k] = v
        return d
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ab", required=True)
    p.add_argument("--aa", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    dest = Path(args.output)
    if dest.exists() or dest.is_symlink() or dest.resolve() in {Path(args.ab).resolve(), Path(args.aa).resolve()}:
        raise ValueError("output must be new")
    result = reconcile(read_unique(args.ab), read_unique(args.aa))
    dest.write_text(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
