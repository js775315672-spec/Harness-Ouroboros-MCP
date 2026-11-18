"""W03 independent diagnostics and W02 handoff reconciliation."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import p3l_w03_rule_diagnostics as w03


class LedgerRuleDiagnosticsTests(unittest.TestCase):
    def test_all_provisional_rules_are_independently_isolated(self):
        rows = w03.rule_diagnostics()
        self.assertEqual(len(rows), 19)
        self.assertEqual(len(set(x["case"] for x in rows)), 19)
        self.assertTrue(all(x["isolated_rule_passed"] and x["input_unchanged"] for x in rows))
        for case_id in ("empty_fixes_valid", "empty_fix_rejected", "thirteen_fixes_rejected",
                        "fix_129_bytes_rejected", "change_257_bytes_rejected",
                        "change_hangul_258_rejected", "change_lf_rejected"):
            self.assertIn(case_id, {x["case"] for x in rows})

    def test_w02_w03_manifest_and_sha_handoff(self):
        report = w03.diagnose()
        self.assertTrue(report["w01_provisional_gate_passed"])
        self.assertEqual(report["cases_checked"], 19)
        self.assertEqual(report["isolated_rule_passed"], 19)
        self.assertEqual(report["candidate_contract_matches"], 19)
        self.assertEqual(report["candidate_contract_mismatches"], [])
        self.assertEqual(report["legacy_contract_matches"], 7)
        self.assertEqual(len(report["legacy_contract_mismatches"]), 12)
        self.assertEqual(report["model_calls"], 0)
        self.assertFalse(report["candidate_model_generated"])
        self.assertFalse(report["promoted"])
        self.assertFalse(report["merge_authorized"])

    def test_wrong_w02_sha_receipt_is_rejected(self):
        report = w03.w02.build()
        report["w01_case_manifest_sha256"] = "0" * 64
        with patch.object(w03.w02, "build", return_value=report):
            with self.assertRaisesRegex(ValueError, "W02 contract manifest"):
                w03.diagnose()

    def test_candidate_wrong_exception_reason_cannot_pass(self):
        def wrong_field_validator(records):
            raise ValueError("invalid CI evidence URL")
        with patch.object(w03, "candidate_validate", wrong_field_validator):
            with self.assertRaises(ValueError):
                w03.rule_diagnostics()

    def test_always_reject_is_not_a_valid_negative_case(self):
        def reject_all(records):
            raise ValueError("invalid fixes")
        with patch.object(w03, "candidate_validate", reject_all):
            with self.assertRaises(ValueError):
                w03.rule_diagnostics()

    def test_unchanged_input_required(self):
        def mutating_candidate(records):
            records[0]["change"] = "tampered"
            return 1
        with patch.object(w03, "candidate_validate", mutating_candidate):
            with self.assertRaises(ValueError):
                w03.rule_diagnostics()


if __name__ == "__main__":
    unittest.main()
