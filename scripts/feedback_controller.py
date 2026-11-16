#!/usr/bin/env python3
"""Fail-closed Harness -> coding-model feedback controller.

Produces a bounded, reviewable prompt payload. Does not call an AI provider,
modify source code, or grant the model access to Harness policies.
"""
import argparse,json,pathlib,sys
from task_selector import select
from model_stagnation_gate import evaluate as check_model_stagnation

REQUIRED_CHECKS=("harness","ouroboros","regression","secrets")
MAX_LOG_CHARS=4000
MAX_ATTEMPTS=5

def feedback(proposal,checks,attempt=1,max_attempts=MAX_ATTEMPTS,
             model_history=None,model_context=None):
    if not isinstance(proposal,dict) or proposal.get("decision")!="propose":
        raise ValueError("missing active development proposal")
    if type(attempt) is not int or type(max_attempts) is not int or not 1<=max_attempts<=MAX_ATTEMPTS or not 1<=attempt<=max_attempts:
        raise ValueError("invalid bounded retry counters")
    if not isinstance(checks,dict) or set(checks)!=set(REQUIRED_CHECKS):
        raise ValueError("incomplete independent Harness evidence")
    normalized={}
    for name in REQUIRED_CHECKS:
        evidence=checks[name]
        if not isinstance(evidence,dict) or set(evidence)!={"status","log"}:
            raise ValueError("malformed check evidence")
        status=evidence["status"]
        log=evidence["log"]
        if status not in ("pass","fail") or not isinstance(log,str) or len(log)>MAX_LOG_CHARS:
            raise ValueError("invalid check status or oversized log")
        normalized[name]={"status":status,"log":log}
    failures=[name for name in REQUIRED_CHECKS if normalized[name]["status"]=="fail"]
    retry_gate = None
    if model_history is not None or model_context is not None:
        if (type(model_context) is not dict
                or set(model_context) != {"task_sha256", "model_sha256",
                                          "baseline_source_sha256"}
                or model_history is None):
            raise ValueError("model retry history and immutable context required")
        retry_gate = check_model_stagnation(
            model_history, model_context["task_sha256"],
            model_context["model_sha256"], model_context["baseline_source_sha256"],
            max_attempts=max_attempts)
        if retry_gate["decision"] == "stop":
            return {"decision": "stop", "cycle": proposal["cycle"],
                    "attempt": attempt, "failed_checks": failures,
                    "reason": retry_gate["reason"],
                    "model_call_performed": False,
                    "human_merge_approval_required": True,
                    "model_retry_gate": retry_gate}
        if model_history and model_history[-1]["outcome"] != "candidate_passed":
            failures.append("model_candidate")
    if not failures:
        return {"decision":"review","cycle":proposal["cycle"],"attempt":attempt,
                "failed_checks":[],"model_call_performed":False,
                "requires_independent_review":True}
    if attempt>=max_attempts:
        return {"decision":"stop","cycle":proposal["cycle"],"attempt":attempt,
                "failed_checks":failures,"reason":"retry_budget_exhausted",
                "model_call_performed":False}
    return {"decision":"request_fix","cycle":proposal["cycle"],"attempt":attempt,
            "next_attempt":attempt+1,"task":proposal["task"],
            "failed_checks":failures,"evidence":normalized,
            "instruction":"Fix the source defect. Do not weaken tests, security gates, or Harness policies.",
            "model_call_performed":False,"human_merge_approval_required":True,
            **({"model_retry_gate":retry_gate} if retry_gate is not None else {})}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--completed",type=int,default=0)
    p.add_argument("--checks",type=pathlib.Path,required=True)
    p.add_argument("--attempt",type=int,default=1)
    p.add_argument("--output",type=pathlib.Path)
    args=p.parse_args()
    try:
        checks=json.loads(args.checks.read_text(encoding="utf-8"))
        result=feedback(select(args.completed),checks,args.attempt)
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    except (ValueError,OSError,UnicodeError) as exc:
        print("BLOCK:",str(exc),file=sys.stderr);return 2
    print(json.dumps(result,sort_keys=True));return 0
if __name__=="__main__":sys.exit(main())
