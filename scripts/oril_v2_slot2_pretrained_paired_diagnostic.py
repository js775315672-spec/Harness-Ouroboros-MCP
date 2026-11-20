#!/usr/bin/env python3
"""Actual pretrained Qwen CPU prompt-pair diagnostic; NOT LoRA or heldout evaluation.

Same pinned public model and exact public questions; prompt lengths and paired
timings are measured, not assumed. No quality or speed gain claims.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import time

try:
    from .oril_v2_pretrained_qwen_cpu_smoke import (
        MODEL_ID, build_masked_inputs, sha256_file,
    )
except ImportError:
    from oril_v2_pretrained_qwen_cpu_smoke import (
        MODEL_ID, build_masked_inputs, sha256_file,
    )

# Public diagnostic questions, never call these "heldout".
QUESTIONS = [
    ("What is 2 plus 3? Answer with one digit.", "5"),
    ("What is 7 minus 4? Answer with one digit.", "3"),
    ("What is 3 times 3? Answer with one digit.", "9"),
    ("What is 8 divided by 2? Answer with one digit.", "4"),
]
VERBOSE = ("You are an expert mathematical assistant. Please carefully read "
           "the question, avoid unrelated text, and provide only the final "
           "single digit. Do not explain your reasoning or add commentary.")
COMPACT = "Reply with only the digit."
LABELS = ("verbose", "compact")


def validate_report(report):
    if (not isinstance(report, dict) or report.get("model_id") != MODEL_ID
            or report.get("pretrained_checkpoint_loaded") is not True
            or report.get("weights_trained_this_run") is not False
            or report.get("gpu_lora_training_proven") is not False
            or report.get("independent_heldout_accuracy_proven") is not False
            or report.get("quality_gain") is not None
            or report.get("speed_gain") is not None):
        raise ValueError("false provenance or model improvement claim")
    rev = report.get("resolved_revision")
    if not isinstance(rev, str) or len(rev) != 40 or any(c not in "0123456789abcdef" for c in rev):
        raise ValueError("unresolved checkpoint revision")
    weights = report.get("weight_files")
    if not isinstance(weights, list) or not weights:
        raise ValueError("no weights")
    for weight in weights:
        if (not isinstance(weight, dict)
                or type(weight.get("bytes")) is not int or weight["bytes"] <= 0
                or not isinstance(weight.get("sha256"), str)
                or len(weight["sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in weight["sha256"])):
            raise ValueError("invalid weight evidence")
    rows = report.get("pairs")
    if not isinstance(rows, list) or len(rows) != len(QUESTIONS):
        raise ValueError("missing paired observations")
    seen = set()
    for i, pair in enumerate(rows):
        if (not isinstance(pair, dict) or pair.get("question_id") != i + 1
                or pair.get("execution_order") != (
                    ["verbose", "compact"] if i % 2 == 0 else ["compact", "verbose"]
                )):
            raise ValueError("order not observed/counterbalanced")
        records = pair.get("observations")
        if not isinstance(records, list) or len(records) != 2:
            raise ValueError("missing observations")
        if [r.get("variant") for r in records if isinstance(r, dict)] != pair["execution_order"]:
            raise ValueError("execution order mismatch")
        for r in records:
            if (type(r.get("input_tokens")) is not int or r["input_tokens"] <= 0
                    or type(r.get("generated_tokens")) is not int or not 1 <= r["generated_tokens"] <= 16
                    or type(r.get("elapsed_seconds")) not in (int, float)
                    or not math.isfinite(r["elapsed_seconds"]) or r["elapsed_seconds"] <= 0
                    or r.get("attention_mask_explicit") is not True
                    or not isinstance(r.get("output"), str)
                    or not r["output"].strip()
                    or type(r.get("exact_public_answer_match")) is not bool):
                raise ValueError("invalid real observation")
        seen.add(i + 1)
    if len(seen) != len(QUESTIONS):
        raise ValueError("duplicate question")
    return True


def measure(model, tokenizer, torch, question, expected, variant):
    instruction = VERBOSE if variant == "verbose" else COMPACT
    chat = [{"role": "system", "content": instruction},
            {"role": "user", "content": question}]
    inputs = build_masked_inputs(tokenizer, chat, torch)
    start = time.perf_counter()
    with torch.inference_mode():
        output = model.generate(**inputs, do_sample=False, max_new_tokens=16,
                                pad_token_id=tokenizer.eos_token_id)
    elapsed = time.perf_counter() - start
    generated = output[0][inputs["input_ids"].shape[1]:]
    decoded = tokenizer.decode(generated, skip_special_tokens=True)
    return {
        "variant": variant,
        "input_tokens": int(inputs["input_ids"].shape[1]),
        "generated_tokens": int(generated.shape[0]),
        "elapsed_seconds": round(elapsed, 6),
        "attention_mask_explicit": True,
        "output": decoded,
        "exact_public_answer_match": decoded.strip() == expected,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True)
    args = p.parse_args()
    dest = Path(args.output)
    if dest.exists() or dest.is_symlink():
        raise ValueError("refuse overwrite")
    import torch
    from huggingface_hub import HfApi, snapshot_download
    from transformers import AutoModelForCausalLM, AutoTokenizer
    torch.set_num_threads(2)
    torch.manual_seed(42)
    revision = HfApi().model_info(MODEL_ID).sha
    if not isinstance(revision, str) or len(revision) != 40:
        raise ValueError("unresolved model")
    path = Path(snapshot_download(
        repo_id=MODEL_ID, revision=revision,
        allow_patterns=["*.json", "*.safetensors", "*.model", "*.tiktoken", "*.txt"]))
    weights = sorted(path.glob("*.safetensors"))
    if not weights:
        raise ValueError("no pretrained checkpoint")
    weight_files = [{"name": f.name, "bytes": f.stat().st_size, "sha256": sha256_file(f)}
                    for f in weights]
    tokenizer = AutoTokenizer.from_pretrained(str(path), local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        str(path), local_files_only=True, torch_dtype=torch.float32).eval()
    pairs = []
    for i, (question, expected) in enumerate(QUESTIONS):
        order = ["verbose", "compact"] if i % 2 == 0 else ["compact", "verbose"]
        observations = [measure(model, tokenizer, torch, question, expected, variant)
                        for variant in order]
        pairs.append({"question_id": i + 1, "execution_order": order,
                      "observations": observations})
    report = {
        "schema_version": 1, "model_id": MODEL_ID, "resolved_revision": revision,
        "weight_files": weight_files, "pretrained_checkpoint_loaded": True,
        "weights_trained_this_run": False, "gpu_lora_training_proven": False,
        "independent_heldout_accuracy_proven": False, "quality_gain": None,
        "speed_gain": None, "pairs": pairs,
        "environment": {"torch": torch.__version__, "cpu_only": not torch.cuda.is_available()},
        "notes": "Four public arithmetic prompts, 8 CPU calls, no independent heldout or LoRA; descriptive measurements only.",
    }
    validate_report(report)
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "pairs": len(pairs),
        "calls": sum(len(x["observations"]) for x in pairs),
        "total_input_tokens": {
            k: sum(next(o["input_tokens"] for o in pair["observations"] if o["variant"] == k)
                   for pair in pairs) for k in LABELS},
        "public_exact_matches": {
            k: sum(next(o["exact_public_answer_match"] for o in pair["observations"] if o["variant"] == k)
                   for pair in pairs) for k in LABELS},
        "elapsed_seconds": {
            k: [next(o["elapsed_seconds"] for o in pair["observations"] if o["variant"] == k)
                for pair in pairs] for k in LABELS},
        "independent_heldout_accuracy_proven": False,
        "gpu_lora_training_proven": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
