import sys,tempfile,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from ast_policy import check_ast
class AstPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        subprocess.run(["git","init","-q",str(self.root)],check=True)
        (self.root/"scripts").mkdir()
        self.path=self.root/"scripts"/"demo.py"
        self.rules=[{"from":"scripts/","import":"production_trading"}]
    def scan(self,source):
        self.path.write_text(source)
        subprocess.run(["git","-C",str(self.root),"add","-A"],check=True)
        return check_ast(self.root,self.rules)
    def test_import(self):self.assertTrue(self.scan("import production_trading"))
    def test_from_import(self):self.assertTrue(self.scan("from production_trading.api import order"))
    def test_alias_import(self):self.assertTrue(self.scan("import production_trading as pt"))
    def test_comments_not_import(self):self.assertFalse(self.scan("# import production_trading"))
    def test_syntax_error_blocks(self):self.assertTrue(self.scan("def broken("))
    def test_safe(self):self.assertFalse(self.scan("import pathlib"))
if __name__=="__main__":unittest.main()
