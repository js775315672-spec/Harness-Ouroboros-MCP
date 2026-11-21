#!/usr/bin/env python3
"""Read-only, repo-local context and evidence validation for the ouroboros agent.

No network calls, writes, model calls, agent scheduling, or cross-repository imports.
This copy belongs to its own repository and may evolve separately.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
AGENT_ID = "ouroboros"
STATE = Path("docs/evolution/independent-state.json")
LEDGER = Path("docs/evolution/independent-ledger.jsonl")
SCHEMA = "independent-agent-state-v1"
ALLOWED = {
    "NOT_STARTED", "PROPOSED", "RUNNING", "BLOCKED",
    "INCONCLUSIVE", "FAILED", "VERIFIED", "REJECTED",
}

def require(test: bool, reason: str) -> None:
    if not test:
        raise ValueError(reason)

def validate_state(row: object) -> dict:
    require(isinstance(row, dict), "state must be a JSON object")
    require(row.get("schema") == SCHEMA, "state schema mismatch")
    require(row.get("agent_id") == AGENT_ID, "agent identity mismatch")
    require(row.get("evolution_status") in ALLOWED, "invalid evolution status")
    require(row.get("operation_mode") == "research_draft_only",
            "unexpected operation mode; requires explicit policy review")
    for key in ("current_assessment", "next_experiment"):
        require(isinstance(row.get(key), str) and bool(row[key].strip()),
                f"missing {key}")
    require(isinstance(row.get("metrics"), dict), "metrics must be an object")
    require(isinstance(row.get("evidence_urls"), list), "evidence_urls must be a list")
    require(all(isinstance(x, str) and x.startswith("https://")
                for x in row["evidence_urls"]), "invalid evidence url")
    if row.get("last_verified_independent_gain") is not None:
        gain = row["last_verified_independent_gain"]
        require(isinstance(gain, dict) and all(
            gain.get(k) for k in ("run_url", "evaluator_sha256", "metric", "gain")
        ), "verified gain lacks independent evidence")
        require(row.get("last_verified_cycle"), "verified gain without cycle")
    return row

def read_ledger(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    cycle_ids: set[str] = set()
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"ledger line {n}: malformed JSON: {exc}") from exc
        require(isinstance(row, dict), f"ledger line {n}: not an object")
        require(row.get("schema") == "independent-agent-cycle-v1", f"ledger line {n}: schema")
        require(row.get("agent_id") == AGENT_ID, f"ledger line {n}: agent id")
        cid = row.get("cycle_id")
        require(isinstance(cid, str) and bool(cid.strip()), f"ledger line {n}: cycle id")
        require(cid not in cycle_ids, f"ledger line {n}: duplicate cycle id")
        cycle_ids.add(cid)
        verdict = row.get("verdict")
        require(verdict in ALLOWED, f"ledger line {n}: verdict")
        if verdict == "VERIFIED":
            for k in ("source_commit", "evaluator_run_url", "candidate_sha256",
                      "evaluator_sha256", "heldout_result"):
                require(row.get(k) is not None, f"ledger line {n}: missing {k}")
        records.append(row)
    return records

def load_snapshot(root: Path = ROOT) -> tuple[dict, list[dict]]:
    state = json.loads((root / STATE).read_text(encoding="utf-8"))
    return validate_state(state), read_ledger(root / LEDGER)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Own-agent research memory (read only)")
    parser.add_argument("command", choices=("check", "context", "json"))
    args = parser.parse_args(argv)
    try:
        snapshot, records = load_snapshot()
        if args.command == "check":
            print(f"OK: {AGENT_ID} state valid; {len(records)} independent cycle records")
        elif args.command == "json":
            print(json.dumps({"identity": AGENT_ID, "state": snapshot,
                              "cycle_count": len(records)}, ensure_ascii=False, indent=2))
        else:
            print(f"# {AGENT_ID} | independent context")
            print(f"Status: {snapshot['evolution_status']} (as of {snapshot['observed_at']})")
            print(f"Assessment: {snapshot['current_assessment']}")
            print(f"Next owned experiment: {snapshot['next_experiment']}")
            print(f"Own ledger records: {len(records)}")
            print("Unmeasured items: " + "; ".join(snapshot.get("missing_measurements", [])))
            print("External agents are optional, untrusted evidence sources, not prerequisites.")
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Invalid ouroboros research memory: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
