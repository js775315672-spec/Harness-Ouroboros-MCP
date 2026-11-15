import importlib.util,json,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/"scripts"/(name+".py"))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
G=load("governance");O=load("ouroboros")
class Gates(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.root=Path(self.t.name)
        subprocess.run(["git","init","-q",str(self.root)],check=True)
        for name in ("HARNESS_POLICY.md","scripts/harness_check.py"):
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text("safe")
        self.add()
        self.cfg=json.loads((ROOT/"harness-policy.json").read_text())
    def add(self):subprocess.run(["git","-C",str(self.root),"add","-A"],check=True)
    def test_eight_gates(self):
        result=G.check(self.root,self.cfg)
        self.assertEqual(len(result),8);self.assertFalse(any(result.values()))
    def test_boundary(self):
        p=self.root/"secrets"/"a";p.parent.mkdir();p.write_text("x");self.add()
        self.assertTrue(G.check(self.root,self.cfg)["boundaries"])
    def test_layers(self):
        self.cfg["layers"]["forbidden_imports"]=[{"from":"app/","import":"blocked"}]
        p=self.root/"app"/"x.py";p.parent.mkdir();p.write_text("import blocked");self.add()
        self.assertTrue(G.check(self.root,self.cfg)["layers"])
    def test_secrets(self):
        (self.root/"scripts/harness_check.py").unlink();self.add()
        self.assertTrue(G.check(self.root,self.cfg)["secrets"])
    def test_security(self):
        self.cfg["security"]["forbidden_patterns"]=["dangerous_call"]
        (self.root/"x.py").write_text("dangerous_call");self.add()
        self.assertTrue(G.check(self.root,self.cfg)["security"])
    def test_structure(self):
        self.cfg["structure"]["required_files"]=["MISSING"]
        self.assertTrue(G.check(self.root,self.cfg)["structure"])
    def test_spec(self):
        self.cfg["spec"]["required_files"]=["TRD.md"]
        self.assertTrue(G.check(self.root,self.cfg)["spec"])
    def test_deps(self):
        (self.root/".env").write_text("x");self.add()
        self.assertTrue(G.check(self.root,self.cfg)["deps"])
    def test_mutation(self):
        p=self.root/"production-secrets"/"a";p.parent.mkdir();p.write_text("x");self.add()
        self.assertTrue(G.check(self.root,self.cfg)["mutation"])
    def test_checkpoint(self):
        p=self.root/"checkpoint.json";O.checkpoint(p,{"stage":"evaluate"})
        self.assertEqual(json.loads(p.read_text())["stage"],"evaluate")
    def test_invalid_stage(self):
        with self.assertRaises(ValueError):O.evaluate(self.root,"merge","pass","")
if __name__=="__main__":unittest.main()
