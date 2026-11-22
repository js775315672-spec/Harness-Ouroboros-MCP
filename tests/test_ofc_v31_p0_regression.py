import unittest
from unittest.mock import patch
from agent import cycle_registry as r

SOURCE = "a" * 40

class OuroborosRegistryRegression(unittest.TestCase):
    def base(self):
        return dict(schema=1, agent=r.AGENT, cycle="cycle-o", source=SOURCE,
                    phase="open", owner="old", generation=2, expires=0,
                    checkpoint="previous", pending=None, results={"prior": "receipt"})

    def test_acquire_fences_old_owner_and_preserves_results(self):
        state, changed = r.transition(self.base(), "acquire", "new", 0, SOURCE, "", 100, 60)
        self.assertTrue(changed)
        self.assertEqual(state["generation"], 3)
        self.assertEqual(state["results"], {"prior": "receipt"})
        with self.assertRaises(r.Blocked):
            r.transition(state, "checkpoint", "old", 2, SOURCE, "stale", 101, 60)

    def test_pending_blocks_reacquire_and_checkpoint(self):
        state = self.base()
        state["pending"] = "external-key"
        with self.assertRaises(r.Blocked):
            r.transition(state, "acquire", "new", 0, SOURCE, "", 100, 60)
        state["expires"] = 150
        with self.assertRaises(r.Blocked):
            r.transition(state, "checkpoint", "old", 2, SOURCE, "skip", 101, 60)

    def test_source_rollover_rejected(self):
        with self.assertRaises(r.Blocked):
            r.transition(self.base(), "acquire", "new", 0, "b" * 40, "", 100, 60)

    def test_remote_cas_rejection_propagates(self):
        refs = f"{'c'*40}\t{r.REF}\n{SOURCE}\trefs/heads/main"
        state = self.base()
        def fake_git(*args, **kwargs):
            if args[0] == "ls-remote": return refs
            if args[0] == "fetch": return ""
            if args[0] == "show":
                import json
                return json.dumps(state)
            if args[0] == "hash-object": return "d"*40
            if args[0] == "mktree": return "e"*40
            if args[0] == "commit-tree": return "f"*40
            if args[0] == "push": raise __import__("subprocess").CalledProcessError(1, "git push")
            raise AssertionError(args)
        with patch.object(r, "git", side_effect=fake_git):
            with self.assertRaises(__import__("subprocess").CalledProcessError):
                r.transact("test-remote", "acquire", owner="new", source=SOURCE)
if __name__ == "__main__":
    unittest.main()
