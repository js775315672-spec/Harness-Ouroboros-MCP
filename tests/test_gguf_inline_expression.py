"""Normalize a single exact inline code wrapper; never change Python semantics."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from qwen_semantic_repair_loop import normalize_candidate, run_loop, build_prompt
from qwen_source_guard import TARGET

FRAGMENT = "'cycle' not in proposal or not isinstance(proposal['cycle'], int) or proposal['cycle'] < 1"


class InlineExpressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / TARGET).read_text(encoding="utf-8")

    def test_recorded_7b_inline_backticks_are_ast_scoped_not_autoapproved(self):
        line, inspection = normalize_candidate("`" + FRAGMENT + "`", self.source)
        self.assertEqual(inspection["status"], "ast_scoped_candidate")
        self.assertTrue(line.endswith(" or (" + FRAGMENT + "):"))
        self.assertFalse(inspection["merge_authorized"])

    def test_inline_cleanup_does_not_bypass_disposable_negative_controls(self):
        calls = []
        def reject(line):
            calls.append(line)
            return {"status": "candidate_negative_failed"}
        result = run_loop(self.source, lambda _: "`" + FRAGMENT + "`", reject)
        self.assertEqual(result["model_calls"], 2)
        self.assertEqual(result["docker_comparisons"], 1)
        self.assertEqual(result["status"], "stalled_duplicate_candidate")
        self.assertIsNone(result["candidate"])
        self.assertFalse(result["merge_authorized"])
        self.assertEqual(len(calls), 1)

    def test_reject_ambiguous_or_executable_markup(self):
        for raw in [
            "``" + FRAGMENT + "``",
            "`" + FRAGMENT + "` more",
            "prefix `" + FRAGMENT + "`",
            "`" + FRAGMENT + "\n" + "`",
            "```" + FRAGMENT + "`",
            "`import os`",
        ]:
            with self.subTest(raw=repr(raw)[:45]):
                with self.assertRaises(ValueError):
                    normalize_candidate(raw, self.source)

    def test_feedback_does_not_supply_complete_candidate(self):
        prompt = build_prompt("candidate_negative_failed", 3)
        self.assertIn("type(True) is bool", prompt)
        self.assertIn("type(1) is int", prompt)
        self.assertNotIn(FRAGMENT, prompt)


if __name__ == "__main__":
    unittest.main()
