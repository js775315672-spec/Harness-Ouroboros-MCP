"""Reserve approved offline Hydra tasks in a create-only GitHub ref ledger."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

from p3l_hydra_fast_lane_gate import IDENT, SHA40, SHA64
from p3l_hydra_github_completion import verify_completion
from p3l_hydra_shared_dispatch import REPO, record_head, request

SUITES = {"fast-lane": "test_p3l_hydra_fast_lane_gate.py",
          "completion-ledger": "test_p3l_hydra_completion_rehearsal.py",
          "checkpoint-model-replay": "test_resumable_task_queue.py",
          "selector-model-replay": "test_p3l_hydra_cancelled_worker.py",
          "identity-model-replay": "test_p3l_hydra_proposal_identity.py"}


def fetch(path):
    return json.loads(subprocess.check_output(["gh", "api", path], timeout=15))


def verify_grade_archive(raw, artifact, receipt, grade):
    if len(raw) > 256_000 or "sha256:" + hashlib.sha256(raw).hexdigest() != artifact["digest"]:
        raise ValueError("independent grade ZIP digest differs")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        if (len(members) != 1 or members[0].filename != "grade.json"
                or members[0].file_size > 64_000):
            raise ValueError("unexpected independent grade ZIP contents")
        observed = json.loads(archive.read(members[0]))
    expected = {"receipt": receipt, "grade": grade}
    if json.dumps(observed, sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ValueError("independent grade ZIP differs from ledger receipt")


def model_result_proof(approval):
    run = approval["model_result_run"]
    identity = approval["suite"] == "identity-model-replay"
    selector = identity or approval["suite"] == "selector-model-replay"
    family = "identity" if identity else "selector" if selector else "checkpoint"
    target = "scripts/p3l_hydra_next_task.py" if selector else "tests/test_resumable_task_queue.py"
    prefix = "proposal-identity" if identity else "cancelled-worker" if selector else "checkpoint-attestation"
    if type(run) is not int or run <= 0 or approval["id"] != f"{family}-replay-{run}":
        raise ValueError("invalid approved model replay")
    result = json.loads(Path(f"hydra/model-results/{prefix}-{run}.json").read_bytes())
    receipt, grade = result["receipt"], result["grade"]
    if (result["schema"] != "hydra-model-result-v1" or result["run"] != run
            or result["verdict"] != "accepted_independent" or result["model_calls"] != 1
            or receipt["run"] != str(run) or receipt["live"] is not True
            or result["candidate_commit"] != approval["head"] or not SHA40.fullmatch(approval["head"])
            or grade["target"] != target
            or grade["proposal_sha256"] != receipt["proposal_sha256"]
            or not SHA64.fullmatch(grade["candidate_sha256"])
            or (selector and (
                type(grade.get("passed")) is not int or grade["passed"] != (6 if identity else 8)
                or grade.get("base_sha") != ("5160e12527ff58f644ec5bd91cd3efdc82acc628" if identity else "ab2fcda4ad04491623aa287598cef727496d83a9")
                or receipt.get("proposal_task_sha256") != ("780c02af6109a7913dbf39dbb69c72f29383947e7a598bea1eef221b3ffcbebf" if identity else "e412a21bc82b6934432ea7fac7741bc4bf0feab90578a1637db2daac17f43730")))
            or (not selector and (grade["normal_test_count"] != 7 or grade["mutant_assertion_failures"] != 3))):
        raise ValueError("model receipt does not authorize this exact test replay")
    metadata = fetch(f"repos/{REPO}/actions/runs/{run}")
    if (metadata.get("workflow_id") != (423988182 if identity else 423972341 if selector else 423749758)
            or metadata.get("head_branch") != ("run/hydra-third-cycle-model" if identity else "run/hydra-second-cycle-exception" if selector else "run/hydra-checkpoint-model-scaffold")
            or metadata.get("status") != "completed" or metadata.get("conclusion") != "success"):
        raise ValueError("model source did not complete with independent success")
    proof = verify_completion(
        dict(task=approval["id"], head=receipt["head"], run_id=run, job_id=result["independent_job"]),
        repository=REPO, workflow=(".github/workflows/hydra-third-cycle-model.yml" if identity else ".github/workflows/hydra-second-cycle-exception.yml" if selector
                                   else ".github/workflows/hydra-checkpoint-model-revised.yml"),
        job_name="independent", required_step="Independently grade bound Qwen output", fetch=fetch)
    artifact, = [item for item in result["artifacts"] if item["name"] == "hydra-checkpoint-independent-grade"]
    live = fetch(f"repos/{REPO}/actions/artifacts/{int(artifact['id'])}")
    if (live.get("name") != artifact["name"] or live.get("digest") != artifact["digest"]
            or live.get("workflow_run", {}).get("id") != run or live.get("expired") is not False
            or type(live.get("size_in_bytes")) is not int or not 0 < live["size_in_bytes"] <= 256_000):
        raise ValueError("independent grade artifact provenance differs")
    raw = subprocess.check_output(["gh", "api", f"repos/{REPO}/actions/artifacts/{int(artifact['id'])}/zip"],
                                  timeout=30)
    verify_grade_archive(raw, artifact, receipt, grade)
    return proof, grade["candidate_sha256"], target


def claim(approval, namespace):
    task = approval["id"]
    suite = SUITES[approval["suite"]]
    head = approval["head"]
    key = hashlib.sha256(task.encode()).hexdigest()
    ref = f"refs/heads/{namespace}/{key}"
    read_ref = "/ref/" + ref.removeprefix("refs/")
    existing, body = request("GET", read_ref)
    if existing == 200:
        if record_head(body, ref) != head:
            raise ValueError("execution ledger conflict")
        print(json.dumps({"task": task, "status": "already_spent", "ref": ref}))
        return None
    if existing != 404:
        raise ValueError(f"execution ledger lookup failed ({existing})")
    candidate_sha = ""
    candidate_target = ""
    if approval["suite"] in {"checkpoint-model-replay", "selector-model-replay", "identity-model-replay"}:
        proof, candidate_sha, candidate_target = model_result_proof(approval)
    else:
        event = dict(task=task, head=head, run_id=approval["run"], job_id=approval["job"])
        proof = verify_completion(event, repository=REPO, workflow=approval["workflow"],
                                  job_name="source", required_step="Verify approved intake fixture",
                                  fetch=fetch, trusted_push=(approval["branch"], head,
                                                             approval["workflow_id"]))
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
    return {"task": task, "head": head, "suite": suite, "candidate_sha": candidate_sha, "candidate_target": candidate_target}


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
