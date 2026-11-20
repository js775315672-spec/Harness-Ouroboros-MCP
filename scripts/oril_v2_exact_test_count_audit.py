#!/usr/bin/env python3
"""Strict offline regression runner: exact test totals, no skipped cases, one candidate SHA.

This is an additive audit; it does not authorize dataset provenance or training.
"""
import pathlib
import re
import subprocess
import sys

SUITES = (
    ("test_oril_v2_dataset_split_audit.py", 14),
    ("test_oril_v2_dataset_manifest_attestation.py", 12),
    ("test_oril_v2_raw_sample_integrity.py", 18),
    ("test_oril_v2_dataset_contract_bridge.py", 15),
    ("test_oril_v2_dataset_contract_cli.py", 5),
    ("test_oril_v2_dataset_frozen_pin.py", 4),
    ("test_oril_v2_external_pin_boundary.py", 8),
    ("test_oril_v2_signed_ledger_boundary.py", 10),
    ("test_oril_v2_anchored_ledger_boundary.py", 14),
)
SUMMARY = re.compile(r"^Ran ([0-9]+) tests? in ([0-9]+(?:\\.[0-9]+)?)s$", re.MULTILINE)


def check_result(output, returncode, expected):
    """Fail closed on missing/duplicate summaries, skips, or wrong test totals."""
    if returncode != 0:
        raise ValueError("nonzero unittest exit status")
    summaries = SUMMARY.findall(output)
    if len(summaries) != 1:
        raise ValueError("missing or ambiguous unittest summary")
    count = int(summaries[0][0])
    if count != expected:
        raise ValueError(f"test count drift: expected {expected}, got {count}")
    if re.search(r"(?im)^\\s*.*\\.\\.\\. skipped", output) or re.search(r"(?i)skipped\\s*=\\s*[0-9]+", output):
        raise ValueError("skipped test detected")
    if not re.search(r"(?m)^OK\\s*$", output):
        raise ValueError("missing final OK")
    if re.search(r"(?m)^(?:FAILED|ERROR|FAIL):", output):
        raise ValueError("failure marker in test output")
    return count


def run(root):
    total = 0
    for filename, expected in SUITES:
        path = root / "tests" / filename
        if not path.is_file():
            raise ValueError(f"missing test module: {filename}")
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", str(root / "tests"),
             "-p", filename, "-v"],
            capture_output=True, text=True, timeout=120, cwd=root,
        )
        output = completed.stdout + completed.stderr
        print(f"SUITE {filename} EXPECTED {expected}", flush=True)
        print(output, flush=True)
        total += check_result(output, completed.returncode, expected)
    if total != 100:
        raise ValueError(f"unexpected total: {total}")
    print(f"EXACT_INTEGRATED_TOTAL={total} SKIPPED=0", flush=True)
    return total


if __name__ == "__main__":
    try:
        run(pathlib.Path(__file__).resolve().parents[1])
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"INTEGRATION AUDIT FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
