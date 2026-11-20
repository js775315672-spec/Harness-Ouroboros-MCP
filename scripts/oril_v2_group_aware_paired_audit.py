#!/usr/bin/env python3
"""Group-aware independent-evaluation *audit* of claimed paired student results.

Requires paired evaluator from PR #276. This does not attest any real model run.
Prevents correlated task variants from inflating independent sample size.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import random

from oril_v2_paired_student_eval import check, read

def group_audit(baseline, candidate, *, min_groups=30, samples=2000,
                noninferiority_margin=0.02, token_target=20):
    if (type(min_groups) is not int or min_groups < 1 or
            type(samples) is not int or samples < 100 or
            type(noninferiority_margin) not in (int, float) or
            not math.isfinite(noninferiority_margin) or not 0 <= noninferiority_margin < 1 or
            type(token_target) not in (int, float) or
            not math.isfinite(token_target) or not 0 <= token_target <= 100):
        raise ValueError("invalid audit settings")
    a, b = check(baseline), check(candidate)
    if a.keys() != b.keys():
        raise ValueError("paired task sets differ")
    keys = sorted(a)
    if not all(a[k]["dataset_sha256"] == b[k]["dataset_sha256"] and
               a[k]["group_id"] == b[k]["group_id"] and
               a[k]["seed"] == b[k]["seed"] for k in keys):
        raise ValueError("dataset/group/seed mismatch")
    grouped = defaultdict(list)
    for k in keys:
        # Case-fold grouping to prevent easy group ID casing bypasses.
        grouped[a[k]["group_id"].strip().casefold()].append(k)
    groups = sorted(grouped)
    n_groups = len(groups)
    # Use equal-weight group means, not per-task weighting, to prevent a
    # single large correlated group from dominating quality estimates.
    changes = []
    group_tokens_a, group_tokens_b = [], []
    for group in groups:
        ids = grouped[group]
        changes.append(sum(int(b[k]["correct"]) - int(a[k]["correct"]) for k in ids) / len(ids))
        group_tokens_a.append(sum(a[k]["input_tokens"] + a[k]["output_tokens"] for k in ids))
        group_tokens_b.append(sum(b[k]["input_tokens"] + b[k]["output_tokens"] for k in ids))
    rng = random.Random(0)
    boot = []
    for _ in range(samples):
        boot.append(sum(changes[rng.randrange(n_groups)] for _ in range(n_groups)) / n_groups)
    boot.sort()
    low = boot[int(0.025 * samples)]
    high = boot[min(samples - 1, math.ceil(0.975 * samples) - 1)]
    total_a, total_b = sum(group_tokens_a), sum(group_tokens_b)
    reduction = 100 * (total_a - total_b) / total_a if total_a else None
    sufficient = n_groups >= min_groups
    quality_pass = sufficient and low >= -noninferiority_margin
    token_pass = reduction is not None and reduction >= token_target
    status = ("향상" if quality_pass and token_pass else
              "판단불가" if not sufficient else
              "악화" if high < -noninferiority_margin else "유지/미입증")
    return {
        "schema_version": 1,
        "task_rows": len(keys),
        "independent_groups_proxy": n_groups,
        "max_rows_per_group": max(map(len, grouped.values())),
        "group_mean_accuracy_delta": round(sum(changes) / n_groups, 6),
        "group_bootstrap_95ci": [round(low, 6), round(high, 6)],
        "bootstrap_samples": samples,
        "baseline_total_tokens": total_a,
        "candidate_total_tokens": total_b,
        "token_reduction_pct": round(reduction, 3) if reduction is not None else None,
        "quality_noninferiority_pass": quality_pass,
        "token_saving_pass": token_pass,
        "status": status,
        "independent_evaluation_attested": False,
        "gpu_training_attested": False,
        "model_quality_gain_attested": False,
        "note": "Group labels and scores are untrusted input claims. Independent groups proxy does not prove statistical independence; bootstrap exploratory only."
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--baseline", required=True)
    p.add_argument("--candidate", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--min-groups", type=int, default=30)
    args = p.parse_args()
    paths = [Path(x).resolve() for x in (args.baseline, args.candidate, args.output)]
    if len(set(paths)) != 3:
        raise ValueError("input/output path alias")
    result = group_audit(read(paths[0]), read(paths[1]), min_groups=args.min_groups)
    paths[2].write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
