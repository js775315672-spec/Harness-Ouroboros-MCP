#!/usr/bin/env python3
"""Independent read-only arithmetic audit of 30 PUBLIC Qwen A/A observations.

No imports from experiment scripts. This verifies consistency, not provenance,
actual execution, independent heldout intelligence, or causal speed improvement.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")


def read_unique(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    path = Path(path)
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("oversized report")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def audit(report):
    if type(report) is not dict or report.get("schema_version") != 1:
        raise ValueError("invalid schema")
    if report.get("model_id") != MODEL or not isinstance(report.get("resolved_revision"), str) or not SHA40.fullmatch(report["resolved_revision"]):
        raise ValueError("invalid model revision")
    if (report.get("pretrained_checkpoint_loaded") is not True or
        report.get("weights_trained_this_run") is not False or
        report.get("gpu_lora_training_proven") is not False or
        report.get("independent_heldout_accuracy_proven") is not False or
        report.get("quality_gain") is not None or report.get("speed_gain") is not None):
        raise ValueError("false model improvement or training claim")
    weights = report.get("weight_files")
    if not isinstance(weights, list) or not weights:
        raise ValueError("missing weight hashes")
    for w in weights:
        if (type(w) is not dict or not isinstance(w.get("name"), str) or
            not w["name"].endswith(".safetensors") or
            type(w.get("bytes")) is not int or w["bytes"] <= 0 or
            not isinstance(w.get("sha256"), str) or not SHA64.fullmatch(w["sha256"])):
            raise ValueError("invalid weight metadata")
    rows = report.get("rows")
    if type(rows) is not list or len(rows) != 30:
        raise ValueError("expected exactly 30 public groups")
    tasks, signed, absolute, times, tokens, matches = [], [], [], [], [], [0, 0]
    for i, row in enumerate(rows):
        a, b = 11 + 3*i, 2 + i % 7
        task = {"group_id": f"public-arithmetic-{i+1:02d}",
                "question": f"What is {a} plus {b}? Answer with only the integer.",
                "expected": str(a+b)}
        if type(row) is not dict or any(row.get(k) != v for k, v in task.items()):
            raise ValueError("public task mismatch or reorder")
        tasks.append(task)
        obs = row.get("observations")
        if type(obs) is not list or len(obs) != 2:
            raise ValueError("exactly two observations")
        pair = []
        for j, x in enumerate(obs):
            if type(x) is not dict or x.get("variant") != "compact" or x.get("attention_mask_explicit") is not True:
                raise ValueError("not an A/A compact observation")
            if type(x.get("input_tokens")) is not int or not 0 < x["input_tokens"] <= 100000:
                raise ValueError("invalid input tokens")
            if type(x.get("generated_tokens")) is not int or not 1 <= x["generated_tokens"] <= 16:
                raise ValueError("invalid generated tokens")
            t = x.get("elapsed_seconds")
            if type(t) not in (int, float) or not math.isfinite(t) or not 0 < t < 86400:
                raise ValueError("invalid timing")
            output = x.get("output")
            if not isinstance(output, str) or not output.strip() or len(output) > 4000:
                raise ValueError("invalid output")
            correct = output.strip() == task["expected"]
            if type(x.get("exact_public_answer_match")) is not bool or x["exact_public_answer_match"] != correct:
                raise ValueError("invalid answer label")
            matches[j] += int(correct)
            pair.append(x)
        if pair[0]["input_tokens"] != pair[1]["input_tokens"]:
            raise ValueError("A/A token mismatch")
        signed.append(pair[1]["elapsed_seconds"] - pair[0]["elapsed_seconds"])
        absolute.append(abs(signed[-1]))
        times.extend(x["elapsed_seconds"] for x in pair)
        tokens.append(pair[0]["input_tokens"])
    task_sha = hashlib.sha256(json.dumps(tasks, sort_keys=True).encode()).hexdigest()
    if report.get("public_tasks_sha256") != task_sha:
        raise ValueError("task digest mismatch")
    expected = {
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
    if report.get("summary") != expected:
        raise ValueError("A/A raw values disagree with summary")
    return {
        "schema_version": 1,
        "groups": 30, "reported_calls": 60,
        "public_exact_matches_first": matches[0],
        "public_exact_matches_second": matches[1],
        "raw_pair_signed_differences_seconds": signed,
        "median_absolute_pair_drift_seconds": expected["median_absolute_pair_drift_seconds"],
        "median_signed_second_minus_first_seconds": expected["median_signed_second_minus_first_seconds"],
        "weight_bytes_independently_verified": False,
        "actual_model_calls_independently_attested": False,
        "independent_heldout_accuracy_proven": False,
        "gpu_lora_training_proven": False,
        "causal_speed_gain_proven": False,
        "decision": "판단불가",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    dest = Path(args.output)
    if dest.resolve() == Path(args.input).resolve() or dest.exists() or dest.is_symlink():
        raise ValueError("output must be new and distinct")
    result = audit(read_unique(args.input))
    dest.write_text(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "raw_pair_signed_differences_seconds"}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
