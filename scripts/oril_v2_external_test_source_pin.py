#!/usr/bin/env python3
"""Experimental fail-closed verifier for an externally pinned test source digest.

The SHA-256 must be provided by an independently controlled reviewer.
A digest computed from the candidate branch is NOT an independent trust root.
This module does not authorize training, merging or deployment.
"""
import argparse
import hashlib
import json
import pathlib
import re
import sys

HEX = re.compile(r"[0-9a-f]{64}\Z")
TARGET = "tests/test_oril_v2_signed_ledger_boundary.py"


def verify(root, trusted_sha256):
    result = {"test_source_integrity_pass": False, "independent_authority_verified": False,
              "training_approved": False, "promotion_approved": False}
    try:
        if not isinstance(trusted_sha256, str) or not HEX.fullmatch(trusted_sha256):
            raise ValueError("missing or invalid external SHA-256")
        root = pathlib.Path(root).resolve(strict=True)
        candidate = root / TARGET
        if candidate.is_symlink() or not candidate.is_file():
            raise ValueError("test source missing or symlink")
        raw = candidate.read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if actual != trusted_sha256:
            raise ValueError("test source SHA-256 differs from independent pin")
        result["test_source_integrity_pass"] = True
        result["reason"] = "source matches supplied digest; independent pin authority NOT authenticated"
    except (OSError, ValueError, TypeError) as exc:
        result["reason"] = str(exc)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True)
    p.add_argument("--trusted-sha256", required=True,
                   help="Must come from an independent reviewer, not this candidate branch")
    a = p.parse_args()
    result = verify(a.root, a.trusted_sha256)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["test_source_integrity_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
