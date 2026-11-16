#!/usr/bin/env python3
"""Optional model-stagnation-aware wrapper around immutable historical feedback.

Do not edit scripts/feedback_controller.py: prior Qwen source-commit and replay
evidence pins its byte-for-byte historical source hash. This adapter never
initiates model inference, executes candidate source, pushes or merges.
"""
from feedback_controller import feedback
from model_stagnation_gate import evaluate

CONTEXT_FIELDS = frozenset(("task_sha256","model_sha256",
                            "baseline_source_sha256"))


def feedback_with_history(proposal, checks, model_history, model_context,
                          attempt=1, max_attempts=5):
    """Stop repeated model failures while leaving legacy feedback unchanged."""
    # Let the preserved historical verifier first validate proposal, checks,
    # status, attempt limits, and safety boundary.
    legacy = feedback(proposal, checks, attempt, max_attempts)
    if (type(model_context) is not dict
            or frozenset(model_context) != CONTEXT_FIELDS
            or type(model_history) is not list):
        raise ValueError("immutable task/model/source context and list required")
    verdict = evaluate(model_history, model_context["task_sha256"],
                       model_context["model_sha256"],
                       model_context["baseline_source_sha256"],
                       max_attempts=max_attempts)
    if verdict["decision"] == "stop":
        return {"decision":"stop", "reason": verdict["reason"],
                "cycle": proposal["cycle"], "attempt":attempt,
                "failed_checks": legacy.get("failed_checks",[]),
                "model_retry_gate":verdict,
                "model_call_performed":False,
                "human_merge_approval_required":True,
                "merge_authorized":False}
    if model_history and model_history[-1]["outcome"] != "candidate_passed":
        # Infrastructure can be fully green although model source failed.
        # Declare model rejection separately rather than falsifying the
        # independent Harness regression check status.
        if attempt >= max_attempts:
            return {"decision":"stop","reason":"retry_budget_exhausted",
                    "cycle":proposal["cycle"],"attempt":attempt,
                    "model_retry_gate":verdict,"model_call_performed":False,
                    "human_merge_approval_required":True,
                    "merge_authorized":False}
        return {
            "decision":"request_fix","cycle":proposal["cycle"],
            "attempt":attempt,"next_attempt":attempt+1,
            "task":proposal["task"],
            "failed_checks":[*legacy.get("failed_checks",[]),
                             "model_candidate"],
            "model_retry_gate":verdict,
            "instruction":"Fix model-authored source; do not change tests or gates.",
            "model_call_performed":False,
            "human_merge_approval_required":True,
            "merge_authorized":False
        }
    return {**legacy, "model_retry_gate":verdict,
            "model_call_performed":False,"merge_authorized":False}
