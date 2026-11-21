"""Offline safety tests for P5->P6 public prompt selection; no model downloads."""
import unittest
from oril.orchestrator import plan


class PlanGuardTests(unittest.TestCase):
    def test_clean_first_candidate(self):
        self.assertEqual(plan({"tried": [], "candidate_errors": 0}), "remove_redundancy")

    def test_errors_change_priority(self):
        self.assertEqual(plan({"tried": [], "candidate_errors": 1}), "integer_format")

    def test_previous_trials_not_repeated(self):
        self.assertEqual(plan({"tried": ["integer_format"], "candidate_errors": 1}), "check_sum")

    def test_exhausted_budget_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "budget exhausted"):
            plan({"tried": ["remove_redundancy", "integer_format", "check_sum"], "candidate_errors": 0})

    def test_duplicate_trial_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "prompt history"):
            plan({"tried": ["integer_format", "integer_format"], "candidate_errors": 1})

    def test_unknown_trial_fails_closed(self):
        with self.assertRaises(ValueError):
            plan({"tried": ["invented_strategy"], "candidate_errors": 1})

    def test_bad_history_type_fails_closed(self):
        with self.assertRaises(ValueError):
            plan({"tried": "integer_format", "candidate_errors": 1})

    def test_negative_errors_fails_closed(self):
        with self.assertRaises(ValueError):
            plan({"tried": [], "candidate_errors": -1})

    def test_error_count_above_public_suite_fails_closed(self):
        with self.assertRaises(ValueError):
            plan({"tried": [], "candidate_errors": 31})

    def test_boolean_error_count_fails_closed(self):
        with self.assertRaises(ValueError):
            plan({"tried": [], "candidate_errors": True})

    def test_missing_memory_fields_fails_closed(self):
        with self.assertRaises(ValueError):
            plan({})


if __name__ == "__main__":
    unittest.main()
