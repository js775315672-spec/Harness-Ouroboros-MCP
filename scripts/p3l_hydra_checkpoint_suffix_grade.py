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

BASE = "5bb714c62347bdca91becdb5fbfc195a855fd76c"
TARGET = Path("hydra/memory/campaign.json")



def proposal_digest(raw):
    if len(raw) > 32_000 or hashlib.sha256(raw).hexdigest() != "593a488e067befda55b99bba05fc2c0553a6338ea288c01690f5aa0913c1e498":
        raise ValueError("unexpected proposal archive digest")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        if len(members) != 1 or members[0].filename != "proposal.json" or members[0].file_size > 4096:
            raise ValueError("unexpected proposal archive member")
        data = archive.read(members[0])
    expected = json.loads("{\"head\":\"1c55c4df65778ab6919a887b4f32fb5ba76ef14c\",\"id\":\"hydra-problem-7c4945c52c0cc76132c2\",\"job_id\":135708808655,\"model_calls\":0,\"run_id\":44566289515,\"state\":\"proposed\",\"target\":\"hydra/memory/campaign.json\",\"task\":\"Advance the persisted campaign checkpoint beyond the last verified production receipt.\",\"url\":\"https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44566289515/job/135708808655\"}")
    if json.dumps(json.loads(data), sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ValueError("proposal does not match the reviewed task")
    return hashlib.sha256(data).hexdigest()


def verify(checkout, raw):
    head = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    if head != BASE:
        raise ValueError("unexpected grading checkout HEAD")
    value = unwrap_proposal(raw).decode().strip()
    tree = ast.parse(value, mode="eval")
    contract = ast.parse("verified[len(completed):]", mode="eval")
    if ast.dump(tree) != ast.dump(contract):
        raise ValueError("expected a slice of the verified suffix")
    checkpoint = json.loads((checkout / TARGET).read_bytes())
    first, = checkpoint["completed"]
    second = dict(sequence=2,run=44560093173,job=135686805027,
                  head="98a50941c19b847f1a00e7937e716f39ebf63b3d",
                  task="continuity-replay-44558947017",model_result_run=44558947017)
    third = dict(sequence=3,run=44565309602,job=135705473970,
                 head="7dcaf6660f3a81b9ff9a7a6e35789ca23bb6d17f",
                 task="continuity-replay-44562246674",model_result_run=44562246674)
    checks = '''
import json
from pathlib import Path
checkpoint = json.loads(Path("current.json").read_bytes())
verified = json.loads(Path("receipts.json").read_bytes())
def extend(completed, verified):
    if verified[:len(completed)] != completed:
        raise ValueError("verified history disagrees with the existing checkpoint")
    return completed + MODEL_EXPRESSION
original = checkpoint["completed"]
candidate = extend(original, verified)
assert len(original) == 1 and len(candidate) == 3
assert candidate[:len(original)] == original
assert candidate == verified
assert extend(candidate, verified) == candidate
try:
    extend(original, verified[::-1])
except ValueError:
    pass
else:
    raise ValueError("reordered history was accepted")
checkpoint["completed"] = candidate
for row in candidate:
    assert row["sequence"] == candidate.index(row) + 1
print(json.dumps(checkpoint, indent=2))
'''.replace("MODEL_EXPRESSION", value)
    with tempfile.TemporaryDirectory(prefix="hydra-checkpoint-suffix-") as folder:
        root = Path(folder)
        root.chmod(0o755)
        (root / "current.json").write_text(json.dumps(checkpoint))
        (root / "receipts.json").write_text(json.dumps([first,second,third]))
        result = subprocess.run(_docker_command(root, "python:3.11-slim", ["-B", "-c", checks]),
                                text=True, capture_output=True, timeout=60)
        if result.returncode:
            raise ValueError("candidate failed checkpoint checks: " + result.stderr)
    candidate = json.dumps(json.loads(result.stdout),indent=2) + "\n"
    return {"base_sha": BASE, "target": TARGET.as_posix(), "passed": 6,
            "proposal_sha256": hashlib.sha256(raw).hexdigest(),
            "candidate_sha256": hashlib.sha256(candidate.encode()).hexdigest()}
