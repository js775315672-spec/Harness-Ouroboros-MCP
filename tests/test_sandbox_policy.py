import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from sandbox_policy import policy
from task_selector import select
class SandboxPolicyTests(unittest.TestCase):
    def test_read_only_manifest(self):
        result=policy(select(),"agent/cycle-1-baseline")
        self.assertEqual(result["github_token_permissions"],{"contents":"read"})
        self.assertFalse(result["execution_enabled"])
        self.assertEqual(result["isolation_status"],"policy_only_not_a_sandbox")
    def test_write_token_denied(self):
        with self.assertRaises(ValueError):
            policy(select(),"agent/cycle-1-baseline",{"contents":"write"})
    def test_extra_permission_denied(self):
        with self.assertRaises(ValueError):
            policy(select(),"agent/cycle-1-baseline",{"contents":"read","pull-requests":"write"})
    def test_empty_permissions_denied(self):
        with self.assertRaises(ValueError):
            policy(select(),"agent/cycle-1-baseline",{})
    def test_unsafe_branch_denied(self):
        with self.assertRaises(ValueError):
            policy(select(),"main")
    def test_merge_still_human_approved(self):
        self.assertTrue(policy(select(),"agent/cycle-1-baseline")["human_merge_approval_required"])
if __name__=="__main__":unittest.main()
