"""Offline boundary tests for archived model-authored repair evidence."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from verified_model_patch_review import inspect_proposal, replay

EVIDENCE = ROOT / "proposals/feedback_cycle_guard_7b.json"


class VerifiedPatchReviewTests(unittest.TestCase):
    def test_archived_model_patch_matches_current_source_and_ast(self):
        before = (ROOT / "scripts/feedback_controller.py").read_bytes()
        record, inspected = inspect_proposal(ROOT, EVIDENCE)
        self.assertEqual(record["outcome"], "isolated_source_repair_passed")
        self.assertEqual(inspected["status"], "ast_scoped_candidate")
        result = replay(ROOT, EVIDENCE)
        self.assertEqual(result["status"], "static_review_only")
        self.assertFalse(result["docker_replayed"])
        self.assertFalse(result["merge_authorized"])
        self.assertEqual((ROOT / "scripts/feedback_controller.py").read_bytes(), before)

    def test_forged_candidate_or_digest_fails_closed(self):
        record = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        for field, value in (
            ("candidate_line", "    if True:"),
            ("source_sha256", "0" * 64),
            ("outcome", "anything_else"),
            ("human_review_required", False),
            ("successful_run", "https://fake.host/run/1"),
        ):
            bad = dict(record, **{field: value})
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "forged.json"
                path.write_text(json.dumps(bad), encoding="utf-8")
                with self.assertRaises(ValueError):
                    inspect_proposal(ROOT, path)

    def test_symlinked_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            symlink = Path(tmp) / "evidence.json"
            symlink.symlink_to(EVIDENCE)
            with self.assertRaises(ValueError):
                inspect_proposal(ROOT, symlink)

    def test_docker_report_cannot_fake_success_with_missing_negative_tests(self):
        record = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        accepted = {
            "status": "isolated_source_repair_passed",
            "source_sha256": record["source_sha256"],
            "candidate_line_sha256": record["candidate_line_sha256"],
            "source_checkout_modified": False, "merge_authorized": False,
            "network_disabled": True, "filesystem_read_only": True,
            "baseline_regression": {"passed": True, "tests_run": 8},
            "baseline_negative_control": {"passed": False, "tests_run": 3},
            "candidate_regression": {"passed": True, "tests_run": 8},
            "candidate_negative_control": {"passed": False, "tests_run": 3},
        }
        with patch("verified_model_patch_review.compare_line", return_value=accepted):
            with self.assertRaises(ValueError):
                replay(ROOT, EVIDENCE, docker=True)
        accepted["candidate_negative_control"]["passed"] = True
        with patch("verified_model_patch_review.compare_line", return_value=accepted):
            self.assertEqual(replay(ROOT, EVIDENCE, docker=True)["status"],
                             "isolated_replay_passed")


if __name__ == "__main__":
    unittest.main()
