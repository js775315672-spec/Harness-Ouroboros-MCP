import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from task_selector import select
from agent_handoff import handoff
class AgentHandoffTests(unittest.TestCase):
    def test_valid_isolated_branch(self):
        result=handoff(select(0),"agent/cycle-1-baseline")
        self.assertEqual(result["mode"],"handoff_only")
        self.assertFalse(result["network_writes"])
        self.assertTrue(result["human_merge_approval_required"])
    def test_reject_main_branch(self):
        with self.assertRaises(ValueError):handoff(select(0),"main")
    def test_reject_cycle_mismatch(self):
        with self.assertRaises(ValueError):handoff(select(0),"agent/cycle-2-baseline")
    def test_reject_path_injection(self):
        with self.assertRaises(ValueError):handoff(select(0),"agent/cycle-1-../../main")
    def test_reject_write_enabled_proposal(self):
        proposal=dict(select(0),writes_allowed=True)
        with self.assertRaises(ValueError):handoff(proposal,"agent/cycle-1-baseline")
    def test_reject_no_merge_approval(self):
        proposal=dict(select(0),requires_human_merge_approval=False)
        with self.assertRaises(ValueError):handoff(proposal,"agent/cycle-1-baseline")
    def test_reject_stopped_cycle(self):
        with self.assertRaises(ValueError):handoff(select(30,target=30,ceiling=30),"agent/cycle-31-baseline")
if __name__=="__main__":unittest.main()
