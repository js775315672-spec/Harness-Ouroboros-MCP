#!/usr/bin/env python3
"""Experimental path-component audit: reject symlinked parent directories.

The older evidence checks reject symlinks at the final file but may accept a
symlinked ancestor that resolves inside the root. This additional fail-closed
gate does not attest GPU execution or approve model promotion.
"""
import argparse
import json
import pathlib
import sys

try:
    from scripts.oril_v2_gpu_log_byte_audit import check_log_bytes
    from scripts.oril_v2_training_evidence_audit import strict_load
except ModuleNotFoundError:
    from oril_v2_gpu_log_byte_audit import check_log_bytes
    from oril_v2_training_evidence_audit import strict_load


def safe_components(root, relative):
    if type(relative) is not str or not relative or "\\" in relative:
        raise ValueError("unsafe evidence path")
    p = pathlib.PurePosixPath(relative)
    if p.is_absolute() or any(part in ("..", "") for part in p.parts) or relative in (".", "./"):
        raise ValueError("unsafe evidence path")
    root = pathlib.Path(root).resolve(strict=True)
    current = root
    for part in p.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("symlink in evidence path component")
    if not current.is_file() or not current.resolve(strict=True).is_relative_to(root):
        raise ValueError("evidence file missing or outside root")
    return current


def check_components(root, evidence_path, log_relative_path):
    result = {"evidence_consistent": False, "path_components_verified": False,
              "gpu_execution_attested": False, "independent_evaluation_verified": False,
              "intelligence_improved": False, "training_approved": False,
              "promotion_approved": False}
    try:
        doc = strict_load(evidence_path)
        safe_components(root, doc["adapter"]["path"])
        safe_components(root, log_relative_path)
        parent = check_log_bytes(root, evidence_path, log_relative_path)
        if not parent["evidence_consistent"]:
            raise ValueError("underlying evidence check rejected: " + parent["reason"])
        result["path_components_verified"] = True
        result["evidence_consistent"] = True
        result["reason"] = "path components and candidate hashes match; no trusted attestation"
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        result["reason"] = str(exc)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True)
    p.add_argument("--evidence", required=True)
    p.add_argument("--log-path", required=True)
    a = p.parse_args()
    out = check_components(a.root, a.evidence, a.log_path)
    print(json.dumps(out, sort_keys=True))
    return 0 if out["evidence_consistent"] else 1


if __name__ == "__main__":
    sys.exit(main())
