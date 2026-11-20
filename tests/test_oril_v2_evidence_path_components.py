"""Regression tests for symlinked ancestors of candidate GPU logs and adapters."""
import hashlib
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import test_oril_v2_training_evidence_audit as fixtures
from oril_v2_evidence_path_components import check_components
from oril_v2_gpu_log_byte_audit import check_log_bytes


class EvidenceAncestorTests(unittest.TestCase):
    def write(self):
        fixtures.TrainingEvidenceAuditTests.write(self)

    def setUp(self):
        fixtures.TrainingEvidenceAuditTests.setUp(self)
        self.log = self.root / "gpu.log"
        self.log.write_bytes(b"synthetic-log")

    def audit(self, log="gpu.log"):
        return check_components(self.root, self.evidence, log)

    def test_clean_evidence_accepted_without_gpu_attestation(self):
        r = self.audit()
        self.assertTrue(r["path_components_verified"], r)
        self.assertTrue(r["evidence_consistent"], r)
        self.assertFalse(r["gpu_execution_attested"])
        self.assertFalse(r["training_approved"])

    def test_symlinked_log_parent_rejected_even_if_inside_root(self):
        real = self.root / "real_logs"
        real.mkdir()
        (real / "gpu.log").write_bytes(self.log.read_bytes())
        (self.root / "alias_logs").symlink_to(real, target_is_directory=True)
        # Parent check accepts matching bytes via the symlinked directory.
        self.assertTrue(check_log_bytes(self.root, self.evidence, "alias_logs/gpu.log")["evidence_consistent"])
        r = self.audit("alias_logs/gpu.log")
        self.assertFalse(r["evidence_consistent"], r)
        self.assertIn("symlink", r["reason"])

    def test_symlinked_adapter_parent_rejected_even_if_inside_root(self):
        real = self.root / "real_adapter"
        real.mkdir()
        (real / "weights.bin").write_bytes(self.adapter.read_bytes())
        (self.root / "alias_adapter").symlink_to(real, target_is_directory=True)
        self.doc["adapter"]["path"] = "alias_adapter/weights.bin"
        self.write()
        self.assertTrue(check_log_bytes(self.root, self.evidence, "gpu.log")["evidence_consistent"])
        r = self.audit()
        self.assertFalse(r["evidence_consistent"], r)
        self.assertIn("symlink", r["reason"])

    def test_missing_log_rejected(self):
        self.log.unlink()
        self.assertFalse(self.audit()["evidence_consistent"])

    def test_escape_rejected(self):
        self.assertFalse(self.audit("../gpu.log")["evidence_consistent"])

    def test_claimed_hash_mismatch_rejected(self):
        self.log.write_bytes(b"changed")
        self.assertFalse(self.audit()["evidence_consistent"])


if __name__ == "__main__":
    unittest.main()
