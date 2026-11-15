import importlib.util,json,sys,tempfile,unittest,subprocess
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from mcp_bridge import Server,VERSION
class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.server=Server(ROOT)
    def request(self,method,params=None,ident=1):
        return self.server.handle({"jsonrpc":"2.0","id":ident,"method":method,"params":params or {}})
    def initialize(self):
        return self.request("initialize",{"protocolVersion":VERSION,"capabilities":{},"clientInfo":{"name":"test","version":"1"}})
    def test_uninitialized_denied(self):
        self.assertEqual(self.request("tools/list")["error"]["code"],-32002)
    def test_initialize_and_list(self):
        self.assertIn("result",self.initialize())
        self.assertEqual(self.request("tools/list")["result"]["tools"][0]["name"],"harness.evaluate")
    def test_evaluate(self):
        self.initialize()
        response=self.request("tools/call",{"name":"harness.evaluate","arguments":{}})
        self.assertFalse(response["result"]["isError"])
    def test_git_failure_returns_tool_error(self):
        self.initialize()
        with patch('mcp_bridge.evaluate_gates',side_effect=subprocess.CalledProcessError(1,['git'])):
            response=self.request('tools/call',{'name':'harness.evaluate','arguments':{}})
        self.assertTrue(response['result']['isError'])
    def test_recovery_missing_history_blocks(self):
        self.initialize()
        response=self.request("tools/call",{"name":"ouroboros.recover_latest","arguments":{}})
        self.assertTrue(response["result"]["isError"])
    def test_recovery_commit_bound(self):
        self.initialize()
        record={"schema_version":1,"stage":"evaluate","outcome":"pass","note":"","commit":"a"*40,"timestamp":"2026-11-15T00:00:00+00:00","next_stage":"evolve","requires_human_merge_approval":True}
        with patch("mcp_bridge.subprocess.run") as git,patch("mcp_bridge.recover_latest",return_value=record) as recover:
            git.return_value.stdout="a"*40+"\\n"
            response=self.request("tools/call",{"name":"ouroboros.recover_latest","arguments":{}})
        self.assertFalse(response["result"]["isError"])
        self.assertEqual(recover.call_args.kwargs["expected_commit"],"a"*40)
    def test_recovery_rejects_arbitrary_path(self):
        self.initialize()
        response=self.request("tools/call",{"name":"ouroboros.recover_latest","arguments":{"path":"/tmp/other"}})
        self.assertEqual(response["error"]["code"],-32602)
    def test_unknown_tool(self):
        self.initialize()
        self.assertEqual(self.request("tools/call",{"name":"run","arguments":{}})["error"]["code"],-32602)
    def test_notification_no_response(self):
        self.assertIsNone(self.server.handle({"jsonrpc":"2.0","method":"notifications/initialized"}))
    def test_no_unexpected_arguments(self):
        self.initialize()
        self.assertEqual(self.request("tools/call",{"name":"harness.evaluate","arguments":{"execute":True}})["error"]["code"],-32602)
    def test_bad_handshake(self):
        self.assertEqual(self.request("initialize",{"protocolVersion":"bad","capabilities":{},"clientInfo":{}})["error"]["code"],-32602)
if __name__=="__main__":unittest.main()
