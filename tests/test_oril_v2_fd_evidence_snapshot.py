"""Offline POSIX evidence snapshot adversarial regression."""
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
class SnapshotTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name) / "root"
        self.root.mkdir()
        (self.root / "dir").mkdir()
        self.file = self.root / "dir" / "evidence.log"
        self.file.write_bytes(b"approved")
        self.digest = hashlib.sha256(b"approved").hexdigest()

    def read(self, path="dir/evidence.log", digest=None):
        return read_evidence_snapshot(self.root, path, self.digest if digest is None else digest)

    def test_regular_file(self):
        self.assertEqual(self.read(), b"approved")

    def test_modified_bytes(self):
        self.file.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            self.read()

    def test_symlinked_file_rejected(self):
        self.file.rename(self.root / "outside")
        self.file.symlink_to(self.root / "outside")
        with self.assertRaises(OSError):
            self.read()

    def test_symlinked_parent_rejected(self):
        (self.root / "dir").rename(self.root / "actual")
        (self.root / "dir").symlink_to(self.root / "actual", target_is_directory=True)
        with self.assertRaises(OSError):
            self.read()

    def test_dot_dot_and_absolute_rejected(self):
        for path in ("../dir/evidence.log", "dir/../dir/evidence.log",
                     "/etc/passwd", "./dir/evidence.log", "dir//evidence.log", ""):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.read(path)

    def test_untrusted_digest_rejected(self):
        for digest in ("", "A" * 64, "0" * 63, True):
            with self.subTest(digest=digest), self.assertRaises(ValueError):
                self.read(digest=digest)

    def test_directory_as_file_rejected(self):
        with self.assertRaises((ValueError, OSError)):
            self.read("dir")

    def test_oversized_file_rejected(self):
        with self.assertRaisesRegex(ValueError, "oversized"):
            read_evidence_snapshot(self.root, "dir/evidence.log", self.digest, max_bytes=2)

    def test_root_symlink_rejected(self):
        link = self.root.parent / "rootlink"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            read_evidence_snapshot(link, "dir/evidence.log", self.digest)

    def test_replacement_after_directory_open_does_not_redirect(self):
        """Swap dir path immediately after its FD opens, before final file open."""
        original_open = os.open
        swapped = [False]
        def swap_open(path, flags, *args, **kwargs):
            fd = original_open(path, flags, *args, **kwargs)
            if path == "dir" and not swapped[0]:
                swapped[0] = True
                (self.root / "dir").rename(self.root / "trusted")
                (self.root / "dir").mkdir()
                (self.root / "dir" / "evidence.log").write_bytes(b"evil")
            return fd
        with mock.patch("oril_v2_fd_evidence_snapshot.os.open", side_effect=swap_open):
            self.assertEqual(self.read(), b"approved")
        self.assertTrue(swapped[0])

    def test_fifo_rejected_without_blocking(self):
        self.file.unlink()
        os.mkfifo(self.file)
        with self.assertRaises(ValueError):
            self.read()

    def test_candidate_controls_both_bytes_and_digest_is_not_attestation(self):
        self.file.write_bytes(b"attacker-controlled")
        attacker_digest = hashlib.sha256(b"attacker-controlled").hexdigest()
        self.assertEqual(self.read(digest=attacker_digest), b"attacker-controlled")

if __name__ == "__main__":
    unittest.main()
