#!/usr/bin/env python3
"""Fail-closed autonomous development loop controller.

Planning and state transitions only. This module NEVER invokes a model,
executes code, writes source files, pushes commits, or merges PRs.
An external sandboxed executor must supply independently verified evidence.
"""
import argparse
import json
from pathlib import Path

CHECKS = ("harness", "ouroboros", "regression", "secrets")
MAX_ATTEMPTS = 5
MAX_CYCLES = 30

def transition(state, evidence=None):
    if not isinstance(state, dict):
        raise ValueError("invalid state")
    if set(state) != {"cycle", "attempt", "phase"}:
        raise ValueError("unexpected state fields")
    cycle, attempt, phase = state["cycle"], state["attempt"], state["phase"]
    if type(cycle) is not int or not 1 <= cycle <= MAX_CYCLES:
        raise ValueError("cycle out of bounds")
    if type(attempt) is not int or not 1 <= attempt <= MAX_ATTEMPTS:
        raise ValueError("attempt out of bounds")
    if phase not in ("await_evidence", "stopped"):
        raise ValueError("invalid phase")
    if phase == "stopped":
        return {"decision": "stop", "reason": "already_stopped", "state": state}
    if evidence is None:
        return {"decision": "await_external_executor", "state": state,
                "model_connected": False, "code_executed": False,
                "requires_human_merge_approval": True}
    if not isinstance(evidence, dict) or set(evidence) != {"source_changed", "checks", "commit", "ci_url"}:
        raise ValueError("incomplete evidence")
    if evidence["source_changed"] is not True:
        raise ValueError("no source change: verification repetitions are not development")
    sha = evidence["commit"]
    if not isinstance(sha, str) or len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("invalid commit")
    url = evidence["ci_url"]
    if not isinstance(url, str) or not url.startswith("https://github.com/") or "/actions/runs/" not in url:
        raise ValueError("invalid CI reference")
    checks = evidence["checks"]
    if not isinstance(checks, dict) or set(checks) != set(CHECKS) or any(checks[k] not in ("pass", "fail") for k in CHECKS):
        raise ValueError("invalid check evidence")
    if any(checks[k] == "fail" for k in CHECKS):
        if attempt == MAX_ATTEMPTS:
            return {"decision": "stop", "reason": "retry_budget_exhausted",
                    "state": {"cycle": cycle, "attempt": attempt, "phase": "stopped"}}
        return {"decision": "request_external_fix", "failed_checks": [k for k in CHECKS if checks[k] == "fail"],
                "state": {"cycle": cycle, "attempt": attempt + 1, "phase": "await_evidence"},
                "model_connected": False}
    if cycle == MAX_CYCLES:
        return {"decision": "human_review", "state": {"cycle": cycle, "attempt": attempt, "phase": "stopped"},
                "merge_authorized": False}
    return {"decision": "request_next_external_task",
            "state": {"cycle": cycle + 1, "attempt": 1, "phase": "await_evidence"},
            "merge_authorized": False, "independent_ci_attested": False}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    try:
        state = json.loads(args.state.read_text()) if args.state else {"cycle": 1, "attempt": 1, "phase": "await_evidence"}
        evidence = json.loads(args.evidence.read_text()) if args.evidence else None
        result = transition(state, evidence)
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"decision": "blocked", "reason": str(exc)[:200]}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
