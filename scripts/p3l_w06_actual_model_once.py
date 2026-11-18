#!/usr/bin/env python3
"""W06: a single real Qwen model attempt on the W02 contract, review only."""
import argparse
from functools import partial
import hashlib
import json
from pathlib import Path
import subprocess

import p3g_qwen_ledger_feedback_repair as p3g
import p3l_w04_one_call_gate as w04
from p3l_w04_attempt_registry import AttemptBlocked, AttemptInput
import p3l_w02_model_handoff as w02

# Source digests independently rejected by W05 in runs 44233044418,
# 44256635138, 44264996365 (repeated in 44269883090), 44285978475,
# and 44287350233.
REJECTED_CANDIDATE_DIGESTS = frozenset({
    "7dac043a9f115a179107ea67cd89e4966dc59c96338429362720e1aaf2ecedbb",
    "b3040620a1e0c136ff81fbe6d2c34ef61d42c5744b1eae2e3e144f90fe7be861",
    "bef7d24b09bbb068d3106d21c22d72a76209e0093e7e1e6c4ccc307a7f6c747f",
    "b2bc7ecf096ff5d7a94412f9e07cd3736e9213292121726584b676771f18348e",
    "ec528fbde8e7c63d0e904054aed565ae01d9f1ee9bfa7a6c42811e828182dd74",
})
INFERENCE_OPTIONS = {"exact_prompt": True, "temperature": "0", "seed": "1085"}


def inference_config_sha256():
    return w04.digest_json(p3g.inference_flags("7b", **INFERENCE_OPTIONS))

def sha(data):
    return hashlib.sha256(data).hexdigest()


def managed_attempt_input(root, review_sha, handoff, model):
    parent = subprocess.run(
        ["git", "rev-parse", "--verify", "--end-of-options", review_sha + "^"],
        cwd=root, capture_output=True, text=True, timeout=10, check=True,
    ).stdout.strip()
    return AttemptInput(
        task_type="ledger-validation",
        public_contract_sha256=handoff["w01_provisional_spec_sha256"],
        base_sha=parent,
        head_sha=review_sha,
        model_revision=model["revision"],
        gguf_sha256=model["sha256"],
        inference_config_sha256=inference_config_sha256(),
        prompt_sha256=handoff["prompt_sha256"],
    )


def execute(root, review_sha, run_id, binary, weights, metadata, infer_fn=None, *, admission=None):
    if type(run_id) is not int or run_id<1:
        raise ValueError("invalid workflow run id")
    if type(review_sha) is not str or len(review_sha)!=40 or any(c not in "0123456789abcdef" for c in review_sha):
        raise ValueError("invalid reviewed commit")
    observed=subprocess.run(["git","rev-parse","HEAD"],cwd=root,capture_output=True,text=True,timeout=10,check=True).stdout.strip()
    if observed!=review_sha:
        raise ValueError("wrong reviewed commit")
    plan=w04.plan(root,history=[],model_id="7b")
    handoff=w02.build(root)
    if plan["decision"]!="allow_one_model_call" or plan["prompt_sha256"]!=handoff["prompt_sha256"]:
        raise ValueError("W04 refused one model attempt")
    model=p3g.check_model(weights,metadata,"7b")
    if infer_fn is None:
        infer_fn=partial(p3g.infer_prepared, **INFERENCE_OPTIONS)
    if admission is not None:
        registry,lease=admission
        if lease.task_key != managed_attempt_input(root,review_sha,handoff,model).task_key:
            raise AttemptBlocked("lease does not match the verified W06 inputs")
        observed=subprocess.run(["git","rev-parse","HEAD"],cwd=root,capture_output=True,text=True,
                                timeout=10,check=True).stdout.strip()
        registry.start(lease,observed_head=observed,run_id=run_id)
    raw,elapsed=infer_fn(binary,weights,handoff["prompt"],"7b")
    if type(raw) is not str or not 1<=len(raw.encode("utf-8"))<=6000:
        raise ValueError("invalid bounded model response")
    receipt={
        "schema":"p3l-w06-one-shot-output-v1",
        "run_id":run_id,"runner_role":"model_inference",
        "model_calls":1,"model_id":"7b",
        "task_sha256":plan["task_sha256"],
        "prompt_sha256":plan["prompt_sha256"],
        "source_sha256":plan["source_sha256"],
        "model_config_sha256":plan["model_config_sha256"],
        "raw_response":raw,
        "raw_response_sha256":sha(raw.encode("utf-8")),
        "candidate_source_sha256":None,
        "diff_sha256":None,
        "merge_authorized":False,
    }
    try:
        replacement=p3g.inspect_replacement(raw)
        original=p3g.file_bytes(root,p3g.TARGET).decode("utf-8")
        patched,diff=p3g.patch_original(original,replacement)
        receipt["candidate_source_sha256"]=sha(patched.encode("utf-8"))
        receipt["diff_sha256"]=sha(diff.encode("utf-8"))
        if receipt["candidate_source_sha256"] in REJECTED_CANDIDATE_DIGESTS:
            receipt["schema"]="p3l-w06-duplicate-rejected-v1"
            receipt["static_rejection"]="candidate source already rejected by independent W05"
    except (ValueError,SyntaxError) as exc:
        # Preserve original response, do not fabricate a valid patch.
        receipt["schema"]="p3l-w06-static-rejected-v1"
        receipt["static_rejection"]=type(exc).__name__+": "+str(exc)[:160]
    return receipt

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--head-sha",required=True)
    p.add_argument("--run-id",type=int,required=True)
    p.add_argument("--cli",type=Path,required=True)
    p.add_argument("--gguf",type=Path,required=True)
    p.add_argument("--metadata",type=Path,required=True)
    p.add_argument("--llama-revision",required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    if len(args.llama_revision)!=40 or any(c not in "0123456789abcdef" for c in args.llama_revision):
        raise ValueError("invalid pinned llama.cpp revision")
    result=execute(w02.ROOT,args.head_sha,args.run_id,args.cli,args.gguf,args.metadata)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    metadata=json.loads(args.metadata.read_bytes())
    metadata.update(llama_cpp_revision=args.llama_revision,
                    llama_binary_sha256=p3g.sha256_file(args.cli),
                    inference_config_sha256=inference_config_sha256(),
                    prompt_sha256=result["prompt_sha256"])
    args.metadata.write_text(json.dumps(metadata,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("W06 real model completed; output:",result["schema"])
    return 0 if result["schema"]=="p3l-w06-one-shot-output-v1" else 2

if __name__=="__main__":
    raise SystemExit(main())
