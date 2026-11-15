import unittest
from scripts.coding_task_contract import validate_task

def valid():
    return {"task_id":"regression_001",
            "goal":"Add a regression test for the safe response parser.",
            "allowed_files":["scripts/model_feedback_loop.py","tests/test_model_feedback_loop.py"],
            "acceptance_tests":["tests/test_model_feedback_loop.py"],"max_attempts":2}

class CodingTaskContractTests(unittest.TestCase):
    def test_valid_task_does_not_authorize_execution(self):
        result=validate_task(valid())
        self.assertFalse(result["model_execution_authorized"])
        self.assertFalse(result["patch_application_authorized"])
        self.assertFalse(result["merge_authorized"])
        self.assertTrue(result["requires_harness_revalidation"])

    def test_reject_unsafe_paths(self):
        for path in ("../secrets.py",".github/workflows/main.py","scripts/../x.py",
                     "scripts/.secret.py","scripts/file.txt","/tmp/x.py",
                     "scripts\\\\evil.py","scripts/__pycache__/x.py"):
            with self.subTest(path=path):
                task=valid()
                task["allowed_files"]=[path,"tests/test_model_feedback_loop.py"]
                with self.assertRaises(ValueError):validate_task(task)

    def test_reject_unscoped_acceptance_test(self):
        task=valid()
        task["allowed_files"]=["scripts/model_feedback_loop.py"]
        with self.assertRaises(ValueError):validate_task(task)

    def test_reject_unknown_fields_and_missing_fields(self):
        task=valid()
        task["secret"]="not allowed"
        with self.assertRaises(ValueError):validate_task(task)
        task=valid()
        del task["goal"]
        with self.assertRaises(ValueError):validate_task(task)

    def test_reject_attempt_limit_and_bool(self):
        for limit in (0,4,True,1.0):
            task=valid()
            task["max_attempts"]=limit
            with self.assertRaises(ValueError):validate_task(task)

    def test_reject_duplicate_paths(self):
        task=valid()
        task["allowed_files"]=["tests/test_model_feedback_loop.py"]*2
        with self.assertRaises(ValueError):validate_task(task)

    def test_reject_non_test_acceptance(self):
        task=valid()
        task["acceptance_tests"]=["scripts/model_feedback_loop.py"]
        with self.assertRaises(ValueError):validate_task(task)
