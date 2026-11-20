"""Regression: second output creation failure must not leave an empty first output."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "oril_v2_teacher_distillation_pack.py"
REVIEW = "https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/123"


def sample():
    return {
        "case_id": "a", "group_id": "a", "split": "train",
        "task_type": "repair", "question": "What failed?",
        "teacher_answer": "Check the source SHA.", "checks": ["check"],
        "quality": 0.95, "review_accepted": True,
        "review_url": REVIEW, "candidate_sha": "a" * 40,
    }


class SecondOpenRollbackTests(unittest.TestCase):
    def execute(self, root, report):
        root = Path(root)
        src = root / "input.jsonl"
        src.write_text(json.dumps(sample()) + "\n", encoding="utf-8")
        train = root / "candidate.jsonl"
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--input", str(src),
             "--output-train", str(train), "--output-report", str(report)],
            capture_output=True, text=True, timeout=10)
        return proc, train

    def test_existing_report_does_not_leave_empty_train(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "existing.json"
            report.write_text("HELDOUT_PROTECTED", encoding="utf-8")
            proc, train = self.execute(tmp, report)
            self.assertNotEqual(proc.returncode, 0)
            self.assertFalse(train.exists())
            self.assertEqual(report.read_text(), "HELDOUT_PROTECTED")

    def test_report_symlink_does_not_leave_empty_train(self):
        with tempfile.TemporaryDirectory() as tmp:
            protected = Path(tmp) / "heldout.json"
            protected.write_text("SECRET", encoding="utf-8")
            report = Path(tmp) / "report-link.json"
            report.symlink_to(protected)
            proc, train = self.execute(tmp, report)
            self.assertNotEqual(proc.returncode, 0)
            self.assertFalse(train.exists())
            self.assertEqual(protected.read_text(), "SECRET")

    def test_report_dangling_symlink_does_not_leave_empty_train(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "dangling.json"
            report.symlink_to(Path(tmp) / "absent.json")
            proc, train = self.execute(tmp, report)
            self.assertNotEqual(proc.returncode, 0)
            self.assertFalse(train.exists())
            self.assertTrue(report.is_symlink())

    def test_report_missing_parent_does_not_leave_empty_train(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "no-directory" / "report.json"
            proc, train = self.execute(tmp, report)
            self.assertNotEqual(proc.returncode, 0)
            self.assertFalse(train.exists())

    def test_success_writes_both_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.json"
            proc, train = self.execute(tmp, report)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(len(train.read_text().splitlines()), 1)
            self.assertEqual(json.loads(report.read_text())["selected_train_rows"], 1)

    def test_repeat_success_refuses_clobber(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.json"
            first, train = self.execute(tmp, report)
            self.assertEqual(first.returncode, 0, first.stderr)
            snapshot = train.read_bytes()
            second, _ = self.execute(tmp, report)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(train.read_bytes(), snapshot)


if __name__ == "__main__":
    unittest.main()
