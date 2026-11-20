"""Synthetic manifest attestation regression tests."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.oril_v2_dataset_manifest_attestation import (
    fingerprint, load_manifest, reject_duplicate_keys, reject_constant
)


def sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


class ManifestAttestationTests(unittest.TestCase):
    def setUp(self):
        self.data = {"schema_version": 1, "splits": {"train": [{"sample_id": "a"}], "test": []}}

    def test_valid_pin(self):
        out = fingerprint(self.data, sha(self.data))
        self.assertTrue(out["pin_matches"])
        self.assertFalse(out["training_approved"])
        self.assertFalse(out["promotion_approved"])

    def test_mutation_breaks_pin(self):
        before = sha(self.data)
        self.data["splits"]["train"][0]["sample_id"] = "b"
        self.assertFalse(fingerprint(self.data, before)["pin_matches"])

    def test_key_order_does_not_change_pin(self):
        other = {"splits": self.data["splits"], "schema_version": 1}
        self.assertTrue(fingerprint(other, sha(self.data))["pin_matches"])

    def test_array_order_changes_pin(self):
        self.data["splits"]["train"].append({"sample_id": "b"})
        before = sha(self.data)
        self.data["splits"]["train"].reverse()
        self.assertFalse(fingerprint(self.data, before)["pin_matches"])

    def test_uppercase_pin_rejected(self):
        with self.assertRaises(ValueError):
            fingerprint(self.data, sha(self.data).upper())

    def test_short_pin_rejected(self):
        with self.assertRaises(ValueError):
            fingerprint(self.data, "abc")

    def test_missing_pin_rejected(self):
        with self.assertRaises(ValueError):
            fingerprint(self.data, None)

    def test_nan_manifest_rejected(self):
        self.data["score"] = float("nan")
        with self.assertRaises(ValueError):
            fingerprint(self.data, "a" * 64)

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "manifest.json"
            path.write_text('{"schema_version":1,"schema_version":2}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                load_manifest(path)

    def test_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "manifest.json"
            path.write_text('{"value":NaN}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "nonfinite JSON number"):
                load_manifest(path)

    def test_json_whitespace_not_change_fingerprint(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "manifest.json"
            path.write_text(json.dumps(self.data, indent=4), encoding="utf-8")
            self.assertEqual(fingerprint(load_manifest(path), sha(self.data))["manifest_sha256"], sha(self.data))

    def test_not_claiming_raw_content_verification(self):
        out = fingerprint(self.data, sha(self.data))
        self.assertFalse(out["raw_sample_hashes_verified"])
        self.assertFalse(out["provenance_verified"])


if __name__ == "__main__":
    unittest.main()
