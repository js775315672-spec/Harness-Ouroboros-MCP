"""Regression tests for the dependency-free scanner."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "harness_check.py"
spec = importlib.util.spec_from_file_location("harness_check", SCRIPT)
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)

class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def put(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        subprocess.run(["git", "-C", str(self.root), "add", name], check=True)

    def test_clean(self):
        self.put("README.md", b"safe text")
        self.assertEqual(scanner.scan(self.root), ([], []))

    def test_github_token(self):
        self.put("config.txt", b"ghp_" + b"A" * 36)
        self.assertTrue(scanner.scan(self.root)[0])

    def test_large_file_not_skipped(self):
        self.put("large.txt", b"x" * (1024 * 1024 + 5) + b"AKIA" + b"A" * 16)
        self.assertTrue(scanner.scan(self.root)[0])

    def test_same_name_is_scanned(self):
        self.put("other/harness_check.py", b"ghp_" + b"B" * 36)
        self.assertTrue(scanner.scan(self.root)[0])

    def test_binary_fails_closed(self):
        self.put("binary.bin", b"abc\0def")
        self.assertTrue(scanner.scan(self.root)[1])

    def test_missing_tracked_file_fails_closed(self):
        self.put("missing.txt", b"hello")
        (self.root / "missing.txt").unlink()
        self.assertTrue(scanner.scan(self.root)[1])

    def test_untracked_file_ignored(self):
        self.put("tracked.txt", b"safe")
        (self.root / "untracked.txt").write_bytes(b"ghp_" + b"C" * 36)
        self.assertEqual(scanner.scan(self.root), ([], []))

if __name__ == "__main__":
    unittest.main()
