#!/usr/bin/env python3
"""Write reproducible, non-executing evidence for a scoped model patch proposal."""
import argparse
import hashlib
import json
import pathlib
import sys
from scoped_patch_gate import inspect_scoped_patch

def _read(path):
    data=path.read_bytes()
    if len(data)>120000:
        raise ValueError("input exceeds size limit")
    return json.loads(data.decode("utf-8")),hashlib.sha256(data).hexdigest()

def evaluate(task_path,response_path):
    task,task_hash=_read(task_path)
    response,response_hash=_read(response_path)
    try:
        result=inspect_scoped_patch(task,response)
        status="accepted_for_review"
        reason=None
    except (ValueError,KeyError,TypeError) as exc:
        result=None
        status="rejected"
        reason=str(exc)[:300]
    return {"schema_version":1,"status":status,"reason":reason,
            "task_sha256":task_hash,"proposal_sha256":response_hash,
            "inspection":result,"generated_code_executed":False,
            "patch_applied":False,"merge_authorized":False,
            "full_harness_passed":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("task",type=pathlib.Path)
    p.add_argument("proposal",type=pathlib.Path)
    p.add_argument("--output",type=pathlib.Path,required=True)
    args=p.parse_args()
    try:
        report=evaluate(args.task,args.proposal)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    except (OSError,UnicodeError,json.JSONDecodeError,ValueError) as exc:
        print("BLOCK:",str(exc),file=sys.stderr)
        return 2
    print(json.dumps(report,sort_keys=True))
    return 0 if report["status"]=="accepted_for_review" else 2

if __name__=="__main__":
    sys.exit(main())
