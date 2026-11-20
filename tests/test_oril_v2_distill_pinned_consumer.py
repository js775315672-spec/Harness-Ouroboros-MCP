"""Consumer verification regression; all examples synthetic, no student model."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_distill_pair_marker import publish
from oril_v2_distill_pinned_consumer import consume


class PinnedConsumerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.train = root / "train.jsonl"
        self.report = root / "report.json"
        self.marker = root / "pair.commit.json"
        self.train.write_text(json.dumps({"messages": [
            {"role": "user", "content": "Test?"}, {"role": "assistant", "content": "Test."}]}) + "\n")
        self.report.write_text(json.dumps({
            "student_weights_updated": False, "heldout_evaluation_performed": False}) + "\n")
        publish(self.train, self.report, self.marker)

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, **kw):
        return consume(self.train, self.report, self.marker, **kw)

    def test_committed_pair_consumed_as_bytes(self):
        a, b = self.read()
        self.assertIsInstance(a, bytes)
        self.assertIsInstance(b, bytes)
        self.assertIn(b"messages", a)

    def test_replaced_path_during_open_is_rejected(self):
        def replace(path):
            original = path.with_name("original.jsonl")
            os.rename(path, original)
            path.write_bytes(original.read_bytes())
        # The open FD is already pinned when before_read replaces the path.
        # The intended fail-closed signal is the snapshot's post-read
        # metadata change, not the earlier path-replacement check.
        with self.assertRaisesRegex(ValueError, "file changed during snapshot"):
            self.read(before_read=replace)

    def test_same_size_tamper_after_publish_rejected(self):
        raw = self.train.read_bytes()
        self.train.write_bytes(raw.replace(b"Test?", b"Fake?"))
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            self.read()

    def test_report_tamper_after_publish_rejected(self):
        self.report.write_text('{"student_weights_updated":true,"heldout_evaluation_performed":true}')
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            self.read()

    def test_marker_replacement_after_publish_rejected(self):
        self.marker.write_text('{"schema":"malicious"}')
        with self.assertRaisesRegex(ValueError, "invalid marker schema"):
            self.read()

    def test_marker_symlink_rejected(self):
        orig = self.marker.with_name("original.marker")
        self.marker.rename(orig)
        self.marker.symlink_to(orig)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.read()

    def test_train_symlink_rejected(self):
        orig = self.train.with_name("original.train")
        self.train.rename(orig)
        self.train.symlink_to(orig)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.read()

    def test_report_missing_rejected(self):
        self.report.unlink()
        with self.assertRaises(FileNotFoundError):
            self.read()

    def test_fifo_rejected_without_blocking(self):
        self.train.unlink()
        os.mkfifo(self.train)
        with self.assertRaisesRegex(ValueError, "unsafe file type"):
            self.read()

    def test_truncated_train_rejected(self):
        self.train.write_bytes(self.train.read_bytes()[:-1])
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            self.read()

    def test_train_empty_rejected(self):
        self.train.write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            self.read()

    def test_marker_duplicate_json_key_rejected(self):
        self.marker.write_text('{"schema":"x","schema":"y"}')
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            self.read()

    def test_nonfinite_marker_json_rejected(self):
        self.marker.write_text('{"schema":NaN}')
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            self.read()

    def test_report_model_claim_false_positive_rejected(self):
        # A local producer could publish a report asserting training: consumer
        # refuses that assertion even when hashes agree.
        self.marker.unlink()
        self.report.write_text(json.dumps({
            "student_weights_updated": True, "heldout_evaluation_performed": False}))
        publish(self.train, self.report, self.marker)
        with self.assertRaisesRegex(ValueError, "report cannot assert"):
            self.read()

    def test_report_independent_eval_claim_rejected(self):
        self.marker.unlink()
        self.report.write_text(json.dumps({
            "student_weights_updated": False, "heldout_evaluation_performed": True}))
        publish(self.train, self.report, self.marker)
        with self.assertRaisesRegex(ValueError, "report cannot assert"):
            self.read()

    def test_cli_only_prints_hashes_not_teacher_answer(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "oril_v2_distill_pinned_consumer.py"
        run = subprocess.run([
            sys.executable, str(script), "--train", str(self.train),
            "--report", str(self.report), "--marker", str(self.marker)],
            capture_output=True, text=True, timeout=5)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertNotIn("Test.", run.stdout)
        self.assertFalse(json.loads(run.stdout)["model_trained"])

    def test_reopening_after_consumption_is_not_allowed_as_a_contract(self):
        data, _ = self.read()
        self.train.write_text("MALICIOUS")
        self.assertIn(b"Test.", data)
        self.assertNotIn(b"MALICIOUS", data)


if __name__ == "__main__":
    unittest.main()
