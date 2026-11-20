"""Adversarial root-binding boundary tests for the experimental FD snapshot.

These tests deliberately DO NOT certify root provenance or GPU execution.
"""
import hashlib
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_fd_evidence_snapshot import read_evidence_snapshot


@unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"), "POSIX only")
class RootBindingBoundaryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = pathlib.Path(tmp.name)
        self.root = base / "root"
        self.root.mkdir()
        (self.root / "dir").mkdir()
        (self.root / "dir" / "evidence.log").write_bytes(b"approved")
        self.good = hashlib.sha256(b"approved").hexdigest()
        self.evil = hashlib.sha256(b"attacker").hexdigest()

    def swap_root(self):
        self.root.rename(self.root.parent / "original")
        self.root.mkdir()
        (self.root / "dir").mkdir()
        (self.root / "dir" / "evidence.log").write_bytes(b"attacker")

    def test_root_swap_before_open_rejected_by_independent_digest(self):
        self.swap_root()
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            read_evidence_snapshot(self.root, "dir/evidence.log", self.good)

    def test_root_swap_before_open_with_candidate_digest_passes_not_attestation(self):
        self.swap_root()
        self.assertEqual(read_evidence_snapshot(self.root, "dir/evidence.log", self.evil), b"attacker")

    def test_root_swap_after_open_stays_on_original_inode(self):
        original_open = os.open
        swapped = [False]
        def intercept(path, flags, *args, **kwargs):
            fd = original_open(path, flags, *args, **kwargs)
            if pathlib.Path(path) == self.root and not swapped[0]:
                swapped[0] = True
                self.swap_root()
            return fd
        with mock.patch("oril_v2_fd_evidence_snapshot.os.open", side_effect=intercept):
            payload = read_evidence_snapshot(self.root, "dir/evidence.log", self.good)
        self.assertTrue(swapped[0])
        self.assertEqual(payload, b"approved")


if __name__ == "__main__":
    unittest.main()
