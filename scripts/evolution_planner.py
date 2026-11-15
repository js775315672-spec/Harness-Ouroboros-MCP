#!/usr/bin/env python3
"""Bounded, evidence-based evolutionary verification planner (read-only)."""
import argparse,json,pathlib,sys
MAX_CYCLES=10000
PHASES=("baseline","boundary","security","recovery","fault_injection","integration","mutation","regression")
def plan(completed,target=30,ceiling=MAX_CYCLES,stagnation=0,stagnation_limit=20):
    if type(completed) is not int or completed<0:raise ValueError("invalid completed count")
    if type(target) is not int or type(ceiling) is not int or not 1<=target<=ceiling<=MAX_CYCLES:raise ValueError("invalid limits")
    if type(stagnation) is not int or type(stagnation_limit) is not int or stagnation<0 or stagnation_limit<1:raise ValueError("invalid stagnation")
    if completed>=ceiling:return {"decision":"stop","reason":"ceiling reached","completed":completed}
    if completed>=target and stagnation>=stagnation_limit:return {"decision":"stop","reason":"no measured improvement","completed":completed}
    return {"decision":"propose","next_cycle":completed+1,"phase":PHASES[completed%len(PHASES)],"requires_new_commit":True,"requires_full_ci":True,"requires_human_merge_approval":True,"note":"planning only: no autonomous code execution or claim of verification"}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--completed",type=int,required=True)
    p.add_argument("--target",type=int,default=30)
    p.add_argument("--ceiling",type=int,default=MAX_CYCLES)
    p.add_argument("--stagnation",type=int,default=0)
    p.add_argument("--stagnation-limit",type=int,default=20)
    args=p.parse_args()
    try:result=plan(args.completed,args.target,args.ceiling,args.stagnation,args.stagnation_limit)
    except ValueError as exc:
        print("BLOCK:",str(exc),file=sys.stderr);return 2
    print(json.dumps(result,sort_keys=True));return 0
if __name__=="__main__":sys.exit(main())
