"""Mutation proof against the actual 100-test integrated ORIL suite.

All edits occur inside an isolated temporary copy. Never edits source checkout,
protected verifier, or operational approval gates.
"""
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
AUDITOR = "scripts/oril_v2_exact_test_count_audit.py"
TARGET = "tests/test_oril_v2_signed_ledger_boundary.py"


class RealIntegratedMutationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        for name in ("scripts", "tests"):
            shutil.copytree(ROOT / name, self.root / name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        self.target = self.root / TARGET
        self.assertTrue(self.target.is_file())
        self.original = self.target.read_text(encoding="utf-8")

    def run_audit(self):
        return subprocess.run(
            [sys.executable, AUDITOR], cwd=self.root, text=True,
            capture_output=True, timeout=180, check=False)

    def mutate(self, replacement):
        match = re.search(r"(?m)^(?P<indent>[ \t]*)def test_[A-Za-z0-9_]+\(self\):", self.original)
        self.assertIsNotNone(match, "fixture must contain an actual test method")
        altered = replacement(match)
        self.target.write_text(
            self.original[:match.start()] + altered + self.original[match.end():],
            encoding="utf-8")

    def test_real_integrated_baseline_exact_100(self):
        run = self.run_audit()
        self.assertEqual(run.returncode, 0, run.stdout[-3000:] + run.stderr)
        self.assertIn("EXACT_INTEGRATED_TOTAL=100 SKIPPED=0", run.stdout)

    def test_real_integrated_removed_test_fails_closed(self):
        def remove(match):
            return match.group(0).replace("def test_", "def helper_", 1)
        self.mutate(remove)
        run = self.run_audit()
        self.assertNotEqual(run.returncode, 0, run.stdout[-3000:] + run.stderr)
        self.assertIn("test count drift: expected 10, got 9", run.stderr)
        self.assertNotIn("EXACT_INTEGRATED_TOTAL=100", run.stdout)

    def test_real_integrated_skipped_test_fails_closed(self):
        def skip(match):
            return (match.group("indent") +
                    '@__import__("unittest").skip("injected integration mutation")\n' +
                    match.group(0))
        self.mutate(skip)
        run = self.run_audit()
        self.assertNotEqual(run.returncode, 0, run.stdout[-3000:] + run.stderr)
        self.assertIn("skipped test detected", run.stderr)
        self.assertNotIn("EXACT_INTEGRATED_TOTAL=100", run.stdout)


if __name__ == "__main__":
    unittest.main()
