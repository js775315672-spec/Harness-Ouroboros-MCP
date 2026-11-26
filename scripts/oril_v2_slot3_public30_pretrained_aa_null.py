#!/usr/bin/env python3
"""Real pretrained Qwen CPU A/A null control over 30 PUBLIC arithmetic groups.

Two identical compact prompts per group, with a single model load. Not hidden
evaluation, GPU training, causal speed attribution, or model improvement.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

from oril_v2_slot1_30_public_qwen_pairs import public_tasks
from oril_v2_slot2_pretrained_paired_diagnostic import measure
from oril_v2_pretrained_qwen_cpu_smoke import MODEL_ID, sha256_file


def audit_null(rows):
    tasks = public_tasks()
    if not isinstance(rows, list) or len(rows) != len(tasks):
        raise ValueError("expected exactly 30 public groups")
    signed, absolute, times, tokens = [], [], [], []
    for i, (task, row) in enumerate(zip(tasks, rows)):
        if not isinstance(row, dict) or row.get("group_id") != task["group_id"] or row.get("question") != task["question"] or row.get("expected") != task["expected"]:
            raise ValueError("missing or reordered public group")
        obs = row.get("observations")
        if not isinstance(obs, list) or len(obs) != 2:
            raise ValueError("exactly two A/A observations required")
        pair = []
        for j, x in enumerate(obs):
            if not isinstance(x, dict) or x.get("variant") != "compact":
                raise ValueError("A/A must use identical compact prompt")
            if type(x.get("input_tokens")) is not int or x["input_tokens"] <= 0:
                raise ValueError("invalid input tokens")
            if type(x.get("generated_tokens")) is not int or not 1 <= x["generated_tokens"] <= 16:
                raise ValueError("invalid output tokens")
            if type(x.get("elapsed_seconds")) not in (int, float) or not math.isfinite(x["elapsed_seconds"]) or x["elapsed_seconds"] <= 0:
                raise ValueError("invalid timing")
            if x.get("attention_mask_explicit") is not True or not isinstance(x.get("output"), str) or not x["output"].strip():
                raise ValueError("invalid model output")
            if type(x.get("exact_public_answer_match")) is not bool or x["exact_public_answer_match"] != (x["output"].strip() == task["expected"]):
                raise ValueError("untrusted public label")
            pair.append(x)
        if pair[0]["input_tokens"] != pair[1]["input_tokens"]:
            raise ValueError("identical A/A prompt token counts must match")
        a, b = (x["elapsed_seconds"] for x in pair)
        signed.append(b - a)
        absolute.append(abs(b - a))
        times.extend([a, b])
        tokens.append(pair[0]["input_tokens"])
    return {
        "public_groups": 30, "actual_calls_claimed": 60,
        "same_prompt_token_count_mismatches": 0,
        "median_signed_second_minus_first_seconds": round(statistics.median(signed), 6),
        "median_absolute_pair_drift_seconds": round(statistics.median(absolute), 6),
        "median_call_seconds": round(statistics.median(times), 6),
        "compact_input_tokens_per_call_total": sum(tokens),
        "independent_heldout_accuracy_proven": False,
        "gpu_lora_training_proven": False,
        "model_quality_gain_proven": False,
        "causal_speed_gain_proven": False,
        "decision": "판단불가",
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
    if not isinstance(revision, str) or len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
        raise ValueError("unresolved model revision")
    path = Path(snapshot_download(repo_id=MODEL_ID, revision=revision,
                                 allow_patterns=["*.json", "*.safetensors", "*.model", "*.tiktoken", "*.txt"]))
    weights = sorted(path.glob("*.safetensors"))
    if not weights:
        raise ValueError("no pretrained weights")
    weight_files = [{"name": f.name, "bytes": f.stat().st_size, "sha256": sha256_file(f)} for f in weights]
    tokenizer = AutoTokenizer.from_pretrained(str(path), local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        str(path), local_files_only=True, torch_dtype=torch.float32).eval()
    rows = []
    for task in public_tasks():
        obs = [measure(model, tokenizer, torch, task["question"], task["expected"], "compact")
               for _ in range(2)]
        rows.append({**task, "observations": obs})
    report = {
        "schema_version": 1, "model_id": MODEL_ID, "resolved_revision": revision,
        "weight_files": weight_files, "pretrained_checkpoint_loaded": True,
        "weights_trained_this_run": False, "gpu_lora_training_proven": False,
        "independent_heldout_accuracy_proven": False, "quality_gain": None,
        "speed_gain": None,
        "public_tasks_sha256": hashlib.sha256(json.dumps(public_tasks(), sort_keys=True).encode()).hexdigest(),
        "rows": rows, "summary": audit_null(rows),
        "note": "Public A/A repeated identical compact prompts. Execution and provenance self-reported; no hidden eval or causal attribution.",
    }
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
