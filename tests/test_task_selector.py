import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from task_selector import select,TASKS
class TaskSelectorTests(unittest.TestCase):
    def test_first_task(self):
        result=select()
        self.assertEqual(result["cycle"],1)
        self.assertEqual(result["phase"],"baseline")
        self.assertFalse(result["coding_agent_connected"])
        self.assertFalse(result["writes_allowed"])
    def test_all_phases_have_distinct_tasks(self):
        tasks=[select(i)["task"] for i in range(8)]
        self.assertEqual(len(set(tasks)),8)
        self.assertEqual(len(TASKS),8)
    def test_stop_at_ceiling(self):
        self.assertEqual(select(30,target=30,ceiling=30)["decision"],"stop")
    def test_invalid_limits_fail(self):
        with self.assertRaises(ValueError):select(-1)
    def test_merge_requires_human(self):
        self.assertTrue(select()["requires_human_merge_approval"])
if __name__=="__main__":unittest.main()
