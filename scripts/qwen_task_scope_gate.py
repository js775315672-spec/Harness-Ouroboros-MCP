#!/usr/bin/env python3
"""Fail-closed scope gate for the next Qwen multi-file development phase.

No arbitrary shell commands, protected governance files, or automatic merges.
This module only validates a proposed task manifest; it does not execute code.
"""
import json
from pathlib import PurePosixPath

ALLOWED = frozenset({
    "scripts/feedback_controller.py",
    "scripts/task_selector.py",
    "scripts/development_coordinator.py",
    "tests/test_model_feedback_loop.py",
    "tests/test_feedback_controller.py",
    "tests/test_task_selector.py",
})
PROTECTED_PREFIXES = (".github/", "security/", "policies/", "secrets/")
MAX_FILES = 2

def validate_task(task):
    if not isinstance(task, dict) or set(task) != {"task_id", "goal", "files", "requires_human_review"}:
        raise ValueError("invalid task contract")
    task_id, goal, files = task["task_id"], task["goal"], task["files"]
    if not isinstance(task_id, str) or not task_id.isascii() or not task_id.replace("_", "").isalnum() or len(task_id) > 64:
        raise ValueError("invalid task id")
    if not isinstance(goal, str) or not 1 <= len(goal) <= 400:
        raise ValueError("invalid goal")
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES or any(not isinstance(name, str) for name in files) or len(files) != len(set(files)):
        raise ValueError("invalid file list")
    for name in files:
        if not isinstance(name, str):
            raise ValueError("invalid path type")
        path = PurePosixPath(name)
        if name.startswith("/") or "\\" in name or ".." in path.parts or str(path) != name:
            raise ValueError("unsafe path")
        if name.startswith(PROTECTED_PREFIXES) or name not in ALLOWED:
            raise ValueError("file not allowlisted")
    if task["requires_human_review"] is not True:
        raise ValueError("human review is mandatory")
    return {"decision": "scoped_proposal_only", "task_id": task_id,
            "files": files, "max_files": MAX_FILES,
            "execution_authorized": False, "merge_authorized": False}

if __name__ == "__main__":
    print(json.dumps({"decision": "module_only", "execution_authorized": False}))
