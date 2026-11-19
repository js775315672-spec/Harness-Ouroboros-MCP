#!/usr/bin/env python3
"""Read-only lane selector for Hydra fast-loop preflight.

This is a deterministic planning contract, NOT a distributed lease, executor,
CI attestor, model invocation, approval or authorization to merge/promote.
All task states are untrusted until externally attested.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
PATH = re.compile(r"(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\Z")
STATES = {"pending", "running", "passed", "failed", "blocked"}
SCHEMA = "p3l-hydra-fast-lanes-v1"


def _digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def select_lanes(data):
    """Advisory only: select nonconflicting, dependency-ready tasks in FIFO order."""
    if type(data) is not dict or set(data) != {"schema", "head_sha", "max_parallel", "tasks"}:
        raise ValueError("invalid plan structure")
    if data["schema"] != SCHEMA or type(data["head_sha"]) is not str or not SHA40.fullmatch(data["head_sha"]):
        raise ValueError("invalid plan identity")
    limit = data["max_parallel"]
    if type(limit) is not int or not 1 <= limit <= 4:
        raise ValueError("invalid parallel limit")
    tasks = data["tasks"]
    if type(tasks) is not list or not 1 <= len(tasks) <= 16:
        raise ValueError("invalid task list")
    by_key = {}
    for task in tasks:
        if type(task) is not dict or set(task) != {"key", "base_sha", "state", "deps", "paths", "evidence_sha"}:
            raise ValueError("invalid task structure")
        key = task["key"]
        if type(key) is not str or not IDENT.fullmatch(key) or key in by_key:
            raise ValueError("duplicate or invalid task key")
        if type(task["base_sha"]) is not str or not SHA40.fullmatch(task["base_sha"]):
            raise ValueError("invalid task sha")
        if task["base_sha"] != data["head_sha"]:
            raise ValueError("stale base sha")
        if type(task["state"]) is not str or task["state"] not in STATES:
            raise ValueError("invalid task state")
        deps = task["deps"]
        paths = task["paths"]
        if type(deps) is not list or len(deps) > 16 or any(type(x) is not str or not IDENT.fullmatch(x) for x in deps):
            raise ValueError("invalid dependencies")
        if len(deps) != len(set(deps)):
            raise ValueError("repeated dependency")
        if type(paths) is not list or not 1 <= len(paths) <= 16:
            raise ValueError("invalid paths")
        if any(type(x) is not str or not PATH.fullmatch(x) or x in (".", "..")
               or ".." in x.split("/") for x in paths) or len(set(paths)) != len(paths):
            raise ValueError("unsafe or duplicate path")
        proof = task["evidence_sha"]
        if task["state"] == "passed":
            if type(proof) is not str or not SHA64.fullmatch(proof):
                raise ValueError("passed state lacks evidence digest")
        elif proof is not None:
            raise ValueError("nonpassed state supplied success evidence")
        by_key[key] = task

    for task in tasks:
        if task["key"] in task["deps"] or any(d not in by_key for d in task["deps"]):
            raise ValueError("invalid dependency reference")
    visited, active = set(), set()
    def visit(key):
        if key in active:
            raise ValueError("dependency cycle")
        if key in visited:
            return
        active.add(key)
        for dep in by_key[key]["deps"]:
            visit(dep)
        active.remove(key)
        visited.add(key)
    for key in by_key:
        visit(key)

    occupied = {p for t in tasks if t["state"] == "running" for p in t["paths"]}
    selected = []
    for task in tasks:
        if len(selected) >= limit:
            break
        if task["state"] != "pending" or any(by_key[d]["state"] != "passed" for d in task["deps"]):
            continue
        if occupied.intersection(task["paths"]):
            continue
        selected.append(task["key"])
        occupied.update(task["paths"])
    return {
        "schema": "p3l-hydra-fast-lane-proposal-v1",
        "head_sha": data["head_sha"],
        "input_sha256": _digest(data),
        "eligible": selected,
        "task_count": len(tasks),
        "model_calls": 0,
        "model_code_executed": False,
        "ci_attested": False,
        "lease_acquired": False,
        "merge_authorized": False,
        "promotion_authorized": False,
    }


def _load(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64_000:
        raise ValueError("unsafe plan/receipt file")
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if bool(args.out) == bool(args.verify):
        parser.error("select one of --out or --verify")
    try:
        result = select_lanes(_load(args.plan))
        if args.verify:
            if _load(args.verify) != result:
                raise ValueError("stale or forged lane receipt")
            print("PASS: same-SHA read-only lane receipt; no execution credit")
        else:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            print("Read-only eligible lanes:", result["eligible"])
        return 0
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        print("BLOCK:", str(exc)[:160])
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
