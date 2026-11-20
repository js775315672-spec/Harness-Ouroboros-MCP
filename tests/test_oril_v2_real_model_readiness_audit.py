import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_real_model_readiness_audit import audit, check_checkpoint


class RealReadinessAuditTests(unittest.TestCase):
    def test_missing_prerequisites_are_explicit(self):
        r = audit(gpu_probe={"nvidia_smi_available": False, "gpu_count": None, "gpu_names": []})
        self.assertFalse(r["ready_for_local_inference_attempt"])
        self.assertFalse(r["ready_for_proven_lora_training"])
        self.assertEqual(len(r["missing_evidence"]), 4)
        self.assertIsNone(r["model_intelligence_improved"])

    def test_fake_gpu_claim_is_not_training_proof(self):
        r = audit(gpu_probe={"nvidia_smi_available": True, "gpu_count": 1, "gpu_names": ["Fake"]})
        self.assertFalse(r["ready_for_proven_lora_training"])
        self.assertFalse(r["adapter_sha256_verified"])
        self.assertIsNone(r["training_steps_observed"])

    def test_checkpoint_without_weights_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config.json").write_text("{}")
            self.assertFalse(check_checkpoint(root)["weights_present"])

    def test_checkpoint_with_weight_and_config_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config.json").write_text("{}")
            (root / "model.safetensors").write_bytes(b"fake-not-a-model")
            ckpt = check_checkpoint(root)
            self.assertTrue(ckpt["weights_present"])
            self.assertEqual(len(ckpt["config_sha256"]), 64)

    def test_symlinked_config_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "real.json").write_text("{}")
            (root / "config.json").symlink_to(root / "real.json")
            self.assertIsNone(check_checkpoint(root)["config_sha256"])

    def test_existing_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.json"
            out.write_text("original")
            cmd = [sys.executable, str(Path(__file__).resolve().parents[1] /
                   "scripts/oril_v2_real_model_readiness_audit.py"), "--output", str(out)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(out.read_text(), "original")

    def test_cli_writes_missing_evidence_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.json"
            cmd = [sys.executable, str(Path(__file__).resolve().parents[1] /
                   "scripts/oril_v2_real_model_readiness_audit.py"), "--output", str(out)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(out.read_text())
            self.assertFalse(report["ready_for_proven_lora_training"])
            self.assertIsNone(report["independent_heldout_score"])
            self.assertIn("local_model_checkpoint", report["missing_evidence"])

    def test_heldout_and_adapter_files_do_not_imply_training(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = root / "model"
            model.mkdir()
            (model / "config.json").write_text("{}")
            (model / "model.safetensors").write_bytes(b"fake")
            heldout = root / "heldout.jsonl"
            heldout.write_text('{"task":1}\n')
            adapter = root / "adapter"
            adapter.mkdir()
            (adapter / "adapter_config.json").write_text("{}")
            (adapter / "adapter_model.safetensors").write_bytes(b"fake")
            r = audit(model, heldout, adapter,
                      gpu_probe={"nvidia_smi_available": True, "gpu_count": 1,
                                 "gpu_names": ["Fake"]})
            self.assertTrue(r["ready_for_local_inference_attempt"])
            self.assertTrue(r["adapter_files_present"])
            self.assertFalse(r["ready_for_proven_lora_training"])
            self.assertIsNone(r["independent_heldout_score"])


if __name__ == "__main__":
    unittest.main()
