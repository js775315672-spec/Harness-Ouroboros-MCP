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

BASE = "9e770aae0e992d4f477d15484f10b677159db97a"
TARGET = Path("scripts/p3l_hydra_grade_artifact.py")
def proposal_digest(raw):
    if len(raw) > 32_000 or hashlib.sha256(raw).hexdigest() != "58c901bc183011e767932a1ce51248a4c2914752b0388ecb0c05e5a2e3c61698":
        raise ValueError("unexpected proposal archive digest")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        if len(members) != 1 or members[0].filename != "proposal.json" or members[0].file_size > 4096:
            raise ValueError("unexpected proposal archive member")
        data = archive.read(members[0])
    expected = json.loads("{\"head\":\"cdff438ec57007f52561482bfaa8f67461cfb877\",\"id\":\"hydra-problem-e3f13bc5981de2c2061c\",\"job_id\":135814065376,\"model_calls\":0,\"run_id\":44595933355,\"state\":\"proposed\",\"target\":\"scripts/p3l_hydra_grade_artifact.py\",\"task\":\"Select the unique independent grade archive by name, run and digest before constructing a model receipt.\",\"url\":\"https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44595933355/job/135814065376\"}")
    if json.dumps(json.loads(data), sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ValueError("proposal does not match the reviewed task")
    return hashlib.sha256(data).hexdigest()


def verify(checkout, raw):
    head = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    if head != BASE:
        raise ValueError("unexpected grading checkout HEAD")
    value = unwrap_proposal(raw).decode().strip()
    tree = ast.parse(value, mode="eval")
    contract = ast.parse("artifact['name'] == 'hydra-checkpoint-independent-grade'", mode="eval")
    if ast.dump(tree) != ast.dump(contract):
        raise ValueError("expected an exact independent-grade name comparison")
    candidate = """import re


def select_grade(artifacts, run):
    matches = [artifact for artifact in artifacts if MODEL_EXPRESSION]
    if len(matches) != 1:
        raise ValueError("expected one independent grade archive")
    grade = matches[0]
    if (type(grade["id"]) is not int or grade["id"] <= 0
            or grade["expired"] is not False
            or grade["workflow_run"]["id"] != run
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", grade["digest"])):
        raise ValueError("invalid grade archive provenance")
    return grade
""".replace("MODEL_EXPRESSION", value)
    checks = """
from p3l_hydra_grade_artifact import select_grade
grade = dict(name="hydra-checkpoint-independent-grade",id=14562348341,expired=False,
             workflow_run={"id":44591454500},digest="sha256:"+"a"*64)
model = {**grade,"name":"hydra-checkpoint-model","id":14564455082}
def blocked(items):
    try:
        select_grade(items,44591454500)
    except ValueError:
        return True
    return False
assert select_grade([model,grade],44591454500) == grade
assert select_grade([grade,model],44591454500) == grade
assert blocked([model])
assert blocked([grade,grade])
assert blocked([{**grade,"workflow_run":{"id":1}}])
assert blocked([{**grade,"digest":"sha256:short"}])
assert blocked([{**grade,"expired":True}])
print("GRADE ARCHIVE 7/7")
"""
    with tempfile.TemporaryDirectory(prefix="hydra-grade-artifact-") as folder:
        root = Path(folder)
        root.chmod(0o755)
        (root / TARGET.name).write_text(candidate)
        result = subprocess.run(_docker_command(root, "python:3.11-slim", ["-c", checks]),
                                text=True, capture_output=True, timeout=60)
        if result.returncode or "GRADE ARCHIVE 7/7" not in result.stdout:
            raise ValueError("candidate failed grade archive checks: " + result.stderr)
    return {"base_sha": BASE, "target": TARGET.as_posix(), "passed": 7,
            "proposal_sha256": hashlib.sha256(raw).hexdigest(),
            "candidate_sha256": hashlib.sha256(candidate.encode()).hexdigest()}
