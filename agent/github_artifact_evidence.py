"""Read-only GitHub Actions evidence fetcher. No model calls or OPS writes.

Only trust GitHub API responses fetched with a separately supplied read token.
ZIP digest is calculated over downloaded archive bytes, not receipt text.
"""
import hashlib
import json
import re
import urllib.request

API = "https://api.github.com"
SHA40 = re.compile(r"^[0-9a-f]{40}$")

def github_json(url, token, opener=urllib.request.urlopen):
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "ofc-evidence-readonly"})
    with opener(req, timeout=30) as response:
        return json.load(response)

def verify_actions_artifact(repo, run_id, artifact_id, expected_head_sha,
                            token, *, opener=urllib.request.urlopen):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo or ""):
        raise RuntimeError("invalid repository")
    if not isinstance(run_id, int) or run_id <= 0 or not isinstance(artifact_id, int) or artifact_id <= 0:
        raise RuntimeError("invalid GitHub IDs")
    if not SHA40.fullmatch(expected_head_sha or "") or not token:
        raise RuntimeError("missing trusted head or token")
    root = f"{API}/repos/{repo}/actions"
    run = github_json(f"{root}/runs/{run_id}", token, opener)
    if (run.get("repository", {}).get("full_name") != repo or
        run.get("head_sha") != expected_head_sha or
        run.get("status") != "completed" or run.get("conclusion") != "success"):
        raise RuntimeError("run not independently verified")
    artifact = github_json(f"{root}/artifacts/{artifact_id}", token, opener)
    if (artifact.get("workflow_run", {}).get("id") != run_id or
        artifact.get("expired") is not False or artifact.get("size_in_bytes", 0) <= 0):
        raise RuntimeError("artifact not bound to successful run")
    req = urllib.request.Request(f"{root}/artifacts/{artifact_id}/zip", headers={
        "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
        "User-Agent": "ofc-evidence-readonly"})
    with opener(req, timeout=30) as response:
        data = response.read(50_000_001)
    if len(data) > 50_000_000 or not data.startswith(b"PK"):
        raise RuntimeError("invalid or oversized artifact ZIP")
    return {"repository": repo, "run_id": run_id, "artifact_id": artifact_id,
            "head_sha": expected_head_sha, "zip_sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data), "run_conclusion": "success"}
