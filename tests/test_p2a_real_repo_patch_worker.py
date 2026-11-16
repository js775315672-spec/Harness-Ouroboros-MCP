"""Offline P2a adversarial gates; no model, Docker or repo write required."""
from pathlib import Path
import ast
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"scripts"))
import p2a_real_repo_patch_worker as s

SAMPLE = """def handoff(proposal,branch):
    if not isinstance(proposal,dict):
        raise ValueError('missing proposal')
    if not isinstance(branch,str) or not SAFE_BRANCH.fullmatch(branch):
        raise ValueError('unsafe branch')
    return {'mode':'handoff_only'}
"""

class TestP2aActualRepoSourcePatch(unittest.TestCase):
    def bad(self, raw):
        with self.assertRaises(ValueError):
            s.inspect_replacement(raw)

    def test_real_repo_source_anchor_exists(self):
        origin = (ROOT/s.TARGET).read_text()
        self.assertEqual(s.original_function(origin).name, "handoff")
        self.assertIn("SAFE_BRANCH", origin)

    def test_real_function_replacement_parses(self):
        self.assertEqual(s.inspect_replacement(SAMPLE), SAMPLE)

    def test_real_function_replacement_is_a_scope_limited_diff(self):
        old = (ROOT/s.TARGET).read_text()
        replacement = s.inspect_replacement(SAMPLE)
        new, diff = s.patch_original(old, replacement)
        self.assertNotEqual(old, new)
        self.assertIn("def handoff(", diff)
        self.assertIn("SAFE_BRANCH", new)
        self.assertEqual(
            [node.name for node in ast.parse(old).body
             if isinstance(node, ast.FunctionDef)],
            [node.name for node in ast.parse(new).body
             if isinstance(node, ast.FunctionDef)])

    def test_untrusted_import_is_rejected(self):
        self.bad("import os\n" + SAMPLE)

    def test_untrusted_shell_exec_is_rejected(self):
        self.bad("def handoff(proposal,branch):\n    return eval('123')\n")

    def test_untrusted_file_access_is_rejected(self):
        self.bad("def handoff(proposal,branch):\n    return open('/etc/passwd')\n")

    def test_dynamic_attribute_is_rejected(self):
        self.bad("def handoff(proposal,branch):\n    return proposal.__class__\n")

    def test_input_mutation_is_rejected(self):
        self.bad("def handoff(proposal,branch):\n    proposal['task']='merge'\n    return {}\n")

    def test_parent_proposal_rebind_is_rejected(self):
        self.bad("def handoff(proposal,branch):\n    proposal={}\n    return proposal\n")

    def test_global_function_rejected(self):
        self.bad("def handoff(proposal,branch):\n    return __import__('os')\n")

    def test_extra_top_level_code_rejected(self):
        self.bad(SAMPLE + "\nprint('side effect')\n")

    def test_wrong_function_signature_rejected(self):
        self.bad("def handoff(proposal,branch,extra):\n    return {}\n")

    def test_disallow_control_transport(self):
        self.bad(SAMPLE.replace("\n", "\r\n"))

    def test_allow_one_python_fence_without_source_repair(self):
        marker = chr(96)*3
        wrapped = marker+"python\n"+SAMPLE+marker
        self.assertEqual(s.inspect_replacement(wrapped), SAMPLE)

    def test_reject_nested_markdown_text(self):
        marker = chr(96)*3
        self.bad("Explanation\n"+marker+"python\n"+SAMPLE+marker)

    def test_target_patched_source_differs_from_static_original(self):
        old=(ROOT/s.TARGET).read_text()
        new,_=s.patch_original(old,SAMPLE)
        self.assertEqual(ast.parse(new).body[0].__class__,
                         ast.parse(old).body[0].__class__)

    def test_fixed_holdout_has_exact_ten_cases(self):
        file = (ROOT/"tests/heldout_p2a_agent_handoff.py").read_text()
        self.assertEqual(file.count("    def test_"), s.HOLDOUT_COUNT)
        self.assertIn('test_reject_newline_injected_in_task', file)

    def test_replay_forged_merge_authority_rejected(self):
        old = s.git_identity
        with patch.object(s,"git_identity",return_value=None):
            _,_,base=s.context(ROOT,"a"*40)
            record={**base,"model_calls":1,"raw_response":SAMPLE,
                    "response_sha256":s.digest(SAMPLE.encode()),
                    "outcome":"static_rejected",
                    "grade":None,"replacement_sha256":None,
                    "merge_authorized":True}
            with self.assertRaises(ValueError):
                s.replay(ROOT,"a"*40,record)

    def test_proposed_file_path_fixed(self):
        self.assertEqual(s.TARGET,"scripts/agent_handoff.py")
        self.assertNotIn(".github/workflows", s.SUPPORT)

    def test_source_prompt_includes_true_existing_code_not_holdout(self):
        original=(ROOT/s.TARGET).read_text()
        prompt=s.source_prompt(original)
        self.assertIn("def handoff(",prompt)
        self.assertIn("240 UTF-8 bytes",prompt)
        self.assertNotIn("test_reject_newline_injected_in_task",prompt)
        self.assertLess(len(prompt.encode()),5000)


if __name__ == "__main__":
    unittest.main()
