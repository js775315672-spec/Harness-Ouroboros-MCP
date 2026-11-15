#!/usr/bin/env python3
"""Bridge real Qwen review artifacts into a bounded, fail-closed loop decision.

This bridge does not assert independent CI attestation, apply a patch, run a
coding agent, or fabricate a source commit. It only requests the next action.
"""
import argparse
import json
from pathlib import Path
from autonomous_loop_controller import transition

def _read(path):
    raw = Path(path).read_bytes()
    if not raw or len(raw) > 120000:
        raise ValueError("invalid evidence size")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate evidence key")
            result[key] = value
        return result
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError("evidence must be an object")
    return value

def decide(inference, regression, review):
    if inference.get("status") != "accepted_for_review":
        return {"decision": "stop", "reason": "model_proposal_not_accepted"}
    if regression.get("status") != "isolated_regression_passed":
        return {"decision": "stop", "reason": "isolated_regression_not_passed"}
    if review.get("decision") != "ready_for_human_review":
        return {"decision": "stop", "reason": "human_review_gate_not_ready"}
    if any(item.get("merge_authorized") is not False for item in (inference, regression, review)):
        raise ValueError("unsafe merge authorization")
    if inference.get("patch_applied") is not False or regression.get("patch_applied_to_checkout") is not False:
        raise ValueError("unexpected source modification")
    if review.get("model_patch_applied") is not False:
        raise ValueError("review gate claims patch application")
    proof = regression.get("provenance")
    if not isinstance(proof, dict) or proof.get("provenance_verified") is not True or proof.get("model_response_replayed") is not True:
        raise ValueError("model provenance not verified")
    state = transition({"cycle": 1, "attempt": 1, "phase": "await_evidence"})
    return {"decision": "await_independent_ci_and_external_coding_executor",
            "controller_decision": state["decision"],
            "review_ready": True, "source_modified": False,
            "independent_ci_attested": False, "autonomous_coding_connected": False,
            "merge_authorized": False,
            "next_step": "independently attest CI and connect an approved sandboxed coding executor"}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--regression", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = decide(_read(args.inference), _read(args.regression), _read(args.review))
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        result = {"decision": "blocked", "reason": str(exc)[:200], "merge_authorized": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["decision"] == "await_independent_ci_and_external_coding_executor" else 2

if __name__ == "__main__":
    raise SystemExit(main())
