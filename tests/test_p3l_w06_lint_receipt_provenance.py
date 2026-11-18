"""Fail-closed provenance checks for read-only W06 receipt diagnostics."""
import hashlib
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import p3l_w06_public_contract_lint as lint


def valid_receipt():
    raw = "def validate(records):\n    return len(records)\n"
    return {
        "schema": "p3l-w06-one-shot-output-v1",
        "run_id": 44233044418,
        "raw_response": raw,
        "raw_response_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "candidate_source_sha256": "a" * 64,
    }


class ReceiptProvenanceTests(unittest.TestCase):
    def test_rejects_forged_or_missing_run_ids(self):
        for bad in (True, False, 0, -1, 1.0, "44233044418", None):
            with self.subTest(bad=bad):
                data = valid_receipt()
                data["run_id"] = bad
                with self.assertRaisesRegex(ValueError, "run_id"):
                    lint.diagnose(data)

    def test_rejects_malformed_candidate_digests(self):
        for bad in (None, True, "a" * 63, "A" * 64, "z" * 64, 123):
            with self.subTest(bad=bad):
                data = valid_receipt()
                data["candidate_source_sha256"] = bad
                with self.assertRaisesRegex(ValueError, "candidate_source_sha256"):
                    lint.diagnose(data)

    def test_valid_receipt_is_still_advisory(self):
        result = lint.diagnose(valid_receipt())
        self.assertEqual(result["run_id"], 44233044418)
        self.assertFalse(result["candidate_passed"])
        self.assertFalse(result["independent_replay_completed"])


if __name__ == "__main__":
    unittest.main()
