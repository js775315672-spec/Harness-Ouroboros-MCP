import copy
import unittest
from scripts.oril_slot2_cycle_chain_preflight import check

S = "a" * 40
T = "b" * 40
U = "c" * 40
def row(cid, pred, src, cand):
    return dict(cycle_id=cid, predecessor_id=pred, source_sha=src,
                candidate_sha=cand, memory_sha=U,
                model_run_url="https://github.com/a/b/actions/runs/123",
                independent_run_url="https://github.com/a/b/actions/runs/124")
class ChainTests(unittest.TestCase):
    def setUp(self):
        self.rows = [row("one", None, S, T), row("two", "one", T, U)]
    def test_valid(self):
        self.assertFalse(check(self.rows)["promotion_allowed"])
    def test_empty(self):
        with self.assertRaises(ValueError): check([])
    def test_duplicate(self):
        self.rows[1]["cycle_id"] = "one"
        with self.assertRaises(ValueError): check(self.rows)
    def test_predecessor(self):
        self.rows[1]["predecessor_id"] = None
        with self.assertRaises(ValueError): check(self.rows)
    def test_candidate_handoff(self):
        self.rows[1]["source_sha"] = S
        with self.assertRaises(ValueError): check(self.rows)
    def test_missing(self):
        del self.rows[0]["memory_sha"]
        with self.assertRaises(ValueError): check(self.rows)
    def test_fake_sha(self):
        self.rows[0]["candidate_sha"] = "xyz"
        with self.assertRaises(ValueError): check(self.rows)
    def test_same_run(self):
        self.rows[0]["independent_run_url"] = self.rows[0]["model_run_url"]
        with self.assertRaises(ValueError): check(self.rows)
    def test_non_github(self):
        self.rows[0]["model_run_url"] = "https://example.com/run"
        with self.assertRaises(ValueError): check(self.rows)
    def test_duplicate_ids_across_three(self):
        self.rows.append(row("one", "two", U, S))
        with self.assertRaises(ValueError): check(self.rows)
if __name__ == "__main__":
    unittest.main()
