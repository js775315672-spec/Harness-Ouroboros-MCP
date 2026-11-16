"""P2c offline provenance tests: third model sees second failure, never test source."""
from pathlib import Path
import ast
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import p2c_qwen_third_source_repair as s


class ThirdModelFeedbackTests(unittest.TestCase):
    def test_exact_second_model_response_frozen(self):
        raw=s.file_bytes(ROOT,s.PREVIOUS)
        self.assertEqual(len(raw),1342)
        self.assertEqual(s.digest(raw),s.PREVIOUS_SHA256)

    def test_second_model_was_overrestrictive_about_internal_spaces(self):
        code=s.inspect_replacement(s.file_bytes(ROOT,s.PREVIOUS).decode())
        self.assertIn("c in ' \\t'",code)
        self.assertNotIn("task != task.strip()",code)

    def test_explicit_two_types_of_space_feedback(self):
        source=(ROOT/s.TARGET).read_text()
        prompt=s.source_prompt(source,ROOT)
        self.assertIn("VALID tasks including interior spaces",prompt)
        self.assertIn("INVALID tasks beginning or ending",prompt)
        self.assertIn("Attempt #2 wrongly",prompt)
        self.assertIn("Attempt #1 kept all 13 old",prompt)
        self.assertIn("SECOND QWEN MODEL OUTPUT",prompt)
        self.assertLess(len(prompt.encode()),5000)

    def test_prompt_does_not_leak_frozen_hidden_test_implementation(self):
        p=s.source_prompt((ROOT/s.TARGET).read_text(),ROOT)
        self.assertNotIn("test_no_proposal_mutation_and_fail_closed_input",p)
        self.assertNotIn("HiddenRealRepoHandoffSecurity",p)

    def test_fixed_prior_source_and_target_hash(self):
        self.assertEqual(s.digest(s.file_bytes(ROOT,s.TARGET)),
                         s.BASE_SOURCE_SHA256)
        self.assertNotEqual(s.PREVIOUS_SHA256,s.BASE_SOURCE_SHA256)

    def test_second_model_code_static_guard_only(self):
        raw=s.file_bytes(ROOT,s.PREVIOUS).decode()
        clean=s.inspect_replacement(raw)
        fn=ast.parse(clean).body[0]
        self.assertEqual(fn.name,"handoff")
        self.assertEqual([a.arg for a in fn.args.args],["proposal","branch"])

    def test_prev_source_reconstructs_scoped_real_repo_diff(self):
        old=(ROOT/s.TARGET).read_text()
        previous=s.inspect_replacement(s.file_bytes(ROOT,s.PREVIOUS).decode())
        new,diff=s.patch_original(old,previous)
        self.assertIn("def main():",new)
        self.assertTrue(diff.startswith("--- a/scripts/agent_handoff.py"))

    def test_no_harness_or_legacy_test_edits(self):
        self.assertEqual(s.HOLDOUT_COUNT,10)
        self.assertEqual(s.REGRESSION_TESTS,
                         {"test_agent_handoff.py":7,"test_sandbox_policy.py":6})
        self.assertEqual(s.TARGET,"scripts/agent_handoff.py")

    def test_second_original_is_context_bound_and_no_approval(self):
        with patch.object(s,"git_identity",return_value=None):
            _,prompt,contract=s.context(ROOT,"a"*40)
        self.assertEqual(contract["prior_failed_model_sha256"],
                         s.PREVIOUS_SHA256)
        self.assertFalse(contract["merge_authorized"])
        self.assertEqual(contract["ci_attested_model_source_commits"],0)

    def test_model_source_read_is_not_executable_on_host(self):
        raw=s.file_bytes(ROOT,s.PREVIOUS).decode()
        with self.assertRaises(ValueError):
            s.inspect_replacement(raw+"\nimport os\n")


if __name__=="__main__":
    unittest.main()
