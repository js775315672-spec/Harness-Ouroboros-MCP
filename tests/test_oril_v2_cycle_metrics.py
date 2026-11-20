import unittest
from scripts.oril_v2_cycle_metrics import compare


class CycleMetricsTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            {"cycle_id": str(i), "task_type": "validator", "difficulty": "small",
             "total_seconds": x, "accepted_improvements": 1}
            for i, x in enumerate((100, 90, 80, 70))
        ]

    def test_improved_speed(self):
        result = compare(self.records, "3")
        self.assertEqual(result["metrics"]["total_seconds"]["verdict"], "향상")
        self.assertEqual(result["metrics"]["total_seconds"]["previous_median"], 90)

    def test_missing_not_zero(self):
        self.records[-1].pop("total_seconds")
        self.assertEqual(compare(self.records, "3")["metrics"]["total_seconds"]["verdict"], "판단불가")

    def test_incomparable_difficulty_excluded(self):
        self.records[1]["difficulty"] = "large"
        self.assertEqual(compare(self.records, "3")["metrics"]["total_seconds"]["verdict"], "판단불가")

    def test_duplicate_rejected(self):
        self.records[-1]["cycle_id"] = "0"
        with self.assertRaises(ValueError):
            compare(self.records, "0")

    def test_zero_baseline_not_fabricated(self):
        for r in self.records:
            r["retries"] = 0
        self.assertEqual(compare(self.records, "3")["metrics"]["retries"]["verdict"], "유지")

    def test_future_cycles_not_leaked(self):
        self.records.append({"cycle_id": "4", "task_type": "validator",
                             "difficulty": "small", "total_seconds": 1})
        self.assertEqual(compare(self.records, "3")["metrics"]["total_seconds"]["previous_median"], 90)


if __name__ == "__main__":
    unittest.main()
