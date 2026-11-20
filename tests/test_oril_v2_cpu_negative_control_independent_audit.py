"""Independent negative-control report auditor regression tests."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_cpu_negative_control_independent_audit import audit, unique


def fixture():
    pairs = []
    for order, a, b in [("a_first", 1, 2), ("b_first", 3, 2),
                        ("a_first", 4, 5), ("b_first", 6, 5)]:
        pairs.append({"order": order, "a_elapsed_seconds": a,
                      "b_elapsed_seconds": b, "input_tokens": 10})
    return {
        "schema_version": 1,
        "experiment": "tiny_random_weight_qwen2_cpu_same_prompt_negative_control",
        "raw_pairs": pairs,
        "n_pairs": 4, "n_real_generations": 8,
        "observed_orders": ["a_first", "b_first", "a_first", "b_first"],
        "order_counts": {"a_first": 2, "b_first": 2},
        "b_minus_a_seconds_median": 0,
        "b_minus_a_seconds_median_by_order": {"a_first": 1, "b_first": -1},
        "absolute_paired_difference_seconds_median": 1,
        "same_prompt_both_conditions": True,
        "speed_gain_verified": False, "pretrained_weights": False,
        "gpu_used": False, "lora_adapter_created": False,
        "optimizer_steps": 0, "heldout_quality_gain": None,
        "negative_control_passed": None,
    }


class AuditTests(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(audit(fixture())["audited_pairs"], 4)

    def test_never_certifies_speed_or_quality(self):
        result = audit(fixture())
        self.assertIsNone(result["model_speed_improved"])
        self.assertIsNone(result["model_quality_improved"])
        self.assertFalse(result["execution_provenance_independently_attested"])

    def test_tampered_pooled_median(self):
        r = fixture()
        r["b_minus_a_seconds_median"] = 0.9
        with self.assertRaisesRegex(ValueError, "median"):
            audit(r)

    def test_tampered_absolute_noise(self):
        r = fixture()
        r["absolute_paired_difference_seconds_median"] = 0
        with self.assertRaisesRegex(ValueError, "absolute"):
            audit(r)

    def test_tampered_order_median(self):
        r = fixture()
        r["b_minus_a_seconds_median_by_order"]["b_first"] = 1
        with self.assertRaisesRegex(ValueError, "order median"):
            audit(r)

    def test_tampered_counts(self):
        r = fixture()
        r["n_real_generations"] = 9
        with self.assertRaisesRegex(ValueError, "generation"):
            audit(r)

    def test_tampered_observed_order(self):
        r = fixture()
        r["observed_orders"][0] = "b_first"
        with self.assertRaisesRegex(ValueError, "order summary"):
            audit(r)

    def test_unbalanced_order(self):
        r = fixture()
        r["raw_pairs"][0]["order"] = "b_first"
        with self.assertRaisesRegex(ValueError, "unbalanced"):
            audit(r)

    def test_negative_elapsed(self):
        r = fixture()
        r["raw_pairs"][0]["a_elapsed_seconds"] = -1
        with self.assertRaisesRegex(ValueError, "elapsed"):
            audit(r)

    def test_boolean_elapsed(self):
        r = fixture()
        r["raw_pairs"][0]["a_elapsed_seconds"] = True
        with self.assertRaisesRegex(ValueError, "elapsed"):
            audit(r)

    def test_false_model_claim(self):
        for field in ("speed_gain_verified", "pretrained_weights",
                      "gpu_used", "lora_adapter_created"):
            with self.subTest(field=field):
                r = fixture()
                r[field] = True
                with self.assertRaisesRegex(ValueError, "false positive"):
                    audit(r)

    def test_no_optimizer_or_heldout_claim(self):
        r = fixture()
        r["optimizer_steps"] = 1
        with self.assertRaisesRegex(ValueError, "optimizer"):
            audit(r)
        r = fixture()
        r["heldout_quality_gain"] = 0.2
        with self.assertRaisesRegex(ValueError, "heldout"):
            audit(r)

    def test_duplicate_json_key(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON"):
            json.loads('{"x":1,"x":2}', object_pairs_hook=unique)

    def test_cli_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "report.json"
            f.write_text(json.dumps(fixture()))
            tool = Path(__file__).resolve().parents[1] / "scripts" / "oril_v2_cpu_negative_control_independent_audit.py"
            r = subprocess.run([sys.executable, str(tool), "--input", str(f)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(json.loads(r.stdout)["raw_arithmetic_consistent"])


if __name__ == "__main__":
    unittest.main()
