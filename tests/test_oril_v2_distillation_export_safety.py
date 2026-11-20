"""Fail-closed dataset export tests: existing files, symlinks, private permissions."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "oril_v2_teacher_distillation_pack.py"
SHA = "a" * 40
URL = "https://github.com/js775315672-spec/Harness-Ouroboros-MCP/pull/274"


def row():
    return {
        "case_id": "case-1", "group_id": "family-1", "split": "train",
        "task_type": "review", "question": "Check this bounded task",
        "teacher_answer": "Use exact test evidence.", "checks": ["test passes"],
        "quality": 0.99, "review_accepted": True,
        "review_url": URL, "candidate_sha": SHA,
    }


def run(root, *, train=None, report=None):
    root = Path(root)
    source = root / "source.jsonl"
    source.write_text(json.dumps(row()) + "\n", encoding="utf-8")
    return subprocess.run([
        sys.executable, str(SCRIPT), "--input", str(source),
        "--output-train", str(train or root / "student.jsonl"),
        "--output-report", str(report or root / "summary.json"),
    ], capture_output=True, text=True, timeout=10)


class ExportSafetyTests(unittest.TestCase):
    def test_existing_train_file_not_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "student.jsonl"
            target.write_text("SECRET HELDOUT DATA")
            result = run(td)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(target.read_text(), "SECRET HELDOUT DATA")

    def test_existing_report_file_not_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "summary.json"
            target.write_text("KEEP ME")
            result = run(td)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(target.read_text(), "KEEP ME")
            self.assertFalse((Path(td) / "student.jsonl").exists() and
                             (Path(td) / "student.jsonl").stat().st_size > 0)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_train_symlink_cannot_modify_target(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            victim = root / "heldout.jsonl"
            victim.write_text("SECRET-UNTOUCHED")
            (root / "student.jsonl").symlink_to(victim)
            result = run(td)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(victim.read_text(), "SECRET-UNTOUCHED")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_report_symlink_cannot_modify_target(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            victim = root / "heldout.jsonl"
            victim.write_text("SECRET-UNTOUCHED")
            (root / "summary.json").symlink_to(victim)
            result = run(td)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(victim.read_text(), "SECRET-UNTOUCHED")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_dangling_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "student.jsonl").symlink_to(root / "absent")
            result = run(td)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / "absent").exists())

    def test_normal_outputs_private_and_parseable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = run(td)
            self.assertEqual(result.returncode, 0, result.stderr)
            train = root / "student.jsonl"
            report = root / "summary.json"
            self.assertEqual(len(train.read_text().splitlines()), 1)
            self.assertEqual(json.loads(report.read_text())["selected_train_rows"], 1)
            if os.name == "posix":
                self.assertEqual(train.stat().st_mode & 0o777, 0o600)
                self.assertEqual(report.stat().st_mode & 0o777, 0o600)

    def test_second_run_refuses_to_overwrite_first(self):
        with tempfile.TemporaryDirectory() as td:
            first = run(td)
            self.assertEqual(first.returncode, 0, first.stderr)
            root = Path(td)
            before = ((root / "student.jsonl").read_bytes(),
                      (root / "summary.json").read_bytes())
            second = run(td)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(before, ((root / "student.jsonl").read_bytes(),
                                      (root / "summary.json").read_bytes()))


if __name__ == "__main__":
    unittest.main()
