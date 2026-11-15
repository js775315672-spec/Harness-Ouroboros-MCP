import json, pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from development_ledger import validate
def record(i,commit):
    return {"cycle":i,"commit":commit,"change":"Add a tested feature","checks":{"harness":"pass","ouroboros":"pass","regression":"pass","secrets":"pass"},"fixes":[],"ci_url":"https://github.com/org/repo/actions/runs/123"}
class LedgerTests(unittest.TestCase):
    def test_distinct_verified_cycles(self):
        self.assertEqual(validate([record(1,"a"*40),record(2,"b"*40)]),2)
    def test_duplicate_commit_rejected(self):
        with self.assertRaises(ValueError):validate([record(1,"a"*40),record(2,"a"*40)])
    def test_failed_check_rejected(self):
        r=record(1,"a"*40);r["checks"]["regression"]="fail"
        with self.assertRaises(ValueError):validate([r])
    def test_missing_ci_rejected(self):
        r=record(1,"a"*40);r["ci_url"]=""
        with self.assertRaises(ValueError):validate([r])
    def test_cycle_number_gap_rejected(self):
        with self.assertRaises(ValueError):validate([record(2,"a"*40)])
    def test_empty_change_rejected(self):
        r=record(1,"a"*40);r["change"]=" "
        with self.assertRaises(ValueError):validate([r])
if __name__=="__main__":unittest.main()
