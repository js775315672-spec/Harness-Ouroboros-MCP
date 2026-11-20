"""Compare an ORIL candidate against a public historical proof."""
import copy
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "scripts"))
import p3l_hydra_standing as standing

fixtures = Path("/fixtures")
run_id = 44613839140
job_id = 135877882125
artifact_id = 14572374289
root = f"repos/{standing.REPO}/actions"
run_path = f"{root}/runs/{run_id}"
artifact_path = f"{root}/artifacts/{artifact_id}"
responses = {
    run_path: json.loads((fixtures / "run.json").read_bytes()),
    f"{root}/jobs/{job_id}": json.loads((fixtures / "job.json").read_bytes()),
    artifact_path: json.loads((fixtures / "artifact.json").read_bytes()),
}
archive = (fixtures / "grade.zip").read_bytes()
assert hashlib.sha256(archive).hexdigest() == (
    "4889df2128fdb2ed8ff6ba811f60074f3c7b7a08cabb6e69563cac74aaacada4"
)
approval, = [
    row for row in json.loads(Path("hydra/approvals.json").read_bytes())["approvals"]
    if row["model_result_run"] == run_id
]


def prove(change=None, evidence=archive):
    metadata = copy.deepcopy(responses)
    reads = []
    archives = []
    if change:
        path, key, value = change
        metadata[path][key] = value

    def fetch(path):
        reads.append(path)
        return metadata[path]

    def download(command, *, timeout):
        assert command == ["gh", "api", artifact_path + "/zip"] and timeout == 30
        archives.append(command)
        return evidence

    standing.fetch = fetch
    standing.subprocess.check_output = download
    proof = standing.model_result_proof(approval)
    return proof, len(reads), len(archives)


proof, metadata_reads, archive_reads = prove()
assert proof[0]["passed"] is True
assert metadata_reads == int(sys.argv[1]) and archive_reads == 1
for change, evidence in (
    ((run_path, "status", "in_progress"), archive),
    ((run_path, "head_sha", "0" * 40), archive),
    ((f"{root}/jobs/{job_id}", "steps", []), archive),
    ((artifact_path, "expired", True), archive),
    (None, archive + b"x"),
):
    try:
        prove(change, evidence)
    except ValueError:
        continue
    raise AssertionError("The proof accepted altered evidence")

print(json.dumps({
    "proof_checks": 6,
    "metadata_reads": metadata_reads,
    "archive_reads": archive_reads,
    "proof_sha256": proof[0]["sha256"],
}, sort_keys=True))
