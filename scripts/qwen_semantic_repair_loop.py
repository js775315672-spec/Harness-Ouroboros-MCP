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
        "The previous output could not be used as one guarded expression. "
        "Do NOT output a complete function, if statement, raise, return, "
        "Markdown or explanation. Output only a Python boolean expression.",
    "candidate_negative_failed":
        "Disposable tests rejected the candidate: absent cycle, None, boolean "
        "True/False, text, float, zero, and negatives must all raise ValueError. "
        "Positive integers must remain valid. Reconsider bool being a subclass "
        "of int and avoid unsafe comparisons before type validation.",
    "candidate_regression_failed":
        "Existing feedback controller tests regressed. Your new invalid-cycle "
        "predicate should not reject positive integer cycles and should not "
        "change the existing proposal/decision checks."
}


def build_prompt(previous_category=None, attempt=1):
    if type(attempt) is not int or not 1 <= attempt <= MAX_ATTEMPTS:
        raise ValueError("invalid prompt attempt")
    prompt = (
        "Write ONE Python boolean expression that evaluates True when the "
        "proposal dictionary contains an INVALID 'cycle': missing, None, "
        "boolean, non-integer, zero, or negative. Positive integers are valid. "
        "The expression will be safely appended using OR to the existing "
        "feedback_controller.py first if guard. The program already raises "
        "ValueError when this condition is True. Do NOT write if, raise, "
        "return, a function, Markdown, or an explanation. Output only the "
        "boolean expression using the variable proposal. Keep it short. "
        "Check invalid types before numeric comparisons."
    )
    if previous_category:
        if previous_category not in FEEDBACK:
            raise ValueError("untrusted feedback category")
        prompt += "\nTrusted test feedback: " + FEEDBACK[previous_category]
    if attempt == 2:
        prompt += (
            "\nFormat retry: your entire response must be only an expression. "
            "You may combine several checks with OR. Do not repeat any "
            "existing proposal or decision checks."
        )
    elif attempt == 3:
        prompt += (
            "\nFinal format retry: output a single expression with checks "
            "covering invalid integer type, boolean values, and nonpositive "
            "numbers. Avoid comparing a non-number with a number. "
            "No code block or statement."
        )
    return prompt


def normalize_candidate(raw, source):
    """Accept one valid full guard or assemble a single AST-approved predicate."""
    try:
        full_line = normalize_model_line(raw)
        inspected = inspect_semantic_line(full_line, source)
        return full_line, inspected
    except (ValueError, SyntaxError):
        pass
    if not isinstance(raw, str) or len(raw) > 350 or "\r" in raw or "\x00" in raw:
        raise ValueError("invalid model predicate response")
    expression = raw.strip()
    fence = chr(96) * 3
    if expression.startswith(fence):
        parts = expression.split("\n")
        if (len(parts) != 3 or parts[0] not in (fence, fence + "python") or
                parts[2] != fence):
            raise ValueError("invalid expression fence")
        expression = parts[1].strip()
    if (not expression or len(expression) > 250 or "\n" in expression or
            expression.startswith("if ") or expression.endswith(":")):
        raise ValueError("a single boolean expression is required")
    line = ORIGINAL[:-1] + " or (" + expression + "):"
    return line, inspect_semantic_line(line, source)


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
        prompt = build_prompt(category, attempt)
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
            normalized, inspected = normalize_candidate(raw, source)
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
