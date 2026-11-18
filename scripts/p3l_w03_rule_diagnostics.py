#!/usr/bin/env python3
"""W03: independent rule-level diagnostic for provisional W01/W02 handoff.

Does not execute untrusted model code, train, promote or merge anything.
Coordinator-authored infrastructure, not a completed model worker.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

import p3l_w02_model_handoff as w02
from p3l_w01_candidate_validator import validate as candidate_validate
from p3l_w01_contract_drift import audit, cases, gate_exit_code
from development_ledger import validate as legacy_validate


def _target_field(case_id):
    if case_id.startswith("change_"):
        return "change"
    return "fixes"


def _repaired_record(record, field):
    value = copy.deepcopy(record)
    if field == "change":
        value["change"] = "tested change"
    else:
        value["fixes"] = ["fixed"]
    return value


def rule_diagnostics():
    """Each negative case must fail for exactly the intended field."""
    rows = []
    for case_id, sample, expected in cases():
        original = copy.deepcopy(sample)
        field = _target_field(case_id)
        if field == "change" and not sample["fixes"]:
            raise ValueError("change test has invalid independent fixes input")
        if field == "fixes" and sample["change"] != "tested change":
            raise ValueError("fixes test has invalid independent change input")
        error_type, reason = None, None
        try:
            verdict = candidate_validate([sample])
            accepted = type(verdict) is int and verdict == 1
            if not accepted:
                error_type = "InvalidValidatorResult"
        except Exception as exc:
            accepted = False
            error_type = type(exc).__name__
            reason = str(exc)
        if expected != accepted or original != sample:
            raise ValueError("candidate decision or input immutability mismatch: " + case_id)
        if expected:
            if error_type is not None:
                raise ValueError("valid case failed: " + case_id)
        else:
            if error_type != "ValueError" or not reason or field not in reason:
                raise ValueError("rejection could be masked by another field: " + case_id)
            repaired = _repaired_record(original, field)
            repaired_before = copy.deepcopy(repaired)
            if candidate_validate([repaired]) != 1 or repaired != repaired_before:
                raise ValueError("repaired single-field variant is still invalid: " + case_id)
        rows.append({
            "case": case_id, "target_field": field,
            "expected_accept": expected, "observed_accept": accepted,
            "validator_error_type": error_type,
            "input_unchanged": sample == original,
            "isolated_rule_passed": True,
        })
    return rows


def diagnose(root=w02.ROOT):
    handoff = w02.build(root)
    isolated = audit(candidate_validate)
    original = audit(legacy_validate)
    if gate_exit_code(isolated, True) != 0:
        raise ValueError("W01 candidate acceptance gate failed")
    rows = rule_diagnostics()
    if len(rows) != handoff["w01_case_count"] or len(rows) != 19:
        raise ValueError("W02 case set mismatch")
    manifest = [[row["case"], row["expected_accept"]] for row in rows]
    actual_digest = hashlib.sha256(json.dumps(
        manifest, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    if actual_digest != handoff["w01_case_manifest_sha256"]:
        raise ValueError("W02 contract manifest disagreed with W03")
    return {
        "schema": "p3l-w03-rule-diagnostics-v1",
        "source_path": handoff["source_path"],
        "original_source_sha256": handoff["legacy_sha256"],
        "w01_candidate_sha256": handoff["w01_candidate_sha256"],
        "w02_prompt_sha256": handoff["prompt_sha256"],
        "w01_case_manifest_sha256": actual_digest,
        "w01_provisional_gate_passed": True,
        "cases_checked": len(rows),
        "isolated_rule_passed": len(rows),
        "candidate_contract_matches": isolated["matches"],
        "candidate_contract_mismatches": isolated["mismatches"],
        "legacy_contract_matches": original["matches"],
        "legacy_contract_mismatches": original["mismatches"],
        "details": rows,
        "model_calls": 0, "candidate_model_generated": False,
        "promoted": False, "merge_authorized": False,
        "fixed_25_modified": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = diagnose()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("PASS: W02 -> W03 provisional handoff 19/19 rule-isolated; no model call or promotion")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
