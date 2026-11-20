"""Independent synthetic tests for the pinned dataset signature trust boundary."""
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
from oril_v2_anchored_ledger_boundary import verify_anchored
from oril_v2_signed_ledger_boundary import verify


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AnchoredLedgerTests(unittest.TestCase):
    def setUp(self):
        if not shutil.which("openssl"):
            self.fail("OpenSSL is required; CI must not silently skip the security tests")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        self.manifest = self.root / "manifest.json"
        self.ledger = self.root / "ledger.json"
        self.checkpoint = self.root / "checkpoint.json"
        self.key = self.root / "key.pem"
        self.pub = self.root / "pub.pem"
        self.sig = self.root / "sig.bin"
        self.policy_file = self.root / "policy.json"
        self.manifest.write_bytes(b'{"samples":[]}')
        self._gen_key(self.key, self.pub)
        self.doc = {
            "dataset_id": "dataset-A",
            "manifest_sha256": digest(self.manifest),
            "version": 3,
            "signer_id": "reviewer-A",
            "schema_version": 1,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        }
        self.cp = {"dataset_id": "dataset-A", "signer_id": "reviewer-A", "min_version": 3}
        self._sign(self.key)
        self._write_checkpoint()
        self.policy = self._policy()
        self._write_policy()
        self.trusted_pin = digest(self.policy_file)

    def _gen_key(self, key, pub):
        subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt",
                        "rsa_keygen_bits:2048", "-out", str(key)],
                       check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", str(key), "-pubout", "-out", str(pub)],
                       check=True, capture_output=True)

    def _sign(self, key):
        self.ledger.write_text(json.dumps(self.doc), encoding="utf-8")
        canonical = self.root / "canonical"
        canonical.write_bytes(json.dumps(self.doc, sort_keys=True,
                                         separators=(",", ":"), ensure_ascii=False).encode())
        subprocess.run(["openssl", "dgst", "-sha256", "-sign", str(key),
                        "-out", str(self.sig), str(canonical)],
                       capture_output=True, check=True)

    def _write_checkpoint(self):
        self.checkpoint.write_text(json.dumps(self.cp), encoding="utf-8")

    def _policy(self):
        return {"schema_version": 1, "dataset_id": "dataset-A", "signer_id": "reviewer-A",
                "min_version": self.cp["min_version"], "public_key_sha256": digest(self.pub),
                "checkpoint_sha256": digest(self.checkpoint)}

    def _write_policy(self):
        self.policy_file.write_text(json.dumps(self.policy, sort_keys=True), encoding="utf-8")

    def result(self, pin=None):
        return verify_anchored(self.manifest, self.ledger, self.sig, self.pub,
                               self.checkpoint, self.policy_file,
                               self.trusted_pin if pin is None else pin)

    def test_valid_pin_matches_but_does_not_certify_provenance(self):
        out = self.result()
        self.assertTrue(out["anchor_consistent"], out)
        self.assertTrue(out["signature_valid"], out)
        self.assertTrue(out["integrity_pass"], out)
        for key in ("provenance_verified", "training_approved", "promotion_approved"):
            self.assertFalse(out[key])

    def test_missing_trusted_pin_rejected(self):
        self.assertFalse(self.result("")["integrity_pass"])

    def test_invalid_pin_format_rejected(self):
        self.assertFalse(self.result("Z" * 64)["integrity_pass"])

    def test_policy_replacement_rejected_with_unchanged_external_pin(self):
        self.policy["signer_id"] = "changed"
        self._write_policy()
        self.assertIn("pin mismatch", self.result()["reason"])

    def test_public_key_swap_rejected(self):
        other_key, other_pub = self.root / "other.key", self.root / "other.pub"
        self._gen_key(other_key, other_pub)
        self.pub.write_bytes(other_pub.read_bytes())
        self.assertIn("public key", self.result()["reason"])

    def test_checkpoint_downgrade_rejected(self):
        self.cp["min_version"] = 1
        self._write_checkpoint()
        self.assertIn("checkpoint", self.result()["reason"])

    def test_attacker_resigns_with_swapped_key_and_lowered_checkpoint(self):
        attacker_key, attacker_pub = self.root / "attacker.key", self.root / "attacker.pub"
        self._gen_key(attacker_key, attacker_pub)
        self.pub.write_bytes(attacker_pub.read_bytes())
        self.cp["min_version"] = 1
        self._write_checkpoint()
        self.doc["version"] = 2
        self._sign(attacker_key)
        # Demonstrate the original caller-provided-key/checkpoint trust gap.
        self.assertTrue(verify(self.manifest, self.ledger, self.sig,
                               self.pub, self.checkpoint)["integrity_pass"])
        # Frozen policy pin from independent authority blocks this substitution.
        out = self.result()
        self.assertFalse(out["integrity_pass"], out)
        self.assertFalse(out["provenance_verified"])

    def test_attacker_can_defeat_only_a_self_controlled_pin(self):
        attacker_key, attacker_pub = self.root / "attacker.key", self.root / "attacker.pub"
        self._gen_key(attacker_key, attacker_pub)
        self.pub.write_bytes(attacker_pub.read_bytes())
        self.cp["min_version"] = 1
        self._write_checkpoint()
        self.doc["version"] = 2
        self._sign(attacker_key)
        self.policy = self._policy()
        self._write_policy()
        # A compromised trust channel can endorse its own malicious policy.
        # This is an explicit limitation, NOT success at provenance verification.
        out = self.result(pin=digest(self.policy_file))
        self.assertTrue(out["integrity_pass"], out)
        self.assertFalse(out["provenance_verified"], out)
        self.assertFalse(out["training_approved"], out)

    def test_duplicate_policy_json_key_rejected_even_with_matching_pin(self):
        blob = json.dumps(self.policy)
        self.policy_file.write_text(blob[:-1] + ',"schema_version":1}', encoding="utf-8")
        self.assertIn("duplicate", self.result(pin=digest(self.policy_file))["reason"])

    def test_policy_boolean_schema_version_rejected(self):
        self.policy["schema_version"] = True
        self._write_policy()
        self.assertIn("schema_version", self.result(pin=digest(self.policy_file))["reason"])

    def test_policy_and_checkpoint_different_minimum_rejected(self):
        self.policy["min_version"] = 4
        self._write_policy()
        self.assertIn("checkpoint differs", self.result(pin=digest(self.policy_file))["reason"])

    def test_mutated_manifest_rejected_after_pinning(self):
        self.manifest.write_bytes(b'{"samples":["tampered"]}')
        out = self.result()
        self.assertTrue(out["anchor_consistent"])
        self.assertFalse(out["integrity_pass"])
        self.assertTrue(out["signature_valid"])

    def test_expired_re_signed_ledger_rejected(self):
        self.doc["expires_at"] = "2000-01-01T00:00:00Z"
        self._sign(self.key)
        self.assertFalse(self.result()["integrity_pass"])

    def test_checkpoint_boolean_version_rejected(self):
        self.cp["min_version"] = True
        self._write_checkpoint()
        self.policy["checkpoint_sha256"] = digest(self.checkpoint)
        self.policy["min_version"] = True
        self._write_policy()
        self.assertIn("trusted min_version", self.result(pin=digest(self.policy_file))["reason"])


if __name__ == "__main__":
    unittest.main()
