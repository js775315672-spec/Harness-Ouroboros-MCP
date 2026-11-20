#!/usr/bin/env python3
"""Read-only ORIL GitHub Actions evidence bridge, not a model-quality certificate.

Sources: GET /actions/runs, GET /actions/runs/{id}/jobs.  Historical cycle
timers, model calls, costs, accepted improvements and held-out scores cannot be
reconstructed from CI job timestamps. These remain null, never fabricated.
"""
import argparse
from datetime import datetime
import json
import math
import os
import re
import statistics
import sys
from urllib.request import Request, urlopen

SHA40 = re.compile(r"^[0-9a-f]{40}$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
CONCLUSIONS = {"success", "failure", "cancelled", "timed_out", "action_required"}


def seconds(start, finish):
    if not isinstance(start, str) or not isinstance(finish, str):
        return None
    try:
        a = datetime.fromisoformat(start.replace("Z", "+00:00"))
        b = datetime.fromisoformat(finish.replace("Z", "+00:00"))
        if a.tzinfo is None or b.tzinfo is None:
            return None
        value = (b - a).total_seconds()
        return value if math.isfinite(value) and value >= 0 else None
    except (ValueError, OverflowError):
        return None


def _dt(value):
    if not isinstance(value, str):
        return None
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return d if d.tzinfo is not None else None
    except ValueError:
        return None


def summarize_run(run, jobs):
    """One run, not a merged-PR SHA claim. Unknown values remain null."""
    if not isinstance(run, dict) or not isinstance(jobs, list):
        raise ValueError("run and jobs required")
    run_id = run.get("id")
    sha = run.get("head_sha")
    if type(run_id) is not int or run_id < 1 or not isinstance(sha, str) or not SHA40.fullmatch(sha):
        raise ValueError("run ID and exact head SHA required")
    if run.get("status") != "completed" or run.get("conclusion") not in CONCLUSIONS:
        raise ValueError("only completed runs with known conclusions")
    if not jobs:
        raise ValueError("job evidence required; empty job list is not a pass")
    spans, job_api_head_shas = [], []
    for job in jobs:
        if not isinstance(job, dict) or type(job.get("id")) is not int:
            raise ValueError("job ID required")
        a, b = _dt(job.get("started_at")), _dt(job.get("completed_at"))
        if a and b and b >= a:
            spans.append((a, b))
        # Job API head_sha is a reported ref field, NOT observed checkout SHA.
        if isinstance(job.get("head_sha"), str) and SHA40.fullmatch(job["head_sha"]):
            job_api_head_shas.append(job["head_sha"])
    queue = seconds(run.get("created_at"),
                    min((a for a, _ in spans)).isoformat() if spans else None)
    job_wall = (max(b for _, b in spans) - min(a for a, _ in spans)).total_seconds() if spans else None
    job_cpu_sum = sum((b - a).total_seconds() for a, b in spans) if spans else None
    ended = max((b for _, b in spans), default=None)
    return {
        "run_id": run_id,
        "url": run.get("html_url") or None,
        "workflow_name": run.get("name"),
        "event": run.get("event"),
        "head_sha": sha,
        "job_api_head_shas": sorted(set(job_api_head_shas)),
        "actual_checkout_sha": None,  # requires checkout step log evidence; API head_sha is not checkout
        "run_attempt": run.get("run_attempt") if type(run.get("run_attempt")) is int else None,
        "conclusion": run["conclusion"],
        "job_count": len(jobs),
        "timed_job_count": len(spans),
        "queue_seconds": queue,
        "ci_job_wall_seconds": job_wall,
        "ci_job_sum_seconds": job_cpu_sum,
        "first_job_started": min((a for a, _ in spans), default=None).isoformat() if spans else None,
        "last_job_completed": ended.isoformat() if ended else None,
        "tests_passed": None,  # requires explicit per-test log evidence
        "skipped_tests": None,
        "accepted_independent_improvements": None,
        "model_call_seconds": None,
        "verification_phase_seconds": None,
        "operational_followup_seconds": None,
        "whole_cycle_seconds": None,
        "queue_bottleneck": "CI queue only; other waits not measured",
        "usd_cost": None,
        "gpu_training_attested": None,
        "adapter_created_attested": None,
        "heldout_quality_delta": None,
    }


def report(rows, workflow_name, event, window=12):
    """Compare only same workflow and trigger; excludes missing run/job data."""
    if type(window) is not int or not 5 <= window <= 12:
        raise ValueError("comparison window must be 5..12")
    if not workflow_name or not event:
        raise ValueError("workflow and trigger required for task comparability")
    same = [x for x in rows if x["workflow_name"] == workflow_name and x["event"] == event]
    same.sort(key=lambda r: (r["first_job_started"] or "", r["run_id"]))
    samples = same[-window:]
    prev = samples[:-1]
    current = samples[-1] if samples else None
    # Only successful, measured runs support positive latency comparisons.
    prior_good = [r["ci_job_wall_seconds"] for r in prev
                  if r["conclusion"] == "success" and r["ci_job_wall_seconds"] is not None]
    current_good = (current is not None and current["conclusion"] == "success"
                    and current["ci_job_wall_seconds"] is not None)
    median = statistics.median(prior_good) if len(prior_good) >= 5 else None
    change = (100 * (current["ci_job_wall_seconds"] / median - 1)
              if current_good and median is not None and median > 0 else None)
    speed = "판단불가"
    if change is not None:
        speed = ("유지" if abs(change) < 1 else "향상" if change < 0 else "악화")
    failure = sum(r["conclusion"] != "success" for r in samples)
    attempts = [r["run_attempt"] for r in samples]
    retry = (sum(x > 1 for x in attempts) / len(attempts)
             if attempts and all(type(x) is int and x >= 1 for x in attempts) else None)
    # Throughput is CI success events/hour, NOT verified improvements/hour.
    valid = [r for r in samples if r["first_job_started"] and r["last_job_completed"]]
    hourly = None
    if len(valid) >= 2:
        start = min(_dt(r["first_job_started"]) for r in valid)
        end = max(_dt(r["last_job_completed"]) for r in valid)
        hours = (end - start).total_seconds() / 3600
        if hours > 0:
            hourly = sum(r["conclusion"] == "success" for r in valid) / hours
    return {
        "schema_version": 1,
        "source": "GitHub Actions REST runs and jobs, read only",
        "selection": {"workflow_name": workflow_name, "event": event,
                      "window": window, "n": len(samples),
                      "previous_successful_timing_n": len(prior_good)},
        "run_ids": [r["run_id"] for r in samples],
        "runs": samples,
        "ci_speed": {
            "previous_median_seconds": median,
            "current_seconds": current["ci_job_wall_seconds"] if current else None,
            "change_pct": round(change, 2) if change is not None else None,
            "verdict": speed,
            "caveat": "Same workflow/event only; code changes can alter difficulty. Not developer velocity.",
        },
        "observed_ci_failure_rate": failure / len(samples) if samples else None,
        "observed_workflow_rerun_rate": retry,
        "successful_ci_runs_per_hour": hourly,
        "independent_accepted_improvements_per_hour": None,
        "agent_retry_rate": None,
        "regression_rate": None,
        "rollback_rate": None,
        "cost_usd": None,
        "model_call_seconds": None,
        "independent_evaluation_seconds": None,
        "operational_followup_seconds": None,
        "whole_development_cycle_seconds": None,
        "heldout_quality_change": None,
        "developer_speed_verdict": "판단불가",
        "model_quality_verdict": "판단불가",
        "proof_limit": "CI success and job timing are NOT independently accepted code changes or model intelligence gains.",
    }


def github_json(url, token=None):
    if not url.startswith("https://api.github.com/repos/"):
        raise ValueError("refusing arbitrary API host")
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": "oril-v2-read-only-proof-report",
               "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = "Bearer " + token
    with urlopen(Request(url, headers=headers), timeout=20) as response:
        return json.load(response)


def collect(repo, workflow_name, event, window=12, token=None, api=github_json):
    if (not isinstance(repo, str) or not REPO.fullmatch(repo)
            or any(part in (".", "..") for part in repo.split("/"))):
        raise ValueError("owner/repo required")
    root = "https://api.github.com/repos/" + repo
    # Most recent 100 includes failed/queued/other workflows. Never claim
    # exhaustive historical coverage, especially if older runs are absent.
    payload = api(root + "/actions/runs?per_page=100", token)
    if not isinstance(payload, dict):
        raise ValueError("invalid GitHub Actions runs response")
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        raise ValueError("GitHub Actions runs response missing")
    matches = [x for x in runs
               if x.get("name") == workflow_name and x.get("event") == event
               and x.get("status") == "completed" and x.get("conclusion") in CONCLUSIONS]
    matches = matches[:window]
    rows = []
    for run in matches:
        rid = run["id"]
        result = api(root + "/actions/runs/" + str(rid) + "/jobs?per_page=100", token)
        if not isinstance(result.get("jobs"), list):
            raise ValueError("job list missing for run " + str(rid))
        if result.get("total_count", len(result["jobs"])) > len(result["jobs"]):
            raise ValueError("job pagination incomplete for run " + str(rid))
        rows.append(summarize_run(run, result["jobs"]))
    result = report(rows, workflow_name, event, window)
    result["collection"] = {"repository": repo, "run_listing_scope": "latest 100 workflow runs only",
                            "matching_completed_run_count": len(matches),
                            "older_history_exhaustive": False}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--event", default="pull_request")
    parser.add_argument("--window", type=int, default=12)
    parser.add_argument("--output", default="-")
    args = parser.parse_args()
    out = collect(args.repo, args.workflow, args.event, args.window,
                  token=os.environ.get("GITHUB_TOKEN"))
    blob = json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output == "-":
        sys.stdout.write(blob)
    else:
        with open(args.output, "w", encoding="utf-8") as file:
            file.write(blob)


if __name__ == "__main__":
    main()
