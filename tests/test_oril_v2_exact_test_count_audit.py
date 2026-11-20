"""Mutation tests: the integration audit must not accept misleading green output."""
import pathlib
import sys
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_exact_test_count_audit import check_result, SUITES


class ExactCountAuditTests(unittest.TestCase):
    def test_expected_total_is_100(self):
        self.assertEqual(sum(n for _, n in SUITES), 100)
        self.assertEqual(len({name for name, _ in SUITES}), len(SUITES))

    def test_valid_unittest_output(self):
        self.assertEqual(check_result("Ran 14 tests in 0.123s\n\nOK\n", 0, 14), 14)

    def test_missing_summary_rejected(self):
        with self.assertRaises(ValueError):
            check_result("OK\n", 0, 14)

    def test_wrong_count_rejected(self):
        with self.assertRaises(ValueError):
            check_result("Ran 13 tests in 0.123s\n\nOK\n", 0, 14)

    def test_duplicate_summary_rejected(self):
        with self.assertRaises(ValueError):
            check_result("Ran 14 tests in 0.1s\nRan 14 tests in 0.1s\nOK\n", 0, 14)

    def test_skipped_status_rejected(self):
        with self.assertRaises(ValueError):
            check_result("test_case ... skipped 'no dependency'\nRan 14 tests in 0.1s\nOK\n", 0, 14)

    def test_skipped_summary_rejected(self):
        with self.assertRaises(ValueError):
            check_result("Ran 14 tests in 0.1s\nOK (skipped=1)\n", 0, 14)

    def test_nonzero_exit_rejected(self):
        with self.assertRaises(ValueError):
            check_result("Ran 14 tests in 0.1s\nOK\n", 1, 14)

    def test_failure_marker_rejected(self):
        with self.assertRaises(ValueError):
            check_result("FAIL: test_x\nRan 14 tests in 0.1s\nOK\n", 0, 14)

    def test_no_final_ok_rejected(self):
        with self.assertRaises(ValueError):
            check_result("Ran 14 tests in 0.1s\n", 0, 14)


if __name__ == "__main__":
    unittest.main()
