"""End-to-end mutation tests for the exact-count gate.

Unlike fabricated output strings, these tests execute real unittest modules in
separate subprocesses and feed their actual stdout/stderr into the audit gate.
No production tests, approval gate or existing verifier are modified.
"""
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_exact_test_count_audit import check_result


class ActualSubprocessMutationTests(unittest.TestCase):
    def run_fixture(self, fixture):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "test_mutation_fixture.py"
            path.write_text(textwrap.dedent(fixture), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", tmp,
                 "-p", "test_mutation_fixture.py", "-v"],
                capture_output=True, text=True, timeout=30, check=False)
        return result.stdout + result.stderr, result.returncode

    def test_unmodified_fixture_passes_gate(self):
        output, status = self.run_fixture("""
            import unittest
            class Fixture(unittest.TestCase):
                def test_one(self): self.assertTrue(True)
                def test_two(self): self.assertEqual(2, 2)
        """)
        self.assertEqual(check_result(output, status, 2), 2)

    def test_removed_test_rejected_even_when_unittest_reports_ok(self):
        output, status = self.run_fixture("""
            import unittest
            class Fixture(unittest.TestCase):
                def test_one(self): self.assertTrue(True)
                def helper_two(self): self.assertEqual(2, 2)
        """)
        self.assertEqual(status, 0)
        with self.assertRaisesRegex(ValueError, "test count drift"):
            check_result(output, status, 2)

    def test_skipped_test_rejected_even_when_unittest_reports_ok(self):
        output, status = self.run_fixture("""
            import unittest
            class Fixture(unittest.TestCase):
                def test_one(self): self.assertTrue(True)
                @unittest.skip("mutated skip")
                def test_two(self): self.assertTrue(True)
        """)
        self.assertEqual(status, 0)
        with self.assertRaisesRegex(ValueError, "skipped test"):
            check_result(output, status, 2)

    def test_failing_test_rejected_by_process_exit(self):
        output, status = self.run_fixture("""
            import unittest
            class Fixture(unittest.TestCase):
                def test_one(self): self.assertTrue(True)
                def test_two(self): self.fail("mutated failure")
        """)
        self.assertNotEqual(status, 0)
        with self.assertRaisesRegex(ValueError, "nonzero unittest exit"):
            check_result(output, status, 2)

    def test_extra_test_rejected_even_when_unittest_reports_ok(self):
        output, status = self.run_fixture("""
            import unittest
            class Fixture(unittest.TestCase):
                def test_one(self): self.assertTrue(True)
                def test_two(self): self.assertTrue(True)
                def test_three(self): self.assertTrue(True)
        """)
        self.assertEqual(status, 0)
        with self.assertRaisesRegex(ValueError, "test count drift"):
            check_result(output, status, 2)


if __name__ == "__main__":
    unittest.main()
