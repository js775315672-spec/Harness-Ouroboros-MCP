import unittest
from scripts.unified_diff_structure import validate_diff_structure

PATH="tests/test_example.py"
def diff(body,header="@@ -1 +1 @@"):
    return f"diff --git a/{PATH} b/{PATH}\n--- a/{PATH}\n+++ b/{PATH}\n{header}\n{body}"

class UnifiedDiffStructureTests(unittest.TestCase):
    def test_valid_one_line_replacement(self):
        result=validate_diff_structure(diff("-old\n+new\n"))
        self.assertEqual(result["hunks"],1)
        self.assertFalse(result["patch_approved_for_application"])

    def test_valid_addition_with_zero_old_lines(self):
        self.assertTrue(validate_diff_structure(diff("+new\n","@@ -0,0 +1 @@"))["structure_valid"])

    def test_reject_missing_markers(self):
        with self.assertRaises(ValueError):
            validate_diff_structure(f"diff --git a/{PATH} b/{PATH}\n@@ -1 +1 @@\n-old\n+new\n")

    def test_reject_count_mismatch(self):
        with self.assertRaises(ValueError):
            validate_diff_structure(diff("-old\n+new\n","@@ -2 +1 @@"))

    def test_reject_unexpected_metadata(self):
        with self.assertRaises(ValueError):
            validate_diff_structure(diff("index 123..456\n-old\n+new\n"))

    def test_reject_duplicate_file(self):
        item=diff("-old\n+new\n")
        with self.assertRaises(ValueError):
            validate_diff_structure(item+item)

    def test_reject_missing_final_newline(self):
        with self.assertRaises(ValueError):
            validate_diff_structure(diff("-old\n+new"))

    def test_reject_malformed_hunk_line(self):
        with self.assertRaises(ValueError):
            validate_diff_structure(diff("old\n+new\n"))

    def test_reject_missing_hunk(self):
        with self.assertRaises(ValueError):
            validate_diff_structure(f"diff --git a/{PATH} b/{PATH}\n--- a/{PATH}\n+++ b/{PATH}\n")
