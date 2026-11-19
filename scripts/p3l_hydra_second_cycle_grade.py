"""Independently check a one-line Hydra selector proposal in an offline container."""
import ast
import hashlib
import subprocess
import tempfile
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


def verify(checkout, raw):
    assert subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip() == BASE
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
    assert original.count(OLD) == 1
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
