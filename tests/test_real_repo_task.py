import unittest
from scripts.real_repo_task import prepare, TASK
from scripts.coding_task_contract import validate_task

class RealRepoTaskTests(unittest.TestCase):
    def test_task_is_scoped_to_real_regression_file(self):
        prepared=prepare()
        self.assertEqual(prepared["contract"]["allowed_files"],["tests/test_model_feedback_loop.py"])
        self.assertEqual(prepared["contract"]["acceptance_tests"],["tests/test_model_feedback_loop.py"])
        self.assertEqual(prepared["contract"]["max_attempts"],2)

    def test_prompt_explicitly_requires_diff_not_executable_code(self):
        prepared=prepare()
        self.assertIn("unified git diff",prepared["prompt"])
        self.assertIn("accurate '@@' hunk line counts",prepared["prompt"])
        self.assertFalse(prepared["model_called"])
        self.assertFalse(prepared["patch_applied"])
        self.assertTrue(prepared["requires_human_review"])

    def test_contract_is_fail_closed(self):
        contract=validate_task(TASK)
        self.assertFalse(contract["model_execution_authorized"])
        self.assertFalse(contract["patch_application_authorized"])
        self.assertFalse(contract["merge_authorized"])
