"""Offline adversarial function-level benchmark gate tests.

Never executes an untrusted source answer. The only real execution path stages
candidate.py and immutable evaluator tests inside read-only no-network Docker.
"""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from qwen_function_level_probe import (
    inspect_function, task_lock, git_blob_sha, PROMPT,
    format_function_prompt, TEST_FILE, EXPECTED_METHODS,
)

SAFE = """def merge_intervals(intervals):
    if not isinstance(intervals, (list, tuple)):
        raise ValueError("invalid intervals")
    pairs = []
    for item in intervals:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError("bad pair")
        start, end = item
        if type(start) is not int or type(end) is not int or start > end:
            raise ValueError("bad interval")
        pairs.append((start, end))
    pairs.sort()
    result = []
    for start, end in pairs:
        if result and start <= result[-1][1] + 1:
            left, previous_end = result[-1]
            result[-1] = (left, max(end, previous_end))
        else:
            result.append((start, end))
    return result
"""


class FunctionLevelGateTests(unittest.TestCase):
    def test_fixed_task_and_hidden_test_integrity(self):
        lock, checksum, tests = task_lock(ROOT)
        self.assertEqual(lock["expected_heldout_test_methods"], 13)
        self.assertEqual(lock["trusted_tests_git_blob_sha"], git_blob_sha(tests))
        self.assertEqual(len(checksum),64)
        self.assertTrue(lock["sandbox"]["network_disabled"])
        self.assertTrue(lock["sandbox"]["no_model_editable_tests"])
        self.assertEqual(lock["max_model_calls"],1)
        self.assertFalse(lock["prompt_contains_tests"])
        self.assertNotIn("test_reject_bad_outer_input", PROMPT)

    def test_whole_function_would_be_allowed_as_model_data(self):
        self.assertEqual(inspect_function(SAFE), SAFE)
        self.assertIn("def merge_intervals(intervals):", format_function_prompt())
        self.assertNotIn("heldout_merge_intervals.py",format_function_prompt())

    def test_executable_import_shell_test_edit_and_dunder_rejected(self):
        malformed = [
            "import os\n" + SAFE,
            SAFE + "\nprint('done')\n",
            "def evil(intervals):\n    return []\n",
            "def merge_intervals(intervals):\n    return __import__('os').system('id')\n",
            "def merge_intervals(intervals):\n    open('/etc/passwd')\n    return []\n",
            "def merge_intervals(intervals):\n    return intervals.__class__\n",
            "def merge_intervals(intervals):\n    return eval('1')\n",
            "def merge_intervals(intervals):\n    exec('print(1)')\n",
            "def merge_intervals(intervals):\n    global x\n    return []\n",
            "def merge_intervals(intervals):\n    def helper(x):\n        return x\n    return []\n",
            "def merge_intervals(intervals):\n    return []\n" + chr(96)*3,
        ]
        for bad in malformed:
            with self.subTest(raw=repr(bad)[:60]):
                with self.assertRaises(ValueError):
                    inspect_function(bad)

    def test_no_source_execution_or_environment_required_for_help(self):
        completed = subprocess.run(
            [sys.executable, "scripts/qwen_function_level_probe.py", "--help"],
            cwd=ROOT, capture_output=True, text=True, timeout=12)
        self.assertEqual(completed.returncode,0,completed.stderr)
        self.assertIn("--report",completed.stdout)

    def test_immutable_test_fixture_has_thirteen_methods(self):
        raw=(ROOT/TEST_FILE).read_text(encoding="utf-8")
        count=raw.count("    def test_")
        self.assertEqual(count, EXPECTED_METHODS)
        self.assertNotIn("exec(",raw)
        self.assertNotIn("eval(",raw)


if __name__=="__main__":
    unittest.main()
