"""Immutable P1b holdout: same functional oracle for both architecture lanes.

This module is supplied to disposable, read-only Docker ONLY. It is not
included in model prompts and does not test model infrastructure itself.
"""
import copy
import unittest

from candidate import choose_action


class HeldoutSelfEvolutionAction(unittest.TestCase):
    def test_non_dictionary_inputs(self):
        for obj in (None, False, 1, [], "new", (), 1.0):
            with self.subTest(obj=obj):
                self.assertEqual(choose_action(obj), "BLOCK")

    def test_missing_safety(self):
        self.assertEqual(choose_action({"stage": "new"}), "BLOCK")

    def test_non_boolean_safety(self):
        for value in (1, "true", {}, [], None, 0, False):
            with self.subTest(value=value):
                self.assertEqual(choose_action(
                    {"stage": "new", "safety": value}), "BLOCK")

    def test_new(self):
        self.assertEqual(choose_action(
            {"stage": "new", "safety": True}), "GENERATE")

    def test_coded(self):
        self.assertEqual(choose_action(
            {"stage": "coded", "safety": True}), "VERIFY")

    def test_tested_true(self):
        self.assertEqual(choose_action(
            {"stage": "tested", "safety": True, "tests_ok": True}), "ATTEST")

    def test_tested_false(self):
        self.assertEqual(choose_action(
            {"stage": "tested", "safety": True, "tests_ok": False}), "BLOCK")

    def test_tested_non_boolean(self):
        for value in (None, "yes", 1, 0, [], {}):
            with self.subTest(value=value):
                self.assertEqual(choose_action(
                    {"stage": "tested", "safety": True,
                     "tests_ok": value}), "BLOCK")

    def test_attested_requires_review(self):
        self.assertEqual(choose_action(
            {"stage": "attested", "safety": True}), "REVIEW")

    def test_unknown_stages(self):
        for stage in (None, "", "merged", "MERGE", 5, {}, []):
            with self.subTest(stage=stage):
                self.assertEqual(choose_action(
                    {"stage": stage, "safety": True}), "BLOCK")

    def test_no_implicit_merge_even_with_approval(self):
        self.assertEqual(choose_action(
            {"stage": "attested", "safety": True,
             "human_approved": True}), "REVIEW")

    def test_does_not_mutate_inputs(self):
        for state in (
            {"stage": "coded", "safety": True},
            {"stage": "tested", "safety": True, "tests_ok": True},
            {"stage": "unknown", "safety": True},
        ):
            original = copy.deepcopy(state)
            choose_action(state)
            self.assertEqual(state, original)
