#!/usr/bin/env python3
"""Read-only W01 contract drift probe. Coordinator-authored, NOT model output.

Checks existing validate(records) against proposed W01 rules without editing it.
A green probe run does NOT mean W01 is accepted or the 25 fixed checks passed.
"""
import argparse
import copy
import json
import pathlib
import sys

from development_ledger import validate


def valid_record():
    return {
        "cycle": 1, "commit": "a" * 40, "change": "tested change",
        "checks": {k: "pass" for k in ("harness", "ouroboros", "regression", "secrets")},
        "fixes": [], "ci_url": "https://github.com/org/repo/actions/runs/123",
    }


def cases():
    """Expected decisions from W01 proposed contract, NOT existing implementation."""
    variants = [
        ("empty_fixes_valid", {}, True),
        ("one_fix_valid", {"fixes": ["fixed"]}, True),
        ("empty_fix_rejected", {"fixes": [""]}, False),
        ("twelve_fixes_valid", {"fixes": ["x"] * 12}, True),
        ("thirteen_fixes_rejected", {"fixes": ["x"] * 13}, False),
        ("fix_128_bytes_valid", {"fixes": ["x" * 128]}, True),
        ("fix_129_bytes_rejected", {"fixes": ["x" * 129]}, False),
        ("hangul_126_bytes_valid", {"fixes": ["가" * 42]}, True),
        ("hangul_129_bytes_rejected", {"fixes": ["가" * 43]}, False),
        ("change_256_bytes_valid", {"change": "x" * 256}, True),
        ("change_257_bytes_rejected", {"change": "x" * 257}, False),
        ("change_hangul_255_valid", {"change": "가" * 85}, True),
        ("change_hangul_258_rejected", {"change": "가" * 86}, False),
    ]
    for field in ("fixes", "change"):
        for name, char in (("nul", "\x00"), ("lf", "\n"), ("esc", "\x1b")):
            value = ["ok" + char] if field == "fixes" else "ok" + char
            variants.append((field + "_" + name + "_rejected", {field: value}, False))
    # Whitespace-only policy remains undecided; do not silently assert a new rule.
    for name, changes, expected in variants:
        record = valid_record()
        record.update(changes)
        yield name, record, expected


def audit(validator=validate):
    rows = []
    for name, record, expected in cases():
        supplied = copy.deepcopy(record)
        before = copy.deepcopy(supplied)
        try:
            verdict = validator([supplied])
            # bool is an int subclass: True == 1. Never accept it as
            # a verified ledger count. Unexpected return types/counts
            # must fail closed, not become acceptance evidence.
            if type(verdict) is not int or verdict not in (0, 1):
                observed = False
                error = "InvalidValidatorResult"
            else:
                observed = verdict == 1
                error = None
        except Exception as exc:
            # Candidate validators may raise TypeError, AssertionError, or
            # other ordinary errors. Record the failure without letting one
            # malformed case suppress the remaining independent evidence.
            # SystemExit/KeyboardInterrupt are intentionally not swallowed.
            observed = False
            error = type(exc).__name__
        unchanged = supplied == before
        rows.append({
            "case": name, "expected_accept": expected, "observed_accept": observed,
            "input_unchanged": unchanged,
            "matches_contract": observed == expected and unchanged and error not in ("InvalidValidatorResult",) and (error is None or (error == "ValueError" and not expected)),
            "error_type": error,
        })
    return {
        "schema": "p3l-w01-contract-drift-v1",
        "author": "GPT-6 coordinator (not model-generated)",
        "scope": "existing validator vs proposed W01 rules; NOT model document acceptance",
        "model_calls": 0, "candidate_verified": False, "merge_authorized": False,
        "fixed_25_modified": False,
        "cases": rows, "matches": sum(x["matches_contract"] for x in rows),
        "mismatches": [x["case"] for x in rows if not x["matches_contract"]],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=pathlib.Path)
    args = parser.parse_args()
    report = audit()
    data = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(data, encoding="utf-8")
    else:
        print(data, end="")
    # Drift is reported as evidence, not a CI infrastructure failure.
    return 0


if __name__ == "__main__":
    sys.exit(main())
