#!/usr/bin/env python3
"""Two bounded AST microtasks for Qwen's experimental source repair.

Only validated model expressions are assembled into a trusted source-line
template. Never runs model output or changes the repository checkout.
"""
import ast
import hashlib

try:
    from .qwen_source_guard import ORIGINAL, TASK, inspect_line
except ImportError:
    from qwen_source_guard import ORIGINAL, TASK, inspect_line

KINDS = ("type", "range")
EXPECTED = {
    "type": 'type(proposal.get("cycle")) is not int',
    "range": 'proposal["cycle"] < 1',
}
PROMPTS = {
    "type": (
        "Write ONLY one Python boolean expression which checks that "
        "proposal.get('cycle') is NOT of exactly builtin int type. "
        "A bool must be rejected. Use the type(...) is not int syntax. "
        "No if statement, colon, 'or', comments, or explanation."
    ),
    "range": (
        "Write ONLY one Python boolean expression which checks that "
        "proposal['cycle'] is less than integer 1. "
        "No if statement, colon, 'or', comments, or explanation."
    ),
}
MODE = "ast_microfragments_v1"
MAX_ATTEMPTS_PER_KIND = 3


def normalize_fragment(kind, raw):
    """Accept cosmetic whitespace/fencing, not arbitrary Python expressions."""
    if kind not in KINDS or not isinstance(raw, str):
        raise ValueError("invalid fragment")
    if len(raw) > 180 or "\r" in raw or "\x00" in raw:
        raise ValueError("unsafe fragment size or characters")
    value = raw.strip()
    fence = chr(96) * 3
    if value.startswith(fence):
        parts = value.split("\n")
        if len(parts) != 3 or parts[0] not in (fence, fence + "python") or parts[-1] != fence:
            raise ValueError("invalid fragment fence")
        value = parts[1].strip()
    if not value or "\n" in value or len(value) > 160:
        raise ValueError("only one expression permitted")
    try:
        actual = ast.parse(value, mode="eval")
        expected = ast.parse(EXPECTED[kind], mode="eval")
    except SyntaxError as exc:
        raise ValueError("invalid Python expression") from exc
    if ast.dump(actual, include_attributes=False) != ast.dump(expected, include_attributes=False):
        raise ValueError("fragment AST differs from the trusted task contract")
    return value


def build_candidate(responses, source):
    if not isinstance(responses, dict) or set(responses) != set(KINDS):
        raise ValueError("both model fragments are mandatory")
    parts = [normalize_fragment(kind, responses[kind]) for kind in KINDS]
    line = ORIGINAL[:-1] + " or " + " or ".join(parts) + ":"
    inspection = inspect_line(line, source)
    return {
        "provider": "qwen", "status": "proposal", "task_id": TASK["task_id"],
        "generation_mode": MODE,
        "microtask_responses": [
            {"kind": kind, "raw_response": responses[kind]} for kind in KINDS
        ],
        "line": line,
        "source_patch": inspection["patch"],
        "source_sha256": inspection["source_sha256"],
        "model_line_sha256": inspection["model_line_sha256"],
    }


def run_microtask_trials(generate, source, max_attempts=MAX_ATTEMPTS_PER_KIND):
    """Perform at most six model calls; stop without a patch on any failure."""
    if type(max_attempts) is not int or not 1 <= max_attempts <= MAX_ATTEMPTS_PER_KIND:
        raise ValueError("invalid per-fragment retry budget")
    attempts = []
    accepted = {}
    for kind in KINDS:
        for index in range(1, max_attempts + 1):
            prompt = PROMPTS[kind]
            if index > 1:
                prompt += " Previous response failed the exact-expression AST gate. Retry with only the expression."
            raw = generate(kind, prompt)
            row = {"kind": kind, "attempt": index}
            if isinstance(raw, str):
                row["response_sha256"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                row["response_length"] = len(raw)
            else:
                row["response_sha256"] = None
                row["response_length"] = None
            try:
                normalize_fragment(kind, raw)
            except ValueError:
                row["status"] = "rejected"
                row["reason_type"] = "expression_ast_rejected"
            else:
                row["status"] = "accepted"
                accepted[kind] = raw
            attempts.append(row)
            if row["status"] == "accepted":
                break
        if kind not in accepted:
            return {"status": "model_proposal_rejected",
                    "model_calls": len(attempts), "attempts": attempts,
                    "candidate": None}
    candidate = build_candidate(accepted, source)
    return {"status": "accepted_for_disposable_review",
            "model_calls": len(attempts), "attempts": attempts,
            "candidate": candidate}
