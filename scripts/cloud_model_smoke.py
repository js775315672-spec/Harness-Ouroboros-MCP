#!/usr/bin/env python3
"""Opt-in CPU inference smoke test for a small public Qwen model.

Run only in an explicitly dispatched cloud workflow. No secrets, paid API,
source edits, patch application or trading. Outputs bounded metadata only.
"""
import argparse,json,os,sys,time

DEFAULT_MODEL="Qwen/Qwen2.5-0.5B-Instruct"
PROMPT="Write one Python function named add that returns the sum of two integers. Return code only."

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--model",default=DEFAULT_MODEL,choices=[DEFAULT_MODEL])
    parser.add_argument("--output",default="artifacts/cloud-model-smoke.json")
    args=parser.parse_args()
    start=time.monotonic()
    report={"model":args.model,"provider":"qwen","mode":"cpu_local_weights",
            "model_called":False,"generation_completed":False,
            "patch_applied":False,"harness_passed":False,
            "paid_api_used":False,"secrets_used":False}
    try:
        os.environ["HF_HUB_DISABLE_TELEMETRY"]="1"
        os.environ["TOKENIZERS_PARALLELISM"]="false"
        import torch
        from transformers import AutoModelForCausalLM,AutoTokenizer
        from scripts.model_feedback_loop import run_loop,save_report
        tokenizer=AutoTokenizer.from_pretrained(args.model,trust_remote_code=False)
        model=AutoModelForCausalLM.from_pretrained(args.model,trust_remote_code=False,torch_dtype=torch.float32)
        model.eval()
        def generate(task):
            prompt=tokenizer.apply_chat_template([{"role":"user","content":task}],tokenize=False,add_generation_prompt=True)
            inputs=tokenizer(prompt,return_tensors="pt")
            with torch.inference_mode():
                generated=model.generate(**inputs,max_new_tokens=96,do_sample=False,
                                         pad_token_id=tokenizer.eos_token_id)
            return tokenizer.decode(generated[0][inputs["input_ids"].shape[1]:],skip_special_tokens=True)
        result=run_loop(generate,max_attempts=3)
        report.update(model_called=True,generation_completed=True,
                      output_chars=len(result["attempts"][-1]["output_preview"]),
                      output_preview=result["attempts"][-1]["output_preview"],
                      feedback_passed=result["passed"],feedback_attempts=result["attempts"],
                      model_output_executed=False)
        if not result["passed"]:raise ValueError("bounded static feedback validation failed")
        return_code=0
    except Exception as exc:
        report["error_type"]=type(exc).__name__
        report["error_message"]=str(exc)[:400]
        return_code=2
    finally:
        report["duration_seconds"]=round(time.monotonic()-start,2)
        os.makedirs(os.path.dirname(args.output) or ".",exist_ok=True)
        with open(args.output,"w",encoding="utf-8") as handle:
            json.dump(report,handle,indent=2,sort_keys=True)
            handle.write("\n")
        print(json.dumps(report,sort_keys=True))
    return return_code
if __name__=="__main__":sys.exit(main())
