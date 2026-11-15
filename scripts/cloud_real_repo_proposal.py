#!/usr/bin/env python3
"""One-shot real Qwen proposal for a scoped repository test change.

Runs public CPU model weights in CI. Generated text is data only: never
executed, applied, committed or merged. Rejection is recorded as evidence.
"""
import hashlib
import json
import os
from pathlib import Path

try:
    from .real_repo_task import prepare
    from .scoped_patch_gate import inspect_scoped_patch
except ImportError:
    from real_repo_task import prepare
    from scoped_patch_gate import inspect_scoped_patch

MODEL="Qwen/Qwen2.5-0.5B-Instruct"
TARGET=Path("tests/test_model_feedback_loop.py")
OUTPUT=Path("artifacts/real-repo-qwen-proposal.json")

def assess(raw,task):
    proposal={"provider":"qwen","status":"proposal",
              "summary":"One-shot model-generated regression-test diff",
              "patch":raw}
    try:
        inspection=inspect_scoped_patch(task,proposal)
        return {"status":"accepted_for_review","reason":None,"inspection":inspection}
    except (ValueError,TypeError,KeyError) as exc:
        return {"status":"rejected","reason":str(exc)[:300],"inspection":None}

def main():
    report={"model":MODEL,"real_model_calls":0,"paid_api_used":False,
            "secrets_used":False,"generated_code_executed":False,
            "patch_applied":False,"merge_authorized":False,
            "full_harness_passed":False,"status":"not_started"}
    try:
        os.environ["HF_HUB_DISABLE_TELEMETRY"]="1"
        os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"]="1"
        os.environ["TOKENIZERS_PARALLELISM"]="false"
        from transformers import AutoTokenizer,AutoModelForCausalLM
        import torch
        task=prepare()
        source=TARGET.read_text(encoding="utf-8")
        if len(source)>12000:
            raise ValueError("source file exceeds prompt size budget")
        report["source_sha256"]=hashlib.sha256(source.encode()).hexdigest()
        prompt=task["prompt"]+"\nCurrent file contents:\n"+source
        tokenizer=AutoTokenizer.from_pretrained(MODEL,trust_remote_code=False)
        model=AutoModelForCausalLM.from_pretrained(
            MODEL,trust_remote_code=False,torch_dtype=torch.float32)
        model.eval()
        tokens=tokenizer(tokenizer.apply_chat_template(
            [{"role":"user","content":prompt}],tokenize=False,
            add_generation_prompt=True),return_tensors="pt")
        report["real_model_calls"]=1
        with torch.inference_mode():
            result=model.generate(**tokens,max_new_tokens=384,do_sample=False,
                                  pad_token_id=tokenizer.eos_token_id)
        raw=tokenizer.decode(result[0][tokens["input_ids"].shape[1]:],
                             skip_special_tokens=True)
        report["response_sha256"]=hashlib.sha256(raw.encode()).hexdigest()
        report["response_chars"]=len(raw)
        report["response_preview"]=raw[:1200]
        report.update(assess(raw,task["task"]))
        report["task_id"]=task["task"]["task_id"]
        report["inspection_kind"]="static_scope_and_unified_diff_only"
    except Exception as exc:
        report["status"]="error"
        report["error_type"]=type(exc).__name__
        report["error_message"]=str(exc)[:300]
    finally:
        OUTPUT.parent.mkdir(parents=True,exist_ok=True)
        OUTPUT.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",
                          encoding="utf-8")
        print(json.dumps(report,sort_keys=True))
    return 0 if report["status"] in ("accepted_for_review","rejected") else 2

if __name__=="__main__":
    raise SystemExit(main())
