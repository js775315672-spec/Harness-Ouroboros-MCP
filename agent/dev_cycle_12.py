"""DEV-only 12-step sequential orchestrator. No OPS, merge, or protected writes."""
import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def save(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".cycle-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def run(state_path, agent, candidate_cmd, verifier_cmd, max_cycles=12, budget_seconds=3600, max_cost=0.0):
    if agent not in ("Ouroboros", "Cerberus", "Fenrir"):
        raise ValueError("unknown independent agent")
    if not 1 <= max_cycles <= 12 or budget_seconds <= 0 or max_cost < 0:
        raise ValueError("invalid bounds")
    path = Path(state_path)
    config = {"agent": agent, "candidate": candidate_cmd, "verifier": verifier_cmd,
              "max_cycles": max_cycles, "budget_seconds": budget_seconds, "max_cost": max_cost}
    fingerprint = digest(config)
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
        "config_sha256": fingerprint, "agent": agent, "cycles": [], "pending": None, "status": "ready"}
    if state["config_sha256"] != fingerprint or state["agent"] != agent:
        raise RuntimeError("state/config mismatch; never reuse another agent's ledger")
    if state.get("pending"):
        raise RuntimeError("ambiguous pending operation: inspect external receipts; do not retry")
    if state["status"] in ("failed", "budget_exhausted", "complete"):
        return state
    start = time.monotonic()
    for index in range(len(state["cycles"]) + 1, max_cycles + 1):
        if time.monotonic() - start >= budget_seconds:
            state["status"] = "budget_exhausted"
            break
        key = digest({"config": fingerprint, "index": index})
        state["pending"] = {"cycle": index, "operation_key": key, "phase": "candidate"}
        save(path, state)
        # Deliberately do not auto-retry after process crash or ambiguous response.
        try:
            candidate = subprocess.run(candidate_cmd, shell=False, capture_output=True, text=True,
                                       timeout=max(1, budget_seconds - (time.monotonic() - start)))
            state["pending"]["phase"] = "verification"
            state["pending"]["candidate_sha256"] = hashlib.sha256(candidate.stdout.encode()).hexdigest()
            save(path, state)
            if candidate.returncode != 0:
                raise RuntimeError("candidate failed")
            verifier = subprocess.run(verifier_cmd, shell=False, capture_output=True, text=True,
                                      timeout=max(1, budget_seconds - (time.monotonic() - start)))
            if verifier.returncode != 0:
                raise RuntimeError("independent verifier rejected candidate")
            receipt = {"cycle": index, "operation_key": key,
                       "candidate_stdout_sha256": hashlib.sha256(candidate.stdout.encode()).hexdigest(),
                       "verifier_stdout_sha256": hashlib.sha256(verifier.stdout.encode()).hexdigest(),
                       "candidate_exit": candidate.returncode, "verifier_exit": verifier.returncode,
                       "independent_evaluation": "external_command_pass_only",
                       "improvement_claim": "NOT_ESTABLISHED", "cost": None}
            state["cycles"].append(receipt)
            state["pending"] = None
            save(path, state)
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            state["status"] = "failed"
            state["failure_type"] = type(exc).__name__
            # Preserve pending; manual reconciliation is mandatory.
            save(path, state)
            return state
    else:
        state["status"] = "complete"
    save(path, state)
    return state

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True, choices=["Ouroboros", "Cerberus", "Fenrir"])
    parser.add_argument("--state", required=True)
    parser.add_argument("--candidate", nargs="+", required=True)
    parser.add_argument("--verifier", nargs="+", required=True)
    parser.add_argument("--max-cycles", type=int, default=12)
    parser.add_argument("--budget-seconds", type=int, default=3600)
    args = parser.parse_args()
    print(json.dumps(run(args.state, args.agent, args.candidate, args.verifier,
                         args.max_cycles, args.budget_seconds), sort_keys=True))

if __name__ == "__main__":
    main()
