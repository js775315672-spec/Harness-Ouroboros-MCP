#!/usr/bin/env python3
"""Read-only Ouroboros evaluation: derive checkpoint outcome from verified gate results."""
import argparse
import json
import pathlib
import subprocess
import sys
from governance import check

def evaluate_gates(root, policy_path):
    policy=json.loads(policy_path.read_text(encoding="utf-8"))
    result=check(root,policy)
    failures={name:issues for name,issues in result.items() if issues}
    return {"outcome":"blocked" if failures else "pass","gates":{name:("fail" if issues else "pass") for name,issues in result.items()},"findings":failures}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=pathlib.Path,default=pathlib.Path(__file__).resolve().parents[1])
    parser.add_argument("--policy",default="harness-policy.json")
    parser.add_argument("--checkpoint",type=pathlib.Path)
    args=parser.parse_args()
    root=args.root.resolve()
    try:
        result=evaluate_gates(root,root/args.policy)
        if args.checkpoint:
            from ouroboros import evaluate,checkpoint
            record=evaluate(root,"evaluate",result["outcome"],json.dumps(result,sort_keys=True))
            checkpoint(args.checkpoint,record)
    except (OSError,ValueError,UnicodeError,subprocess.CalledProcessError) as exc:
        print("BLOCK: evaluation unavailable:",type(exc).__name__,file=sys.stderr)
        return 2
    print(json.dumps(result,sort_keys=True))
    return 0 if result["outcome"]=="pass" else 1
if __name__=="__main__":
    sys.exit(main())
