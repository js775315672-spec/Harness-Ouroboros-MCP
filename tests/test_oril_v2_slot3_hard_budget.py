"""Regression: callers cannot override the student example safety ceilings."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_teacher_distillation_pack import compile_examples
from test_oril_v2_teacher_distillation_pack import case


class HardBudgetTests(unittest.TestCase):
    def test_reject_more_than_sixteen(self):
        with self.assertRaisesRegex(ValueError, "invalid selection budgets"):
            compile_examples([case(1)], max_cases=17)

    def test_reject_more_than_six_thousand_chars(self):
        with self.assertRaisesRegex(ValueError, "invalid selection budgets"):
            compile_examples([case(1)], max_total_chars=6001)

    def test_reject_boolean_budget(self):
        with self.assertRaisesRegex(ValueError, "invalid selection budgets"):
            compile_examples([case(1)], max_cases=True)

    def test_reject_zero_budget(self):
        with self.assertRaisesRegex(ValueError, "invalid selection budgets"):
            compile_examples([case(1)], max_total_chars=0)


if __name__ == "__main__":
    unittest.main()
