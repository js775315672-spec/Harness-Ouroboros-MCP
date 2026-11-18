"""W05 replay result -> W07 review -> W08 fail-closed successor handoff."""
import pathlib
import sys
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import p3l_w07_promotion_review as w07
import p3l_w08_successor_preview as w08

def synthetic_w05_receipt(passed=True):
    return {
        "schema":"p3l-w05-independent-replay-v1",
        "run_id":1234,
        "runner_role":"independent_replay",
        "task_sha256":"a"*64,
        "source_sha256":"b"*64,
        "raw_response_sha256":"c"*64,
        "candidate_source_sha256":"d"*64,
        "diff_sha256":"e"*64,
        "test_count":25,
        "suites":{name:{"tests_run":count,"passed":passed}
                  for name,count in w07.FROZEN.items()},
        "candidate_passed":passed,
        "independent_replay_completed":True,
        "merge_authorized":False,
        "promoted":False,
    }

class W05W07W08IntegrationTests(unittest.TestCase):
    def test_synthetic_green_evidence_is_only_review_not_promotion(self):
        review=w07.review(synthetic_w05_receipt(),"a"*40,"b"*40)
        handoff=w08.preview(review)
        self.assertFalse(review["promotion_performed"])
        self.assertEqual(handoff["decision"],"blocked_until_w07_authorized_activation")
        self.assertEqual(handoff["current_active_sha"],"a"*40)
        self.assertEqual(handoff["unapproved_candidate_sha"],"b"*40)
        self.assertFalse(handoff["new_source_patch_submitted"])
        self.assertFalse(handoff["successor_task_started"])

    def test_red_evidence_cannot_advance_to_w08(self):
        with self.assertRaises(ValueError):
            w07.review(synthetic_w05_receipt(False),"a"*40,"b"*40)

    def test_forged_w07_approval_cannot_trigger_new_task(self):
        review=w07.review(synthetic_w05_receipt(),"a"*40,"b"*40)
        review["w08_handoff_authorized"]=True
        with self.assertRaises(ValueError):
            w08.preview(review)

if __name__=="__main__":
    unittest.main()
