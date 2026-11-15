import unittest
import pathlib
import sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from cloud_real_repo_proposal import assess

TASK={"task_id":"parser_regression",
      "goal":"Add a regression test for multiple Python fences.",
      "allowed_files":["tests/test_model_feedback_loop.py"],
      "acceptance_tests":["tests/test_model_feedback_loop.py"],
      "max_attempts":2}
PATH="tests/test_model_feedback_loop.py"
VALID=f"diff --git a/{PATH} b/{PATH}\n--- a/{PATH}\n+++ b/{PATH}\n@@ -1 +1 @@\n-old\n+new\n"

class RealRepoQwenProposalTests(unittest.TestCase):
    def test_valid_diff_review_only(self):
        report=assess(VALID,TASK)
        self.assertEqual(report["status"],"accepted_for_review")
        self.assertFalse(report["inspection"]["patch_approved_for_application"])
    def test_explanatory_prose_rejected(self):
        self.assertEqual(assess("Here is a patch:\n"+VALID,TASK)["status"],"rejected")
    def test_outside_scope_rejected(self):
        self.assertEqual(assess(VALID.replace(PATH,"scripts/other.py"),TASK)["status"],"rejected")
    def test_empty_proposal_rejected(self):
        self.assertEqual(assess("",TASK)["status"],"rejected")

    def test_real_source_single_line_patch_accepted_for_review_only(self):
        from cloud_real_repo_proposal import _target_line, prompt_for_attempt
        source=(pathlib.Path(__file__).resolve().parents[1]/PATH).read_text(encoding="utf-8")
        n,old=_target_line(source)
        new=old.replace("\\\\n","\\n")
        self.assertNotEqual(old,new)
        patch=(f"diff --git a/{PATH} b/{PATH}\n--- a/{PATH}\n+++ b/{PATH}\n"
               f"@@ -{n} +{n} @@\n-{old}\n+{new}\n")
        result=assess(patch,TASK,source)
        self.assertEqual(result["status"],"accepted_for_review",result["reason"])
        self.assertTrue(result["inspection"]["source_context"]["python_ast_parsed"])
        self.assertTrue(result["inspection"]["source_context"]["test_fixture_real_newlines"])
        self.assertFalse(result["inspection"]["patch_approved_for_application"])
        self.assertIn(f"Line {n}: {old}",prompt_for_attempt("Goal",source))
        self.assertIn("rejected: test failure",prompt_for_attempt("Goal",source,"test failure"))

    def test_real_source_rejects_wrong_context_and_noop(self):
        from cloud_real_repo_proposal import _target_line
        source=(pathlib.Path(__file__).resolve().parents[1]/PATH).read_text(encoding="utf-8")
        n,old=_target_line(source)
        new=old.replace("\\\\n","\\n")
        prefix=f"diff --git a/{PATH} b/{PATH}\n--- a/{PATH}\n+++ b/{PATH}\n"
        wrong=prefix+f"@@ -{n} +{n} @@\n-not the real file line\n+{new}\n"
        self.assertEqual(assess(wrong,TASK,source)["status"],"rejected")
        noop=prefix+f"@@ -{n} +{n} @@\n-{old}\n+{old}\n"
        self.assertEqual(assess(noop,TASK,source)["status"],"rejected")
        wrong_position=prefix+f"@@ -{n+1} +{n+1} @@\n-{old}\n+{new}\n"
        self.assertEqual(assess(wrong_position,TASK,source)["status"],"rejected")
