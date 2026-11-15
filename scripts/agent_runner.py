#!/usr/bin/env python3
"""Bounded local agent execution adapter. No shell, network, or Git writes.

Only an explicitly supplied executable is run; default mode is dry-run.
This is NOT an AI coding model. Never execute untrusted repository content.
"""
import argparse,json,os,pathlib,subprocess,sys,time
from agent_handoff import handoff
from task_selector import select

def prepare(proposal,branch,command=None,allow_execution=False,timeout=30):
    contract=handoff(proposal,branch)
    if type(timeout) is not int or not 1<=timeout<=300:
        raise ValueError("timeout outside 1..300 seconds")
    if command is not None:
        if not isinstance(command,list) or not command or any(not isinstance(x,str) or not x for x in command):
            raise ValueError("command must be a nonempty argv list")
    if allow_execution:
        raise ValueError("execution disabled until a sandboxed runner and approval gate are installed")
    return dict(contract,execution_enabled=False,execution_attempted=False,
                timeout_seconds=timeout,command_supplied=command is not None,
                execution_status="blocked" if command is not None else "dry_run")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--completed",type=int,default=0)
    p.add_argument("--branch",required=True)
    p.add_argument("--timeout",type=int,default=30)
    p.add_argument("--output",type=pathlib.Path)
    args=p.parse_args()
    try:
        result=prepare(select(args.completed),args.branch,timeout=args.timeout)
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    except (ValueError,OSError) as exc:
        print("BLOCK:",str(exc),file=sys.stderr);return 2
    print(json.dumps(result,sort_keys=True));return 0
if __name__=="__main__":sys.exit(main())
