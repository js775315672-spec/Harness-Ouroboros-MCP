import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from qwen_loop_evidence_bridge import decide

INFERENCE = {"status": "accepted_for_review", "patch_applied": False, "merge_authorized": False}
REGRESSION = {"status": "isolated_regression_passed", "patch_applied_to_checkout": False,
              "merge_authorized": False,
              "provenance": {"provenance_verified": True, "model_response_replayed": True}}
REVIEW = {"decision": "ready_for_human_review", "merge_authorized": False, "model_patch_applied": False}

class BridgeTests(unittest.TestCase):
    def test_review_does_not_claim_autonomous_coding(self):
        result = decide(INFERENCE, REGRESSION, REVIEW)
        self.assertEqual(result["decision"], "await_independent_ci_and_external_coding_executor")
        self.assertFalse(result["source_modified"])
        self.assertFalse(result["autonomous_coding_connected"])
        self.assertFalse(result["independent_ci_attested"])

    def test_rejected_model_stops(self):
        self.assertEqual(decide(dict(INFERENCE, status="rejected"), REGRESSION, REVIEW)["decision"], "stop")

    def test_failed_regression_stops(self):
        self.assertEqual(decide(INFERENCE, dict(REGRESSION, status="failed"), REVIEW)["decision"], "stop")

    def test_review_not_ready_stops(self):
        self.assertEqual(decide(INFERENCE, REGRESSION, dict(REVIEW, decision="blocked"))["decision"], "stop")

    def test_merge_claim_blocked(self):
        with self.assertRaises(ValueError):
            decide(INFERENCE, REGRESSION, dict(REVIEW, merge_authorized=True))

    def test_source_mutation_blocked(self):
        with self.assertRaises(ValueError):
            decide(dict(INFERENCE, patch_applied=True), REGRESSION, REVIEW)

    def test_missing_provenance_blocked(self):
        with self.assertRaises(ValueError):
            decide(INFERENCE, dict(REGRESSION, provenance={}), REVIEW)

if __name__ == "__main__":
    unittest.main()
