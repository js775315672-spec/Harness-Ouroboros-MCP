#!/usr/bin/env python3
"""Bounded Qwen repository patch proposals: no execution, application or merge."""
import ast
import hashlib
import json
import os
import re
from pathlib import Path

try:
    from .real_repo_task import prepare
    from .scoped_patch_gate import inspect_scoped_patch
    from .replacement_proposal import build_single_line_diff
except ImportError:
    from real_repo_task import prepare
    from scoped_patch_gate import inspect_scoped_patch
    from replacement_proposal import build_single_line_diff

MODEL="Qwen/Qwen2.5-0.5B-Instruct"
TARGET=Path("tests/test_model_feedback_loop.py")
OUTPUT=Path("artifacts/real-repo-qwen-proposal.json")

def _target_line(source):
    lines=source.splitlines()
    matches=[i for i,line in enumerate(lines)
             if line.strip()=="def test_reject_multiple_fences(self):"]
    if len(matches)!=1:
        raise ValueError("unique target regression test not found")
    index=matches[0]+1
    if index>=len(lines) or not lines[index].startswith('        answer='):
        raise ValueError("target assignment not found")
    return index+1,lines[index]

def prompt_for_attempt(goal,source,reason=None):
    number,line=_target_line(source)
    prompt=(
        "You are fixing one Python unittest string literal. "
        "The current string contains literal backslash-n instead of actual "
        "newlines after Python evaluates it. "
        "Replace double backslashes with single backslashes before n. "
        "Output EXACTLY ONE complete Python source line, starting with "
        "eight spaces followed by answer=. "
        "No diff, no Markdown, no commentary, no extra lines.\n"
        f"Original source line {number}:\n{line}\n"
    )
    if reason:
        prompt+=f"Your previous one-line proposal failed validation: {reason[:160]}. Fix and output one line only.\n"
    return prompt

def _check_one_line_change(raw,source):
    lines=raw.splitlines()
    if len(lines)!=6:
        raise ValueError("task requires exactly one two-line replacement hunk")
    match=re.fullmatch(r"@@ -(\d+)(?:,1)? \+(\d+)(?:,1)? @@",lines[3])
    number,original=_target_line(source)
    if not match or int(match.group(1))!=number or int(match.group(2))!=number:
        raise ValueError("hunk must point to the real regression assignment")
    if lines[4]!="-"+original:
        raise ValueError("removed line must match repository source exactly")
    replacement=lines[5][1:]
    if not lines[5].startswith("+        answer=") or replacement==original:
        raise ValueError("only the assignment may change")
    current=source.splitlines(keepends=True)
    current[number-1]=replacement+"\n"
    tree=ast.parse("".join(current))
    target_class=next((n for n in tree.body
                       if isinstance(n,ast.ClassDef) and n.name=="FeedbackLoopTests"),None)
    if target_class is None:
        raise ValueError("test class not found")
    methods=[n for n in target_class.body if isinstance(n,ast.FunctionDef)
             and n.name=="test_reject_multiple_fences"]
    if len(methods)!=1 or not methods[0].body:
        raise ValueError("target method invalid")
    assignment=methods[0].body[0]
    if not isinstance(assignment,ast.Assign) or len(assignment.targets)!=1:
        raise ValueError("target assignment altered")
    if not isinstance(assignment.targets[0],ast.Name) or assignment.targets[0].id!="answer":
        raise ValueError("answer variable missing")
    value=assignment.value
    fence=chr(96)*3
    if not isinstance(value,ast.Constant) or not isinstance(value.value,str):
        raise ValueError("answer must remain a string literal")
    if value.value.count(fence+"python")!=2 or value.value.count(fence)!=4:
        raise ValueError("test must retain two Python code fences")
    if "\n" not in value.value or "\\n" in value.value:
        raise ValueError("test input must use real newlines, not literal backslash-n")
    return {"line":number,"source_content_matched":True,
            "python_ast_parsed":True,"test_fixture_real_newlines":True}

def assess(raw,task,source=None):
    proposal={"provider":"qwen","status":"proposal",
              "summary":"One-shot model-generated regression-test diff","patch":raw}
    try:
        inspection=inspect_scoped_patch(task,proposal)
        if source is not None:
            inspection["source_context"]=_check_one_line_change(raw,source)
        return {"status":"accepted_for_review","reason":None,"inspection":inspection}
    except (ValueError,TypeError,KeyError,SyntaxError) as exc:
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
        report["task_id"]=task["task"]["task_id"]
        report["inspection_kind"]="static_scope_structure_source_and_ast_only"
        report["model_output_format"]="single_python_assignment_line"
        report["patch_origin"]="deterministic_single_line_builder"
        tokenizer=AutoTokenizer.from_pretrained(MODEL,trust_remote_code=False)
        model=AutoModelForCausalLM.from_pretrained(
            MODEL,trust_remote_code=False,torch_dtype=torch.float32)
        model.eval()
        attempts=[]
        reason=None
        for attempt in range(task["contract"]["max_attempts"]):
            prompt=prompt_for_attempt(task["prompt"],source,reason)
            tokens=tokenizer(tokenizer.apply_chat_template(
                [{"role":"user","content":prompt}],tokenize=False,
                add_generation_prompt=True),return_tensors="pt")
            report["real_model_calls"]+=1
            with torch.inference_mode():
                output=model.generate(**tokens,max_new_tokens=256,do_sample=False,
                                      pad_token_id=tokenizer.eos_token_id)
            raw=tokenizer.decode(output[0][tokens["input_ids"].shape[1]:],
                                 skip_special_tokens=True)
            patch_hash=None
            try:
                number,old_line=_target_line(source)
                proposed_diff=build_single_line_diff(raw,old_line,number)
                patch_hash=hashlib.sha256(proposed_diff.encode("utf-8")).hexdigest()
                assessment=assess(proposed_diff,task["task"],source)
            except ValueError as exc:
                assessment={"status":"rejected","reason":str(exc)[:300],"inspection":None}
            attempts.append({"attempt":attempt+1,
                             "response_sha256":hashlib.sha256(raw.encode()).hexdigest(),
                             "response_chars":len(raw),"response_preview":raw[:1600],
                             "synthesized_patch_sha256":patch_hash,
                             "response_ends_with_newline":raw.endswith("\n"),
                             "status":assessment["status"],"reason":assessment["reason"]})
            report.update(assessment)
            if assessment["status"]=="accepted_for_review":
                break
            reason=assessment["reason"]
        report["attempts"]=attempts
        report["max_attempts"]=task["contract"]["max_attempts"]
    except Exception as exc:
        report["status"]="error"
        report["error_type"]=type(exc).__name__
        report["error_message"]=str(exc)[:300]
    finally:
        OUTPUT.parent.mkdir(parents=True,exist_ok=True)
        OUTPUT.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",
                          encoding="utf-8")
        print(json.dumps(report,sort_keys=True))
    return 0 if report["status"]=="accepted_for_review" else 2

if __name__=="__main__":
    raise SystemExit(main())
