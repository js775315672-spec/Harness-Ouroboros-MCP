import pathlib
import sys
import tempfile
import unittest
import json

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from scoped_patch_evidence import evaluate

TASK={"task_id":"parser_regression","goal":"Add a regression test for parser output.",
      "allowed_files":["tests/test_model_feedback_loop.py"],
      "acceptance_tests":["tests/test_model_feedback_loop.py"],"max_attempts":2}
PATH="tests/test_model_feedback_loop.py"
PATCH=f"diff --git a/{PATH} b/{PATH}\n--- a/{PATH}\n+++ b/{PATH}\n@@ -1 +1 @@\n-old\n+new\n"
PROPOSAL={"provider":"qwen","status":"proposal","summary":"Proposed test update","patch":PATCH}

class ScopedPatchEvidenceTests(unittest.TestCase):
    def run_evidence(self,task,proposal):
        with tempfile.TemporaryDirectory() as tmp:
            a=pathlib.Path(tmp)/"task.json"
            b=pathlib.Path(tmp)/"proposal.json"
            a.write_text(json.dumps(task),encoding="utf-8")
            b.write_text(json.dumps(proposal),encoding="utf-8")
            return evaluate(a,b)

    def test_accepted_review_is_not_application(self):
        report=self.run_evidence(TASK,PROPOSAL)
        self.assertEqual(report["status"],"accepted_for_review")
        self.assertEqual(len(report["task_sha256"]),64)
        self.assertEqual(len(report["proposal_sha256"]),64)
        self.assertFalse(report["patch_applied"])
        self.assertFalse(report["full_harness_passed"])
        self.assertFalse(report["merge_authorized"])

    def test_out_of_scope_proposal_rejected_with_evidence(self):
        bad=dict(PROPOSAL)
        bad["patch"]=PATCH.replace(PATH,"scripts/other.py")
        report=self.run_evidence(TASK,bad)
        self.assertEqual(report["status"],"rejected")
        self.assertIsNotNone(report["reason"])
        self.assertFalse(report["patch_applied"])

    def test_missing_acceptance_file_rejected(self):
        bad=dict(TASK)
        bad["allowed_files"]=["scripts/other.py","tests/test_model_feedback_loop.py"]
        report=self.run_evidence(bad,dict(PROPOSAL,patch=PATCH.replace(PATH,"scripts/other.py")))
        self.assertEqual(report["status"],"rejected")
