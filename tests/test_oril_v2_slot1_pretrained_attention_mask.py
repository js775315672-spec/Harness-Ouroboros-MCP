"""Mock-only attention mask regression: no download, no torch dependency."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_pretrained_qwen_cpu_smoke import build_masked_inputs, validate_report, MODEL_ID


class FakeTensor:
    def __init__(self, shape):
        self.shape = shape
        self.ndim = len(shape)


class FakeTokenizer:
    def __init__(self, shape=(1, 4)):
        self.shape = shape
        self.called = 0

    def apply_chat_template(self, chat, **kwargs):
        self.called += 1
        assert kwargs["return_tensors"] == "pt"
        assert kwargs["add_generation_prompt"] is True
        return FakeTensor(self.shape)


class FakeTorch:
    def __init__(self, shape=None):
        self.shape = shape
        self.calls = 0

    def ones_like(self, token_ids):
        self.calls += 1
        return FakeTensor(self.shape or token_ids.shape)


class AttentionMaskTests(unittest.TestCase):
    def test_single_batch_mask_matches_tokens(self):
        tok, torch = FakeTokenizer(), FakeTorch()
        result = build_masked_inputs(tok, [{"role": "user", "content": "test"}], torch)
        self.assertEqual(result["input_ids"].shape, (1, 4))
        self.assertEqual(result["attention_mask"].shape, (1, 4))
        self.assertEqual((tok.called, torch.calls), (1, 1))

    def test_empty_batch_rejected_before_mask(self):
        torch = FakeTorch()
        with self.assertRaisesRegex(ValueError, "nonempty"):
            build_masked_inputs(FakeTokenizer((1, 0)), [], torch)
        self.assertEqual(torch.calls, 0)

    def test_multiple_batches_rejected(self):
        with self.assertRaisesRegex(ValueError, "single"):
            build_masked_inputs(FakeTokenizer((2, 4)), [], FakeTorch())

    def test_unbatched_rejected(self):
        with self.assertRaisesRegex(ValueError, "single"):
            build_masked_inputs(FakeTokenizer((4,)), [], FakeTorch())

    def test_wrong_mask_shape_rejected(self):
        with self.assertRaisesRegex(ValueError, "mask shape"):
            build_masked_inputs(FakeTokenizer((1, 4)), [], FakeTorch((1, 3)))

    def test_proof_without_mask_assertion_rejected(self):
        evidence = {
            "model_id": MODEL_ID, "resolved_revision": "a" * 40,
            "weight_files": [{"name": "model.safetensors", "bytes": 100, "sha256": "b" * 64}],
            "pretrained_checkpoint_loaded": True, "weights_trained_this_run": False,
            "gpu_lora_training_proven": False, "independent_heldout_accuracy_proven": False,
            "inferences": [{"input_tokens": 4, "generated_tokens": 2,
                            "elapsed_seconds": 0.3, "output": "text"} for _ in range(2)]
        }
        with self.assertRaisesRegex(ValueError, "invalid inference"):
            validate_report(evidence)
        for item in evidence["inferences"]:
            item["attention_mask_explicit"] = True
        self.assertTrue(validate_report(evidence))


if __name__ == "__main__":
    unittest.main()
