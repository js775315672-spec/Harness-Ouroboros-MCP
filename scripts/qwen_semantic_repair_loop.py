#!/usr/bin/env python3
"""Unhinted Qwen source repair -> Docker failure feedback -> bounded retry.

The prompt never supplies a correct replacement line. A trusted categorical
failure from disposable tests may influence the next prompt. Docker logs,
untrusted source text, and model outputs are never replayed as instructions.
"""
import hashlib

try:
    from .qwen_source_guard import ORIGINAL, TARGET
    from .qwen_source_trial import normalize_model_line
    from .qwen_semantic_source_guard import inspect_semantic_line
except ImportError:
    from qwen_source_guard import ORIGINAL, TARGET
    from qwen_source_trial import normalize_model_line
    from qwen_semantic_source_guard import inspect_semantic_line

MAX_ATTEMPTS = 3
RECOVERABLE = {"candidate_negative_failed", "candidate_regression_failed"}
FEEDBACK = {
    "ast_scope_rejected":
        "The prior line failed the AST scope gate. Preserve the two original "
        "reject checks in order, append only safe cycle-related OR predicates, "
        "and output exactly one conditional line. Do not add statements.",
    "candidate_negative_failed":
        "Disposable tests rejected the patch: invalid cycles include absent, "
        "None, boolean True/False, text, float, zero and negatives. They must "
        "raise ValueError; positive integers must remain accepted. Repair the "
        "predicate while preserving the original checks.",
    "candidate_regression_failed":
        "The existing feedback controller tests failed for the candidate. "
        "Preserve the original proposal and decision validation while "
        "repairing the cycle checks. Return only one conditional line."
}


def build_prompt(previous_category=None):
    prompt = (
        "Repair the FIRST if guard line in scripts/feedback_controller.py. "
        "The function should reject a proposal with a missing cycle, a bool, "
        "a non-integer cycle or an integer cycle <= 0 by raising ValueError. "
        "Valid positive integer cycles should retain the existing behavior. "
        "Do not weaken any existing rejection of invalid proposal/decision. "
        "Output ONLY the full replacement Python if line, with its final colon. "
        "No Markdown, code fence, explanation or extra statements.\n"
        "Original guard line:\n" + ORIGINAL
    )
    if previous_category:
        if previous_category not in FEEDBACK:
            raise ValueError("untrusted feedback category")
        prompt += "\nTrusted validation feedback: " + FEEDBACK[previous_category]
    return prompt


def run_loop(source, generate, evaluate, max_attempts=MAX_ATTEMPTS):
    """generate(prompt) is model inference; evaluate(line) is real Docker compare."""
    if type(max_attempts) is not int or not 1 <= max_attempts <= MAX_ATTEMPTS:
        raise ValueError("invalid retry budget")
    if not isinstance(source, str) or source.splitlines().count(ORIGINAL) != 1:
        raise ValueError("ambiguous source baseline")
    if not callable(generate) or not callable(evaluate):
        raise ValueError("missing model or independent evaluator")
    attempts, category, final_candidate, final_comparison = [], None, None, None
    comparisons = 0
    for attempt in range(1, max_attempts + 1):
        prompt = build_prompt(category)
        raw = generate(prompt)
        row = {"attempt": attempt, "prompt_sha256": hashlib.sha256(
            prompt.encode("utf-8")).hexdigest()}
        if isinstance(raw, str):
            row["response_sha256"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            row["response_length"] = len(raw)
            row["response_preview"] = raw[:160]
        else:
            row["response_sha256"] = None
            row["response_length"] = None
        try:
            normalized = normalize_model_line(raw)
            inspected = inspect_semantic_line(normalized, source)
        except (ValueError, SyntaxError):
            row["status"] = "ast_scope_rejected"
            category = "ast_scope_rejected"
            attempts.append(row)
            continue
        row["line_sha256"] = inspected["line_sha256"]
        result = evaluate(normalized)
        comparisons += 1
        if not isinstance(result, dict):
            raise ValueError("invalid Docker comparison result")
        status = result.get("status")
        if status not in RECOVERABLE | {"isolated_source_repair_passed",
                                      "baseline_regression_failed",
                                      "negative_control_invalid",
                                      "docker_execution_failed"}:
            raise ValueError("unexpected Docker status")
        row["status"] = status
        row["docker_tests"] = {
            key: (value.get("passed") if isinstance(value, dict) else None)
            for key, value in (
                (k, result.get(k)) for k in (
                    "baseline_regression", "baseline_negative_control",
                    "candidate_regression", "candidate_negative_control"))
        }
        attempts.append(row)
        final_comparison = result
        if status == "isolated_source_repair_passed":
            if (result.get("source_checkout_modified") is not False or
                    result.get("merge_authorized") is not False or
                    result.get("source_sha256") != inspected["source_sha256"] or
                    result.get("candidate_line_sha256") != inspected["line_sha256"]):
                raise ValueError("Docker provenance or write safety mismatch")
            final_candidate = {
                "model_raw_response": raw, "candidate_line": normalized,
                "source_sha256": inspected["source_sha256"],
                "candidate_line_sha256": inspected["line_sha256"],
                "response_sha256": row["response_sha256"],
                "attempt": attempt, "human_review_required": True,
                "source_checkout_modified": False, "merge_authorized": False,
            }
            break
        if status not in RECOVERABLE:
            break
        category = status
    return {
        "status": "isolated_source_repair_passed" if final_candidate else
                  (attempts[-1]["status"] if attempts else "blocked"),
        "model_calls": len(attempts), "docker_comparisons": comparisons,
        "max_model_calls": max_attempts, "attempts": attempts,
        "candidate": final_candidate, "last_comparison": final_comparison,
        "model_output_executed_in_checkout": False,
        "source_checkout_modified": False, "merge_authorized": False,
        "no_exact_solution_in_prompts": True, "paid_api_used": False,
        "secrets_used": False,
    }
