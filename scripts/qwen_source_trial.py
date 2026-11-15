#!/usr/bin/env python3
"""Experimental Qwen CPU proposal for a real Python source guard.

Never writes to the working source, executes model code or merges a PR.
A rejected proposal is a truthful experimental result, not an approved patch.
"""
import hashlib
import json
import os
from pathlib import Path

try:
    from .qwen_source_guard import TARGET, ORIGINAL, TASK, inspect_line
except ImportError:
    from qwen_source_guard import TARGET, ORIGINAL, TASK, inspect_line

MODEL = "Qwen/Qwen2.5-Coder-0.5B-Instruct"
REPORT = Path("artifacts/source-guard-qwen-report.json")
CANDIDATE = Path("artifacts/source-guard-qwen-candidate.json")

def normalize_model_line(raw):
    """Normalize cosmetic fences only; never weaken the AST guard."""
    if not isinstance(raw, str) or len(raw) > 350 or "\r" in raw or "\x00" in raw:
        raise ValueError("unsafe model response")
    line = raw.removesuffix("\n")
    fence = chr(96) * 3
    for opening in (fence + "python\n", fence + "\n"):
        if line.startswith(opening) and line.endswith("\n" + fence):
            line = line[len(opening):-(len(fence) + 1)]
            break
    if "\n" in line:
        raise ValueError("multiple model source lines")
    if line.startswith("if "):
        line = "    " + line
    return line

def evaluate_response(raw, source):
    if not isinstance(raw, str):
        raise ValueError("nontext model response")
    normalized = normalize_model_line(raw)
    result = inspect_line(normalized, source)
    return {"status": "accepted_for_disposable_review",
            "normalized_line": normalized,
            "raw_response_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            "task_id": TASK["task_id"], "source_sha256": result["source_sha256"],
            "model_line_sha256": result["model_line_sha256"],
            "source_patch": result["patch"], "source_ast_guard_verified": True,
            "patch_applied_to_checkout": False, "merge_authorized": False}

def main():
    report = {"status": "not_started", "model": MODEL, "task_id": TASK["task_id"],
              "model_calls": 0, "paid_api_used": False, "secrets_used": False,
              "source_checkout_modified": False, "model_code_executed": False,
              "merge_authorized": False, "attempts": []}
    try:
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
        os.environ["TOKENIZERS_PARALLELISM"] = "false"
        from transformers import AutoTokenizer, AutoModelForCausalLM
        import torch
        path = Path(TARGET)
        if path.is_symlink() or not path.is_file():
            raise ValueError("unsafe source file")
        source = path.read_text(encoding="utf-8")
        if len(source.encode("utf-8")) > 12000 or source.count(ORIGINAL) != 1:
            raise ValueError("source is untrusted or too large")
        report["source_sha256"] = hashlib.sha256(source.encode("utf-8")).hexdigest()
        tokenizer = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=False)
        model = AutoModelForCausalLM.from_pretrained(
            MODEL, trust_remote_code=False, torch_dtype=torch.float32)
        model.eval()
        reason = None
        for attempt in range(2):
            prompt = (
                "Repair this ONE Python source line for feedback_controller.feedback. "
                "It must reject missing, boolean, non-integer or non-positive cycle. "
                "Retain the original invalid proposal checks. "
                "Use short-circuit OR, checking type(proposal.get(\"cycle\")) is not int "
                "before comparing proposal[\"cycle\"] < 1. "
                "Output exactly one full Python source line starting with 4 spaces and 'if '. "
                "Do not output Markdown, explanatory text, or additional code.\n"
                "Original line:\n" + ORIGINAL + "\n"
            )
            if reason:
                prompt += (
                    "Previous output was rejected by the source AST gate. "
                    "Do not rewrite the old condition. Extend it with BOTH "
                    "additional short-circuit OR checks: "
                    "type(proposal.get(\"cycle\")) is not int AND "
                    "proposal[\"cycle\"] < 1. "
                    "Each must be a Python 'or' clause in one continued if line; "
                    "finish with a single colon. No fences or explanatory text.\n"
                )
            inputs = tokenizer(tokenizer.apply_chat_template(
                [{"role": "user", "content": prompt}], tokenize=False,
                add_generation_prompt=True), return_tensors="pt")
            report["model_calls"] += 1
            with torch.inference_mode():
                output = model.generate(**inputs, max_new_tokens=160, do_sample=False,
                                        pad_token_id=tokenizer.eos_token_id)
            raw = tokenizer.decode(output[0][inputs["input_ids"].shape[1]:],
                                   skip_special_tokens=True)
            row = {"attempt": attempt + 1,
                   "response_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                   "response_length": len(raw),
                   "response_preview": raw[:350]}
            try:
                candidate = evaluate_response(raw, source)
                row["status"] = "accepted"
                report["attempts"].append(row)
                payload = {"provider": "qwen", "status": "proposal",
                           "task_id": TASK["task_id"], "raw_response": raw,
                           "line": candidate["normalized_line"],
                           "source_patch": candidate["source_patch"],
                           "source_sha256": candidate["source_sha256"],
                           "model_line_sha256": candidate["model_line_sha256"]}
                CANDIDATE.parent.mkdir(parents=True, exist_ok=True)
                encoded = json.dumps(payload, sort_keys=True, indent=2) + "\n"
                CANDIDATE.write_text(encoded, encoding="utf-8")
                report["candidate_sha256"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
                report["status"] = "accepted_for_disposable_review"
                break
            except (ValueError, SyntaxError) as exc:
                reason = type(exc).__name__  # Never relay raw untrusted content as instructions.
                row["status"] = "rejected"
                row["reason_type"] = reason
                report["attempts"].append(row)
                report["status"] = "model_proposal_rejected"
    except Exception as exc:
        report["status"] = "error"
        report["error_type"] = type(exc).__name__
        report["error_message"] = str(exc)[:200]
    finally:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "accepted_for_disposable_review" else 2

if __name__ == "__main__":
    raise SystemExit(main())
