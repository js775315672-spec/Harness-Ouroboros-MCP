#!/usr/bin/env python3
"""Validate a coding-agent handoff without granting repository write privileges."""
import argparse,json,pathlib,re,sys
from task_selector import select

SAFE_BRANCH=re.compile(r"^agent/cycle-[1-9][0-9]*-[a-z0-9][a-z0-9-]{0,40}$")
def handoff(proposal, branch):
    if not isinstance(proposal, dict) or proposal.get("decision") != "propose":
        raise ValueError("no proposed development task")
    cycle = proposal.get("cycle")
    if type(cycle) is not int or cycle < 1:
        raise ValueError("invalid cycle")
    if not isinstance(branch, str) or not SAFE_BRANCH.fullmatch(branch) or not branch.startswith(f"agent/cycle-{cycle}-"):
        raise ValueError("unsafe or mismatched isolated branch")
    if proposal.get("coding_agent_connected") is not False or proposal.get("writes_allowed") is not False:
        raise ValueError("proposal must be read-only")
    if proposal.get("requires_human_merge_approval") is not True:
        raise ValueError("human merge approval required")
    task = proposal.get("task")
    if (not isinstance(task, str)
            or not task.strip()
            or task != task.strip()
            or len(task.encode("utf-8")) > 240
            or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in task)):
        raise ValueError("invalid task")
    return {"cycle": cycle, "task": task, "isolated_branch": branch,
            "mode": "handoff_only", "network_writes": False, "secrets_allowed": False,
            "paid_api_allowed": False, "live_trading_allowed": False,
            "human_merge_approval_required": True,
            "status": "awaiting_external_coding_agent"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--completed",type=int,default=0)
    p.add_argument("--branch",required=True)
    p.add_argument("--output",type=pathlib.Path)
    args=p.parse_args()
    try:
        result=handoff(select(args.completed),args.branch)
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    except (ValueError,OSError) as exc:
        print("BLOCK:",str(exc),file=sys.stderr);return 2
    print(json.dumps(result,sort_keys=True));return 0
if __name__=="__main__":sys.exit(main())
