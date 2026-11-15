#!/usr/bin/env python3
"""Fail-closed, review-only handoff of a verified model patch into Ouroboros queue.

This is a bridge, not a source code executor. It consumes a pinned archived
model candidate, optionally replays independent Docker tests, emits a bounded
unified patch, and creates a queue checkpoint still awaiting external execution.
No task is marked complete, no source file is changed, and no merge is allowed.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import sys

from qwen_source_guard import ORIGINAL, TARGET
from verified_model_patch_review import inspect_proposal, replay
from resumable_task_queue import new_queue, next_action, load as load_queue, save as save_queue

REPOSITORY = "js775315672-spec/Harness-Ouroboros-MCP"
SHA = re.compile(r"[0-9a-f]{40}\Z")
TASK = "feedback_cycle_guard"
DESCRIPTION = "Review a model-authored invalid-cycle guard repair; no automatic source write"
FILES = ("queue.json", "candidate.patch", "receipt.json")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def make_patch(root, record):
    target = Path(root) / TARGET
    if target.is_symlink() or not target.is_file():
        raise ValueError("unsafe trusted source target")
    original = target.read_text(encoding="utf-8")
    anchor = ORIGINAL + "\n"
    if original.count(anchor) != 1:
        raise ValueError("trusted patch anchor missing or ambiguous")
    candidate_line = record["candidate_line"]
    changed = original.replace(anchor, candidate_line + "\n", 1)
    if changed == original:
        raise ValueError("no source change in candidate")
    delta = "".join(difflib.unified_diff(
        original.splitlines(keepends=True),
        changed.splitlines(keepends=True),
        fromfile="a/" + TARGET, tofile="b/" + TARGET, n=3))
    if not delta.startswith("--- a/" + TARGET + "\n+++ b/" + TARGET + "\n"):
        raise ValueError("unexpected patch structure")
    # The generated patch is only ever an artifact; never run git apply here.
    return ("diff --git a/" + TARGET + " b/" + TARGET + "\n" + delta).encode("utf-8")


def construct(root, evidence_path, commit, docker=False, docker_replay=replay):
    if not isinstance(commit, str) or not SHA.fullmatch(commit):
        raise ValueError("invalid commit for queue checkpoint")
    record, inspection = inspect_proposal(root, evidence_path)
    if record["task_id"] != TASK:
        raise ValueError("archived proposal does not match queue task")
    if docker:
        verification = docker_replay(root, evidence_path, docker=True)
        if (not isinstance(verification, dict) or
                verification.get("status") != "isolated_replay_passed" or
                verification.get("docker_replayed") is not True or
                verification.get("merge_authorized") is not False or
                verification.get("candidate_line_sha256") != inspection["line_sha256"]):
            raise ValueError("independent Docker replay not attested")
        gate = "docker_replay_passed"
    else:
        gate = "static_ast_only"
    queue = new_queue([{"id": TASK, "description": DESCRIPTION}], REPOSITORY, commit)
    action = next_action(queue)
    if (action["decision"] != "await_external_executor" or
            action["completed_tasks"] != 0 or
            action["task_id"] != TASK or
            action["merge_authorized"] is not False):
        raise ValueError("queue must remain pending, not completed")
    patch = make_patch(root, record)
    receipt = {
        "schema": 1,
        "task_id": TASK,
        "repository": REPOSITORY,
        "head_commit": commit,
        "source_sha256": record["source_sha256"],
        "candidate_line_sha256": record["candidate_line_sha256"],
        "patch_sha256": sha256(patch),
        "gate": gate,
        "next_action": "await_external_executor",
        "completed_tasks": 0,
        "candidate_patches_generated": 1,
        "code_applied": False,
        "source_checkout_modified": False,
        "autonomous_coding_connected": False,
        "merge_authorized": False,
        "human_review_required": True,
    }
    return queue, patch, receipt


def write_artifacts(directory, queue, patch, receipt):
    directory = Path(directory).absolute()
    if directory.is_symlink():
        raise ValueError("symlink output directory forbidden")
    directory.mkdir(parents=True, exist_ok=True)
    if any((directory / name).exists() or (directory / name).is_symlink() for name in FILES):
        raise ValueError("refusing to overwrite handoff artifacts")
    save_queue(directory / FILES[0], queue)
    try:
        with (directory / FILES[1]).open("xb") as stream:
            stream.write(patch)
        with (directory / FILES[2]).open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, indent=2, sort_keys=True)
            stream.write("\n")
    except OSError:
        # Fail closed; a partial handoff is never accepted by verify().
        raise


def verify(root, evidence_path, directory, commit, require_docker=True):
    directory = Path(directory).absolute()
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("unsafe artifact directory")
    for name in FILES:
        item = directory / name
        if item.is_symlink() or not item.is_file() or item.stat().st_size > 262144:
            raise ValueError("unsafe handoff artifact")
    queue = load_queue(directory / FILES[0])
    if (queue["repo"] != REPOSITORY or queue["base_commit"] != commit or
            queue["last_commit"] != commit or queue["index"] != 0 or
            queue["generation"] != 0 or queue["events"] or
            queue["controller"] != {"cycle": 1, "attempt": 1, "phase": "await_evidence"}):
        raise ValueError("checkpoint not bound to current review commit")
    pending = next_action(queue)
    if (pending["decision"] != "await_external_executor" or
            pending["task_id"] != TASK or
            pending["completed_tasks"] != 0 or
            pending["merge_authorized"] is not False):
        raise ValueError("review artifact cannot complete a development cycle")
    expected_queue, expected_patch, expected_receipt = construct(
        root, evidence_path, commit, docker=False)
    if queue != expected_queue:
        raise ValueError("unexpected serialized queue")
    if (directory / FILES[1]).read_bytes() != expected_patch:
        raise ValueError("patch differs from scoped model proposal")
    receipt = json.loads((directory / FILES[2]).read_text(encoding="utf-8"))
    if not isinstance(receipt, dict) or set(receipt) != set(expected_receipt):
        raise ValueError("invalid handoff receipt")
    expected_receipt["gate"] = "docker_replay_passed" if require_docker else receipt.get("gate")
    if receipt != expected_receipt:
        raise ValueError("handoff receipt mismatch or missing Docker proof")
    return {"status": "verified_review_handoff", "task_id": TASK,
            "completed_tasks": 0, "patch_sha256": expected_receipt["patch_sha256"],
            "checkpoint_restored": True, "code_applied": False,
            "merge_authorized": False, "human_review_required": True,
            "docker_replay_receipt": receipt["gate"] == "docker_replay_passed"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=("prepare", "verify"))
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--evidence", type=Path,
                   default=Path("proposals/feedback_cycle_guard_7b.json"))
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--head-sha", required=True)
    p.add_argument("--docker", action="store_true")
    args = p.parse_args()
    try:
        if args.mode == "prepare":
            queue, patch, receipt = construct(args.root, args.evidence, args.head_sha, docker=args.docker)
            write_artifacts(args.out, queue, patch, receipt)
            result = {"status": "review_handoff_prepared", **receipt}
        else:
            result = verify(args.root, args.evidence, args.out, args.head_sha,
                            require_docker=True)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError, UnicodeError,
            json.JSONDecodeError) as exc:
        print(json.dumps({"status": "blocked", "error_type": type(exc).__name__}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
