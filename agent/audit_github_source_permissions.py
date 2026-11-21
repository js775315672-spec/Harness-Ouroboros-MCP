"""B2 read-only GitHub source, PR state and execution-authority audit.

Uses authenticated HTTPS GET requests only. No merge, push, write operation,
or token/callback injection into the production recovery API.
"""
import base64
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

REPO = os.environ["GITHUB_REPOSITORY"]
EXPECTED_PR = int(os.environ["OFC_EXPECTED_PR"])
AGENT = os.environ["OFC_AGENT"]
RUN_ID = os.environ["GITHUB_RUN_ID"]
TOKEN = os.environ["GITHUB_TOKEN"]
EVENT_PATH = Path(os.environ["GITHUB_EVENT_PATH"])
BRANCH = "ofc/p0-expired-lease-recovery-spec-20261122"
HEX_SHA = re.compile(r"^[a-f0-9]{40}$")
API_ROOT = "https://api.github.com/repos/" + REPO + "/"
errors = []
warnings = []
api_calls = []


def require(condition, description):
    if not condition:
        errors.append(description)


def get(path, *, optional=False):
    request = Request(
        API_ROOT + path, method="GET",
        headers={"Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "OFC-b2-source-permissions-audit",
                 "Authorization": "Bearer " + TOKEN})
    try:
        with urlopen(request, timeout=25) as response:
            code = response.status
            data = json.load(response)
            require(code == 200, "unexpected HTTP status for " + path)
            api_calls.append({"path": path, "status": code})
            return data
    except HTTPError as exc:
        api_calls.append({"path": path, "status": exc.code})
        if optional and exc.code in (403, 404):
            warnings.append("API permission visibility unavailable for " +
                            path + ": HTTP " + str(exc.code))
            return None
        raise


def workflow_permissions():
    contents = Path(".github/workflows/ofc-registry.yml").read_text(
        encoding="utf-8")
    start = contents.index("\npermissions:\n") + len("\npermissions:\n")
    end = contents.index("\njobs:\n", start)
    grants = {}
    for line in contents[start:end].splitlines():
        match = re.fullmatch(r"  ([a-z-]+): (read|write|none)", line)
        if match:
            grants[match.group(1)] = match.group(2)
    require(grants == {"contents": "read", "pull-requests": "read",
                       "actions": "read"},
            "workflow permissions must be limited to three read-only scopes")
    require("persist-credentials: false" in contents,
            "checkout may persist credentials")
    require("ref: ${{ github.event.pull_request.head.sha }}" in contents,
            "checkout is not pinned to exact PR head")
    return grants


def main():
    report = {
        "kind": "OFC_B2_REAL_GITHUB_API_READ_ONLY",
        "repo": REPO, "agent": AGENT, "pr_number": EXPECTED_PR,
        "run_id": RUN_ID, "requests": api_calls,
        "errors": errors, "warnings": warnings}
    try:
        require(bool(TOKEN), "missing runner authentication token")
        event = json.loads(EVENT_PATH.read_text(encoding="utf-8"))
        event_pr = event.get("pull_request", {})
        require(event.get("number") == EXPECTED_PR,
                "workflow event PR number mismatch")
        require(event_pr.get("number") == EXPECTED_PR,
                "workflow event PR object mismatch")
        require(event.get("repository", {}).get("full_name") == REPO,
                "workflow event repository mismatch")
        require(os.environ.get("GITHUB_EVENT_NAME") == "pull_request",
                "workflow did not originate from pull_request event")
        require(os.environ.get("GITHUB_HEAD_REF") == BRANCH,
                "workflow head branch mismatch")
        require(os.environ.get("GITHUB_BASE_REF") == "main",
                "workflow base branch mismatch")

        grants = workflow_permissions()
        report["declared_job_permissions"] = grants

        repo = get("")
        pr = get("pulls/" + str(EXPECTED_PR))
        main_ref = get("git/ref/heads/main")
        head_ref = get("git/ref/heads/" + quote(BRANCH, safe="/"))
        run = get("actions/runs/" + RUN_ID)
        head_sha = pr.get("head", {}).get("sha")
        base_sha = pr.get("base", {}).get("sha")
        main_sha = main_ref.get("object", {}).get("sha")
        branch_sha = head_ref.get("object", {}).get("sha")
        event_head = event_pr.get("head", {}).get("sha")
        event_base = event_pr.get("base", {}).get("sha")

        require(repo.get("full_name") == REPO, "repository identity mismatch")
        require(repo.get("default_branch") == "main",
                "repository default branch is not main")
        require(pr.get("number") == EXPECTED_PR, "actual PR number mismatch")
        require(pr.get("state") == "open", "PR is not open")
        require(pr.get("draft") is True, "PR is no longer Draft")
        require(pr.get("merged") is False, "PR was merged")
        require(pr.get("merged_at") is None, "PR has merged timestamp")
        require(pr.get("base", {}).get("ref") == "main", "PR base not main")
        require(pr.get("head", {}).get("ref") == BRANCH,
                "PR head branch differs from expected")
        require(pr.get("head", {}).get("repo", {}).get("full_name") == REPO,
                "PR head is not in independent repository")
        require(pr.get("base", {}).get("repo", {}).get("full_name") == REPO,
                "PR base is not in independent repository")
        require(isinstance(head_sha, str) and HEX_SHA.fullmatch(head_sha),
                "invalid PR head sha")
        require(isinstance(base_sha, str) and HEX_SHA.fullmatch(base_sha),
                "invalid PR base sha")
        require(head_sha == branch_sha == event_head,
                "PR head, branch ref, and event head differ")
        require(base_sha == main_sha == event_base,
                "PR base, main ref, and event base differ")
        require(run.get("event") == "pull_request",
                "Action execution event not pull_request")
        require(run.get("head_branch") == BRANCH,
                "Action execution head branch mismatch")
        require(run.get("name") == "P0 registry checks",
                "Action execution workflow mismatch")
        require(run.get("repository", {}).get("full_name") == REPO,
                "Action execution repository mismatch")

        # A pull_request workflow run can contain a synthetic merge SHA.
        # Only merged=true and a confirmed main ref could prove a real merge.
        report["github"] = {
            "pull_request": {"number": pr.get("number"), "state": pr.get("state"),
                             "draft": pr.get("draft"), "merged": pr.get("merged"),
                             "merged_at": pr.get("merged_at"),
                             "head_sha": head_sha, "base_sha": base_sha,
                             "merge_commit_sha_not_proof": pr.get("merge_commit_sha")},
            "main_sha": main_sha, "branch_sha": branch_sha,
            "event_head_sha": event_head, "event_base_sha": event_base,
            "run": {"id": run.get("id"), "event": run.get("event"),
                    "head_branch": run.get("head_branch"),
                    "head_sha_may_be_synthetic": run.get("head_sha"),
                    "status": run.get("status")},
        }

        # Operational execution authority is distinct from GitHub account admin
        # and from the job's read-only permissions.
        encoded_ref = quote("ofc-cycle-registry-v1", safe="")
        state_file = get("contents/state.json?ref=" + encoded_ref)
        require(state_file.get("encoding") == "base64",
                "cannot authenticate operational state encoding")
        ledger = json.loads(base64.b64decode(
            state_file.get("content", "")).decode("utf-8"))
        require(ledger.get("agent") == AGENT and ledger.get("schema") == 1,
                "operational ledger identity mismatch")
        require(ledger.get("source") == main_sha,
                "operational ledger pinned source drift")
        require(ledger.get("pending") is None,
                "unresolved external operation exists")
        require(ledger.get("expires") == 0,
                "unexpected active operational execution lease")
        report["execution_authority"] = {
            "ledger_generation": ledger.get("generation"),
            "ledger_phase": ledger.get("phase"),
            "ledger_pending": ledger.get("pending"),
            "lease_expires": ledger.get("expires"),
            "active_lease": ledger.get("expires", 0) > 0,
            "production_merge_recovery_authorized": False,
            "account_admin_not_equivalent_to_run_token": True,
        }

        # Read-only policy API may be inaccessible to the Actions token.
        policy = get("actions/permissions/workflow", optional=True)
        report["repository_workflow_policy"] = (
            {"visibility": "READABLE",
             "default_workflow_permissions":
                 policy.get("default_workflow_permissions"),
             "can_approve_pull_request_reviews":
                 policy.get("can_approve_pull_request_reviews")}
            if isinstance(policy, dict)
            else {"visibility": "NOT_AUTHORIZED_OR_NOT_AVAILABLE"})
    except Exception as exc:
        errors.append(type(exc).__name__ + ": " + str(exc))
    report["pass"] = not errors
    output = Path("artifacts/ofc-b2-github-source-read-only.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print("OFC_B2_SOURCE_AUDIT=" + json.dumps(report, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
