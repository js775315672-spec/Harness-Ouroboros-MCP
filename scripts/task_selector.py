#!/usr/bin/env python3
"""Bounded, offline-capable Ouroboros development task selector.

Selection is deterministic and read-only. A coding agent is NOT connected.
"""
import argparse,json,sys
from evolution_planner import plan

TASKS={
 "baseline":("Establish a reproducible failing regression test","tests"),
 "boundary":("Add boundary-condition tests for an existing module","tests"),
 "security":("Strengthen input validation without secrets or network writes","security"),
 "recovery":("Test checkpoint recovery and restart invariants","recovery"),
 "fault_injection":("Add failure-injection regression coverage","tests"),
 "integration":("Verify cross-module contracts with integration tests","integration"),
 "mutation":("Test that intentionally invalid inputs are rejected","tests"),
 "regression":("Prevent a previously observed defect from recurring","tests"),
}
def select(completed=0,target=30,ceiling=10000):
    decision=plan(completed,target=target,ceiling=ceiling)
    if decision["decision"]=="stop":return {"decision":"stop","reason":decision["reason"]}
    phase=decision["phase"]
    task,area=TASKS[phase]
    return {"decision":"propose","cycle":decision["next_cycle"],"phase":phase,
            "task":task,"area":area,"requires_human_merge_approval":True,
            "coding_agent_connected":False,"writes_allowed":False,
            "note":"task proposal only; no AI code generation or verified development"}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--completed",type=int,default=0)
    p.add_argument("--target",type=int,default=30)
    p.add_argument("--ceiling",type=int,default=10000)
    args=p.parse_args()
    try:result=select(args.completed,args.target,args.ceiling)
    except ValueError as exc:
        print("BLOCK:",str(exc),file=sys.stderr);return 2
    print(json.dumps(result,sort_keys=True));return 0
if __name__=="__main__":sys.exit(main())
