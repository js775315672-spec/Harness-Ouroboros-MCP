#!/usr/bin/env python3
"""Fail-closed, resumable development queue for independently attested CI tasks.

No model, shell, Git writes, deployments, secrets, paid API, or PR merges.
Each successful task needs a distinct commit and a completed GitHub CI run.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import urllib.error
import urllib.request

from autonomous_loop_controller import transition, MAX_ATTEMPTS, MAX_CYCLES
from ci_attestation import verify_record

SHA = re.compile(r"[0-9a-f]{40}\Z")
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
TASK = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}\Z")
MAX_FILE_BYTES = 262_144
MAX_TASKS = MAX_CYCLES
KEYS = {"schema", "repo", "base_commit", "last_commit", "tasks", "index",
        "controller", "events", "generation", "integrity",
        "requires_human_merge_approval"}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def fingerprint(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def seal(payload):
    record = dict(payload)
    record["integrity"] = fingerprint(payload)
    return record


def validate(record):
    if not isinstance(record, dict) or set(record) != KEYS:
        raise ValueError("unexpected checkpoint structure")
    digest = record.get("integrity")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("invalid checkpoint digest")
    if fingerprint({k: v for k, v in record.items() if k != "integrity"}) != digest:
        raise ValueError("checkpoint integrity mismatch")
    if type(record["schema"]) is not int or record["schema"] != 1:
        raise ValueError("unknown checkpoint version")
    if not isinstance(record["repo"], str) or not REPO.fullmatch(record["repo"]):
        raise ValueError("invalid repository")
    for key in ("base_commit", "last_commit"):
        if not isinstance(record[key], str) or not SHA.fullmatch(record[key]):
            raise ValueError("invalid commit binding")
    if record["requires_human_merge_approval"] is not True:
        raise ValueError("merge approval must remain mandatory")
    tasks = record["tasks"]
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= MAX_TASKS:
        raise ValueError("bounded nonempty task list required")
    ids = set()
    for task in tasks:
        if not isinstance(task, dict) or set(task) != {"id", "description"}:
            raise ValueError("invalid task schema")
        ident, desc = task["id"], task["description"]
        if not isinstance(ident, str) or not TASK.fullmatch(ident) or ident in ids:
            raise ValueError("invalid or duplicate task identifier")
        if not isinstance(desc, str) or not 1 <= len(desc.strip()) <= 240 or "\x00" in desc:
            raise ValueError("invalid task description")
        ids.add(ident)
    index, generation, events = record["index"], record["generation"], record["events"]
    if type(index) is not int or not 0 <= index <= len(tasks):
        raise ValueError("invalid task position")
    if type(generation) is not int or generation < 0 or not isinstance(events, list):
        raise ValueError("invalid history")
    if len(events) != generation or len(events) > MAX_TASKS * MAX_ATTEMPTS:
        raise ValueError("history length mismatch")
    seen_commits = set()
    passed = 0
    for seq, event in enumerate(events, 1):
        if not isinstance(event, dict) or set(event) != {"seq", "task_id", "commit", "decision", "attested", "evidence_digest"}:
            raise ValueError("invalid event schema")
        if type(event["seq"]) is not int or event["seq"] != seq:
            raise ValueError("nonsequential event")
        if event["task_id"] not in ids or not isinstance(event["commit"], str) or not SHA.fullmatch(event["commit"]):
            raise ValueError("invalid event binding")
        if event["commit"] in seen_commits or event["commit"] == record["base_commit"]:
            raise ValueError("reused commit evidence")
        seen_commits.add(event["commit"])
        if event["decision"] not in ("request_external_fix", "stop", "task_attested"):
            raise ValueError("invalid event decision")
        if type(event["attested"]) is not bool or event["attested"] != (event["decision"] == "task_attested"):
            raise ValueError("attestation/decision mismatch")
        if not isinstance(event["evidence_digest"], str) or not re.fullmatch(r"[0-9a-f]{64}", event["evidence_digest"]):
            raise ValueError("invalid evidence digest")
        if event["decision"] == "task_attested":
            if passed >= len(tasks) or event["task_id"] != tasks[passed]["id"]:
                raise ValueError("out-of-order completed task")
            passed += 1
    if passed != index:
        raise ValueError("task progress not supported by history")
    state = record["controller"]
    if not isinstance(state, dict) or set(state) != {"cycle", "attempt", "phase"}:
        raise ValueError("invalid controller")
    if type(state["cycle"]) is not int or state["cycle"] != (min(index, MAX_CYCLES) if index == len(tasks) else index + 1):
        raise ValueError("cycle and task position differ")
    if type(state["attempt"]) is not int or not 1 <= state["attempt"] <= MAX_ATTEMPTS:
        raise ValueError("invalid retry position")
    if state["phase"] not in ("await_evidence", "stopped"):
        raise ValueError("invalid controller phase")
    if index == len(tasks) and state["phase"] != "stopped":
        raise ValueError("completed queue must stop")
    if canonical(record).__len__() > MAX_FILE_BYTES:
        raise ValueError("checkpoint too large")
    return record


def new_queue(tasks, repo, commit):
    record = seal({"schema": 1, "repo": repo, "base_commit": commit,
                   "last_commit": commit, "tasks": tasks, "index": 0,
                   "controller": {"cycle": 1, "attempt": 1, "phase": "await_evidence"},
                   "events": [], "generation": 0,
                   "requires_human_merge_approval": True})
    return validate(record)


def next_action(record):
    validate(record)
    if record["controller"]["phase"] == "stopped":
        return {"decision": "human_review" if record["index"] == len(record["tasks"]) else "blocked_retry_budget", "task_id": None,
                "completed_tasks": record["index"], "autonomous_coding_connected": False,
                "merge_authorized": False}
    state = record["controller"]
    pending = transition(state)
    return {"decision": pending["decision"], "task_id": record["tasks"][record["index"]]["id"],
            "attempt": state["attempt"], "completed_tasks": record["index"],
            "autonomous_coding_connected": False, "merge_authorized": False}


def advance(record, evidence, fetch=None):
    validate(record)
    if record["controller"]["phase"] == "stopped":
        raise ValueError("stopped checkpoint cannot advance")
    if not isinstance(evidence, dict) or set(evidence) != {"task_id", "source_changed", "commit", "ci_url", "checks"}:
        raise ValueError("invalid evidence schema")
    task = record["tasks"][record["index"]]
    if evidence["task_id"] != task["id"]:
        raise ValueError("wrong task evidence")
    if evidence["commit"] in {record["base_commit"], *(x["commit"] for x in record["events"])}:
        raise ValueError("replayed or unchanged commit")
    if not isinstance(evidence["ci_url"], str) or not evidence["ci_url"].startswith(
            f'https://github.com/{record["repo"]}/actions/runs/'):
        raise ValueError("CI repository mismatch")
    decision = transition(record["controller"], {k: evidence[k] for k in
                      ("source_changed", "commit", "ci_url", "checks")})
    passed = decision["decision"] in ("request_next_external_task", "human_review")
    if passed:
        def strict_fetch(url):
            if fetch is None:
                req = urllib.request.Request(url, headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "AURA-resumable-readonly-attestor"})
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = json.load(response)
            else:
                data = fetch(url)
            if (not isinstance(data, dict) or data.get("name") != "Harness safety checks"
                    or data.get("path") != ".github/workflows/harness.yml"):
                raise ValueError("not the required Harness CI workflow")
            return data
        attested = verify_record({"cycle": record["index"] + 1,
                                  "commit": evidence["commit"],
                                  "ci_url": evidence["ci_url"]}, fetch=strict_fetch)
        if attested.get("verified") is not True:
            raise ValueError("external attestation missing")
    event = {"seq": record["generation"] + 1, "task_id": task["id"],
             "commit": evidence["commit"], "decision": "task_attested" if passed else decision["decision"],
             "attested": passed, "evidence_digest": fingerprint(evidence)}
    payload = {k: v for k, v in record.items() if k != "integrity"}
    payload["events"] = record["events"] + [event]
    payload["generation"] += 1
    if passed:
        payload["index"] += 1
        payload["last_commit"] = evidence["commit"]
        if payload["index"] == len(payload["tasks"]):
            payload["controller"] = {"cycle": min(payload["index"], MAX_CYCLES),
                                      "attempt": 1, "phase": "stopped"}
        else:
            payload["controller"] = {"cycle": payload["index"] + 1,
                                      "attempt": 1, "phase": "await_evidence"}
    else:
        payload["controller"] = decision["state"]
    return validate(seal(payload))


def load(path):
    path = Path(path).absolute()
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("unsafe checkpoint file")
    return validate(json.loads(path.read_text(encoding="utf-8")))


def save(path, record, expected_integrity=None):
    validate(record)
    path = Path(path).absolute()
    if path.is_symlink():
        raise ValueError("symlink checkpoint forbidden")
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + ".lock")
    lock_fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        if expected_integrity is None:
            if path.exists():
                raise ValueError("refusing to replace existing checkpoint")
        elif load(path)["integrity"] != expected_integrity:
            raise ValueError("stale checkpoint generation")
        fd, temp = tempfile.mkstemp(prefix=".queue-", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(record, stream, sort_keys=True, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
    finally:
        os.close(lock_fd)
        os.unlink(lock)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("init", "inspect", "advance"))
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--tasks", type=Path)
    parser.add_argument("--repo")
    parser.add_argument("--commit")
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "init":
            if args.tasks is None or args.repo is None or args.commit is None:
                raise ValueError("tasks, repo, commit required")
            if args.tasks.stat().st_size > 20_000:
                raise ValueError("task input too large")
            record = new_queue(json.loads(args.tasks.read_text(encoding="utf-8")),
                               args.repo, args.commit)
            save(args.checkpoint, record)
        elif args.command == "inspect":
            record = load(args.checkpoint)
        else:
            if args.evidence is None or args.evidence.stat().st_size > 20_000:
                raise ValueError("bounded evidence file required")
            before = load(args.checkpoint)
            record = advance(before, json.loads(args.evidence.read_text(encoding="utf-8")))
            save(args.checkpoint, record, expected_integrity=before["integrity"])
        print(json.dumps(next_action(record), sort_keys=True, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError, UnicodeError,
            urllib.error.URLError) as exc:
        print(json.dumps({"decision": "blocked", "reason": type(exc).__name__}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
