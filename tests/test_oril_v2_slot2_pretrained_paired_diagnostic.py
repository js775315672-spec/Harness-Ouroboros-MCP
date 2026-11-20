"""No-download protocol tests for real pretrained Qwen paired prompt diagnostic."""
import copy
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_slot2_pretrained_paired_diagnostic import (
    MODEL_ID, QUESTIONS, validate_report, VERBOSE, COMPACT,
)


def fixture():
    return {
        "model_id": MODEL_ID,
        "resolved_revision": "a" * 40,
        "weight_files": [{"name": "model.safetensors", "bytes": 900,
                          "sha256": "b" * 64}],
        "pretrained_checkpoint_loaded": True,
        "weights_trained_this_run": False,
        "gpu_lora_training_proven": False,
        "independent_heldout_accuracy_proven": False,
        "quality_gain": None,
        "speed_gain": None,
        "pairs": [{
            "question_id": i + 1,
            "execution_order": order,
            "observations": [{
                "variant": variant, "input_tokens": 20 if variant == "verbose" else 8,
                "generated_tokens": 2, "elapsed_seconds": 0.2,
                "attention_mask_explicit": True,
                "output": str(i + 1), "exact_public_answer_match": False,
            } for variant in order],
        } for i, order in enumerate(
            [["verbose", "compact"] if j % 2 == 0 else ["compact", "verbose"]
             for j in range(len(QUESTIONS))])],
    }


class PairedDiagnostic(unittest.TestCase):
    def test_valid_fixture(self):
        self.assertTrue(validate_report(fixture()))

    def test_both_variants_distinct(self):
        self.assertNotEqual(VERBOSE, COMPACT)

    def test_rejects_false_training(self):
        r = fixture()
        r["weights_trained_this_run"] = True
        with self.assertRaises(ValueError):
            validate_report(r)

    def test_rejects_false_heldout(self):
        r = fixture()
        r["independent_heldout_accuracy_proven"] = True
        with self.assertRaises(ValueError):
            validate_report(r)

    def test_rejects_false_quality_gain(self):
        r = fixture()
        r["quality_gain"] = 0.1
        with self.assertRaises(ValueError):
            validate_report(r)

    def test_rejects_false_speed_gain(self):
        r = fixture()
        r["speed_gain"] = 0.2
        with self.assertRaises(ValueError):
            validate_report(r)

    def test_rejects_missing_pair(self):
        r = fixture()
        r["pairs"].pop()
        with self.assertRaisesRegex(ValueError, "paired"):
            validate_report(r)

    def test_rejects_fake_order(self):
        r = fixture()
        r["pairs"][0]["execution_order"] = ["compact", "verbose"]
        with self.assertRaisesRegex(ValueError, "order"):
            validate_report(r)

    def test_rejects_observation_order_mismatch(self):
        r = fixture()
        r["pairs"][0]["observations"].reverse()
        with self.assertRaisesRegex(ValueError, "order"):
            validate_report(r)

    def test_rejects_zero_tokens(self):
        r = fixture()
        r["pairs"][0]["observations"][0]["input_tokens"] = 0
        with self.assertRaisesRegex(ValueError, "observation"):
            validate_report(r)

    def test_rejects_nonfinite_latency(self):
        r = fixture()
        r["pairs"][0]["observations"][0]["elapsed_seconds"] = float("nan")
        with self.assertRaisesRegex(ValueError, "observation"):
            validate_report(r)

    def test_rejects_implicit_mask(self):
        r = fixture()
        r["pairs"][0]["observations"][0]["attention_mask_explicit"] = False
        with self.assertRaisesRegex(ValueError, "observation"):
            validate_report(r)

    def test_rejects_invalid_sha(self):
        r = fixture()
        r["weight_files"][0]["sha256"] = "x" * 64
        with self.assertRaisesRegex(ValueError, "weight"):
            validate_report(r)

    def test_rejects_nonpretrained(self):
        r = fixture()
        r["pretrained_checkpoint_loaded"] = False
        with self.assertRaisesRegex(ValueError, "provenance"):
            validate_report(r)

    def test_package_import_from_repo_root(self):
        import subprocess
        run = subprocess.run([sys.executable, "-c",
            "from scripts.oril_v2_slot2_pretrained_paired_diagnostic import validate_report; print(validate_report.__name__)"],
            cwd=str(Path(__file__).resolve().parents[1]),
            capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("validate_report", run.stdout)

    def test_rejects_extra_pair(self):
        r = fixture()
        r["pairs"].append(copy.deepcopy(r["pairs"][-1]))
        with self.assertRaisesRegex(ValueError, "paired"):
            validate_report(r)


if __name__ == "__main__":
    unittest.main()
