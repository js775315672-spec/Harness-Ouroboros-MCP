#!/usr/bin/env python3
"""Offline fail-closed manifest pin boundary check. NOT a provenance authenticator."""
import argparse
import hashlib
import json
import re
from pathlib import Path

HEX = re.compile(r"[0-9a-f]{64}\Z")

def no_duplicates(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key")
        out[key] = value
    return out

def reject_constant(value):
    raise ValueError("nonfinite JSON constant: " + value)

def verify(manifest_path, anchor_path, dataset_root):
    manifest = Path(manifest_path).resolve(strict=True)
    anchor = Path(anchor_path).resolve(strict=True)
    root = Path(dataset_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("dataset root must be directory")
    if anchor == manifest or anchor == root or root in anchor.parents:
        raise ValueError("anchor must be outside dataset root")
    if manifest != root and root not in manifest.parents:
        raise ValueError("manifest must be inside dataset root")
    if not manifest.is_file() or not anchor.is_file():
        raise ValueError("regular files required")
    expected = anchor.read_text(encoding="ascii").strip()
    if not HEX.fullmatch(expected):
        raise ValueError("invalid pinned SHA256")
    raw = manifest.read_bytes()
    obj = json.loads(raw, object_pairs_hook=no_duplicates, parse_constant=reject_constant)
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    actual = hashlib.sha256(canonical).hexdigest()
    if actual != expected:
        raise ValueError("manifest pin mismatch")
    return {"integrity_pass": True, "provenance_verified": False,
            "training_approved": False, "promotion_approved": False, "manifest_sha256": actual}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--anchor", required=True)
    parser.add_argument("--dataset-root", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.manifest, args.anchor, args.dataset_root), sort_keys=True))
    except (OSError, ValueError, UnicodeError, TypeError) as exc:
        print(json.dumps({"integrity_pass": False, "provenance_verified": False,
                          "training_approved": False, "promotion_approved": False,
                          "error": str(exc)}))
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
