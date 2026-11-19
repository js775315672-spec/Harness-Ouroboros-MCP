"""Independently check a one-line Hydra selector proposal in an offline container."""
import ast
import hashlib
import io
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path

from disposable_regression_compare import _docker_command
from p3l_w08_verify_test import unwrap_proposal

BASE = "ab2fcda4ad04491623aa287598cef727496d83a9"
TARGET = Path("scripts/p3l_hydra_next_task.py")
OLD = 'conclusion not in {"success", "failure", "timed_out"}'
ALLOWED = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not,
           ast.Compare, ast.In, ast.NotIn, ast.Is, ast.IsNot, ast.Eq, ast.NotEq,
           ast.Name, ast.Load, ast.Constant, ast.Set, ast.Tuple, ast.List)
CASES = """
from p3l_hydra_next_task import select
def run(i):
    return dict(id=i,event="push",head_branch="main",status="completed",run_attempt=1,head_sha="a"*40)
def job(i,name,c):
    return dict(id=i,name=name,conclusion=c)
def one(name,c):
    return select([run(1)],{1:[job(1,name,c)]})["decision"]
assert one("Worker a","cancelled")=="needs_approval", "cancelled-worker-regression"
assert one("admit","cancelled")=="no_unresolved_failure"
assert one("Worker a","skipped")=="no_unresolved_failure"
assert one("Worker a","unexpected")=="no_unresolved_failure"
assert one("Worker a","timed_out")=="needs_approval"
assert one("admit","failure")=="needs_approval"
assert select([run(1),run(2)],{1:[job(1,"Worker a","cancelled")],2:[job(2,"Worker a","success")]})["proposal"] is None
assert select([run(1),run(2)],{1:[job(1,"Worker a","cancelled")],2:[job(2,"Worker a","skipped")]})["proposal"]["job_id"]==1
print("SECOND CYCLE REGRESSION 8/8")
"""


def proposal_digest(raw):
    if len(raw) > 32_000 or hashlib.sha256(raw).hexdigest() != "1e6f018d34ec964b7c124b030fac5912871f24c69ae0efb4d438ab3e86c1b7ed":
        raise ValueError("unexpected proposal archive digest")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        if len(members) != 1 or members[0].filename != "proposal.json" or members[0].file_size > 4096:
            raise ValueError("unexpected proposal archive member")
        data = archive.read(members[0])
    expected = {
        "head": "12a384f5c6f21588cd55413957f693eacab2ec66",
        "id": "hydra-problem-4e6bedd9950af20fff1f",
        "job_id": 135570224389, "model_calls": 0, "run_id": 44527038293,
        "state": "proposed", "target": TARGET.as_posix(),
        "task": "Handle cancelled approved workers in Hydra next-task selection.",
        "url": "https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44527038293/job/135570224389",
    }
    if json.dumps(json.loads(data), sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ValueError("proposal does not match the reviewed task")
    return hashlib.sha256(data).hexdigest()


def verify(checkout, raw):
    head = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    if head != BASE:
        raise ValueError("unexpected grading checkout HEAD")
    value = unwrap_proposal(raw).decode().strip()
    if "\n" in value or len(value) > 300:
        raise ValueError("expected one bounded expression")
    tree = ast.parse(value, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED) or isinstance(node, ast.Name) and node.id not in {"conclusion", "match"}:
            raise ValueError("unsupported predicate syntax")
        if isinstance(node, ast.Constant) and node.value not in (None, "success", "failure", "timed_out", "cancelled", "skipped"):
            raise ValueError("unexpected predicate literal")
    original = (checkout / TARGET).read_text(encoding="utf-8")
    if original.count(OLD) != 1:
        raise ValueError("unexpected selector replacement anchor")
    candidate = original.replace(OLD, value)
    with tempfile.TemporaryDirectory(prefix="hydra-second-cycle-") as folder:
        root = Path(folder)
        root.chmod(0o755)
        source = root / TARGET.name
        source.write_text(original)
        def run():
            command = _docker_command(root, "python:3.11-slim", ["-B", "-c", CASES])
            return subprocess.run(command, text=True, capture_output=True, timeout=60)
        baseline = run()
        if baseline.returncode != 1 or "AssertionError: cancelled-worker-regression" not in baseline.stderr:
            raise ValueError("the pinned baseline did not reproduce the intended failure: " + baseline.stderr)
        source.write_text(candidate)
        checked = run()
        if checked.returncode != 0 or "SECOND CYCLE REGRESSION 8/8" not in checked.stdout:
            raise ValueError("generated predicate failed independent checks: " + checked.stderr)
    return {"base_sha": BASE, "target": TARGET.as_posix(), "passed": 8,
            "proposal_sha256": hashlib.sha256(raw).hexdigest(),
            "candidate_sha256": hashlib.sha256(candidate.encode()).hexdigest()}
