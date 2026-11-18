"""W01 proposed input-contract boundary tests for the real ledger validator.

Coordinator-authored implementation evidence. This is not a model-generated
candidate and does not modify or replace the fixed 25-case oracle.
"""
import copy
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from p3l_w01_candidate_validator import validate
from p3l_w01_contract_drift import audit, cases, gate_exit_code, valid_record


class W01ValidatorAcceptanceTests(unittest.TestCase):
    def test_all_nineteen_boundaries_with_unchanged_input(self):
        scenarios = list(cases())
        self.assertEqual(len(scenarios), 19)
        for case_id, record, expected in scenarios:
            with self.subTest(case=case_id):
                original = copy.deepcopy(record)
                if expected:
                    self.assertEqual(validate([record]), 1)
                else:
                    with self.assertRaises(ValueError):
                        validate([record])
                self.assertEqual(record, original)

    def test_real_evidence_passes_explicit_gate_without_candidate_claim(self):
        report = audit(validate)
        self.assertEqual(report["matches"], 19)
        self.assertEqual(report["mismatches"], [])
        self.assertEqual(gate_exit_code(report, require_zero_drift=True), 0)
        self.assertFalse(report["candidate_verified"])
        self.assertFalse(report["merge_authorized"])
        self.assertEqual(report["model_calls"], 0)

    def test_disallowed_c1_controls_fail_closed(self):
        for field in ("change", "fixes"):
            record = valid_record()
            if field == "change":
                record["change"] = "tested\u0085control"
            else:
                record["fixes"] = ["tested\u0085control"]
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    validate([record])

    def test_unpaired_surrogate_is_not_valid_utf8(self):
        for field in ("change", "fixes"):
            record = valid_record()
            if field == "change":
                record["change"] = "tested\ud800"
            else:
                record["fixes"] = ["tested\ud800"]
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    validate([record])


if __name__ == "__main__":
    unittest.main()
