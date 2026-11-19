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

BASE = "953fab313975d1193afaf50fead274064edda964"
TARGET = Path("scripts/p3l_hydra_campaign_continuity.py")
def proposal_digest(raw):
    if len(raw) > 32_000 or hashlib.sha256(raw).hexdigest() != "a34a5c256bb92db94bfd71539ef58c0a0ef8b77e7d747ba16b287a3f482a5843":
        raise ValueError("unexpected proposal archive digest")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        if len(members) != 1 or members[0].filename != "proposal.json" or members[0].file_size > 4096:
            raise ValueError("unexpected proposal archive member")
        data = archive.read(members[0])
    expected = json.loads("{\"head\":\"13a160a43aeef2b5724b0040ce56006546064d97\",\"id\":\"hydra-problem-eb411cdc0ad74760f92a\",\"job_id\":135871512300,\"model_calls\":0,\"run_id\":44612217383,\"state\":\"proposed\",\"target\":\"scripts/p3l_hydra_campaign_continuity.py\",\"task\":\"Require the successful fixed offline suite step within each completed production worker.\",\"url\":\"https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44612217383/job/135871512300\"}")
    if json.dumps(json.loads(data), sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ValueError("proposal does not match the reviewed task")
    return hashlib.sha256(data).hexdigest()


def verify(checkout, raw):
    head = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    if head != BASE:
        raise ValueError("unexpected grading checkout HEAD")
    value = unwrap_proposal(raw).decode().strip()
    tree = ast.parse(value, mode="eval")
    contract = ast.parse("len(steps) != 1", mode="eval")
    if ast.dump(tree) != ast.dump(contract):
        raise ValueError("expected a bounded step-count rejection expression")
    original = (checkout / TARGET).read_text(encoding="utf-8")
    anchor = '        manifest_file = read('
    if original.count(anchor) != 1:
        raise ValueError("unexpected production evidence guard")
    candidate = original.replace(anchor,
        '        if len(completed) > 1 or "steps" in job:\n'
        '            verify_offline_step(job)\n' + anchor)
    helper = """
def verify_offline_step(job):
    steps = [step for step in job.get("steps", []) if step.get("name") == "Execute the fixed suite offline"]
    if MODEL_EXPRESSION or steps[0].get("status") != "completed" or steps[0].get("conclusion") != "success":
        raise ValueError("production predecessor lacks exactly one successful offline suite step")


""".replace("MODEL_EXPRESSION",value)
    candidate = candidate.replace("def next_sequence", helper.lstrip() + "def next_sequence")
    checks = '''
from p3l_hydra_campaign_continuity import verify_offline_step
step=dict(name="Execute the fixed suite offline",status="completed",conclusion="success")
def rejected(job):
    try:
        verify_offline_step(job)
    except ValueError:
        return True
    return False
assert verify_offline_step({"steps":[step]}) is None
assert rejected({})
assert rejected({"steps":[{**step,"conclusion":"skipped"}]})
assert rejected({"steps":[step,step]})
assert rejected({"steps":[{**step,"status":"in_progress"}]})
assert rejected({"steps":[{**step,"name":"unrelated"}]})
print("OFFLINE STEP 6/6")
'''
    with tempfile.TemporaryDirectory(prefix="hydra-offline-step-") as folder:
        root = Path(folder)
        root.chmod(0o755)
        (root / TARGET.name).write_text(candidate)
        (root / "p3l_hydra_next_task.py").write_bytes((checkout / "scripts/p3l_hydra_next_task.py").read_bytes())
        result = subprocess.run(_docker_command(root,"python:3.11-slim",["-c",checks]),
                                text=True,capture_output=True,timeout=60)
        if result.returncode or "OFFLINE STEP 6/6" not in result.stdout:
            raise ValueError("candidate failed offline-step checks: " + result.stderr)
    return {"base_sha":BASE,"target":TARGET.as_posix(),"passed":6,
            "proposal_sha256":hashlib.sha256(raw).hexdigest(),
            "candidate_sha256":hashlib.sha256(candidate.encode()).hexdigest()}
