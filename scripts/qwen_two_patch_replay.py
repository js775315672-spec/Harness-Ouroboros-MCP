#!/usr/bin/env python3
"""Independent, no-model Docker replay of two archived Qwen-authored source edits.

Outputs a review-only unified patch and a *pending* two-task Ouroboros queue.
A successful replay is evidence of behavior in isolated Docker, NOT proof of
model authorship, independent CI commit approval, a finished development cycle,
unattended hours-long coding, or permission to merge/deploy/trade.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import sys

from qwen_source_guard import TARGET
from qwen_second_task_trial import (
    LOG_ORIGINAL, TASK_ID, evaluate, make_candidate, normalize_expression,
)
from verified_model_patch_review import inspect_proposal
from resumable_task_queue import new_queue, load as load_queue, save as save_queue

REPO = "js775315672-spec/Harness-Ouroboros-MCP"
ARCHIVE = "proposals/two_qwen_7b_patches_v1.json"
FIRST = "proposals/feedback_cycle_guard_7b.json"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
REVIEW_FILES = ("queue.json", "candidate.patch", "receipt.json")
FIELDS = {
    "schema_version", "task_ids", "first_model_run", "second_model_run",
    "model", "license", "gguf_sha256", "model_revision",
    "baseline_source_sha256", "first_line_sha256",
    "second_model_response_sha256", "second_line_sha256", "second_line",
    "first_plus_second_source_sha256", "model_calls_second",
    "docker_comparisons_second", "existing_regression_tests",
    "new_negative_test_methods", "isolated_source_patched",
    "checkout_source_modified", "queue_completed_tasks", "merge_authorized",
    "requires_human_review",
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def inspect(root, archive=ARCHIVE):
    root = Path(root).resolve(strict=True)
    path = root / archive
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 12000:
        raise ValueError("invalid two-patch evidence path")
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or set(doc) != FIELDS:
        raise ValueError("invalid two-patch evidence schema")
    if (type(doc["schema_version"]) is not int or doc["schema_version"] != 1
            or doc["task_ids"] != ["feedback_cycle_guard", TASK_ID]
            or doc["model"] != "Qwen/Qwen2.5-Coder-7B-Instruct-GGUF"
            or doc["license"] != "apache-2.0"
            or doc["isolated_source_patched"] is not True
            or doc["checkout_source_modified"] is not False
            or type(doc["queue_completed_tasks"]) is not int
            or doc["queue_completed_tasks"] != 0
            or doc["merge_authorized"] is not False
            or doc["requires_human_review"] is not True):
        raise ValueError("model scope or governance invariant mismatch")
    for key in ("model_calls_second", "docker_comparisons_second",
                "existing_regression_tests", "new_negative_test_methods"):
        if type(doc[key]) is not int or doc[key] < 1:
            raise ValueError("invalid evidence counter")
    if (doc["model_calls_second"] != 1 or doc["docker_comparisons_second"] != 1
            or doc["existing_regression_tests"] != 8
            or doc["new_negative_test_methods"] != 3):
        raise ValueError("unexpected bounded trial evidence")
    for key in ("gguf_sha256", "baseline_source_sha256",
                "first_line_sha256", "second_model_response_sha256",
                "second_line_sha256", "first_plus_second_source_sha256"):
        if not isinstance(doc[key], str) or not SHA64.fullmatch(doc[key]):
            raise ValueError("malformed archived source or model digest")
    if not isinstance(doc["model_revision"], str) or not SHA40.fullmatch(doc["model_revision"]):
        raise ValueError("unverified model revision")
    for key in ("first_model_run", "second_model_run"):
        value = doc[key]
        if (not isinstance(value, str) or not re.fullmatch(
                r"https://github\.com/js775315672-spec/Harness-Ouroboros-MCP/"
                r"actions/runs/[1-9][0-9]*", value)):
            raise ValueError("unverified run reference syntax")
    first_record, _ = inspect_proposal(root, root / FIRST)
    target = root / TARGET
    if target.is_symlink() or not target.is_file():
        raise ValueError("unsafe source checkout path")
    original = target.read_bytes()
    if (sha256(original) != doc["baseline_source_sha256"]
            or first_record["source_sha256"] != doc["baseline_source_sha256"]
            or first_record["candidate_line_sha256"] != doc["first_line_sha256"]):
        raise ValueError("archived first source repair baseline mismatch")
    line = doc["second_line"]
    anchor = LOG_ORIGINAL[:-1] + " or ("
    if (not isinstance(line, str) or len(line) > 350
            or not line.startswith(anchor) or not line.endswith("):")
            or "\n" in line or "\r" in line):
        raise ValueError("untrusted second model line")
    expression = normalize_expression(line[len(anchor):-2])
    first_source, second_source, rebuilt_line = make_candidate(
        original.decode("utf-8"), first_record["candidate_line"], expression)
    if (rebuilt_line != line or
            sha256(line.encode("utf-8")) != doc["second_line_sha256"]
            or sha256(second_source.encode("utf-8")) != doc["first_plus_second_source_sha256"]):
        raise ValueError("second model source cannot be reproduced")
    return doc, first_record, original.decode("utf-8"), second_source, expression


def patch_bytes(before, after):
    diff = "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile="a/" + TARGET, tofile="b/" + TARGET, n=3))
    if not diff.startswith("--- a/" + TARGET + "\n+++ b/" + TARGET + "\n"):
        raise ValueError("empty or untrusted generated patch")
    data = ("diff --git a/" + TARGET + " b/" + TARGET + "\n" + diff).encode("utf-8")
    if not 0 < len(data) < 5000:
        raise ValueError("scoped patch budget exceeded")
    return data


def construct(root, commit, evaluator=evaluate):
    if not isinstance(commit, str) or not SHA40.fullmatch(commit):
        raise ValueError("invalid head commit")
    doc, first, original, combined, expression = inspect(root)
    result = evaluator(root, first["candidate_line"], expression,
                       doc["baseline_source_sha256"])
    if (not isinstance(result, dict)
            or result.get("outcome") != "second_patch_passed"
            or result.get("second_patch_sha256") != doc["first_plus_second_source_sha256"]
            or result.get("second_line_sha256") != doc["second_line_sha256"]
            or result.get("source_checkout_modified") is not False
            or result.get("merge_authorized") is not False
            or not isinstance(result.get("baseline_negative_control"), dict)
            or result["baseline_negative_control"].get("passed") is not False
            or result["baseline_negative_control"].get("tests_run") != 3
            or not isinstance(result.get("candidate_negative_control"), dict)
            or result["candidate_negative_control"].get("passed") is not True
            or result["candidate_negative_control"].get("tests_run") != 3
            or not isinstance(result.get("candidate_regression"), dict)
            or result["candidate_regression"].get("passed") is not True
            or result["candidate_regression"].get("tests_run") != 8):
        raise ValueError("independent two-patch Docker replay failed")
    queue = new_queue([
        {"id": "feedback_cycle_guard",
         "description": "Model-authored invalid cycle guard - pending external source commit"},
        {"id": TASK_ID,
         "description": "Second model-authored log control guard - pending external source commit"},
    ], REPO, commit)
    diff = patch_bytes(original, combined)
    receipt = {"schema_version": 1, "head_commit": commit, "task_count": 2,
               "completed_tasks": 0, "queue_pending": True,
               "patch_sha256": sha256(diff),
               "source_sha256": doc["baseline_source_sha256"],
               "combined_source_sha256": doc["first_plus_second_source_sha256"],
               "docker_replay": "independent_two_patch_replay_passed",
               "first_model_run": doc["first_model_run"],
               "second_model_run": doc["second_model_run"],
               "checkout_modified": False, "merge_authorized": False,
               "human_approval_required": True}
    return queue, diff, receipt


def write(directory, queue, patch, receipt):
    directory = Path(directory).absolute()
    if directory.is_symlink():
        raise ValueError("unsafe review artifact output directory")
    directory.mkdir(parents=True, exist_ok=True)
    if any((directory / file).exists() or (directory / file).is_symlink()
           for file in REVIEW_FILES):
        raise ValueError("refusing review artifact overwrite")
    save_queue(directory / "queue.json", queue)
    (directory / "candidate.patch").write_bytes(patch)
    (directory / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify(root, directory, commit):
    root, directory = Path(root).resolve(strict=True), Path(directory).absolute()
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("invalid two-patch artifact location")
    for name in REVIEW_FILES:
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 262144:
            raise ValueError("invalid artifact file")
    doc, first, original, combined, expression = inspect(root)
    checkpoint = load_queue(directory / "queue.json")
    if (checkpoint["base_commit"] != commit or
            checkpoint["last_commit"] != commit or checkpoint["index"] != 0
            or checkpoint["generation"] != 0 or checkpoint["events"]
            or checkpoint["requires_human_merge_approval"] is not True
            or [x["id"] for x in checkpoint["tasks"]] != doc["task_ids"]):
        raise ValueError("queue tampering or false task completion")
    expected_diff = patch_bytes(original, combined)
    if (directory / "candidate.patch").read_bytes() != expected_diff:
        raise ValueError("two-patch output has changed")
    receipt = json.loads((directory / "receipt.json").read_text(encoding="utf-8"))
    if (not isinstance(receipt, dict) or receipt.get("schema_version") != 1
            or receipt.get("head_commit") != commit
            or receipt.get("task_count") != 2
            or receipt.get("completed_tasks") != 0
            or receipt.get("queue_pending") is not True
            or receipt.get("patch_sha256") != sha256(expected_diff)
            or receipt.get("combined_source_sha256") != doc["first_plus_second_source_sha256"]
            or receipt.get("docker_replay") != "independent_two_patch_replay_passed"
            or receipt.get("checkout_modified") is not False
            or receipt.get("merge_authorized") is not False
            or receipt.get("human_approval_required") is not True):
        raise ValueError("missing independent replay receipt")
    return {"status": "review_only_two_patch_queue_restored",
            "tasks": len(checkpoint["tasks"]), "completed_tasks": 0,
            "source_checkout_modified": False, "merge_authorized": False,
            "patch_sha256": sha256(expected_diff)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=("prepare", "verify"))
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--head-sha", required=True)
    p.add_argument("--directory", type=Path, required=True)
    args = p.parse_args()
    try:
        if args.command == "prepare":
            queue, diff, receipt = construct(args.root, args.head_sha)
            write(args.directory, queue, diff, receipt)
            result = {"status": "independent_two_patch_replay_passed",
                      "pending_tasks": 2, "completed_tasks": 0,
                      "source_checkout_modified": False, "merge_authorized": False}
        else:
            result = verify(args.root, args.directory, args.head_sha)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError,
            UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "blocked", "error_type": type(exc).__name__,
                          "error_code": str(exc)[:130]}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
