"""Mutation tests for independent public-30 raw audit. No GPU dependencies."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_slot2_public30_independent_audit import audit, read_unique


def fixture():
    rows = []
    tasks = []
    for i in range(30):
        a, b = 11+3*i, 2+i%7
        task = {"group_id": f"public-arithmetic-{i+1:02d}",
                "question": f"What is {a} plus {b}? Answer with only the integer.",
                "expected": str(a+b)}
        tasks.append(task)
        order = ["verbose", "compact"] if i%2 == 0 else ["compact", "verbose"]
        rows.append({**task, "execution_order": order,
                     "observations": [
                         {"variant": v, "input_tokens": 60 if v == "verbose" else 30,
                          "elapsed_seconds": .2 if v == "verbose" else .1,
                          "output": task["expected"], "exact_public_answer_match": True,
                          "attention_mask_explicit": True} for v in order]})
    return {
        "schema_version": 1, "model_id": "Qwen/Qwen2.5-0.5B-Instruct",
        "resolved_revision": "a"*40,
        "weight_files": [{"name": "model.safetensors", "bytes": 100,
                          "sha256": "b"*64}],
        "public_tasks_sha256": hashlib.sha256(json.dumps(tasks, sort_keys=True).encode()).hexdigest(),
        "pretrained_checkpoint_loaded": True, "weights_trained_this_run": False,
        "gpu_lora_training_proven": False,
        "independent_heldout_accuracy_proven": False,
        "quality_gain": None, "speed_gain": None,
        "rows": rows,
        "summary": {
            "public_groups": 30, "actual_calls_claimed": 60,
            "input_tokens": {"verbose": 1800, "compact": 900},
            "public_exact_matches": {"verbose": 30, "compact": 30},
            "latency_median_seconds": {"verbose": .2, "compact": .1},
            "input_token_saving_pct_descriptive": 50.,
            "quality_gain_proven": False, "speed_gain_proven": False,
            "independent_heldout_accuracy_proven": False,
            "gpu_lora_training_proven": False, "decision": "판단불가",
        }
    }


class AuditTests(unittest.TestCase):
    def test_valid_30_pairs(self):
        out = audit(fixture())
        self.assertEqual(out["raw_calls"], 60)
        self.assertEqual(out["token_saving_pct_descriptive"], 50.)
        self.assertEqual(out["paired_accuracy_discordance"]["compact_only_correct"], 0)
        self.assertFalse(out["actual_calls_independently_attested"])
        self.assertFalse(out["heldout_quality_proven"])

    def test_rejects_forged_total(self):
        r = fixture()
        r["summary"]["input_tokens"]["compact"] = 899
        with self.assertRaisesRegex(ValueError, "summary"):
            audit(r)

    def test_rejects_forged_accuracy(self):
        r = fixture()
        r["rows"][0]["observations"][0]["output"] = "wrong"
        with self.assertRaisesRegex(ValueError, "label"):
            audit(r)

    def test_rejects_missing_pair(self):
        r = fixture()
        r["rows"].pop()
        with self.assertRaisesRegex(ValueError, "30"):
            audit(r)

    def test_rejects_reordered_pair(self):
        r = fixture()
        r["rows"][0]["observations"].reverse()
        with self.assertRaisesRegex(ValueError, "variant"):
            audit(r)

    def test_rejects_wrong_task(self):
        r = fixture()
        r["rows"][2]["question"] = "different"
        with self.assertRaisesRegex(ValueError, "question"):
            audit(r)

    def test_rejects_false_training(self):
        r = fixture()
        r["weights_trained_this_run"] = True
        with self.assertRaisesRegex(ValueError, "training"):
            audit(r)

    def test_rejects_false_heldout(self):
        r = fixture()
        r["independent_heldout_accuracy_proven"] = True
        with self.assertRaisesRegex(ValueError, "training"):
            audit(r)

    def test_rejects_false_quality_gain(self):
        r = fixture()
        r["quality_gain"] = 0.3
        with self.assertRaisesRegex(ValueError, "gain"):
            audit(r)

    def test_rejects_nonfinite_timing(self):
        r = fixture()
        r["rows"][0]["observations"][0]["elapsed_seconds"] = float("nan")
        with self.assertRaisesRegex(ValueError, "latency"):
            audit(r)

    def test_rejects_boolean_tokens(self):
        r = fixture()
        r["rows"][0]["observations"][0]["input_tokens"] = True
        with self.assertRaisesRegex(ValueError, "token"):
            audit(r)

    def test_rejects_invalid_weights(self):
        r = fixture()
        r["weight_files"][0]["sha256"] = "bad"
        with self.assertRaisesRegex(ValueError, "weight"):
            audit(r)

    def test_rejects_task_hash_mismatch(self):
        r = fixture()
        r["public_tasks_sha256"] = "0"*64
        with self.assertRaisesRegex(ValueError, "SHA"):
            audit(r)

    def test_rejects_duplicate_json_keys(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"x.json"
            p.write_text('{"a":1,"a":2}')
            with self.assertRaisesRegex(ValueError, "duplicate JSON"):
                read_unique(p)

    def test_rejects_missing_mask(self):
        r = fixture()
        r["rows"][0]["observations"][0]["attention_mask_explicit"] = False
        with self.assertRaisesRegex(ValueError, "mask"):
            audit(r)


if __name__ == "__main__":
    unittest.main()
