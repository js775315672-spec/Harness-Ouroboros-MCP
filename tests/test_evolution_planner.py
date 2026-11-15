import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from evolution_planner import plan
class EvolutionPlannerTests(unittest.TestCase):
    def test_first_cycle(self):
        self.assertEqual(plan(0)["next_cycle"],1)
    def test_progress_after_target(self):
        self.assertEqual(plan(30)["next_cycle"],31)
    def test_ceiling(self):
        self.assertEqual(plan(10000)["decision"],"stop")
    def test_stagnation_after_target(self):
        self.assertEqual(plan(40,stagnation=20)["reason"],"no measured improvement")
    def test_no_early_stagnation_stop(self):
        self.assertEqual(plan(10,stagnation=20)["decision"],"propose")
    def test_over_ceiling_rejected(self):
        with self.assertRaises(ValueError):plan(0,ceiling=10001)
    def test_completed_count_over_ceiling_rejected(self):
        with self.assertRaises(ValueError):plan(10001)
    def test_completed_count_over_custom_ceiling_rejected(self):
        with self.assertRaises(ValueError):plan(101,target=30,ceiling=100)
    def test_invalid_target_rejected(self):
        with self.assertRaises(ValueError):plan(0,target=0)
    def test_human_approval_required(self):
        self.assertIs(plan(0)["requires_human_merge_approval"],True)
if __name__=="__main__":unittest.main()
