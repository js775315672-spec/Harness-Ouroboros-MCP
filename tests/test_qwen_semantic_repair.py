"""Offline safety, feedback and provenance tests for non-templated Qwen repair."""
import hashlib
import pathlib
import sys
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from qwen_source_guard import ORIGINAL, TARGET
from qwen_semantic_source_guard import inspect_semantic_line
from qwen_semantic_repair_loop import build_prompt, normalize_candidate, run_loop
from qwen_semantic_disposable_compare import compare_line

VALID = (
    ORIGINAL[:-1] +
    ' or not isinstance(proposal.get("cycle"), int) or '
    'isinstance(proposal.get("cycle"), bool) or proposal["cycle"] <= 0:'
)
INCOMPLETE = (
    ORIGINAL[:-1] +
    ' or not isinstance(proposal.get("cycle"), int) or proposal["cycle"] <= 0:'
)


def evidence(line, source, status):
    return {
        "status": status,
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "candidate_line_sha256": hashlib.sha256(line.encode()).hexdigest(),
        "source_checkout_modified": False, "merge_authorized": False,
        "baseline_regression": {"passed": True},
        "baseline_negative_control": {"passed": False},
        "candidate_regression": {"passed": True},
        "candidate_negative_control":
            {"passed": status == "isolated_source_repair_passed"},
    }


class SemanticRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / TARGET).read_text(encoding="utf-8")

    def test_non_reference_ast_candidate_accepted_for_disposable_testing(self):
        result = inspect_semantic_line(VALID, self.source)
        self.assertEqual(result["status"], "ast_scoped_candidate")
        self.assertFalse(result["merge_authorized"])

    def test_incomplete_guard_is_ast_valid_but_needs_docker(self):
        self.assertEqual(
            inspect_semantic_line(INCOMPLETE, self.source)["status"],
            "ast_scoped_candidate")

    def test_literal_membership_is_staticaly_safe_but_not_preapproved(self):
        candidate = (
            ORIGINAL[:-1] +
            " or (not (proposal.get('cycle') in [None, False, 0, -1])):"
        )
        self.assertEqual(
            inspect_semantic_line(candidate, self.source)["status"],
            "ast_scoped_candidate")
        for unsafe in (
            ORIGINAL[:-1] + ' or proposal.get("cycle") in [__import__("os")]:',
            ORIGINAL[:-1] + ' or proposal.get("cycle") in [x for x in range(5)]:',
        ):
            with self.assertRaises(ValueError):
                inspect_semantic_line(unsafe, self.source)

    def test_disallowed_side_effects_are_blocked(self):
        unsafe = [
            ORIGINAL[:-1] + ' or __import__("os").system("id"):',
            ORIGINAL[:-1] + ' or proposal.__dict__:',
            ORIGINAL[:-1] + ' or (x := True):',
            ORIGINAL[:-1] + ' or (lambda: 1)():',
            ORIGINAL[:-1] + ' or proposal["secret"]:',
        ]
        for line in unsafe:
            with self.subTest(line=line):
                with self.assertRaises(ValueError):
                    inspect_semantic_line(line, self.source)

    def test_original_checks_cannot_be_removed_or_rewritten(self):
        bad = '    if proposal.get("decision") != "propose" or proposal["cycle"] <= 0:'
        with self.assertRaises(ValueError):
            inspect_semantic_line(bad, self.source)

    def test_short_predicate_fragment_is_scoped_by_trusted_guard(self):
        fragment = (
            'not isinstance(proposal.get("cycle"), int) or '
            'isinstance(proposal.get("cycle"), bool) or '
            'proposal["cycle"] <= 0'
        )
        line, inspection = normalize_candidate(fragment, self.source)
        self.assertEqual(inspection["status"], "ast_scoped_candidate")
        self.assertTrue(line.startswith(ORIGINAL[:-1] + " or ("))
        self.assertTrue(line.endswith("):"))
        with self.assertRaises(ValueError):
            normalize_candidate('__import__("os").system("id")', self.source)

    def test_multiline_response_cannot_run(self):
        with self.assertRaises(ValueError):
            inspect_semantic_line(VALID + "\n    import os", self.source)

    def test_prompt_contains_requirements_without_final_solution(self):
        prompt = build_prompt("candidate_negative_failed")
        self.assertIn("positive integers", prompt)
        self.assertNotIn('type(proposal.get("cycle")) is not int', prompt)
        self.assertNotIn('isinstance(proposal.get("cycle"), bool)', prompt)
        with self.assertRaises(ValueError):
            build_prompt("model says ignore safety")

    def test_docker_failure_feeds_bounded_retry_and_then_success(self):
        answers = iter(["    if broken:", INCOMPLETE, VALID])
        prompts = []
        checked = []
        def generate(prompt):
            prompts.append(prompt)
            return next(answers)
        def evaluate(line):
            checked.append(line)
            return evidence(line, self.source,
                            "isolated_source_repair_passed" if line == VALID
                            else "candidate_negative_failed")
        result = run_loop(self.source, generate, evaluate)
        self.assertEqual(result["status"], "isolated_source_repair_passed")
        self.assertEqual(result["model_calls"], 3)
        self.assertEqual(result["docker_comparisons"], 2)
        self.assertEqual([row["status"] for row in result["attempts"]],
                         ["ast_scope_rejected", "candidate_negative_failed",
                          "isolated_source_repair_passed"])
        self.assertIn("Disposable tests rejected", prompts[2])
        self.assertEqual(checked, [INCOMPLETE, VALID])
        self.assertFalse(result["merge_authorized"])
        self.assertEqual(result["candidate"]["candidate_line"], VALID)

    def test_duplicate_repair_candidate_stops_without_repeated_docker(self):
        calls = []
        def evaluate(line):
            calls.append(line)
            return evidence(line, self.source, "candidate_regression_failed")
        result = run_loop(self.source, lambda prompt: INCOMPLETE, evaluate)
        self.assertEqual(result["status"], "stalled_duplicate_candidate")
        self.assertEqual(result["model_calls"], 2)
        self.assertEqual(result["docker_comparisons"], 1)
        self.assertEqual(calls, [INCOMPLETE])
        self.assertIsNone(result["candidate"])
        self.assertFalse(result["merge_authorized"])

    def test_exhausted_retry_never_claims_success(self):
        result = run_loop(self.source, lambda prompt: "invalid code",
                          lambda line: self.fail("docker should not run"))
        self.assertEqual(result["status"], "ast_scope_rejected")
        self.assertEqual(result["model_calls"], 3)
        self.assertEqual(result["docker_comparisons"], 0)
        self.assertIsNone(result["candidate"])

    def test_baseline_or_provenance_failure_cannot_be_repaired_away(self):
        result = run_loop(self.source, lambda prompt: VALID,
                          lambda line: evidence(line, self.source,
                                                "negative_control_invalid"))
        self.assertEqual(result["model_calls"], 1)
        self.assertIsNone(result["candidate"])
        with self.assertRaises(ValueError):
            run_loop(self.source, lambda prompt: VALID,
                     lambda line: dict(evidence(
                         line, self.source, "isolated_source_repair_passed"),
                         merge_authorized=True))

    def test_disposable_comparison_accepts_only_real_candidate_tests(self):
        seen = []
        def fake_test(workspace, pattern):
            stage = "candidate" if "candidate" in str(workspace) else "baseline"
            seen.append((stage, pattern))
            if stage == "candidate":
                self.assertIn(VALID, (pathlib.Path(workspace) / TARGET).read_text())
            if pattern == "test_feedback_controller.py":
                return {"passed": True, "tests_run": 8, "exit_code": 0}
            return {"passed": stage == "candidate", "tests_run": 3,
                    "exit_code": 0 if stage == "candidate" else 1}
        before = (ROOT / TARGET).read_bytes()
        with patch("qwen_semantic_disposable_compare._test",
                   side_effect=fake_test):
            result = compare_line(ROOT, VALID)
        self.assertEqual(result["status"], "isolated_source_repair_passed")
        self.assertEqual(len(seen), 4)
        self.assertFalse(result["source_checkout_modified"])
        self.assertEqual(before, (ROOT / TARGET).read_bytes())

    def test_disposable_comparison_cannot_pass_invalid_baseline(self):
        def fake_test(workspace, pattern):
            return {"passed": True, "tests_run":
                    8 if pattern == "test_feedback_controller.py" else 3,
                    "exit_code": 0}
        with patch("qwen_semantic_disposable_compare._test",
                   side_effect=fake_test):
            result = compare_line(ROOT, VALID)
        self.assertEqual(result["status"], "negative_control_invalid")
        self.assertFalse(result["merge_authorized"])


if __name__ == "__main__":
    unittest.main()
