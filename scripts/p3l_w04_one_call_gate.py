#!/usr/bin/env python3
"""W04: preflight gate for exactly one new model call; never runs models."""
import argparse
import hashlib
import json
from pathlib import Path

import p3l_w02_model_handoff as w02
import p3l_w03_rule_diagnostics as w03
from model_stagnation_gate import evaluate
from gguf_cpu_runtime import approved_model

def digest_json(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def plan(root=w02.ROOT, history=None, model_id="7b"):
    if history is None:
        history=[]
    request=w02.build(root)
    diagnostics=w03.diagnose(root)
    if (diagnostics["w02_prompt_sha256"]!=request["prompt_sha256"]
            or diagnostics["w01_case_manifest_sha256"]!=request["w01_case_manifest_sha256"]
            or diagnostics["isolated_rule_passed"]!=19):
        raise ValueError("W01/W02/W03 handoff invalid")
    model=approved_model(model_id)
    model_identity=digest_json({"model_id":model_id,"allowlist":model})
    task=digest_json({
        "prompt_sha256":request["prompt_sha256"],
        "manifest_sha256":request["w01_case_manifest_sha256"],
        "validator_sha256":request["w01_candidate_sha256"],
        "baseline_source_sha256":request["legacy_sha256"],
    })
    verdict=evaluate(history,task,model_identity,request["legacy_sha256"],max_attempts=1)
    if verdict["decision"]!="allow_one_model_call" or verdict["next_attempt"]!=1:
        raise ValueError("W04 forbids additional model attempt")
    return {
        "schema":"p3l-w04-one-call-preflight-v1",
        "task_sha256":task,
        "prompt_sha256":request["prompt_sha256"],
        "model_id":model_id,
        "model_config_sha256":model_identity,
        "model_config_only_not_weights":True,
        "source_sha256":request["legacy_sha256"],
        "w01_candidate_sha256":request["w01_candidate_sha256"],
        "manifest_sha256":request["w01_case_manifest_sha256"],
        "w03_rule_checks":diagnostics["isolated_rule_passed"],
        "decision":verdict["decision"],
        "next_attempt":1,
        "max_attempts":1,
        "model_calls":0,
        "model_invoked":False,
        "model_candidate_passed":False,
        "independent_replay_completed":False,
        "merge_authorized":False,
        "promoted":False,
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    result=plan()
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("PASS: W04 allows exactly one proposed model attempt; model not called")

if __name__=="__main__":
    main()
