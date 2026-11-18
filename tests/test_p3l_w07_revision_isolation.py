"""Reject a mismatched checkout or altered evidence before historical replay."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import p3l_w07_revision_isolation as review


class RevisionIsolationTests(unittest.TestCase):
    def test_wrong_checkout_stops_before_reading_artifacts(self):
        with patch.object(review, "git", return_value=b"wrong\n"), \
             patch.object(review, "read_artifact") as read:
            with self.assertRaisesRegex(ValueError, "differs from the reviewed W07 revision"):
                review.rehearse(ROOT, Path("unused-evidence"))
        read.assert_not_called()

    def test_valid_json_in_tampered_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            filename = root / "123" / "artifact.zip"
            filename.parent.mkdir()
            with zipfile.ZipFile(filename, "w") as archive:
                archive.writestr("verdict.json", json.dumps({"test_count": 25}))
            expected = hashlib.sha256(filename.read_bytes()).hexdigest()
            self.assertEqual(review.read_artifact(root, ("123", expected), "verdict.json"),
                             ({"test_count": 25},))
            with zipfile.ZipFile(filename, "w") as archive:
                archive.writestr("verdict.json", json.dumps({"test_count": 24}))
            with self.assertRaisesRegex(ValueError, "differs from the reviewed archive"):
                review.read_artifact(root, ("123", expected), "verdict.json")


if __name__ == "__main__":
    unittest.main()
