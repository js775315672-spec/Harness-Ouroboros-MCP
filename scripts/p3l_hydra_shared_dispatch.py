"""Spend a single synthetic Hydra execution slot across workflow runs."""
import hashlib
from http.client import HTTPSConnection
import json
import os
from pathlib import Path
import subprocess

from p3l_hydra_fast_lane_gate import SHA40
from p3l_hydra_github_completion import verify_completion

REPO = "js775315672-spec/Harness-Ouroboros-MCP"
SOURCE = {"task": "w01_contract", "head": "06ee12b142669f2f03f2c70280ae5d6559adc73c",
          "run_id": 44480103747, "job_id": 135409999784}
TASK = "hydra_followup_probe"


def request(method, path, body=None):
    connection = HTTPSConnection("api.github.com", timeout=12)
    try:
        connection.request(method, f"/repos/{REPO}/git/{path}", body=body,
                           headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"],
                                    "Accept": "application/vnd.github+json",
                                    "Content-Type": "application/json", "User-Agent": "hydra-rehearsal"})
        response = connection.getresponse()
        data = response.read(32001)
        if len(data) > 32000:
            raise ValueError("oversized GitHub artifact response")
        return response.status, data
    finally:
        connection.close()


def record_head(raw, ref):
    data = json.loads(raw)
    target = data.get("object", {})
    head = target.get("sha")
    if data.get("ref") != ref or target.get("type") != "commit" or not isinstance(head, str) or not SHA40.fullmatch(head):
        raise ValueError("GitHub did not return the exact execution record")
    return head


def main():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, timeout=10).strip()
    if head != os.environ["REVIEW_HEAD"]:
        raise ValueError("wrong reviewed checkout")
    def fetch(path):
        return json.loads(subprocess.check_output(["gh", "api", path], timeout=15))
    origin = verify_completion(SOURCE, repository=REPO,
                               workflow=".github/workflows/hydra-isolated-dispatch.yml",
                               job_name="source", required_step="Run exact Hydra core suite", fetch=fetch)
    key = hashlib.sha256((origin["sha256"] + ":" + TASK).encode()).hexdigest()
    ref = "refs/heads/rehearsal/hydra-cross-run/" + key
    status, data = request("POST", "refs", json.dumps({"ref": ref, "sha": head}).encode())
    if status == 201:
        recorded = record_head(data, ref)
        if recorded != head:
            raise ValueError("created execution record points to a different checkout")
        admitted = True
    elif status in (409, 422):
        confirmed, data = request("GET", "ref/" + ref.removeprefix("refs/"))
        if confirmed != 200:
            raise ValueError("creation conflict lacks a durable execution record")
        recorded = record_head(data, ref)
        admitted = False
    else:
        raise ValueError(f"execution record HTTP {status}")
    output = {"source_proof_sha256": origin["sha256"], "task": TASK, "ref": ref,
              "recorded_head": recorded, "head": head, "admitted": admitted,
              "http_status": status, "model_calls": 0}
    print(json.dumps(output, sort_keys=True))
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as stream:
        stream.write(f"admitted={str(admitted).lower()}\n")


if __name__ == "__main__":
    main()
