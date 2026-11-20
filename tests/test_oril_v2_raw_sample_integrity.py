"""Synthetic offline regression suite for raw sample SHA-256 verification."""
import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts.oril_v2_raw_sample_integrity import verify, _reject_duplicate_keys, _reject_constant


def digest(data):
    return hashlib.sha256(data).hexdigest()


class RawSampleIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.samples = {}
        for split in ("train", "validation", "test"):
            name = split + ".txt"
            data = ("sample " + split).encode()
            (self.root / name).write_bytes(data)
            self.samples[split] = [{
                "sample_id": split, "relative_path": name, "content_sha256": digest(data)
            }]
        self.manifest = {"schema_version": 1, "splits": self.samples}

    def test_clean_data_passes_without_authorizing_training(self):
        result = verify(self.manifest, self.root)
        self.assertEqual(result["raw_sample_integrity"], "pass")
        self.assertEqual(result["total_checked"], 3)
        self.assertFalse(result["training_approved"])
        self.assertFalse(result["promotion_approved"])
        self.assertEqual(result["independent_model_evaluation"], "unmeasured")

    def test_changed_raw_bytes_fail(self):
        (self.root / "test.txt").write_bytes(b"tampered")
        result = verify(self.manifest, self.root)
        self.assertEqual(result["raw_sample_integrity"], "fail")
        self.assertEqual(result["mismatches"][0]["sample_id"], "test")

    def test_mismatched_expected_digest_fail(self):
        self.samples["train"][0]["content_sha256"] = "0" * 64
        self.assertEqual(verify(self.manifest, self.root)["raw_sample_integrity"], "fail")

    def test_absolute_path_rejected(self):
        self.samples["train"][0]["relative_path"] = "/etc/passwd"
        with self.assertRaises(ValueError):
            verify(self.manifest, self.root)

    def test_parent_traversal_rejected(self):
        self.samples["train"][0]["relative_path"] = "../secret.txt"
        with self.assertRaises(ValueError):
            verify(self.manifest, self.root)

    def test_windows_backslash_rejected(self):
        self.samples["train"][0]["relative_path"] = "..\\secret.txt"
        with self.assertRaises(ValueError):
            verify(self.manifest, self.root)

    def test_symlink_rejected(self):
        target = self.root / "train.txt"
        link = self.root / "link.txt"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not supported")
        self.samples["train"][0]["relative_path"] = "link.txt"
        with self.assertRaises(ValueError):
            verify(self.manifest, self.root)

    def test_directory_as_sample_rejected(self):
        (self.root / "subdir").mkdir()
        self.samples["train"][0]["relative_path"] = "subdir"
        with self.assertRaises(ValueError):
            verify(self.manifest, self.root)

    def test_hardlinked_duplicate_rejected(self):
        link = self.root / "hardlink.txt"
        try:
            os.link(self.root / "train.txt", link)
        except OSError:
            self.skipTest("hardlinks not supported")
        self.samples["validation"][0]["relative_path"] = "hardlink.txt"
        self.samples["validation"][0]["content_sha256"] = self.samples["train"][0]["content_sha256"]
        with self.assertRaises(ValueError):
            verify(self.manifest, self.root)

    def test_duplicate_sample_id_rejected(self):
        self.samples["validation"][0]["sample_id"] = "train"
        with self.assertRaises(ValueError):
            verify(self.manifest, self.root)

    def test_duplicate_path_rejected(self):
        self.samples["validation"][0]["relative_path"] = "train.txt"
        with self.assertRaises(ValueError):
            verify(self.manifest, self.root)

    def test_uppercase_digest_rejected(self):
        self.samples["train"][0]["content_sha256"] = "A" * 64
        with self.assertRaises(ValueError):
            verify(self.manifest, self.root)

    def test_boolean_schema_version_rejected(self):
        self.manifest["schema_version"] = True
        with self.assertRaises(ValueError):
            verify(self.manifest, self.root)

    def test_empty_split_rejected(self):
        self.manifest["splits"]["test"] = []
        with self.assertRaises(ValueError):
            verify(self.manifest, self.root)

    def test_missing_provenance_not_fabricated(self):
        result = verify(self.manifest, self.root)
        self.assertEqual(result["dataset_provenance"], "unverified")
        self.assertEqual(result["semantic_leakage"], "unmeasured")

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(ValueError):
            json.loads('{"splits":{},"splits":{}}', object_pairs_hook=_reject_duplicate_keys)

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(ValueError):
            json.loads('{"x":NaN}', parse_constant=_reject_constant)

    def test_missing_root_rejected(self):
        with self.assertRaises(ValueError):
            verify(self.manifest, self.root / "missing")


if __name__ == "__main__":
    unittest.main()
