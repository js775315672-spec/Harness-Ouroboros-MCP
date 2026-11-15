"""Offline independent replay tests: two model patches, pending queue, no fake completion."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from qwen_two_patch_replay import (
    inspect, patch_bytes, construct, write, verify, REPO,
)
from qwen_source_guard import TARGET

ARCHIVE = ROOT / "proposals/two_qwen_7b_patches_v1.json"
HEAD = "a" * 40


def fake_success(root, first_line, expression, source_hash):
    record = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    return {"outcome": "second_patch_passed",
            "second_patch_sha256": record["first_plus_second_source_sha256"],
            "second_line_sha256": record["second_line_sha256"],
            "source_checkout_modified": False, "merge_authorized": False,
            "baseline_negative_control": {"passed": False, "tests_run": 3},
            "candidate_negative_control": {"passed": True, "tests_run": 3},
            "candidate_regression": {"passed": True, "tests_run": 8}}


class IndependentReplayTests(unittest.TestCase):
    def test_both_archived_model_sources_reconstruct_exactly(self):
        record, first, original, combined, expression = inspect(ROOT)
        self.assertEqual(record["task_ids"],
                         ["feedback_cycle_guard", "feedback_log_control_guard"])
        self.assertEqual(first["task_id"], "feedback_cycle_guard")
        self.assertIn("chr(0) in log or chr(27) in log", expression)
        self.assertIn(record["second_line"], combined)
        self.assertNotEqual(combined, original)
        diff = patch_bytes(original, combined)
        self.assertEqual(diff.count(b"\n+        if "), 1)
        self.assertGreaterEqual(diff.count(b"\n+    if "), 1)
        self.assertEqual((ROOT / TARGET).read_text(encoding="utf-8"), original)

    def test_new_queue_is_always_pending_with_two_uncompleted_tasks(self):
        queue, diff, receipt = construct(ROOT, HEAD, evaluator=fake_success)
        self.assertEqual(queue["index"], 0)
        self.assertEqual(queue["generation"], 0)
        self.assertEqual(queue["events"], [])
        self.assertEqual([x["id"] for x in queue["tasks"]],
                         ["feedback_cycle_guard", "feedback_log_control_guard"])
        self.assertEqual(receipt["completed_tasks"], 0)
        self.assertTrue(receipt["queue_pending"])
        self.assertFalse(receipt["merge_authorized"])
        self.assertIn(b"feedback_controller.py", diff)

    def test_files_transfer_verifies_read_only_without_advancing_work(self):
        queue, diff, receipt = construct(ROOT, HEAD, evaluator=fake_success)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "handoff"
            write(path, queue, diff, receipt)
            result = verify(ROOT, path, HEAD)
            self.assertEqual(result["status"], "review_only_two_patch_queue_restored")
            self.assertEqual(result["tasks"], 2)
            self.assertEqual(result["completed_tasks"], 0)
            self.assertFalse(result["merge_authorized"])
            with self.assertRaises(ValueError):
                verify(ROOT, path, "b" * 40)
            with self.assertRaises(ValueError):
                write(path, queue, diff, receipt)

    def test_patch_or_receipt_mutation_is_blocked(self):
        queue, diff, receipt = construct(ROOT, HEAD, evaluator=fake_success)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "handoff"
            write(path, queue, diff, receipt)
            (path / "candidate.patch").write_bytes(diff + b"\nunsafe")
            with self.assertRaises(ValueError):
                verify(ROOT, path, HEAD)
            (path / "candidate.patch").write_bytes(diff)
            status = dict(receipt, completed_tasks=2)
            (path / "receipt.json").write_text(json.dumps(status), encoding="utf-8")
            with self.assertRaises(ValueError):
                verify(ROOT, path, HEAD)

    def test_failed_docker_replay_never_creates_a_queue(self):
        wrong = dict(fake_success(ROOT, "", "", ""), outcome="second_patch_test_failed")
        with self.assertRaises(ValueError):
            construct(ROOT, HEAD, evaluator=lambda *args: wrong)
        wrong = dict(fake_success(ROOT, "", "", ""),
                     candidate_negative_control={"passed": False, "tests_run": 3})
        with self.assertRaises(ValueError):
            construct(ROOT, HEAD, evaluator=lambda *args: wrong)

    def test_invalid_head_and_missing_archive_fail_closed(self):
        with self.assertRaises(ValueError):
            construct(ROOT, "invalid", evaluator=fake_success)
        with self.assertRaises(ValueError):
            inspect(ROOT, "proposals/missing-evidence.json")


if __name__ == "__main__":
    unittest.main()
