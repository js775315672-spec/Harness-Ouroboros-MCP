"""Reject invented fractional events while preserving real continuous timings."""
import json
import unittest
from scripts.oril_v2_cycle_metrics import compare, valid_metric

COUNT_FIELDS = ("accepted_improvements", "retries", "failures", "regressions", "rollbacks")


def data(field, history, current):
    return [
        {"cycle_id": str(i), "task_type": "same", "difficulty": "small", field: value}
        for i, value in enumerate([*history, current])
    ]


class DiscreteCountsTests(unittest.TestCase):
    def test_fractional_current_counts_unmeasured_for_each_count_field(self):
        for field in COUNT_FIELDS:
            with self.subTest(field=field):
                metric = compare(data(field, [1, 2, 3], 1.5), "3")["metrics"][field]
                self.assertIsNone(metric["current"])
                self.assertEqual(metric["verdict"], "판단불가")

    def test_fractional_history_does_not_count_as_a_sample(self):
        metric = compare(data("accepted_improvements", [1, 2.5, 3, 4], 2), "4")["metrics"]["accepted_improvements"]
        self.assertEqual(metric["n"], 3)
        self.assertEqual(metric["previous_median"], 3)

    def test_fractional_history_below_threshold_remains_unknown(self):
        metric = compare(data("failures", [1.5, 2, 3], 1), "3")["metrics"]["failures"]
        self.assertEqual(metric["n"], 2)
        self.assertEqual(metric["verdict"], "판단불가")

    def test_integral_float_count_rejected(self):
        self.assertFalse(valid_metric("retries", 2.0))

    def test_boolean_count_rejected(self):
        self.assertFalse(valid_metric("rollbacks", True))

    def test_negative_count_rejected(self):
        self.assertFalse(valid_metric("regressions", -1))

    def test_integer_count_still_compares(self):
        metric = compare(data("accepted_improvements", [1, 2, 3], 4), "3")["metrics"]["accepted_improvements"]
        self.assertEqual(metric["verdict"], "향상")
        json.dumps(metric, allow_nan=False)

    def test_fractional_duration_remains_valid(self):
        metric = compare(data("total_seconds", [2.0, 2.5, 3.0], 1.5), "3")["metrics"]["total_seconds"]
        self.assertEqual(metric["verdict"], "향상")
        self.assertEqual(metric["current"], 1.5)


if __name__ == "__main__":
    unittest.main()
