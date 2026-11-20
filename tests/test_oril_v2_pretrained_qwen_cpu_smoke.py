"""No GPU/model download required: fail-closed proof schema tests."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_pretrained_qwen_cpu_smoke import MODEL_ID, validate_report


def fixture():
    return {
        "model_id": MODEL_ID, "resolved_revision": "a" * 40,
        "weight_files": [{"name": "model.safetensors", "bytes": 123,
                          "sha256": "b" * 64}],
        "pretrained_checkpoint_loaded": True, "weights_trained_this_run": False,
        "gpu_lora_training_proven": False,
        "independent_heldout_accuracy_proven": False,
        "inferences": [{"input_tokens": 5, "generated_tokens": 3,
                        "elapsed_seconds": 0.2, "output": "some text"}] * 2,
    }


class ProofSchema(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(validate_report(fixture()))

    def test_rejects_wrong_model(self):
        x = fixture()
        x["model_id"] = "toy/random"
        with self.assertRaises(ValueError):
            validate_report(x)

    def test_rejects_missing_revision(self):
        x = fixture()
        x["resolved_revision"] = ""
        with self.assertRaises(ValueError):
            validate_report(x)

    def test_rejects_missing_weights(self):
        x = fixture()
        x["weight_files"] = []
        with self.assertRaises(ValueError):
            validate_report(x)

    def test_rejects_zero_bytes(self):
        x = fixture()
        x["weight_files"][0]["bytes"] = 0
        with self.assertRaises(ValueError):
            validate_report(x)

    def test_rejects_untrained_checkpoint_claim(self):
        x = fixture()
        x["pretrained_checkpoint_loaded"] = False
        with self.assertRaises(ValueError):
            validate_report(x)

    def test_rejects_false_lora_claim(self):
        x = fixture()
        x["gpu_lora_training_proven"] = True
        with self.assertRaises(ValueError):
            validate_report(x)

    def test_rejects_false_heldout_claim(self):
        x = fixture()
        x["independent_heldout_accuracy_proven"] = True
        with self.assertRaises(ValueError):
            validate_report(x)

    def test_rejects_no_generation(self):
        x = fixture()
        x["inferences"][0] = {**x["inferences"][0], "generated_tokens": 0}
        with self.assertRaises(ValueError):
            validate_report(x)

    def test_rejects_zero_time(self):
        x = fixture()
        x["inferences"][0] = {**x["inferences"][0], "elapsed_seconds": 0}
        with self.assertRaises(ValueError):
            validate_report(x)

    def test_rejects_empty_output(self):
        x = fixture()
        x["inferences"][0] = {**x["inferences"][0], "output": " "}
        with self.assertRaises(ValueError):
            validate_report(x)

    def test_rejects_single_inference(self):
        x = fixture()
        x["inferences"].pop()
        with self.assertRaises(ValueError):
            validate_report(x)


if __name__ == "__main__":
    unittest.main()
