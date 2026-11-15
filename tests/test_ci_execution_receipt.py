import pathlib
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from ci_execution_receipt import receipt

ENV = {"GITHUB_REPOSITORY": "org/repo", "GITHUB_SHA": "a"*40, "GITHUB_RUN_ID": "123"}

class ReceiptTests(unittest.TestCase):
    def test_receipt_never_claims_autonomous_coding(self):
        result = receipt(ENV, datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(result["kind"], "verification")
        self.assertFalse(result["source_changed_by_this_step"])
        self.assertFalse(result["continuous_autonomous_development_verified"])
        self.assertFalse(result["independent_github_attestation"])
        self.assertEqual(result["run_url"], "https://github.com/org/repo/actions/runs/123")

    def test_incomplete_provenance_rejected(self):
        with self.assertRaises(ValueError):
            receipt({"GITHUB_REPOSITORY": "org/repo"})

    def test_invalid_sha_rejected(self):
        with self.assertRaises(ValueError):
            receipt(dict(ENV, GITHUB_SHA="fake"))

    def test_invalid_run_id_rejected(self):
        with self.assertRaises(ValueError):
            receipt(dict(ENV, GITHUB_RUN_ID="0"))

    def test_invalid_repo_rejected(self):
        with self.assertRaises(ValueError):
            receipt(dict(ENV, GITHUB_REPOSITORY="org/repo/extra"))

    def test_naive_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            receipt(ENV, datetime(2026, 1, 1))

if __name__ == "__main__":
    unittest.main()
