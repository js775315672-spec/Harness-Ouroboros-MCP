"""Test source semantic mutation is caught only with a separately frozen digest."""
import hashlib
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from oril_v2_external_test_source_pin import verify, TARGET

BEFORE = '''    def test_missing_signature_rejected(self):
        self.sig.unlink()
        self.assertFalse(self.result()["integrity_pass"])
'''
AFTER = '''    def test_missing_signature_rejected(self):
        self.assertTrue(True)
'''


class ExternalTestSourcePin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        target = self.root / TARGET
        target.parent.mkdir(parents=True)
        self.original = (ROOT / TARGET).read_bytes()
        target.write_bytes(self.original)
        self.target = target
        self.pin = hashlib.sha256(self.original).hexdigest()

    def test_unmodified_source_matches_frozen_digest(self):
        result = verify(self.root, self.pin)
        self.assertTrue(result["test_source_integrity_pass"], result)
        self.assertFalse(result["independent_authority_verified"])
        self.assertFalse(result["training_approved"])

    def test_semantic_assertion_weakening_rejected(self):
        original = self.original.decode()
        self.assertEqual(original.count(BEFORE), 1, "mutation target drift")
        self.target.write_text(original.replace(BEFORE, AFTER, 1))
        result = verify(self.root, self.pin)
        self.assertFalse(result["test_source_integrity_pass"], result)
        self.assertIn("differs", result["reason"])

    def test_attacker_supplied_matching_digest_is_not_trust(self):
        original = self.original.decode()
        self.assertEqual(original.count(BEFORE), 1)
        self.target.write_text(original.replace(BEFORE, AFTER, 1))
        forged = hashlib.sha256(self.target.read_bytes()).hexdigest()
        result = verify(self.root, forged)
        self.assertTrue(result["test_source_integrity_pass"], result)
        self.assertFalse(result["independent_authority_verified"])
        self.assertFalse(result["promotion_approved"])

    def test_missing_or_malformed_external_pin_rejected(self):
        for invalid in ("", "Z" * 64, "a" * 63, None, True):
            with self.subTest(pin=repr(invalid)):
                self.assertFalse(verify(self.root, invalid)["test_source_integrity_pass"])

    def test_missing_and_symlink_test_source_rejected(self):
        self.target.unlink()
        self.assertFalse(verify(self.root, self.pin)["test_source_integrity_pass"])
        external = self.root / "external.py"
        external.write_bytes(self.original)
        self.target.symlink_to(external)
        self.assertFalse(verify(self.root, self.pin)["test_source_integrity_pass"])

    def test_cli_failure_and_success_codes(self):
        script = ROOT / "scripts/oril_v2_external_test_source_pin.py"
        args = [sys.executable, str(script), "--root", str(self.root),
                "--trusted-sha256", self.pin]
        ok = subprocess.run(args, text=True, capture_output=True, check=False)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.target.write_bytes(self.original + b"\n# mutation\n")
        bad = subprocess.run(args, text=True, capture_output=True, check=False)
        self.assertEqual(bad.returncode, 1, bad.stdout)
        self.assertIn("false", bad.stdout.lower())


if __name__ == "__main__":
    unittest.main()
