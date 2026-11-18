"""Spend one synthetic budget across Actions runs using a create-only Git ref."""
import argparse
import hashlib
from http.client import HTTPSConnection
import json
import os
from pathlib import Path

from p3l_w04_attempt_registry import SHA40

REPOSITORY = "js775315672-spec/Harness-Ouroboros-MCP"
REHEARSAL_BASE = "0740c52707e5d2bbb750e8281d0a1e40457d9084"
REHEARSAL_BRANCH = "work/p3l-w04-ref-cas-rehearsal"
API_PATH = f"/repos/{REPOSITORY}/git"
REF_PREFIX = "refs/heads/rehearsal/w04-cas/"
MAX_RESPONSE = 32 * 1024


def github(token, method, route, payload=None):
    headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}",
               "Content-Type": "application/json", "User-Agent": "harness-w04-rehearsal"}
    connection = HTTPSConnection("api.github.com", timeout=12)
    try:
        connection.request(method, API_PATH + route, body=payload, headers=headers)
        response = connection.getresponse()
        data = response.read(MAX_RESPONSE + 1)
        if len(data) > MAX_RESPONSE:
            raise ValueError("oversized GitHub reference response")
        return response.status, data
    finally:
        connection.close()


def verified_ref(body, expected_ref):
    payload = json.loads(body)
    target = payload.get("object") if type(payload) is dict else None
    if (type(target) is not dict or payload.get("ref") != expected_ref
            or target.get("type") != "commit" or type(target.get("sha")) is not str
            or SHA40.fullmatch(target["sha"]) is None):
        raise ValueError("GitHub response did not identify the exact rehearsal ref")
    return target["sha"]


def claim(base, head, request):
    if base != REHEARSAL_BASE or type(head) is not str or SHA40.fullmatch(head) is None or head == base:
        raise ValueError("unexpected review revisions")
    slot = hashlib.sha256(f"w04-ref-cas-rehearsal:{base}".encode()).hexdigest()
    ref = REF_PREFIX + slot
    status, body = request("POST", "/refs", json.dumps({"ref": ref, "sha": head}).encode())
    if status == 201:
        winner = verified_ref(body, ref)
        if winner != head:
            raise ValueError("created ref differs from requested HEAD")
        outcome = "START_RECORDED"
    elif status in (409, 422):
        confirmed, body = request("GET", "/ref/" + ref.removeprefix("refs/"))
        if confirmed != 200:
            raise ValueError("ref conflict has no confirmed durable record")
        winner = verified_ref(body, ref)
        outcome = "DUPLICATE_BLOCKED"
    else:
        raise ValueError(f"ref creation failed with HTTP {status}")
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
