"""Demonstrate semantic test weakening invisible to exact-count auditing.

Only a disposable copy is modified. A frozen SHA256 snapshot, held outside
that copy, detects the change. This is NOT a protected production trust root.
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGET = pathlib.Path("tests/test_oril_v2_signed_ledger_boundary.py")
AUDITOR = pathlib.Path("scripts/oril_v2_exact_test_count_audit.py")
BEFORE = '''    def test_missing_signature_rejected(self):
        self.sig.unlink()
        self.assertFalse(self.result()["integrity_pass"])
'''
AFTER = '''    def test_missing_signature_rejected(self):
        self.assertTrue(True)
'''


def sha256(blob):
    return hashlib.sha256(blob).hexdigest()


class SemanticMutationProof(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        for directory in ("scripts", "tests"):
            shutil.copytree(ROOT / directory, self.root / directory,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        self.target = self.root / TARGET
        self.original = (ROOT / TARGET).read_bytes()
        self.frozen_digest = sha256(self.original)
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(self.original.decode("utf-8").count(BEFORE), 1,
                         "Targeted security test changed; do not silently retarget mutation")

    def audit(self):
        return subprocess.run([sys.executable, str(self.root / AUDITOR)],
                              cwd=self.root, text=True, capture_output=True,
                              timeout=180, check=False)

    def test_unmodified_suite_matches_frozen_digest_and_passes(self):
        self.assertEqual(sha256(self.target.read_bytes()), self.frozen_digest)
        result = self.audit()
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        self.assertIn("EXACT_INTEGRATED_TOTAL=100 SKIPPED=0", result.stdout)

    def test_same_count_semantic_weakening_passes_audit_but_fails_frozen_digest(self):
        mutated = self.original.decode("utf-8").replace(BEFORE, AFTER, 1).encode("utf-8")
        self.target.write_bytes(mutated)
        self.assertNotEqual(sha256(self.target.read_bytes()), self.frozen_digest,
                            "Frozen independent test-file digest must reject mutation")
        result = self.audit()
        self.assertEqual(result.returncode, 0,
                         "The count-only auditor unexpectedly rejected this mutation; "
                         "reassess hypothesis: " + result.stderr[-3000:])
        self.assertIn("EXACT_INTEGRATED_TOTAL=100 SKIPPED=0", result.stdout)
        self.assertNotIn("skipped test detected", result.stderr)


if __name__ == "__main__":
    unittest.main()
