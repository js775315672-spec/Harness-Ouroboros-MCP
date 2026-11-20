#!/usr/bin/env python3
"""Offline paired student evaluation. Does not run models or attest hidden data."""
import argparse
import hashlib
import json
import math
import random
from pathlib import Path

FIELDS = {"task_id", "group_id", "dataset_sha256", "model_sha256", "seed",
          "correct", "input_tokens", "output_tokens", "latency_ms"}
SHA = set("0123456789abcdef")


def sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in SHA for c in value)


def read(path):
    rows = []
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            if len(line) > 16384:
                raise ValueError("oversized input row")
            def unique(pairs):
                d = {}
                for k, v in pairs:
                    if k in d:
                        raise ValueError("duplicate JSON field")
                    d[k] = v
                return d
            rows.append(json.loads(line, object_pairs_hook=unique,
                                   parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON"))))
    return rows


def check(rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError("nonempty rows required")
    seen, dataset, model, groups = set(), set(), set(), {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != FIELDS:
            raise ValueError("exact schema required")
        if not isinstance(row["task_id"], str) or not row["task_id"].strip() or len(row["task_id"]) > 100:
            raise ValueError("invalid task id")
        if not isinstance(row["group_id"], str) or not row["group_id"].strip() or len(row["group_id"]) > 100:
            raise ValueError("invalid group id")
        if row["task_id"] in seen:
            raise ValueError("duplicate task id")
        seen.add(row["task_id"])
        if not sha(row["dataset_sha256"]) or not sha(row["model_sha256"]):
            raise ValueError("invalid SHA")
        dataset.add(row["dataset_sha256"])
        model.add(row["model_sha256"])
        if type(row["seed"]) is not int or row["seed"] < 0:
            raise ValueError("invalid seed")
        if type(row["correct"]) is not bool:
            raise ValueError("correct must be boolean")
        for k in ("input_tokens", "output_tokens"):
            if type(row[k]) is not int or row[k] < 0:
                raise ValueError("invalid token count")
        if type(row["latency_ms"]) not in (int, float) or not math.isfinite(row["latency_ms"]) or row["latency_ms"] < 0:
            raise ValueError("invalid latency")
        groups[row["task_id"]] = row["group_id"]
    if len(dataset) != 1 or len(model) != 1:
        raise ValueError("each cohort must have one dataset and model SHA")
    return {x["task_id"]: x for x in rows}


def evaluate(baseline, candidate, *, min_tasks=30, bootstrap_samples=2000):
    if type(min_tasks) is not int or min_tasks < 1 or type(bootstrap_samples) is not int or bootstrap_samples < 100:
        raise ValueError("invalid evaluation settings")
    a, b = check(baseline), check(candidate)
    if a.keys() != b.keys():
        raise ValueError("paired task sets differ")
    keys = sorted(a)
    if not all(a[k]["dataset_sha256"] == b[k]["dataset_sha256"] and
               a[k]["group_id"] == b[k]["group_id"] and
               a[k]["seed"] == b[k]["seed"] for k in keys):
        raise ValueError("dataset/group/seed mismatch")
    n = len(keys)
    a_score = sum(a[k]["correct"] for k in keys) / n
    b_score = sum(b[k]["correct"] for k in keys) / n
    delta = b_score - a_score
    changes = [int(b[k]["correct"]) - int(a[k]["correct"]) for k in keys]
    improved = sum(x == 1 for x in changes)
    regressed = sum(x == -1 for x in changes)
    total_a = sum(a[k]["input_tokens"] + a[k]["output_tokens"] for k in keys)
    total_b = sum(b[k]["input_tokens"] + b[k]["output_tokens"] for k in keys)
    lat_a = sum(a[k]["latency_ms"] for k in keys)
    lat_b = sum(b[k]["latency_ms"] for k in keys)
    rng = random.Random(0)
    deltas = []
    for _ in range(bootstrap_samples):
        deltas.append(sum(changes[rng.randrange(n)] for _ in range(n)) / n)
    deltas.sort()
    low = deltas[int(0.025 * bootstrap_samples)]
    high = deltas[min(bootstrap_samples - 1, math.ceil(0.975 * bootstrap_samples) - 1)]
    token_reduction = 100 * (total_a - total_b) / total_a if total_a else None
    latency_reduction = 100 * (lat_a - lat_b) / lat_a if lat_a else None
    sufficient = n >= min_tasks
    # Conservative: noninferiority needs paired lower CI >= -2pp.
    quality_pass = sufficient and low >= -0.02
    efficient = token_reduction is not None and token_reduction >= 20
    status = ("향상" if quality_pass and efficient else
              "판단불가" if not sufficient else
              "악화" if high < -0.02 else "유지/미입증")
    return {
        "schema_version": 1, "paired_tasks": n,
        "baseline_model_sha256": baseline[0]["model_sha256"],
        "candidate_model_sha256": candidate[0]["model_sha256"],
        "dataset_sha256": baseline[0]["dataset_sha256"],
        "baseline_accuracy": round(a_score, 6),
        "candidate_accuracy": round(b_score, 6),
        "paired_accuracy_delta": round(delta, 6),
        "paired_bootstrap_95ci": [round(low, 6), round(high, 6)],
        "bootstrap_samples": bootstrap_samples,
        "improved_cases": improved, "regressed_cases": regressed,
        "baseline_total_tokens": total_a, "candidate_total_tokens": total_b,
        "token_reduction_pct": round(token_reduction, 3) if token_reduction is not None else None,
        "baseline_total_latency_ms": round(lat_a, 3),
        "candidate_total_latency_ms": round(lat_b, 3),
        "latency_reduction_pct": round(latency_reduction, 3) if latency_reduction is not None else None,
        "quality_noninferiority_pass": quality_pass,
        "token_saving_pass": efficient,
        "status": status,
        "independent_evaluation_attested": False,
        "gpu_training_attested": False,
        "note": "Input rows are claims, not independently attested. Bootstrap is exploratory, not a hidden evaluator certificate."
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", required=True)
    p.add_argument("--candidate", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--min-tasks", type=int, default=30)
    args = p.parse_args()
    paths = [Path(x).resolve() for x in (args.baseline, args.candidate, args.output)]
    if len(set(paths)) != 3:
        raise ValueError("output must be separate from inputs")
    result = evaluate(read(paths[0]), read(paths[1]), min_tasks=args.min_tasks)
    paths[2].write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
