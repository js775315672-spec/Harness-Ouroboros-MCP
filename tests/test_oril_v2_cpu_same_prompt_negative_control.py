"""Offline contract tests; mocked measurements are not real CPU inference."""
import copy
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import oril_v2_cpu_same_prompt_negative_control as control


def sample(i):
    a = {"input_tokens": 5, "output_tokens": 2, "elapsed_seconds": 1.0 + i * .1}
    b = {"input_tokens": 5, "output_tokens": 2, "elapsed_seconds": 1.2 + i * .1}
    return {"order": "a_first" if i % 2 == 0 else "b_first", "a": a, "b": b}


class SamePromptNegativeControlTests(unittest.TestCase):
    def test_noise_report_cannot_claim_quality(self):
        r = control.summarize_negative_control([sample(i) for i in range(6)])
        self.assertEqual(r["n_real_generations"], 12)
        self.assertAlmostEqual(r["b_minus_a_seconds_median"], .2)
        self.assertFalse(r["speed_gain_verified"])
        self.assertFalse(r["pretrained_weights"])
        self.assertFalse(r["lora_adapter_created"])
        self.assertIsNone(r["heldout_quality_gain"])
        self.assertIsNone(r["negative_control_passed"])

    def test_order_balance_and_observed_orders(self):
        r = control.summarize_negative_control([sample(i) for i in range(6)])
        self.assertEqual(r["order_counts"], {"a_first": 3, "b_first": 3})
        self.assertEqual(r["observed_orders"], ["a_first", "b_first"] * 3)

    def test_same_prompt_token_mismatch_rejected(self):
        p = [sample(i) for i in range(4)]
        p[0]["b"]["input_tokens"] = 9
        with self.assertRaisesRegex(ValueError, "same prompt"):
            control.summarize_negative_control(p)

    def test_nan_and_bool_rejected(self):
        for value in (float("nan"), float("inf"), True, -1):
            p = [sample(i) for i in range(4)]
            p[0]["a"]["elapsed_seconds"] = value
            with self.subTest(value=str(value)):
                with self.assertRaisesRegex(ValueError, "measured value"):
                    control.summarize_negative_control(p)

    def test_single_order_rejected(self):
        p = [sample(i) for i in range(4)]
        for x in p:
            x["order"] = "a_first"
        with self.assertRaisesRegex(ValueError, "both orders"):
            control.summarize_negative_control(p)

    def test_invalid_pairs_rejected(self):
        with self.assertRaisesRegex(ValueError, "four pairs"):
            control.summarize_negative_control([sample(0)])
        p = [sample(i) for i in range(4)]
        p[0]["order"] = "guessed"
        with self.assertRaisesRegex(ValueError, "observed order"):
            control.summarize_negative_control(p)

    def test_real_runner_order_alternates_with_same_question(self):
        calls = []
        def fake_invoke(adapter, model_dir, question):
            calls.append(question)
            return {"input_tokens": 5, "output_tokens": 2,
                    "elapsed_seconds": 1.0}
        with patch.object(control, "build_tiny_checkpoint", return_value="a" * 64), \
             patch.object(control, "invoke", side_effect=fake_invoke):
            r = control.run(4)
        self.assertEqual(len(calls), 8)
        self.assertTrue(all(x == control.SHORT for x in calls))
        self.assertEqual(r["observed_orders"], ["a_first", "b_first"] * 2)

    def test_odd_or_excessive_runs_rejected(self):
        for n in (0, 3, 5, 21, True):
            with self.subTest(n=n):
                with self.assertRaisesRegex(ValueError, "even"):
                    control.run(n)


if __name__ == "__main__":
    unittest.main()
