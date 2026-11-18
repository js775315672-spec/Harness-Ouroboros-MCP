"""W07 promotion/rollback review must never activate unreviewed candidate."""
import pathlib,sys,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import p3l_w07_promotion_review as w07

def receipt():
    return {"schema":"p3l-w05-independent-replay-v1","run_id":123,
            "runner_role":"independent_replay",
            "task_sha256":"a"*64,"source_sha256":"b"*64,
            "raw_response_sha256":"c"*64,"candidate_source_sha256":"d"*64,
            "diff_sha256":"e"*64,"test_count":25,
            "suites":{name:{"tests_run":n,"passed":True} for name,n in w07.FROZEN.items()},
            "candidate_passed":True,"independent_replay_completed":True,
            "merge_authorized":False,"promoted":False}

class W07ReviewTests(unittest.TestCase):
    def test_valid_receipt_still_cannot_promote(self):
        x=w07.review(receipt(),"a"*40,"b"*40)
        self.assertEqual(x["rollback_target_commit"],"a"*40)
        self.assertEqual(x["decision"],"await_verified_commit_ci_and_user_approval")
        self.assertFalse(x["candidate_active"])
        self.assertFalse(x["w08_handoff_authorized"])
        self.assertFalse(x["promotion_performed"])

    def test_same_active_and_candidate_blocked(self):
        with self.assertRaises(ValueError):w07.review(receipt(),"a"*40,"a"*40)

    def test_failures_and_missing_tests_block(self):
        for field,value in (("candidate_passed",False),("independent_replay_completed",False),
                            ("promoted",True),("test_count",24),("run_id",0)):
            x=receipt();x[field]=value
            with self.subTest(field=field):
                with self.assertRaises(ValueError):w07.review(x,"a"*40,"b"*40)
        x=receipt();del x["suites"]["heldout_p3f_development_ledger.py"]
        with self.assertRaises(ValueError):w07.review(x,"a"*40,"b"*40)
if __name__=="__main__":
    unittest.main()
