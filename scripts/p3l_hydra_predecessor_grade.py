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

BASE = "ebe5ec07c88de264fe267f48ea20905941f9c588"
TARGET = Path("scripts/p3l_hydra_campaign_continuity.py")
CASES = """
import base64,json
from p3l_hydra_campaign_continuity import next_sequence,REPO
head="a"*40
row=dict(sequence=1,run=10,job=20,head=head,task="memory-replay-30",model_result_run=30)
approval=dict(id=row["task"],model_result_run=30)
def read(path, approvals, encoding="base64"):
    if "/contents/" in path:
        assert path.endswith("?ref="+head)
        raw=json.dumps({"enabled":True,"approvals":approvals}).encode()
        return dict(type="file",encoding=encoding,content=base64.b64encode(raw).decode())
    repo=dict(full_name=REPO)
    if path.endswith("/runs/10"):
        return dict(id=10,repository=repo,workflow_id=423685918,head_branch="main",head_sha=head,run_attempt=1,status="completed",conclusion="success",event="push")
    if path.endswith("/jobs/20"):
        return dict(id=20,run_id=10,head_sha=head,status="completed",name="Worker "+row["task"],conclusion="success")
    if "/runs/" in path:
        return dict(id=int(path.rsplit("/",1)[-1]),repository=repo,status="completed",conclusion="success")
    raise ValueError(path)
def call(approvals, model=30, encoding="base64"):
    cp=dict(schema="hydra-nine-cycle-checkpoint-v1",campaign="hydra-nine-cycle",requested=9,completed=[{**row,"model_result_run":model}])
    return next_sequence(cp,lambda path:read(path,approvals,encoding))
def blocked(approvals, model=30, encoding="base64"):
    try:
        call(approvals,model,encoding)
    except ValueError:
        return True
    return False
assert blocked([approval],40), "misattributed-model-regression"
assert call([approval])["next_sequence"]==2
assert blocked([])
assert blocked([approval,approval])
assert blocked([approval],encoding="utf-8")
print("PREDECESSOR BINDING 5/5")
"""


def proposal_digest(raw):
    if len(raw) > 32_000 or hashlib.sha256(raw).hexdigest() != "4a17031ae1408641eed3cfb128282d405f205f39b7f2d1e94dfd0449b9e29882":
        raise ValueError("unexpected proposal archive digest")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        if len(members) != 1 or members[0].filename != "proposal.json" or members[0].file_size > 4096:
            raise ValueError("unexpected proposal archive member")
        data = archive.read(members[0])
    expected = json.loads("{\"head\":\"673fa564088832ed3845450911d32f40559c4a4c\",\"id\":\"hydra-problem-6eab797e33c1786ff096\",\"job_id\":135676293625,\"model_calls\":0,\"run_id\":44557180546,\"state\":\"proposed\",\"target\":\"scripts/p3l_hydra_campaign_continuity.py\",\"task\":\"Require a campaign predecessor model run to match the accepted production receipt.\",\"url\":\"https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44557180546/job/135676293625\"}")
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
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Expression, ast.Compare, ast.NotEq, ast.Subscript, ast.Name, ast.Load, ast.Constant)):
            raise ValueError("unsupported evidence expression")
        if isinstance(node, ast.Name) and node.id not in {"row", "entry"}:
            raise ValueError("unexpected evidence variable")
        if isinstance(node, ast.Constant) and node.value != "model_result_run":
            raise ValueError("unexpected evidence field")
    original = (checkout / TARGET).read_text(encoding="utf-8")
    anchor = '        model = read(f"{root}/runs/{row[\'model_result_run\']}")\n'
    if original.count(anchor) != 1:
        raise ValueError("unexpected predecessor anchor")
    candidate = original.replace("import hashlib\n", "import base64\nimport hashlib\n")
    candidate = candidate.replace(anchor,
        '        manifest_file = read(f"repos/{REPO}/contents/hydra/approvals.json?ref={row[\'head\']}")\n'
        '        if manifest_file.get("type") != "file" or manifest_file.get("encoding") != "base64":\n'
        '            raise ValueError("unsupported approval manifest evidence")\n'
        '        manifest = json.loads(base64.b64decode(manifest_file["content"]))\n'
        '        entries = [item for item in manifest["approvals"] if item["id"] == row["task"]]\n'
        '        if len(entries) != 1:\n'
        '            raise ValueError("campaign predecessor requires one exact approval")\n'
        '        entry = entries[0]\n'
        f'        if {value}:\n'
        '            raise ValueError("model run does not match approved predecessor")\n'
        + anchor)
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
        if baseline.returncode != 1 or "AssertionError: misattributed-model-regression" not in baseline.stderr:
            raise ValueError("baseline did not reproduce misattribution: " + baseline.stderr)
        result = run(candidate)
        if result.returncode != 0 or "PREDECESSOR BINDING 5/5" not in result.stdout:
            raise ValueError("candidate failed predecessor regression: " + result.stderr)
    return {"base_sha": BASE, "target": TARGET.as_posix(), "passed": 5,
            "proposal_sha256": hashlib.sha256(raw).hexdigest(),
            "candidate_sha256": hashlib.sha256(candidate.encode()).hexdigest()}
