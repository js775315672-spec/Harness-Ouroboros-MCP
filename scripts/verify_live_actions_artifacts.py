"""Verify real GitHub Actions artifacts by downloading the exact ZIP bytes.

Invoked in an isolated, read-only Actions job after matrix artifacts upload.
"""
import json
import os
import sys
import urllib.request
from agent.actions_evidence import verify_actions
from agent.artifact_integrity import verify_zip, download_zip

repo = os.environ["GITHUB_REPOSITORY"]
run_id = int(os.environ["GITHUB_RUN_ID"])
sha = os.environ["PINNED_HEAD_SHA"]
token = os.environ["GITHUB_TOKEN"]
prefix = "ofc-v31-p0-"

def get(path):
    req = urllib.request.Request("https://api.github.com" + path, method="GET",
        headers={"Accept":"application/vnd.github+json",
                 "Authorization":"Bearer " + token})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)

# This verifier job is still running, so the overall workflow is not completed.
# Validate identity and the completed producer jobs, not overall run success.
base = f"/repos/{repo}/actions/runs/{run_id}"
run = get(base)
if run.get("id") != run_id or run.get("head_sha") != sha or run.get("repository", {}).get("full_name") != repo:
    raise SystemExit("BLOCKED: run identity mismatch")
jobs = get(base + "/jobs?per_page=100")
if jobs.get("total_count") != len(jobs.get("jobs", [])):
    raise SystemExit("BLOCKED: incomplete job listing")
producers = [j for j in jobs["jobs"] if j.get("name", "").startswith("isolated-regression (")]
if len(producers) != 2 or any(j.get("conclusion") != "success" for j in producers):
    raise SystemExit("BLOCKED: incomplete Windows/Linux matrix")
artifacts = get(base + "/artifacts?per_page=100")
if artifacts.get("total_count") != len(artifacts.get("artifacts", [])):
    raise SystemExit("BLOCKED: incomplete artifact listing")
items = [a for a in artifacts["artifacts"] if a.get("name", "").startswith(prefix)]
if len(items) != 2 or len({a["name"] for a in items}) != 2:
    raise SystemExit("BLOCKED: expected two OS artifacts")
for item in items:
    digest = verify_zip(item, repo=repo, run_id=run_id, head_sha=sha,
                        fetch=lambda url: download_zip(url, token=token))
    print(json.dumps({"run_id":run_id, "head_sha":sha,
                      "artifact_id":item["id"], "name":item["name"],
                      "digest":digest, "bytes_verified":True}, sort_keys=True))
