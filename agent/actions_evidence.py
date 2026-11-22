"""Read-only GitHub Actions evidence adapter. No mutations, no secrets, no OPS writes.

The REST transport is injected for deterministic offline CI tests. Artifact metadata
is validated, but its digest is NOT independently verified until archive bytes are
downloaded and hashed by a separately authorized verifier.
"""
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable
from agent import cycle_registry as registry

SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class Evidence:
    run_id: int
    head_sha: str
    job_ids: tuple[int, ...]
    artifact_ids: tuple[int, ...]
    artifact_digests: tuple[str, ...]
    artifact_bytes_verified: bool = False


def github_get(path: str, token: str = "") -> dict:
    """Only GET from api.github.com; caller supplies token, never logs it."""
    request = urllib.request.Request(
        "https://api.github.com" + path,
        headers={"Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 **({"Authorization": "Bearer " + token} if token else {})},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response)
    except (OSError, ValueError) as exc:
        raise registry.Blocked("GitHub Actions evidence unavailable") from exc


def verify_actions(repo: str, run_id: int, head_sha: str,
                   *, get: Callable[[str], dict] = github_get,
                   require_artifact: bool = True) -> Evidence:
    """Fail closed on pagination, identity drift, missing jobs/artifacts and stale data.

    A passing metadata check is NOT cryptographic verification of archive bytes.
    """
    if not REPO.fullmatch(repo) or type(run_id) is not int or run_id <= 0:
        raise registry.Blocked("invalid repository or run ID")
    if not SHA.fullmatch(head_sha):
        raise registry.Blocked("invalid pinned head SHA")
    base = f"/repos/{repo}/actions/runs/{run_id}"
    try:
        run = get(base)
        jobs = get(base + "/jobs?per_page=100")
        artifacts = get(base + "/artifacts?per_page=100")
    except Exception as exc:
        raise registry.Blocked("read-only evidence lookup failed") from exc
    if (run.get("id") != run_id or run.get("head_sha") != head_sha
            or run.get("repository", {}).get("full_name") != repo
            or run.get("status") != "completed" or run.get("conclusion") != "success"):
        raise registry.Blocked("run identity, source or result mismatch")
    job_list = jobs.get("jobs")
    if (not isinstance(job_list, list) or not job_list
            or jobs.get("total_count") != len(job_list)):
        raise registry.Blocked("missing or paginated jobs")
    ids = []
    for job in job_list:
        if (type(job.get("id")) is not int or job.get("run_id") != run_id
                or job.get("head_sha") not in (None, head_sha)
                or job.get("status") != "completed"
                or job.get("conclusion") != "success"):
            raise registry.Blocked("job evidence failed")
        ids.append(job["id"])
    if len(ids) != len(set(ids)):
        raise registry.Blocked("duplicate job IDs")
    items = artifacts.get("artifacts")
    if (not isinstance(items, list)
            or artifacts.get("total_count") != len(items)):
        raise registry.Blocked("missing or paginated artifacts")
    if require_artifact and not items:
        raise registry.Blocked("required artifact absent")
    artifact_ids, digests = [], []
    for artifact in items:
        workflow = artifact.get("workflow_run") or {}
        if (type(artifact.get("id")) is not int
                or artifact.get("expired") is not False
                or artifact.get("size_in_bytes", 0) <= 0
                or workflow.get("id") != run_id
                or workflow.get("head_sha") != head_sha
                or not isinstance(artifact.get("digest"), str)
                or not DIGEST.fullmatch(artifact["digest"])):
            raise registry.Blocked("artifact provenance or digest metadata invalid")
        artifact_ids.append(artifact["id"])
        digests.append(artifact["digest"])
    if len(artifact_ids) != len(set(artifact_ids)):
        raise registry.Blocked("duplicate artifact IDs")
    return Evidence(run_id, head_sha, tuple(ids), tuple(artifact_ids),
                    tuple(digests), False)
