"""Check pausing and restarting a two-lane dispatch ledger."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from p3l_hydra_completion_rehearsal import CompletionRegistry
from p3l_hydra_generation_rehearsal import make_plan


class DispatchPauseTests(unittest.TestCase):
    def test_pause_survives_reopen_without_releasing_spent_slots(self):
        head = "a" * 40
        plan = make_plan(head)
        plan["max_parallel"] = 2
        plan["tasks"][2]["deps"] = ["source"]
        plan["tasks"].append({**plan["tasks"][2], "key": "third", "paths": ["tests/third.py"]})
        scope = ("first", "second", "third")
        source = dict(task="source", head=head, run_id=1, job_id=1)
        finish = dict(task="first", head=head, run_id=1, job_id=2)

        def proof(event):
            return {**event, "passed": True, "sha256": "b" * 64}

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "queue.sqlite"
            registry = CompletionRegistry(path, plan, approved_tasks=scope)
            registry.set_paused(True)
            with self.assertRaisesRegex(ValueError, "paused"):
                registry.complete(source, proof)
            registry.set_paused(False)
            self.assertEqual(registry.complete(source, proof)["reserved"], ["first", "second"])
            self.assertTrue(registry.consume("first", source, observed_head=head, completion=(1, 2)))
            registry.set_paused(True)
            reopened = CompletionRegistry(path, plan, approved_tasks=scope)
            with self.assertRaisesRegex(ValueError, "paused"):
                reopened.consume("second", source, observed_head=head, completion=(1, 3))
            with self.assertRaisesRegex(ValueError, "paused"):
                reopened.complete(finish, proof)
            reopened.set_paused(False)
            self.assertFalse(reopened.consume("first", source, observed_head=head, completion=(1, 2)))
            self.assertTrue(reopened.consume("second", source, observed_head=head, completion=(1, 3)))
            self.assertEqual(reopened.complete(finish, proof)["reserved"], ["third"])
            self.assertFalse(reopened.complete(finish, proof)["accepted"])
