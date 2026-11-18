"""Offline regression tests for explicit W01 contract acceptance gate.

Coordinator-authored; no model calls, no changes to frozen 25 cases.
"""
import copy
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from p3l_w01_contract_drift import audit, gate_exit_code, cases


class W01ZeroDriftGateTests(unittest.TestCase):
    @staticmethod
    def complete_report():
        rows = [{"case": name, "expected_accept": expected,
                 "observed_accept": expected, "input_unchanged": True,
                 "error_type": None if expected else "ValueError",
                 "matches_contract": True} for name, _, expected in cases()]
        return {"schema": "p3l-w01-contract-drift-v1", "cases": rows,
                "matches": len(rows), "mismatches": [],
                "candidate_verified": False, "merge_authorized": False,
                "model_calls": 0, "fixed_25_modified": False}

    def test_spoofed_full_report_without_decisions_rejected(self):
        report = self.complete_report()
        report["cases"] = [{"case": row["case"], "matches_contract": True}
                           for row in report["cases"]]
        self.assertEqual(gate_exit_code(report, True), 2)

    def test_spoofed_acceptance_and_error_types_rejected(self):
        for field, value in (("expected_accept", False),
                             ("observed_accept", False),
                             ("input_unchanged", False),
                             ("error_type", "RuntimeError")):
            report = self.complete_report()
            row = next(x for x in report["cases"] if x["case"] == "empty_fixes_valid")
            row[field] = value
            with self.subTest(field=field):
                self.assertEqual(gate_exit_code(report, True), 2)

    def test_missing_required_error_type_rejected(self):
        report = self.complete_report()
        del report["cases"][0]["error_type"]
        self.assertEqual(gate_exit_code(report, True), 2)

    def test_spoofed_report_provenance_rejected(self):
        for field, value in (("schema", "unknown"), ("candidate_verified", True),
                             ("merge_authorized", True), ("model_calls", 1),
                             ("fixed_25_modified", True)):
            report = self.complete_report()
            report[field] = value
            with self.subTest(field=field):
                self.assertEqual(gate_exit_code(report, True), 2)

    def test_observation_mode_does_not_claim_acceptance(self):
        self.assertEqual(gate_exit_code(audit(), False), 0)

    def test_real_validator_meets_all_proposed_rules(self):
        report = audit()
        self.assertEqual(len(report["cases"]), 19)
        self.assertEqual(report["matches"], 19)
        self.assertEqual(report["mismatches"], [])
        self.assertEqual(gate_exit_code(report, True), 0)

    def test_deliberately_incomplete_validator_is_blocked(self):
        report = audit(lambda records: 1)
        self.assertTrue(report["mismatches"])
        self.assertEqual(gate_exit_code(report, True), 2)

    def test_perfect_report_can_pass_only_when_complete(self):
        report = self.complete_report()
        self.assertEqual(gate_exit_code(report, True), 0)

    def test_incomplete_or_spoofed_case_sets_fail_closed(self):
        names = [name for name, _, _ in cases()]
        good = [{"case": name, "matches_contract": True} for name in names]
        for rows in (good[:1], good[:-1], good[:-1] + [good[0]],
                     good[:-1] + [{"case": "unrecognized", "matches_contract": True}]):
            with self.subTest(rows=len(rows)):
                report = {"cases": rows, "matches": len(rows), "mismatches": []}
                self.assertEqual(gate_exit_code(report, True), 2)

    def test_empty_or_malformed_reports_fail_closed(self):
        for report in ({}, {"cases": [], "matches": 0, "mismatches": []},
                       {"cases": [{"matches_contract": False}], "matches": 1, "mismatches": []},
                       {"cases": [{"matches_contract": True}], "matches": 1, "mismatches": ["x"]}):
            with self.subTest(report=report):
                self.assertEqual(gate_exit_code(report, True), 2)

    def test_cli_writes_evidence_when_gate_passes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "report.json"
            command = [sys.executable, str(ROOT / "scripts/p3l_w01_contract_drift.py"),
                       "--out", str(path), "--require-zero-drift"]
            proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(path.exists())
            import json
            report = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(report["mismatches"], [])
            self.assertEqual(report["matches"], 19)
            self.assertFalse(report["candidate_verified"])


if __name__ == "__main__":
    unittest.main()
