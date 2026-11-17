"""Offline tests for read-only W01 drift probe; no fixed tests are changed."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from p3l_w01_contract_drift import audit, cases, valid_record


class ContractDriftTests(unittest.TestCase):
    def test_case_ids_are_unique(self):
        names = [name for name, _, _ in cases()]
        self.assertEqual(len(names), len(set(names)))
        self.assertGreaterEqual(len(names), 19)

    def test_valid_baseline(self):
        row = valid_record()
        self.assertEqual(row["fixes"], [])
        self.assertEqual(row["cycle"], 1)

    def test_hangul_utf8_boundaries(self):
        by_name = {name: (record, expected) for name, record, expected in cases()}
        self.assertEqual(len(by_name["hangul_126_bytes_valid"][0]["fixes"][0].encode()), 126)
        self.assertEqual(len(by_name["hangul_129_bytes_rejected"][0]["fixes"][0].encode()), 129)
        self.assertEqual(len(by_name["change_hangul_255_valid"][0]["change"].encode()), 255)
        self.assertEqual(len(by_name["change_hangul_258_rejected"][0]["change"].encode()), 258)

    def test_current_validator_drift_is_reported_not_silenced(self):
        result = audit()
        self.assertEqual(result["model_calls"], 0)
        self.assertFalse(result["candidate_verified"])
        self.assertFalse(result["merge_authorized"])
        self.assertEqual(result["matches"] + len(result["mismatches"]), len(result["cases"]))
        self.assertEqual(result["mismatches"], [
            row["case"] for row in result["cases"] if not row["matches_contract"]
        ])
        self.assertTrue(all(
            row["matches_contract"] == (row["expected_accept"] == row["observed_accept"])
            for row in result["cases"]
        ))
        self.assertIn("empty_fixes_valid", {row["case"] for row in result["cases"]})
        # A future validator that meets the contract must not fail this probe.
        # Drift is an observation, not a permanently expected failure.

    def test_perfect_validator_has_no_drift(self):
        decisions = {name: expected for name, _, expected in cases()}
        names = iter(decisions)
        def fake_validator(records):
            name = next(names)
            if not decisions[name]:
                raise ValueError("rejected")
            return 1
        result = audit(fake_validator)
        self.assertEqual(result["mismatches"], [])
        self.assertEqual(result["matches"], len(decisions))


if __name__ == "__main__":
    unittest.main()
