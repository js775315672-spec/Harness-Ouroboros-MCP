"""Independently check an identity-only Hydra selector repair."""
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

BASE = "5160e12527ff58f644ec5bd91cd3efdc82acc628"
TARGET = Path("scripts/p3l_hydra_next_task.py")
OLD = """f"{run['id']}:{job['id']}" """
OLD = OLD.rstrip()
CASES = """
from p3l_hydra_next_task import select
def p(r,j,head,name,outcome="failure"):
    run=dict(id=r,event="push",head_branch="main",status="completed",run_attempt=1,head_sha=head)
    job=dict(id=j,name=name,conclusion=outcome)
    return select([run],{r:[job]})["proposal"]
first=p(1,2,"a"*40,"Worker a")
repeat=p(3,4,"a"*40,"Worker a")
assert first["id"]==repeat["id"], "duplicate-proposal-regression"
assert first["id"]!=p(3,4,"b"*40,"Worker a")["id"]
assert first["id"]!=p(3,4,"a"*40,"Worker b")["id"]
assert repeat["run_id"]==3 and repeat["job_id"]==4
assert repeat["evidence"].endswith("/runs/3/job/4")
assert p(3,4,"a"*40,"Worker a","success") is None
print("THIRD CYCLE REGRESSION 6/6")
"""


def proposal_digest(raw):
    if len(raw) > 32_000 or hashlib.sha256(raw).hexdigest() != "6ed5329b266974d53302f850bc16be6bd22b5214d4221b8b4d8585fdc82a5f1b":
        raise ValueError("unexpected proposal archive digest")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        if len(members) != 1 or members[0].filename != "proposal.json" or members[0].file_size > 4096:
            raise ValueError("unexpected proposal archive member")
        data = archive.read(members[0])
    expected = json.loads("{\"head\":\"62bb4db2df8a4a3404ca5d10402f7d54e17ba47b\",\"id\":\"hydra-problem-cc6aa17df7b516bfb56a\",\"job_id\":135655008171,\"model_calls\":0,\"run_id\":44551180471,\"state\":\"proposed\",\"target\":\"scripts/p3l_hydra_next_task.py\",\"task\":\"Keep the proposal identity stable for recurring failures of the same job at the same revision.\",\"url\":\"https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44551180471/job/135655008171\"}")
    if json.dumps(json.loads(data), sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ValueError("proposal does not match the reviewed task")
    return hashlib.sha256(data).hexdigest()


def verify(checkout, raw):
    head = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    if head != BASE:
        raise ValueError("unexpected grading checkout HEAD")
    value = unwrap_proposal(raw).decode().strip()
    if "\n" in value or len(value) > 160:
        raise ValueError("expected a bounded identity expression")
    tree = ast.parse(value, mode="eval")
    allowed = (ast.Expression, ast.JoinedStr, ast.FormattedValue, ast.Subscript, ast.Name, ast.Load, ast.Constant)
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise ValueError("unsupported identity expression")
        if isinstance(node, ast.Name) and node.id not in {"run", "job"}:
            raise ValueError("unexpected identity variable")
        if isinstance(node, ast.Constant) and node.value not in {"head_sha", "name", ":"}:
            raise ValueError("unexpected identity literal")
    original = (checkout / TARGET).read_text(encoding="utf-8")
    if original.count(OLD) != 1:
        raise ValueError("unexpected identity anchor")
    candidate = original.replace(OLD, value)
    with tempfile.TemporaryDirectory(prefix="hydra-third-cycle-") as folder:
        root = Path(folder)
        root.chmod(0o755)
        source = root / TARGET.name
        def run(code):
            source.write_text(code)
            command = _docker_command(root, "python:3.11-slim", ["-B", "-c", CASES])
            return subprocess.run(command, text=True, capture_output=True, timeout=60)
        baseline = run(original)
        if baseline.returncode != 1 or "AssertionError: duplicate-proposal-regression" not in baseline.stderr:
            raise ValueError("baseline did not reproduce the issue")
        candidate_result = run(candidate)
        if candidate_result.returncode != 0 or "THIRD CYCLE REGRESSION 6/6" not in candidate_result.stdout:
            raise ValueError("candidate failed regression: " + candidate_result.stderr)
    return {"base_sha": BASE, "target": TARGET.as_posix(), "passed": 6,
            "proposal_sha256": hashlib.sha256(raw).hexdigest(),
            "candidate_sha256": hashlib.sha256(candidate.encode()).hexdigest()}
