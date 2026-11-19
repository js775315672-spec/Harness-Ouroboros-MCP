"""Check completion deduplication, evidence and plan identity in a disposable database."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
from p3l_hydra_completion_rehearsal import CompletionRegistry


class CompletionRehearsalTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "completion.sqlite3"
        self.plan = json.loads((HERE / "fixtures/p3l_hydra_fast_lane_plan.json").read_bytes())
        self.plan["tasks"][0].update(state="running", evidence_sha=None)
        self.event = {"task": "w01_contract", "head": self.plan["head_sha"], "run_id": 11, "job_id": 22}
        self.registry = CompletionRegistry(self.path, self.plan)

    @staticmethod
    def verify(event):
        return {**event, "passed": True, "sha256": "c" * 64}

    def test_racing_delivery_and_reopen_only_admit_one_completion(self):
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: self.registry.complete(self.event, self.verify), range(2)))
        self.assertCountEqual(results, [
            {"accepted": True, "eligible": ["w06_public_probe", "w05_receipt_gate"]},
            {"accepted": False, "eligible": []},
        ])
        reopened = CompletionRegistry(self.path, self.plan)
        self.assertFalse(reopened.complete(self.event, self.verify)["accepted"])
        with self.assertRaisesRegex(ValueError, "different receipt"):
            reopened.complete(self.event, lambda e: {**self.verify(e), "sha256": "d" * 64})

    def test_wrong_evidence_and_stale_head_do_not_unlock_dependencies(self):
        with self.assertRaisesRegex(ValueError, "not independently verified"):
            self.registry.complete(self.event, lambda e: {**self.verify(e), "job_id": 23})
        with self.assertRaisesRegex(ValueError, "not independently verified"):
            self.registry.complete(self.event, lambda e: {**self.verify(e), "passed": False})
        with self.assertRaisesRegex(ValueError, "stale"):
            self.registry.complete({**self.event, "head": "f" * 40}, self.verify)
        self.assertTrue(self.registry.complete(self.event, self.verify)["accepted"])

    def test_existing_database_does_not_accept_a_different_plan(self):
        with self.assertRaisesRegex(ValueError, "different input plan"):
            CompletionRegistry(self.path, {**self.plan, "max_parallel": 1})

    def test_only_approved_successor_is_reserved_once(self):
        scope = ("w05_receipt_gate",)
        path = self.path.with_name("approved.sqlite3")
        registry = CompletionRegistry(path, self.plan, approved_tasks=scope)
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: registry.complete(self.event, self.verify), range(2)))
        self.assertCountEqual([result["reserved"] for result in results], [["w05_receipt_gate"], []])
        reopened = CompletionRegistry(path, self.plan, approved_tasks=scope)
        self.assertEqual(reopened.complete(self.event, self.verify)["reserved"], [])
        with self.assertRaisesRegex(ValueError, "different approval scope"):
            CompletionRegistry(path, self.plan, approved_tasks=(*scope, "w06_public_probe"))

    def test_reserved_slot_blocks_a_second_completion_from_overbooking(self):
        anchor, _, later, _ = self.plan["tasks"]
        later.update(state="running", deps=[])
        blocked_path = self.plan["tasks"][1]["paths"]
        self.plan["tasks"] += [
            {**anchor, "key": "after_later", "state": "pending", "paths": blocked_path,
             "deps": [later["key"]]},
        ]
        registry = CompletionRegistry(self.path.with_name("capacity.sqlite3"), self.plan,
                                      approved_tasks=("w06_public_probe", "after_later"))
        self.assertEqual(registry.complete(self.event, self.verify)["reserved"], ["w06_public_probe"])
        later_event = {**self.event, "task": later["key"], "job_id": 23}
        self.assertEqual(registry.complete(later_event, self.verify)["reserved"], [])

    def test_zero_approved_successors_and_failed_evidence(self):
        registry = CompletionRegistry(self.path.with_name("empty.sqlite3"), self.plan, approved_tasks=())
        with self.assertRaisesRegex(ValueError, "not independently verified"):
            registry.complete(self.event, lambda e: {**self.verify(e), "passed": False})
        result = registry.complete(self.event, self.verify)
        self.assertTrue(result["accepted"])
        self.assertEqual(result["reserved"], [])

    def test_running_task_counts_toward_parallel_limit(self):
        self.plan["max_parallel"] = 1
        running = self.plan["tasks"][2]
        running.update(state="running", deps=[])
        registry = CompletionRegistry(self.path.with_name("one-slot.sqlite3"), self.plan,
                                      approved_tasks=("w06_public_probe",))
        self.assertEqual(registry.complete(self.event, self.verify)["reserved"], [])
        final_event = {**self.event, "task": running["key"], "job_id": 23}
        self.assertEqual(registry.complete(final_event, self.verify)["reserved"], ["w06_public_probe"])


if __name__ == "__main__":
    unittest.main()
