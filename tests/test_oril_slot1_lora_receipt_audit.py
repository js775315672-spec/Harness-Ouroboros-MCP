"""Regression tests for public LoRA receipt consistency and fail-closed claims."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from oril_slot1_lora_receipt_audit import audit


class AuditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        source = ROOT / "experiments" / "hydra-lora"
        for name in ("train.csv", "eval.csv"):
            shutil.copy2(source / name, self.root / name)
        (self.root / "run-01").mkdir()
        for name in ("receipt.json", "adapter.safetensors"):
            shutil.copy2(source / "run-01" / name, self.root / "run-01" / name)

    def receipt(self):
        return self.root / "run-01" / "receipt.json"

    def mutate(self, key, value):
        data = json.loads(self.receipt().read_text())
        data[key] = value
        self.receipt().write_text(json.dumps(data))

    def test_real_fixture_reconciles_without_promotion(self):
        result = audit(self.root)
        self.assertTrue(result["receipt_consistent"])
        self.assertEqual(result["public_regressed"], 3)
        self.assertEqual(result["optimizer_steps_reported"], 100)
        self.assertFalse(result["promotion_allowed"])
        self.assertFalse(result["gpu_execution_independently_attested"])

    def test_reject_tampered_adapter(self):
        with (self.root / "run-01" / "adapter.safetensors").open("ab") as f:
            f.write(b"x")
        with self.assertRaisesRegex(ValueError, "adapter sha256"):
            audit(self.root)

    def test_reject_tampered_eval(self):
        with (self.root / "eval.csv").open("a") as f:
            f.write("tampered,success\\n")
        with self.assertRaisesRegex(ValueError, "split digest"):
            audit(self.root)

    def test_reject_false_accuracy(self):
        self.mutate("candidate_correct", 12)
        with self.assertRaisesRegex(ValueError, "candidate_correct"):
            audit(self.root)

    def test_reject_hidden_regression(self):
        self.mutate("regressed", 0)
        with self.assertRaisesRegex(ValueError, "regressed"):
            audit(self.root)

    def test_reject_false_optimizer_steps(self):
        self.mutate("optimizer_steps", 0)
        with self.assertRaisesRegex(ValueError, "optimizer step"):
            audit(self.root)

    def test_reject_nonfinite_loss(self):
        self.mutate("initial_loss", float("nan"))
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            audit(self.root)


if __name__ == "__main__":
    unittest.main()
