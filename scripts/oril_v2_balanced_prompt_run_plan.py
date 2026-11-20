#!/usr/bin/env python3
"""Generate an offline, deterministic, answer-free interleaved A/B and A/A run plan.

A=verbose prompt, B=distilled prompt. Never loads hidden answers or runs models.
A/A controls repeat the exact same prompt twice; no claim of causal identification.
"""
import argparse
import hashlib
import json
import random
import re
from pathlib import Path

GROUP = re.compile(r"^[A-Za-z0-9_.:-]{1,100}$")

def make_plan(groups, seed=20261121):
    if not isinstance(groups, list) or len(groups) < 30:
        raise ValueError("at least 30 independent group IDs required")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("integer seed required")
    if any(not isinstance(g, str) or not GROUP.fullmatch(g) for g in groups):
        raise ValueError("invalid group ID")
    canonical = [g.casefold() for g in groups]
    if len(set(canonical)) != len(groups):
        raise ValueError("duplicate group IDs")
    rng = random.Random(seed)
    ordered = sorted(groups, key=str.casefold)
    rng.shuffle(ordered)
    out = []
    for i, group in enumerate(ordered):
        # A/B and A/A each occur for every group, with balanced order.
        ab = ("A", "B") if i % 2 == 0 else ("B", "A")
        aa = ("A", "A")
        blocks = [("AB", ab), ("AA", aa)]
        if i % 2:
            blocks.reverse()
        for kind, variants in blocks:
            for j, variant in enumerate(variants):
                out.append({"group_id": group, "block": kind,
                            "position": j + 1, "variant": variant,
                            "global_sequence": len(out) + 1})
    return out

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--groups", required=True, help="JSON array of group IDs only; no hidden answers")
    p.add_argument("--output", required=True)
    p.add_argument("--seed", type=int, default=20261121)
    args = p.parse_args()
    src = Path(args.groups)
    dest = Path(args.output)
    if src.resolve() == dest.resolve():
        raise ValueError("input and output paths must differ")
    raw = src.read_bytes()
    if len(raw) > 65536:
        raise ValueError("input too large")
    groups = json.loads(raw.decode("utf-8"))
    plan = make_plan(groups, args.seed)
    payload = "".join(json.dumps(x, sort_keys=True, ensure_ascii=False) + "\n" for x in plan)
    dest.write_text(payload, encoding="utf-8")
    print(json.dumps({"plan_sha256": hashlib.sha256(payload.encode()).hexdigest(),
                      "groups": len(groups), "calls": len(plan),
                      "ab_blocks": len(groups), "aa_blocks": len(groups),
                      "seed": args.seed, "real_model_calls": 0,
                      "quality_gain": None}, sort_keys=True))

if __name__ == "__main__":
    main()
