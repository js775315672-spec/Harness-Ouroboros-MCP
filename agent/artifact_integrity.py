"""Read-only Actions artifact archive verification (SHA-256 over exact downloaded ZIP bytes).

Never extracts or executes ZIP. Caller pins the artifact metadata and injects a
read-only download transport; verify_actions() must run before this function.
"""
import hashlib
import hmac
import io
import re
import urllib.request
import urllib.parse
import zipfile
from agent import cycle_registry as registry

DIGEST = re.compile(r"^sha256:([0-9a-f]{64})$")
MAX_BYTES = 50 * 1024 * 1024

def download_zip(url: str, token: str = "") -> bytes:
    if not url.startswith("https://api.github.com/repos/") or "/actions/artifacts/" not in url or not url.endswith("/zip"):
        raise registry.Blocked("untrusted artifact download URL")
    request = urllib.request.Request(url, method="GET",
        headers={"Accept": "application/vnd.github+json",
                 **({"Authorization": "Bearer " + token} if token else {})})
    class SafeRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
            if redirected and urllib.parse.urlsplit(newurl).hostname != urllib.parse.urlsplit(req.full_url).hostname:
                redirected.remove_header('Authorization')
                redirected.remove_unredirected_header('Authorization')
            return redirected

    try:
        opener = urllib.request.build_opener(SafeRedirect())
        with opener.open(request, timeout=20) as response:
            data = response.read(MAX_BYTES + 1)
    except (OSError, ValueError) as exc:
        raise registry.Blocked("artifact download failed") from exc
    return data

def verify_zip(artifact: dict, *, repo: str, run_id: int, head_sha: str,
               fetch=download_zip, max_bytes: int = MAX_BYTES) -> str:
    """Return verified sha256 digest, otherwise BLOCKED without side effects."""
    if not isinstance(artifact, dict):
        raise registry.Blocked("artifact metadata absent")
    match = DIGEST.fullmatch(artifact.get("digest", ""))
    workflow = artifact.get("workflow_run") or {}
    artifact_id = artifact.get("id")
    size = artifact.get("size_in_bytes")
    if (not match or type(artifact_id) is not int or artifact_id <= 0
            or type(run_id) is not int or run_id <= 0
            or not re.fullmatch(r"[0-9a-f]{40}", head_sha)
            or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo)
            or artifact.get("expired") is not False
            or workflow.get("id") != run_id or workflow.get("head_sha") != head_sha
            or type(size) is not int or size <= 0 or size > max_bytes):
        raise registry.Blocked("artifact provenance, size or digest missing")
    url = f"https://api.github.com/repos/{repo}/actions/artifacts/{artifact_id}/zip"
    try:
        data = fetch(url)
    except Exception as exc:
        raise registry.Blocked("artifact download unavailable") from exc
    if not isinstance(data, bytes) or len(data) != size or len(data) > max_bytes:
        raise registry.Blocked("artifact bytes missing, truncated or oversized")
    if not hmac.compare_digest(hashlib.sha256(data).hexdigest(), match.group(1)):
        raise registry.Blocked("artifact digest mismatch")
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise registry.Blocked("artifact is not a ZIP archive")
    return "sha256:" + hashlib.sha256(data).hexdigest()
