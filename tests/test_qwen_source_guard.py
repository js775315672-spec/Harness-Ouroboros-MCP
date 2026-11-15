import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from qwen_source_guard import EXPECTED, ORIGINAL, TASK, inspect_line

class QwenSourceGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "scripts/feedback_controller.py").read_text(encoding="utf-8")

    def test_valid_model_source_change_is_review_only(self):
        result = inspect_line(EXPECTED, self.source)
        self.assertEqual(result["status"], "bounded_source_proposal")
        self.assertEqual(result["target"], TASK["files"][0])
        self.assertTrue(result["source_executable_condition_changed"])
        self.assertTrue(result["source_ast_guard_verified"])
        self.assertFalse(result["source_checkout_changed"])
        self.assertFalse(result["model_code_executed"])
        self.assertFalse(result["merge_authorized"])
        self.assertIn("diff --git a/scripts/feedback_controller.py", result["patch"])

    def test_cosmetic_spacing_of_same_ast_is_acceptable(self):
        result = inspect_line(EXPECTED.replace(" or ", "  or "), self.source)
        self.assertEqual(result["status"], "bounded_source_proposal")

    def test_unmodified_line_rejected(self):
        with self.assertRaises(ValueError):
            inspect_line(ORIGINAL, self.source)

    def test_weaker_predicate_rejected(self):
        with self.assertRaises(ValueError):
            inspect_line('    if proposal.get("cycle") < 1:', self.source)

    def test_arbitrary_side_effect_rejected(self):
        with self.assertRaises(ValueError):
            inspect_line(EXPECTED[:-1] + " or __import__('os').system('id'):", self.source)

    def test_extra_statement_rejected(self):
        with self.assertRaises(ValueError):
            inspect_line(EXPECTED + "\n    print('unsafe')", self.source)

    def test_source_anchor_tampering_rejected(self):
        with self.assertRaises(ValueError):
            inspect_line(EXPECTED, self.source.replace(ORIGINAL, "    if False:"))

    def test_missing_source_newline_rejected(self):
        with self.assertRaises(ValueError):
            inspect_line(EXPECTED, self.source.rstrip("\n"))

    def test_bad_indentation_rejected(self):
        with self.assertRaises(ValueError):
            inspect_line(EXPECTED.lstrip(), self.source)

if __name__ == "__main__":
    unittest.main()
