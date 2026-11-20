import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_balanced_prompt_run_plan import make_plan

class BalancedPlanTests(unittest.TestCase):
    def setUp(self):
        self.groups = [f"g{i:03}" for i in range(30)]

    def test_minimum_independent_groups(self):
        with self.assertRaisesRegex(ValueError, "at least 30"):
            make_plan(self.groups[:29])

    def test_reject_case_alias(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            make_plan(self.groups + ["G000"])

    def test_reject_unsafe_identifiers(self):
        with self.assertRaisesRegex(ValueError, "invalid"):
            make_plan(self.groups[:-1] + ["hidden answer\nSECRET"])

    def test_exact_balanced_calls(self):
        p = make_plan(self.groups)
        self.assertEqual(len(p), 120)
        self.assertEqual([x["global_sequence"] for x in p], list(range(1,121)))
        self.assertEqual(sum(x["block"] == "AB" for x in p), 60)
        self.assertEqual(sum(x["block"] == "AA" for x in p), 60)

    def test_ab_order_balanced(self):
        p = make_plan(self.groups)
        ab = [x for x in p if x["block"] == "AB"]
        self.assertEqual(sum(x["position"] == 1 and x["variant"] == "A" for x in ab), 15)
        self.assertEqual(sum(x["position"] == 1 and x["variant"] == "B" for x in ab), 15)

    def test_aa_identical_controls(self):
        p = make_plan(self.groups)
        self.assertTrue(all(x["variant"] == "A" for x in p if x["block"] == "AA"))

    def test_each_group_has_two_blocks(self):
        p = make_plan(self.groups)
        for g in self.groups:
            rows = [x for x in p if x["group_id"] == g]
            self.assertEqual(len(rows), 4)
            self.assertEqual({x["block"] for x in rows}, {"AB", "AA"})

    def test_determinism_independent_of_input_order(self):
        self.assertEqual(make_plan(self.groups), make_plan(list(reversed(self.groups))))

    def test_seed_changes_order(self):
        self.assertNotEqual(make_plan(self.groups, 1), make_plan(self.groups, 2))

    def test_boolean_seed_rejected(self):
        with self.assertRaisesRegex(ValueError, "integer seed"):
            make_plan(self.groups, True)

    def test_output_has_no_answers_or_model_claims(self):
        text = json.dumps(make_plan(self.groups))
        self.assertNotIn("teacher_answer", text)
        self.assertNotIn("quality_gain", text)
        self.assertNotIn("optimizer_steps", text)

    def test_cli_real_run_and_digest(self):
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "groups.json"
            b = Path(d) / "plan.jsonl"
            a.write_text(json.dumps(self.groups))
            cmd = [sys.executable, str(Path(__file__).resolve().parents[1] /
                   "scripts/oril_v2_balanced_prompt_run_plan.py"),
                   "--groups", str(a), "--output", str(b)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["real_model_calls"], 0)
            self.assertIsNone(report["quality_gain"])
            self.assertEqual(len(b.read_text().splitlines()), 120)

    def test_reject_overwrite_source(self):
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "groups.json"
            a.write_text(json.dumps(self.groups))
            result = subprocess.run([sys.executable,
                str(Path(__file__).resolve().parents[1] / "scripts/oril_v2_balanced_prompt_run_plan.py"),
                "--groups", str(a), "--output", str(a)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(json.loads(a.read_text()), self.groups)

if __name__ == "__main__":
    unittest.main()
