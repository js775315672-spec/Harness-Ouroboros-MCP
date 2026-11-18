"""Offline regression tests for explicit W01 contract acceptance gate.

Coordinator-authored; no model calls, no changes to frozen 25 cases.
"""
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from p3l_w01_contract_drift import audit, gate_exit_code, cases


class W01ZeroDriftGateTests(unittest.TestCase):
    def test_observation_mode_does_not_claim_acceptance(self):
        self.assertEqual(gate_exit_code(audit(), False), 0)

    def test_real_baseline_mismatch_blocks_acceptance(self):
        report = audit()
        self.assertTrue(report["mismatches"])
        self.assertEqual(gate_exit_code(report, True), 2)

    def test_perfect_report_can_pass_only_when_complete(self):
        report = {"cases": [{"case": name, "matches_contract": True} for name, _, _ in cases()], "matches": 19, "mismatches": []}
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

    def test_cli_writes_evidence_even_when_gate_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "report.json"
            command = [sys.executable, str(ROOT / "scripts/p3l_w01_contract_drift.py"),
                       "--out", str(path), "--require-zero-drift"]
            proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 2, proc.stderr)
            self.assertTrue(path.exists())
            import json
            report = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(report["mismatches"])
            self.assertFalse(report["candidate_verified"])


if __name__ == "__main__":
    unittest.main()
