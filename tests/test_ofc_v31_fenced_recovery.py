"""P0 fail-closed recovery: generation fencing and unresolved-effect preservation."""
import unittest
from agent import cycle_registry as r

SOURCE = "a" * 40

class FencedRecovery(unittest.TestCase):
    def state(self):
        return dict(schema=1, agent=r.AGENT, cycle="unchanged-cycle",
                    source=SOURCE, phase="open", owner="expired-owner",
                    generation=9, expires=90, checkpoint="saved",
                    pending=None, results={"done": "verified-receipt"})

    def test_recover_preserves_receipts_and_cycle(self):
        state, changed = r.transition(self.state(), "recover", "new-owner",
                                      9, SOURCE, "", 100, 30)
        self.assertTrue(changed)
        self.assertEqual(state["generation"], 10)
        self.assertEqual(state["cycle"], "unchanged-cycle")
        self.assertEqual(state["results"], {"done": "verified-receipt"})
        self.assertEqual(state["checkpoint"], "saved")
        self.assertEqual(state["owner"], "new-owner")

    def test_old_generation_cannot_recover_twice(self):
        state, _ = r.transition(self.state(), "recover", "first", 9, SOURCE, "", 100, 10)
        with self.assertRaises(r.Blocked):
            r.transition(state, "recover", "second", 9, SOURCE, "", 111, 10)
        self.assertEqual(state["owner"], "first")

    def test_pending_never_cleared(self):
        state = self.state()
        state["pending"] = "unknown-external-result"
        with self.assertRaises(r.Blocked):
            r.transition(state, "recover", "new", 9, SOURCE, "", 100, 30)
        self.assertEqual(state["pending"], "unknown-external-result")

    def test_source_drift_blocks(self):
        with self.assertRaises(r.Blocked):
            r.transition(self.state(), "recover", "new", 9, "b" * 40, "", 100, 30)

    def test_active_lease_blocks(self):
        with self.assertRaises(r.Blocked):
            r.transition(self.state(), "recover", "new", 9, SOURCE, "", 80, 30)

    def test_recovery_rejects_complete_and_blocked(self):
        for phase in ("complete", "blocked"):
            with self.subTest(phase=phase):
                state = self.state()
                state["phase"] = phase
                with self.assertRaises(r.Blocked):
                    r.transition(state, "recover", "new", 9, SOURCE, "", 100, 30)

    def test_recovery_rejects_bad_ttl(self):
        for ttl in (0, 3601):
            with self.subTest(ttl=ttl):
                with self.assertRaises(r.Blocked):
                    r.transition(self.state(), "recover", "new", 9, SOURCE, "", 100, ttl)

if __name__ == "__main__":
    unittest.main()
