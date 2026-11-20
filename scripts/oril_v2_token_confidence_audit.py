#!/usr/bin/env python3
"""Group-clustered uncertainty gate for claimed token savings; no model attestation."""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import random
from oril_v2_group_aware_paired_audit import group_audit, canonical_group_id
from oril_v2_paired_student_eval import check, read

def token_confidence_audit(baseline, candidate, *, min_groups=30, samples=2000, token_target=20):
    if type(samples) is not int or samples < 100 or type(token_target) not in (int, float) or not math.isfinite(token_target) or not 0 <= token_target <= 100:
        raise ValueError("invalid bootstrap settings")
    result = group_audit(baseline, candidate, min_groups=min_groups, samples=samples, token_target=token_target)
    a, b = check(baseline), check(candidate)
    grouped = defaultdict(list)
    for k in sorted(a):
        grouped[canonical_group_id(a[k]["group_id"])].append(k)
    pairs = [(sum(a[k]["input_tokens"]+a[k]["output_tokens"] for k in ids),
              sum(b[k]["input_tokens"]+b[k]["output_tokens"] for k in ids))
             for _, ids in sorted(grouped.items())]
    if not sum(x for x, _ in pairs):
        raise ValueError("nonzero baseline token counts required")
    rng = random.Random(0)
    n = len(pairs)
    reductions = []
    zero_resamples = 0
    for _ in range(samples):
        sampled = [pairs[rng.randrange(n)] for _ in range(n)]
        total_a = sum(x for x, _ in sampled)
        total_b = sum(y for _, y in sampled)
        if total_a == 0:
            zero_resamples += 1
        else:
            reductions.append(100*(total_a-total_b)/total_a)
    lower = upper = None
    if not zero_resamples:
        reductions.sort()
        lower = reductions[int(.025*samples)]
        upper = reductions[min(samples-1, math.ceil(.975*samples)-1)]
    enough = n >= min_groups
    robust = enough and lower is not None and lower >= token_target
    quality = result["quality_noninferiority_pass"]
    result.update({
        "token_bootstrap_95ci": [round(lower,6), round(upper,6)] if lower is not None else None,
        "token_bootstrap_samples": samples,
        "token_bootstrap_zero_baseline_resamples": zero_resamples,
        "token_saving_point_estimate_pass": result["token_saving_pass"],
        "token_saving_pass": robust,
        "status": ("향상" if quality and robust else "판단불가" if not enough
                   else "악화" if result["group_bootstrap_95ci"][1] < -.02
                   else "유지/미입증"),
        "token_uncertainty_gate": "group_clustered_bootstrap_lower_95ci",
        "independent_evaluation_attested": False,
        "gpu_training_attested": False,
        "model_quality_gain_attested": False,
        "note": "Untrusted token/group claims; a point estimate >=20% is insufficient without grouped lower CI >=20%. No real model quality or token savings proven."
    })
    return result

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--baseline", required=True)
    p.add_argument("--candidate", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--min-groups", type=int, default=30)
    args = p.parse_args()
    paths = [Path(x).resolve() for x in (args.baseline, args.candidate, args.output)]
    if len(set(paths)) != 3:
        raise ValueError("output must be distinct from inputs")
    result = token_confidence_audit(read(paths[0]), read(paths[1]), min_groups=args.min_groups)
    paths[2].write_text(json.dumps(result, sort_keys=True, indent=2)+"\n", encoding="utf-8")

if __name__ == "__main__":
    main()
