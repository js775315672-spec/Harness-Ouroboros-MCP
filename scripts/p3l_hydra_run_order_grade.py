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

BASE = "fe3bba3d6191832997126baa1127a43d6675a4cd"
TARGET = Path("scripts/p3l_hydra_campaign_continuity.py")
CASES = '''
import base64, json
from p3l_hydra_campaign_continuity import next_sequence, REPO
head = "a"*40
rows = [dict(sequence=i, run=10+i, job=20+i, head=head, task=str(i), model_result_run=30+i) for i in (1,2)]
def call(order, times):
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
                              completed=[{**rows[i],"sequence":j} for j,i in enumerate(order,1)]),read)
def blocked(order,times):
    try:
        call(order,times)
    except ValueError:
        return True
    return False
times=("2026-11-19T10:00:00Z","2026-11-19T11:00:00Z")
assert blocked((1,0),times), "run-order-regression"
assert call((0,1),times)["next_sequence"]==3
assert blocked((0,1),(times[0],times[0]))
assert blocked((0,1),(times[0],"2026-11-19T11:00:00+01:00"))
assert blocked((0,1),(times[0],"2026-11-19T11:00:00"))
print("RUN ORDER 5/5")
'''


def proposal_digest(raw):
    if len(raw) > 32_000 or hashlib.sha256(raw).hexdigest() != "c97deead49355632d056042ffa9e5d5272d0a0caa871145f1daa4d8708eb2f37":
        raise ValueError("unexpected proposal archive digest")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        if len(members) != 1 or members[0].filename != "proposal.json" or members[0].file_size > 4096:
            raise ValueError("unexpected proposal archive member")
        data = archive.read(members[0])
    expected = json.loads("{\"head\":\"827dae72f2800ede51791bfbca89c3bffe0459ff\",\"id\":\"hydra-problem-39c0db33e0291f8a7f54\",\"job_id\":135689943524,\"model_calls\":0,\"run_id\":44560996084,\"state\":\"proposed\",\"target\":\"scripts/p3l_hydra_campaign_continuity.py\",\"task\":\"Reject reordered successful production runs in the continuous campaign checkpoint.\",\"url\":\"https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44560996084/job/135689943524\"}")
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
    comparison = tree.body
    if (not isinstance(comparison, ast.Compare) or len(comparison.ops) != 1
            or not isinstance(comparison.ops[0], (ast.Lt, ast.LtE, ast.Gt, ast.GtE))
            or not all(isinstance(node, ast.Name) for node in [comparison.left, *comparison.comparators])
            or {comparison.left.id, comparison.comparators[0].id} != {"started_at", "previous_started_at"}):
        raise ValueError("expected one comparison of the two evidence timestamps")
    original = (checkout / TARGET).read_text(encoding="utf-8")
    anchor = '        runs.add(row["run"])\n'
    if original.count(anchor) != 1:
        raise ValueError("unexpected run order anchor")
    candidate = original.replace("import base64\n", "import base64\nfrom datetime import datetime\n")
    candidate = candidate.replace("    for sequence, row", "    previous_started_at = None\n    for sequence, row")
    candidate = candidate.replace(anchor,
        '        started_at = datetime.fromisoformat(run["run_started_at"].replace("Z", "+00:00"))\n'
        '        if started_at.utcoffset() is None:\n'
        '            raise ValueError("production run start time lacks a timezone")\n'
        f'        if previous_started_at is not None and ({value}):\n'
        '            raise ValueError("production runs are out of order")\n'
        '        previous_started_at = started_at\n' + anchor)
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
        if baseline.returncode != 1 or "AssertionError: run-order-regression" not in baseline.stderr:
            raise ValueError("baseline did not reproduce reordered runs: " + baseline.stderr)
        result = run(candidate)
        if result.returncode != 0 or "RUN ORDER 5/5" not in result.stdout:
            raise ValueError("candidate failed run order regression: " + result.stderr)
    return {"base_sha": BASE, "target": TARGET.as_posix(), "passed": 5,
            "proposal_sha256": hashlib.sha256(raw).hexdigest(),
            "candidate_sha256": hashlib.sha256(candidate.encode()).hexdigest()}
