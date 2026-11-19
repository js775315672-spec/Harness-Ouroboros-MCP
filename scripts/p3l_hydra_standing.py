"""Reserve approved offline Hydra tasks in a create-only GitHub ref ledger."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from p3l_hydra_fast_lane_gate import IDENT, SHA40, SHA64
from p3l_hydra_github_completion import verify_completion
from p3l_hydra_shared_dispatch import REPO, record_head, request

SUITES = {"fast-lane": "test_p3l_hydra_fast_lane_gate.py",
          "completion-ledger": "test_p3l_hydra_completion_rehearsal.py",
          "checkpoint-model-replay": "test_resumable_task_queue.py"}


def fetch(path):
    return json.loads(subprocess.check_output(["gh", "api", path], timeout=15))


def model_result_proof(approval):
    run = approval["model_result_run"]
    if type(run) is not int or run <= 0 or approval["id"] != f"checkpoint-replay-{run}":
        raise ValueError("invalid approved model replay")
    result = json.loads(Path(f"hydra/model-results/checkpoint-attestation-{run}.json").read_bytes())
    receipt, grade = result["receipt"], result["grade"]
    if (result["schema"] != "hydra-model-result-v1" or result["run"] != run
            or result["verdict"] != "accepted_independent" or result["model_calls"] != 1
            or receipt["run"] != str(run) or receipt["live"] is not True
            or result["candidate_commit"] != approval["head"] or not SHA40.fullmatch(approval["head"])
            or grade["target"] != "tests/test_resumable_task_queue.py"
            or grade["proposal_sha256"] != receipt["proposal_sha256"]
            or not SHA64.fullmatch(grade["candidate_sha256"])
            or grade["normal_test_count"] != 7 or grade["mutant_assertion_failures"] != 3):
        raise ValueError("model receipt does not authorize this exact test replay")
    metadata = fetch(f"repos/{REPO}/actions/runs/{run}")
    if (metadata.get("workflow_id") != 423749758
            or metadata.get("head_branch") != "run/hydra-checkpoint-model-scaffold"
            or metadata.get("status") != "completed" or metadata.get("conclusion") != "success"):
        raise ValueError("model source did not complete with independent success")
    proof = verify_completion(
        dict(task=approval["id"], head=receipt["head"], run_id=run, job_id=result["independent_job"]),
        repository=REPO, workflow=".github/workflows/hydra-checkpoint-model-revised.yml",
        job_name="independent", required_step="Independently grade bound Qwen output", fetch=fetch)
    artifact, = [item for item in result["artifacts"] if item["name"] == "hydra-checkpoint-independent-grade"]
    live = fetch(f"repos/{REPO}/actions/artifacts/{int(artifact['id'])}")
    if (live.get("name") != artifact["name"] or live.get("digest") != artifact["digest"]
            or live.get("workflow_run", {}).get("id") != run):
        raise ValueError("independent grade artifact provenance differs")
    return proof, grade["candidate_sha256"]


def claim(approval, namespace):
    task = approval["id"]
    suite = SUITES[approval["suite"]]
    head = approval["head"]
    candidate_sha = ""
    if approval["suite"] == "checkpoint-model-replay":
        proof, candidate_sha = model_result_proof(approval)
    else:
        event = dict(task=task, head=head, run_id=approval["run"], job_id=approval["job"])
        proof = verify_completion(event, repository=REPO, workflow=approval["workflow"],
                                  job_name="source", required_step="Verify approved intake fixture",
                                  fetch=fetch, trusted_push=(approval["branch"], head,
                                                             approval["workflow_id"]))
    key = hashlib.sha256(task.encode()).hexdigest()
    ref = f"refs/heads/{namespace}/{key}"
    status, body = request("POST", "refs", json.dumps({"ref": ref, "sha": head}).encode())
    if status in (409, 422):
        confirmed, body = request("GET", "ref/" + ref.removeprefix("refs/"))
        if confirmed != 200 or record_head(body, ref) != head:
            raise ValueError("execution ledger conflict")
        print(json.dumps({"task": task, "status": "already_spent", "ref": ref}))
        return None
    if status != 201 or record_head(body, ref) != head:
        raise ValueError(f"execution ledger rejected claim ({status})")
    print(json.dumps({"task": task, "status": "spent", "ref": ref, "proof": proof["sha256"]}))
    return {"task": task, "head": head, "suite": suite, "candidate_sha": candidate_sha}


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
