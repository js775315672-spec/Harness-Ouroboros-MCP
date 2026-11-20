"""Fail-closed, offline consistency check for separately saved GitHub Actions run/jobs API JSON.

This checks two *supplied* snapshots for internal consistency, not their authenticity.
For real provenance, independently fetch or archive the GitHub API response and URL.
No network, token access, model invocation, training, or deployment is performed.
"""

import argparse
import json
from pathlib import Path

from scripts.oril_v2_job_telemetry import extract


def _positive_int(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def assemble(run, jobs_page, expected_sha):
    """Require matching run ID, attempt and SHA for a complete job page."""
    if not isinstance(run, dict) or not isinstance(jobs_page, dict):
        raise ValueError("run and jobs_page JSON objects required")
    run_id = _positive_int(run.get("id"), "run id")
    attempt = _positive_int(run.get("run_attempt"), "run attempt")
    jobs = jobs_page.get("jobs")
    total = jobs_page.get("total_count")
    if not isinstance(jobs, list) or isinstance(total, bool) or not isinstance(total, int) or total < 1:
        raise ValueError("complete nonempty jobs list with total_count required")
    if len(jobs) != total:
        raise ValueError("jobs page is incomplete or total_count mismatch; paginate before measuring")
    for job in jobs:
        if not isinstance(job, dict):
            raise ValueError("each job must be a JSON object")
        if job.get("run_id") != run_id or isinstance(job.get("run_id"), bool):
            raise ValueError("job run_id mismatch")
        if job.get("run_attempt") != attempt or isinstance(job.get("run_attempt"), bool):
            raise ValueError("job run_attempt mismatch")
        if job.get("head_sha") != run.get("head_sha"):
            raise ValueError("job head_sha mismatch")
    result = extract({"head_sha": run.get("head_sha"), "run_id": run_id, "jobs": jobs}, expected_sha)
    result.update({
        "run_attempt": attempt,
        "run_status": run.get("status"),
        "run_conclusion": run.get("conclusion"),
        "jobs_reported_total": total,
        "source_run_url": run.get("html_url"),
        "snapshot_authenticity": "unverified",
    })
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_json", type=Path)
    parser.add_argument("jobs_json", type=Path)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args()
    run = json.loads(args.run_json.read_text(encoding="utf-8"))
    jobs = json.loads(args.jobs_json.read_text(encoding="utf-8"))
    print(json.dumps(assemble(run, jobs, args.sha), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
