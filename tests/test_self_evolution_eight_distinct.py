"""Offline attack tests for P1d. No model or Docker is loaded in these tests."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"scripts"))
import self_evolution_eight_distinct as s


class P1dTests(unittest.TestCase):
    def reject(self, raw):
        with self.assertRaises(ValueError):
            s.inspect_source(raw)

    def test_task_registry_has_eight_different_specs(self):
        self.assertEqual(tuple(s.TASKS),tuple(f"{n:02d}" for n in range(1,9)))
        self.assertEqual(len(set(s.TASKS.values())),8)

    def test_eight_unique_prompts_and_contracts(self):
        cfg=s.load_config(ROOT/"configs/self-evolution-8lanes.json")
        prompts=[s.task_prompt(cfg,k) for k in s.TASKS]
        self.assertEqual(len(set(prompts)),8)
        for task, prompt in zip(s.TASKS,prompts):
            self.assertIn(s.TASKS[task],prompt)
            self.assertIn("def",prompt)

    def test_simple_valid_single_function(self):
        src="def solve(data):\n    return None\n"
        self.assertEqual(s.inspect_source(src),src)

    def test_exact_python_fence_allowed_without_rewriting(self):
        marker=chr(96)*3
        src="def solve(data):\n    return None\n"
        self.assertEqual(s.inspect_source(marker+"python\n"+src+marker),src)

    def test_unknown_fence_rejected(self):
        self.reject(chr(96)*3+"bash\ndef solve(data):\n    return None\n"+chr(96)*3)

    def test_two_functions_rejected(self):
        self.reject("def solve(data):\n    return None\n\ndef other():\n    return 4\n")

    def test_import_rejected(self):
        self.reject("def solve(data):\n    import os\n    return None\n")

    def test_global_rejected(self):
        self.reject("def solve(data):\n    global secret\n    return 4\n")

    def test_dynamic_eval_rejected(self):
        self.reject("def solve(data):\n    return eval('3')\n")

    def test_file_access_rejected(self):
        self.reject("def solve(data):\n    return open('secret')\n")

    def test_attribute_dunder_rejected(self):
        self.reject("def solve(data):\n    return data.__class__\n")

    def test_attribute_assignment_rejected(self):
        self.reject("def solve(data):\n    data.x = 1\n    return None\n")

    def test_input_rebinding_rejected(self):
        self.reject("def solve(data):\n    data = []\n    return data\n")

    def test_wrong_signature_rejected(self):
        self.reject("def solve(data, second):\n    return None\n")

    def test_physical_control_byte_rejected(self):
        self.reject("def solve(data):\r\n    return None\r\n")

    def test_unknown_global_rejected(self):
        self.reject("def solve(data):\n    return untrusted_global\n")

    def test_replay_rejects_false_commit(self):
        fields,_,_ = s.context(ROOT,ROOT/"configs/self-evolution-8lanes.json",
                               "01","a"*40)
        r = {**fields, "source_sha":"f"*40,
             "model_calls":1,"raw_response":"def solve(data):\n    return None\n"}
        with self.assertRaises(ValueError):
            s.replay(ROOT,ROOT/"configs/self-evolution-8lanes.json","a"*40,r)

    def test_replay_rejects_fake_model_response_hash(self):
        fields,_,_ = s.context(ROOT,ROOT/"configs/self-evolution-8lanes.json",
                               "01","a"*40)
        r = {**fields,"model_calls":1,"raw_response":"def solve(data):\n    return None\n",
             "response_sha256":"f"*64}
        with self.assertRaises(ValueError):
            s.replay(ROOT,ROOT/"configs/self-evolution-8lanes.json","a"*40,r)

    def test_frozen_holdout_cannot_be_missing(self):
        raw,digest=s.heldout(ROOT)
        self.assertGreater(len(raw),1000)
        self.assertEqual(digest,s.sha(raw))

    def test_no_external_model_calls_in_preflight(self):
        cfg=s.load_config(ROOT/"configs/self-evolution-8lanes.json")
        self.assertEqual(len(s.build_manifests(cfg,"a"*40)),8)

if __name__=="__main__":
    unittest.main()
