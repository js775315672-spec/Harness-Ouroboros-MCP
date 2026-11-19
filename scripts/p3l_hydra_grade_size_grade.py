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

BASE = "768132073f9b4f28567277f5eb224c7b3604d55b"
TARGET = Path("scripts/p3l_hydra_grade_artifact.py")
def proposal_digest(raw):
    if len(raw) > 32_000 or hashlib.sha256(raw).hexdigest() != "9bc53099aa23b953d059a172bfc9a5ce8dad192197eb1adc78220f0434e5b24e":
        raise ValueError("unexpected proposal archive digest")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        if len(members) != 1 or members[0].filename != "proposal.json" or members[0].file_size > 4096:
            raise ValueError("unexpected proposal archive member")
        data = archive.read(members[0])
    expected = json.loads("{\"head\":\"75a95922ca4ce166dce58186ff95225a008c984d\",\"id\":\"hydra-problem-239c58f463606d23ef4e\",\"job_id\":135832397130,\"model_calls\":0,\"run_id\":44601097330,\"state\":\"proposed\",\"target\":\"scripts/p3l_hydra_grade_artifact.py\",\"task\":\"Reject missing, zero, or oversized independent grade archive sizes before receipt preparation.\",\"url\":\"https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44601097330/job/135832397130\"}")
    if json.dumps(json.loads(data), sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ValueError("proposal does not match the reviewed task")
    return hashlib.sha256(data).hexdigest()


def verify(checkout, raw):
    head = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    if head != BASE:
        raise ValueError("unexpected grading checkout HEAD")
    value = unwrap_proposal(raw).decode().strip()
    tree = ast.parse(value, mode="eval")
    contract = ast.parse("not 0 < size <= 256000", mode="eval")
    if ast.dump(tree) != ast.dump(contract):
        raise ValueError("expected an inclusive size-bound rejection condition")
    original = (checkout / TARGET).read_text(encoding="utf-8")
    anchor = "    return grade\n"
    if original.count(anchor) != 1:
        raise ValueError("unexpected grade selector anchor")
    candidate = original.replace(anchor,
        '    size = grade.get("size_in_bytes")\n'
        f'    if type(size) is not int or {value}:\n'
        '        raise ValueError("invalid grade archive size")\n' + anchor)
    checks = """
from p3l_hydra_grade_artifact import select_grade
grade = dict(name="hydra-checkpoint-independent-grade",id=14562348341,expired=False,
             workflow_run={"id":44591454500},size_in_bytes=1,digest="sha256:"+"a"*64)
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
assert select_grade([{**grade,"size_in_bytes":256000}],44591454500)["size_in_bytes"] == 256000
assert blocked([{**grade,"size_in_bytes":256001}])
assert blocked([{**grade,"size_in_bytes":0}])
assert blocked([{**grade,"size_in_bytes":True}])
assert blocked([{k:v for k,v in grade.items() if k!="size_in_bytes"}])
print("GRADE ARCHIVE 12/12")
"""
    with tempfile.TemporaryDirectory(prefix="hydra-grade-artifact-") as folder:
        root = Path(folder)
        root.chmod(0o755)
        (root / TARGET.name).write_text(candidate)
        result = subprocess.run(_docker_command(root, "python:3.11-slim", ["-c", checks]),
                                text=True, capture_output=True, timeout=60)
        if result.returncode or "GRADE ARCHIVE 12/12" not in result.stdout:
            raise ValueError("candidate failed grade archive checks: " + result.stderr)
    return {"base_sha": BASE, "target": TARGET.as_posix(), "passed": 12,
            "proposal_sha256": hashlib.sha256(raw).hexdigest(),
            "candidate_sha256": hashlib.sha256(candidate.encode()).hexdigest()}
