"""Spend one synthetic budget across Actions runs using a create-only Git ref."""
import argparse
import hashlib
import json
import os
from pathlib import Path

from p3l_w04_attempt_registry import SHA40
from p3l_w04_github_claim import REPOSITORY, create_once, github

REHEARSAL_BASE = "0740c52707e5d2bbb750e8281d0a1e40457d9084"
REHEARSAL_BRANCH = "work/p3l-w04-ref-cas-rehearsal"
REF_PREFIX = "refs/heads/rehearsal/w04-cas/"


def claim(base, head, request):
    if base != REHEARSAL_BASE or type(head) is not str or SHA40.fullmatch(head) is None or head == base:
        raise ValueError("unexpected review revisions")
    slot = hashlib.sha256(f"w04-ref-cas-rehearsal:{base}".encode()).hexdigest()
    ref = REF_PREFIX + slot
    created, status, winner = create_once(ref, head, request)
    outcome = "START_RECORDED" if created else "DUPLICATE_BLOCKED"
    return {"outcome": outcome, "create_http_status": status, "ref": ref, "slot_sha256": slot,
            "requested_head": head, "recorded_head": winner}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if (os.environ.get("GITHUB_REPOSITORY") != REPOSITORY
            or os.environ.get("GITHUB_EVENT_NAME") != "pull_request"
            or os.environ.get("GITHUB_RUN_ATTEMPT") != "1"
            or os.environ.get("GITHUB_HEAD_REF") != REHEARSAL_BRANCH):
        raise ValueError("unexpected rehearsal context")
    token = os.environ["GH_TOKEN"]
    result = claim(os.environ["REVIEW_BASE"], os.environ["REVIEW_HEAD"],
                   lambda *args: github(token, *args))
    result.update(run_id=int(os.environ["GITHUB_RUN_ID"]), runner=os.environ["RUNNER_NAME"],
                  workflow_sha=os.environ["GITHUB_SHA"], model_calls=0)
    receipt = json.dumps(result, sort_keys=True) + "\n"
    args.receipt.write_text(receipt, encoding="utf-8")
    print(receipt, end="")


if __name__ == "__main__":
    main()
