"""Read a W05 input archive from the expected GitHub Actions run and job."""
import hashlib
import io
import json
import re
import subprocess
import zipfile

REPOSITORY = "js775315672-spec/Harness-Ouroboros-MCP"
WORKFLOW = ".github/workflows/ledger-next-experiment.yml"
MAX_ARCHIVE_BYTES = 40_000
QWEN_REVISION = "13fb94bfda8c8cf22497dc57b78f391a9acb426a"
QWEN_WEIGHTS_SHA256 = "509287f78cb4d4cf6b3843734733b914b2c158e43e22a7f4bf5e963800894d3c"


def github_api(path):
    result = subprocess.run(
        ["gh", "api", "--hostname", "github.com", path],
        capture_output=True, timeout=30, check=False,
    )
    if result.returncode:
        raise ValueError("GitHub Actions evidence request failed")
    return result.stdout


def read_model_archive(run_id, head_sha, artifact_id, *, fetch=github_api):
    """Obtain model JSON bytes only after binding the ZIP to Actions metadata."""
    if (type(run_id) is not int or run_id < 1 or type(artifact_id) is not int or artifact_id < 1
            or type(head_sha) is not str or re.fullmatch(r"[0-9a-f]{40}", head_sha) is None):
        raise ValueError("invalid expected GitHub Actions identity")
    actions = f"repos/{REPOSITORY}/actions"
    run_path = f"{actions}/runs/{run_id}"
    run = json.loads(fetch(run_path))
    repo_id = run["repository"]["id"]
    if (type(repo_id) is not int or repo_id < 1 or run["repository"]["full_name"] != REPOSITORY
            or type(run["id"]) is not int or run["id"] != run_id
            or type(run["run_attempt"]) is not int or run["run_attempt"] != 1
            or run["path"] != WORKFLOW or run["event"] != "pull_request"
            or run["head_sha"] != head_sha or run["head_repository"]["full_name"] != REPOSITORY):
        raise ValueError("GitHub workflow run or reviewed HEAD mismatch")
    jobs = json.loads(fetch(f"{run_path}/attempts/1/jobs?per_page=100"))
    if type(jobs["total_count"]) is not int or jobs["total_count"] != len(jobs["jobs"]):
        raise ValueError("incomplete GitHub workflow job list")
    model_jobs = [job for job in jobs["jobs"] if job["name"] == "actual_qwen_model"]
    if len(model_jobs) != 1:
        raise ValueError("expected exactly one model job")
    job = model_jobs[0]
    if (type(job["id"]) is not int or job["id"] < 1 or type(job["run_id"]) is not int
            or job["run_id"] != run_id or job["head_sha"] != head_sha
            or job["status"] != "completed" or job["conclusion"] != "success"):
        raise ValueError("GitHub model job did not complete successfully at reviewed HEAD")
    uploads = [step for step in job["steps"]
               if step["name"] == "Keep raw model output and provenance on pass or failure"]
    if len(uploads) != 1 or uploads[0]["status"] != "completed" or uploads[0]["conclusion"] != "success":
        raise ValueError("GitHub model artifact upload did not succeed")
    artifact_path = f"{actions}/artifacts/{artifact_id}"
    artifact = json.loads(fetch(artifact_path))
    source = artifact["workflow_run"]
    if (type(artifact["id"]) is not int or artifact["id"] != artifact_id
            or artifact["name"] != "p3l-w06-raw-model-output" or artifact["expired"] is not False
            or type(source["id"]) is not int or source["id"] != run_id
            or type(source["repository_id"]) is not int or source["repository_id"] != repo_id
            or type(source["head_repository_id"]) is not int or source["head_repository_id"] != repo_id
            or source["head_sha"] != head_sha or source["head_branch"] != run["head_branch"]):
        raise ValueError("GitHub model artifact source mismatch")
    size = artifact["size_in_bytes"]
    if type(size) is not int or not 1 <= size <= MAX_ARCHIVE_BYTES:
        raise ValueError("invalid GitHub model artifact size")
    archive = fetch(f"{artifact_path}/zip")
    found = hashlib.sha256(archive).hexdigest()
    if len(archive) != size or artifact["digest"] != f"sha256:{found}":
        raise ValueError("GitHub model artifact bytes mismatch")
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        if sorted(zipped.namelist()) != ["model-output.json", "model-provenance.json"]:
            raise ValueError("unexpected model artifact contents")
        if any(not 1 <= item.file_size <= MAX_ARCHIVE_BYTES for item in zipped.infolist()):
            raise ValueError("invalid model artifact member size")
        receipt = json.loads(zipped.read("model-output.json"))
        model = json.loads(zipped.read("model-provenance.json"))
    if (model["model"] != "7b" or model["revision"] != QWEN_REVISION
            or model["sha256"] != QWEN_WEIGHTS_SHA256
            or model["secret_or_paid_api_used"] is not False):
        raise ValueError("unexpected pinned Qwen model provenance")
    return receipt, {
        "repository": REPOSITORY,
        "head_sha": head_sha,
        "workflow": WORKFLOW,
        "run_id": run_id,
        "model_job_id": job["id"],
        "model_artifact_id": artifact_id,
        "model_archive_sha256": found,
        "model_revision": model["revision"],
        "model_weights_sha256": model["sha256"],
    }
