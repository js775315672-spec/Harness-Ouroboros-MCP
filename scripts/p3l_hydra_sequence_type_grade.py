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

BASE = "d6d8cb9dc288dbdaf8c52af236735876a8879d3b"
TARGET = Path("scripts/p3l_hydra_campaign_continuity.py")
CASES = '''
import base64, json
from p3l_hydra_campaign_continuity import next_sequence, REPO
head = "a"*40
rows = [dict(sequence=i, run=10+i, job=20+i, head=head, task=str(i), model_result_run=30+i) for i in (1,2)]
def call(order, times, first_sequence=1):
    def read(path):
        if "/contents/" in path:
            approvals = [{"id":r["task"],"model_result_run":r["model_result_run"]} for r in rows]
            return dict(type="file",encoding="base64",content=base64.b64encode(json.dumps(dict(approvals=approvals)).encode()).decode())
        ident = int(path.rsplit("/",1)[-1])
        if "/jobs/" in path:
            return dict(id=ident,run_id=ident-10,head_sha=head,status="completed",name="Worker "+rows[ident-21]["task"],conclusion="success")
        result = dict(id=ident,repository=dict(full_name=REPO),status="completed",conclusion="success")
        if ident in (11,12):
            result.update(workflow_id=423685918,head_branch="main",head_sha=head,run_attempt=1,event="push",run_started_at=times[ident-11])
        return result
    return next_sequence(dict(schema="hydra-nine-cycle-checkpoint-v1",campaign="hydra-nine-cycle",requested=9,
                              completed=[{**rows[i],"sequence":first_sequence if j == 1 else j} for j,i in enumerate(order,1)]),read)
def blocked(order,times,first_sequence=1):
    try:
        call(order,times,first_sequence)
    except ValueError:
        return True
    return False
times=("2026-11-19T10:00:00Z","2026-11-19T11:00:00Z")
assert blocked((0,1),times,True), "sequence-type-regression"
assert blocked((0,1),times,1.0)
assert blocked((0,1),times,"1")
assert call((0,1),times)["next_sequence"]==3
assert blocked((1,0),times)
print("SEQUENCE TYPE 5/5")
'''


def proposal_digest(raw):
    if len(raw) > 32_000 or hashlib.sha256(raw).hexdigest() != "5cfc8b6738e6505852be7c362527c987022736e9049ea390af03d84b268b2065":
        raise ValueError("unexpected proposal archive digest")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        if len(members) != 1 or members[0].filename != "proposal.json" or members[0].file_size > 4096:
            raise ValueError("unexpected proposal archive member")
        data = archive.read(members[0])
    expected = json.loads("{\"head\":\"9b3eca44687cc5f96530273f29d7aa4d3146f491\",\"id\":\"hydra-problem-8e88d706c7d3ae0858a3\",\"job_id\":135792182226,\"model_calls\":0,\"run_id\":44589741112,\"state\":\"proposed\",\"target\":\"scripts/p3l_hydra_campaign_continuity.py\",\"task\":\"Reject non-integer sequence values in verified campaign receipts.\",\"url\":\"https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44589741112/job/135792182226\"}")
    if json.dumps(json.loads(data), sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ValueError("proposal does not match the reviewed task")
    return hashlib.sha256(data).hexdigest()


def verify(checkout, raw):
    head = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    if head != BASE:
        raise ValueError("unexpected grading checkout HEAD")
    value = unwrap_proposal(raw).decode().strip()
    if "\n" in value or len(value) > 160:
        raise ValueError("expected one bounded expression")
    tree = ast.parse(value, mode="eval")
    expected = ast.parse("type(row['sequence']) is not int", mode="eval")
    if ast.dump(tree) != ast.dump(expected):
        raise ValueError("expected an exact integer type check on sequence")
    original = (checkout / TARGET).read_text(encoding="utf-8")
    anchor = '        if (row["sequence"] != sequence'
    if original.count(anchor) != 1:
        raise ValueError("unexpected sequence guard anchor")
    candidate = original.replace(anchor, f"        if ({value} or " + anchor.removeprefix("        if ("))
    with tempfile.TemporaryDirectory(prefix="hydra-predecessor-") as folder:
        root = Path(folder)
        root.chmod(0o755)
        source = root / TARGET.name
        helper = root / "p3l_hydra_next_task.py"
        helper.write_bytes((checkout / "scripts/p3l_hydra_next_task.py").read_bytes())
        def run(code):
            source.write_text(code)
            return subprocess.run(_docker_command(root, "python:3.11-slim", ["-B", "-c", CASES]),
                                  text=True, capture_output=True, timeout=60)
        baseline = run(original)
        if baseline.returncode != 1 or "AssertionError: sequence-type-regression" not in baseline.stderr:
            raise ValueError("baseline did not reproduce invalid sequence acceptance: " + baseline.stderr)
        result = run(candidate)
        if result.returncode != 0 or "SEQUENCE TYPE 5/5" not in result.stdout:
            raise ValueError("candidate failed sequence type regression: " + result.stderr)
    return {"base_sha": BASE, "target": TARGET.as_posix(), "passed": 5,
            "proposal_sha256": hashlib.sha256(raw).hexdigest(),
            "candidate_sha256": hashlib.sha256(candidate.encode()).hexdigest()}
