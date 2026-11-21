#!/usr/bin/env python3
"""Independent raw-pair audit for the 30 PUBLIC Qwen experiment.

Does not import experiment-side summarizers. Checks arithmetic independently.
Public diagnostics cannot certify heldout accuracy, LoRA or intelligence gain.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
HEX = re.compile(r"^[0-9a-f]{64}$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def audit(report):
    if type(report) is not dict or report.get("schema_version") != 1:
        raise ValueError("invalid report schema")
    if report.get("model_id") != MODEL or not isinstance(report.get("resolved_revision"), str) or not SHA40.fullmatch(report["resolved_revision"]):
        raise ValueError("untrusted model identity")
    weights = report.get("weight_files")
    if not isinstance(weights, list) or not weights:
        raise ValueError("missing weight hashes")
    for w in weights:
        if (not isinstance(w, dict) or not isinstance(w.get("name"), str)
            or not w["name"].endswith(".safetensors")
            or type(w.get("bytes")) is not int or w["bytes"] <= 0
            or not isinstance(w.get("sha256"), str) or not HEX.fullmatch(w["sha256"])):
            raise ValueError("invalid weight metadata")
    if any(report.get(k) is not False for k in
           ("weights_trained_this_run", "gpu_lora_training_proven",
            "independent_heldout_accuracy_proven", "pretrained_checkpoint_loaded") if k != "pretrained_checkpoint_loaded"):
        raise ValueError("false training or heldout claim")
    if report.get("pretrained_checkpoint_loaded") is not True:
        raise ValueError("missing checkpoint claim")
    if report.get("quality_gain") is not None or report.get("speed_gain") is not None:
        raise ValueError("unjustified gain claim")
    rows = report.get("rows")
    if type(rows) is not list or len(rows) != 30:
        raise ValueError("expected 30 public pairs")
    public_tasks = []
    sums = {"verbose": 0, "compact": 0}
    hits = {"verbose": 0, "compact": 0}
    latencies = {"verbose": [], "compact": []}
    per_pair = []
    for i, row in enumerate(rows):
        a, b = 11 + 3*i, 2 + i % 7
        q = f"What is {a} plus {b}? Answer with only the integer."
        gid = f"public-arithmetic-{i+1:02d}"
        if not isinstance(row, dict) or row.get("group_id") != gid or row.get("question") != q or row.get("expected") != str(a+b):
            raise ValueError("public question/answer drift")
        public_tasks.append({"group_id": gid, "question": q, "expected": str(a+b)})
        order = ["verbose", "compact"] if i % 2 == 0 else ["compact", "verbose"]
        obs = row.get("observations")
        if row.get("execution_order") != order or type(obs) is not list or len(obs) != 2:
            raise ValueError("counterbalanced observations required")
        pair = {}
        for variant, x in zip(order, obs):
            if not isinstance(x, dict) or x.get("variant") != variant or x.get("attention_mask_explicit") is not True:
                raise ValueError("invalid variant or mask")
            t, elapsed, output = x.get("input_tokens"), x.get("elapsed_seconds"), x.get("output")
            if type(t) is not int or not 0 < t <= 100000:
                raise ValueError("invalid token count")
            if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or not 0 < elapsed < 86400:
                raise ValueError("invalid latency")
            if not isinstance(output, str) or not output.strip() or len(output) > 4000:
                raise ValueError("invalid output")
            correct = output.strip() == str(a+b)
            if type(x.get("exact_public_answer_match")) is not bool or x["exact_public_answer_match"] != correct:
                raise ValueError("public label mismatch")
            sums[variant] += t
            hits[variant] += int(correct)
            latencies[variant].append(elapsed)
            pair[variant] = {"tokens": t, "correct": correct, "elapsed": elapsed}
        per_pair.append(pair)
    task_sha = hashlib.sha256(json.dumps(public_tasks, sort_keys=True).encode()).hexdigest()
    if report.get("public_tasks_sha256") != task_sha:
        raise ValueError("task SHA mismatch")
    if sums["verbose"] <= 0:
        raise ValueError("invalid verbose total")
    savings = round(100 * (1 - sums["compact"] / sums["verbose"]), 3)
    medians = {k: round(statistics.median(v), 6) for k, v in latencies.items()}
    expected_summary = {
        "public_groups": 30, "actual_calls_claimed": 60,
        "input_tokens": sums, "public_exact_matches": hits,
        "latency_median_seconds": medians,
        "input_token_saving_pct_descriptive": savings,
        "quality_gain_proven": False, "speed_gain_proven": False,
        "independent_heldout_accuracy_proven": False,
        "gpu_lora_training_proven": False, "decision": "판단불가",
    }
    if report.get("summary") != expected_summary:
        raise ValueError("raw observations disagree with summary")
    # Paired, group-level public accuracy: never substitute 60 correlated calls
    # for 60 independent questions.
    discordant = {
        "compact_only_correct": sum(p["compact"]["correct"] and not p["verbose"]["correct"] for p in per_pair),
        "verbose_only_correct": sum(p["verbose"]["correct"] and not p["compact"]["correct"] for p in per_pair),
    }
    return {
        "schema_version": 1, "source": "30 public Qwen arithmetic pairs",
        "raw_groups": 30, "raw_calls": 60,
        "input_tokens": sums, "public_exact_matches": hits,
        "paired_accuracy_discordance": discordant,
        "token_saving_pct_descriptive": savings,
        "latency_median_seconds": medians,
        "observed_model_revision": report["resolved_revision"],
        "weight_hash_metadata_present": True,
        "weight_bytes_independently_verified": False,
        "actual_calls_independently_attested": False,
        "heldout_quality_proven": False, "lora_training_proven": False,
        "decision": "판단불가",
    }


def read_unique(path):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError("duplicate JSON key")
            out[k] = v
        return out
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    if Path(args.input).resolve() == Path(args.output).resolve() or Path(args.output).exists() or Path(args.output).is_symlink():
        raise ValueError("output must be new and separate")
    result = audit(read_unique(args.input))
    Path(args.output).write_text(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
