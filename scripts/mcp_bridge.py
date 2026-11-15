#!/usr/bin/env python3
"""Offline MCP-compatible JSON-RPC adapter for existing Harness evaluation.
No command execution, network access, repository writes, or automatic merge.
"""
import json
from evaluation import evaluate_gates
from pathlib import Path

VERSION="2025-06-18"
class Server:
    def __init__(self,root=None):
        self.root=Path(root or Path(__file__).resolve().parents[1])
        self.initialized=False
    def error(self,ident,code,message):
        return {"jsonrpc":"2.0","id":ident,"error":{"code":code,"message":message}}
    def handle(self,req):
        if not isinstance(req,dict) or req.get("jsonrpc")!="2.0" or not isinstance(req.get("method"),str):
            return self.error(None,-32600,"Invalid Request")
        if "id" in req and (type(req["id"]) not in (str,int)):
            return self.error(None,-32600,"Invalid Request")
        method=req["method"];ident=req.get("id")
        if "id" not in req:
            if method=="notifications/initialized" and self.initialized:return None
            return None
        params=req.get("params",{})
        if not isinstance(params,dict):return self.error(ident,-32602,"Invalid params")
        if method=="initialize":
            if self.initialized:return self.error(ident,-32600,"Already initialized")
            if set(params)-{"protocolVersion","capabilities","clientInfo"}:return self.error(ident,-32602,"Invalid params")
            if params.get("protocolVersion")!=VERSION or not isinstance(params.get("capabilities"),dict) or not isinstance(params.get("clientInfo"),dict):
                return self.error(ident,-32602,"Unsupported or incomplete handshake")
            self.initialized=True
            result={"protocolVersion":VERSION,"capabilities":{"tools":{"listChanged":False}},"serverInfo":{"name":"harness-readonly-bridge","version":"0.1.0"}}
        elif method=="ping":
            if params:return self.error(ident,-32602,"Unexpected params")
            result={}
        elif not self.initialized:
            return self.error(ident,-32002,"Server not initialized")
        elif method=="tools/list":
            if params:return self.error(ident,-32602,"Unexpected params")
            result={"tools":[{"name":"harness.evaluate","description":"Read-only eight-gate policy evaluation","inputSchema":{"type":"object","properties":{},"additionalProperties":False}}]}
        elif method=="tools/call":
            if set(params)!={"name","arguments"} or params["name"]!="harness.evaluate" or params["arguments"]!={}:
                return self.error(ident,-32602,"Unknown tool or invalid arguments")
            try:
                evaluation=evaluate_gates(self.root,self.root/"harness-policy.json")
                result={"content":[{"type":"text","text":json.dumps(evaluation,sort_keys=True)}],"isError":evaluation["outcome"]!="pass"}
            except (OSError,ValueError,UnicodeError) as exc:
                result={"content":[{"type":"text","text":"Policy evaluation blocked: "+type(exc).__name__}],"isError":True}
        else:return self.error(ident,-32601,"Method not found")
        return {"jsonrpc":"2.0","id":ident,"result":result}
def main():
    import sys
    server=Server()
    for line in sys.stdin:
        if len(line)>65536:
            print(json.dumps(server.error(None,-32700,"Input too large")),flush=True);continue
        try:
            def no_duplicates(pairs):
                out={}
                for k,v in pairs:
                    if k in out:raise ValueError("duplicate key")
                    out[k]=v
                return out
            req=json.loads(line,object_pairs_hook=no_duplicates,parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid constant")))
            reply=server.handle(req)
        except (ValueError,RecursionError):
            reply=server.error(None,-32700,"Parse error")
        if reply is not None:print(json.dumps(reply,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
