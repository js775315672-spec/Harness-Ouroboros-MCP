import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_paired_student_eval import check, evaluate, read

SHA = "a" * 64
MODEL_A = "b" * 64
MODEL_B = "c" * 64


def rows(n=40, *, model=MODEL_A, tokens=100, correct=True):
    return [
        dict(task_id=f"t-{i}", group_id=f"g-{i}", dataset_sha256=SHA,
             model_sha256=model, seed=17, correct=correct,
             input_tokens=tokens, output_tokens=20, latency_ms=100.0)
        for i in range(n)
    ]


class PairedEvaluationTests(unittest.TestCase):
    def test_equal_accuracy_and_25pct_token_reduction_passes(self):
        a, b = rows(), rows(model=MODEL_B, tokens=70)
        report = evaluate(a, b)
        self.assertEqual(report["paired_tasks"], 40)
        self.assertEqual(report["token_reduction_pct"], 25.0)
        self.assertEqual(report["status"], "향상")
        self.assertTrue(report["quality_noninferiority_pass"])
        self.assertFalse(report["independent_evaluation_attested"])
        self.assertFalse(report["gpu_training_attested"])

    def test_unpaired_tasks_rejected(self):
        a, b = rows(), rows()
        b[0]["task_id"] = "different"
        with self.assertRaisesRegex(ValueError, "paired task"):
            evaluate(a, b)

    def test_dataset_mismatch_rejected(self):
        a, b = rows(), rows()
        b[0]["dataset_sha256"] = "d" * 64
        with self.assertRaises(ValueError):
            evaluate(a, b)

    def test_seed_mismatch_rejected(self):
        a, b = rows(), rows()
        b[0]["seed"] = 18
        with self.assertRaisesRegex(ValueError, "dataset/group/seed"):
            evaluate(a, b)

    def test_group_mismatch_rejected(self):
        a, b = rows(), rows()
        b[0]["group_id"] = "other"
        with self.assertRaisesRegex(ValueError, "dataset/group/seed"):
            evaluate(a, b)

    def test_too_few_tasks_never_approves(self):
        r = evaluate(rows(5), rows(5, tokens=50))
        self.assertEqual(r["status"], "판단불가")
        self.assertFalse(r["quality_noninferiority_pass"])

    def test_accuracy_regression_blocks_promotion(self):
        a, b = rows(), rows(model=MODEL_B, tokens=50)
        for x in b[:15]:
            x["correct"] = False
        r = evaluate(a, b)
        self.assertEqual(r["status"], "악화")
        self.assertEqual(r["regressed_cases"], 15)
        self.assertFalse(r["quality_noninferiority_pass"])

    def test_identical_cohort_deterministic(self):
        a, b = rows(), rows(tokens=70)
        self.assertEqual(evaluate(a, b), evaluate(a, list(reversed(b))))

    def test_zero_baseline_tokens_unknown(self):
        a, b = rows(), rows()
        for x in a + b:
            x["input_tokens"] = 0
            x["output_tokens"] = 0
        r = evaluate(a, b)
        self.assertIsNone(r["token_reduction_pct"])
        self.assertNotEqual(r["status"], "향상")

    def test_rejects_forged_negative_tokens(self):
        a = rows()
        a[0]["input_tokens"] = -1
        with self.assertRaisesRegex(ValueError, "token"):
            check(a)

    def test_rejects_nan_latency(self):
        a = rows()
        a[0]["latency_ms"] = float("nan")
        with self.assertRaisesRegex(ValueError, "latency"):
            check(a)

    def test_rejects_boolean_token_count(self):
        a = rows()
        a[0]["input_tokens"] = True
        with self.assertRaisesRegex(ValueError, "token"):
            check(a)

    def test_rejects_duplicate_task_id(self):
        a = rows()
        a.append(copy.deepcopy(a[0]))
        with self.assertRaisesRegex(ValueError, "duplicate task"):
            check(a)

    def test_rejects_inconsistent_model_sha(self):
        a = rows()
        a[0]["model_sha256"] = MODEL_B
        with self.assertRaisesRegex(ValueError, "one dataset and model"):
            check(a)

    def test_rejects_duplicate_json_field(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "in.jsonl"
            path.write_text(json.dumps(rows(1)[0])[:-1] + ',"seed":42}\n')
            with self.assertRaisesRegex(ValueError, "duplicate JSON"):
                read(path)

    def test_cli_does_not_overwrite_input(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            a, b = d / "a.jsonl", d / "b.jsonl"
            a.write_text("\n".join(json.dumps(x) for x in rows()) + "\n")
            b.write_text("\n".join(json.dumps(x) for x in rows(tokens=70)) + "\n")
            cmd = [sys.executable, str(Path(__file__).resolve().parents[1] /
                    "scripts/oril_v2_paired_student_eval.py"),
                   "--baseline", str(a), "--candidate", str(b),
                   "--output", str(a)]
            r = subprocess.run(cmd, capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertEqual(len(a.read_text().splitlines()), 40)

    def test_rejects_empty_input(self):
        with self.assertRaisesRegex(ValueError, "nonempty"):
            evaluate([], rows())

    def test_rejects_missing_field(self):
        a = rows()
        del a[0]["seed"]
        with self.assertRaisesRegex(ValueError, "exact schema"):
            check(a)

    def test_mixed_results_not_automatic_gain(self):
        a, b = rows(), rows(tokens=70)
        b[0]["correct"] = False
        r = evaluate(a, b)
        self.assertFalse(r["quality_noninferiority_pass"])
        self.assertNotEqual(r["status"], "향상")


if __name__ == "__main__":
    unittest.main()
