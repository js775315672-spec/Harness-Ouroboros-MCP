"""Synthetic fail-fast tests. NO actual Qwen weights, GPU or LoRA are loaded."""
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_local_qwen_adapter import run_inference


class Tensor:
    def __init__(self, shape):
        self.shape = shape
    def to(self, device):
        return self


class FakeTokenizer:
    chat_template = None
    shape = (1, 3)
    mask_shape = None
    @classmethod
    def from_pretrained(cls, *args, **kwargs):
        return cls()
    def __call__(self, prompt, return_tensors="pt"):
        out = {"input_ids": Tensor(self.shape)}
        if self.mask_shape is not None:
            out["attention_mask"] = Tensor(self.mask_shape)
        return out
    def decode(self, tokens, skip_special_tokens=True):
        return "ok"


class FakeGenerated:
    def __init__(self, input_length):
        self.shape = (1, input_length + 1)
    def __getitem__(self, key):
        return Tensor((1, 1))


class FakeModel:
    loads = 0
    @classmethod
    def from_pretrained(cls, *args, **kwargs):
        cls.loads += 1
        return cls()
    def to(self, device):
        return self
    def eval(self):
        return self
    def generate(self, **kwargs):
        return FakeGenerated(kwargs["input_ids"].shape[-1])


class FakeInferenceMode:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class TokenBudgetBeforeWeights(unittest.TestCase):
    def setUp(self):
        FakeTokenizer.shape = (1, 3)
        FakeTokenizer.mask_shape = None
        FakeModel.loads = 0

    def run_case(self):
        torch = types.SimpleNamespace(
            manual_seed=lambda x: None, inference_mode=FakeInferenceMode,
            cuda=types.SimpleNamespace(is_available=lambda: False))
        transformers = types.SimpleNamespace(
            AutoTokenizer=FakeTokenizer, AutoModelForCausalLM=FakeModel)
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "config.json").write_text("{}")
            with patch.dict(sys.modules, {"torch": torch, "transformers": transformers}):
                return run_inference({"question": "short", "case_id": "c", "seed": 1},
                                     model_dir=root)

    def test_oversized_token_count_rejected_before_weight_load(self):
        FakeTokenizer.shape = (1, 4097)
        with self.assertRaisesRegex(ValueError, "4096"):
            self.run_case()
        self.assertEqual(FakeModel.loads, 0)

    def test_empty_tokens_rejected_before_weight_load(self):
        FakeTokenizer.shape = (1, 0)
        with self.assertRaisesRegex(ValueError, "4096"):
            self.run_case()
        self.assertEqual(FakeModel.loads, 0)

    def test_multi_batch_rejected_before_weight_load(self):
        FakeTokenizer.shape = (2, 4)
        with self.assertRaisesRegex(ValueError, "4096"):
            self.run_case()
        self.assertEqual(FakeModel.loads, 0)

    def test_missing_batch_dimension_rejected_before_weight_load(self):
        FakeTokenizer.shape = (4,)
        with self.assertRaisesRegex(ValueError, "4096"):
            self.run_case()
        self.assertEqual(FakeModel.loads, 0)

    def test_mask_mismatch_rejected_before_weight_load(self):
        FakeTokenizer.mask_shape = (1, 2)
        with self.assertRaisesRegex(ValueError, "mask shape"):
            self.run_case()
        self.assertEqual(FakeModel.loads, 0)

    def test_4096_tokens_permitted(self):
        FakeTokenizer.shape = (1, 4096)
        self.run_case()
        self.assertEqual(FakeModel.loads, 1)

    def test_valid_mask_permitted(self):
        FakeTokenizer.mask_shape = (1, 3)
        result = self.run_case()
        self.assertEqual(result["input_tokens"], 3)
        self.assertEqual(FakeModel.loads, 1)


if __name__ == "__main__":
    unittest.main()
