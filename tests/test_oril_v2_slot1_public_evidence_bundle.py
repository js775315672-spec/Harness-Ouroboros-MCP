import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "scripts"))
import oril_v2_slot1_public_evidence_bundle as m

SHA = "a" * 40

class BundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ab = Path(self.tmp.name) / "ab.json"
        self.aa = Path(self.tmp.name) / "aa.json"
        self.ab.write_text('{"x":1}', encoding="utf-8")
        self.aa.write_text('{"x":2}', encoding="utf-8")
        self.kw = dict(ab_run=44841372111, aa_run=44843133109, ab_sha=SHA, aa_sha="b"*40)

    def test_hashes_and_unverified_flags(self):
        with patch.object(m, "reconcile", return_value={"decision": "판단불가"}):
            out = m.bundle(self.ab, self.aa, **self.kw)
        self.assertEqual(len(out["source"]["ab"]["raw_sha256"]), 64)
        self.assertFalse(out["source_run_sha_verified_via_github_api"])
        self.assertFalse(out["artifacts_retrieved_by_independent_verifier"])
        self.assertFalse(out["gpu_lora_training_proven"])
        self.assertEqual(out["decision"], "판단불가")

    def test_same_path_rejected(self):
        with self.assertRaises(ValueError):
            m.bundle(self.ab, self.ab, **self.kw)

    def test_duplicate_run_rejected(self):
        with self.assertRaises(ValueError):
            m.bundle(self.ab, self.aa, **dict(self.kw, aa_run=self.kw["ab_run"]))

    def test_bad_run_rejected(self):
        with self.assertRaises(ValueError):
            m.bundle(self.ab, self.aa, **dict(self.kw, ab_run=-1))

    def test_bad_sha_rejected(self):
        with self.assertRaises(ValueError):
            m.bundle(self.ab, self.aa, **dict(self.kw, ab_sha="ABC"))

    def test_symlink_rejected(self):
        link = Path(self.tmp.name) / "link"
        link.symlink_to(self.ab)
        with self.assertRaises(ValueError):
            m.bundle(link, self.aa, **self.kw)

    def test_identical_contents_rejected(self):
        self.aa.write_bytes(self.ab.read_bytes())
        with self.assertRaises(ValueError):
            m.bundle(self.ab, self.aa, **self.kw)

    def test_duplicate_json_key_rejected(self):
        self.ab.write_text('{"x":1,"x":2}', encoding="utf-8")
        with self.assertRaises(ValueError):
            m.bundle(self.ab, self.aa, **self.kw)

    def test_auditor_error_propagates(self):
        with patch.object(m, "reconcile", side_effect=ValueError("bad model")):
            with self.assertRaisesRegex(ValueError, "bad model"):
                m.bundle(self.ab, self.aa, **self.kw)

    def test_oversized_rejected(self):
        with patch.object(m, "MAX_BYTES", 2):
            with self.assertRaises(ValueError):
                m.bundle(self.ab, self.aa, **self.kw)

if __name__ == "__main__":
    unittest.main()
