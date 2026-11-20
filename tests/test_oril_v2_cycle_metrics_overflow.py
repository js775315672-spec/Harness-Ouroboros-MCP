"""Regression tests for finite-only cycle trend outputs and overflow-safe arithmetic."""
import json
import math
import unittest

from scripts.oril_v2_cycle_metrics import compare


def sample(values):
    return [{"cycle_id": str(i), "task_type": "validator", "difficulty": "small",
             "total_seconds": v} for i, v in enumerate(values)]


class OverflowSafetyTests(unittest.TestCase):
    def test_huge_ratio_not_false_speed_regression(self):
        result = compare(sample([1e-308, 1e-308, 1e-308, 1e308]), "3")
        metric = result["metrics"]["total_seconds"]
        self.assertEqual(metric["verdict"], "판단불가")
        self.assertIsNone(metric["change_pct"])
        json.dumps(result, allow_nan=False)

    def test_huge_ratio_not_false_improvement(self):
        result = compare(sample([1e-308, 1e-308, 1e-308, 1e308]), "3")
        self.assertNotEqual(result["metrics"]["total_seconds"]["verdict"], "향상")

    def test_nan_current_serializes_strict_json(self):
        result = compare(sample([100, 90, 80, math.nan]), "3")
        self.assertIsNone(result["metrics"]["total_seconds"]["current"])
        json.dumps(result, allow_nan=False)

    def test_inf_current_serializes_strict_json(self):
        result = compare(sample([100, 90, 80, math.inf]), "3")
        self.assertIsNone(result["metrics"]["total_seconds"]["current"])
        json.dumps(result, allow_nan=False)

    def test_negative_current_is_unmeasured(self):
        result = compare(sample([100, 90, 80, -1]), "3")
        self.assertIsNone(result["metrics"]["total_seconds"]["current"])
        self.assertEqual(result["metrics"]["total_seconds"]["verdict"], "판단불가")

    def test_extremely_large_integer_history_not_crash(self):
        result = compare(sample([10 ** 1000, 100, 90, 80]), "3")
        self.assertEqual(result["metrics"]["total_seconds"]["n"], 2)
        self.assertEqual(result["metrics"]["total_seconds"]["verdict"], "판단불가")

    def test_extremely_large_integer_current_not_crash(self):
        result = compare(sample([100, 90, 80, 10 ** 1000]), "3")
        self.assertIsNone(result["metrics"]["total_seconds"]["current"])
        json.dumps(result, allow_nan=False)

    def test_finite_control_remains_improvement(self):
        result = compare(sample([100, 90, 80, 70]), "3")
        self.assertEqual(result["metrics"]["total_seconds"]["verdict"], "향상")
        self.assertEqual(result["metrics"]["total_seconds"]["change_pct"], -22.22)


if __name__ == "__main__":
    unittest.main()
