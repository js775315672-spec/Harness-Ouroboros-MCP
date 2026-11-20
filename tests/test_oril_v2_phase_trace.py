"""Runtime model/verification/operations phase tracer: measured but unattested."""
import json
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_phase_trace import run_timed, summarize

SHA = "a" * 40


class PhaseTraceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target = pathlib.Path(self.tmp.name) / "spans.jsonl"

    def read(self):
        return [json.loads(line) for line in self.target.read_text().splitlines()]

    def test_real_subprocess_time_is_recorded_with_source_and_ids(self):
        result = run_timed("model_call", [sys.executable, "-c", "pass"],
                           self.target, sha=SHA, run_id=123)
        self.assertEqual(result, 0)
        rows = self.read()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sha"], SHA)
        self.assertEqual(rows[0]["actions_run_id"], 123)
        self.assertGreaterEqual(rows[0]["duration_seconds"], 0)
        self.assertFalse(rows[0]["verified_independent"])

    def test_failed_command_measured_but_not_success(self):
        status = run_timed("independent_verification",
                           [sys.executable, "-c", "raise SystemExit(3)"],
                           self.target, sha=SHA, run_id=123)
        self.assertEqual(status, 3)
        summary = summarize(self.read(), sha=SHA, run_id=123)
        self.assertIsNone(summary["spans_seconds"]["independent_verification"])
        self.assertEqual(summary["sample_counts"]["independent_verification"], 0)

    def test_missing_command_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "command"):
            run_timed("model_call", [], self.target)

    def test_phase_name_must_be_recognized(self):
        with self.assertRaisesRegex(ValueError, "phase"):
            run_timed("fake_gpu_training", [sys.executable], self.target)

    def test_sha_validation(self):
        with self.assertRaisesRegex(ValueError, "SHA"):
            run_timed("whole_cycle", [sys.executable], self.target, sha="short")

    def test_missing_phases_remain_null(self):
        run_timed("operational_followup", [sys.executable, "-c", "pass"],
                  self.target, sha=SHA, run_id=123)
        summary = summarize(self.read(), sha=SHA, run_id=123)
        self.assertIsNone(summary["spans_seconds"]["model_call"])
        self.assertIsNone(summary["spans_seconds"]["independent_verification"])
        self.assertIsNone(summary["spans_seconds"]["whole_cycle"])
        self.assertGreater(summary["spans_seconds"]["operational_followup"], 0)


    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW") and hasattr(os, "symlink"), "POSIX nofollow required")
    def test_symlink_output_does_not_overwrite_target(self):
        target = pathlib.Path(self.tmp.name) / "victim.txt"
        target.write_text("untouched", encoding="utf-8")
        self.target.symlink_to(target)
        with self.assertRaises(OSError):
            run_timed("model_call", [sys.executable, "-c", "pass"],
                      self.target, sha=SHA, run_id=123)
        self.assertEqual(target.read_text(encoding="utf-8"), "untouched")

    def test_existing_world_readable_output_rejected(self):
        self.target.write_text("original\\n", encoding="utf-8")
        os.chmod(self.target, 0o644)
        with self.assertRaises(PermissionError):
            run_timed("model_call", [sys.executable, "-c", "pass"],
                      self.target, sha=SHA, run_id=123)
        self.assertEqual(self.target.read_text(encoding="utf-8"), "original\\n")

    def test_trace_file_private_mode(self):
        run_timed("model_call", [sys.executable, "-c", "pass"],
                  self.target, sha=SHA, run_id=123)
        self.assertEqual(self.target.stat().st_mode & 0o077, 0)

    def test_cross_run_rejection(self):
        run_timed("model_call", [sys.executable, "-c", "pass"],
                  self.target, sha=SHA, run_id=123)
        with self.assertRaisesRegex(ValueError, "Actions run mismatch"):
            summarize(self.read(), sha=SHA, run_id=456)

    def test_nonfinite_or_forged_schema_rejected(self):
        row = {"schema_version": 1, "source": "runner_monotonic_unattested",
               "phase": "model_call", "duration_seconds": float("nan"), "returncode": 0}
        with self.assertRaisesRegex(ValueError, "invalid measured"):
            summarize([row])
        row["duration_seconds"] = 1.0
        row["source"] = "independently_verified"
        with self.assertRaisesRegex(ValueError, "unknown phase source"):
            summarize([row])

    def test_two_real_spans_sum_without_claiming_independence(self):
        for i in range(2):
            run_timed("model_call", [sys.executable, "-c", "pass"],
                      self.target, sha=SHA, run_id=123)
        result = summarize(self.read(), sha=SHA, run_id=123)
        self.assertEqual(result["sample_counts"]["model_call"], 2)
        self.assertGreater(result["spans_seconds"]["model_call"], 0)
        self.assertFalse(result["independently_attested"])


    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"), "POSIX fd required")
    def test_symlinked_parent_is_rejected_without_touching_victim(self):
        outside = pathlib.Path(self.tmp.name) / "outside"
        outside.mkdir()
        victim = outside / "trace.jsonl"
        victim.write_text("preserve", encoding="utf-8")
        link = pathlib.Path(self.tmp.name) / "redirect"
        link.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            run_timed("model_call", [sys.executable, "-c", "pass"],
                      link / "trace.jsonl", sha=SHA, run_id=123)
        self.assertEqual(victim.read_text(encoding="utf-8"), "preserve")

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"), "POSIX fd required")
    def test_nested_regular_directories_still_work(self):
        folder = pathlib.Path(self.tmp.name) / "safe" / "nested"
        folder.mkdir(parents=True)
        dest = folder / "trace.jsonl"
        self.assertEqual(run_timed("model_call", [sys.executable, "-c", "pass"],
                                   dest, sha=SHA, run_id=123), 0)
        self.assertEqual(len(dest.read_text().splitlines()), 1)

    def test_parent_traversal_rejected(self):
        dest = pathlib.Path(self.tmp.name) / "safe" / ".." / "trace.jsonl"
        with self.assertRaisesRegex(ValueError, "parent traversal"):
            run_timed("model_call", [sys.executable, "-c", "pass"],
                      dest, sha=SHA, run_id=123)


if __name__ == "__main__":
    unittest.main()
