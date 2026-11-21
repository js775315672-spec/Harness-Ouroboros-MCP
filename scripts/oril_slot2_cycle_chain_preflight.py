"""Read-only ORIL cycle-chain structural preflight. Never grants promotion."""
import argparse
import json
import re
from pathlib import Path

SHA = re.compile(r"^[a-f0-9]{40}$")
REQUIRED = ("cycle_id", "predecessor_id", "source_sha", "candidate_sha", "model_run_url", "independent_run_url", "memory_sha")

def check(cycles):
    if not isinstance(cycles, list) or not cycles:
        raise ValueError("nonempty cycle list required")
    seen = set()
    previous = None
    for i, row in enumerate(cycles):
        if not isinstance(row, dict) or any(k not in row for k in REQUIRED):
            raise ValueError(f"cycle {i}: missing evidence")
        cid = row["cycle_id"]
        if not isinstance(cid, str) or not cid.strip() or cid in seen:
            raise ValueError(f"cycle {i}: invalid/duplicate id")
        if row["predecessor_id"] != previous:
            raise ValueError(f"cycle {i}: broken predecessor chain")
        for field in ("source_sha", "candidate_sha", "memory_sha"):
            if not isinstance(row[field], str) or not SHA.fullmatch(row[field]):
                raise ValueError(f"cycle {i}: invalid {field}")
        for field in ("model_run_url", "independent_run_url"):
            value = row[field]
            if not isinstance(value, str) or not re.fullmatch(
                r"https://github\.com/[^/]+/[^/]+/actions/runs/[1-9][0-9]*", value
            ):
                raise ValueError(f"cycle {i}: invalid {field}")
        if row["model_run_url"] == row["independent_run_url"]:
            raise ValueError(f"cycle {i}: non-independent run reference")
        if i and row["source_sha"] != cycles[i-1]["candidate_sha"]:
            raise ValueError(f"cycle {i}: candidate not carried forward")
        seen.add(cid)
        previous = cid
    return {"structural_chain": "PASS", "cycles": len(cycles),
            "independent_provenance": "UNVERIFIED", "promotion_allowed": False,
            "model_improvement": "NOT_DEMONSTRATED"}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("json_path")
    args = p.parse_args()
    try:
        result = check(json.loads(Path(args.json_path).read_text(encoding="utf-8")))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"structural_chain": "FAIL", "reason": str(exc), "promotion_allowed": False}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
