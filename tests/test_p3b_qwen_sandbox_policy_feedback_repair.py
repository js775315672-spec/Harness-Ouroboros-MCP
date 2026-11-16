"""P3b offline provenance checks; one fresh call not executed in these tests."""
from pathlib import Path
import ast
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import p3b_qwen_sandbox_policy_feedback_repair as s

class P3bFrozenFirstFailureTests(unittest.TestCase):
    def test_exact_first_model_raw_output_sha(self):
        data=s.file_bytes(ROOT,s.PREVIOUS)
        self.assertEqual(s.digest(data),s.PREVIOUS_SHA256)

    def test_first_generated_source_was_noop(self):
        old=(ROOT/s.TARGET).read_text()
        previous=s.inspect_replacement(s.file_bytes(ROOT,s.PREVIOUS).decode())
        current=s.original_function(old)
        orig=''.join(old.splitlines(keepends=True)[current.lineno-1:current.end_lineno])
        self.assertEqual(ast.dump(ast.parse(previous),include_attributes=False),
                         ast.dump(ast.parse(orig),include_attributes=False))

    def test_inference_prompt_has_real_failure_feedback(self):
        p=s.source_prompt((ROOT/s.TARGET).read_text(),ROOT)
        self.assertIn("AST-identical copy",p)
        self.assertIn("FIRST QWEN OUTPUT",p)
        self.assertIn("extern",p)
        self.assertIn("plain builtin dict",p)
        self.assertLess(len(p.encode()),5000)

    def test_original_hidden_oracle_not_leaked_into_prompt(self):
        p=s.source_prompt((ROOT/s.TARGET).read_text(),ROOT)
        self.assertNotIn("test_spoofed_comparison_cannot_accept_write_permission",p)
        self.assertNotIn("FrozenSandboxPolicySecurity",p)

    def test_all_frozen_old_and_new_test_counts_same(self):
        self.assertEqual(s.REGRESSION_TESTS,
                         {"test_agent_handoff.py":7,"test_sandbox_policy.py":6,
                          "test_agent_handoff_security_p2d.py":10})
        text=(ROOT/"tests/heldout_p3a_sandbox_policy.py").read_text()
        self.assertEqual(text.count("    def test_"),10)

    def test_scoped_patched_source_still_enforced(self):
        original=(ROOT/s.TARGET).read_text()
        fn='''def policy(proposal,branch,workflow_permissions=None):
    contract=handoff(proposal,branch)
    return {"github_token_permissions":{"contents":"read"}}
'''
        after,diff=s.patch_original(original,s.inspect_replacement(fn))
        self.assertNotEqual(after,original)
        self.assertTrue(diff.startswith("--- a/scripts/sandbox_policy.py"))
        self.assertIn("def main():",after)

    def test_noop_original_still_rejected_by_guard(self):
        original=(ROOT/s.TARGET).read_text()
        with self.assertRaises(ValueError):
            s.patch_original(original,s.inspect_replacement(
                s.file_bytes(ROOT,s.PREVIOUS).decode()))

    def test_context_contains_frozen_first_failure_and_no_authority(self):
        with patch.object(s,"git_identity",return_value=None):
            _,prompt,contract=s.context(ROOT,"a"*40)
        self.assertEqual(contract["prior_rejected_model_sha256"],
                         s.PREVIOUS_SHA256)
        self.assertFalse(contract["merge_authorized"])
        self.assertFalse(contract["model_remote_push_authorized"])
        self.assertIn(s.PREVIOUS,contract["trusted_inputs_sha256"])

    def test_unknown_function_call_rejected(self):
        with self.assertRaises(ValueError):
            s.inspect_replacement('''def policy(proposal,branch,workflow_permissions=None):
    return eval("unsafe")
''')

    def test_replay_forged_green_rejected(self):
        with patch.object(s,"git_identity",return_value=None):
            _,_,base=s.context(ROOT,"a"*40)
            raw=s.file_bytes(ROOT,s.PREVIOUS).decode()
            forged={**base,"model_calls":1,
                    "raw_response":raw,"response_sha256":s.digest(raw.encode()),
                    "merge_authorized":True,"outcome":"real_source_patch_passed"}
            with self.assertRaises(ValueError):
                s.replay(ROOT,"a"*40,forged)

if __name__=="__main__":
    unittest.main()
