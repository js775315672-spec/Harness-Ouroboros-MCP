#!/usr/bin/env python3
"""Rehearse the first W07 handoff with an isolated W05 evidence revision."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASELINE_COMMIT = "f2c8c5d37c7f4fe79a658cc25a6b0ec126972578"
CANDIDATE_COMMIT = "3cbbf0adb1bc3e958e0a7430fbcfea3fa710e267"
RUN_ID = 44288613606
TARGET = "scripts/development_ledger.py"
MODEL_ARCHIVE = ("14420098154", "f56f5f2f0ae4175207a0e093f5abb732dc244e2a42e233af5bebb638b4482813")
REPLAY_ARCHIVE = ("14420732180", "b9cbc40a613b549253a6af422101ee341aa7428e4935fae4cfedb2f9b89b49d3")
VERIFIED_ARCHIVE = ("14420024839", "c1ac7426a92f4a6a99313adc1fe91a986210909806de1a7c714584a13b4f1799")


def git(root, *args):
    return subprocess.check_output(
        ["git", *args], cwd=root, timeout=20,
        env={**os.environ, "GIT_NO_REPLACE_OBJECTS": "1"},
    )


def read_artifact(evidence, identity, *members):
    artifact_id, expected = identity
    with (evidence / artifact_id / "artifact.zip").open("rb") as stream:
        data = stream.read(40_001)
    if len(data) > 40_000 or hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"W05 artifact {artifact_id} differs from the reviewed archive")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return tuple(json.loads(archive.read(name)) for name in members)


# A fresh interpreter resolves W01–W06 imports from the pinned archive.
# On Windows only, the Linux resource import is supplied for static replay.
# Any resource operation would still fail, and no Docker or model is invoked.
RECONSTRUCT = """
import json
from pathlib import Path
import sys
import types

if sys.platform == "win32":
    sys.modules["resource"] = types.ModuleType("resource")
sys.path.insert(0, str(Path.cwd() / "scripts"))

import p3l_w05_replay_evidence as w05

model, verdict, provenance, verified = json.load(sys.stdin)
run_id = verified["github_provenance"]["run_id"]
w05.require_verified_replay(verdict, provenance, model, verified["github_provenance"], run_id)
plan, source = w05.reconstruct(Path.cwd(), model, run_id)
print(json.dumps({"plan": plan, "source": source}))
"""


def rehearse(candidate, evidence):
    candidate = candidate.resolve(strict=True)
    if (git(candidate, "rev-parse", "HEAD").decode().strip() != CANDIDATE_COMMIT
            or git(candidate, "rev-parse", "HEAD^").decode().strip() != BASELINE_COMMIT
            or git(candidate, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").decode().splitlines() != [TARGET]
            or git(candidate, "status", "--porcelain", "--untracked-files=no")):
        raise ValueError("candidate checkout differs from the reviewed W07 revision")

    model, = read_artifact(evidence, MODEL_ARCHIVE, "model-output.json")
    verdict, provenance = read_artifact(evidence, REPLAY_ARCHIVE, "verdict.json", "provenance.json")
    verified, = read_artifact(evidence, VERIFIED_ARCHIVE, "verified.json")
    origin = verified["github_provenance"]
    if (origin["head_sha"] != BASELINE_COMMIT or origin["run_id"] != RUN_ID
            or origin["model_artifact_id"] != int(MODEL_ARCHIVE[0])
            or origin["model_archive_sha256"] != MODEL_ARCHIVE[1]
            or verified["replay_artifact_id"] != int(REPLAY_ARCHIVE[0])
            or verified["replay_archive_sha256"] != REPLAY_ARCHIVE[1]
            or any(verified.get(key) != value for key, value in verdict.items())):
        raise ValueError("W05 strict gate evidence does not identify this baseline and replay")

    baseline = git(ROOT, "archive", "--format=zip", BASELINE_COMMIT, "scripts", "docs/p3l")
    with tempfile.TemporaryDirectory(prefix="p3l-w07-baseline-") as directory:
        with zipfile.ZipFile(io.BytesIO(baseline)) as archive:
            archive.extractall(directory)
        replay = subprocess.run(
            [sys.executable, "-E", "-B", "-c", RECONSTRUCT], cwd=directory,
            input=json.dumps([model, verdict, provenance, verified]).encode(),
            capture_output=True, timeout=30, check=True,
        )
    reconstructed = json.loads(replay.stdout)
    source = reconstructed["source"].encode()
    if (source != git(candidate, "show", f"HEAD:{TARGET}")
            or source != (candidate / TARGET).read_bytes()
            or hashlib.sha256(source).hexdigest() != verdict["candidate_source_sha256"]):
        raise ValueError("candidate source does not match the independently verified patch")
    return {
        "schema": "p3l-w07-revision-isolation-v1",
        "status": "REVIEW_PENDING",
        "historical_commit": BASELINE_COMMIT,
        "historical_source_sha256": reconstructed["plan"]["source_sha256"],
        "historical_task_sha256": reconstructed["plan"]["task_sha256"],
        "historical_reconstruction_verified": True,
        "proposed_runtime_commit": CANDIDATE_COMMIT,
        "proposed_runtime_source_sha256": verdict["candidate_source_sha256"],
        "rollback_target_commit": BASELINE_COMMIT,
        "w05_run_id": RUN_ID,
        "historical_docker_test_count": verdict["test_count"],
        "model_calls": 0,
        "candidate_active": False,
        "merge_authorized": False,
        "w08_handoff_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-checkout", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = rehearse(args.candidate_checkout, args.evidence_root)
        args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except subprocess.CalledProcessError as error:
        detail = error.stderr.decode("utf-8", errors="replace").strip() if error.stderr else str(error)
        parser.exit(2, f"BLOCK: {detail}\n")
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired, zipfile.BadZipFile) as error:
        parser.exit(2, f"BLOCK: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
