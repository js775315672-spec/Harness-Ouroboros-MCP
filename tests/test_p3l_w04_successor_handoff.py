"""Verified predecessor deliveries may queue only one review-only successor."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import sqlite3
import sys
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from p3l_w04_attempt_registry import AttemptBlocked, AttemptRegistry
import p3l_w04_successor_handoff as handoff


class SuccessorHandoffTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.database = self.root / "attempts.sqlite3"
        self.registry = AttemptRegistry(self.database)
        w07 = handoff.w07
        self.verified = self.enterContext(patch.object(w07, "rehearse", return_value={
            "status": "REVIEW_PENDING", "historical_docker_test_count": 25,
            "w08_handoff_authorized": False, "w05_run_id": w07.RUN_ID,
            "historical_commit": w07.BASELINE_COMMIT, "proposed_runtime_commit": w07.CANDIDATE_COMMIT,
        }))
        self.enterContext(patch.object(w07, "read_artifact", return_value=({"github_provenance": {
            "model_revision": "3" * 40, "model_weights_sha256": "b" * 64,
            "inference_config_sha256": "c" * 64, "prompt_sha256": "d" * 64,
        }},)))
        self.enterContext(patch.object(w07, "git", side_effect=lambda root, verb, ref:
                          b"1" * 40 if verb == "rev-parse" else b"public contract"))
        self.inputs = handoff.historical_inputs(self.root)

    def record(self, inputs=None, *, receipt=handoff.w07.MODEL_ARCHIVE[1]):
        inputs = inputs or self.inputs
        lease = self.registry.reserve(inputs, "worker", ttl_seconds=30)
        run_id = handoff.w07.RUN_ID
        self.registry.start(lease, observed_head=inputs.head_sha, run_id=run_id)
        self.registry.record_model_generated(lease, run_id=run_id, receipt_sha256=receipt)

    def deliver(self, registry=None):
        return handoff.prepare_successor(registry or self.registry, candidate=self.root, evidence=self.root)

    def saved(self):
        with closing(sqlite3.connect(self.database)) as db:
            return db.execute("SELECT proposal_json FROM successor_handoffs").fetchall()

    def test_race_and_restart_keep_one_review_only_proposal(self):
        self.record()
        barrier = Barrier(2)

        def worker():
            registry = AttemptRegistry(self.database)
            barrier.wait(timeout=5)
            return self.deliver(registry)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = [future.result(timeout=10) for future in (pool.submit(worker), pool.submit(worker))]
        self.assertCountEqual([first["created"], second["created"]], [True, False])
        self.assertEqual(first["proposal"], second["proposal"])
        restarted = self.deliver(AttemptRegistry(self.database))
        self.assertFalse(restarted["created"])
        self.assertEqual(restarted["proposal"]["status"], "REVIEW_PENDING")
        self.assertIs(restarted["proposal"]["w08_execution_authorized"], False)
        self.assertEqual(restarted["proposal"]["model_calls"], 0)
        self.assertEqual(len(self.saved()), 1)

    def test_unverified_completion_cannot_create_a_proposal(self):
        self.record()
        self.verified.side_effect = ValueError("independent replay evidence is invalid")
        with self.assertRaisesRegex(ValueError, "independent replay"):
            self.deliver()
        self.assertEqual(self.saved(), [])

    def test_other_prompt_does_not_match_reconciled_predecessor(self):
        self.record(replace(self.inputs, prompt_sha256="f" * 64))
        with self.assertRaisesRegex(AttemptBlocked, "no matching reconciled model artifact"):
            self.deliver()
        self.assertEqual(self.saved(), [])

    def test_wrong_archive_cannot_create_a_proposal(self):
        self.record(receipt="a" * 64)
        with self.assertRaisesRegex(AttemptBlocked, "no matching reconciled model artifact"):
            self.deliver()
        self.assertEqual(self.saved(), [])

    def test_conflicting_retry_cannot_replace_pending_proposal(self):
        self.record()
        self.deliver()
        saved = self.saved()
        choice = {**handoff.select(), "phase": "boundary"}
        with patch.object(handoff, "select", return_value=choice):
            with self.assertRaisesRegex(AttemptBlocked, "different successor proposal"):
                self.deliver()
        self.assertEqual(self.saved(), saved)


if __name__ == "__main__":
    unittest.main()
