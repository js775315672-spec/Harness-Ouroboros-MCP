#!/usr/bin/env python3
"""Run a real pretrained Qwen inference smoke, not LoRA training or heldout evaluation.

Downloads pinned-by-resolved-revision model weights on the runner and records
their bytes/hash. Never claims improved intelligence or independent accuracy.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"
PROMPTS = [
    "In one sentence, explain why a heldout evaluation must be isolated from training.",
    "In one sentence, state one risk of evaluating a model only on its training data.",
]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def validate_report(report):
    if report.get("model_id") != MODEL_ID:
        raise ValueError("wrong model")
    if not isinstance(report.get("resolved_revision"), str) or len(report["resolved_revision"]) != 40:
        raise ValueError("unresolved revision")
    if not report.get("pretrained_checkpoint_loaded") or report.get("weights_trained_this_run"):
        raise ValueError("not a pretrained inference-only run")
    if report.get("gpu_lora_training_proven") or report.get("independent_heldout_accuracy_proven"):
        raise ValueError("false training/evaluation claim")
    files = report.get("weight_files")
    if not isinstance(files, list) or not files:
        raise ValueError("missing checkpoint weight evidence")
    if not all(isinstance(f.get("bytes"), int) and f["bytes"] > 0
               and isinstance(f.get("sha256"), str) and len(f["sha256"]) == 64 for f in files):
        raise ValueError("invalid weight evidence")
    if len(report.get("inferences", [])) != 2:
        raise ValueError("expected two actual model inferences")
    for result in report["inferences"]:
        if (not isinstance(result.get("input_tokens"), int) or result["input_tokens"] < 1
                or not isinstance(result.get("generated_tokens"), int)
                or result["generated_tokens"] < 1
                or not isinstance(result.get("elapsed_seconds"), (int, float))
                or result["elapsed_seconds"] <= 0
                or not isinstance(result.get("output"), str) or not result["output"].strip()):
            raise ValueError("invalid inference evidence")
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True)
    p.add_argument("--max-new-tokens", type=int, default=16)
    args = p.parse_args()
    if not 1 <= args.max_new_tokens <= 32:
        raise ValueError("bounded generation only")
    # Avoid any secrets in artifact; use public model and fixed task prompts only.
    import torch
    from huggingface_hub import HfApi, snapshot_download
    from transformers import AutoModelForCausalLM, AutoTokenizer
    torch.set_num_threads(2)
    torch.manual_seed(42)
    resolved = HfApi().model_info(MODEL_ID).sha
    if not isinstance(resolved, str) or len(resolved) != 40:
        raise ValueError("unresolved model commit")
    path = Path(snapshot_download(
        repo_id=MODEL_ID, revision=resolved,
        allow_patterns=["*.json", "*.safetensors", "*.model", "*.tiktoken", "*.txt"],
    ))
    weights = sorted(path.glob("*.safetensors"))
    if not weights:
        raise ValueError("no actual pretrained safetensors checkpoint")
    evidence = [{"name": w.name, "bytes": w.stat().st_size, "sha256": sha256_file(w)}
                for w in weights]
    tokenizer = AutoTokenizer.from_pretrained(str(path), local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        str(path), local_files_only=True, torch_dtype=torch.float32).eval()
    inferences = []
    for prompt in PROMPTS:
        chat = [{"role": "user", "content": prompt}]
        inputs = tokenizer.apply_chat_template(chat, tokenize=True,
                                                add_generation_prompt=True,
                                                return_tensors="pt")
        start = time.perf_counter()
        with torch.inference_mode():
            output = model.generate(inputs, do_sample=False, max_new_tokens=args.max_new_tokens,
                                    pad_token_id=tokenizer.eos_token_id)
        elapsed = time.perf_counter() - start
        generated = output[0][inputs.shape[1]:]
        decoded = tokenizer.decode(generated, skip_special_tokens=True)
        inferences.append({
            "prompt_id": len(inferences) + 1,
            "input_tokens": int(inputs.shape[1]),
            "generated_tokens": int(generated.shape[0]),
            "elapsed_seconds": round(elapsed, 6),
            "output": decoded,
        })
    report = {
        "schema_version": 1,
        "model_id": MODEL_ID,
        "resolved_revision": resolved,
        "weight_files": evidence,
        "pretrained_checkpoint_loaded": True,
        "weights_trained_this_run": False,
        "gpu_lora_training_proven": False,
        "independent_heldout_accuracy_proven": False,
        "quality_gain": None,
        "inferences": inferences,
        "environment": {"torch": torch.__version__, "cpu_only": not torch.cuda.is_available()},
    }
    validate_report(report)
    dest = Path(args.output)
    if dest.exists() or dest.is_symlink():
        raise ValueError("refuse to overwrite existing report")
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "model_id": MODEL_ID, "resolved_revision": resolved,
        "weight_file_count": len(evidence), "weight_bytes": sum(f["bytes"] for f in evidence),
        "input_tokens": [x["input_tokens"] for x in inferences],
        "generated_tokens": [x["generated_tokens"] for x in inferences],
        "elapsed_seconds": [x["elapsed_seconds"] for x in inferences],
        "pretrained_inference_completed": True, "gpu_lora_training_proven": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
