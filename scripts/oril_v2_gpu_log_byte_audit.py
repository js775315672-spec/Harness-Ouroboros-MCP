#!/usr/bin/env python3
"""Offline GPU log byte-presence gate; candidate logs never prove real GPU use.

Experimental additive check on top of the existing training evidence audit.
No approvals, GPU attestation or independent evaluation are granted.
"""
import argparse
import hashlib
import json
import pathlib
import sys

try:
    from scripts.oril_v2_training_evidence_audit import check, strict_load
except ModuleNotFoundError:
    from oril_v2_training_evidence_audit import check, strict_load


def check_log_bytes(root, evidence_path, log_relative_path):
    result = {
        "evidence_consistent": False, "artifact_verified": False,
        "log_bytes_verified": False, "gpu_execution_attested": False,
        "independent_evaluation_verified": False, "intelligence_improved": False,
        "training_approved": False, "promotion_approved": False,
    }
    try:
        parent = check(root, evidence_path)
        result["artifact_verified"] = bool(parent["artifact_verified"])
        if not parent["evidence_consistent"]:
            raise ValueError("parent evidence rejected: " + parent["reason"])
        if not isinstance(log_relative_path, str) or not log_relative_path:
            raise ValueError("log path required")
        path = pathlib.PurePosixPath(log_relative_path)
        if path.is_absolute() or ".." in path.parts or "\\" in log_relative_path or path.parts == (".",):
            raise ValueError("unsafe log path")
        root = pathlib.Path(root).resolve(strict=True)
        target = root / path
        if target.is_symlink() or not target.is_file() or not target.resolve().is_relative_to(root):
            raise ValueError("log absent, symlink or outside root")
        doc = strict_load(evidence_path)
        expected = doc["gpu"]["log_sha256"]
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError("GPU log digest mismatch")
        result["log_bytes_verified"] = True
        result["evidence_consistent"] = True
        result["reason"] = "candidate log bytes match claimed digest; no trusted GPU attestation"
    except (OSError, ValueError, TypeError, UnicodeError, OverflowError, KeyError) as exc:
        result["reason"] = str(exc)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True)
    p.add_argument("--evidence", required=True)
    p.add_argument("--log-path", required=True)
    a = p.parse_args()
    result = check_log_bytes(a.root, a.evidence, a.log_path)
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0 if result["evidence_consistent"] else 1


if __name__ == "__main__":
    sys.exit(main())
