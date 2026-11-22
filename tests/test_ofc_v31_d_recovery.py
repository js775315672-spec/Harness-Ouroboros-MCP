"""OFC v3.1 D: isolated recovery negative tests; no OPS side effects."""
import copy
import unittest
from agent import cycle_registry as registry


class TestIndependentRecoverySafety(unittest.TestCase):
    def setUp(self):
        self.source = "a" * 40
        self.owner = "dev-test-run-1"
        self.now = 1000
        self.state, changed = registry.transition({}, "acquire", self.owner, 0, self.source, "", self.now, 10)
        self.assertTrue(changed)
        self.assertEqual(self.state["agent"], "ouroboros")

    def test_expired_pending_must_not_be_replayed(self):
        state, _ = registry.transition(copy.deepcopy(self.state), "reserve", self.owner, self.state["generation"], self.source, "qwen-once", self.now + 1, 10)
        for command in ("acquire", "recover"):
            with self.subTest(command=command), self.assertRaises(registry.Blocked):
                registry.transition(copy.deepcopy(state), command, "new-owner", state["generation"], self.source, "", self.now + 20, 10)
        self.assertEqual(state["pending"], "qwen-once")
        self.assertEqual(state["results"], {})

    def test_fenced_recovery_rejects_stale_generation(self):
        with self.assertRaises(registry.Blocked):
            registry.transition(copy.deepcopy(self.state), "recover", "new-owner", self.state["generation"] - 1, self.source, "", self.now + 20, 10)

    def test_fenced_recovery_preserves_results(self):
        state, _ = registry.transition(copy.deepcopy(self.state), "reserve", self.owner, self.state["generation"], self.source, "artifact", self.now + 1, 10)
        state, _ = registry.transition(state, "record", self.owner, state["generation"], self.source, "artifact=sha256:abc", self.now + 2, 10)
        state, _ = registry.transition(state, "recover", "new-owner", state["generation"], self.source, "", self.now + 20, 10)
        self.assertEqual(state["results"]["artifact"], "sha256:abc")
        self.assertEqual(state["generation"], 2)
        with self.assertRaises(registry.Blocked):
            registry.transition(state, "reserve", "new-owner", 2, self.source, "artifact", self.now + 21, 10)

    def test_source_drift_is_blocked(self):
        with self.assertRaises(registry.Blocked):
            registry.transition(copy.deepcopy(self.state), "recover", "new-owner", self.state["generation"], "b" * 40, "", self.now + 20, 10)


if __name__ == "__main__":
    unittest.main()
