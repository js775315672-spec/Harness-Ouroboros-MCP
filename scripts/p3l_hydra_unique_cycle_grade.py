"""Grade a bounded duplicate-evidence rejection expression."""
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

BASE = "d863043c4a8cb3ae5eeb14e46ea5e03f09ebba89"
TARGET = Path("scripts/p3l_hydra_cycle_memory.py")
CASES = """
import copy
from p3l_hydra_cycle_memory import select
row=dict(cycle=1,candidate="a"*40,independent={"normal_passed":1},operational_tests=1,model=10,operation=20,problem="evidence",change="example",lessons=["lesson"])
def check(rows):
    return select(dict(schema="hydra-verified-history-v1",cycles=rows),"evidence")
def rejects(rows):
    try:
        check(rows)
    except ValueError:
        return True
    return False
assert rejects([row,{**row,"cycle":2}]), "duplicate-run-regression"
assert rejects([row,{**row,"cycle":2,"model":30}])
assert rejects([row,{**row,"cycle":2,"operation":30}])
assert rejects([row,{**row,"cycle":2,"model":20,"operation":30}])
assert rejects([{**row,"operation":10}])
assert rejects([row,{**row,"cycle":1,"model":30,"operation":40}])
assert len(check([row,{**row,"cycle":2,"model":30,"operation":40}]))==2
print("UNIQUE CYCLE EVIDENCE 7/7")
"""


def proposal_digest(raw):
    if len(raw) > 32_000 or hashlib.sha256(raw).hexdigest() != "aa45c2f9cc83f6d795429d6681ffb62de7c251f46f8e5909c3662824ec2e34ad":
        raise ValueError("unexpected proposal archive digest")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        if len(members) != 1 or members[0].filename != "proposal.json" or members[0].file_size > 4096:
            raise ValueError("unexpected proposal archive member")
        data = archive.read(members[0])
    expected = json.loads("{\"head\":\"beaa0158e3157c9d343a93ec6f8052d90138e2b9\",\"id\":\"hydra-problem-1fcbfe02d34c6c6147e9\",\"job_id\":135665867403,\"model_calls\":0,\"run_id\":44554240280,\"state\":\"proposed\",\"target\":\"scripts/p3l_hydra_cycle_memory.py\",\"task\":\"Reject duplicate independent and operational run receipts in the cycle memory index.\",\"url\":\"https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44554240280/job/135665867403\"}")
    if json.dumps(json.loads(data), sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ValueError("proposal does not match the reviewed task")
    return hashlib.sha256(data).hexdigest()


def verify(checkout, raw):
    head = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    if head != BASE:
        raise ValueError("unexpected grading checkout HEAD")
    value = unwrap_proposal(raw).decode().strip()
    if "\n" in value or len(value) > 240:
        raise ValueError("expected one bounded expression")
    allowed = (ast.Expression, ast.BoolOp, ast.Or, ast.Compare, ast.In, ast.Eq,
               ast.Subscript, ast.Name, ast.Load, ast.Constant)
    for node in ast.walk(ast.parse(value, mode="eval")):
        if not isinstance(node, allowed):
            raise ValueError("unsupported evidence expression")
        if isinstance(node, ast.Name) and node.id not in {"row", "used_runs"}:
            raise ValueError("unexpected variable")
        if isinstance(node, ast.Constant) and node.value not in {"model", "operation"}:
            raise ValueError("unexpected literal")
    original = (checkout / TARGET).read_text(encoding="utf-8")
    for anchor in ("    seen = set()\n", '        seen.add(row["cycle"])\n'):
        if original.count(anchor) != 1:
            raise ValueError("unexpected memory insertion anchor")
    candidate = original.replace("    seen = set()\n", "    seen = set()\n    used_runs = set()\n")
    anchor = '        seen.add(row["cycle"])\n'
    candidate = candidate.replace(anchor, f'        if {value}:\n            raise ValueError("cycle run already credited")\n'
                                  '        used_runs.update((row["model"], row["operation"]))\n' + anchor)
    with tempfile.TemporaryDirectory(prefix="hydra-unique-cycle-") as folder:
        root = Path(folder)
        root.chmod(0o755)
        source = root / TARGET.name
        def run(code):
            source.write_text(code)
            command = _docker_command(root, "python:3.11-slim", ["-B", "-c", CASES])
            return subprocess.run(command, text=True, capture_output=True, timeout=60)
        baseline = run(original)
        if baseline.returncode != 1 or "AssertionError: duplicate-run-regression" not in baseline.stderr:
            raise ValueError("baseline did not reproduce duplicate credit")
        result = run(candidate)
        if result.returncode != 0 or "UNIQUE CYCLE EVIDENCE 7/7" not in result.stdout:
            raise ValueError("candidate failed evidence regression: " + result.stderr)
    return {"base_sha": BASE, "target": TARGET.as_posix(), "passed": 7,
            "proposal_sha256": hashlib.sha256(raw).hexdigest(),
            "candidate_sha256": hashlib.sha256(candidate.encode()).hexdigest()}
