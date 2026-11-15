import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from qwen_task_scope_gate import validate_task

TASK = {"task_id": "feedback_regression", "goal": "Improve feedback regression coverage",
        "files": ["scripts/feedback_controller.py", "tests/test_feedback_controller.py"],
        "requires_human_review": True}

class QwenTaskScopeGateTests(unittest.TestCase):
    def test_scoped_two_file_task(self):
        result = validate_task(TASK)
        self.assertEqual(result["decision"], "scoped_proposal_only")
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["merge_authorized"])

    def test_protected_workflow_rejected(self):
        with self.assertRaises(ValueError):
            validate_task(dict(TASK, files=[".github/workflows/harness.yml"]))

    def test_traversal_rejected(self):
        with self.assertRaises(ValueError):
            validate_task(dict(TASK, files=["scripts/../tests/test_task_selector.py"]))

    def test_nonallowlisted_file_rejected(self):
        with self.assertRaises(ValueError):
            validate_task(dict(TASK, files=["scripts/governance.py"]))

    def test_more_than_two_files_rejected(self):
        with self.assertRaises(ValueError):
            validate_task(dict(TASK, files=list(TASK["files"]) + ["tests/test_task_selector.py"]))

    def test_duplicate_files_rejected(self):
        with self.assertRaises(ValueError):
            validate_task(dict(TASK, files=[TASK["files"][0]]*2))

    def test_human_review_required(self):
        with self.assertRaises(ValueError):
            validate_task(dict(TASK, requires_human_review=False))

    def test_invalid_task_id_rejected(self):
        with self.assertRaises(ValueError):
            validate_task(dict(TASK, task_id="../../unsafe"))

if __name__ == "__main__":
    unittest.main()
