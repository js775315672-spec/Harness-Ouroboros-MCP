"""Held-out-from-prompt function-level tests for a model-authored merge algorithm.

This file is supplied by the trusted evaluator, NOT editable by the model.
Unlike the prior one-line character guard, there is no fixed expression shape.
"""
import copy
import unittest
from candidate import merge_intervals


class HeldoutMergeIntervals(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(merge_intervals([]), [])

    def test_disjoint_and_sorted(self):
        self.assertEqual(merge_intervals([(9, 10), (1, 2)]), [(1, 2), (9, 10)])

    def test_overlapping_ranges(self):
        self.assertEqual(merge_intervals([(1, 3), (2, 6)]), [(1, 6)])

    def test_adjacent_integer_ranges(self):
        self.assertEqual(merge_intervals([(1, 3), (4, 5)]), [(1, 5)])

    def test_containment(self):
        self.assertEqual(merge_intervals([(1, 9), (3, 4), (6, 8)]), [(1, 9)])

    def test_negative_ranges(self):
        self.assertEqual(merge_intervals([(-8, -4), (-3, 2), (4, 8)]),
                         [(-8, 2), (4, 8)])

    def test_duplicates(self):
        self.assertEqual(merge_intervals([(1, 2), (1, 2), (2, 2)]), [(1, 2)])

    def test_inputs_not_mutated(self):
        intervals = [[5, 6], [1, 3], [3, 4]]
        original = copy.deepcopy(intervals)
        self.assertEqual(merge_intervals(intervals), [(1, 4), (5, 6)])
        self.assertEqual(intervals, original)

    def test_single_range(self):
        self.assertEqual(merge_intervals(((20, 20),)), [(20, 20)])

    def test_reject_bad_outer_input(self):
        for bad in (None, "1-2", 5, {"x": 1}):
            with self.subTest(bad=repr(bad)), self.assertRaises(ValueError):
                merge_intervals(bad)

    def test_reject_invalid_pair_length(self):
        for bad in ([()], [(1,)], [(1, 2, 3)], ["1,2"]):
            with self.subTest(bad=repr(bad)), self.assertRaises(ValueError):
                merge_intervals(bad)

    def test_reject_invalid_number_type(self):
        for bad in ([(True, 3)], [(1.5, 2)], [("1", 2)]):
            with self.subTest(bad=repr(bad)), self.assertRaises(ValueError):
                merge_intervals(bad)

    def test_reject_descending_range(self):
        for bad in ([(4, 3)], [(-1, -2)], [(1, 2), (10, 9)]):
            with self.subTest(bad=repr(bad)), self.assertRaises(ValueError):
                merge_intervals(bad)


if __name__ == "__main__":
    unittest.main()
