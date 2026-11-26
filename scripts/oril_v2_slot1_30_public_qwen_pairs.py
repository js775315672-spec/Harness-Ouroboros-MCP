#!/usr/bin/env python3
"""30 public arithmetic groups, 60 actual pretrained Qwen CPU calls.

This is a descriptive PUBLIC diagnostic, not a heldout test, LoRA training,
or a claim of accuracy/speed improvement. Reuses pinned model/measurement
implementation from slot2. Each pair is counterbalanced; no new dependencies.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import time

from oril_v2_slot2_pretrained_paired_diagnostic import measure
from oril_v2_pretrained_qwen_cpu_smoke import MODEL_ID, sha256_file


def public_tasks():
    # Unique public prompts. A generated sequence avoids handpicked successes.
    tasks = []
    for i in range(30):
        a = 11 + i * 3
        b = 2 + i % 7
        question = f"What is {a} plus {b}? Answer with only the integer."
        tasks.append({"group_id": f"public-arithmetic-{i+1:02d}",
                      "question": question, "expected": str(a+b)})
    assert len({x["question"] for x in tasks}) == 30
    return tasks


def summarize(rows):
    if len(rows) != 30:
        raise ValueError("expected 30 independent public groups")
    ids = set()
    totals = {"verbose": {"input_tokens": 0, "correct": 0, "latencies": []},
              "compact": {"input_tokens": 0, "correct": 0, "latencies": []}}
    for i, row in enumerate(rows):
        if row.get("group_id") in ids or row.get("group_id") != public_tasks()[i]["group_id"]:
            raise ValueError("duplicate or reordered group")
        ids.add(row["group_id"])
        if row.get("question") != public_tasks()[i]["question"]:
            raise ValueError("public question mismatch")
        if row.get("expected") != public_tasks()[i]["expected"]:
            raise ValueError("public answer mismatch")
        expected_order = ["verbose", "compact"] if i % 2 == 0 else ["compact", "verbose"]
        if row.get("execution_order") != expected_order:
            raise ValueError("not counterbalanced")
        obs = row.get("observations")
        if not isinstance(obs, list) or len(obs) != 2 or [x.get("variant") for x in obs] != expected_order:
            raise ValueError("missing or reordered observations")
        for x in obs:
            if type(x.get("input_tokens")) is not int or x["input_tokens"] <= 0:
                raise ValueError("invalid tokens")
            if type(x.get("elapsed_seconds")) not in (int, float) or not 0 < x["elapsed_seconds"] < 86400:
                raise ValueError("invalid timing")
            if not isinstance(x.get("output"), str) or not x["output"].strip():
                raise ValueError("invalid output")
            if x.get("attention_mask_explicit") is not True:
                raise ValueError("missing attention mask")
            correct = x["output"].strip() == row["expected"]
            if type(x.get("exact_public_answer_match")) is not bool or x["exact_public_answer_match"] != correct:
                raise ValueError("incorrect self-reported label")
            entry = totals[x["variant"]]
            entry["input_tokens"] += x["input_tokens"]
            entry["correct"] += int(correct)
            entry["latencies"].append(x["elapsed_seconds"])
    verbose = totals["verbose"]
    compact = totals["compact"]
    return {
        "public_groups": 30, "actual_calls_claimed": 60,
        "input_tokens": {k: totals[k]["input_tokens"] for k in totals},
        "public_exact_matches": {k: totals[k]["correct"] for k in totals},
        "latency_median_seconds": {k: round(statistics.median(totals[k]["latencies"]), 6) for k in totals},
        "input_token_saving_pct_descriptive":
            round(100*(1-compact["input_tokens"]/verbose["input_tokens"]), 3),
        "quality_gain_proven": False, "speed_gain_proven": False,
        "independent_heldout_accuracy_proven": False,
        "gpu_lora_training_proven": False,
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
    if not isinstance(revision, str) or len(revision) != 40:
        raise ValueError("unresolved model revision")
    path = Path(snapshot_download(
        repo_id=MODEL_ID, revision=revision,
        allow_patterns=["*.json", "*.safetensors", "*.model", "*.tiktoken", "*.txt"]))
    weights = sorted(path.glob("*.safetensors"))
    if not weights:
        raise ValueError("no pretrained weights")
    files = [{"name": f.name, "bytes": f.stat().st_size, "sha256": sha256_file(f)}
             for f in weights]
    tokenizer = AutoTokenizer.from_pretrained(str(path), local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        str(path), local_files_only=True, torch_dtype=torch.float32).eval()
    rows = []
    for i, task in enumerate(public_tasks()):
        order = ["verbose", "compact"] if i % 2 == 0 else ["compact", "verbose"]
        obs = [measure(model, tokenizer, torch, task["question"], task["expected"], variant)
               for variant in order]
        rows.append({**task, "execution_order": order, "observations": obs})
    result = summarize(rows)
    report = {
        "schema_version": 1, "model_id": MODEL_ID,
        "resolved_revision": revision, "weight_files": files,
        "public_tasks_sha256": hashlib.sha256(json.dumps(public_tasks(), sort_keys=True).encode()).hexdigest(),
        "pretrained_checkpoint_loaded": True,
        "weights_trained_this_run": False,
        "gpu_lora_training_proven": False,
        "independent_heldout_accuracy_proven": False,
        "quality_gain": None, "speed_gain": None,
        "rows": rows, "summary": result,
        "note": "Public deterministic arithmetic only; self-reported CPU execution, not independently authenticated, no hidden evaluation.",
    }
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
