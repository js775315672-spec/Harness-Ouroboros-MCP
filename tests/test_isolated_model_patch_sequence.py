"""Offline tests for real disposable git-apply of model source and two task phases."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from model_task_queue_bridge import make_patch
from verified_model_patch_review import inspect_proposal
from isolated_model_patch_sequence import stage_patch, run_phase, FOLLOWUP_TEST
from qwen_source_guard import TARGET

EVIDENCE = ROOT / "proposals/feedback_cycle_guard_7b.json"
SHA = "a" * 40


def model():
    record, _ = inspect_proposal(ROOT, EVIDENCE)
    return make_patch(ROOT, record), record


def stub_test(workspace, pattern):
    patch_content = (Path(workspace) / TARGET).read_text(encoding="utf-8")
    _, record = model()
    assert record["candidate_line"] in patch_content
    count = {"test_feedback_controller.py": 8, "test_semantic_cycle_guard.py": 3,
             "test_extended_cycle_guard.py": 3}[pattern]
    return {"passed": True, "tests_run": count, "network_disabled": True,
            "filesystem_read_only": True, "privileges_dropped": True}


class IsolatedPatchSequenceTests(unittest.TestCase):
    def test_patch_is_actually_applied_to_disposable_source(self):
        patch_bytes, record = model()
        before = (ROOT / TARGET).read_bytes()
        with tempfile.TemporaryDirectory() as d:
            staged = Path(d) / "stage"
            hashes = stage_patch(ROOT, patch_bytes, record, staged)
            target = (staged / TARGET).read_text(encoding="utf-8")
            self.assertIn(record["candidate_line"], target)
            self.assertNotEqual(hashes["applied_sha256"], record["source_sha256"])
            self.assertEqual((ROOT / TARGET).read_bytes(), before)
            self.assertTrue((staged / "tests/test_extended_cycle_guard.py").is_file())
            self.assertIn("test_absent_cycle_or_none_blocked", FOLLOWUP_TEST)

    def test_both_phases_run_in_order_with_no_false_queue_completion(self):
        patch_bytes, record = model()
        with patch("isolated_model_patch_sequence._strict_patch",
                   return_value=(patch_bytes, record)):
            with patch("isolated_model_patch_sequence._test", side_effect=stub_test) as tester:
                phase1 = run_phase(Path("."), ROOT / "does-not-matter", SHA, 1)
                self.assertEqual(phase1["docker_tests"],
                                 {"test_feedback_controller.py": 8,
                                  "test_semantic_cycle_guard.py": 3})
                phase2 = run_phase(ROOT, ROOT / "does-not-matter", SHA, 2, phase1)
        self.assertEqual(tester.call_count, 3)
        self.assertEqual(phase1["ouroboros_queue_completed_tasks"], 0)
        self.assertEqual(phase2["ouroboros_queue_completed_tasks"], 0)
        self.assertFalse(phase2["model_generated_followup"])
        self.assertFalse(phase2["merge_authorized"])
        self.assertEqual(phase2["docker_tests"], {"test_extended_cycle_guard.py": 3})
        self.assertTrue(phase2["source_applied_in_disposable_checkout"])

    def test_phase_two_blocks_invalid_prior_receipt(self):
        patch_bytes, record = model()
        with patch("isolated_model_patch_sequence._strict_patch",
                   return_value=(patch_bytes, record)):
            with patch("isolated_model_patch_sequence._test", side_effect=stub_test):
                one = run_phase(ROOT, "unused", SHA, 1)
                for changed in (
                    dict(one, commit="b" * 40),
                    dict(one, status="failed"),
                    dict(one, patch_sha256="0" * 64),
                    dict(one, all_checks_passed=False),
                    dict(one, merge_authorized=True),
                    dict(one, host_source_modified=True)
                ):
                    with self.subTest(change=changed):
                        with self.assertRaises(ValueError):
                            run_phase(ROOT, "unused", SHA, 2, changed)

    def test_disallowed_patch_is_not_applied(self):
        patch_bytes, record = model()
        with tempfile.TemporaryDirectory() as d:
            stage = Path(d) / "stage"
            with self.assertRaises(ValueError):
                stage_patch(ROOT, patch_bytes.replace(
                    b"+    if ", b"+    if __import__('os').system('id') or "), record, stage)
            self.assertEqual((ROOT / TARGET).read_bytes(),
                             (ROOT / TARGET).read_bytes())

    def test_untrusted_docker_report_blocks_phase(self):
        patch_bytes, record = model()
        with patch("isolated_model_patch_sequence._strict_patch",
                   return_value=(patch_bytes, record)):
            with patch("isolated_model_patch_sequence._test",
                       return_value={"passed": True, "tests_run": 8,
                                     "network_disabled": False,
                                     "filesystem_read_only": True,
                                     "privileges_dropped": True}):
                with self.assertRaises(ValueError):
                    run_phase(ROOT, "unused", SHA, 1)

    def test_invalid_phase_cannot_execute(self):
        with self.assertRaises(ValueError):
            run_phase(ROOT, "unused", SHA, 3)


if __name__ == "__main__":
    unittest.main()
