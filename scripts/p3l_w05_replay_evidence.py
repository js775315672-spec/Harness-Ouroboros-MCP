#!/usr/bin/env python3
"""W05 independent runner: regrade model-generated ledger code in isolated Docker.

A signed-looking JSON receipt is not proof: this routine reconstructs the
source from exact raw model text and RE-RUNS fixed test suites. Never promotes.
"""
import argparse
import hashlib
import json
from pathlib import Path

import p3g_qwen_ledger_feedback_repair as p3g
import p3l_w04_one_call_gate as w04

def digest(data):
    return hashlib.sha256(data).hexdigest()

def replay(root, report, run_id):
    if type(run_id) is not int or run_id<1 or type(report) is not dict:
        raise ValueError("invalid run identity or report")
    required={"schema","run_id","runner_role","model_calls","model_id",
              "task_sha256","prompt_sha256","source_sha256",
              "model_config_sha256","raw_response","raw_response_sha256",
              "candidate_source_sha256","diff_sha256","merge_authorized"}
    if set(report)!=required:
        raise ValueError("missing or unexpected model receipt fields")
    if (report["schema"]!="p3l-w06-one-shot-output-v1"
            or type(report["run_id"]) is not int or report["run_id"]!=run_id
            or report["runner_role"]!="model_inference"
            or type(report["model_calls"]) is not int or report["model_calls"]!=1
            or report["model_id"]!="7b"
            or report["merge_authorized"] is not False):
        raise ValueError("model execution evidence invalid")
    plan=w04.plan(root,model_id=report["model_id"])
    for key,reference in (("task_sha256","task_sha256"),
                          ("prompt_sha256","prompt_sha256"),
                          ("source_sha256","source_sha256"),
                          ("model_config_sha256","model_config_sha256")):
        if report[key]!=plan[reference]:
            raise ValueError("receipt differs from W04 preflight: "+key)
    raw=report["raw_response"]
    if type(raw) is not str or digest(raw.encode("utf-8"))!=report["raw_response_sha256"]:
        raise ValueError("raw response SHA mismatch")
    replacement=p3g.inspect_replacement(raw)
    original=p3g.file_bytes(root,p3g.TARGET).decode("utf-8")
    patched,diff=p3g.patch_original(original,replacement)
    if (digest(patched.encode("utf-8"))!=report["candidate_source_sha256"]
            or digest(diff.encode("utf-8"))!=report["diff_sha256"]):
        raise ValueError("model source or diff evidence changed")
    # Actual independent execution in a separate no-network read-only Docker runner.
    grade=p3g.grade(root,patched)
    suites=grade.get("candidate")
    if type(suites) is not dict or set(suites)!=set(p3g.FROZEN_SUITES):
        raise ValueError("frozen suites absent from independent replay")
    details={}
    all_passed=True
    for name,count in p3g.FROZEN_SUITES.items():
        actual=suites[name]
        if type(actual) is not dict or type(actual.get("tests_run")) is not int or actual["tests_run"]!=count:
            raise ValueError("independent test count mismatch")
        # False == 0 and 0.0 == 0 in Python; neither is valid process
        # evidence. A numeric 0/1 is not a valid boolean verdict either.
        if type(actual.get("passed")) is not bool or type(actual.get("exit_code")) is not int:
            raise ValueError("independent test verdict has invalid evidence types")
        passed=actual["passed"] is True and actual["exit_code"]==0
        all_passed=all_passed and passed
        details[name]={"tests_run":count,"passed":passed}
    if grade.get("status")!=("real_source_patch_passed" if all_passed else "real_source_patch_failed"):
        raise ValueError("replay status contradicts suite evidence")
    return {
        "schema":"p3l-w05-independent-replay-v1",
        "run_id":run_id,
        "runner_role":"independent_replay",
        "task_sha256":plan["task_sha256"],
        "source_sha256":plan["source_sha256"],
        "raw_response_sha256":report["raw_response_sha256"],
        "candidate_source_sha256":report["candidate_source_sha256"],
        "diff_sha256":report["diff_sha256"],
        "test_count":sum(x["tests_run"] for x in details.values()),
        "suites":details,
        "candidate_passed":all_passed,
        "independent_replay_completed":True,
        "merge_authorized":False,"promoted":False,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--run-id",type=int,required=True)
    args=p.parse_args()
    if args.input.is_symlink() or not args.input.is_file() or args.input.stat().st_size>30000:
        raise SystemExit("BLOCK: unsafe model report")
    report=json.loads(args.input.read_text(encoding="utf-8"))
    result=replay(w04.w02.ROOT,report,args.run_id)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("W05 independent model replay:",result["test_count"],"tests, passed:",result["candidate_passed"])
    return 0 if result["candidate_passed"] else 2

if __name__=="__main__":
    raise SystemExit(main())
