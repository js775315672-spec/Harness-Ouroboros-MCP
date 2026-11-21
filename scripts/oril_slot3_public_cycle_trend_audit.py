#!/usr/bin/env python3
"""Read-only public cycle trend audit. No promotion or model-quality claims."""
import json
import math
import statistics
import sys

REQUIRED = {"campaign", "cycle", "task_id", "group_digest", "model_revision",
            "duration_s", "baseline_correct", "candidate_correct", "n_groups",
            "input_tokens_base", "input_tokens_candidate", "source_url"}

def audit(rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError("nonempty cycle array required")
    seen = set()
    for r in rows:
        if not isinstance(r, dict) or not REQUIRED <= r.keys():
            raise ValueError("missing fields")
        key = (r["campaign"], r["cycle"])
        if key in seen:
            raise ValueError("duplicate cycle")
        seen.add(key)
        if not isinstance(r["cycle"], int) or isinstance(r["cycle"], bool) or r["cycle"] < 1:
            raise ValueError("invalid cycle")
        for field in ("duration_s", "baseline_correct", "candidate_correct",
                      "n_groups", "input_tokens_base", "input_tokens_candidate"):
            value = r[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not  isinstance(value, int if field != "duration_s" else (int, float)) or value < 0:
                raise ValueError("invalid numeric field: " + field)
        if not math.isfinite(r["duration_s"]) or r["duration_s"] <= 0 or r["n_groups"] <= 0 or r["input_tokens_base"] <= 0:
            raise ValueError("invalid denominator")
        if max(r["baseline_correct"], r["candidate_correct"]) > r["n_groups"]:
            raise ValueError("accuracy exceeds groups")
        for field in ("task_id", "group_digest", "model_revision", "source_url", "campaign"):
            if not isinstance(r[field], str) or not r[field].strip():
                raise ValueError("invalid identity: " + field)
        if not r["source_url"].startswith("https://github.com/"):
            raise ValueError("unverifiable source URL")
    signatures = {(r["task_id"], r["group_digest"], r["model_revision"]) for r in rows}
    durations = [r["duration_s"] for r in rows]
    savings = [(r["input_tokens_base"] - r["input_tokens_candidate"]) /
               r["input_tokens_base"] for r in rows]
    return {
        "n": len(rows),
        "duration_median_s": statistics.median(durations),
        "duration_range_s": [min(durations), max(durations)],
        "input_savings_median_pct": round(100 * statistics.median(savings), 3),
        "comparable_task_environment": len(signatures) == 1,
        "public_accuracy_changes": [r["candidate_correct"] - r["baseline_correct"] for r in rows],
        "independent_verified_gain_per_hour": None,
        "heldout_quality_change": None,
        "speed_trend": "판단불가",
        "model_quality": "판단불가",
        "promotion_allowed": False,
        "note": "Public repeated tasks and reported measurements only; not independent provenance or heldout."
    }

def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit.py cycles.json")
    with open(sys.argv[1], encoding="utf-8") as f:
        rows = json.load(f)
    print(json.dumps(audit(rows), ensure_ascii=False, sort_keys=True))

if __name__ == "__main__":
    main()
