#!/usr/bin/env python3
"""Fail-closed offline binding of observed model calls to a frozen A/B+A/A plan.

Does not authenticate an external model, token counter, GPU, or independent evaluator.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

PLAN_KEYS = {"group_id", "block", "position", "variant", "global_sequence"}
OBS_KEYS = PLAN_KEYS | {"prompt_sha256", "model_revision", "input_tokens",
                        "output_tokens", "latency_ms", "run_id"}
SHA = "0123456789abcdef"
MAX_BYTES = 4 * 1024 * 1024


def read_jsonl(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("input too large")
    rows = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if len(line) > 24000:
                raise ValueError("line too large")
            if not line.strip():
                raise ValueError("blank lines forbidden")
            def unique(pairs):
                out = {}
                for k, v in pairs:
                    if k in out:
                        raise ValueError("duplicate JSON key")
                    out[k] = v
                return out
            rows.append(json.loads(line, object_pairs_hook=unique,
                                   parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON"))))
    return rows


def audit(plan, observations):
    if not isinstance(plan, list) or len(plan) < 120 or len(plan) % 4:
        raise ValueError("plan requires >=30 groups of four")
    if not isinstance(observations, list):
        raise ValueError("observations must be list")
    seen, groups, prompts, plans = set(), {}, {}, {}
    for idx, row in enumerate(plan, 1):
        if not isinstance(row, dict) or set(row) != PLAN_KEYS:
            raise ValueError("invalid plan schema")
        if type(row["global_sequence"]) is not int or row["global_sequence"] != idx:
            raise ValueError("noncontiguous plan sequence")
        if (row["block"] not in ("AB", "AA") or row["variant"] not in ("A", "B")
                or type(row["position"]) is not int or row["position"] not in (1, 2)
                or not isinstance(row["group_id"], str) or not row["group_id"]):
            raise ValueError("invalid plan field")
        key = (row["group_id"], row["block"], row["position"])
        if key in seen:
            raise ValueError("duplicate planned position")
        seen.add(key)
        groups.setdefault(row["group_id"], []).append(row)
        plans[idx] = row
    if len(groups) * 4 != len(plan):
        raise ValueError("not exactly four calls per group")
    for rows in groups.values():
        aa = [x for x in rows if x["block"] == "AA"]
        ab = [x for x in rows if x["block"] == "AB"]
        if (len(aa) != 2 or len(ab) != 2 or
                sorted(x["position"] for x in aa) != [1, 2] or
                sorted(x["position"] for x in ab) != [1, 2] or
                [x["variant"] for x in sorted(aa, key=lambda x:x["position"])] != ["A", "A"] or
                sorted(x["variant"] for x in ab) != ["A", "B"]):
            raise ValueError("invalid AB/AA balance")
    if len(observations) != len(plan):
        raise ValueError("missing or extra model observations")
    revisions, run_ids = set(), set()
    total_input = 0
    for idx, row in enumerate(observations, 1):
        if not isinstance(row, dict) or set(row) != OBS_KEYS:
            raise ValueError("invalid observation schema")
        for key in PLAN_KEYS:
            if row[key] != plans[idx][key] or type(row[key]) is not type(plans[idx][key]):
                raise ValueError("observation diverges from frozen plan")
        if (not isinstance(row["prompt_sha256"], str) or len(row["prompt_sha256"]) != 64 or
                any(c not in SHA for c in row["prompt_sha256"])):
            raise ValueError("invalid prompt digest")
        if (not isinstance(row["model_revision"], str) or len(row["model_revision"]) != 40 or
                any(c not in SHA for c in row["model_revision"])):
            raise ValueError("unpinned model revision")
        if not isinstance(row["run_id"], str) or not row["run_id"].strip() or len(row["run_id"]) > 100:
            raise ValueError("invalid run ID")
        for key in ("input_tokens", "output_tokens"):
            if type(row[key]) is not int or row[key] < (1 if key == "input_tokens" else 0):
                raise ValueError("invalid token count")
        if (type(row["latency_ms"]) not in (float, int) or
                not math.isfinite(row["latency_ms"]) or row["latency_ms"] <= 0):
            raise ValueError("invalid latency")
        revisions.add(row["model_revision"])
        run_ids.add(row["run_id"])
        total_input += row["input_tokens"]
        group_key = (row["group_id"], row["variant"])
        if group_key in prompts and prompts[group_key] != row["prompt_sha256"]:
            raise ValueError("same group/variant has inconsistent prompt digest")
        prompts[group_key] = row["prompt_sha256"]
    if len(revisions) != 1:
        raise ValueError("model revision drift")
    if len(run_ids) != 1:
        raise ValueError("run ID drift")
    canonical = "".join(json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
                        for x in plan)
    return {
        "plan_sha256_canonical": hashlib.sha256(canonical.encode()).hexdigest(),
        "groups": len(groups), "planned_calls": len(plan),
        "observed_calls": len(observations), "total_input_tokens": total_input,
        "observed_model_revision_claim": next(iter(revisions)),
        "observed_run_id_claim": next(iter(run_ids)),
        "external_model_execution_authenticated": False,
        "independent_heldout_quality_proven": False,
        "gpu_lora_training_proven": False,
        "note": "Input measurements and model/run identity are untrusted assertions; no accuracy gain claim.",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--plan", required=True)
    p.add_argument("--observations", required=True)
    p.add_argument("--report", required=True)
    args = p.parse_args()
    if len({str(Path(x).resolve()) for x in (args.plan, args.observations, args.report)}) != 3:
        raise ValueError("input/output paths must be distinct")
    result = audit(read_jsonl(args.plan), read_jsonl(args.observations))
    Path(args.report).write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
