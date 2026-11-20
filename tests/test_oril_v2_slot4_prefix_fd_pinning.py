"""POSIX descriptor pinning regression; synthetic filesystem only, not real Qwen."""
import hashlib
import os
from pathlib import Path
from unittest.mock import patch
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_paired_prompt_variant_adapter import read_prefix


@unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"), "POSIX only")
class PinnedPrefixTests(unittest.TestCase):
    def test_fifo_without_reader_fails_immediately(self):
        with tempfile.TemporaryDirectory() as root:
            fifo = Path(root) / "prompt.fifo"
            os.mkfifo(fifo)
            with self.assertRaisesRegex(ValueError, "regular local file"):
                read_prefix(fifo, "0" * 64)

    def test_parent_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            real = Path(root) / "real"
            real.mkdir()
            (real / "prefix.txt").write_text("SAFE")
            alias = Path(root) / "alias"
            alias.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlinked"):
                read_prefix(alias / "prefix.txt", hashlib.sha256(b"SAFE").hexdigest())

    def test_parent_rename_swap_after_open_does_not_redirect(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            real = root / "real"
            real.mkdir()
            (real / "prefix.txt").write_text("SAFE")
            attacker = root / "attacker"
            attacker.mkdir()
            (attacker / "prefix.txt").write_text("EVIL")
            original_open = os.open
            triggered = [False]

            def swap_on_file_open(path, flags, *args, **kwargs):
                if path == "prefix.txt" and not triggered[0]:
                    triggered[0] = True
                    real.rename(root / "old-real")
                    real.symlink_to(attacker, target_is_directory=True)
                return original_open(path, flags, *args, **kwargs)

            with patch("oril_v2_paired_prompt_variant_adapter.os.open", side_effect=swap_on_file_open):
                actual = read_prefix(real / "prefix.txt", hashlib.sha256(b"SAFE").hexdigest())
            self.assertTrue(triggered[0])
            self.assertEqual(actual, "SAFE")

    def test_symlink_swap_at_file_open_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            target = root / "target"
            target.write_text("SAFE")
            source = root / "prefix.txt"
            source.write_text("SAFE")
            original_open = os.open
            triggered = [False]

            def swap_on_file_open(path, flags, *args, **kwargs):
                if path == "prefix.txt" and not triggered[0]:
                    triggered[0] = True
                    source.unlink()
                    source.symlink_to(target)
                return original_open(path, flags, *args, **kwargs)

            with patch("oril_v2_paired_prompt_variant_adapter.os.open", side_effect=swap_on_file_open):
                with self.assertRaisesRegex(ValueError, "symlinked"):
                    read_prefix(source, hashlib.sha256(b"SAFE").hexdigest())
            self.assertTrue(triggered[0])

    def test_nonexistent_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, "unreadable"):
                read_prefix(Path(root) / "missing.txt", "0" * 64)

    def test_original_prefix_sha_still_verified(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "prefix.txt"
            p.write_text("SAFE")
            with self.assertRaisesRegex(ValueError, "SHA mismatch"):
                read_prefix(p, hashlib.sha256(b"EVIL").hexdigest())

    def test_normal_unicode_prefix(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "prefix.txt"
            p.write_text("검수된 교사 사례", encoding="utf-8")
            self.assertEqual(read_prefix(p, hashlib.sha256(p.read_bytes()).hexdigest()), "검수된 교사 사례")


if __name__ == "__main__":
    unittest.main()
