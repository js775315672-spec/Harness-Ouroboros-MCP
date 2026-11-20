"""Pair-marker consumer contract tests; all fixtures are synthetic."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_distill_pair_marker import publish, verify


class PairMarkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.train = root / "train.jsonl"
        self.report = root / "report.json"
        self.marker = root / "pair.commit.json"
        self.train.write_text('{"messages":[]}\n')
        self.report.write_text('{"student_weights_updated":false}\n')

    def tearDown(self):
        self.tmp.cleanup()

    def test_unpublished_pair_fails_closed(self):
        with self.assertRaises(FileNotFoundError):
            verify(self.train, self.report, self.marker)

    def test_published_pair_verifies(self):
        expected = publish(self.train, self.report, self.marker)
        self.assertEqual(verify(self.train, self.report, self.marker), expected)
        self.assertFalse(expected["student_weights_updated"])
        self.assertFalse(expected["independent_evaluation"])

    def test_train_tamper_fails(self):
        publish(self.train, self.report, self.marker)
        self.train.write_text('{"messages":["changed"]}\n')
        with self.assertRaisesRegex(ValueError, "integrity"):
            verify(self.train, self.report, self.marker)

    def test_report_tamper_fails(self):
        publish(self.train, self.report, self.marker)
        self.report.write_text('{"student_weights_updated":true}\n')
        with self.assertRaisesRegex(ValueError, "integrity"):
            verify(self.train, self.report, self.marker)

    def test_missing_report_does_not_publish(self):
        self.report.unlink()
        with self.assertRaises(ValueError):
            publish(self.train, self.report, self.marker)
        self.assertFalse(self.marker.exists())

    def test_existing_marker_never_overwritten(self):
        self.marker.write_text("protected")
        with self.assertRaises(FileExistsError):
            publish(self.train, self.report, self.marker)
        self.assertEqual(self.marker.read_text(), "protected")

    def test_symlink_marker_refused(self):
        outside = self.marker.parent / "victim"
        outside.write_text("protected")
        self.marker.symlink_to(outside)
        with self.assertRaises(FileExistsError):
            publish(self.train, self.report, self.marker)
        self.assertEqual(outside.read_text(), "protected")

    def test_symlink_train_refused(self):
        original = self.train.parent / "original"
        original.write_text(self.train.read_text())
        self.train.unlink()
        self.train.symlink_to(original)
        with self.assertRaisesRegex(ValueError, "symlink"):
            publish(self.train, self.report, self.marker)

    def test_cross_directory_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            with self.assertRaisesRegex(ValueError, "same directory"):
                publish(self.train, self.report, Path(other) / "marker")

    def test_marker_payload_corruption_rejected(self):
        publish(self.train, self.report, self.marker)
        raw = json.loads(self.marker.read_text())
        raw["student_weights_updated"] = True
        self.marker.write_text(json.dumps(raw))
        with self.assertRaisesRegex(ValueError, "integrity"):
            verify(self.train, self.report, self.marker)

    def test_duplicate_marker_json_keys_rejected(self):
        publish(self.train, self.report, self.marker)
        self.marker.write_text('{"schema":"a","schema":"b"}')
        with self.assertRaisesRegex(ValueError, "duplicate marker"):
            verify(self.train, self.report, self.marker)

    def test_second_publish_fails_without_changing_original(self):
        first = publish(self.train, self.report, self.marker)
        with self.assertRaises(FileExistsError):
            publish(self.train, self.report, self.marker)
        self.assertEqual(verify(self.train, self.report, self.marker), first)

    def test_cli_publish_verify(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "oril_v2_distill_pair_marker.py"
        for action in ("publish", "verify"):
            p = subprocess.run([sys.executable, str(script), action,
                                "--train", str(self.train),
                                "--report", str(self.report),
                                "--marker", str(self.marker)],
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertTrue(json.loads(p.stdout)["ok"])

    def test_no_marker_on_output_write_failure_simulation(self):
        # A failed producer never calls publish: consumer refuses orphan train.
        self.report.unlink()
        with self.assertRaises((FileNotFoundError, ValueError)):
            verify(self.train, self.report, self.marker)

    def test_marker_has_owner_only_permissions(self):
        publish(self.train, self.report, self.marker)
        self.assertEqual(self.marker.stat().st_mode & 0o077, 0)


if __name__ == "__main__":
    unittest.main()
