"""Committed, non-production candidate of first Qwen 7B source repair."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from feedback_controller_verified import feedback
from task_selector import select


def checks(log=""):
    return {name: {"status": "pass", "log": log}
            for name in ("harness", "ouroboros", "regression", "secrets")}


class FirstModelCommittedRepair(unittest.TestCase):
    def test_archived_source_line_matches_model_output(self):
        recorded = json.loads(
            (ROOT / "proposals/feedback_cycle_guard_7b.json").read_text(encoding="utf-8"))
        source = (ROOT / "scripts/feedback_controller_verified.py").read_text(encoding="utf-8")
        line = recorded["candidate_line"]
        self.assertEqual(source.count(line + "\n"), 1)
        self.assertEqual(
            hashlib.sha256(line.encode("utf-8")).hexdigest(),
            recorded["candidate_line_sha256"])

    def test_original_historical_baseline_remains_unmodified(self):
        recorded = json.loads(
            (ROOT / "proposals/feedback_cycle_guard_7b.json").read_text(encoding="utf-8"))
        baseline = (ROOT / "scripts/feedback_controller.py").read_bytes()
        self.assertEqual(hashlib.sha256(baseline).hexdigest(),
                         recorded["source_sha256"])

    def test_reject_bad_cycle(self):
        for value in (None, True, False, 0, -1, 0.5, 2.5, "1", [], {}):
            with self.subTest(value=repr(value)):
                with self.assertRaises(ValueError):
                    feedback(dict(select(), cycle=value), checks())
        with self.assertRaises(ValueError):
            feedback({"decision": "propose"}, checks())

    def test_accept_positive_ints(self):
        for cycle in (1, 2, 10**12):
            with self.subTest(cycle=cycle):
                self.assertEqual(
                    feedback(dict(select(), cycle=cycle), checks())["decision"], "review")

    def test_second_model_line_and_combined_source_match_archived_hashes(self):
        recorded = json.loads(
            (ROOT / "proposals/two_qwen_7b_patches_v1.json").read_text(
                encoding="utf-8"))
        source = (ROOT / "scripts/feedback_controller_verified.py").read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(),
                         recorded["first_plus_second_source_sha256"])
        self.assertEqual(source.decode("utf-8").count(recorded["second_line"] + "\n"), 1)
        self.assertEqual(
            hashlib.sha256(recorded["second_line"].encode("utf-8")).hexdigest(),
            recorded["second_line_sha256"])

    def test_second_model_rejects_untrusted_log_control_bytes(self):
        for control in (chr(0), chr(27)):
            with self.subTest(char=ord(control)):
                with self.assertRaises(ValueError):
                    feedback(select(), checks("prefix" + control + "suffix"))

    def test_second_model_preserves_human_multiline_logs(self):
        result = feedback(select(), checks("Korean 한국어\nordinary second line"))
        self.assertEqual(result["decision"], "review")
        self.assertFalse(result["model_call_performed"])

    def test_empty_and_long_logs_preserve_existing_behavior(self):
        self.assertEqual(feedback(select(), checks(""))["decision"], "review")
        with self.assertRaises(ValueError):
            feedback(select(), checks("x" * 4001))

    def test_existing_feedback_behavior(self):
        self.assertEqual(feedback(select(), checks())["decision"], "review")
        bad = checks()
        bad["regression"]["status"] = "fail"
        self.assertEqual(feedback(select(), bad)["decision"], "request_fix")


if __name__ == "__main__":
    unittest.main()
