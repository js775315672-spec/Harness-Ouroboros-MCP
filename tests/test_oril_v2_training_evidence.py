"""Synthetic unit tests only: passing does not attest any real training."""
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_training_evidence import validate

DATA = b"synthetic-test-adapter-not-a-real-model"
def fixture():
    h = lambda value: hashlib.sha256(value.encode()).hexdigest()
    return {
        "schema_version": "oril-v2-training-evidence-0.1",
        "status": "VERIFIED_TRAINING",
        "source_commit_sha": "a" * 40,
        "authorization_ref": "synthetic-approval",
        "model_base_digest": h("base"),
        "tokenizer_digest": h("tokenizer"),
        "training_dataset_digest": h("train"),
        "heldout_dataset_digest": h("heldout"),
        "trainer_config_digest": h("config"),
        "run_url": "https://example.invalid/synthetic-run",
        "run_id": "synthetic-1",
        "gpu_telemetry_ref": "synthetic-gpu-log",
        "gpu_device": "synthetic-gpu",
        "trainer_exit_code": 0,
        "optimizer_steps": 1,
        "adapter_sha256": hashlib.sha256(DATA).hexdigest(),
        "adapter_size_bytes": len(DATA),
        "base_model_compatible": True,
        "heldout_contamination_free": True,
        "training_actor": "synthetic-trainer",
    }

class TrainingEvidenceTests(unittest.TestCase):
    def test_synthetic_complete_preflight(self):
        ok, errors = validate(fixture(), DATA)
        self.assertTrue(ok, errors)

    def test_unverified_status(self):
        m = fixture()
        m["status"] = "TRAINING_COMPLETED_UNVERIFIED"
        self.assertFalse(validate(m, DATA)[0])

    def test_missing_authorization(self):
        m = fixture()
        m["authorization_ref"] = None
        self.assertIn("missing_authorization_ref", validate(m, DATA)[1])

    def test_zero_steps(self):
        m = fixture()
        m["optimizer_steps"] = 0
        self.assertIn("invalid_optimizer_steps", validate(m, DATA)[1])

    def test_boolean_steps_rejected(self):
        m = fixture()
        m["optimizer_steps"] = True
        self.assertFalse(validate(m, DATA)[0])

    def test_missing_adapter(self):
        self.assertIn("adapter_bytes_unavailable", validate(fixture())[1])

    def test_forged_adapter_digest(self):
        self.assertIn("adapter_digest_mismatch", validate(fixture(), b"forged")[1])

    def test_duplicate_run(self):
        self.assertIn("duplicate_run_id", validate(fixture(), DATA, {"synthetic-1"})[1])

    def test_missing_gpu(self):
        m = fixture()
        m["gpu_telemetry_ref"] = None
        self.assertFalse(validate(m, DATA)[0])

    def test_heldout_collision(self):
        m = fixture()
        m["heldout_dataset_digest"] = m["training_dataset_digest"]
        self.assertIn("train_heldout_digest_collision", validate(m, DATA)[1])

    def test_incompatible_base(self):
        m = fixture()
        m["base_model_compatible"] = False
        self.assertFalse(validate(m, DATA)[0])

    def test_contamination(self):
        m = fixture()
        m["heldout_contamination_free"] = False
        self.assertFalse(validate(m, DATA)[0])

    def test_evaluation_required(self):
        m = fixture()
        m["status"] = "INDEPENDENTLY_EVALUATED"
        self.assertIn("missing_independent_eval", validate(m, DATA)[1])

    def test_promotion_approval_required(self):
        m = fixture()
        m["status"] = "PROMOTED"
        m["independent_eval_ref"] = "synthetic-eval"
        self.assertIn("missing_promotion_approval", validate(m, DATA)[1])

    def test_self_promotion_rejected(self):
        m = fixture()
        m.update(status="PROMOTED", independent_eval_ref="synthetic-eval",
                 promotion_approval_ref="synthetic-user-approval",
                 promotion_actor=m["training_actor"])
        self.assertIn("self_promotion", validate(m, DATA)[1])

    def test_non_object_rejected(self):
        self.assertFalse(validate([], DATA)[0])

if __name__ == "__main__":
    unittest.main()
