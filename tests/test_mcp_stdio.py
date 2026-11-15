"""Subprocess stdio protocol smoke tests: real JSON-RPC framing and process lifecycle."""
import json,subprocess,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SERVER=ROOT/"scripts"/"mcp_bridge.py"
def invoke(messages):
    payload="".join(json.dumps(m)+"\n" for m in messages)
    return subprocess.run([sys.executable,str(SERVER)],input=payload,text=True,capture_output=True,timeout=10,cwd=ROOT)
class StdioTests(unittest.TestCase):
    def handshake(self):
        return {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}
    def test_handshake_list_and_evaluate(self):
        messages=[self.handshake(),{"jsonrpc":"2.0","method":"notifications/initialized"},
          {"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}},
          {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"harness.evaluate","arguments":{}}}]
        result=invoke(messages)
        self.assertEqual(result.returncode,0,result.stderr)
        replies=[json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(replies),3)
        self.assertEqual(replies[0]["result"]["protocolVersion"],"2025-06-18")
        names=[tool["name"] for tool in replies[1]["result"]["tools"]]
        self.assertIn("harness.evaluate",names)
        self.assertIn("ouroboros.recover_latest",names)
        self.assertFalse(replies[2]["result"]["isError"])
    def test_malformed_json_fails_closed(self):
        result=subprocess.run([sys.executable,str(SERVER)],input="{broken\n",text=True,capture_output=True,timeout=10,cwd=ROOT)
        self.assertEqual(json.loads(result.stdout)["error"]["code"],-32700)
    def test_no_executable_tool(self):
        result=invoke([self.handshake(),{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"run","arguments":{}}}])
        replies=[json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(replies[1]["error"]["code"],-32602)
    def test_recovery_without_journal_fails_closed(self):
        result=invoke([self.handshake(),{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"ouroboros.recover_latest","arguments":{}}}])
        replies=[json.loads(line) for line in result.stdout.splitlines()]
        self.assertTrue(replies[1]["result"]["isError"])
if __name__=="__main__":unittest.main()
