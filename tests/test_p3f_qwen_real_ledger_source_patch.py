"""P3f adversarial real ledger source patch contract, no model calls."""
from pathlib import Path
import ast
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import p3f_qwen_real_ledger_source_patch as s

SAMPLE='''def validate(records):
    if type(records) is not list:
        raise ValueError("records required")
    return len(records)
'''

class FreshLedgerPatchTests(unittest.TestCase):
    def reject(self,src):
        with self.assertRaises(ValueError):s.inspect_replacement(src)

    def test_true_existing_ledger_function(self):
        self.assertEqual(s.TARGET,"scripts/development_ledger.py")
        self.assertEqual(s.original_function((ROOT/s.TARGET).read_text()).name,
                         "validate")

    def test_exact_single_parameter(self):
        self.assertEqual(s.inspect_replacement(SAMPLE),SAMPLE)

    def test_extra_parameter_rejected(self):
        self.reject(SAMPLE.replace("validate(records)","validate(records,unsafe)"))

    def test_default_argument_rejected(self):
        self.reject(SAMPLE.replace("validate(records)","validate(records=None)"))

    def test_source_import_rejected(self):
        self.reject("import os\n"+SAMPLE)

    def test_runtime_exec_rejected(self):
        self.reject('''def validate(records):
    return eval("42")
''')

    def test_input_mutation_rejected(self):
        self.reject('''def validate(records):
    records[0]="write"
    return 0
''')

    def test_global_input_rebinding_rejected(self):
        self.reject('''def validate(records):
    records=[]
    return 0
''')

    def test_second_function_rejected(self):
        self.reject(SAMPLE+'\ndef unsafe():\n    return 1\n')

    def test_legitimate_record_loop_variable_is_not_protected_input(self):
        source = '''def validate(records):
    total = 0
    for record in records:
        total += 1
    return total
'''
        self.assertEqual(s.inspect_replacement(source),source)

    def test_exact_records_argument_rebinding_still_rejected(self):
        source = '''def validate(records):
    records = []
    return 0
'''
        self.reject(source)

    def test_target_scoped_patch_preserves_other_functions(self):
        old=(ROOT/s.TARGET).read_text()
        after,diff=s.patch_original(old,SAMPLE)
        self.assertNotEqual(after,old)
        self.assertIn("def main():",after)
        self.assertIn("def validate(",diff)
        self.assertIn('CI=re.compile(',after)

    def test_prompt_contains_real_source_not_hidden_tests(self):
        p=s.source_prompt((ROOT/s.TARGET).read_text())
        self.assertIn("def validate(records)",p)
        self.assertIn("at most 12 entries",p)
        self.assertIn("256 UTF-8 BYTES",p)
        self.assertNotIn("test_reject_newline_in_fix_entry",p)
        self.assertLess(len(p.encode()),5000)

    def test_fixed_old_and_new_test_totals(self):
        self.assertEqual(s.REGRESSION_TESTS,
                         {"test_development_ledger.py":8,
                          "test_ci_attestation.py":7})
        oracle=(ROOT/"tests/heldout_p3f_development_ledger.py").read_text()
        self.assertEqual(oracle.count("    def test_"),10)

    def test_context_binds_hidden_suite_sha(self):
        with patch.object(s,"git_identity",return_value=None):
            _,_,receipt=s.context(ROOT,"a"*40)
        self.assertIn("tests/heldout_p3f_development_ledger.py",
                      receipt["trusted_inputs_sha256"])
        self.assertEqual(receipt["model"],s.MODEL)
        self.assertIs(receipt["merge_authorized"],False)

    def test_invalid_git_repo_source_change_is_rejected(self):
        with patch.object(s,"git_identity",side_effect=ValueError("SHA mismatch")):
            with self.assertRaises(ValueError):
                s.context(ROOT,"b"*40)

    def test_forged_merge_permission_replay_blocked(self):
        with patch.object(s,"git_identity",return_value=None):
            _,_,base=s.context(ROOT,"a"*40)
            forged={**base,"merge_authorized":True,
                    "model_calls":1,"raw_response":SAMPLE,
                    "response_sha256":s.digest(SAMPLE.encode())}
            with self.assertRaises(ValueError):
                s.replay(ROOT,"a"*40,forged)

    def test_static_gate_does_not_execute_python(self):
        self.reject('''def validate(records):
    import subprocess
    return subprocess.run(["echo","unsafe"])
''')

if __name__=="__main__":
    unittest.main()
