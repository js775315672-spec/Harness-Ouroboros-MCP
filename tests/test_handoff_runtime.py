import datetime,pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from handoff_runtime import measure
from task_selector import select
UTC=datetime.timezone.utc
class HandoffRuntimeTests(unittest.TestCase):
    def test_duration_is_monotonic_and_not_coding(self):
        times=iter([10.0,10.125])
        wall=iter([datetime.datetime(2026,1,1,tzinfo=UTC),datetime.datetime(2026,1,1,0,0,1,tzinfo=UTC)])
        result=measure(select(),"agent/cycle-1-baseline",clock=lambda:next(times),wall_clock=lambda:next(wall))
        self.assertEqual(result["elapsed_seconds"],0.125)
        self.assertEqual(result["code_changes"],0)
        self.assertFalse(result["actual_agent_execution"])
    def test_invalid_branch_blocks_timing(self):
        with self.assertRaises(ValueError):
            measure(select(),"main")
if __name__=="__main__":unittest.main()
