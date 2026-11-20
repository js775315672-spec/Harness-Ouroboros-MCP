"""Independent negative cases for caller-supplied root descriptor (synthetic only)."""
import hashlib
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_preopened_root_fd import read_from_trusted_root_fd


@unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"), "POSIX only")
class PreopenedRootFDTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name) / "root"
        (self.root / "dir").mkdir(parents=True)
        (self.root / "dir" / "evidence.log").write_bytes(b"approved")
        self.good = hashlib.sha256(b"approved").hexdigest()
        self.evil = hashlib.sha256(b"attacker").hexdigest()
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.addCleanup(os.close, self.fd)

    def test_trusted_original(self):
        self.assertEqual(read_from_trusted_root_fd(self.fd, "dir/evidence.log", self.good), b"approved")

    def test_root_path_replaced_but_fd_remains_original(self):
        self.root.rename(self.root.parent / "original")
        (self.root / "dir").mkdir(parents=True)
        (self.root / "dir" / "evidence.log").write_bytes(b"attacker")
        self.assertEqual(read_from_trusted_root_fd(self.fd, "dir/evidence.log", self.good), b"approved")

    def test_attacker_digest_does_not_redirect_trusted_fd(self):
        self.root.rename(self.root.parent / "original")
        (self.root / "dir").mkdir(parents=True)
        (self.root / "dir" / "evidence.log").write_bytes(b"attacker")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            read_from_trusted_root_fd(self.fd, "dir/evidence.log", self.evil)

    def test_symlink_parent_rejected(self):
        (self.root / "dir").rename(self.root / "actual")
        (self.root / "dir").symlink_to(self.root / "actual", target_is_directory=True)
        with self.assertRaises(OSError):
            read_from_trusted_root_fd(self.fd, "dir/evidence.log", self.good)

    def test_invalid_root_fd_rejected(self):
        with self.assertRaises(ValueError):
            read_from_trusted_root_fd(-1, "dir/evidence.log", self.good)

    def test_candidate_controlled_fd_and_digest_is_not_provenance(self):
        self.root.rename(self.root.parent / "original")
        (self.root / "dir").mkdir(parents=True)
        (self.root / "dir" / "evidence.log").write_bytes(b"attacker")
        attacker_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            self.assertEqual(read_from_trusted_root_fd(attacker_fd, "dir/evidence.log", self.evil), b"attacker")
        finally:
            os.close(attacker_fd)


if __name__ == "__main__":
    unittest.main()
