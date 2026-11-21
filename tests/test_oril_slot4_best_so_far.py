import unittest
from scripts.oril_slot4_best_so_far import select

def rec(n,score,reg=0,state="tested"):
    return dict(cycle_id=f"run-{n}",candidate_sha=f"{n:064x}",evidence_sha256=f"{n+10:064x}",public_correct=score,public_total=30,new_regressions=reg,token_saving_pct=40.0,review_state=state)

class TestPublicSelection(unittest.TestCase):
    def test_later_worse_candidate_not_best(self):
        r=select([rec(1,20),rec(2,27),rec(3,25)])
        self.assertEqual(r["public_best_cycle_id"],"run-2")
        self.assertFalse(r["promotion_allowed"])
    def test_rejected_excluded(self):
        self.assertEqual(select([rec(1,29,1,"rejected"),rec(2,20)])["public_best_cycle_id"],"run-2")
    def test_no_eligible(self):
        self.assertIsNone(select([rec(1,29,1,"rejected")])["public_best_cycle_id"])
    def test_duplicate(self):
        with self.assertRaises(ValueError): select([rec(1,20),rec(1,20)])
    def test_bad_digest(self):
        r=rec(1,20);r["candidate_sha"]="wrong"
        with self.assertRaises(ValueError): select([r])
    def test_nan(self):
        r=rec(1,20);r["token_saving_pct"]=float("nan")
        with self.assertRaises(ValueError): select([r])
    def test_extra_field(self):
        r=rec(1,20);r["private_grade"]="pass"
        with self.assertRaises(ValueError): select([r])
    def test_bool_count(self):
        r=rec(1,20);r["public_correct"]=True
        with self.assertRaises(ValueError): select([r])
    def test_tie_earliest(self):
        self.assertEqual(select([rec(1,20),rec(2,20)])["public_best_cycle_id"],"run-1")

if __name__=="__main__":unittest.main()
