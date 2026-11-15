import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from disposable_failure_feedback import classify

INFERENCE = {"status": "accepted_for_review", "real_model_calls": 1}
REGRESSION = {"status": "regression_failed", "merge_authorized": False,
              "patch_applied_to_checkout": False}

class DisposableFeedbackTests(unittest.TestCase):
    def test_failure_requests_next_run_repair(self):
        result = classify(INFERENCE, REGRESSION)
        self.assertEqual(result["decision"], "request_repair")
        self.assertTrue(result["next_run_only"])
        self.assertFalse(result["executed_repair_model_call"])

    def test_pass_requires_no_repair(self):
        self.assertEqual(classify(INFERENCE, dict(REGRESSION, status="isolated_regression_passed"))["decision"], "no_repair_needed")

    def test_second_attempt_stops(self):
        self.assertEqual(classify(dict(INFERENCE, real_model_calls=2), REGRESSION)["decision"], "stop")

    def test_unsafe_mutation_claim_rejected(self):
        with self.assertRaises(ValueError):
            classify(INFERENCE, dict(REGRESSION, patch_applied_to_checkout=True))

    def test_unknown_status_rejected(self):
        with self.assertRaises(ValueError):
            classify(INFERENCE, dict(REGRESSION, status="invented"))

    def test_missing_attempt_count_rejected(self):
        with self.assertRaises(ValueError):
            classify({"status": "accepted_for_review"}, REGRESSION)

    def test_rejected_inference_stops(self):
        self.assertEqual(classify(dict(INFERENCE, status="rejected"), REGRESSION)["decision"], "stop")

if __name__ == "__main__":
    unittest.main()
