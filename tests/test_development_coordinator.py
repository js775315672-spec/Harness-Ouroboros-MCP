import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
import development_coordinator

class CoordinatorTests(unittest.TestCase):
    def test_empty_ledger_proposes_first_real_change(self):
        result=development_coordinator.coordinate([])
        self.assertEqual(result["verified_development_cycles"],0)
        self.assertEqual(result["next"]["next_cycle"],1)
        self.assertFalse(result["autonomous_coding_connected"])
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
