"""Fail-closed adaptive DEV campaign planner: 10 batches x 12 cycles.

This module deliberately does NOT invoke models, write OPS state, or certify
improvements. Only independently verified batch receipts permit advancement.
"""
import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

BATCH_SIZE = 12
MAX_BATCHES = 10

def stable_key(agent, campaign, batch, cycle, candidate_sha):
    if not all((agent, campaign, candidate_sha)):
        raise ValueError("missing provenance")
    if not 1 <= batch <= MAX_BATCHES or not 1 <= cycle <= BATCH_SIZE:
        raise ValueError("out of bounds")
    payload = [agent, campaign, batch, cycle, candidate_sha]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()

def persist(path, state):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".adaptive-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, sort_keys=True, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def new_campaign(agent, campaign, max_wall_seconds, max_cost_usd=0.0):
    if agent not in ("Ouroboros", "Cerberus", "Fenrir") or not campaign:
        raise ValueError("agent/campaign required")
    if max_wall_seconds <= 0 or max_cost_usd < 0:
        raise ValueError("invalid budget")
    return {"agent": agent, "campaign": campaign, "max_wall_seconds": max_wall_seconds,
            "max_cost_usd": max_cost_usd, "elapsed_seconds": 0.0,
            "spent_usd": 0.0, "batches": [], "pending": None,
            "status": "ready", "version": 1}

def next_batch(state):
    if state["pending"]:
        raise RuntimeError("pending receipt: reconcile before retry")
    if state["status"] != "ready":
        return None
    if state["elapsed_seconds"] >= state["max_wall_seconds"] or state["spent_usd"] >= state["max_cost_usd"] and state["max_cost_usd"] > 0:
        state["status"] = "budget_exhausted"
        return None
    if len(state["batches"]) >= MAX_BATCHES:
        state["status"] = "complete"
        return None
    if state["batches"] and not state["batches"][-1]["independent_pass"]:
        state["status"] = "blocked"
        return None
    return len(state["batches"]) + 1

def reserve_batch(state, batch, candidate_sha):
    if batch != next_batch(state):
        raise RuntimeError("batch out of order or blocked")
    if not candidate_sha:
        raise ValueError("candidate SHA required")
    state["pending"] = {"batch": batch, "candidate_sha": candidate_sha,
                        "operation_key": stable_key(state["agent"], state["campaign"], batch, 1, candidate_sha)}
    return state["pending"]

def record_batch(state, receipt):
    pending = state["pending"]
    if not pending:
        raise RuntimeError("no reserved batch")
    required = ("batch", "candidate_sha", "operation_key", "evaluator_sha",
                "evidence_sha256", "independent_pass", "elapsed_seconds", "cost_usd",
                "cycles_completed")
    if any(key not in receipt for key in required):
        raise ValueError("incomplete independent evidence")
    if any(receipt[key] != pending[key] for key in ("batch", "candidate_sha", "operation_key")):
        raise RuntimeError("receipt does not match pending")
    if not receipt["evaluator_sha"] or not receipt["evidence_sha256"]:
        raise ValueError("missing evaluator provenance")
    if not isinstance(receipt["independent_pass"], bool) or not 0 <= receipt["cycles_completed"] <= BATCH_SIZE:
        raise ValueError("invalid evaluation")
    if receipt["elapsed_seconds"] < 0 or receipt["cost_usd"] < 0:
        raise ValueError("invalid measurements")
    state["elapsed_seconds"] += receipt["elapsed_seconds"]
    state["spent_usd"] += receipt["cost_usd"]
    state["batches"].append(dict(receipt))
    state["pending"] = None
    if not receipt["independent_pass"] or receipt["cycles_completed"] != BATCH_SIZE:
        state["status"] = "blocked"
    elif state["elapsed_seconds"] >= state["max_wall_seconds"] or state["spent_usd"] > state["max_cost_usd"]:
        state["status"] = "budget_exhausted"
    elif len(state["batches"]) == MAX_BATCHES:
        state["status"] = "complete"
    return state

def load(path, agent, campaign):
    state = json.loads(Path(path).read_text(encoding="utf-8"))
    if state["agent"] != agent or state["campaign"] != campaign:
        raise RuntimeError("independent ledger mismatch")
    return state

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--agent", required=True, choices=["Ouroboros", "Cerberus", "Fenrir"])
    p.add_argument("--campaign", required=True)
    p.add_argument("--state", required=True)
    p.add_argument("--max-wall-seconds", type=float, default=3600)
    p.add_argument("--max-cost-usd", type=float, default=0)
    args = p.parse_args()
    path = Path(args.state)
    state = load(path, args.agent, args.campaign) if path.exists() else new_campaign(
        args.agent, args.campaign, args.max_wall_seconds, args.max_cost_usd)
    # Read-only plan: no auto-reservation, external side effects, or cost guessing.
    try:
        planned = next_batch(state)
    except RuntimeError:
        planned = None
    persist(path, state)
    print(json.dumps({"status": state["status"], "next_batch": planned,
                      "completed_batches": len(state["batches"]), "actual_model_calls": 0}))

if __name__ == "__main__":
    main()

def authorize_external_execution(state, *, verified_free_provider=False,
                                 evaluator_attested=False, exclusive_lease=False,
                                 predicted_wall_seconds=None, predicted_cost_usd=None):
    """Strict preflight: no external calls without proven free execution and lease.

    This is a gate, not a Qwen connector or proof of independent evaluation.
    """
    import math
    if state.get("pending") is not None or state.get("status") != "ready":
        raise RuntimeError("execution blocked: pending or non-ready state")
    if not (verified_free_provider and evaluator_attested and exclusive_lease):
        raise RuntimeError("execution blocked: provider/evaluator/lease unverified")
    if predicted_wall_seconds is None or predicted_cost_usd is None:
        raise RuntimeError("execution blocked: unmeasured budget")
    if not all(isinstance(v, (int, float)) and math.isfinite(v) and v >= 0
               for v in (predicted_wall_seconds, predicted_cost_usd)):
        raise RuntimeError("execution blocked: invalid budget estimate")
    if state["elapsed_seconds"] + predicted_wall_seconds > state["max_wall_seconds"]:
        raise RuntimeError("execution blocked: time budget")
    if state["spent_usd"] + predicted_cost_usd > state["max_cost_usd"]:
        raise RuntimeError("execution blocked: cost budget")
    if predicted_cost_usd != 0:
        raise RuntimeError("execution blocked: paid calls not approved")
    return True

def verify_attested_receipt(pending, receipt, *, trusted_evaluator_sha,
                            trusted_evidence_sha256, trusted_run_id):
    """Compare evidence against independently obtained trusted values.

    Trusted arguments MUST come from a separately authenticated GitHub run /
    downloaded artifact, never from the candidate's own receipt. This helper
    does not fetch or authenticate that evidence by itself.
    """
    import re
    if not isinstance(receipt, dict) or not isinstance(pending, dict):
        raise RuntimeError("untrusted receipt")
    for k in ("batch", "candidate_sha", "operation_key"):
        if receipt.get(k) != pending.get(k):
            raise RuntimeError("receipt mismatch")
    if not isinstance(trusted_run_id, int) or trusted_run_id <= 0:
        raise RuntimeError("untrusted run ID")
    if not re.fullmatch(r"[0-9a-f]{40}", trusted_evaluator_sha or ""):
        raise RuntimeError("untrusted evaluator SHA")
    if not re.fullmatch(r"[0-9a-f]{64}", trusted_evidence_sha256 or ""):
        raise RuntimeError("untrusted evidence digest")
    if (receipt.get("evaluator_sha") != trusted_evaluator_sha or
        receipt.get("evidence_sha256") != trusted_evidence_sha256 or
        receipt.get("run_id") != trusted_run_id):
        raise RuntimeError("forged or mismatched evaluation provenance")
    if receipt.get("independent_pass") is not True:
        raise RuntimeError("evaluation did not pass")
    return True
