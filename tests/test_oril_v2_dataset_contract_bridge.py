"""Cross-PR integration tests: must execute original pinned validator modules."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.oril_v2_dataset_contract_bridge import project, run, load
from scripts.oril_v2_dataset_manifest_attestation import fingerprint
from scripts.oril_v2_dataset_split_audit import audit
from scripts.oril_v2_raw_sample_integrity import verify


def digest(data):
    return hashlib.sha256(data).hexdigest()


class DatasetContractBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest = {"schema_version": 1, "splits": {}}
        for split in ("train", "validation", "test"):
            data = ("unique sample " + split).encode()
            (self.root / (split + ".txt")).write_bytes(data)
            self.manifest["splits"][split] = [{
                "sample_id": split, "content_sha256": digest(data),
                "group_id": "group-" + split, "source_id": "source-" + split,
                "relative_path": split + ".txt"
            }]
        self.expected = digest(json.dumps(self.manifest, sort_keys=True,
                                          separators=(",", ":"), ensure_ascii=False,
                                          allow_nan=False).encode())

    def check(self, manifest=None, expected=None):
        return run(manifest if manifest is not None else self.manifest,
                   expected if expected is not None else self.expected,
                   self.root, fingerprint, audit, verify)

    def test_valid_canonical_manifest_passes_all_stages(self):
        result = self.check()
        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["manifest_pin"]["pin_matches"])
        self.assertEqual(result["split_audit"]["split_integrity"], "pass")
        self.assertEqual(result["raw_audit"]["raw_sample_integrity"], "pass")
        self.assertFalse(result["training_approved"])
        self.assertFalse(result["promotion_approved"])

    def test_projection_keeps_exact_contracts(self):
        a, b = project(self.manifest)
        self.assertEqual(set(a["splits"]["train"][0]), {"sample_id", "content_sha256", "group_id", "source_id"})
        self.assertEqual(set(b["splits"]["train"][0]), {"sample_id", "relative_path", "content_sha256"})

    def test_changed_manifest_rejected_before_other_checks(self):
        self.manifest["splits"]["train"][0]["source_id"] = "changed"
        result = self.check()
        self.assertEqual(result["failed_stage"], "manifest_pin")
        self.assertNotIn("raw_audit", result)

    def test_wrong_expected_hash_rejected(self):
        self.assertEqual(self.check(expected="0" * 64)["failed_stage"], "manifest_pin")

    def test_train_test_content_overlap_detected(self):
        sample = self.manifest["splits"]["test"][0]
        sample["content_sha256"] = self.manifest["splits"]["train"][0]["content_sha256"]
        sample["relative_path"] = "train.txt"
        result = self.check(expected=digest(json.dumps(self.manifest, sort_keys=True, separators=(",", ":")).encode()))
        self.assertEqual(result["failed_stage"], "split_integrity")
        self.assertNotIn("raw_audit", result)

    def test_group_leakage_detected(self):
        self.manifest["splits"]["test"][0]["group_id"] = "group-train"
        expected = digest(json.dumps(self.manifest, sort_keys=True, separators=(",", ":")).encode())
        self.assertEqual(self.check(expected=expected)["failed_stage"], "split_integrity")

    def test_changed_raw_bytes_detected(self):
        (self.root / "validation.txt").write_bytes(b"tampered")
        self.assertEqual(self.check()["failed_stage"], "raw_sample_integrity")

    def test_missing_provenance_rejected(self):
        del self.manifest["splits"]["train"][0]["source_id"]
        with self.assertRaises(ValueError):
            self.check()

    def test_extra_field_rejected(self):
        self.manifest["splits"]["test"][0]["unreviewed"] = "injection"
        with self.assertRaises(ValueError):
            self.check()

    def test_unsafe_path_rejected_by_original_raw_verifier(self):
        self.manifest["splits"]["test"][0]["relative_path"] = "../outside"
        expected = digest(json.dumps(self.manifest, sort_keys=True, separators=(",", ":")).encode())
        with self.assertRaises(ValueError):
            self.check(expected=expected)

    def test_duplicate_json_keys_rejected(self):
        p = self.root / "manifest.json"
        p.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
        with self.assertRaises(ValueError):
            load(p)

    def test_nonfinite_json_rejected(self):
        p = self.root / "manifest.json"
        p.write_text('{"schema_version":NaN}', encoding="utf-8")
        with self.assertRaises(ValueError):
            load(p)

    def test_boolean_version_rejected(self):
        self.manifest["schema_version"] = True
        with self.assertRaises(ValueError):
            self.check()

    def test_nonempty_splits_required(self):
        self.manifest["splits"]["test"] = []
        with self.assertRaises(ValueError):
            self.check()

    def test_independent_model_evaluation_not_fabricated(self):
        result = self.check()
        self.assertEqual(result["independent_model_evaluation"], "unmeasured")
        self.assertEqual(result["dataset_provenance"], "unverified")
        self.assertEqual(result["semantic_leakage"], "unmeasured")


if __name__ == "__main__":
    unittest.main()
