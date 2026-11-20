import math
import unittest

from scripts.oril_v2_cycle_metrics import compare


def records():
    return [{"cycle_id": str(i), "task_type": "validator", "difficulty": "small",
             "total_seconds": value}
            for i, value in enumerate((100, 90, 80, 70))]


class NonFiniteMetricsTests(unittest.TestCase):
    def test_nan_history_not_counted(self):
        data = records()
        data[0]["total_seconds"] = float("nan")
        result = compare(data, "3")["metrics"]["total_seconds"]
        self.assertEqual(result["n"], 2)
        self.assertEqual(result["verdict"], "판단불가")

    def test_positive_infinity_history_not_counted(self):
        data = records()
        data[1]["total_seconds"] = math.inf
        result = compare(data, "3")["metrics"]["total_seconds"]
        self.assertEqual(result["n"], 2)
        self.assertIsNone(result["previous_median"])

    def test_negative_infinity_history_not_counted(self):
        data = records()
        data[1]["total_seconds"] = -math.inf
        self.assertEqual(compare(data, "3")["metrics"]["total_seconds"]["verdict"], "판단불가")

    def test_nan_current_not_promoted(self):
        data = records()
        data[-1]["total_seconds"] = float("nan")
        self.assertEqual(compare(data, "3")["metrics"]["total_seconds"]["verdict"], "판단불가")

    def test_infinite_current_not_promoted(self):
        data = records()
        data[-1]["total_seconds"] = math.inf
        self.assertEqual(compare(data, "3")["metrics"]["total_seconds"]["verdict"], "판단불가")

    def test_finite_control_still_improves(self):
        result = compare(records(), "3")["metrics"]["total_seconds"]
        self.assertEqual(result["n"], 3)
        self.assertEqual(result["previous_median"], 90)
        self.assertEqual(result["verdict"], "향상")


if __name__ == "__main__":
    unittest.main()
