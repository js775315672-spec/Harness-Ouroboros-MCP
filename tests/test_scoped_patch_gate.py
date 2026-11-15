import pathlib
import sys
import unittest

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from scoped_patch_gate import inspect_scoped_patch

def task():
    return {"task_id":"parser_regression","goal":"Add an acceptance regression test for parser output.",
            "allowed_files":["scripts/model_feedback_loop.py","tests/test_model_feedback_loop.py"],
            "acceptance_tests":["tests/test_model_feedback_loop.py"],"max_attempts":2}

def patch_for(*paths):
    blocks=[]
    for path in paths:
        blocks.append(f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-old\n+new\n")
    return {"provider":"qwen","status":"proposal","summary":"Proposed test change","patch":"".join(blocks)}

class ScopedPatchTests(unittest.TestCase):
    def test_valid_scoped_patch_remains_unapplied(self):
        result=inspect_scoped_patch(task(),patch_for("scripts/model_feedback_loop.py","tests/test_model_feedback_loop.py"))
        self.assertTrue(result["static_patch_inspection_passed"])
        self.assertFalse(result["patch_approved_for_application"])
        self.assertFalse(result["generated_code_executed"])
        self.assertFalse(result["merge_authorized"])

    def test_outside_scope_denied(self):
        with self.assertRaises(ValueError):
            inspect_scoped_patch(task(),patch_for("tests/test_model_feedback_loop.py","scripts/other.py"))

    def test_missing_acceptance_test_denied(self):
        with self.assertRaises(ValueError):
            inspect_scoped_patch(task(),patch_for("scripts/model_feedback_loop.py"))

    def test_workflow_file_denied(self):
        with self.assertRaises(ValueError):
            inspect_scoped_patch(task(),patch_for(".github/workflows/harness.yml"))

    def test_unsafe_task_denied(self):
        bad=task()
        bad["allowed_files"]=["../secret.py"]
        with self.assertRaises(ValueError):
            inspect_scoped_patch(bad,patch_for("tests/test_model_feedback_loop.py"))
