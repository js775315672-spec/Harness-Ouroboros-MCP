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
