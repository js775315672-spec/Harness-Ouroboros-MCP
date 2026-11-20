"""Regression tests for independently recomputed public Qwen paired observations."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_slot5_public_answer_independent_audit import audit, unique_keys

def fixture():
    pairs = []
    for i, expected in enumerate(("5", "3", "9", "4")):
        order = ["verbose", "compact"] if i % 2 == 0 else ["compact", "verbose"]
        pairs.append({"question_id": i + 1, "execution_order": order,
                      "observations": [{"variant": k, "input_tokens": 100 if k == "verbose" else 40,
                                        "generated_tokens": 2, "elapsed_seconds": 0.2,
                                        "attention_mask_explicit": True,
                                        "output": expected,
                                        "exact_public_answer_match": True} for k in order]})
    return {"schema_version": 1, "model_id": "Qwen/Qwen2.5-0.5B-Instruct",
            "resolved_revision": "a" * 40,
            "weight_files": [{"name": "model.safetensors", "bytes": 100, "sha256": "b" * 64}],
            "pretrained_checkpoint_loaded": True,
            "weights_trained_this_run": False, "gpu_lora_training_proven": False,
            "independent_heldout_accuracy_proven": False, "quality_gain": None,
            "speed_gain": None, "pairs": pairs}

class AuditTests(unittest.TestCase):
    def test_correct_public_answers_recomputed(self):
        x = audit(fixture())
        self.assertEqual(x["public_exact_matches_recomputed"], {"verbose": 4, "compact": 4})
        self.assertEqual(x["input_tokens_recomputed"], {"verbose": 400, "compact": 160})
        self.assertEqual(x["input_token_saving_pct_descriptive"], 60)
        self.assertEqual(x["decision"], "판단불가")
        self.assertFalse(x["independent_heldout_accuracy_proven"])

    def test_wrong_output_false_label_is_valid_observation(self):
        x = fixture()
        x["pairs"][0]["observations"][0]["output"] = "wrong"
        x["pairs"][0]["observations"][0]["exact_public_answer_match"] = False
        out = audit(x)
        self.assertEqual(out["public_exact_matches_recomputed"]["verbose"], 3)

    def test_wrong_output_falsely_claims_correct(self):
        x = fixture()
        x["pairs"][0]["observations"][0]["output"] = "wrong"
        with self.assertRaisesRegex(ValueError, "disagrees"):
            audit(x)

    def test_correct_output_falsely_claims_wrong(self):
        x = fixture()
        x["pairs"][0]["observations"][0]["exact_public_answer_match"] = False
        with self.assertRaisesRegex(ValueError, "disagrees"):
            audit(x)

    def test_whitespace_trim_exactness(self):
        x = fixture()
        x["pairs"][0]["observations"][0]["output"] = " 5\n"
        self.assertEqual(audit(x)["public_exact_matches_recomputed"]["verbose"], 4)

    def test_no_substring_match(self):
        x = fixture()
        x["pairs"][0]["observations"][0]["output"] = "Answer: 5"
        x["pairs"][0]["observations"][0]["exact_public_answer_match"] = False
        self.assertEqual(audit(x)["public_exact_matches_recomputed"]["verbose"], 3)

    def test_rejects_order_mutation(self):
        x = fixture()
        x["pairs"][0]["execution_order"].reverse()
        with self.assertRaisesRegex(ValueError, "order"):
            audit(x)

    def test_rejects_variant_swap(self):
        x = fixture()
        x["pairs"][0]["observations"][0]["variant"] = "compact"
        with self.assertRaisesRegex(ValueError, "variant"):
            audit(x)

    def test_rejects_duplicate_question(self):
        x = fixture()
        x["pairs"][1]["question_id"] = 1
        with self.assertRaisesRegex(ValueError, "question"):
            audit(x)

    def test_rejects_missing_pair(self):
        x = fixture()
        x["pairs"].pop()
        with self.assertRaisesRegex(ValueError, "four public"):
            audit(x)

    def test_rejects_nonfinite_latency(self):
        x = fixture()
        x["pairs"][0]["observations"][0]["elapsed_seconds"] = float("nan")
        with self.assertRaisesRegex(ValueError, "timing"):
            audit(x)

    def test_rejects_boolean_token_count(self):
        x = fixture()
        x["pairs"][0]["observations"][0]["input_tokens"] = True
        with self.assertRaisesRegex(ValueError, "token"):
            audit(x)

    def test_rejects_false_gpu_training(self):
        x = fixture()
        x["gpu_lora_training_proven"] = True
        with self.assertRaisesRegex(ValueError, "unproven"):
            audit(x)

    def test_rejects_false_heldout(self):
        x = fixture()
        x["independent_heldout_accuracy_proven"] = True
        with self.assertRaisesRegex(ValueError, "unproven"):
            audit(x)

    def test_rejects_invalid_checkpoint(self):
        x = fixture()
        x["resolved_revision"] = "bad"
        with self.assertRaisesRegex(ValueError, "revision"):
            audit(x)

    def test_rejects_invalid_weight_sha(self):
        x = fixture()
        x["weight_files"][0]["sha256"] = "bad"
        with self.assertRaisesRegex(ValueError, "weight"):
            audit(x)

    def test_rejects_duplicate_json_key(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            json.loads('{"a":1,"a":2}', object_pairs_hook=unique_keys)

    def test_cli_produces_independent_report(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "raw.json"
            dest = Path(td) / "audit.json"
            src.write_text(json.dumps(fixture()))
            script = Path(__file__).resolve().parents[1] / "scripts" / "oril_v2_slot5_public_answer_independent_audit.py"
            r = subprocess.run([sys.executable, str(script), "--input", str(src),
                                "--output", str(dest)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(dest.read_text())["public_questions"], 4)

    def test_cli_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "raw.json"
            src.write_text(json.dumps(fixture()))
            script = Path(__file__).resolve().parents[1] / "scripts" / "oril_v2_slot5_public_answer_independent_audit.py"
            r = subprocess.run([sys.executable, str(script), "--input", str(src),
                                "--output", str(src)], capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertEqual(json.loads(src.read_text())["schema_version"], 1)

if __name__ == "__main__":
    unittest.main()
