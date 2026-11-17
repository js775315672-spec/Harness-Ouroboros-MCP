"""Offline unit tests for W04 model execution scaffold; no GGUF or network."""
import hashlib
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from p3l_w04_model_trial import git_blob, task_prompt, render, inspect_candidate

class W04ModelTrialTests(unittest.TestCase):
    def test_baseline_git_blob_matches_checked_out_source(self):
        data = (ROOT / "scripts/model_stagnation_gate.py").read_bytes()
        self.assertEqual(git_blob(data), "39e0a1e59eaf2bc04f83bee30fa00041d4d06ba0")

    def test_prompt_anchors_real_existing_code_and_stays_bounded(self):
        data = (ROOT / "scripts/model_stagnation_gate.py").read_text(encoding="utf-8")
        prompt = task_prompt(data)
        self.assertIn("def evaluate(", prompt)
        self.assertIn("normalized_ast_sha256", prompt)
        self.assertLessEqual(len(prompt.encode("utf-8")), 4900)
        self.assertIn("<|im_start|>user", render(prompt))

    def test_candidate_is_parsed_but_not_executed(self):
        code = "def normalized_ast_sha256(source):\n    raise RuntimeError('MUST NOT BE RUN')\n"
        self.assertEqual(inspect_candidate(code),
                         "untrusted_function_candidate_for_review")
        self.assertEqual(inspect_candidate("print('not a function')"),
                         "model_response_rejected")
        self.assertEqual(inspect_candidate("def other(x):\n    return x\n"),
                         "model_response_rejected")

    def test_malformed_or_oversized_output_is_rejected(self):
        self.assertEqual(inspect_candidate("def normalized_ast_sha256("),
                         "model_response_rejected")
        self.assertEqual(inspect_candidate("a" * 6001), "model_response_rejected")
        self.assertEqual(inspect_candidate(""), "model_response_rejected")

if __name__ == "__main__":
    unittest.main()
