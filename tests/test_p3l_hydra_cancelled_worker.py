"""Regression for unresolved cancelled workers in the read-only selector."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from p3l_hydra_next_task import select


class CancelledWorkerTests(unittest.TestCase):
    def test_outcomes(self):
        run = dict(id=1, event="push", head_branch="main", status="completed", run_attempt=1, head_sha="a"*40)
        for name, outcome, expected in [
            ("Worker a", "cancelled", "needs_approval"),
            ("admit", "cancelled", "no_unresolved_failure"),
            ("Worker a", "skipped", "no_unresolved_failure"),
            ("Worker a", "unexpected", "no_unresolved_failure"),
            ("Worker a", "timed_out", "needs_approval"),
            ("admit", "failure", "needs_approval"),
        ]:
            with self.subTest(name=name, outcome=outcome):
                jobs = {1: [dict(id=1, name=name, conclusion=outcome)]}
                self.assertEqual(select([run], jobs)["decision"], expected)

    def test_resolution(self):
        first = dict(id=1, event="push", head_branch="main", status="completed", run_attempt=1, head_sha="a"*40)
        second = {**first, "id": 2}
        jobs = {1:[dict(id=1, name="Worker a", conclusion="cancelled")]}
        jobs[2] = [dict(id=2, name="Worker a", conclusion="skipped")]
        self.assertEqual(select([first, second], jobs)["proposal"]["job_id"], 1)
        jobs[2][0]["conclusion"] = "success"
        self.assertIsNone(select([first, second], jobs)["proposal"])
