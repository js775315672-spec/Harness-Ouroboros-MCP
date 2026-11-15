import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from agent_runner import prepare
from task_selector import select
class AgentRunnerTests(unittest.TestCase):
    def test_dry_run_is_not_execution(self):
        r=prepare(select(),"agent/cycle-1-baseline")
        self.assertFalse(r["execution_attempted"])
        self.assertEqual(r["execution_status"],"dry_run")
    def test_command_never_runs(self):
        r=prepare(select(),"agent/cycle-1-baseline",command=["python3","-V"])
        self.assertFalse(r["execution_attempted"])
        self.assertEqual(r["execution_status"],"blocked")
    def test_execution_permission_denied(self):
        with self.assertRaises(ValueError):
            prepare(select(),"agent/cycle-1-baseline",allow_execution=True)
    def test_reject_invalid_timeout(self):
        for n in (0,-1,301,True):
            with self.subTest(n=n),self.assertRaises(ValueError):
                prepare(select(),"agent/cycle-1-baseline",timeout=n)
    def test_reject_unsafe_command(self):
        for cmd in ([],[""],"echo hi",[None]):
            with self.subTest(cmd=cmd),self.assertRaises(ValueError):
                prepare(select(),"agent/cycle-1-baseline",command=cmd)
    def test_reject_main_branch(self):
        with self.assertRaises(ValueError):
            prepare(select(),"main")
if __name__=="__main__":unittest.main()
