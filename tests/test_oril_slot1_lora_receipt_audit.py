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


    def test_reject_truncated_adapter_even_with_updated_digest(self):
        adapter = self.root / "run-01" / "adapter.safetensors"
        adapter.write_bytes(adapter.read_bytes()[:-1])
        import hashlib
        self.mutate("adapter_sha256", hashlib.sha256(adapter.read_bytes()).hexdigest())
        with self.assertRaisesRegex(ValueError, "offset outside payload"):
            audit(self.root)

    def test_reject_overlapping_tensor_spans_even_with_updated_digest(self):
        import hashlib
        import struct
        adapter = self.root / "run-01" / "adapter.safetensors"
        raw = adapter.read_bytes()
        length = struct.unpack("<Q", raw[:8])[0]
        header = json.loads(raw[8:8 + length])
        # Preserve B's declared byte length while shifting it into A's span.
        # Copying A's offsets would also change B's length and test the wrong gate.
        a_start, a_end = header["A"]["data_offsets"]
        b_start, b_end = header["B"]["data_offsets"]
        b_size = b_end - b_start
        overlap = min(4, a_end - a_start, b_size)
        self.assertGreater(overlap, 0)
        shifted_start = a_end - overlap
        shifted_end = shifted_start + b_size
        self.assertLessEqual(shifted_end, len(raw) - 8 - length)
        header["B"]["data_offsets"] = [shifted_start, shifted_end]
        new_header = json.dumps(header, separators=(",", ":")).encode()
        adapter.write_bytes(struct.pack("<Q", len(new_header)) + new_header + raw[8 + length:])
        self.mutate("adapter_sha256", hashlib.sha256(adapter.read_bytes()).hexdigest())
        with self.assertRaisesRegex(ValueError, "overlapping safetensors"):
            audit(self.root)

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
