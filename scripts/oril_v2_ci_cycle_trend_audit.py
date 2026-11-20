#!/usr/bin/env python3
"""Read-only, workflow-homogeneous GitHub Actions timing and reliability audit.

No claims about model quality, GPU use, developer time, or independent approval.
Consumes a saved GitHub REST actions/runs JSON response (no credentials/network).
"""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics


def parse_time(value):
    if not isinstance(value, str):
        raise ValueError("missing timestamp")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if dt.tzinfo is None:
        raise ValueError("naive timestamp")
    return dt.astimezone(timezone.utc)


def analyze(payload, workflow, *, window=12, min_n=5):
    if not isinstance(payload, dict) or not isinstance(payload.get("workflow_runs"), list):
        raise ValueError("invalid GitHub Actions response")
    if not isinstance(workflow, str) or not workflow.strip():
        raise ValueError("workflow required")
    if type(window) is not int or not 5 <= window <= 100:
        raise ValueError("window must be 5..100")
    if type(min_n) is not int or not 2 <= min_n <= window:
        raise ValueError("invalid min_n")
    records, ids = [], set()
    for run in payload["workflow_runs"]:
        if not isinstance(run, dict) or run.get("name") != workflow:
            continue
        if run.get("event") not in ("push", "pull_request", "workflow_dispatch", "schedule"):
            continue
        if type(run.get("id")) is not int or run["id"] <= 0 or run["id"] in ids:
            raise ValueError("duplicate or invalid run id")
        ids.add(run["id"])
        if run.get("status") != "completed" or run.get("conclusion") not in (
                "success", "failure", "cancelled", "timed_out"):
            continue
        sha = run.get("head_sha")
        if not isinstance(sha, str) or len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
            raise ValueError("invalid head SHA")
        url = run.get("html_url")
        expected = "https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/" + str(run["id"])
        if url != expected:
            raise ValueError("run URL mismatch")
        created, started, updated = (parse_time(run.get(k)) for k in
                                      ("created_at", "run_started_at", "updated_at"))
        queue = (started - created).total_seconds()
        wall = (updated - started).total_seconds()
        if queue < 0 or wall < 0:
            raise ValueError("negative elapsed time")
        records.append({
            "id": run["id"], "sha": sha, "url": url,
            "created": created, "queue_seconds": queue, "wall_seconds": wall,
            "conclusion": run["conclusion"], "event": run["event"],
        })
    records.sort(key=lambda x: (x["created"], x["id"]), reverse=True)
    # Prevent workflow reuse across different events from creating false trends.
    event_counts = {}
    for r in records:
        event_counts[r["event"]] = event_counts.get(r["event"], 0) + 1
    if not event_counts:
        return {"workflow": workflow, "verdict": "판단불가", "reason": "no completed comparable runs",
                "n": 0, "speed_change_pct": None, "model_quality_change": None}
    event = sorted(event_counts, key=lambda x: (-event_counts[x], x))[0]
    sample = [r for r in records if r["event"] == event][:window]
    successes = [r for r in sample if r["conclusion"] == "success"]
    failures = [r for r in sample if r["conclusion"] != "success"]
    # Older/newer windows of the *same workflow and event*, not different tasks.
    half = len(sample) // 2
    newer, older = sample[:half], sample[half:half * 2]
    def median(rows, field):
        return statistics.median(x[field] for x in rows) if rows else None
    old_m, new_m = median(older, "wall_seconds"), median(newer, "wall_seconds")
    change = None if len(sample) < min_n or len(newer) < 2 or len(older) < 2 or old_m is None or old_m == 0 or new_m is None else round(
        100 * (new_m / old_m - 1), 2)
    # The underlying run durations include workflow setup and test runtime.
    # Comparing heterogeneous SHA/tasks is descriptive, not causal speed gain.
    return {
        "workflow": workflow, "event": event, "n": len(sample),
        "successful_runs": len(successes), "failed_cancelled_or_timed_out": len(failures),
        "failure_fraction": round(len(failures) / len(sample), 4),
        "median_wall_seconds": median(sample, "wall_seconds"),
        "median_queue_seconds": median(sample, "queue_seconds"),
        "newer_n": len(newer), "older_n": len(older),
        "newer_median_wall_seconds": new_m, "older_median_wall_seconds": old_m,
        "newer_vs_older_wall_pct": change,
        "verdict": "판단불가",
        "reason": ("insufficient comparable runs" if len(sample) < min_n or
                   len(newer) < 2 or len(older) < 2 else
                   "workflow/event match alone cannot establish equal task difficulty or model quality"),
        "sources": [{"id": r["id"], "sha": r["sha"], "url": r["url"],
                     "wall_seconds": r["wall_seconds"],
                     "queue_seconds": r["queue_seconds"],
                     "conclusion": r["conclusion"]} for r in sample],
        "model_call_seconds": None, "independent_evaluator_seconds": None,
        "operational_followup_seconds": None, "model_quality_change": None,
        "gpu_training_verified": False, "adapter_created_verified": False,
        "independent_improvements_per_hour": None,
        "retry_rate": None, "regression_rate": None, "rollback_rate": None,
        "note": "CI success is not an independent model improvement; updated_at is a run completion proxy",
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
    p.add_argument("--runs-json", required=True)
    p.add_argument("--workflow", required=True)
    p.add_argument("--window", type=int, default=12)
    args = p.parse_args()
    src = Path(args.runs_json)
    if src.stat().st_size > 4 * 1024 * 1024:
        p.error("oversized input")
    data = json.loads(src.read_text(encoding="utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
    print(json.dumps(analyze(data, args.workflow, window=args.window),
                     sort_keys=True, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
