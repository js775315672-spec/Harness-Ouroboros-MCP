import json
import pathlib
import tempfile
import unittest

from scripts.review_decision_gate import decision,_load

def good():
    inference={"status":"accepted_for_review","real_model_calls":1,
               "patch_applied":False,"merge_authorized":False,
               "full_harness_passed":False,"source_sha256":"abc"}
    run={"tests_passed":True,"tests_run":9,
         "network_disabled":True,"filesystem_read_only":True}
    regression={"status":"isolated_regression_passed",
                "patch_applied_to_checkout":False,"merge_authorized":False,
                "full_harness_passed":False,
                "provenance":{"provenance_verified":True,
                              "model_response_replayed":True,
                              "real_model_calls":1,"source_sha256":"abc"},
                "candidate_detects_previously_missed_mutant":True,
                "executed_only_string_literal_change":True,
                "baseline":dict(run),"candidate":dict(run),
                "baseline_negative_control":{"mutant_detected":False,
                                            "probe_in_isolated_container":True},
                "candidate_negative_control":{"mutant_detected":True,
                                             "probe_in_isolated_container":True}}
    return inference,regression

class ReviewDecisionTests(unittest.TestCase):
    def test_all_checks_pass_still_only_human_review(self):
        a,b=good()
        result=decision(a,b)
        self.assertEqual(result["decision"],"ready_for_human_review")
        self.assertFalse(result["merge_authorized"])
        self.assertFalse(result["model_patch_applied"])
        self.assertFalse(result["independent_github_ci_attested"])

    def test_rejects_missing_or_failed_checks(self):
        cases=[
            lambda a,b:a.update(status="rejected"),
            lambda a,b:a.update(real_model_calls=True),
            lambda a,b:a.update(patch_applied=True),
            lambda a,b:b.update(status="regression_failed"),
            lambda a,b:b.update(merge_authorized=True),
            lambda a,b:b.update(provenance={}),
            lambda a,b:b["provenance"].update(model_response_replayed=False),
            lambda a,b:b["provenance"].update(source_sha256="forged"),
            lambda a,b:b.update(candidate_detects_previously_missed_mutant=False),
            lambda a,b:b.update(executed_only_string_literal_change=False),
            lambda a,b:b["candidate"].update(tests_passed=False),
            lambda a,b:b["baseline"].update(tests_run=0),
            lambda a,b:b["candidate"].update(tests_run=10),
            lambda a,b:b["candidate"].update(network_disabled=False),
            lambda a,b:b["candidate_negative_control"].update(mutant_detected=False),
            lambda a,b:b["baseline_negative_control"].update(probe_in_isolated_container=False),
        ]
        for i,change in enumerate(cases):
            with self.subTest(case=i):
                a,b=good()
                change(a,b)
                with self.assertRaises(ValueError):
                    decision(a,b)

    def test_reject_duplicate_json_evidence_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=pathlib.Path(tmp)/"evidence.json"
            p.write_text('{"status":"pass","status":"fail"}',encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"duplicate"):
                _load(p)

    def test_reject_non_object_and_oversize(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=pathlib.Path(tmp)/"evidence.json"
            for payload in ('[]','"text"',"x"*120001):
                p.write_text(payload,encoding="utf-8")
                with self.assertRaises(ValueError):
                    _load(p)
