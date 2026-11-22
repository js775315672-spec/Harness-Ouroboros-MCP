"""No-model-call contract tests for the 120-cycle DEV planner."""
import tempfile
import unittest
from pathlib import Path
from agent.adaptive_dev_120 import (
    MAX_BATCHES, new_campaign, next_batch, reserve_batch, record_batch,
    stable_key, persist, load,
)

class Adaptive120Tests(unittest.TestCase):
    def receipt(self, pending, passed=True, cycles=12, seconds=1, cost=0):
        return dict(pending, evaluator_sha="e"*40, evidence_sha256="f"*64,
                    independent_pass=passed, elapsed_seconds=seconds,
                    cost_usd=cost, cycles_completed=cycles)

    def test_maximum_120_and_stable_keys(self):
        s = new_campaign("Ouroboros", "test-campaign", 100, 0)
        for i in range(1, MAX_BATCHES + 1):
            self.assertEqual(next_batch(s), i)
            p = reserve_batch(s, i, "a"*40)
            self.assertEqual(p["operation_key"], stable_key("Ouroboros", "test-campaign", i, 1, "a"*40))
            record_batch(s, self.receipt(p))
        self.assertEqual(s["status"], "complete")
        self.assertEqual(sum(b["cycles_completed"] for b in s["batches"]), 120)
        self.assertIsNone(next_batch(s))

    def test_pending_and_cross_agent_rejected(self):
        s = new_campaign("Cerberus", "campaign", 60)
        reserve_batch(s, 1, "a"*40)
        with self.assertRaisesRegex(RuntimeError, "pending"):
            next_batch(s)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "state.json"
            persist(p, s)
            with self.assertRaisesRegex(RuntimeError, "ledger mismatch"):
                load(p, "Fenrir", "campaign")

    def test_fail_closed_and_budget(self):
        s = new_campaign("Fenrir", "campaign", 10)
        p = reserve_batch(s, 1, "a"*40)
        record_batch(s, self.receipt(p, passed=False))
        self.assertEqual(s["status"], "blocked")
        self.assertIsNone(next_batch(s))
        t = new_campaign("Fenrir", "other", 10)
        p = reserve_batch(t, 1, "b"*40)
        record_batch(t, self.receipt(p, seconds=11))
        self.assertEqual(t["status"], "budget_exhausted")

    def test_unverified_receipt_preserves_pending(self):
        s = new_campaign("Cerberus", "campaign", 60)
        reserve_batch(s, 1, "a"*40)
        with self.assertRaises(ValueError):
            record_batch(s, {"batch": 1})
        self.assertIsNotNone(s["pending"])

if __name__ == "__main__":
    unittest.main()
