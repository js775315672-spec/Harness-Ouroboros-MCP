"""Verify a bounded model-generated check binding a campaign predecessor."""
import ast
import hashlib
import io
import json
import subprocess
import tempfile
from pathlib import Path
import zipfile

from disposable_regression_compare import _docker_command
from p3l_w08_verify_test import unwrap_proposal

BASE = "90cabdb3bd779aae67aa8d9fcb717e16221c4ecc"
TARGET = Path("scripts/p3l_hydra_campaign_continuity.py")
def proposal_digest(raw):
    if len(raw) > 32_000 or hashlib.sha256(raw).hexdigest() != "16a03a39fd33e98bcdd467f5a01db985db5e1b4e99ccacf0da1d8c6a37cb0c73":
        raise ValueError("unexpected proposal archive digest")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        if len(members) != 1 or members[0].filename != "proposal.json" or members[0].file_size > 4096:
            raise ValueError("unexpected proposal archive member")
        data = archive.read(members[0])
    expected = json.loads("{\"head\":\"c467d11d038e47c9b031952b21f4e9fc14099280\",\"id\":\"hydra-problem-2a2115186c5b31556d48\",\"job_id\":135853658215,\"model_calls\":0,\"run_id\":44607117836,\"state\":\"proposed\",\"target\":\"scripts/p3l_hydra_campaign_continuity.py\",\"task\":\"Recognize a successful original model worker and its bound independent regrade in campaign continuity.\",\"url\":\"https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44607117836/job/135853658215\"}")
    if json.dumps(json.loads(data), sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ValueError("proposal does not match the reviewed task")
    return hashlib.sha256(data).hexdigest()


def verify(checkout, raw):
    head = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    if head != BASE:
        raise ValueError("unexpected grading checkout HEAD")
    value = unwrap_proposal(raw).decode().strip()
    tree = ast.parse(value, mode="eval")
    contract = ast.parse("model['conclusion'] != 'success' and not regrade_verified", mode="eval")
    if ast.dump(tree) != ast.dump(contract):
        raise ValueError("expected a model failure condition with explicitly verified regrade fallback")
    original = (checkout / TARGET).read_text(encoding="utf-8")
    anchor = 'or model["status"] != "completed" or model["conclusion"] != "success"):'
    if original.count(anchor) != 1:
        raise ValueError("unexpected model verdict guard")
    candidate = original.replace(
        '        if (model["id"]',
        '        regrade_verified = model["conclusion"] == "failure" and verified_regrade(root, row, model, read)\n'
        '        if (model["id"]')
    candidate = candidate.replace(anchor, f'or model["status"] != "completed" or ({value})):')
    helper = """
def verified_regrade(root, row, model, read):
    if (row["model_result_run"], row["run"], row["head"], row["task"]) != (
        44602759555, 44606221168, "669ba2845dbafe7e300ac01b3d27231b3e60cb03", "grade-artifact-replay-44602759555"
    ):
        return False
    if (model.get("head_sha"), model.get("head_branch"), model.get("run_attempt")) != (
        "9f2eab88f4828c50818872e056911c77c04a4e28", "run/hydra-campaign-cycle-seven-model", 1
    ):
        return False
    worker = read(f"{root}/jobs/135838532777")
    grade = read(f"{root}/runs/44603716265")
    judge = read(f"{root}/jobs/135841694335")
    if (grade.get("id"), grade.get("head_sha"), grade.get("path"), grade.get("run_attempt"),
            grade.get("conclusion"), grade.get("repository", {}).get("full_name")) != (
        44603716265, "90398ed50acb2ad9ea53c8302d0d07fdc4ff871e",
        ".github/workflows/hydra-campaign-cycle-seven-regrade.yml", 1, "success", REPO
    ):
        return False
    return (
        (worker.get("id"), worker.get("run_id"), worker.get("head_sha"), worker.get("name"), worker.get("conclusion"))
        == (135838532777, 44602759555, model["head_sha"], "worker", "success")
        and (judge.get("id"), judge.get("run_id"), judge.get("head_sha"), judge.get("name"), judge.get("conclusion"))
        == (135841694335, 44603716265, grade["head_sha"], "independent", "success")
    )


"""
    candidate = candidate.replace("def next_sequence", helper.lstrip() + "def next_sequence")
    checks = '''
from p3l_hydra_campaign_continuity import verified_regrade, REPO
row=dict(model_result_run=44602759555,run=44606221168,head="669ba2845dbafe7e300ac01b3d27231b3e60cb03",task="grade-artifact-replay-44602759555")
model=dict(head_sha="9f2eab88f4828c50818872e056911c77c04a4e28",head_branch="run/hydra-campaign-cycle-seven-model",run_attempt=1)
grade=dict(id=44603716265,head_sha="90398ed50acb2ad9ea53c8302d0d07fdc4ff871e",path=".github/workflows/hydra-campaign-cycle-seven-regrade.yml",run_attempt=1,conclusion="success",repository={"full_name":REPO})
worker=dict(id=135838532777,run_id=44602759555,head_sha=model["head_sha"],name="worker",conclusion="success")
judge=dict(id=135841694335,run_id=44603716265,head_sha=grade["head_sha"],name="independent",conclusion="success")
def proof(row=row, model=model, grade=grade, worker=worker, judge=judge):
    evidence={"r/jobs/135838532777":worker,"r/runs/44603716265":grade,"r/jobs/135841694335":judge}
    return verified_regrade("r",row,model,evidence.__getitem__)
assert proof()
assert not proof(row={**row,"run":1})
assert not proof(model={**model,"run_attempt":2})
assert not proof(grade={**grade,"conclusion":"failure"})
assert not proof(worker={**worker,"conclusion":"failure"})
assert not proof(judge={**judge,"run_id":44602759555})
def reject(model,regrade_verified):
    return MODEL_EXPRESSION
assert reject({"conclusion":"failure"},False) and not reject({"conclusion":"failure"},True) and not reject({"conclusion":"success"},False)
print("REGRADE CONTINUITY 7/7")
'''.replace("MODEL_EXPRESSION",value)
    with tempfile.TemporaryDirectory(prefix="hydra-regrade-continuity-") as folder:
        root = Path(folder)
        root.chmod(0o755)
        (root / TARGET.name).write_text(candidate)
        (root / "p3l_hydra_next_task.py").write_bytes((checkout / "scripts/p3l_hydra_next_task.py").read_bytes())
        result = subprocess.run(_docker_command(root,"python:3.11-slim",["-c",checks]),
                                text=True,capture_output=True,timeout=60)
        if result.returncode or "REGRADE CONTINUITY 7/7" not in result.stdout:
            raise ValueError("candidate failed regrade continuity checks: " + result.stderr)
    return {"base_sha":BASE,"target":TARGET.as_posix(),"passed":7,
            "proposal_sha256":hashlib.sha256(raw).hexdigest(),
            "candidate_sha256":hashlib.sha256(candidate.encode()).hexdigest()}
