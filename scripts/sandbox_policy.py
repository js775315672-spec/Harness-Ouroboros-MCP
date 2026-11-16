#!/usr/bin/env python3
"""Fail-closed GitHub Actions sandbox policy for future coding agents.

A policy manifest is not an execution sandbox; no commands are launched.
"""
import argparse,json,pathlib,sys
from agent_handoff import handoff
from task_selector import select

def policy(proposal, branch, workflow_permissions=None):
    contract = handoff(proposal, branch)
    if workflow_permissions is not None:
        if (type(workflow_permissions) is not dict
                or workflow_permissions != {"contents": "read"}):
            raise ValueError("runner must have read-only GitHub token permissions")
    # Return a fresh, exact built-in dictionary, never the caller-owned object.
    # This prevents postvalidation aliasing and malicious dict-subclass equality.
    permissions = {"contents": "read"}
    return {"cycle": contract["cycle"], "branch": branch,
            "execution_enabled": False, "github_token_permissions": permissions,
            "checkout_persist_credentials": False,
            "shell_execution_allowed": False,
            "external_agent_connected": False,
            "network_writes_allowed": False, "secrets_allowed": False,
            "paid_api_allowed": False, "live_trading_allowed": False,
            "human_merge_approval_required": True,
            "isolation_status": "policy_only_not_a_sandbox"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--completed",type=int,default=0)
    p.add_argument("--branch",required=True)
    p.add_argument("--output",type=pathlib.Path)
    args=p.parse_args()
    try:
        result=policy(select(args.completed),args.branch)
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    except (ValueError,OSError) as exc:
        print("BLOCK:",str(exc),file=sys.stderr);return 2
    print(json.dumps(result,sort_keys=True));return 0
if __name__=="__main__":sys.exit(main())
