import importlib.util,json,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name):
    import sys
    sys.path.insert(0,str(ROOT/"scripts"))
    spec=importlib.util.spec_from_file_location(name,ROOT/"scripts"/(name+".py"))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
E=load("evaluation")
O=load("ouroboros")
class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        subprocess.run(["git","init","-q",str(self.root)],check=True)
        for name in ("HARNESS_POLICY.md","harness-policy.json","scripts/harness_check.py","scripts/governance.py","scripts/ouroboros.py"):
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text("safe")
        subprocess.run(["git","-C",str(self.root),"add","-A"],check=True)
        self.policy=ROOT/"harness-policy.json"
    def test_pass(self):
        self.assertEqual(E.evaluate_gates(self.root,self.policy)["outcome"],"pass")
    def test_block(self):
        p=self.root/"secrets"/"key.txt";p.parent.mkdir();p.write_text("fixture")
        subprocess.run(["git","-C",str(self.root),"add","-A"],check=True)
        r=E.evaluate_gates(self.root,self.policy)
        self.assertEqual(r["outcome"],"blocked")
        self.assertEqual(r["gates"]["boundaries"],"fail")
    def test_malformed_policy_fails_closed(self):
        bad=self.root/"bad.json";bad.write_text("{}")
        with self.assertRaises(ValueError):E.evaluate_gates(self.root,bad)
    def test_recover_rejects_symlink(self):
        record={"schema_version":1,"stage":"evaluate","outcome":"pass","note":"","commit":"a"*40,"timestamp":"2026-11-15T00:00:00+00:00","next_stage":"evolve","requires_human_merge_approval":True}
        target=self.root/"target.json";O.checkpoint(target,record)
        link=self.root/"link.json"
        link.symlink_to(target)
        with self.assertRaises(ValueError):O.recover(link)
        with self.assertRaises(ValueError):O.checkpoint(link,record)
    def test_recovery_rejects_oversize(self):
        p=self.root/"large.json";p.write_text("x"*65537)
        with self.assertRaises(ValueError):O.recover(p)
if __name__=="__main__":unittest.main()
