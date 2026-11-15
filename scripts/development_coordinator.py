#!/usr/bin/env python3
"""Read-only, restartable development cycle coordinator; never fabricates commits or CI."""
import argparse,json,pathlib,sys
from development_ledger import validate
from ci_attestation import verify_ledger
from evolution_planner import plan
from task_selector import select

def coordinate(records,target=30,ceiling=10000,fetch=None):
    count=validate(records)
    attestations=verify_ledger(records,fetch=fetch)
    decision=plan(count,target=target,ceiling=ceiling)
    task=select(count,target=target,ceiling=ceiling)
    return {"verified_development_cycles":len(attestations),"next":decision,"proposed_task":task,
            "autonomous_coding_connected":False,
            "verification_repetitions_are_not_development_cycles":True}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--ledger",type=pathlib.Path,required=True)
    parser.add_argument("--target",type=int,default=30)
    parser.add_argument("--ceiling",type=int,default=10000)
    args=parser.parse_args()
    try:
        records=json.loads(args.ledger.read_text(encoding="utf-8"))
        result=coordinate(records,args.target,args.ceiling)
    except (OSError,UnicodeError,ValueError) as exc:
        print("BLOCK:",str(exc),file=sys.stderr)
        return 2
    print(json.dumps(result,sort_keys=True))
    return 0

if __name__=="__main__":sys.exit(main())
