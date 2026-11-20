"""Extract auditable job timing from GitHub Actions jobs JSON; no network or inference."""
import argparse
import datetime as dt
import json
from pathlib import Path


def seconds(start, end):
    if not isinstance(start, str) or not isinstance(end, str):
        return None
    try:
        a = dt.datetime.fromisoformat(start.replace("Z", "+00:00"))
        b = dt.datetime.fromisoformat(end.replace("Z", "+00:00"))
        if a.tzinfo is None or b.tzinfo is None:
            return None
        duration = (b - a).total_seconds()
        return duration if duration >= 0 else None
    except ValueError:
        return None


def extract(payload, expected_sha):
    """Fail closed on missing/mismatched run SHA; never equate CI with improvement."""
    if not isinstance(payload, dict) or not isinstance(expected_sha, str) or len(expected_sha) != 40:
        raise ValueError("40-character expected commit SHA required")
    if payload.get("head_sha") != expected_sha:
        raise ValueError("workflow head_sha mismatch or missing")
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("jobs list required")
    rows = []
    for job in jobs:
        if not isinstance(job, dict) or not isinstance(job.get("id"), int):
            raise ValueError("job id required")
        elapsed = seconds(job.get("started_at"), job.get("completed_at"))
        rows.append({
            "job_id": job["id"],
            "name": job.get("name"),
            "status": job.get("status"),
            "conclusion": job.get("conclusion"),
            "duration_seconds": elapsed,
            "measured": elapsed is not None,
        })
    return {
        "schema_version": 1,
        "source": "github_actions_jobs",
        "head_sha": expected_sha,
        "run_id": payload.get("run_id"),
        "jobs": rows,
        "measured_job_count": sum(x["measured"] for x in rows),
        "unmeasured_job_count": sum(not x["measured"] for x in rows),
        "independent_verification": "unverified",
        "model_quality_change": "unmeasured",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("jobs_json", type=Path)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args()
    result = extract(json.loads(args.jobs_json.read_text(encoding="utf-8")), args.sha)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
