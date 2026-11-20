import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from scripts.oril_v2_external_pin_boundary import verify

class PinBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "dataset"
        self.root.mkdir()
        self.manifest = self.root / "manifest.json"
        self.anchor = self.base / "approved-pin.txt"
        self.data = {"samples": [{"id": "one", "source": "s1"}]}
        self.write_pin()

    def write_pin(self):
        self.manifest.write_text(json.dumps(self.data), encoding="utf-8")
        canonical = json.dumps(self.data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        self.anchor.write_text(hashlib.sha256(canonical).hexdigest(), encoding="ascii")

    def test_clean_pass_not_provenance(self):
        result = verify(self.manifest, self.anchor, self.root)
        self.assertTrue(result["integrity_pass"])
        self.assertFalse(result["provenance_verified"])
        self.assertFalse(result["training_approved"])

    def test_manifest_tamper_rejected(self):
        self.data["samples"][0]["source"] = "attacker"
        self.manifest.write_text(json.dumps(self.data))
        with self.assertRaisesRegex(ValueError, "pin mismatch"):
            verify(self.manifest, self.anchor, self.root)

    def test_self_repin_is_not_authentication(self):
        self.data["samples"][0]["source"] = "attacker"
        self.write_pin()
        result = verify(self.manifest, self.anchor, self.root)
        self.assertFalse(result["provenance_verified"])

    def test_anchor_inside_dataset_rejected(self):
        anchor = self.root / "pin.txt"
        anchor.write_text(self.anchor.read_text())
        with self.assertRaisesRegex(ValueError, "outside dataset"):
            verify(self.manifest, anchor, self.root)

    def test_bad_digest_rejected(self):
        self.anchor.write_text("0" * 63)
        with self.assertRaisesRegex(ValueError, "invalid pinned"):
            verify(self.manifest, self.anchor, self.root)

    def test_duplicate_keys_rejected(self):
        self.manifest.write_text('{"x":1,"x":2}')
        with self.assertRaisesRegex(ValueError, "duplicate"):
            verify(self.manifest, self.anchor, self.root)

    def test_nan_rejected(self):
        self.manifest.write_text('{"x":NaN}')
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            verify(self.manifest, self.anchor, self.root)

    def test_manifest_outside_root_rejected(self):
        other = self.base / "other.json"
        other.write_text("{}")
        with self.assertRaisesRegex(ValueError, "inside dataset"):
            verify(other, self.anchor, self.root)

if __name__ == "__main__":
    unittest.main()
