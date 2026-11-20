"""Prevent finite history samples from creating non-finite medians."""
import json
import math
import unittest

from scripts.oril_v2_cycle_metrics import compare, finite_median


def records(history, current):
    return [
        {"cycle_id": str(i), "task_type": "validator", "difficulty": "small", "total_seconds": value}
        for i, value in enumerate([*history, current])
    ]


class FiniteMedianTests(unittest.TestCase):
    def test_even_two_large_finite_values(self):
        self.assertEqual(finite_median([1e308, 1e308]), 1e308)

    def test_even_four_large_finite_values(self):
        self.assertEqual(finite_median([1e308] * 4), 1e308)

    def test_even_mixed_values(self):
        self.assertEqual(finite_median([8e307, 9e307, 1e308, 1e308]), 9.5e307)

    def test_odd_history_control(self):
        self.assertEqual(finite_median([3, 1, 2]), 2)

    def test_even_history_control(self):
        self.assertEqual(finite_median([1, 3, 5, 7]), 4)

    def test_four_large_history_strict_json(self):
        result = compare(records([1e308] * 4, 1e308), "4")
        metric = result["metrics"]["total_seconds"]
        self.assertTrue(math.isfinite(metric["previous_median"]))
        self.assertEqual(metric["verdict"], "유지")
        json.dumps(result, allow_nan=False)

    def test_four_large_history_current_small_strict_json(self):
        result = compare(records([1e308] * 4, 1e307), "4")
        self.assertEqual(result["metrics"]["total_seconds"]["verdict"], "향상")
        json.dumps(result, allow_nan=False)

    def test_invalid_current_still_unmeasured(self):
        result = compare(records([1e308] * 4, math.inf), "4")
        self.assertEqual(result["metrics"]["total_seconds"]["verdict"], "판단불가")
        self.assertIsNone(result["metrics"]["total_seconds"]["current"])
        json.dumps(result, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
