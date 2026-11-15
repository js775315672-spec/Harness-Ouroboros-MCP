#!/usr/bin/env python3
"""Read-only attestation of two real, separate model-authored repair commits.

Checks the archived source bytes, GitHub commit parentage and changed files,
and the *completed* Harness safety workflow on each commit. Only then calls
resumable_task_queue.advance twice and publishes the resulting checkpoint.
Uses public GitHub REST reads, with no token, source writes, PR merge, or API cost.
Not an unattended coding executor. The verified module is opt-in/non-production.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

from resumable_task_queue import new_queue, advance, save, next_action

REPO = "js775315672-spec/Harness-Ouroboros-MCP"
BASE = "0cd785cd86d4912a603c1048d3573d793fc17678"
COMMITS = (
    "817cbd679de72fae9bd02360af51213ac61176d1",
    "a0383fcd48e6214392519464cd099e0ef46e2667",
)
RUN_IDS = (43724306905, 43724502763)
TASKS = (
    {"id": "feedback_cycle_guard",
     "description": "Commit Qwen-authored invalid-cycle guard in reviewed candidate module"},
    {"id": "feedback_log_control_guard",
     "description": "Commit Qwen-authored log NUL/ESC guard in reviewed candidate module"},
)
FILE = "scripts/feedback_controller_verified.py"
TEST = "tests/test_feedback_controller_verified.py"
ORIGINAL = "scripts/feedback_controller.py"
MODEL1 = "proposals/feedback_cycle_guard_7b.json"
MODEL2 = "proposals/two_qwen_7b_patches_v1.json"
BASE_GUARD = '    if not isinstance(proposal,dict) or proposal.get("decision")!="propose":'
LOG_GUARD = ('        if status not in ("pass","fail") or not isinstance(log,str) '
             'or len(log)>MAX_LOG_CHARS:')
API = "https://api.github.com/repos/" + REPO
SHA = re.compile(r"[0-9a-f]{40}\Z")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def public_get(url):
    if not isinstance(url, str) or not url.startswith(API + "/"):
        raise ValueError("unapproved public GitHub API origin")
    req = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json",
                      "User-Agent": "AURA-readonly-commit-attestor"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def source_bytes(payload):
    if (not isinstance(payload, dict) or payload.get("type") != "file"
            or payload.get("encoding") != "base64"
            or not isinstance(payload.get("content"), str)
            or len(payload["content"]) > 40_000):
        raise ValueError("untrusted Github source content")
    return base64.b64decode(payload["content"].replace("\n", ""), validate=True)


def read_input(root, relative):
    path = Path(root) / relative
    if (path.is_symlink() or not path.is_file() or
            not path.resolve(strict=True).is_relative_to(Path(root).resolve(strict=True))
            or path.stat().st_size > 20_000):
        raise ValueError("invalid trusted archived source file")
    return path.read_bytes()


def attest(root, fetch=public_get):
    root = Path(root).resolve(strict=True)
    original = read_input(root, ORIGINAL)
    first = json.loads(read_input(root, MODEL1).decode("utf-8"))
    second = json.loads(read_input(root, MODEL2).decode("utf-8"))
    if (sha256(original) != first["source_sha256"]
            or sha256(original) != second["baseline_source_sha256"]
            or sha256(first["candidate_line"].encode()) != first["candidate_line_sha256"]
            or sha256(second["second_line"].encode()) != second["second_line_sha256"]):
        raise ValueError("archived model-origin hashes differ")
    text = original.decode("utf-8")
    if text.count(BASE_GUARD + "\n") != 1 or text.count(LOG_GUARD + "\n") != 1:
        raise ValueError("ambiguous model patch anchors")
    first_source = text.replace(BASE_GUARD + "\n", first["candidate_line"] + "\n", 1)
    second_source = first_source.replace(LOG_GUARD + "\n", second["second_line"] + "\n", 1)
    if sha256(second_source.encode()) != second["first_plus_second_source_sha256"]:
        raise ValueError("combined model patch digest mismatch")
    expected = (first_source.encode(), second_source.encode())
    queue = new_queue(list(TASKS), REPO, BASE)
    previous_commit = BASE
    log = []
    for i, (commit, run_id) in enumerate(zip(COMMITS, RUN_IDS)):
        if not SHA.fullmatch(commit):
            raise ValueError("malformed evidence commit")
        commit_meta = fetch(API + "/commits/" + commit)
        if (not isinstance(commit_meta, dict) or commit_meta.get("sha") != commit
                or not isinstance(commit_meta.get("parents"), list)
                or len(commit_meta["parents"]) != 1
                or commit_meta["parents"][0].get("sha") != previous_commit):
            raise ValueError("commit is not a separate chained development change")
        file_rows = commit_meta.get("files")
        if (not isinstance(file_rows, list)
                or {(f.get("filename"), f.get("status"))
                    for f in file_rows if isinstance(f, dict)}
                != {(FILE, "added" if i == 0 else "modified"),
                    (TEST, "added" if i == 0 else "modified")}):
            raise ValueError("changed-file scope or actual code change invalid")
        latest_content = fetch(API + "/contents/" + FILE + "?ref=" + commit)
        if source_bytes(latest_content) != expected[i]:
            raise ValueError("model-authored committed source does not match archived code")
        run_url = f"https://github.com/{REPO}/actions/runs/{run_id}"
        api_run = API + "/actions/runs/" + str(run_id)
        workflow = fetch(api_run)
        if (not isinstance(workflow, dict)
                or workflow.get("name") != "Harness safety checks"
                or workflow.get("path") != ".github/workflows/harness.yml"
                or workflow.get("conclusion") != "success"
                or workflow.get("status") != "completed"
                or workflow.get("head_sha") != commit):
            raise ValueError("independent Harness CI not successful on exact source commit")
        evidence = {
            "task_id": TASKS[i]["id"], "source_changed": True,
            "commit": commit, "ci_url": run_url,
            "checks": {k: "pass" for k in ("harness", "ouroboros", "regression", "secrets")}
        }
        # The queue's existing verifier independently binds CI run URL,
        # repository, workflow name/path and PR head to the exact commit.
        queue = advance(queue, evidence, fetch=fetch)
        if queue["index"] != i + 1:
            raise ValueError("task queue did not advance as attested")
        log.append({"task": TASKS[i]["id"], "commit": commit,
                    "harness_run": run_id, "verified": True})
        previous_commit = commit
    action = next_action(queue)
    if (queue["index"] != 2 or queue["generation"] != 2
            or queue["requires_human_merge_approval"] is not True
            or action["decision"] != "human_review"
            or action["merge_authorized"] is not False):
        raise ValueError("post-attestation queue safety invariant failed")
    return queue, {
        "status": "two_distinct_model_patches_committed_and_ci_attested",
        "task_count": 2, "completed_tasks": 2, "workflows": log,
        "source_candidate_file": FILE, "active_original_source_modified": False,
        "human_merge_approval_required": True, "merge_authorized": False,
        "autonomous_worker_implemented": False,
        "long_running_coding_demonstrated": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        queue, receipt = attest(args.root)
        out = args.output.absolute()
        if out.exists() or out.is_symlink() or out.parent.is_symlink():
            raise ValueError("refusing overwrite or symlink output")
        out.parent.mkdir(parents=True, exist_ok=True)
        save(out, queue)
        proof = out.with_name("attested-two-tasks-receipt.json")
        if proof.exists() or proof.is_symlink():
            raise ValueError("refusing previous receipt overwrite")
        proof.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError, UnicodeError,
            urllib.error.URLError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "blocked", "error_type": type(exc).__name__,
                          "error_code": str(exc)[:130]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
