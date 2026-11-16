"""Offline AST and integrity tests for P1b; no LLM or Docker used here."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import self_evolution_model_lane as s

VALID = """def choose_action(state):
    if not isinstance(state, dict):
        return 'BLOCK'
    if state.get('safety') is not True:
        return 'BLOCK'
    if state.get('stage') == 'new':
        return 'GENERATE'
    if state.get('stage') == 'coded':
        return 'VERIFY'
    if state.get('stage') == 'tested' and state.get('tests_ok') is True:
        return 'ATTEST'
    if state.get('stage') == 'attested':
        return 'REVIEW'
    return 'BLOCK'
"""
COMMIT = "a" * 40


class TestP1bStaticGate(unittest.TestCase):
    def reject(self, source):
        with self.assertRaises(ValueError):
            s.inspect_function(source)

    def test_exact_single_function_allowed(self):
        self.assertEqual(s.inspect_function(VALID), VALID)

    def test_import_blocked(self):
        self.reject("import os\n" + VALID)

    def test_additional_top_level_function_blocked(self):
        self.reject(VALID + "\ndef bad():\n    return 3\n")

    def test_shell_or_file_calls_blocked(self):
        self.reject("def choose_action(state):\n    open('/tmp/a','w')\n    return 'BLOCK'\n")

    def test_eval_blocked(self):
        self.reject("def choose_action(state):\n    return eval('1+1')\n")

    def test_dunder_attributes_blocked(self):
        self.reject("def choose_action(state):\n    return state.__class__\n")

    def test_mutation_blocked(self):
        self.reject("def choose_action(state):\n    state['stage']='new'\n    return 'BLOCK'\n")

    def test_recursion_blocked(self):
        self.reject("def choose_action(state):\n    return choose_action(state)\n")

    def test_nested_loops_blocked(self):
        self.reject("def choose_action(state):\n    while True:\n        return 'BLOCK'\n")

    def test_unknown_global_blocked(self):
        self.reject("def choose_action(state):\n    return secret\n")

    def test_decorators_blocked(self):
        self.reject("@property\ndef choose_action(state):\n    return 'BLOCK'\n")

    def test_fences_and_control_bytes_blocked(self):
        self.reject("def choose_action(state):\n    return 'BLOCK'\n" + chr(96) * 3)
        self.reject("def choose_action(state):\r\n    return 'BLOCK'\r\n")

    def test_architecture_contract_same_goal_different_prompt(self):
        c = s.load_config(ROOT / "configs/self-evolution-8lanes.json")
        p1, p2 = s.prompt(c, "01"), s.prompt(c, "02")
        self.assertNotEqual(p1, p2)
        self.assertIn(s.TASK, p1)
        self.assertIn(s.TASK, p2)
        with self.assertRaises(ValueError):
            s.prompt(c, "03")

    def test_eight_shared_sha_manifests(self):
        c = s.load_config(ROOT / "configs/self-evolution-8lanes.json")
        m = s.build_manifests(c, COMMIT)
        self.assertEqual(len(m), 8)
        self.assertTrue(all(x["source_patch_generated"] is False for x in m))

    def test_verify_rejects_forged_success(self):
        fields, _, _ = s.context(
            ROOT, ROOT / "configs/self-evolution-8lanes.json", "01", COMMIT)
        raw = VALID
        record = {**fields, "model_calls": 1, "raw_response": raw,
                  "response_sha256": s.sha(raw.encode()),
                  "candidate_sha256": s.sha(raw.encode()),
                  "outcome": "model_candidate_passed",
                  "evaluation": {"status": "model_candidate_passed"}}
        record["merge_authorized"] = True
        with self.assertRaises(ValueError):
            s.verify(ROOT, ROOT / "configs/self-evolution-8lanes.json",
                     COMMIT, record)

    def test_verify_rejects_modified_model_response(self):
        fields, _, _ = s.context(
            ROOT, ROOT / "configs/self-evolution-8lanes.json", "01", COMMIT)
        record = {**fields, "model_calls": 1, "raw_response": VALID,
                  "response_sha256": "0" * 64,
                  "candidate_sha256": s.sha(VALID.encode()),
                  "outcome": "model_candidate_passed",
                  "evaluation": {"status": "model_candidate_passed"}}
        with self.assertRaises(ValueError):
            s.verify(ROOT, ROOT / "configs/self-evolution-8lanes.json",
                     COMMIT, record)

    def test_replay_synthetic_record_without_docker(self):
        fields, _, _ = s.context(
            ROOT, ROOT / "configs/self-evolution-8lanes.json", "01", COMMIT)
        record = {**fields, "model_calls": 1, "raw_response": VALID,
                  "response_sha256": s.sha(VALID.encode()),
                  "candidate_sha256": s.sha(VALID.encode()),
                  "outcome": "model_candidate_passed",
                  "evaluation": {"status": "model_candidate_passed"}}
        with patch.object(s, "grade", return_value={"status": "model_candidate_passed"}):
            out = s.verify(ROOT, ROOT / "configs/self-evolution-8lanes.json",
                           COMMIT, record)
        self.assertEqual(out["status"], "candidate_replayed")
        self.assertTrue(out["candidate_passed"])


if __name__ == "__main__":
    unittest.main()
