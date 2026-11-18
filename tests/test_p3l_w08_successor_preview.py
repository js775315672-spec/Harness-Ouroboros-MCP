"""W08 successor must remain a proposal until W07 real promotion approved."""
import pathlib,sys,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import p3l_w08_successor_preview as w08
def review():
    return {"schema":"p3l-w07-review-only-v1",
            "decision":"await_verified_commit_ci_and_user_approval",
            "active_commit":"a"*40,"proposed_commit":"b"*40,
            "promotion_performed":False,"candidate_active":False,
            "w08_handoff_authorized":False,"merge_authorized":False}

class W08SuccessorTests(unittest.TestCase):
    def test_preview_is_not_autonomous_development(self):
        result=w08.preview(review())
        self.assertEqual(result["decision"],"blocked_until_w07_authorized_activation")
        self.assertNotEqual(result["proposed_task_phase"],"ledger_validation")
        self.assertEqual(result["model_calls"],0)
        self.assertEqual(result["verified_development_cycles"],0)
        self.assertFalse(result["new_source_patch_submitted"])
        self.assertFalse(result["successor_task_started"])

    def test_unapproved_or_forged_promotion_is_blocked(self):
        for field,value in (("candidate_active",True),("promotion_performed",True),
                            ("w08_handoff_authorized",True),("merge_authorized",True)):
            r=review();r[field]=value
            with self.subTest(field=field):
                with self.assertRaises(ValueError):w08.preview(r)

    def test_no_credit_for_fake_development_cycle(self):
        with self.assertRaises(ValueError):w08.preview(review(),completed=1)
        with self.assertRaises(ValueError):w08.preview(review(),previous_task_id="other")
if __name__=="__main__":
    unittest.main()
