"""Deterministic, offline ORIL dataset manifest fingerprint and pin verification.

This verifies exact manifest bytes *semantically* through canonical JSON; it does
not prove who created the manifest or that claimed sample hashes match raw data.
It never authorizes model training, evaluation, or promotion.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("nonfinite JSON number: " + value)


def load_manifest(path):
    return json.loads(Path(path).read_text(encoding="utf-8"),
                      object_pairs_hook=reject_duplicate_keys,
                      parse_constant=reject_constant)


def fingerprint(manifest, expected_sha256):
    if not isinstance(manifest, dict) or not isinstance(expected_sha256, str) or DIGEST.fullmatch(expected_sha256) is None:
        raise ValueError("manifest object and pinned lowercase SHA-256 required")
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False).encode("utf-8")
    actual = hashlib.sha256(canonical).hexdigest()
    return {
        "manifest_sha256": actual,
        "expected_sha256": expected_sha256,
        "pin_matches": actual == expected_sha256,
        "provenance_verified": False,
        "raw_sample_hashes_verified": False,
        "training_approved": False,
        "promotion_approved": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    result = fingerprint(load_manifest(args.manifest), args.expected_sha256)
    print(json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False))
    if not result["pin_matches"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
