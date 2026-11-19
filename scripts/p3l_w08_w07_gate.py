"""Verify pinned W07 evidence and the public W08 request without model execution."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

from p3l_w07_revision_isolation import BASELINE_COMMIT, CANDIDATE_COMMIT, git
from p3l_w08_evidence_handoff import PROMPT_SHA256, read_bounded
from p3l_w08_verify_test import TARGET

W07_RUN = 44437891417
W07_WORKFLOW_SHA = "50172e4e297599bc9f7a5d971167e11f862adac4"
SOURCE_SHA = "b7ef9c2c369469942f31aa1b96b8c8256c488c549db7635a162d8da177c9008e"
CI_ZIP = "82f528a83a6b94ed004600ad9d1f2434b81de07fdff250574a77033c2e361a66"
ROLLBACK_ZIP = "29f58159830054852d26520353b00e8973a5ea80407318411fff3e14bf89f5cd"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_member(archive_path, expected_sha, name):
    raw = read_bounded(archive_path, 40_000)
    if digest(raw) != expected_sha:
        raise ValueError("W07 evidence ZIP digest mismatch")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        items = [info for info in archive.infolist() if Path(info.filename).name == name]
        if len(items) != 1 or not 1 <= items[0].file_size <= 100_000:
            raise ValueError("missing or oversized W07 evidence member")
        return json.loads(archive.read(items[0]))


def check(checkout, prompt, ci, rollback):
    if (git(checkout, "rev-parse", "HEAD").decode().strip() != CANDIDATE_COMMIT
            or git(checkout, "status", "--porcelain", "--untracked-files=no")):
        raise ValueError("W08 requires the clean, exact W07 checkout")
    if digest(read_bounded(prompt, 6000)) != PROMPT_SHA256:
        raise ValueError("W08 public prompt digest mismatch")
    identity = {"baseline": BASELINE_COMMIT, "candidate": CANDIDATE_COMMIT,
                "candidate_source_sha256": SOURCE_SHA}
    for path, expected in ((ci, CI_ZIP), (rollback, ROLLBACK_ZIP)):
        manifest = read_member(path, expected, "w07-candidate.json")
        if any(manifest.get(k) != v for k, v in identity.items()):
            raise ValueError("W07 candidate identity mismatch")
    timing = read_member(ci, CI_ZIP, "verification-timing.json")
    origin = timing["provenance"]
    if (timing["outcome"] != "pass" or timing["completed_rounds"] != 30
            or origin["run_id"] != str(W07_RUN) or origin["workflow_sha"] != W07_WORKFLOW_SHA):
        raise ValueError("W07 candidate CI evidence is incomplete")
    recovery = read_member(rollback, ROLLBACK_ZIP, "w07-rollback.json")
    expected_history = [
        ("initial", BASELINE_COMMIT), ("candidate", CANDIDATE_COMMIT),
        ("stale_rollback_blocked", CANDIDATE_COMMIT), ("restored", BASELINE_COMMIT),
        ("reapplied", CANDIDATE_COMMIT), ("repeat_same_candidate", CANDIDATE_COMMIT),
    ]
    if (recovery["simulation_only"] is not True
            or [(x["step"], x["active_commit"]) for x in recovery["history"]] != expected_history):
        raise ValueError("W07 rollback evidence is incomplete")
    return {"candidate_sha": CANDIDATE_COMMIT, "w07_run": W07_RUN,
            "prompt_sha256": PROMPT_SHA256, "target": TARGET.as_posix(),
            "w07_evidence_verified": True, "model_calls": 0,
            "operator_release_verified": False}


def main():
    parser = argparse.ArgumentParser()
    for item in ("checkout", "prompt", "ci", "rollback"):
        parser.add_argument("--" + item, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.checkout, args.prompt, args.ci, args.rollback), sort_keys=True))


if __name__ == "__main__":
    main()
