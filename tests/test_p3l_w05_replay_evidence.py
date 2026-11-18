"""W05 strict receipt provenance and independent replay safety tests."""
import hashlib,pathlib,sys,unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import p3l_w05_replay_evidence as w05
import p3l_w04_one_call_gate as w04

RAW="def validate(records):\n    return len(records)\n"
def sample():
    plan=w04.plan()
    old=w05.p3g.file_bytes(ROOT,w05.p3g.TARGET).decode()
    patched,diff=w05.p3g.patch_original(old,RAW)
    return {"schema":"p3l-w06-one-shot-output-v1","run_id":1234,
            "runner_role":"model_inference","model_calls":1,"model_id":"7b",
            "task_sha256":plan["task_sha256"],
            "prompt_sha256":plan["prompt_sha256"],
            "source_sha256":plan["source_sha256"],
            "model_config_sha256":plan["model_config_sha256"],
            "raw_response":RAW,
            "raw_response_sha256":hashlib.sha256(RAW.encode()).hexdigest(),
            "candidate_source_sha256":hashlib.sha256(patched.encode()).hexdigest(),
            "diff_sha256":hashlib.sha256(diff.encode()).hexdigest(),
            "merge_authorized":False}
def grade(ok):
    suites={name:{"tests_run":n,"passed":ok,"exit_code":0 if ok else 1}
            for name,n in w05.p3g.FROZEN_SUITES.items()}
    return {"status":"real_source_patch_passed" if ok else "real_source_patch_failed",
            "candidate":suites}

class W05ReplayTests(unittest.TestCase):
    def test_provenance_and_actual_suite_counts_required(self):
        with patch.object(w05.p3g,"grade",return_value=grade(True)) as runner:
            x=w05.replay(ROOT,sample(),1234)
        runner.assert_called_once()
        self.assertEqual(x["test_count"],25)
        self.assertTrue(x["candidate_passed"])
        self.assertFalse(x["merge_authorized"])

    def test_candidate_failed_is_not_success(self):
        with patch.object(w05.p3g,"grade",return_value=grade(False)):
            self.assertFalse(w05.replay(ROOT,sample(),1234)["candidate_passed"])

    def test_changed_raw_response_and_runner_are_rejected(self):
        for key,value in (("raw_response","def validate(records):\n    return 2\n"),
                          ("run_id",1235),("merge_authorized",True),
                          ("prompt_sha256","a"*64),("runner_role","independent_replay")):
            record=sample()
            record[key]=value
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    w05.replay(ROOT,record,1234)

    def test_boolean_model_call_count_is_not_one_real_call(self):
        record=sample()
        record["model_calls"]=True
        with patch.object(w05.p3g,"grade") as runner:
            with self.assertRaises(ValueError):
                w05.replay(ROOT,record,1234)
            runner.assert_not_called()

    def test_fractional_or_boolean_receipt_run_id_is_rejected(self):
        for bad in (True, 1234.0):
            record=sample()
            record["run_id"]=bad
            with self.subTest(bad=bad), patch.object(w05.p3g,"grade") as runner:
                with self.assertRaises(ValueError):
                    w05.replay(ROOT,record,1234)
                runner.assert_not_called()

    def test_boolean_or_fractional_docker_exit_code_is_not_success(self):
        # Python permits False == 0 and 0.0 == 0; neither is a real
        # integer process exit status from the isolated runner.
        for invalid in (False, 0.0, "0", None):
            evidence=grade(True)
            evidence["candidate"]["test_ci_attestation.py"]["exit_code"]=invalid
            with self.subTest(invalid=repr(invalid)), patch.object(w05.p3g,"grade",return_value=evidence):
                with self.assertRaisesRegex(ValueError,"invalid evidence types"):
                    w05.replay(ROOT,sample(),1234)

    def test_numeric_or_string_docker_passed_flag_is_not_boolean(self):
        for invalid in (1, 0, "true", "false"):
            evidence=grade(True)
            evidence["candidate"]["test_development_ledger.py"]["passed"]=invalid
            with self.subTest(invalid=repr(invalid)), patch.object(w05.p3g,"grade",return_value=evidence):
                with self.assertRaisesRegex(ValueError,"invalid evidence types"):
                    w05.replay(ROOT,sample(),1234)

    def test_missing_frozen_test_count_blocked(self):
        wrong=grade(True)
        wrong["candidate"]["heldout_p3f_development_ledger.py"]["tests_run"]=9
        with patch.object(w05.p3g,"grade",return_value=wrong):
            with self.assertRaises(ValueError):
                w05.replay(ROOT,sample(),1234)
    def test_malformed_source_rejected_before_grade(self):
        record=sample()
        raw="import os\ndef validate(records):\n    return len(records)\n"
        record["raw_response"]=raw
        record["raw_response_sha256"]=hashlib.sha256(raw.encode()).hexdigest()
        with patch.object(w05.p3g,"grade") as runner:
            with self.assertRaises(ValueError):
                w05.replay(ROOT,record,1234)
            runner.assert_not_called()
if __name__=="__main__":
    unittest.main()
