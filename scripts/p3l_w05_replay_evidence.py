#!/usr/bin/env python3
"""W05 independent runner: regrade model-generated ledger code in isolated Docker.

A signed-looking JSON receipt is not proof: this routine reconstructs the
source from exact raw model text and RE-RUNS fixed test suites. Never promotes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re

import p3g_qwen_ledger_feedback_repair as p3g
import p3l_w04_one_call_gate as w04
from p3l_w05_actions_source import read_model_archive, read_replay_archive
from p3l_w06_actual_model_once import inference_config_sha256

def digest(data):
    return hashlib.sha256(data).hexdigest()

def reconstruct(root, report, run_id):
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
    if (type(raw) is not str or type(report["raw_response_sha256"]) is not str
            or digest(raw.encode("utf-8"))!=report["raw_response_sha256"]):
        raise ValueError("raw response SHA mismatch")
    replacement=p3g.inspect_replacement(raw)
    original=p3g.file_bytes(root,p3g.TARGET).decode("utf-8")
    patched,diff=p3g.patch_original(original,replacement)
    if (type(report["candidate_source_sha256"]) is not str or type(report["diff_sha256"]) is not str
            or digest(patched.encode("utf-8"))!=report["candidate_source_sha256"]
            or digest(diff.encode("utf-8"))!=report["diff_sha256"]):
        raise ValueError("model source or diff evidence changed")
    return plan,patched


def replay(root, report, run_id, execution=None):
    plan,patched=reconstruct(root,report,run_id)
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
        if type(actual.get("passed")) is not bool or type(actual.get("exit_code")) is not int:
            raise ValueError("independent test verdict has invalid evidence types")
        passed=actual["passed"]
        if passed != (actual["exit_code"] == 0):
            raise ValueError("independent suite flag contradicts exit code")
        all_passed=all_passed and passed
        details[name]={"tests_run":count,"passed":passed}
        if execution is not None:
            summary=re.search(r"(?m)^FAILED \(([^\n]+)\)\s*\Z",actual.get("log_tail",""))
            execution[name]={"exit_code":actual["exit_code"],
                             "unittest_failure_summary":summary[1] if summary else None}
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


def require_verified_replay(verdict, provenance, report, origin, run_id):
    if (type(verdict) is not dict or type(provenance) is not dict
            or verdict.get("schema") != "p3l-w05-independent-replay-v1"
            or verdict.get("runner_role") != "independent_replay"
            or type(verdict.get("run_id")) is not int or verdict["run_id"] != run_id
            or verdict.get("candidate_passed") is not True
            or verdict.get("independent_replay_completed") is not True
            or verdict.get("merge_authorized") is not False or verdict.get("promoted") is not False
            or type(verdict.get("test_count")) is not int or verdict["test_count"] != 25):
        raise ValueError("independent replay did not prove a complete passing verdict")
    for key in ("task_sha256", "source_sha256", "raw_response_sha256",
                "candidate_source_sha256", "diff_sha256"):
        if type(verdict.get(key)) is not str or verdict[key] != report[key]:
            raise ValueError("replay does not match reconstructed model receipt")
    if any(type(provenance.get(key)) is not type(value) or provenance[key] != value
           for key,value in origin.items()):
        raise ValueError("replay does not match GitHub model artifact provenance")
    suites=verdict.get("suites")
    execution=provenance.get("suite_execution")
    if (type(suites) is not dict or set(suites) != set(p3g.FROZEN_SUITES)
            or type(execution) is not dict or set(execution) != set(p3g.FROZEN_SUITES)):
        raise ValueError("independent replay is missing frozen suites")
    for name,count in p3g.FROZEN_SUITES.items():
        result=suites[name]
        exit_code=execution[name].get("exit_code") if type(execution[name]) is dict else None
        if (type(result) is not dict or type(result.get("tests_run")) is not int
                or result["tests_run"] != count or result.get("passed") is not True
                or type(exit_code) is not int or exit_code != 0):
            raise ValueError("independent replay suite did not pass with typed evidence")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--head-sha",required=True)
    p.add_argument("--artifact-id",type=int,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--run-id",type=int,required=True)
    p.add_argument("--verify-replay-artifact-id",type=int)
    args=p.parse_args()
    report, origin=read_model_archive(args.run_id,args.head_sha,args.artifact_id)
    if args.verify_replay_artifact_id is not None:
        files, replay_job_id, replay_archive_sha256 = read_replay_archive(
            args.run_id,args.head_sha,args.verify_replay_artifact_id)
        reconstruct(w04.w02.ROOT,report,args.run_id)
        if origin.get("inference_config_sha256") != inference_config_sha256():
            raise ValueError("missing or mismatched exact inference configuration")
        require_verified_replay(files["verdict.json"],files["provenance.json"],report,origin,args.run_id)
        args.out.parent.mkdir(parents=True,exist_ok=True)
        verified={**files["verdict.json"],"github_provenance":origin,
                  "replay_job_id":replay_job_id,"replay_archive_sha256":replay_archive_sha256,
                  "replay_artifact_id":args.verify_replay_artifact_id}
        args.out.write_text(json.dumps(verified,sort_keys=True,indent=2)+"\n",encoding="utf-8")
        print("W05 verified GitHub provenance and an independent 25/25; review only")
        return 0
    os.environ.pop("GH_TOKEN",None)
    execution={}
    result=replay(w04.w02.ROOT,report,args.run_id,execution)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    args.out.with_name("provenance.json").write_text(
        json.dumps({**origin,"suite_execution":execution},sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("W05 independent model replay:",result["test_count"],"tests, passed:",result["candidate_passed"])
    return 0 if result["candidate_passed"] else 2

if __name__=="__main__":
    raise SystemExit(main())
