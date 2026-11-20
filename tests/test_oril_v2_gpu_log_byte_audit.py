"""Synthetic GPU log byte checks; never claims that a GPU was used."""
import hashlib
import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
from test_oril_v2_training_evidence_audit import TrainingEvidenceAuditTests
from oril_v2_gpu_log_byte_audit import check_log_bytes


class GPUByteEvidenceTests(unittest.TestCase):
    def write(self):
        TrainingEvidenceAuditTests.write(self)

    def setUp(self):
        TrainingEvidenceAuditTests.setUp(self)
        self.log = self.root / "gpu.log"
        self.log.write_bytes(b"synthetic-log")

    def audit(self, path="gpu.log"):
        return check_log_bytes(self.root, self.evidence, path)

    def test_matching_bytes_do_not_attest_gpu(self):
        out = self.audit()
        self.assertTrue(out["log_bytes_verified"], out)
        self.assertTrue(out["evidence_consistent"])
        for k in ("gpu_execution_attested", "independent_evaluation_verified",
                  "intelligence_improved", "training_approved", "promotion_approved"):
            self.assertFalse(out[k], k)

    def test_missing_log_fails_closed(self):
        self.log.unlink()
        self.assertFalse(self.audit()["evidence_consistent"])

    def test_changed_log_fails_closed(self):
        self.log.write_bytes(b"tampered")
        self.assertIn("digest mismatch", self.audit()["reason"])

    def test_wrong_claimed_log_hash_fails_closed(self):
        self.doc["gpu"]["log_sha256"] = hashlib.sha256(b"fake").hexdigest()
        self.write()
        self.assertFalse(self.audit()["log_bytes_verified"])

    def test_symlink_log_fails_closed(self):
        other = self.root / "other.log"
        other.write_bytes(self.log.read_bytes())
        self.log.unlink()
        self.log.symlink_to(other)
        self.assertFalse(self.audit()["log_bytes_verified"])

    def test_parent_invalid_adapter_fails_closed(self):
        self.adapter.unlink()
        self.assertFalse(self.audit()["evidence_consistent"])

    def test_escape_and_absolute_paths_fail_closed(self):
        for path in ("../gpu.log", "/tmp/gpu.log", "a\\gpu.log", ""):
            with self.subTest(path=path):
                self.assertFalse(self.audit(path)["evidence_consistent"])

    def test_fake_log_and_matching_digest_are_not_attestation(self):
        self.log.write_bytes(b"fabricated-gpu-training-report")
        self.doc["gpu"]["log_sha256"] = hashlib.sha256(self.log.read_bytes()).hexdigest()
        self.write()
        out = self.audit()
        self.assertTrue(out["log_bytes_verified"])
        self.assertFalse(out["gpu_execution_attested"])

    def test_cli_success_and_reject(self):
        cmd = [sys.executable, str(ROOT / "scripts/oril_v2_gpu_log_byte_audit.py"),
               "--root", str(self.root), "--evidence", str(self.evidence),
               "--log-path", "gpu.log"]
        ok = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        self.log.unlink()
        bad = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1, bad.stdout + bad.stderr)


if __name__ == "__main__":
    unittest.main()
