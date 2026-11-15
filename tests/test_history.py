import importlib.util,json,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("history",ROOT/"scripts"/"history.py")
import sys
sys.path.insert(0,str(ROOT/"scripts"))
H=importlib.util.module_from_spec(spec);spec.loader.exec_module(H)
def record(stage="evaluate",commit="a"*40):
    return {"schema_version":1,"stage":stage,"outcome":"pass","note":"ok","commit":commit,
            "timestamp":"2026-11-15T00:00:00+00:00",
            "next_stage":"evolve" if stage=="evaluate" else "seed",
            "requires_human_merge_approval":True}
class JournalTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.path=Path(self.t.name)/"journal.json"
    def test_append_and_recover(self):
        H.append(self.path,record());H.append(self.path,record())
        self.assertEqual(len(H.read_history(self.path)),2)
        self.assertEqual(H.recover_latest(self.path,"a"*40)["stage"],"evaluate")
    def test_tamper_fails_closed(self):
        H.append(self.path,record())
        content=json.loads(self.path.read_text())
        content[0]["record"]["note"]="tampered"
        self.path.write_text(json.dumps(content))
        with self.assertRaises(ValueError):H.read_history(self.path)
    def test_wrong_commit(self):
        H.append(self.path,record())
        with self.assertRaises(ValueError):H.recover_latest(self.path,"b"*40)
        with self.assertRaises(ValueError):H.append(self.path,record(commit="b"*40))
    def test_broken_chain(self):
        H.append(self.path,record());H.append(self.path,record())
        content=json.loads(self.path.read_text());content[1]["previous_hash"]="bad"
        self.path.write_text(json.dumps(content))
        with self.assertRaises(ValueError):H.read_history(self.path)
    def test_symlink(self):
        target=Path(self.t.name)/"target.json";H.append(target,record())
        self.path.symlink_to(target)
        with self.assertRaises(ValueError):H.append(self.path,record())
        with self.assertRaises(ValueError):H.read_history(self.path)
    def test_empty(self):
        with self.assertRaises(ValueError):H.recover_latest(self.path)
    def test_corrupted_json(self):
        self.path.write_text("{")
        with self.assertRaises(ValueError):H.read_history(self.path)
if __name__=="__main__":unittest.main()
