#!/usr/bin/env python3
"""Independently recompute PUBLIC exact-match labels from Qwen CPU paired JSON.

This is an offline arithmetic audit, not independent model execution, not a
heldout evaluation, and not GPU LoRA evidence. Reject self-reported labels
that disagree with the actual generated text. Do not trust report summary.
"""
import argparse
import json
import math
from pathlib import Path
import re

EXPECTED = ("5", "3", "9", "4")
LABELS = ("verbose", "compact")
SHA40 = re.compile(r"^[a-f0-9]{40}$")
SHA64 = re.compile(r"^[a-f0-9]{64}$")


def audit(report):
    if not isinstance(report, dict) or report.get("schema_version") != 1:
        raise ValueError("invalid report schema")
    if report.get("model_id") != "Qwen/Qwen2.5-0.5B-Instruct":
        raise ValueError("unexpected model id")
    if report.get("pretrained_checkpoint_loaded") is not True:
        raise ValueError("pretrained checkpoint not loaded")
    if not isinstance(report.get("resolved_revision"), str) or not SHA40.fullmatch(report["resolved_revision"]):
        raise ValueError("invalid model revision")
    if (report.get("weights_trained_this_run") is not False
            or report.get("gpu_lora_training_proven") is not False
            or report.get("independent_heldout_accuracy_proven") is not False
            or report.get("quality_gain") is not None
            or report.get("speed_gain") is not None):
        raise ValueError("unproven training or model improvement claim")
    weights = report.get("weight_files")
    if not isinstance(weights, list) or not weights:
        raise ValueError("missing weight metadata")
    for w in weights:
        if (not isinstance(w, dict) or type(w.get("bytes")) is not int
                or w["bytes"] <= 0 or not isinstance(w.get("sha256"), str)
                or not SHA64.fullmatch(w["sha256"])):
            raise ValueError("invalid weight metadata")
    pairs = report.get("pairs")
    if not isinstance(pairs, list) or len(pairs) != 4:
        raise ValueError("four public question pairs required")
    result = {k: {"input_tokens": 0, "generated_tokens": 0,
                  "exact_public_matches": 0, "elapsed_seconds": []}
              for k in LABELS}
    for i, pair in enumerate(pairs):
        order = ["verbose", "compact"] if i % 2 == 0 else ["compact", "verbose"]
        if (not isinstance(pair, dict) or type(pair.get("question_id")) is not int
                or pair["question_id"] != i + 1 or pair.get("execution_order") != order):
            raise ValueError("question order mismatch")
        observations = pair.get("observations")
        if not isinstance(observations, list) or len(observations) != 2:
            raise ValueError("missing observations")
        for j, obs in enumerate(observations):
            if not isinstance(obs, dict) or obs.get("variant") != order[j]:
                raise ValueError("variant order mismatch")
            for key in ("input_tokens", "generated_tokens"):
                if type(obs.get(key)) is not int or not 1 <= obs[key] <= 100000:
                    raise ValueError("invalid token count")
            t = obs.get("elapsed_seconds")
            if type(t) not in (int, float) or not math.isfinite(t) or not 0 < t < 86400:
                raise ValueError("invalid timing")
            if obs.get("attention_mask_explicit") is not True:
                raise ValueError("missing explicit attention mask")
            output = obs.get("output")
            if not isinstance(output, str) or not 0 < len(output) <= 10000:
                raise ValueError("invalid generated output")
            exact = output.strip() == EXPECTED[i]
            if type(obs.get("exact_public_answer_match")) is not bool or obs["exact_public_answer_match"] != exact:
                raise ValueError("self-reported answer match disagrees with output")
            entry = result[obs["variant"]]
            entry["input_tokens"] += obs["input_tokens"]
            entry["generated_tokens"] += obs["generated_tokens"]
            entry["exact_public_matches"] += int(exact)
            entry["elapsed_seconds"].append(t)
    verbose, compact = result["verbose"], result["compact"]
    savings = 100 * (1 - compact["input_tokens"] / verbose["input_tokens"])
    return {
        "schema_version": 1,
        "public_questions": 4,
        "actual_observations_claimed": 8,
        "model_revision_claim": report["resolved_revision"],
        "public_exact_matches_recomputed": {k: result[k]["exact_public_matches"] for k in LABELS},
        "input_tokens_recomputed": {k: result[k]["input_tokens"] for k in LABELS},
        "generated_tokens_recomputed": {k: result[k]["generated_tokens"] for k in LABELS},
        "input_token_saving_pct_descriptive": round(savings, 3),
        "elapsed_seconds_raw": {k: result[k]["elapsed_seconds"] for k in LABELS},
        "external_model_execution_authenticated": False,
        "weight_sha_bytes_independently_verified": False,
        "independent_heldout_accuracy_proven": False,
        "gpu_lora_training_proven": False,
        "model_quality_gain": None,
        "model_speed_gain": None,
        "decision": "판단불가",
        "note": "Public 4-question diagnostic only; metadata and execution are self-reported. No heldout noninferiority, speed, or LoRA claim.",
    }


def unique_keys(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key")
        out[key] = value
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    source, dest = Path(args.input), Path(args.output)
    if source.resolve() == dest.resolve() or dest.exists() or dest.is_symlink():
        raise ValueError("refuse input overwrite or existing output")
    if source.stat().st_size > 1024 * 1024:
        raise ValueError("report too large")
    report = json.loads(source.read_text(encoding="utf-8"),
                        object_pairs_hook=unique_keys,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
    result = audit(report)
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
