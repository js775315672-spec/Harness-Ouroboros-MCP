#!/usr/bin/env python3
"""Strict offline coding-model request/response boundary.

No provider is called and no generated code is executed or written.
"""
import argparse,json,pathlib,sys
from feedback_controller import feedback
from task_selector import select

PROVIDERS=("qwen","gpt-oss","gemma")
MAX_TEXT=12000

def request(provider,task,feedback_payload=None):
    if provider not in PROVIDERS:raise ValueError("unsupported model provider")
    if not isinstance(task,str) or not task.strip() or len(task)>MAX_TEXT:
        raise ValueError("invalid coding task")
    if feedback_payload is not None:
        if not isinstance(feedback_payload,dict) or feedback_payload.get("decision")!="request_fix":
            raise ValueError("feedback must request a fix")
        if feedback_payload.get("model_call_performed") is not False:
            raise ValueError("feedback must not claim a completed model call")
    return {"provider":provider,"role":"coder" if provider=="qwen" else "reviewer",
            "task":task,"feedback":feedback_payload,
            "execution":"not_connected","network_request_performed":False,
            "source_changes_written":False,"requires_harness_revalidation":True}

def validate_response(payload):
    if not isinstance(payload,dict) or set(payload)!={"provider","status","summary","patch"}:
        raise ValueError("malformed model response")
    if payload["provider"] not in PROVIDERS or payload["status"] not in ("proposal","reject"):
        raise ValueError("unsupported provider or response status")
    if not isinstance(payload["summary"],str) or not payload["summary"].strip() or len(payload["summary"])>MAX_TEXT:
        raise ValueError("invalid response summary")
    patch=payload["patch"]
    if not isinstance(patch,str) or len(patch)>100000:
        raise ValueError("invalid patch")
    if payload["status"]=="proposal" and not patch.startswith("diff --git "):
        raise ValueError("proposal must contain a git-style patch")
    if payload["status"]=="reject" and patch:
        raise ValueError("rejected proposal must not include a patch")
    return {"provider":payload["provider"],"status":payload["status"],
            "patch_present":bool(patch),"patch_applied":False,
            "harness_passed":False,"model_output_trusted":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--provider",choices=PROVIDERS,default="qwen")
    p.add_argument("--completed",type=int,default=0)
    p.add_argument("--output",type=pathlib.Path)
    args=p.parse_args()
    try:
        proposal=select(args.completed)
        if proposal.get("decision")!="propose":raise ValueError("no active task")
        result=request(args.provider,proposal["task"])
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    except (ValueError,OSError) as exc:
        print("BLOCK:",str(exc),file=sys.stderr);return 2
    print(json.dumps(result,sort_keys=True));return 0
if __name__=="__main__":sys.exit(main())
