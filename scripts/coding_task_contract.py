#!/usr/bin/env python3
"""Fail-closed contract for a single real-repository coding task.

This validates task metadata only. It does not invoke a model, run generated
code, write a repository file, or authorize a merge.
"""
import json
import re
from pathlib import PurePosixPath

ALLOWED_ROOTS=("scripts","tests","agents","orchestration","memory","training")
MAX_PROMPT_CHARS=3000
MAX_FILES=3

def _path(value):
    if not isinstance(value,str) or not value or len(value)>160:
        raise ValueError("invalid path")
    if "\\" in value or value.startswith("/") or "\x00" in value:
        raise ValueError("unsafe path")
    parts=value.split("/")
    if len(parts)<2 or parts[0] not in ALLOWED_ROOTS or any(x in ("",".","..") for x in parts):
        raise ValueError("unsafe path")
    if any(x.startswith(".") or x=="__pycache__" for x in parts):
        raise ValueError("hidden or generated path denied")
    if not value.endswith(".py"):
        raise ValueError("Python files only")
    return value

def validate_task(task):
    if not isinstance(task,dict):
        raise ValueError("task must be an object")
    required={"task_id","goal","allowed_files","acceptance_tests","max_attempts"}
    if set(task)!=required:
        raise ValueError("unknown or missing task fields")
    task_id=task["task_id"]
    if not isinstance(task_id,str) or not re.fullmatch(r"[a-z][a-z0-9_-]{2,39}",task_id):
        raise ValueError("invalid task id")
    goal=task["goal"]
    if not isinstance(goal,str) or not 10<=len(goal)<=MAX_PROMPT_CHARS:
        raise ValueError("invalid goal")
    files=task["allowed_files"]
    if not isinstance(files,list) or not 1<=len(files)<=MAX_FILES:
        raise ValueError("allowed_files must contain 1..3 paths")
    paths=[_path(x) for x in files]
    if len(set(paths))!=len(paths):
        raise ValueError("duplicate paths")
    tests=task["acceptance_tests"]
    if not isinstance(tests,list) or not 1<=len(tests)<=5:
        raise ValueError("acceptance tests required")
    for name in tests:
        if not isinstance(name,str) or not re.fullmatch(r"tests/test_[a-zA-Z0-9_]+\\.py",name):
            raise ValueError("acceptance tests must be test files")
        if name not in paths:
            raise ValueError("acceptance test must be within allowed_files")
    limit=task["max_attempts"]
    if type(limit) is not int or not 1<=limit<=3:
        raise ValueError("max_attempts must be 1..3")
    return {"task_id":task_id,"allowed_files":paths,
            "acceptance_tests":tests,"max_attempts":limit,
            "model_execution_authorized":False,"patch_application_authorized":False,
            "merge_authorized":False,"requires_harness_revalidation":True}

def serialize_task(task):
    return json.dumps(validate_task(task),sort_keys=True)
