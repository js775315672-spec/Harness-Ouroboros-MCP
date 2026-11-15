import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from ci_attestation import verify_record

SHA="a"*40
RECORD={"cycle":1,"commit":SHA,"ci_url":"https://github.com/org/repo/actions/runs/123"}
BASE={"status":"completed","conclusion":"success","html_url":RECORD["ci_url"],"repository":{"full_name":"org/repo"},"event":"pull_request","pull_requests":[{"head":{"sha":SHA}}]}
class AttestationTests(unittest.TestCase):
    def test_matching_successful_pr(self):
        self.assertTrue(verify_record(RECORD,lambda _:dict(BASE))["verified"])
    def test_failed_run_blocked(self):
        data=dict(BASE,conclusion="failure")
        with self.assertRaises(ValueError):verify_record(RECORD,lambda _:data)
    def test_wrong_commit_blocked(self):
        data=dict(BASE,pull_requests=[{"head":{"sha":"b"*40}}])
        with self.assertRaises(ValueError):verify_record(RECORD,lambda _:data)
    def test_wrong_repository_blocked(self):
        data=dict(BASE,repository={"full_name":"attacker/repo"})
        with self.assertRaises(ValueError):verify_record(RECORD,lambda _:data)
    def test_missing_pr_evidence_blocked(self):
        data=dict(BASE,pull_requests=[])
        with self.assertRaises(ValueError):verify_record(RECORD,lambda _:data)
    def test_push_commit_verified(self):
        data=dict(BASE,event="push",head_sha=SHA)
        self.assertTrue(verify_record(RECORD,lambda _:data)["verified"])
    def test_unsupported_trigger_blocked(self):
        data=dict(BASE,event="schedule")
        with self.assertRaises(ValueError):verify_record(RECORD,lambda _:data)
if __name__=="__main__":unittest.main()
