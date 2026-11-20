#!/usr/bin/env python3
"""Publish/verify an ORIL distillation pair commit marker.

A marker is an integrity/complete-write signal for a trusted local producer,
NOT proof of teacher provenance, GPU learning, or external evaluation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

SCHEMA = "oril-distill-pair-v1"
MAX_FILE = 20 * 1024 * 1024


def safe_file(path):
    p = Path(path)
    if p.is_symlink():
        raise ValueError("symlink input forbidden")
    if not p.is_file():
        raise ValueError("regular file required")
    if p.stat().st_size > MAX_FILE:
        raise ValueError("oversized file")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(p, flags)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_FILE:
            raise ValueError("unsafe file type")
        if (st.st_dev, st.st_ino) != (os.stat(p, follow_symlinks=False).st_dev,
                                     os.stat(p, follow_symlinks=False).st_ino):
            raise ValueError("file changed while opening")
        with os.fdopen(fd, "rb", closefd=False) as f:
            data = f.read(MAX_FILE + 1)
        if len(data) > MAX_FILE:
            raise ValueError("oversized file")
        return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    finally:
        os.close(fd)


def paths(train, report, marker):
    p = [Path(x).absolute() for x in (train, report, marker)]
    if len({str(x) for x in p}) != 3:
        raise ValueError("distinct paths required")
    if len({str(x.parent) for x in p}) != 1:
        raise ValueError("pair and marker must share one directory")
    if p[0].parent.is_symlink():
        raise ValueError("symlink directory forbidden")
    return p


def payload(train, report):
    return {"schema": SCHEMA,
            "train": {"name": train.name, **safe_file(train)},
            "report": {"name": report.name, **safe_file(report)},
            "independent_evaluation": False,
            "student_weights_updated": False}


def publish(train, report, marker):
    train, report, marker = paths(train, report, marker)
    if marker.exists() or marker.is_symlink():
        raise FileExistsError("marker already exists")
    data = payload(train, report)
    serialized = (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(marker, flags, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as f:
            f.write(serialized)
            f.flush()
            os.fsync(f.fileno())
    finally:
        os.close(fd)
    # The marker is published only after both output files exist and were hashed.
    # No claim of fully atomic multi-file writes, durable directory fsync, or
    # concurrent-writer safety. Re-verification is required before consumption.
    return data


def verify(train, report, marker):
    train, report, marker = paths(train, report, marker)
    marker_info = safe_file(marker)
    if marker_info["bytes"] > 4096:
        raise ValueError("oversized marker")
    raw = marker.read_bytes()
    def unique(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise ValueError("duplicate marker key")
            out[k] = v
        return out
    data = json.loads(raw, object_pairs_hook=unique)
    if data != payload(train, report):
        raise ValueError("pair integrity mismatch")
    return data


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("publish", "verify"))
    p.add_argument("--train", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--marker", required=True)
    a = p.parse_args()
    data = (publish if a.action == "publish" else verify)(
        a.train, a.report, a.marker)
    print(json.dumps({"ok": True, "schema": data["schema"],
                      "train_sha256": data["train"]["sha256"],
                      "report_sha256": data["report"]["sha256"]},
                     sort_keys=True))


if __name__ == "__main__":
    main()
