"""Offline regression tests: teacher-to-student compact examples, not LoRA proof."""
import copy
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_teacher_distillation_pack import compile_examples, load, validate

SHA = "a" * 40
URL = "https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/123"


def case(i, *, split="train", task_type="debug", group=None, **changes):
    out = {
        "case_id": f"case-{i}", "group_id": group or f"group-{i}",
        "split": split, "task_type": task_type,
        "question": f"Find failure mode for sample {i}",
        "teacher_answer": f"Use a bounded verification step for sample {i}.",
        "checks": ["Regression passes", "No unsafe deployment"],
        "quality": 0.95, "review_accepted": True,
        "review_url": URL, "candidate_sha": SHA,
    }
    out.update(changes)
    return out


class DistillTests(unittest.TestCase):
    def test_training_only_does_not_export_hidden_or_validation_answers(self):
        rows = [case(1), case(2, split="validation"),
                case(3, split="heldout", teacher_answer="SECRET_HELDOUT_ANSWER")]
        result, stats = compile_examples(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(stats["heldout_rows"], 1)
        self.assertEqual(stats["validation_rows"], 1)
        self.assertNotIn("SECRET_HELDOUT_ANSWER", json.dumps(result))
        self.assertFalse(stats["heldout_evaluation_performed"])

    def test_approval_assertion_not_independent_certification(self):
        result, stats = compile_examples([case(1)])
        self.assertEqual(len(result), 1)
        self.assertFalse(stats["independent_review_verified"])
        self.assertFalse(stats["student_weights_updated"])
        self.assertIsNone(stats["model_quality_gain"])
        self.assertIsNone(stats["token_count"])

    def test_duplicate_group_across_splits_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "group leakage"):
            compile_examples([case(1, group="same"), case(2, split="heldout", group="same")])

    def test_case_variant_group_id_across_splits_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "group leakage"):
            compile_examples([case(1, group="Repair-42"),
                              case(2, split="heldout", group="repair-42")])

    def test_case_variant_group_within_train_is_permitted(self):
        result, stats = compile_examples([case(1, group="Repair-42"),
                                          case(2, group="repair-42")])
        self.assertEqual(len(result), 2)
        self.assertEqual(stats["selected_train_rows"], 2)

    def test_duplicate_question_normalized_across_splits_rejected(self):
        with self.assertRaisesRegex(ValueError, "question leakage"):
            compile_examples([case(1, question=" Hello   WORLD "),
                              case(2, split="heldout", question="hello world")])

    def test_duplicate_case_id_rejected(self):
        a = case(1)
        b = case(2, case_id=a["case_id"])
        with self.assertRaisesRegex(ValueError, "duplicate case"):
            validate([a, b])

    def test_quality_filters_unreviewed_and_low_confidence(self):
        examples, stats = compile_examples([
            case(1), case(2, quality=0.4), case(3, review_accepted=False),
        ])
        self.assertEqual(len(examples), 1)
        self.assertEqual(stats["train_rows"], 3)

    def test_rejects_nonfinite_quality_and_boolean(self):
        for bad in (float("nan"), float("inf"), True, -0.1, 1.5):
            with self.subTest(bad=str(bad)):
                with self.assertRaisesRegex(ValueError, "quality"):
                    validate([case(1, quality=bad)])

    def test_capped_answers_not_silently_truncated(self):
        a = case(1, teacher_answer="a" * 70)
        b = case(2, teacher_answer="short")
        chosen, _ = compile_examples([a, b], max_answer_chars=20)
        self.assertEqual([x["metadata"]["case_id"] for x in chosen], ["case-2"])

    def test_deterministic_task_diversity(self):
        rows = [case(1, task_type="debug", quality=0.99),
                case(2, task_type="debug", quality=0.98),
                case(3, task_type="risk", quality=0.91)]
        a, stats = compile_examples(rows, max_cases=2)
        b, _ = compile_examples(list(reversed(rows)), max_cases=2)
        self.assertEqual(a, b)
        self.assertEqual({x["metadata"]["task_type"] for x in a}, {"debug", "risk"})
        self.assertEqual(len(stats["selected_task_types"]), 2)

    def test_budget_is_not_token_count(self):
        rows = [case(1), case(2)]
        candidate, stats = compile_examples(rows, max_total_chars=120)
        self.assertLessEqual(stats["selected_chars"], 120)
        self.assertLess(stats["selected_chars"], stats["available_train_chars"])
        self.assertGreater(stats["char_budget_reduction_pct"], 0)
        self.assertIsNone(stats["token_count"])

    def test_duplicate_question_same_split_is_deduplicated(self):
        examples, _ = compile_examples([case(1), case(2, question=case(1)["question"])])
        self.assertEqual(len(examples), 1)

    def test_rejects_missing_schema_fields(self):
        r = case(1)
        del r["candidate_sha"]
        with self.assertRaisesRegex(ValueError, "exact record"):
            validate([r])

    def test_rejects_invalid_source_or_commit(self):
        with self.assertRaisesRegex(ValueError, "review source"):
            validate([case(1, review_url="https://example.org/attestation")])
        with self.assertRaisesRegex(ValueError, "candidate SHA"):
            validate([case(1, candidate_sha="short")])

    def test_rejects_invalid_checks_and_empty_text(self):
        with self.assertRaisesRegex(ValueError, "review checks"):
            validate([case(1, checks=[])])
        with self.assertRaisesRegex(ValueError, "teacher_answer"):
            validate([case(1, teacher_answer="  ")])

    def test_cli_writes_only_training_and_report_without_leak(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            incoming = root / "all.jsonl"
            train = root / "train.jsonl"
            report = root / "report.json"
            incoming.write_text("\n".join(json.dumps(x) for x in [
                case(1), case(2, split="heldout", teacher_answer="SECRET-DO-NOT-OUTPUT"),
            ]) + "\n")
            run = subprocess.run(
                [sys.executable, str(Path(__file__).resolve().parents[1] /
                                    "scripts" / "oril_v2_teacher_distillation_pack.py"),
                 "--input", str(incoming), "--output-train", str(train),
                 "--output-report", str(report)],
                check=False, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertNotIn("SECRET-DO-NOT-OUTPUT", train.read_text())
            self.assertNotIn("SECRET-DO-NOT-OUTPUT", report.read_text())
            self.assertEqual(json.loads(report.read_text())["selected_train_rows"], 1)

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "duplicate.jsonl"
            row = json.dumps(case(1))
            path.write_text(row[:-1] + ',"case_id":"another"}\n')
            with self.assertRaisesRegex(ValueError, "duplicate JSON"):
                load(path)

    def test_no_eligible_teacher_cases_is_explicit(self):
        result, stats = compile_examples([case(1, review_accepted=False)])
        self.assertEqual(result, [])
        self.assertEqual(stats["selected_train_rows"], 0)

    def test_rejects_invalid_budget(self):
        with self.assertRaisesRegex(ValueError, "budgets"):
            compile_examples([case(1)], max_cases=0)

    def test_two_files_cannot_share_output_path(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "input.jsonl"
            report = Path(root) / "report.json"
            path.write_text(json.dumps(case(1)) + "\n")
            run = subprocess.run([
                sys.executable,
                str(Path(__file__).resolve().parents[1] / "scripts" /
                    "oril_v2_teacher_distillation_pack.py"),
                "--input", str(path), "--output-train", str(path),
                "--output-report", str(report)
            ], capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertEqual(len(path.read_text().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
