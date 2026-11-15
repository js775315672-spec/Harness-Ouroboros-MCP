import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
import development_coordinator

SHA='a'*40
RECORD={'cycle':1,'commit':SHA,'change':'implement feature','checks':{'harness':'pass','ouroboros':'pass','regression':'pass','secrets':'pass'},'fixes':[],'ci_url':'https://github.com/org/repo/actions/runs/123'}
CI={'status':'completed','conclusion':'success','html_url':RECORD['ci_url'],'repository':{'full_name':'org/repo'},'event':'pull_request','pull_requests':[{'head':{'sha':SHA}}]}
class CoordinatorTests(unittest.TestCase):
    def test_valid_attested_cycle_advances(self):
        result=development_coordinator.coordinate([RECORD],fetch=lambda _:dict(CI))
        self.assertEqual(result['verified_development_cycles'],1)
        self.assertEqual(result['next']['next_cycle'],2)
    def test_failed_ci_does_not_advance(self):
        with self.assertRaises(ValueError):
            development_coordinator.coordinate([RECORD],fetch=lambda _:dict(CI,conclusion='failure'))
    def test_commit_mismatch_does_not_advance(self):
        with self.assertRaises(ValueError):
            development_coordinator.coordinate([RECORD],fetch=lambda _:dict(CI,pull_requests=[{'head':{'sha':'b'*40}}]))
    def test_empty_ledger_proposes_first_real_change(self):
        result=development_coordinator.coordinate([])
        self.assertEqual(result["verified_development_cycles"],0)
        self.assertEqual(result["next"]["next_cycle"],1)
        self.assertFalse(result["autonomous_coding_connected"])
        self.assertEqual(result["proposed_task"]["phase"],"baseline")
        self.assertFalse(result["proposed_task"]["writes_allowed"])
    def test_no_fake_development_cycles_from_verification(self):
        result=development_coordinator.coordinate([])
        self.assertTrue(result["verification_repetitions_are_not_development_cycles"])
    def test_invalid_ledger_is_blocked(self):
        with self.assertRaises(ValueError):
            development_coordinator.coordinate([{"cycle":1}])
    def test_invalid_ceiling_is_blocked(self):
        with self.assertRaises(ValueError):
            development_coordinator.coordinate([],target=30,ceiling=1)
if __name__=="__main__":unittest.main()
