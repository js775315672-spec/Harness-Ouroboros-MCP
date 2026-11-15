import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from feedback_controller import feedback
from task_selector import select
def checks(failed=()):
    return {name:{"status":"fail" if name in failed else "pass","log":"failure detail" if name in failed else ""} for name in ("harness","ouroboros","regression","secrets")}
class FeedbackTests(unittest.TestCase):
    def test_failed_check_requests_fix(self):
        result=feedback(select(),checks(("regression",)))
        self.assertEqual(result["decision"],"request_fix")
        self.assertEqual(result["failed_checks"],["regression"])
        self.assertFalse(result["model_call_performed"])
    def test_all_pass_requires_review(self):
        self.assertEqual(feedback(select(),checks())["decision"],"review")
    def test_retry_budget_stops(self):
        self.assertEqual(feedback(select(),checks(("harness",)),attempt=5)["decision"],"stop")
    def test_missing_check_blocks(self):
        with self.assertRaises(ValueError):feedback(select(),{"harness":{"status":"pass","log":""}})
    def test_oversized_log_blocks(self):
        evidence=checks(("secrets",))
        evidence["secrets"]["log"]="x"*4001
        with self.assertRaises(ValueError):feedback(select(),evidence)
    def test_invalid_attempt_blocks(self):
        with self.assertRaises(ValueError):feedback(select(),checks(),attempt=0)
    def test_invalid_status_blocks(self):
        evidence=checks()
        evidence["harness"]["status"]="unknown"
        with self.assertRaises(ValueError):feedback(select(),evidence)
    def test_stopped_task_blocks(self):
        with self.assertRaises(ValueError):feedback(select(30,target=30,ceiling=30),checks())
if __name__=="__main__":unittest.main()
