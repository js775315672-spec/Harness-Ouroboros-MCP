#!/usr/bin/env python3
"""Capture actual command-phase duration from a worker runner.

The JSONL is *candidate-generated telemetry*, not cryptographic attestation.
Never use it alone to authorize training, CI acceptance, or model promotion.
"""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

PHASES = {"whole_cycle", "model_call", "independent_verification", "operational_followup"}
HEX40 = re.compile(r"^[0-9a-f]{40}$")


def utc_now():
    return datetime.now(timezone.utc).isoformat()



def open_secure_trace(path):
    """Walk every parent through pinned directory FDs, never follow symlinks.

    Relative paths are rooted in the current directory FD. The final file is
    opened relative to the pinned parent, so renaming a parent cannot redirect
    the write through an attacker-controlled replacement path.
    """
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory is None or not hasattr(os, "supports_dir_fd") or os.open not in os.supports_dir_fd:
        raise OSError("secure trace output requires O_NOFOLLOW, O_DIRECTORY and dir_fd")
    raw = os.fspath(path)
    if not isinstance(raw, (str, bytes)) or not raw:
        raise ValueError("nonempty trace path required")
    parts = Path(raw).parts
    if ".." in parts:
        raise ValueError("parent traversal is forbidden")
    basename = Path(raw).name
    if basename in ("", ".", ".."):
        raise ValueError("regular filename required")
    root = "/" if os.path.isabs(raw) else "."
    fd = os.open(root, os.O_RDONLY | directory | nofollow | getattr(os, "O_CLOEXEC", 0))
    try:
        parents = parts[1:-1] if os.path.isabs(raw) else parts[:-1]
        for part in parents:
            if part in ("", "."):
                continue
            child = os.open(part, os.O_RDONLY | directory | nofollow |
                            getattr(os, "O_CLOEXEC", 0), dir_fd=fd)
            os.close(fd)
            fd = child
        return os.open(basename, os.O_WRONLY | os.O_APPEND | os.O_CREAT |
                       nofollow | getattr(os, "O_CLOEXEC", 0), 0o600, dir_fd=fd)
    finally:
        os.close(fd)


def run_timed(phase, command, output, *, sha=None, run_id=None):
    if phase not in PHASES:
        raise ValueError("unknown telemetry phase")
    if not isinstance(command, (list, tuple)) or not command:
        raise ValueError("one command required")
    if sha is not None and (not isinstance(sha, str) or not HEX40.fullmatch(sha)):
        raise ValueError("commit SHA must be exact 40 lowercase hexadecimal characters")
    if run_id is not None and (type(run_id) is not int or run_id <= 0):
        raise ValueError("positive run ID required")
    began = utc_now()
    start = time.monotonic_ns()
    try:
        proc = subprocess.run(command, check=False)
        code = proc.returncode
    except OSError:
        code = 127
    duration = (time.monotonic_ns() - start) / 1_000_000_000
    ended = utc_now()
    row = {
        "schema_version": 1,
        "source": "runner_monotonic_unattested",
        "phase": phase, "start_utc": began, "end_utc": ended,
        "duration_seconds": duration,
        "returncode": code, "sha": sha, "actions_run_id": run_id,
        "verified_independent": False,
    }
    target = Path(output)
    # Append a single small JSONL record; no subprocess command, tokens, or env.
    payload = (json.dumps(row, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    descriptor = open_secure_trace(target)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise OSError("trace output must be a regular file")
        if info.st_mode & 0o077:
            raise PermissionError("trace output must not be accessible by group/others")
        # Small fixed-size record; write fully even if interrupted/short.
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short trace write")
            view = view[written:]
    finally:
        os.close(descriptor)
    return code


def summarize(rows, sha=None, run_id=None):
    if not isinstance(rows, list):
        raise ValueError("list of phase records required")
    values = {phase: [] for phase in PHASES}
    for row in rows:
        if not isinstance(row, dict) or row.get("schema_version") != 1:
            raise ValueError("invalid phase record")
        if row.get("source") != "runner_monotonic_unattested":
            raise ValueError("unknown phase source")
        if sha is not None and row.get("sha") != sha:
            raise ValueError("commit mismatch")
        if run_id is not None and row.get("actions_run_id") != run_id:
            raise ValueError("Actions run mismatch")
        if row.get("phase") not in PHASES:
            raise ValueError("unknown phase")
        v = row.get("duration_seconds")
        if type(v) not in (int, float) or not math.isfinite(v) or v < 0:
            raise ValueError("invalid measured phase time")
        if type(row.get("returncode")) is not int:
            raise ValueError("missing returncode")
        if row["returncode"] != 0:
            continue  # failed attempts remain in raw log; not silently successful
        values[row["phase"]].append(v)
    return {
        "source": "runner_monotonic_unattested",
        "spans_seconds": {phase: sum(nums) if nums else None for phase, nums in sorted(values.items())},
        "sample_counts": {phase: len(nums) for phase, nums in sorted(values.items())},
        "independently_attested": False,
        "note": "Phase duration is measured only if worker commands are wrapped. Historical missing spans remain null.",
    }


def main():
    p = argparse.ArgumentParser()
    subs = p.add_subparsers(dest="operation", required=True)
    measure = subs.add_parser("measure")
    measure.add_argument("--phase", choices=sorted(PHASES), required=True)
    measure.add_argument("--output", required=True)
    measure.add_argument("--sha", default=os.getenv("GITHUB_SHA"))
    measure.add_argument("--run-id", type=int, default=int(os.environ["GITHUB_RUN_ID"])
                         if os.getenv("GITHUB_RUN_ID", "").isdigit() else None)
    measure.add_argument("command", nargs=argparse.REMAINDER)
    audit = subs.add_parser("summarize")
    audit.add_argument("input")
    audit.add_argument("--sha")
    audit.add_argument("--run-id", type=int)
    args = p.parse_args()
    if args.operation == "measure":
        command = args.command[1:] if args.command and args.command[0] == "--" else args.command
        return run_timed(args.phase, command, args.output, sha=args.sha, run_id=args.run_id)
    rows = [json.loads(line) for line in Path(args.input).read_text(encoding="utf-8").splitlines() if line.strip()]
    print(json.dumps(summarize(rows, sha=args.sha, run_id=args.run_id), ensure_ascii=False,
                     sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
