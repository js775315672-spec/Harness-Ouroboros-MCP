import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from qwen_scope_bridge import verify_scoped_model_candidate
from cloud_real_repo_proposal import _target_line
from real_repo_task import TASK
from replacement_proposal import build_single_line_diff

def fixture():
    source = (ROOT / "tests/test_model_feedback_loop.py").read_text(encoding="utf-8")
    number, original = _target_line(source)
    replacement = original.replace(chr(92) * 2 + "n", chr(92) + "n")
    patch = build_single_line_diff(replacement, original, number)
    candidate = {"provider": "qwen", "status": "proposal",
                 "summary": "Scoped fixture repair", "patch": patch}
    return source, candidate

class QwenScopeBridgeTests(unittest.TestCase):
    def test_real_source_scoped_candidate_ready_for_disposable_only(self):
        source, candidate = fixture()
        result = verify_scoped_model_candidate(TASK, candidate, source)
        self.assertEqual(result["status"], "scoped_candidate_review_ready")
        self.assertTrue(result["qwen_file_allowlist_checked"])
        self.assertTrue(result["source_anchor_and_ast_checked"])
        self.assertEqual(result["touched_files"], ["tests/test_model_feedback_loop.py"])
        self.assertFalse(result["model_generated_code_executed_by_gate"])
        self.assertFalse(result["patch_applied_to_checkout"])
        self.assertFalse(result["merge_authorized"])

    def test_forbidden_patch_target_fails(self):
        source, candidate = fixture()
        candidate["patch"] = candidate["patch"].replace(
            "tests/test_model_feedback_loop.py", "scripts/governance.py")
        with self.assertRaises(ValueError):
            verify_scoped_model_candidate(TASK, candidate, source)

    def test_two_file_scope_does_not_loosen_single_fixture_executor(self):
        source, candidate = fixture()
        task = dict(TASK, allowed_files=[
            "tests/test_model_feedback_loop.py", "scripts/feedback_controller.py"])
        with self.assertRaises(ValueError):
            verify_scoped_model_candidate(task, candidate, source)

    def test_not_allowlisted_task_fails(self):
        source, candidate = fixture()
        task = dict(TASK, allowed_files=["scripts/governance.py"])
        with self.assertRaises(ValueError):
            verify_scoped_model_candidate(task, candidate, source)

    def test_non_proposal_rejected(self):
        source, candidate = fixture()
        candidate["status"] = "applied"
        with self.assertRaises(ValueError):
            verify_scoped_model_candidate(TASK, candidate, source)

    def test_malformed_patch_rejected(self):
        source, candidate = fixture()
        candidate["patch"] = "print('untrusted')"
        with self.assertRaises(ValueError):
            verify_scoped_model_candidate(TASK, candidate, source)

    def test_corrupted_source_anchor_rejected(self):
        source, candidate = fixture()
        with self.assertRaises(ValueError):
            verify_scoped_model_candidate(TASK, candidate, source.replace(
                "def test_reject_multiple_fences(self):", "def tampered(self):"))

    def test_unknown_task_field_rejected_by_scope(self):
        source, candidate = fixture()
        with self.assertRaises(ValueError):
            verify_scoped_model_candidate(dict(TASK, allowed_files=["tests/x.py"]), candidate, source)

if __name__ == "__main__":
    unittest.main()
