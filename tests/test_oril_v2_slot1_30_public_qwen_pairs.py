"""Offline validation for 30-public-question real Qwen CPU experiment."""
import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_slot1_30_public_qwen_pairs import public_tasks, summarize


def rows():
    out = []
    for i, task in enumerate(public_tasks()):
        order = ["verbose", "compact"] if i % 2 == 0 else ["compact", "verbose"]
        obs = []
        for variant in order:
            obs.append({
                "variant": variant, "input_tokens": 80 if variant == "verbose" else 30,
                "elapsed_seconds": 0.2 if variant == "verbose" else 0.1,
                "output": task["expected"], "exact_public_answer_match": True,
                "attention_mask_explicit": True,
            })
        out.append({**task, "execution_order": order, "observations": obs})
    return out


class PublicQwenTests(unittest.TestCase):
    def test_deterministic_unique_30_groups(self):
        self.assertEqual(public_tasks(), public_tasks())
        self.assertEqual(len({x["question"] for x in public_tasks()}), 30)

    def test_math_answers_independently_computed(self):
        for i, task in enumerate(public_tasks()):
            self.assertEqual(int(task["expected"]), 11 + i*3 + 2 + i%7)

    def test_60_observations_and_token_arithmetic(self):
        s = summarize(rows())
        self.assertEqual(s["actual_calls_claimed"], 60)
        self.assertEqual(s["input_tokens"], {"verbose": 2400, "compact": 900})
        self.assertEqual(s["public_exact_matches"], {"verbose": 30, "compact": 30})
        self.assertEqual(s["input_token_saving_pct_descriptive"], 62.5)

    def test_no_false_gain_or_heldout_claim(self):
        s = summarize(rows())
        for key in ("quality_gain_proven", "speed_gain_proven",
                    "independent_heldout_accuracy_proven", "gpu_lora_training_proven"):
            self.assertFalse(s[key])
        self.assertEqual(s["decision"], "판단불가")

    def test_rejects_missing_group(self):
        with self.assertRaisesRegex(ValueError, "30"):
            summarize(rows()[:-1])

    def test_rejects_duplicate_group(self):
        r = rows()
        r[1]["group_id"] = r[0]["group_id"]
        with self.assertRaises(ValueError):
            summarize(r)

    def test_rejects_question_drift(self):
        r = rows()
        r[0]["question"] = "What is 1 plus 1?"
        with self.assertRaisesRegex(ValueError, "question"):
            summarize(r)

    def test_rejects_answer_drift(self):
        r = rows()
        r[0]["expected"] = "999"
        with self.assertRaisesRegex(ValueError, "answer"):
            summarize(r)

    def test_rejects_order_drift(self):
        r = rows()
        r[1]["execution_order"] = ["verbose", "compact"]
        with self.assertRaisesRegex(ValueError, "counterbalanced"):
            summarize(r)

    def test_rejects_missing_observation(self):
        r = rows()
        r[0]["observations"].pop()
        with self.assertRaisesRegex(ValueError, "observations"):
            summarize(r)

    def test_rejects_self_reported_false_positive(self):
        r = rows()
        r[0]["observations"][0]["output"] = "wrong"
        with self.assertRaisesRegex(ValueError, "self-reported"):
            summarize(r)

    def test_rejects_self_reported_false_negative(self):
        r = rows()
        r[0]["observations"][0]["exact_public_answer_match"] = False
        with self.assertRaisesRegex(ValueError, "self-reported"):
            summarize(r)

    def test_rejects_boolean_tokens(self):
        r = rows()
        r[0]["observations"][0]["input_tokens"] = True
        with self.assertRaisesRegex(ValueError, "tokens"):
            summarize(r)

    def test_rejects_zero_timing(self):
        r = rows()
        r[0]["observations"][0]["elapsed_seconds"] = 0
        with self.assertRaisesRegex(ValueError, "timing"):
            summarize(r)

    def test_rejects_missing_mask(self):
        r = rows()
        r[0]["observations"][0]["attention_mask_explicit"] = False
        with self.assertRaisesRegex(ValueError, "mask"):
            summarize(r)


if __name__ == "__main__":
    unittest.main()
