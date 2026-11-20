#!/usr/bin/env python3
"""Invoke TWO actual model adapters on the SAME heldout tasks, never train weights.

Adapter protocol: stdin {"question": "...", "case_id": "...", "seed": 0}
stdout JSON {"answer": "...", "input_tokens": 1, "output_tokens": 1,
             "model_id": "verified-out-of-band"}.
An adapter's self-reported token/model fields are not trusted attestation.
This runner records real subprocess wall time, not GPU or weight evidence.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time
import unicodedata


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical_group(value):
    """Conservative alias detection; not semantic identity or a privacy guarantee."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(ch for ch in normalized if not ch.isspace()
                   and unicodedata.category(ch) != "Cf")


def strict_json_pairs(pairs):
    """Reject ambiguous repeated keys instead of accepting last-value-wins."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key in heldout manifest")
        result[key] = value
    return result


def reject_nonfinite_json(value):
    raise ValueError("nonfinite JSON constant in heldout manifest")


def read_manifest(path):
    # A private heldout dataset must be bounded BEFORE model execution.
    # Streaming read also avoids unbounded read_bytes() allocations.
    max_bytes, max_cases = 4 * 1024 * 1024, 1000
    with Path(path).open("rb") as handle:
        raw = handle.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("heldout manifest exceeds 4 MiB limit")
    rows = []
    for line in raw.decode("utf-8").splitlines():
        if not line.strip():
            continue
        if len(rows) >= max_cases:
            raise ValueError("heldout manifest exceeds 1000 cases")
        if len(line) > 24000:
            raise ValueError("heldout manifest line too large")
        rows.append(json.loads(line, object_pairs_hook=strict_json_pairs,
                               parse_constant=reject_nonfinite_json))
    if len(rows) < 2:
        raise ValueError("at least two heldout cases required")
    ids, groups = set(), set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"case_id", "group_id", "question", "expected_answer", "split"}:
            raise ValueError("invalid heldout schema")
        if row["split"] != "heldout":
            raise ValueError("only heldout cases accepted")
        if not all(isinstance(row[x], str) and 0 < len(row[x]) <= 4000 for x in ("case_id", "group_id", "question", "expected_answer")):
            raise ValueError("invalid case text")
        canonical = canonical_group(row["group_id"])
        if not canonical:
            raise ValueError("empty canonical heldout group")
        if row["case_id"] in ids or canonical in groups:
            raise ValueError("duplicate case or correlated group")
        ids.add(row["case_id"])
        groups.add(canonical)
    return rows, sha(raw)


def invoke(cmd, question, case_id, seed, timeout):
    if not isinstance(cmd, list) or not cmd or not all(isinstance(s, str) and s for s in cmd):
        raise ValueError("command must be a nonempty JSON string array")
    request = json.dumps({"question": question, "case_id": case_id, "seed": seed})
    start = time.monotonic_ns()
    try:
        proc = subprocess.run(cmd, input=request, text=True, capture_output=True,
                              timeout=timeout, check=False, env=os.environ.copy())
    except subprocess.TimeoutExpired as exc:
        raise ValueError("model adapter timed out") from exc
    elapsed = (time.monotonic_ns() - start) / 1e9
    if proc.returncode or len(proc.stdout) > 200000:
        raise ValueError("adapter failed or returned excessive output")
    try:
        result = json.loads(proc.stdout)
    except (ValueError, TypeError) as exc:
        raise ValueError("adapter must emit one JSON object") from exc
    if not isinstance(result, dict) or set(result) != {"answer", "input_tokens", "output_tokens", "model_id"}:
        raise ValueError("adapter response schema invalid")
    if not isinstance(result["answer"], str) or len(result["answer"]) > 20000:
        raise ValueError("invalid answer")
    if not isinstance(result["model_id"], str) or not result["model_id"].strip():
        raise ValueError("invalid model id")
    for field in ("input_tokens", "output_tokens"):
        if type(result[field]) is not int or result[field] < 0:
            raise ValueError("invalid token count")
    return result, elapsed


def evaluate(rows, manifest_sha, baseline_cmd, candidate_cmd, timeout=30, seed=0):
    if not (0 < timeout <= 3600) or type(seed) is not int:
        raise ValueError("invalid timeout or seed")
    paired = []
    for row in rows:
        b, bt = invoke(baseline_cmd, row["question"], row["case_id"], seed, timeout)
        c, ct = invoke(candidate_cmd, row["question"], row["case_id"], seed, timeout)
        paired.append({
            "case_id": row["case_id"], "group_id": row["group_id"],
            "baseline_correct": b["answer"].strip() == row["expected_answer"].strip(),
            "candidate_correct": c["answer"].strip() == row["expected_answer"].strip(),
            "baseline_input_tokens_claimed": b["input_tokens"],
            "candidate_input_tokens_claimed": c["input_tokens"],
            "baseline_output_tokens_claimed": b["output_tokens"],
            "candidate_output_tokens_claimed": c["output_tokens"],
            "baseline_wall_seconds": round(bt, 6),
            "candidate_wall_seconds": round(ct, 6),
            "baseline_model_id_claimed": b["model_id"],
            "candidate_model_id_claimed": c["model_id"],
        })
    n = len(paired)
    baseline_correct = sum(x["baseline_correct"] for x in paired)
    candidate_correct = sum(x["candidate_correct"] for x in paired)
    baseline_tokens = sum(x["baseline_input_tokens_claimed"] + x["baseline_output_tokens_claimed"] for x in paired)
    candidate_tokens = sum(x["candidate_input_tokens_claimed"] + x["candidate_output_tokens_claimed"] for x in paired)
    return {
        "schema_version": 1,
        "heldout_manifest_sha256": manifest_sha,
        "cases": n,
        "baseline_accuracy": baseline_correct / n,
        "candidate_accuracy": candidate_correct / n,
        "accuracy_delta_pp": 100 * (candidate_correct - baseline_correct) / n,
        "baseline_tokens_claimed": baseline_tokens,
        "candidate_tokens_claimed": candidate_tokens,
        "token_savings_pct_claimed": 100 * (baseline_tokens - candidate_tokens) / baseline_tokens if baseline_tokens else None,
        "baseline_wall_seconds": sum(x["baseline_wall_seconds"] for x in paired),
        "candidate_wall_seconds": sum(x["candidate_wall_seconds"] for x in paired),
        "pairs": paired,
        "independent_evaluation_verified": False,
        "tokenizer_counts_independently_verified": False,
        "gpu_training_verified": False,
        "adapter_weights_verified": False,
        "improvement_approved": False,
        "note": "Actual subprocess timings; token counts and model IDs are adapter claims. Not independent evaluator, GPU, LoRA or promotion evidence.",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--heldout", required=True)
    p.add_argument("--baseline-cmd-json", required=True)
    p.add_argument("--candidate-cmd-json", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--timeout", type=float, default=30)
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args()
    if Path(a.report).resolve() == Path(a.heldout).resolve():
        raise ValueError("report must not overwrite heldout manifest")
    rows, digest = read_manifest(a.heldout)
    baseline_cmd = json.loads(a.baseline_cmd_json)
    candidate_cmd = json.loads(a.candidate_cmd_json)
    # Reserve a new, private output BEFORE running either model. Never truncate
    # an existing report, private heldout file or symlink target.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(a.report, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        result = evaluate(rows, digest, baseline_cmd, candidate_cmd,
                          a.timeout, a.seed)
        handle.write(json.dumps(result, sort_keys=True, indent=2) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    # On model failure an empty private reservation may remain. It is NOT
    # an approved result; downstream consumers must reject empty reports.


if __name__ == "__main__":
    main()
