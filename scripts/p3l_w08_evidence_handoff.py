"""Bind a W08 rehearsal proposal to its producing Actions run and verify it."""
import argparse
import hashlib
import json
import os
from pathlib import Path

from p3l_w08_verify_test import CANDIDATE_COMMIT, TARGET, verify

PROMPT_SHA256 = "087f309b155a815e53c6f8ffd99a0d793ca50eceded93edf31347b0810d65a7f"
PROPOSAL_LIMIT = 6000


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_bounded(path, limit):
    if path.is_symlink() or not path.is_file():
        raise ValueError("unsafe W08 evidence path")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if not 1 <= len(data) <= limit:
        raise ValueError("invalid W08 evidence size")
    return data


def rehearsal_receipt(proposal, run_id, workflow_sha):
    return {
        "schema": "p3l-w08-rehearsal-v1",
        "base_sha": CANDIDATE_COMMIT,
        "run_id": run_id,
        "workflow_sha": workflow_sha,
        "target": TARGET.as_posix(),
        "prompt_sha256": PROMPT_SHA256,
        "proposal_sha256": sha(proposal),
        "model_calls": 0,
        "producer": "coordinator_fixture",
    }


def validate_receipt(raw, proposal, expected_sha, run_id, workflow_sha):
    if sha(raw) != expected_sha:
        raise ValueError("W08 receipt differs from producer job output")
    expected = rehearsal_receipt(proposal, run_id, workflow_sha)
    if raw != encode(expected):
        raise ValueError("W08 evidence identity or proposal mismatch")
    return expected


def encode(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("publish", "verify"))
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--checkout", type=Path)
    args = parser.parse_args()
    run_id = int(os.environ["GITHUB_RUN_ID"])
    workflow_sha = os.environ["GITHUB_SHA"]
    proposal = read_bounded(args.proposal, PROPOSAL_LIMIT)
    if args.stage == "publish":
        raw = encode(rehearsal_receipt(proposal, run_id, workflow_sha))
        with args.receipt.open("xb") as stream:
            stream.write(raw)
        print("receipt_sha256=" + sha(raw))
        return
    if args.checkout is None:
        parser.error("--checkout required for independent verification")
    raw = read_bounded(args.receipt, 2000)
    receipt = validate_receipt(raw, proposal, os.environ["EXPECTED_RECEIPT_SHA"], run_id, workflow_sha)
    result = verify(args.checkout, proposal)
    print(json.dumps({"receipt": receipt, "grade": result}, sort_keys=True))


if __name__ == "__main__":
    main()
