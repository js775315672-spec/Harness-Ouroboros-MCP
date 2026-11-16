"""Offline P1d eight-report aggregator and anti-forgery tests."""
from pathlib import Path
import copy
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import self_evolution_eight_distinct as worker
import self_evolution_p1d_aggregate as summary

HEAD="a"*40
CONF=ROOT/"configs/self-evolution-8lanes.json"
CODE="def solve(data):\n    return None\n"


def records():
    originals=[]
    proofs=[]
    for lane in worker.TASKS:
        contract,_,_=worker.context(ROOT,CONF,lane,HEAD)
        h=worker.sha(CODE.encode())
        originals.append({**contract,"model_calls":1,"raw_response":CODE,
                          "response_sha256":h,
                          "candidate_sha256":h,
                          "outcome":"candidate_passed",
                          "grade":{"status":"candidate_passed"}})
        proofs.append({"lane":lane,"status":"replayed_candidate",
                       "passed":True,"candidate_sha256":h,
                       "merge_authorized":False})
    return originals,proofs


class P1dAggregateTests(unittest.TestCase):
    def summarize(self,mutate=None):
        m,p=records()
        if mutate:
            mutate(m,p)
        return summary.aggregate(ROOT,CONF,HEAD,m,p)

    def reject(self,mutate):
        with self.assertRaises(ValueError):
            self.summarize(mutate)

    def test_identical_source_is_one_unique_candidate(self):
        result=self.summarize()
        self.assertEqual(result["fresh_model_calls"],8)
        self.assertEqual(result["candidate_passes"],8)
        self.assertEqual(result["unique_passing_source_sha256"],1)
        self.assertEqual(result["recursive_parent_promotions"],0)
        self.assertFalse(result["architecture_diversity_proven"])

    def test_one_failure_not_a_pass(self):
        def change(m,p):
            m[0]["outcome"]="candidate_failed"
            m[0]["grade"]={"status":"candidate_failed"}
            p[0]["passed"]=False
        result=self.summarize(change)
        self.assertEqual(result["candidate_passes"],7)

    def test_static_rejection_not_a_pass(self):
        def change(m,p):
            invalid="this is not a Python function"
            m[0]["raw_response"]=invalid
            m[0]["response_sha256"]=worker.sha(invalid.encode())
            m[0]["outcome"]="ast_rejected"
            m[0]["candidate_sha256"]=None
            m[0]["grade"]=None
            p[0].update(status="replayed_ast_rejection",candidate_sha256=None,
                        passed=False)
        result=self.summarize(change)
        self.assertEqual(result["candidate_passes"],7)

    def test_forged_success_rejected(self):
        self.reject(lambda m,p:p[0].update(passed=False))

    def test_changed_model_call_count_rejected(self):
        self.reject(lambda m,p:m[0].update(model_calls=0))

    def test_tampered_raw_source_rejected(self):
        self.reject(lambda m,p:m[0].update(raw_response="new fake source"))

    def test_swapped_task_sha_rejected(self):
        self.reject(lambda m,p:m[0].update(task_sha256="f"*64))

    def test_wrong_commit_rejected(self):
        self.reject(lambda m,p:m[0].update(source_sha="f"*40))

    def test_extra_authority_rejected(self):
        self.reject(lambda m,p:m[0].update(merge_authorized=True))

    def test_parent_promotion_rejected(self):
        self.reject(lambda m,p:m[0].update(recursive_parent_promotions=1))

    def test_replay_hash_mismatch_rejected(self):
        self.reject(lambda m,p:p[0].update(candidate_sha256="f"*64))

    def test_duplicate_lane_rejected(self):
        self.reject(lambda m,p:m[1].update(lane="01"))

    def test_fewer_lanes_rejected(self):
        m,p=records()
        with self.assertRaises(ValueError):
            summary.aggregate(ROOT,CONF,HEAD,m[:7],p)

    def test_unreplayed_success_rejected(self):
        self.reject(lambda m,p:p[1].update(status="runner_green"))

    def test_all_distinct_source_hashes_counted_but_not_architecture(self):
        def change(m,p):
            for i in range(8):
                raw="def solve(data):\n    return "+str(i)+"\n"
                h=worker.sha(raw.encode())
                m[i]["raw_response"]=raw
                m[i]["response_sha256"]=h
                m[i]["candidate_sha256"]=h
                p[i]["candidate_sha256"]=h
        r=self.summarize(change)
        self.assertEqual(r["unique_passing_source_sha256"],8)
        self.assertFalse(r["architecture_diversity_proven"])


if __name__=="__main__":
    unittest.main()
