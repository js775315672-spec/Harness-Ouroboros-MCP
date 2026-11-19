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


if __name__ == "__main__":
    unittest.main()
