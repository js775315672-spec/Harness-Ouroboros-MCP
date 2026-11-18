"""Exercise durable admission and recovery with a disposable SQLite file."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
from threading import Barrier
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from p3l_w04_attempt_registry import AttemptBlocked, AttemptInput, AttemptRegistry

TASK = AttemptInput("ledger-text", "a" * 64, "1" * 40, "2" * 40, "3" * 40,
                    "b" * 64, "c" * 64, "d" * 64)


class AttemptRegistryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "attempts.sqlite3"
        self.now = 100
        self.registry = AttemptRegistry(self.path, clock=lambda: self.now)

    def test_identity_binds_inputs_without_renewing_the_semantic_budget(self):
        revised = replace(TASK, prompt_sha256="e" * 64, head_sha="4" * 40)
        self.assertNotEqual(TASK.task_key, revised.task_key)
        self.assertEqual(TASK.semantic_key, revised.semantic_key)
        with self.assertRaises(ValueError):
            replace(TASK, prompt_sha256=True)

    def test_two_workers_cannot_both_reserve_and_start(self):
        barrier = Barrier(2)
        model = Mock()

        def worker(owner):
            registry = AttemptRegistry(self.path, clock=lambda: self.now)
            barrier.wait(timeout=10)
            try:
                lease = registry.reserve(TASK, owner, ttl_seconds=20)
                registry.start(lease, observed_head=TASK.head_sha, run_id=123)
            except AttemptBlocked:
                return False
            model()
            return True

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, ["runner-a", "runner-b"]))
        self.assertEqual(results.count(True), 1)
        model.assert_called_once_with()
        self.assertEqual(self.registry.status(TASK)["state"], "STARTED")

    def test_heartbeat_and_expiry_fence_the_previous_owner(self):
        first = self.registry.reserve(TASK, "runner-a", ttl_seconds=5)
        self.now = 104
        renewed = self.registry.heartbeat(first, ttl_seconds=5)
        self.now = 105
        self.assertEqual(renewed.expires_at, 109)
        with self.assertRaises(AttemptBlocked):
            self.registry.reserve(TASK, "runner-b", ttl_seconds=5)
        self.now = 109
        self.assertEqual(self.registry.status(TASK)["state"], "EXPIRED")
        revised = replace(TASK, head_sha="4" * 40)
        next_lease = self.registry.reserve(revised, "runner-b", ttl_seconds=5)
        self.assertEqual(next_lease.epoch, first.epoch + 1)
        with self.assertRaises(AttemptBlocked):
            self.registry.start(first, observed_head=TASK.head_sha, run_id=123)
        with self.assertRaises(AttemptBlocked):
            self.registry.heartbeat(first, ttl_seconds=5)
        self.registry.start(next_lease, observed_head=revised.head_sha, run_id=124)

    def test_wrong_head_and_boolean_identifiers_do_not_spend_the_budget(self):
        lease = self.registry.reserve(TASK, "runner-a", ttl_seconds=10)
        with self.assertRaises(ValueError):
            replace(lease, epoch=True)
        with self.assertRaises(ValueError):
            self.registry.start(lease, observed_head=TASK.head_sha, run_id=True)
        with self.assertRaises(AttemptBlocked):
            self.registry.start(lease, observed_head="4" * 40, run_id=123)
        self.assertEqual(self.registry.status(TASK)["state"], "LEASED")
        self.registry.start(lease, observed_head=TASK.head_sha, run_id=123)
        with self.assertRaises(AttemptBlocked):
            self.registry.start(lease, observed_head=TASK.head_sha, run_id=123)

    def test_restart_blocks_a_second_call_and_accepts_only_the_original_receipt(self):
        lease = self.registry.reserve(TASK, "runner-a", ttl_seconds=5)
        self.registry.start(lease, observed_head=TASK.head_sha, run_id=123)
        self.now = 106
        restarted = AttemptRegistry(self.path, clock=lambda: self.now)
        self.assertEqual(restarted.status(TASK)["state"], "UNVERIFIED")
        for inputs in (TASK, replace(TASK, prompt_sha256="e" * 64)):
            with self.assertRaises(AttemptBlocked):
                restarted.reserve(inputs, "runner-b", ttl_seconds=10)
        with self.assertRaises(AttemptBlocked):
            restarted.record_model_generated(lease, run_id=124, receipt_sha256="f" * 64)
        restarted.record_model_generated(lease, run_id=123, receipt_sha256="f" * 64)
        restarted.record_model_generated(lease, run_id=123, receipt_sha256="f" * 64)
        with self.assertRaises(AttemptBlocked):
            restarted.record_model_generated(lease, run_id=123, receipt_sha256="e" * 64)
        with self.assertRaises(AttemptBlocked):
            restarted.reserve(TASK, "runner-b", ttl_seconds=10)
        self.assertEqual(restarted.status(TASK)["state"], "MODEL_GENERATED")


if __name__ == "__main__":
    unittest.main()
