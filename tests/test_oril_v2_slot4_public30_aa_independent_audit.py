import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_slot4_public30_aa_independent_audit import audit, read_unique


def fixture():
    tasks, rows = [], []
    for i in range(30):
        a, b = 11 + i*3, 2 + i % 7
        task = {"group_id": f"public-arithmetic-{i+1:02d}",
                "question": f"What is {a} plus {b}? Answer with only the integer.",
                "expected": str(a+b)}
        tasks.append(task)
        obs = []
        for j in range(2):
            obs.append({"variant": "compact", "input_tokens": 22+i,
                        "generated_tokens": 2, "elapsed_seconds": 1.0 + 0.1*j + i/100,
                        "attention_mask_explicit": True,
                        "output": task["expected"], "exact_public_answer_match": True})
        rows.append({**task, "observations": obs})
    return {
        "schema_version": 1, "model_id": "Qwen/Qwen2.5-0.5B-Instruct",
        "resolved_revision": "a"*40,
        "weight_files": [{"name": "model.safetensors", "bytes": 1024, "sha256": "b"*64}],
        "pretrained_checkpoint_loaded": True,
        "weights_trained_this_run": False,
        "gpu_lora_training_proven": False,
        "independent_heldout_accuracy_proven": False,
        "quality_gain": None, "speed_gain": None,
        "public_tasks_sha256": hashlib.sha256(json.dumps(tasks, sort_keys=True).encode()).hexdigest(),
        "rows": rows,
        "summary": {
            "public_groups": 30, "actual_calls_claimed": 60,
            "same_prompt_token_count_mismatches": 0,
            "median_signed_second_minus_first_seconds": 0.1,
            "median_absolute_pair_drift_seconds": 0.1,
            "median_call_seconds": 1.195,
            "compact_input_tokens_per_call_total": sum(22+i for i in range(30)),
            "independent_heldout_accuracy_proven": False,
            "gpu_lora_training_proven": False,
            "model_quality_gain_proven": False,
            "causal_speed_gain_proven": False,
            "decision": "판단불가",
        },
    }


class TestIndependentNull(unittest.TestCase):
    def test_consistent_raw_null(self):
        r = audit(fixture())
        self.assertEqual(r["groups"], 30)
        self.assertEqual(r["reported_calls"], 60)
        self.assertEqual(r["public_exact_matches_first"], 30)
        self.assertFalse(r["actual_model_calls_independently_attested"])
        self.assertFalse(r["causal_speed_gain_proven"])

    def test_forged_summary_median(self):
        x = fixture()
        x["summary"]["median_absolute_pair_drift_seconds"] = 0.001
        with self.assertRaisesRegex(ValueError, "summary"):
            audit(x)

    def test_wrong_question(self):
        x = fixture()
        x["rows"][0]["question"] = "another"
        with self.assertRaisesRegex(ValueError, "task"):
            audit(x)

    def test_missing_call(self):
        x = fixture()
        x["rows"][0]["observations"].pop()
        with self.assertRaisesRegex(ValueError, "two"):
            audit(x)

    def test_same_prompt_tokens_must_match(self):
        x = fixture()
        x["rows"][0]["observations"][1]["input_tokens"] += 1
        with self.assertRaisesRegex(ValueError, "token mismatch"):
            audit(x)

    def test_label_must_match_raw_output(self):
        x = fixture()
        x["rows"][0]["observations"][0]["output"] = "WRONG"
        with self.assertRaisesRegex(ValueError, "label"):
            audit(x)

    def test_false_lora_claim_rejected(self):
        x = fixture()
        x["gpu_lora_training_proven"] = True
        with self.assertRaisesRegex(ValueError, "false model"):
            audit(x)

    def test_false_heldout_claim_rejected(self):
        x = fixture()
        x["independent_heldout_accuracy_proven"] = True
        with self.assertRaisesRegex(ValueError, "false model"):
            audit(x)

    def test_negative_latency_rejected(self):
        x = fixture()
        x["rows"][0]["observations"][0]["elapsed_seconds"] = -1
        with self.assertRaisesRegex(ValueError, "timing"):
            audit(x)

    def test_nan_latency_rejected(self):
        x = fixture()
        x["rows"][0]["observations"][0]["elapsed_seconds"] = float("nan")
        with self.assertRaisesRegex(ValueError, "timing"):
            audit(x)

    def test_forged_task_digest_rejected(self):
        x = fixture()
        x["public_tasks_sha256"] = "0"*64
        with self.assertRaisesRegex(ValueError, "digest"):
            audit(x)

    def test_invalid_weights_rejected(self):
        x = fixture()
        x["weight_files"][0]["sha256"] = "fake"
        with self.assertRaisesRegex(ValueError, "weight"):
            audit(x)

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.json"
            path.write_text('{"schema_version":1,"schema_version":2}')
            with self.assertRaisesRegex(ValueError, "duplicate JSON"):
                read_unique(path)

    def test_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.json"
            path.write_text('{"elapsed":NaN}')
            with self.assertRaisesRegex(ValueError, "nonfinite JSON"):
                read_unique(path)

    def test_wrong_model_rejected(self):
        x = fixture()
        x["model_id"] = "random-weights"
        with self.assertRaisesRegex(ValueError, "model revision"):
            audit(x)

    def test_boolean_timing_rejected(self):
        x = fixture()
        x["rows"][0]["observations"][0]["elapsed_seconds"] = True
        with self.assertRaisesRegex(ValueError, "timing"):
            audit(x)


if __name__ == "__main__":
    unittest.main()
