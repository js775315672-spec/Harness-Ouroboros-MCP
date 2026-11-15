"""Offline, no-model tests for a second independent Qwen source repair."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from qwen_second_task_trial import (
    TASK_ID, MAX_ATTEMPTS, LOG_ORIGINAL, normalize_expression, make_candidate,
    stage, evaluate, trial, hash_data, BASE_TEST, NEGATIVE_TEST, PROMPT
)
from qwen_source_guard import TARGET
from verified_model_patch_review import inspect_proposal

EVIDENCE = ROOT / "proposals/feedback_cycle_guard_7b.json"
EXPR = r"'\x00' in log or '\x1b' in log"


class FixedResponse:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
    def generate(self, prompt):
        self.calls.append(prompt)
        return next(self.responses)


def first_task():
    record, _ = inspect_proposal(ROOT, EVIDENCE)
    return record


def fake_docker_ok(workspace, pattern):
    target = (Path(workspace) / TARGET).read_text(encoding="utf-8")
    if first_task()["candidate_line"] not in target:
        raise ValueError("first independent patch not staged")
    changed = LOG_ORIGINAL not in target
    if pattern == BASE_TEST:
        return {"passed": True, "tests_run": 8, "exit_code": 0,
                "network_disabled": True, "filesystem_read_only": True,
                "privileges_dropped": True}
    if pattern == NEGATIVE_TEST:
        return {"passed": changed, "tests_run": 3,
                "exit_code": 0 if changed else 1,
                "network_disabled": True, "filesystem_read_only": True,
                "privileges_dropped": True}
    raise ValueError("unexpected Docker pattern")


class SecondTaskTests(unittest.TestCase):
    def test_prompt_identifies_escaped_literals_without_full_answer(self):
        self.assertIn("NOT Python variable names", PROMPT)
        self.assertIn(r"\x00", PROMPT)
        self.assertIn(r"\x1b", PROMPT)
        self.assertNotIn(EXPR, PROMPT)
        self.assertNotIn("NUL in log or ESC in log", PROMPT)

    def test_only_safe_two_control_expression_accepted(self):
        self.assertEqual(normalize_expression(EXPR), EXPR)
        self.assertEqual(normalize_expression(EXPR.replace(" or ", " or ")), EXPR)
        self.assertEqual(normalize_expression("```python\n" + EXPR + "\n```"), EXPR)
        self.assertEqual(normalize_expression("`" + EXPR + "`"), EXPR)
        for bad in (r"'\x00' in log", r"'\x00' in log or '\x00' in log",
                    r"'\n' in log or '\x1b' in log",
                    "import os", "__import__('os').system('id')",
                    "log.clear()", r"'\x00' in log or os.path.exists('x')",
                    "log == None", EXPR + "\nprint(1)",
                    "`" + EXPR + "` trailing"):
            with self.subTest(value=bad[:40]):
                with self.assertRaises(ValueError):
                    normalize_expression(bad)

    def test_second_patch_derived_from_first_but_independent_guard(self):
        rec = first_task()
        original = (ROOT / TARGET).read_text(encoding="utf-8")
        first, second, new_line = make_candidate(original, rec["candidate_line"], EXPR)
        self.assertEqual(first.count(rec["candidate_line"]), 1)
        self.assertIn(new_line, second)
        self.assertNotIn(LOG_ORIGINAL, second)
        self.assertNotEqual(first, second)
        self.assertEqual(second.count(rec["candidate_line"]), 1)
        self.assertEqual(hash_data(original.encode()), rec["source_sha256"])

    def test_both_edits_staged_without_host_source_change(self):
        rec = first_task()
        original = (ROOT / TARGET).read_bytes()
        first, second, _ = make_candidate(original.decode(), rec["candidate_line"], EXPR)
        with tempfile.TemporaryDirectory() as tmp:
            stage(ROOT, first, second, Path(tmp) / "staged")
            self.assertEqual((ROOT / TARGET).read_bytes(), original)
            self.assertEqual((Path(tmp) / "staged/first_patch_only" / TARGET).read_text(), first)
            self.assertEqual((Path(tmp) / "staged/first_plus_second" / TARGET).read_text(), second)

    def test_isolated_docker_negative_controls_must_flip(self):
        rec = first_task()
        with patch("qwen_second_task_trial._test", side_effect=fake_docker_ok) as calls:
            result = evaluate(ROOT, rec["candidate_line"], EXPR, rec["source_sha256"])
        self.assertEqual(calls.call_count, 4)
        self.assertEqual(result["outcome"], "second_patch_passed")
        self.assertFalse(result["baseline_negative_control"]["passed"])
        self.assertTrue(result["candidate_negative_control"]["passed"])
        self.assertFalse(result["merge_authorized"])

    def test_negative_test_failure_does_not_claim_model_success(self):
        rec = first_task()
        with patch("qwen_second_task_trial._test", return_value={
                "passed": True, "tests_run": 8, "exit_code": 0}):
            result = evaluate(ROOT, rec["candidate_line"], EXPR, rec["source_sha256"])
        self.assertEqual(result["outcome"], "baseline_or_negative_control_invalid")

    def test_fresh_model_generation_and_no_fake_queue_progress(self):
        model = FixedResponse([EXPR])
        with patch("qwen_second_task_trial._test", side_effect=fake_docker_ok):
            result = trial(ROOT, model)
        self.assertEqual(result["outcome"], "second_patch_passed")
        self.assertEqual(result["model_calls"], 1)
        self.assertEqual(result["docker_comparisons"], 1)
        self.assertEqual(result["second_task"], TASK_ID)
        self.assertTrue(result["model_generated_second_task"])
        self.assertFalse(result["merge_authorized"])
        self.assertNotIn("completed_tasks", result)

    def test_bad_model_output_stays_failure(self):
        model = FixedResponse(["garbage", "still garbage", "invalid"])
        result = trial(ROOT, model)
        self.assertEqual(result["model_calls"], MAX_ATTEMPTS)
        self.assertEqual(result["docker_comparisons"], 0)
        self.assertFalse(result["model_generated_second_task"])
        self.assertIsNone(result["candidate_line"])

    def test_duplicate_wrong_answer_stops_without_wasting_cpu(self):
        model = FixedResponse(["invalid", "invalid", "should-never-run"])
        result = trial(ROOT, model)
        self.assertEqual(result["model_calls"], 2)
        self.assertEqual(result["outcome"], "duplicate_response_blocked")
        self.assertEqual(result["docker_comparisons"], 0)
        self.assertFalse(result["model_generated_second_task"])
        self.assertEqual(len(model.calls), 2)


if __name__ == "__main__":
    unittest.main()
