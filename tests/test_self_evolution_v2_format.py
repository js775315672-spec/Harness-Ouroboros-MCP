"""P1b v2: test formatting-only variant without weakening frozen v1 AST gate."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import self_evolution_model_lane as s

SOURCE = """def choose_action(state):
    if not isinstance(state, dict):
        return 'BLOCK'
    if state.get('safety') is not True:
        return 'BLOCK'
    stage = state.get('stage')
    if stage == 'new':
        return 'GENERATE'
    if stage == 'coded':
        return 'VERIFY'
    if stage == 'tested' and state.get('tests_ok') is True:
        return 'ATTEST'
    if stage == 'attested':
        return 'REVIEW'
    return 'BLOCK'
"""


def fenced(source):
    mark = chr(96) * 3
    return mark + "python\n" + source.rstrip("\n") + "\n" + mark


class P1bTransportVariantTests(unittest.TestCase):
    def test_v1_strict_still_rejects_fences(self):
        with self.assertRaises(ValueError):
            s.inspect_function(fenced(SOURCE))

    def test_v2_accepted_exact_single_envelope(self):
        self.assertEqual(
            s.inspect_function(fenced(SOURCE), allow_fence=True), SOURCE)

    def test_v2_plain_code_accepted_unchanged(self):
        self.assertEqual(
            s.inspect_function(SOURCE, allow_fence=True), SOURCE)

    def test_refuses_explanation_outside_envelope(self):
        with self.assertRaises(ValueError):
            s.inspect_function("Example:\n" + fenced(SOURCE), allow_fence=True)

    def test_refuses_multiple_fences(self):
        with self.assertRaises(ValueError):
            s.inspect_function(fenced(SOURCE) + "\n" + fenced(SOURCE),
                               allow_fence=True)

    def test_refuses_mismatched_language(self):
        with self.assertRaises(ValueError):
            s.inspect_function(fenced(SOURCE).replace("python\n", "sh\n", 1),
                               allow_fence=True)

    def test_refuses_nested_markdown(self):
        with self.assertRaises(ValueError):
            s.inspect_function(fenced(SOURCE.replace(
                "    return 'BLOCK'\n",
                "    return 'BLOCK'\n    " + chr(96) * 3 + "\n", 1)),
                allow_fence=True)

    def test_unfence_does_not_execute_or_rewrite_source(self):
        rejected = SOURCE.replace(
            "    return 'BLOCK'\n", "    return open('/etc/passwd')\n", 1)
        with self.assertRaises(ValueError):
            s.inspect_function(fenced(rejected), allow_fence=True)

    def test_v2_prompt_is_separate_from_v1(self):
        root = Path(__file__).resolve().parents[1]
        config = s.load_config(root / "configs/self-evolution-8lanes.json")
        old = s.prompt(config, "01")
        new = s.prompt(config, "01", v2=True)
        self.assertNotEqual(old, new)
        self.assertIn("is True", new)
        self.assertIn("Never use truthiness", new)
        self.assertIn(s.TASK, new)

    def test_v2_report_has_distinct_variant_identity(self):
        root = Path(__file__).resolve().parents[1]
        config = root / "configs/self-evolution-8lanes.json"
        v1, _, _ = s.context(root, config, "01", "a"*40)
        v2, _, _ = s.context(root, config, "01", "a"*40, v2=True)
        self.assertNotIn("study_variant", v1)
        self.assertEqual(v2["study_variant"],
                         "p1b-v2-exact-fence-and-boolean-prompt")
        self.assertNotEqual(v1["prompt_sha256"], v2["prompt_sha256"])

    def test_v2_still_rejects_false_success_evidence(self):
        root = Path(__file__).resolve().parents[1]
        config = root / "configs/self-evolution-8lanes.json"
        fields, _, _ = s.context(root, config, "01", "a"*40, v2=True)
        model = fenced(SOURCE)
        record = {**fields, "model_calls": 1, "raw_response": model,
                  "response_sha256": s.sha(model.encode("utf-8")),
                  "candidate_sha256": s.sha(SOURCE.encode("utf-8")),
                  "outcome": "model_candidate_passed",
                  "evaluation": {"status": "model_candidate_passed"}}
        record["merge_authorized"] = True
        with self.assertRaises(ValueError):
            s.verify(root, config, "a"*40, record, v2=True)


if __name__ == "__main__":
    unittest.main()
