#!/usr/bin/env python3
"""Live CPU Qwen trial: no answer template, real Docker feedback, no checkout edit.

No secrets, paid inference, deployment, branch write, or merge capability.
A failed attempt is reported as failed; never relabel as a successful repair.
"""
import hashlib
import json
import os
from pathlib import Path

try:
    from .qwen_source_guard import TARGET
    from .qwen_source_trial import MODEL as LEGACY_MODEL
    from .qwen_semantic_repair_loop import run_loop
    from .qwen_semantic_disposable_compare import compare_line
except ImportError:
    from qwen_source_guard import TARGET
    from qwen_source_trial import MODEL as LEGACY_MODEL
    from qwen_semantic_repair_loop import run_loop
    from qwen_semantic_disposable_compare import compare_line

MODEL = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
REPORT = Path("artifacts/semantic-qwen-report.json")
CANDIDATE = Path("artifacts/semantic-qwen-candidate.json")


def main():
    report = {
        "status": "not_started", "model": MODEL,
        "source_checkout_modified": False, "merge_authorized": False,
        "paid_api_used": False, "secrets_used": False,
    }
    try:
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
        os.environ["TOKENIZERS_PARALLELISM"] = "false"
        from transformers import AutoTokenizer, AutoModelForCausalLM
        import torch
        target = Path(TARGET)
        if target.is_symlink() or not target.is_file():
            raise ValueError("unsafe source path")
        source = target.read_text(encoding="utf-8")
        before = hashlib.sha256(source.encode("utf-8")).hexdigest()
        tokenizer = AutoTokenizer.from_pretrained(
            MODEL, trust_remote_code=False)
        model = AutoModelForCausalLM.from_pretrained(
            MODEL, trust_remote_code=False, torch_dtype=torch.bfloat16)
        model.eval()

        def generate(prompt):
            inputs = tokenizer(tokenizer.apply_chat_template(
                [{"role": "user", "content": prompt}], tokenize=False,
                add_generation_prompt=True), return_tensors="pt")
            with torch.inference_mode():
                output = model.generate(
                    **inputs, max_new_tokens=120, do_sample=False,
                    pad_token_id=tokenizer.eos_token_id)
            return tokenizer.decode(
                output[0][inputs["input_ids"].shape[1]:],
                skip_special_tokens=True)

        result = run_loop(
            source, generate, lambda line: compare_line(Path("."), line))
        candidate = result.pop("candidate")
        if hashlib.sha256(target.read_bytes()).hexdigest() != before:
            raise ValueError("source checkout changed unexpectedly")
        report.update(result)
        report["source_sha256"] = before
        if candidate is not None:
            CANDIDATE.parent.mkdir(parents=True, exist_ok=True)
            encoded = json.dumps(candidate, sort_keys=True, indent=2) + "\n"
            CANDIDATE.write_text(encoded, encoding="utf-8")
            report["candidate_sha256"] = hashlib.sha256(encoded.encode()).hexdigest()
            report["review_required"] = True
        else:
            report["review_required"] = False
    except Exception as exc:
        report["status"] = "blocked"
        report["error_type"] = type(exc).__name__
        report["error_description"] = str(exc)[:160]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "isolated_source_repair_passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
