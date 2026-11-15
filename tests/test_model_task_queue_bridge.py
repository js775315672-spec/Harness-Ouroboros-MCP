"""Model-generated patch -> pending Ouroboros task, with no completion fabrication."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from model_task_queue_bridge import construct, write_artifacts, verify, sha256, TASK
from resumable_task_queue import next_action, load as load_queue

EVIDENCE = ROOT / "proposals/feedback_cycle_guard_7b.json"
SHA = "a" * 40


def approved_docker(*args, **kwargs):
    rec = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    return {"status": "isolated_replay_passed", "docker_replayed": True,
            "candidate_line_sha256": rec["candidate_line_sha256"],
            "merge_authorized": False}


class HandoffTests(unittest.TestCase):
    def test_real_model_candidate_maps_to_pending_task_not_completed(self):
        queue, data, receipt = construct(ROOT, EVIDENCE, SHA, docker=False)
        self.assertEqual(queue["index"], 0)
        self.assertEqual(queue["events"], [])
        self.assertEqual(queue["generation"], 0)
        self.assertEqual(next_action(queue)["task_id"], TASK)
        self.assertIn(b"diff --git a/scripts/feedback_controller.py", data)
        self.assertIn(b"+++ b/scripts/feedback_controller.py", data)
        self.assertIn(b"candidate".replace(b"candidate", b"proposal"), data)
        self.assertEqual(receipt["patch_sha256"], sha256(data))
        self.assertEqual(receipt["gate"], "static_ast_only")
        self.assertFalse(receipt["code_applied"])
        self.assertFalse(receipt["merge_authorized"])

    def test_docker_receipt_required_across_job_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "handoff"
            with patch("model_task_queue_bridge.replay", side_effect=approved_docker):
                queue, diff, receipt = construct(ROOT, EVIDENCE, SHA, docker=True,
                                                docker_replay=approved_docker)
            write_artifacts(out, queue, diff, receipt)
            restored = load_queue(out / "queue.json")
            self.assertEqual(restored["index"], 0)
            result = verify(ROOT, EVIDENCE, out, SHA)
            self.assertEqual(result["status"], "verified_review_handoff")
            self.assertEqual(result["completed_tasks"], 0)
            self.assertFalse(result["code_applied"])
            self.assertFalse(result["merge_authorized"])
            with self.assertRaises(ValueError):
                verify(ROOT, EVIDENCE, out, "b" * 40)
            with self.assertRaises(ValueError):
                write_artifacts(out, queue, diff, receipt)

    def test_reject_unattested_candidate_before_publishing(self):
        cases = [
            {"status": "candidate_negative_failed", "docker_replayed": True,
             "candidate_line_sha256": json.loads(EVIDENCE.read_text())["candidate_line_sha256"],
             "merge_authorized": False},
            {"status": "isolated_replay_passed", "docker_replayed": False,
             "candidate_line_sha256": json.loads(EVIDENCE.read_text())["candidate_line_sha256"],
             "merge_authorized": False},
            {"status": "isolated_replay_passed", "docker_replayed": True,
             "candidate_line_sha256": "0" * 64, "merge_authorized": False},
        ]
        for bad in cases:
            with self.subTest(status=bad):
                with self.assertRaises(ValueError):
                    construct(ROOT, EVIDENCE, SHA, docker=True, docker_replay=lambda *a, **kw: bad)

    def test_patch_tampering_and_receipt_tampering_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "handoff"
            queue, diff, receipt = construct(ROOT, EVIDENCE, SHA, docker=True,
                                            docker_replay=approved_docker)
            write_artifacts(out, queue, diff, receipt)
            original = (out / "candidate.patch").read_bytes()
            (out / "candidate.patch").write_bytes(original + b"\nmalicious")
            with self.assertRaises(ValueError):
                verify(ROOT, EVIDENCE, out, SHA)
            (out / "candidate.patch").write_bytes(original)
            status = json.loads((out / "receipt.json").read_text())
            status["completed_tasks"] = 1
            (out / "receipt.json").write_text(json.dumps(status))
            with self.assertRaises(ValueError):
                verify(ROOT, EVIDENCE, out, SHA)

    def test_static_only_evidence_does_not_claim_docker(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "handoff"
            queue, diff, receipt = construct(ROOT, EVIDENCE, SHA)
            write_artifacts(out, queue, diff, receipt)
            with self.assertRaises(ValueError):
                verify(ROOT, EVIDENCE, out, SHA, require_docker=True)
            status = verify(ROOT, EVIDENCE, out, SHA, require_docker=False)
            self.assertFalse(status["docker_replay_receipt"])

    def test_illegal_commit_and_symlinked_artifacts_are_blocked(self):
        with self.assertRaises(ValueError):
            construct(ROOT, EVIDENCE, "not-sha")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "handoff"
            queue, diff, receipt = construct(ROOT, EVIDENCE, SHA)
            write_artifacts(out, queue, diff, receipt)
            patch_file = out / "candidate.patch"
            patch_file.unlink()
            patch_file.symlink_to(EVIDENCE)
            with self.assertRaises(ValueError):
                verify(ROOT, EVIDENCE, out, SHA)


if __name__ == "__main__":
    unittest.main()
