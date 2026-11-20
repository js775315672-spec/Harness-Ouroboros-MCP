#!/usr/bin/env python3
"""Read a committed ORIL train/report pair into immutable bytes, fail closed.

Consumer must train on the returned bytes, NEVER re-open a pathname after
verification. This is not independent provenance or GPU/LoRA attestation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

from oril_v2_distill_pair_marker import SCHEMA, MAX_FILE, paths

MAX_MARKER = 4096


def _strict_json(raw):
    def unique(pairs):
        result = {}
        for k, value in pairs:
            if k in result:
                raise ValueError("duplicate JSON key")
            result[k] = value
        return result
    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda x: (_ for _ in ()).throw(
                          ValueError("nonfinite JSON constant")))


def _read_pinned(path, limit, *, before_read=None):
    """Open once with no-follow; validate the same descriptor before/after read."""
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if path.is_symlink():
        raise ValueError("symlink path forbidden")
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ValueError("unsafe file type or size")
        if before_read is not None:
            before_read(path)
        # This is intentionally the only read from the opened descriptor.
        with os.fdopen(fd, "rb", closefd=False) as file:
            data = file.read(limit + 1)
        after = os.fstat(fd)
        if len(data) > limit or len(data) != before.st_size:
            raise ValueError("file size changed during snapshot")
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size,
                                      after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError("file changed during snapshot")
        # Ensure the opened object still occupies the expected pathname.
        at_path = os.stat(path, follow_symlinks=False)
        if (at_path.st_dev, at_path.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError("path replaced during snapshot")
        return data
    finally:
        os.close(fd)


def consume(train, report, marker, *, before_read=None):
    """Return verified immutable (train_bytes, report_bytes), not file paths.

    before_read is test-only deterministic fault injection, never needed by
    production consumers. The caller must use these exact bytes and not reopen.
    """
    train, report, marker = paths(train, report, marker)
    marker_raw = _read_pinned(marker, MAX_MARKER)
    metadata = _strict_json(marker_raw)
    if (not isinstance(metadata, dict) or set(metadata) != {
            "schema", "train", "report", "independent_evaluation",
            "student_weights_updated"} or metadata["schema"] != SCHEMA or
            metadata["independent_evaluation"] is not False or
            metadata["student_weights_updated"] is not False):
        raise ValueError("invalid marker schema")
    for key, path in (("train", train), ("report", report)):
        item = metadata[key]
        if (not isinstance(item, dict) or set(item) != {"name", "sha256", "bytes"}
                or item["name"] != path.name or
                type(item["bytes"]) is not int or not 0 <= item["bytes"] <= MAX_FILE
                or not isinstance(item["sha256"], str) or
                len(item["sha256"]) != 64 or
                any(c not in "0123456789abcdef" for c in item["sha256"])):
            raise ValueError("invalid marker entry")
    # Snapshot each file into memory once; verification uses only these bytes.
    train_bytes = _read_pinned(train, MAX_FILE, before_read=before_read)
    report_bytes = _read_pinned(report, MAX_FILE)
    for key, raw in (("train", train_bytes), ("report", report_bytes)):
        if (len(raw) != metadata[key]["bytes"] or
                hashlib.sha256(raw).hexdigest() != metadata[key]["sha256"]):
            raise ValueError("committed pair digest mismatch")
    # Validate report contents but do not claim an external review occurred.
    report_data = _strict_json(report_bytes)
    if (not isinstance(report_data, dict) or
            report_data.get("student_weights_updated") is not False or
            report_data.get("heldout_evaluation_performed") is not False):
        raise ValueError("report cannot assert trained or evaluated student")
    # Strict student training schema: integrity alone does not make an
    # attacker-controlled training row safe. Reject role injection, hidden
    # evaluation rows, unexpected fields and ambiguous empty conversations.
    if not train_bytes.strip():
        raise ValueError("empty train export")
    seen_cases = set()
    for line in train_bytes.splitlines():
        if not line.strip():
            raise ValueError("blank train row")
        row = _strict_json(line)
        if not isinstance(row, dict) or not {"messages"} <= set(row) or (
                set(row) - {"messages", "metadata"}):
            raise ValueError("invalid train row")
        messages = row["messages"]
        if (not isinstance(messages, list) or len(messages) != 2 or
                any(not isinstance(msg, dict) or set(msg) != {"role", "content"}
                    for msg in messages) or
                [msg["role"] for msg in messages] != ["user", "assistant"] or
                any(not isinstance(msg["content"], str) or
                    not msg["content"].strip() or
                    len(msg["content"]) > 4000 or
                    "\x00" in msg["content"] for msg in messages)):
            raise ValueError("invalid student conversation")
        if "metadata" in row:
            metadata = row["metadata"]
            required = {"case_id", "group_id", "task_type",
                        "review_assertion_url", "candidate_sha",
                        "quality_assertion"}
            if not isinstance(metadata, dict) or set(metadata) != required:
                raise ValueError("invalid student metadata")
            for key in ("case_id", "group_id", "task_type",
                        "review_assertion_url", "candidate_sha"):
                if not isinstance(metadata[key], str) or not metadata[key]:
                    raise ValueError("invalid student metadata")
            case_id = metadata["case_id"]
            if case_id in seen_cases:
                raise ValueError("duplicate student case")
            seen_cases.add(case_id)
            quality = metadata["quality_assertion"]
            if (type(quality) not in (float, int) or
                    not 0 <= quality <= 1):
                raise ValueError("invalid student quality")
    return train_bytes, report_bytes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--marker", required=True)
    args = parser.parse_args()
    training, report = consume(args.train, args.report, args.marker)
    print(json.dumps({"ok": True, "train_sha256": hashlib.sha256(training).hexdigest(),
                      "report_sha256": hashlib.sha256(report).hexdigest(),
                      "training_bytes": len(training), "model_trained": False},
                     sort_keys=True))


if __name__ == "__main__":
    main()
