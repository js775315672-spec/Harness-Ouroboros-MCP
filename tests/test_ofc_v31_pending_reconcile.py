import unittest
from agent import cycle_registry as r
from agent.pending_reconcile import Observation, reconcile

SOURCE = "f" * 40

class PendingReconcileContract(unittest.TestCase):
    def setUp(self):
        self.state = dict(schema=1, agent=r.AGENT, cycle="c1", phase="open",
                          owner="runner", generation=3, source=SOURCE,
                          expires=200, pending="operation-1",
                          results={"previous": "retained"})
        self.good = Observation("operation-1", SOURCE, "confirmed", "receipt-1")

    def run_reconcile(self, lookup=None, verify=None, **kwargs):
        return reconcile(self.state, owner=kwargs.get("owner", "runner"),
                         generation=kwargs.get("generation", 3),
                         source=kwargs.get("source", SOURCE),
                         now=kwargs.get("now", 100),
                         lookup=lookup or (lambda key: self.good),
                         verify=verify or (lambda o: True))

    def test_verified_receipt_preserves_old_results(self):
        out = self.run_reconcile()
        self.assertEqual(out["results"], {"previous": "retained", "operation-1": "receipt-1"})
        self.assertIsNone(out["pending"])
        self.assertEqual(self.state["pending"], "operation-1")

    def test_missing_lookup_blocks(self):
        with self.assertRaises(r.Blocked):
            self.run_reconcile(lookup=lambda key: None)
        self.assertEqual(self.state["pending"], "operation-1")

    def test_lookup_error_blocks(self):
        def fail(_): raise TimeoutError("unknown")
        with self.assertRaises(r.Blocked):
            self.run_reconcile(lookup=fail)

    def test_unconfirmed_or_wrong_source_blocks(self):
        for observation in [
            Observation("operation-1", SOURCE, "pending", "r"),
            Observation("operation-1", "0" * 40, "confirmed", "r"),
            Observation("other", SOURCE, "confirmed", "r"),
            Observation("operation-1", SOURCE, "confirmed", ""),
        ]:
            with self.subTest(observation=observation):
                with self.assertRaises(r.Blocked):
                    self.run_reconcile(lookup=lambda key: observation)

    def test_unverified_and_verifier_error_block(self):
        with self.assertRaises(r.Blocked):
            self.run_reconcile(verify=lambda o: False)
        def fail(_): raise ValueError("bad signature")
        with self.assertRaises(r.Blocked):
            self.run_reconcile(verify=fail)

    def test_stale_owner_generation_and_expiry_block(self):
        for kw in [dict(owner="stale"), dict(generation=2),
                   dict(source="0"*40), dict(now=201)]:
            with self.subTest(kw=kw):
                with self.assertRaises(r.Blocked):
                    self.run_reconcile(**kw)

    def test_duplicate_operation_blocks(self):
        self.state["results"]["operation-1"] = "old"
        with self.assertRaises(r.Blocked):
            self.run_reconcile()

    def test_reconciliation_does_not_repeat_external_operation(self):
        calls = []
        def lookup(key):
            calls.append(("read", key))
            return self.good
        self.run_reconcile(lookup=lookup)
        self.assertEqual(calls, [("read", "operation-1")])

if __name__ == "__main__":
    unittest.main()
