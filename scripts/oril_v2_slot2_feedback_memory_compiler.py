#!/usr/bin/env python3
"""Fail-closed ORIL P5->P6 feedback memory compiler.

This only compiles independently verified outcome records into the *next*
falsifiable experiment. It does not attest evidence, train weights, or promote.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

SHA = re.compile(r"^[a-f0-9]{40}$")
IDENT = re.compile(r"^[a-zA-Z0-9_.:-]{1,100}$")
OUTCOMES = {"pass", "fail", "inconclusive"}
METRICS = {"accuracy", "tokens", "latency", "safety"}
REQUIRED = {"cycle_id", "candidate_sha", "baseline_sha", "evaluator_sha",
            "heldout_digest", "evidence_sha256", "evidence_url",
            "independent_review", "heldout", "model_weights_changed",
            "gpu_training_proven", "adapter_sha256", "metric",
            "baseline_value", "candidate_value", "direction", "outcome",
            "hypothesis", "experiment"}
HEX64 = re.compile(r"^[a-f0-9]{64}$")
URL = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/actions/runs/[0-9]+$")
DIRECTIONS = {"higher", "lower"}


def _finite(v):
    return type(v) in (float, int) and math.isfinite(v)


def compile_memory(records):
    if not isinstance(records, list) or not records:
        raise ValueError("nonempty records required")
    seen = set()
    output = []
    for row in records:
        if not isinstance(row, dict) or set(row) != REQUIRED:
            raise ValueError("exact evidence record schema required")
        if not isinstance(row["cycle_id"], str) or not IDENT.fullmatch(row["cycle_id"]):
            raise ValueError("invalid cycle_id")
        if row["cycle_id"] in seen:
            raise ValueError("duplicate cycle_id")
        seen.add(row["cycle_id"])
        for field in ("candidate_sha", "baseline_sha", "evaluator_sha"):
            if not isinstance(row[field], str) or not SHA.fullmatch(row[field]):
                raise ValueError("invalid " + field)
        for field in ("heldout_digest", "evidence_sha256"):
            if not isinstance(row[field], str) or not HEX64.fullmatch(row[field]):
                raise ValueError("invalid " + field)
        if not isinstance(row["evidence_url"], str) or not URL.fullmatch(row["evidence_url"]):
            raise ValueError("invalid evidence_url")
        for field in ("independent_review", "heldout", "model_weights_changed", "gpu_training_proven"):
            if type(row[field]) is not bool:
                raise ValueError("invalid " + field)
        if row["adapter_sha256"] is not None and (
                not isinstance(row["adapter_sha256"], str) or not HEX64.fullmatch(row["adapter_sha256"])):
            raise ValueError("invalid adapter_sha256")
        if row["model_weights_changed"] and not (row["gpu_training_proven"] and row["adapter_sha256"]):
            raise ValueError("model weight claims require GPU and adapter evidence")
        if row["gpu_training_proven"] and not row["adapter_sha256"]:
            raise ValueError("GPU training claim requires adapter SHA")
        if row["metric"] not in METRICS or row["direction"] not in DIRECTIONS or row["outcome"] not in OUTCOMES:
            raise ValueError("invalid metric/direction/outcome")
        if not _finite(row["baseline_value"]) or not _finite(row["candidate_value"]):
            raise ValueError("nonfinite metric")
        for field in ("hypothesis", "experiment"):
            if not isinstance(row[field], str) or not 8 <= len(row[field].strip()) <= 500:
                raise ValueError("invalid " + field)
        # Independent review is an asserted input, NOT cryptographic attestation.
        # The record is never allowed to say verified success on self-report alone.
        eligible = row["independent_review"] and row["heldout"]
        measured_better = (
            row["candidate_value"] > row["baseline_value"] if row["direction"] == "higher"
            else row["candidate_value"] < row["baseline_value"]
        )
        # Even if values improve, independent non-inferiority and significance
        # are upstream responsibilities. Do not infer pass from numeric deltas.
        verdict = "verified_candidate" if eligible and row["outcome"] == "pass" and measured_better else "no_verified_improvement"
        reason = (
            "independent heldout result reported as pass (external provenance not attested)"
            if verdict == "verified_candidate"
            else "no eligible independently reviewed heldout improvement; do not promote"
        )
        output.append({
            "cycle_id": row["cycle_id"],
            "candidate_sha": row["candidate_sha"],
            "evaluator_sha": row["evaluator_sha"],
            "evidence_sha256": row["evidence_sha256"],
            "evidence_url": row["evidence_url"],
            "verdict": verdict,
            "reason": reason,
            "hypothesis": row["hypothesis"],
            "next_experiment": row["experiment"],
            "promotion_allowed": False,
            "review_provenance_attested": False,
            "model_weight_gain_proven": False,
        })
    return sorted(output, key=lambda x: x["cycle_id"])


def load_jsonl(path):
    rows = []
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            if len(line) > 12000:
                raise ValueError("oversized record")
            def reject_duplicate(pairs):
                d = {}
                for k, v in pairs:
                    if k in d:
                        raise ValueError("duplicate JSON key")
                    d[k] = v
                return d
            rows.append(json.loads(line, object_pairs_hook=reject_duplicate,
                                   parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON"))))
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    if Path(args.input).resolve() == Path(args.output).resolve():
        raise ValueError("input/output path collision")
    results = compile_memory(load_jsonl(args.input))
    # Do not print hidden heldout data, only digests and next hypotheses.
    Path(args.output).write_text(
        "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in results),
        encoding="utf-8")


if __name__ == "__main__":
    main()
