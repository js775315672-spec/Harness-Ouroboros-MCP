"""A/A pretrained Qwen public30 null-control offline mutation tests."""
import copy
import math
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_slot1_30_public_qwen_pairs import public_tasks
from oril_v2_slot3_public30_pretrained_aa_null import audit_null


def fixture():
    rows = []
    for task in public_tasks():
        observations = []
        for i in range(2):
            observations.append({
                "variant": "compact", "input_tokens": 20,
                "generated_tokens": 2, "elapsed_seconds": 0.5 + i * 0.02,
                "attention_mask_explicit": True, "output": task["expected"],
                "exact_public_answer_match": True,
            })
        rows.append({**task, "observations": observations})
    return rows


class AANullTests(unittest.TestCase):
    def test_30_groups_60_calls_and_no_quality_claim(self):
        report = audit_null(fixture())
        self.assertEqual(report["public_groups"], 30)
        self.assertEqual(report["actual_calls_claimed"], 60)
        self.assertFalse(report["causal_speed_gain_proven"])
        self.assertFalse(report["independent_heldout_accuracy_proven"])
        self.assertFalse(report["gpu_lora_training_proven"])
        self.assertEqual(report["decision"], "판단불가")

    def test_known_signed_drift(self):
        report = audit_null(fixture())
        self.assertAlmostEqual(report["median_signed_second_minus_first_seconds"], 0.02)
        self.assertAlmostEqual(report["median_absolute_pair_drift_seconds"], 0.02)

    def test_missing_group(self):
        with self.assertRaisesRegex(ValueError, "30 public"):
            audit_null(fixture()[:-1])

    def test_duplicate_group(self):
        rows = fixture()
        rows[1] = copy.deepcopy(rows[0])
        with self.assertRaisesRegex(ValueError, "reordered"):
            audit_null(rows)

    def test_question_tamper(self):
        rows = fixture()
        rows[0]["question"] = "untrusted"
        with self.assertRaisesRegex(ValueError, "reordered"):
            audit_null(rows)

    def test_expected_tamper(self):
        rows = fixture()
        rows[0]["expected"] = "0"
        with self.assertRaisesRegex(ValueError, "reordered"):
            audit_null(rows)

    def test_missing_observation(self):
        rows = fixture()
        rows[0]["observations"].pop()
        with self.assertRaisesRegex(ValueError, "exactly two"):
            audit_null(rows)

    def test_variant_tamper(self):
        rows = fixture()
        rows[0]["observations"][1]["variant"] = "verbose"
        with self.assertRaisesRegex(ValueError, "identical compact"):
            audit_null(rows)

    def test_token_mismatch(self):
        rows = fixture()
        rows[0]["observations"][1]["input_tokens"] = 21
        with self.assertRaisesRegex(ValueError, "token counts"):
            audit_null(rows)

    def test_zero_tokens(self):
        rows = fixture()
        rows[0]["observations"][0]["input_tokens"] = 0
        with self.assertRaisesRegex(ValueError, "input tokens"):
            audit_null(rows)

    def test_nonfinite_latency(self):
        for bad in (float("nan"), float("inf"), 0, -1, True):
            rows = fixture()
            rows[0]["observations"][0]["elapsed_seconds"] = bad
            with self.subTest(bad=str(bad)), self.assertRaisesRegex(ValueError, "timing"):
                audit_null(rows)

    def test_false_public_label(self):
        rows = fixture()
        rows[0]["observations"][0]["exact_public_answer_match"] = False
        with self.assertRaisesRegex(ValueError, "public label"):
            audit_null(rows)

    def test_missing_mask(self):
        rows = fixture()
        rows[0]["observations"][0]["attention_mask_explicit"] = False
        with self.assertRaisesRegex(ValueError, "model output"):
            audit_null(rows)

    def test_empty_output(self):
        rows = fixture()
        rows[0]["observations"][0]["output"] = ""
        with self.assertRaisesRegex(ValueError, "model output"):
            audit_null(rows)

    def test_invalid_generated_tokens(self):
        rows = fixture()
        rows[0]["observations"][0]["generated_tokens"] = 17
        with self.assertRaisesRegex(ValueError, "output tokens"):
            audit_null(rows)

    def test_order_sensitivity_not_conflated_with_quality(self):
        rows = fixture()
        for row in rows:
            row["observations"][0]["elapsed_seconds"] = 1.0
            row["observations"][1]["elapsed_seconds"] = 0.5
        stats = audit_null(rows)
        self.assertEqual(stats["median_signed_second_minus_first_seconds"], -0.5)
        self.assertFalse(stats["causal_speed_gain_proven"])


if __name__ == "__main__":
    unittest.main()
