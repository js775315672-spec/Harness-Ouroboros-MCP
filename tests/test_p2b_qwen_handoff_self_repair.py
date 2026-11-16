"""P2b adversarial self-repair feedback contract (offline, zero model calls)."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import p2b_qwen_handoff_self_repair as s


class TestP2bFrozenPriorModelEvidence(unittest.TestCase):
    def test_exact_previous_real_model_response_digest(self):
        raw=s.file_bytes(ROOT,s.PREVIOUS)
        self.assertEqual(s.digest(raw),s.PREVIOUS_SHA256)
        self.assertEqual(len(raw),1351)

    def test_first_generated_function_is_syntactically_valid(self):
        raw=s.file_bytes(ROOT,s.PREVIOUS).decode()
        source=s.inspect_replacement(raw)
        self.assertIn("def handoff(",source)
        self.assertIn("len(task.encode(",source)

    def test_first_failed_function_did_not_check_boundary_spaces(self):
        first=s.inspect_replacement(s.file_bytes(ROOT,s.PREVIOUS).decode())
        self.assertNotIn("task != task.strip()",first)
        self.assertNotIn("task.strip() != task",first)

    def test_new_prompt_cites_prior_replay_not_hidden_values(self):
        old=(ROOT/s.TARGET).read_text()
        prompt=s.source_prompt(old,ROOT)
        self.assertIn("FIRST MODEL RESPONSE",prompt)
        self.assertIn("failed 1/10 holdout methods",prompt)
        self.assertIn("leading OR trailing whitespace",prompt)
        self.assertNotIn("test_reject_boundary_whitespace",prompt)
        self.assertLess(len(prompt.encode()),5000)

    def test_original_target_is_exact_same_frozen_source(self):
        payload=s.file_bytes(ROOT,s.TARGET)
        self.assertEqual(s.digest(payload),s.BASE_SOURCE_SHA256)

    def test_feedback_cannot_modify_holdout_suite(self):
        self.assertNotIn(s.PREVIOUS,s.SUPPORT)
        self.assertEqual(s.HOLDOUT_COUNT,10)
        self.assertEqual(s.REGRESSION_TESTS["test_agent_handoff.py"],7)
        self.assertEqual(s.REGRESSION_TESTS["test_sandbox_policy.py"],6)

    def test_static_gate_still_rejects_imports(self):
        with self.assertRaises(ValueError):
            s.inspect_replacement("import os\n"+s.inspect_replacement(
                s.file_bytes(ROOT,s.PREVIOUS).decode()))

    def test_scope_guard_preserves_other_repo_functions(self):
        old=(ROOT/s.TARGET).read_text()
        first=s.inspect_replacement(s.file_bytes(ROOT,s.PREVIOUS).decode())
        new,diff=s.patch_original(old,first)
        self.assertIn("def main():",new)
        self.assertIn("SAFE_BRANCH",new)
        self.assertIn("def handoff(",diff)

    def test_context_contains_checked_prior_digest(self):
        with patch.object(s,"git_identity",return_value=None):
            _,prompt,base=s.context(ROOT,"a"*40)
        self.assertEqual(base["prior_failed_model_sha256"],s.PREVIOUS_SHA256)
        self.assertEqual(base["prior_failed_source_sha256"],s.BASE_SOURCE_SHA256)
        self.assertEqual(base["variant"],s.VARIANT)
        self.assertFalse(base["merge_authorized"])

    def test_replay_rejects_fake_approval(self):
        with patch.object(s,"git_identity",return_value=None):
            _,_,base=s.context(ROOT,"a"*40)
            forged={**base,"model_calls":1,
                    "raw_response":s.file_bytes(ROOT,s.PREVIOUS).decode(),
                    "response_sha256":s.PREVIOUS_SHA256,
                    "outcome":"static_rejected",
                    "grade":None,"replacement_sha256":None,
                    "merge_authorized":True}
            with self.assertRaises(ValueError):
                s.replay(ROOT,"a"*40,forged)


if __name__=="__main__":
    unittest.main()
