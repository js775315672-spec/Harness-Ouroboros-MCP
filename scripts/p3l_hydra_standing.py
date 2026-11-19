"""Reserve approved offline Hydra tasks in a create-only GitHub ref ledger."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from p3l_hydra_fast_lane_gate import IDENT
from p3l_hydra_github_completion import verify_completion
from p3l_hydra_shared_dispatch import REPO, record_head, request

SUITES = {"fast-lane": "test_p3l_hydra_fast_lane_gate.py",
          "completion-ledger": "test_p3l_hydra_completion_rehearsal.py"}


def fetch(path):
    return json.loads(subprocess.check_output(["gh", "api", path], timeout=15))


def claim(approval, namespace):
    task = approval["id"]
    suite = SUITES[approval["suite"]]
    event = dict(task=task, head=approval["head"], run_id=approval["run"], job_id=approval["job"])
    proof = verify_completion(event, repository=REPO, workflow=approval["workflow"],
                              job_name="source", required_step="Verify approved intake fixture",
                              fetch=fetch, trusted_push=(approval["branch"], approval["head"],
                                                         approval["workflow_id"]))
    key = hashlib.sha256(task.encode()).hexdigest()
    ref = f"refs/heads/{namespace}/{key}"
    status, body = request("POST", "refs", json.dumps({"ref": ref, "sha": event["head"]}).encode())
    if status in (409, 422):
        confirmed, body = request("GET", "ref/" + ref.removeprefix("refs/"))
        if confirmed != 200 or record_head(body, ref) != event["head"]:
            raise ValueError("execution ledger conflict")
        print(json.dumps({"task": task, "status": "already_spent", "ref": ref}))
        return None
    if status != 201 or record_head(body, ref) != event["head"]:
        raise ValueError(f"execution ledger rejected claim ({status})")
    print(json.dumps({"task": task, "status": "spent", "ref": ref, "proof": proof["sha256"]}))
    return {"task": task, "head": event["head"], "suite": suite}


def main():
    mode = sys.argv[1]
    if mode not in {"review", "production"} or os.environ["GITHUB_REPOSITORY"] != REPO:
        raise ValueError("invalid Hydra invocation")
    if mode == "production":
        status, body = request("GET", "ref/heads/main")
        if status != 200 or record_head(body, "refs/heads/main") != os.environ["GITHUB_SHA"]:
            raise ValueError("stale production approval checkout")
    manifest = json.loads(Path("hydra/approvals.json").read_bytes())
    approvals = manifest["approvals"]
    tasks = [entry["id"] for entry in approvals]
    if (type(manifest["enabled"]) is not bool or len(tasks) > 2 or len(set(tasks)) != len(tasks)
            or any(type(task) is not str or not IDENT.fullmatch(task) for task in tasks)
            or any(entry["suite"] not in SUITES for entry in approvals)):
        raise ValueError("invalid approval manifest")
    queue = []
    if mode == "review" or manifest["enabled"]:
        namespace = "rehearsal/hydra-standing" if mode == "review" else "hydra-ledger/spent"
        queue = [job for entry in approvals if (job := claim(entry, namespace)) is not None]
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"tasks={json.dumps(queue, separators=(',', ':'))}\n")


if __name__ == "__main__":
    main()
