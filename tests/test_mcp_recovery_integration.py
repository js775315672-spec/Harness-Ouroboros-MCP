"""End-to-end MCP recovery tests using a real local git repository and journal."""
import json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from history import append
from mcp_bridge import Server,VERSION

class RecoveryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        subprocess.run(["git","init","-q",str(self.root)],check=True)
        (self.root/"README.md").write_text("fixture")
        subprocess.run(["git","-C",str(self.root),"-c","user.name=Test","-c","user.email=test@example.invalid","commit","--allow-empty","-qm","fixture"],check=True)
        self.head=subprocess.run(["git","-C",str(self.root),"rev-parse","HEAD"],capture_output=True,text=True,check=True).stdout.strip()
        self.server=Server(self.root)
        self.server.handle({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":VERSION,"capabilities":{},"clientInfo":{"name":"test"}}})
        self.path=self.root/"artifacts"/"ouroboros-history.json"
    def record(self,commit=None):
        return {"schema_version":1,"stage":"evaluate","outcome":"pass","note":"safe","commit":commit or self.head,
                "timestamp":"2026-11-15T00:00:00+00:00","next_stage":"evolve","requires_human_merge_approval":True}
    def call(self):
        return self.server.handle({"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"ouroboros.recover_latest","arguments":{}}})["result"]
    def test_verified_journal_recovers(self):
        append(self.path,self.record())
        result=self.call()
        self.assertFalse(result["isError"])
        self.assertEqual(json.loads(result["content"][0]["text"])["commit"],self.head)
    def test_tampered_journal_is_blocked(self):
        append(self.path,self.record())
        entries=json.loads(self.path.read_text())
        entries[0]["record"]["note"]="changed"
        self.path.write_text(json.dumps(entries))
        self.assertTrue(self.call()["isError"])
    def test_other_commit_is_blocked(self):
        append(self.path,self.record("a"*40))
        self.assertTrue(self.call()["isError"])
    def test_symlink_journal_is_blocked(self):
        target=self.root/"target.json"
        append(target,self.record())
        self.path.parent.mkdir()
        self.path.symlink_to(target)
        self.assertTrue(self.call()["isError"])
    def test_no_history_is_blocked(self):
        self.assertTrue(self.call()["isError"])
if __name__=="__main__":unittest.main()
