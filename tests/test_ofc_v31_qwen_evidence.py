"""Offline evidence contract tests; no Qwen API, OPS, or protected holdout."""
import unittest
from agent.qwen_evidence_gate import EvidenceError, verify_receipt, digest


class TestQwenEvidenceGate(unittest.TestCase):
    def setUp(self):
        self.r = dict(role="ouroboros", model_id="Qwen/local-free", model_revision="pinned",
            input_sha256=digest(b"input"), prompt_sha256=digest(b"prompt"),
            weights_sha256=digest(b"weights"), output_sha256=digest(b"output"),
            evaluator_sha="a"*40, candidate_sha="b"*40, run_id=123, independent_pass=False)

    def test_valid_shape_is_not_quality_claim(self):
        self.assertTrue(verify_receipt(self.r))

    def test_wrong_role_is_rejected(self):
        self.r["role"] = "another-agent"
        with self.assertRaises(EvidenceError): verify_receipt(self.r)

    def test_missing_provenance_is_rejected(self):
        del self.r["weights_sha256"]
        with self.assertRaises(EvidenceError): verify_receipt(self.r)

    def test_forged_pass_without_receipt_is_rejected(self):
        self.r["independent_pass"] = True
        with self.assertRaises(EvidenceError): verify_receipt(self.r)

    def test_missing_real_run_is_rejected(self):
        self.r["run_id"] = 0
        with self.assertRaises(EvidenceError): verify_receipt(self.r)


if __name__ == "__main__": unittest.main()
