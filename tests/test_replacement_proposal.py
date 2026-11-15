import pathlib
import unittest

from scripts.replacement_proposal import build_single_line_diff
from scripts.cloud_real_repo_proposal import _target_line,assess
from scripts.real_repo_task import TASK

ROOT=pathlib.Path(__file__).resolve().parents[1]
PATH="tests/test_model_feedback_loop.py"

def fixture():
    source=(ROOT/PATH).read_text(encoding="utf-8")
    number,old=_target_line(source)
    correct=old.replace(chr(92)*2+"n",chr(92)+"n")
    return source,number,old,correct

class ReplacementProposalTests(unittest.TestCase):
    def test_builder_anchors_actual_source_and_passes_static_gates(self):
        source,n,old,new=fixture()
        self.assertNotEqual(old,new)
        patch=build_single_line_diff(new+"\n",old,n)
        self.assertEqual(patch.count("diff --git "),1)
        self.assertIn(f"@@ -{n} +{n} @@\n-{old}\n+{new}\n",patch)
        result=assess(patch,TASK,source)
        self.assertEqual(result["status"],"accepted_for_review",result["reason"])
        self.assertTrue(result["inspection"]["source_context"]["test_fixture_real_newlines"])
        self.assertFalse(result["inspection"]["patch_approved_for_application"])

    def test_accept_unindented_assignment_only_by_normalizing_indent(self):
        source,n,old,new=fixture()
        patch=build_single_line_diff(new.lstrip(),old,n)
        self.assertEqual(assess(patch,TASK,source)["status"],"accepted_for_review")

    def test_reject_multiline_extra_file_code_fence_and_no_change(self):
        _,n,old,new=fixture()
        for raw in (new+"\nother_line\n",new+"\n\n",
                    "diff --git a/tests/x.py b/tests/x.py",
                    "not an assignment","    answer='bad'",old,
                    new+"\r",chr(0),new+"x"*600,
                    "def main(): pass", chr(96)*3+"python\n"+new+"\n"+chr(96)*3):
            with self.subTest(raw=raw[:32]):
                with self.assertRaises(ValueError):
                    build_single_line_diff(raw,old,n)

    def test_non_source_line_and_negative_line_number_denied(self):
        _,n,old,new=fixture()
        for bad in (0,-1,True,1.5):
            with self.subTest(number=bad):
                with self.assertRaises(ValueError):
                    build_single_line_diff(new,old,bad)
        with self.assertRaises(ValueError):
            build_single_line_diff(new,"not an answer assignment",n)

    def test_wrong_value_and_invalid_syntax_rejected_by_ast(self):
        source,n,old,new=fixture()
        for change in ('        answer=42','        answer="bad"',
                       '        answer=__import__("os").system("echo hi")',
                       '        answer=('):
            with self.subTest(change=change):
                patch=build_single_line_diff(change,old,n)
                self.assertEqual(assess(patch,TASK,source)["status"],"rejected")
