#!/usr/bin/env python3
"""Record bounded agent handoff runtime, without claiming autonomous coding."""
import argparse,datetime,json,pathlib,sys,time
from agent_handoff import handoff
from task_selector import select
UTC=datetime.timezone.utc

def measure(proposal,branch,clock=None,wall_clock=None):
    clock=clock or time.monotonic
    wall_clock=wall_clock or (lambda:datetime.datetime.now(UTC))
    start=clock()
    started=wall_clock().astimezone(UTC).isoformat()
    payload=handoff(proposal,branch)
    finished=wall_clock().astimezone(UTC).isoformat()
    payload.update({"started_at":started,"finished_at":finished,
                    "elapsed_seconds":round(clock()-start,6),
                    "code_changes":0,"development_commits":0,
                    "actual_agent_execution":False})
    return payload

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--completed",type=int,default=0)
    p.add_argument("--branch",required=True)
    p.add_argument("--output",type=pathlib.Path,required=True)
    args=p.parse_args()
    try:
        result=measure(select(args.completed),args.branch)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    except (OSError,ValueError) as exc:
        print("BLOCK:",str(exc),file=sys.stderr);return 2
    print(json.dumps(result,sort_keys=True));return 0
if __name__=="__main__":sys.exit(main())
