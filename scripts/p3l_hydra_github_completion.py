"""Independently validate a GitHub job before admitting a Hydra completion."""
import hashlib
import json
from typing import Callable

from p3l_hydra_fast_lane_gate import SHA40


def verify_completion(event, *, repository: str, workflow: str, job_name: str,
                      required_step: str, fetch: Callable):
    if (type(event) is not dict or set(event) != {"task", "head", "run_id", "job_id"}
            or type(event["head"]) is not str or SHA40.fullmatch(event["head"]) is None
            or any(type(event[key]) is not int or not 0 < event[key] <= 2**63 - 1
                   for key in ("run_id", "job_id"))):
        raise ValueError("invalid GitHub completion identity")
    run_id, job_id = event["run_id"], event["job_id"]
    path = f"repos/{repository}/actions"
    run = fetch(f"{path}/runs/{run_id}")
    if (type(run.get("id")) is not int or run["id"] != run_id
            or run.get("repository", {}).get("full_name") != repository
            or run.get("head_repository", {}).get("full_name") != repository
            or run.get("path") != workflow or run.get("event") != "pull_request"
            or run.get("head_sha") != event["head"] or type(run.get("run_attempt")) is not int
            or run["run_attempt"] != 1):
        raise ValueError("GitHub run does not match the expected workflow and source")
    job = fetch(f"{path}/jobs/{job_id}")
    if (type(job.get("id")) is not int or job["id"] != job_id
            or type(job.get("run_id")) is not int or job["run_id"] != run_id
            or job.get("head_sha") != event["head"] or job.get("name") != job_name
            or job.get("status") != "completed" or job.get("conclusion") != "success"):
        raise ValueError("GitHub job does not identify a successful exact completion")
    steps = [step for step in job.get("steps", []) if step.get("name") == required_step]
    if len(steps) != 1 or steps[0].get("status") != "completed" or steps[0].get("conclusion") != "success":
        raise ValueError("required test step did not complete successfully")
    identity = {**event, "repository": repository, "workflow": workflow, "job": job_name,
                "step": required_step, "attempt": 1, "passed": True}
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())
    return {**event, "sha256": digest.hexdigest(), "passed": True}
