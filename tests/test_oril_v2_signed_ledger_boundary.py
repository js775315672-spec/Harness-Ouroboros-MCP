"""Synthetic signed ledger regression; keys generated ephemerally, never production credentials."""
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_signed_ledger_boundary import verify

@unittest.skipUnless(shutil.which("openssl"), "OpenSSL required")
class SignedLedgerBoundary(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.manifest = self.root / "manifest.json"
        self.manifest.write_text('{"samples":[]}', encoding="utf-8")
        self.key = self.root / "key.pem"
        self.pub = self.root / "pub.pem"
        self.sig = self.root / "sig.bin"
        self.ledger = self.root / "ledger.json"
        self.cp = self.root / "checkpoint.json"
        subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt",
                        "rsa_keygen_bits:2048", "-out", str(self.key)],
                       check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", str(self.key), "-pubout", "-out", str(self.pub)],
                       check=True, capture_output=True)
        self.doc = {"dataset_id": "fixture", "manifest_sha256": hashlib.sha256(self.manifest.read_bytes()).hexdigest(),
                    "version": 3, "signer_id": "reviewer", "schema_version": 1,
                    "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}
        self.checkpoint = {"dataset_id": "fixture", "min_version": 3, "signer_id": "reviewer"}
        self.sign()

    def sign(self):
        self.ledger.write_text(json.dumps(self.doc), encoding="utf-8")
        self.cp.write_text(json.dumps(self.checkpoint), encoding="utf-8")
        canonical = self.root / "canonical"
        canonical.write_bytes(json.dumps(self.doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())
        subprocess.run(["openssl", "dgst", "-sha256", "-sign", str(self.key),
                        "-out", str(self.sig), str(canonical)], check=True, capture_output=True)

    def result(self):
        return verify(self.manifest, self.ledger, self.sig, self.pub, self.cp)

    def test_valid_signature_is_integrity_only(self):
        r = self.result()
        self.assertTrue(r["integrity_pass"], r)
        self.assertFalse(r["provenance_verified"])
        self.assertFalse(r["training_approved"])

    def test_manifest_and_repin_without_signature_rejected(self):
        self.manifest.write_text('{"samples":["changed"]}')
        self.doc["manifest_sha256"] = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        self.ledger.write_text(json.dumps(self.doc))
        self.assertFalse(self.result()["integrity_pass"])

    def test_old_valid_signature_rejected_by_checkpoint(self):
        self.checkpoint["min_version"] = 4
        self.cp.write_text(json.dumps(self.checkpoint))
        r = self.result()
        self.assertTrue(r["replay_rejected"])
        self.assertFalse(r["integrity_pass"])

    def test_wrong_signer_rejected(self):
        self.checkpoint["signer_id"] = "other"
        self.cp.write_text(json.dumps(self.checkpoint))
        self.assertFalse(self.result()["integrity_pass"])

    def test_expired_signed_ledger_rejected(self):
        self.doc["expires_at"] = "2000-01-01T00:00:00Z"
        self.sign()
        self.assertFalse(self.result()["integrity_pass"])

    def test_missing_signature_rejected(self):
        self.sig.unlink()
        self.assertFalse(self.result()["integrity_pass"])

    def test_dataset_identity_tamper_rejected(self):
        self.doc["dataset_id"] = "other"
        self.sign()
        self.assertFalse(self.result()["integrity_pass"])

    def test_duplicate_json_keys_rejected(self):
        self.ledger.write_text('{"dataset_id":"fixture","dataset_id":"other"}')
        self.assertFalse(self.result()["integrity_pass"])

if __name__ == "__main__":
    unittest.main()
