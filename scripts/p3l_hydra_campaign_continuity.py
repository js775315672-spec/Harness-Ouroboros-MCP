"""Verify completed campaign receipts before preparing the next sequence."""
import base64
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path

from p3l_hydra_next_task import REPO, fetch

LIMIT = 9
WORKFLOW = 423685918


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def next_sequence(checkpoint, read):
    if (checkpoint.get("schema") != "hydra-nine-cycle-checkpoint-v1"
            or checkpoint.get("campaign") != "hydra-nine-cycle" or checkpoint.get("requested") != LIMIT):
        raise ValueError("unexpected campaign checkpoint")
    completed = checkpoint["completed"]
    if not 0 < len(completed) <= LIMIT:
        raise ValueError("unexpected verified cycle count")
    runs, models, tasks = set(), set(), set()
    previous_started_at = None
    for sequence, row in enumerate(completed, 1):
        if (row["sequence"] != sequence or row["run"] in runs or row["model_result_run"] in models
                or row["task"] in tasks or row["run"] == row["model_result_run"]):
            raise ValueError("campaign evidence is reordered or reused")
        root = f"repos/{REPO}/actions"
        run = read(f"{root}/runs/{row['run']}")
        job = read(f"{root}/jobs/{row['job']}")
        if (run["id"] != row["run"] or run["repository"]["full_name"] != REPO
                or run["workflow_id"] != WORKFLOW or run["head_branch"] != "main"
                or run["head_sha"] != row["head"] or run["run_attempt"] != 1
                or run["status"] != "completed" or run["conclusion"] != "success"
                or run["event"] not in {"push", "schedule", "workflow_dispatch"}
                or job["id"] != row["job"] or job["run_id"] != row["run"]
                or job["head_sha"] != row["head"] or job["status"] != "completed"
                or job["name"] != "Worker " + row["task"] or job["conclusion"] != "success"):
            raise ValueError("campaign predecessor lacks exact successful production evidence")
        manifest_file = read(f"repos/{REPO}/contents/hydra/approvals.json?ref={row['head']}")
        if manifest_file.get("type") != "file" or manifest_file.get("encoding") != "base64":
            raise ValueError("unsupported approval manifest evidence")
        manifest = json.loads(base64.b64decode(manifest_file["content"]))
        entries = [item for item in manifest["approvals"] if item["id"] == row["task"]]
        if len(entries) != 1:
            raise ValueError("campaign predecessor requires one exact approval")
        entry = entries[0]
        if entry["model_result_run"] != row["model_result_run"]:
            raise ValueError("model run does not match approved predecessor")
        model = read(f"{root}/runs/{row['model_result_run']}")
        if (model["id"] != row["model_result_run"] or model["repository"]["full_name"] != REPO
                or model["status"] != "completed" or model["conclusion"] != "success"):
            raise ValueError("campaign predecessor lacks exact successful model evidence")
        if len(completed) > 1:
            started_at = datetime.fromisoformat(run["run_started_at"].replace("Z", "+00:00"))
            if started_at.utcoffset() is None:
                raise ValueError("production run start time lacks a timezone")
            if previous_started_at is not None and (started_at <= previous_started_at):
                raise ValueError("production runs are out of order")
            previous_started_at = started_at
        runs.add(row["run"])
        models.add(row["model_result_run"])
        tasks.add(row["task"])
    return {"campaign": checkpoint["campaign"], "completed": len(completed), "requested": LIMIT,
            "next_sequence": len(completed) + 1 if len(completed) < LIMIT else None,
            "previous_run": completed[-1]["run"], "checkpoint_sha256": digest(checkpoint)}


if __name__ == "__main__":
    checkpoint = json.loads(Path("hydra/memory/campaign.json").read_bytes())
    record = next_sequence(checkpoint, fetch)
    output = Path(os.environ["RUNNER_TEMP"], "campaign-continuity.json")
    output.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(record, sort_keys=True))
