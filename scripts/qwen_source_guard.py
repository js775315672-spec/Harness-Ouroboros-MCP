#!/usr/bin/env python3
"""Source-anchored, executable-code repair gate for a narrowly scoped Qwen task.

Unlike the existing test-string experiment, this permits one actual Python
source-condition change. The only acceptable behavior is a stronger invalid
cycle guard in feedback_controller.feedback. It does NOT apply or execute code.
"""
import ast
import hashlib
from pathlib import Path

try:
    from .qwen_task_scope_gate import validate_task
    from .scoped_patch_gate import inspect_scoped_patch
except ImportError:
    from qwen_task_scope_gate import validate_task
    from scoped_patch_gate import inspect_scoped_patch

TARGET = "scripts/feedback_controller.py"
ORIGINAL = '    if not isinstance(proposal,dict) or proposal.get("decision")!="propose":'
EXPECTED = ('    if not isinstance(proposal,dict) or '
            'proposal.get("decision")!="propose" or '
            'type(proposal.get("cycle")) is not int or proposal["cycle"] < 1:')
TASK = {
    "task_id": "feedback_cycle_guard",
    "goal": "Reject invalid feedback cycle values without weakening current checks.",
    "files": [TARGET],
    "requires_human_review": True,
}
# The existing generic scoped diff contract mandates an acceptance test in the
# patch. For this one-line code task we instead enforce an exact AST expression
# and require separate disposable baseline/candidate tests before human review.

def _feedback_guard(tree):
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "feedback"]
    if len(funcs) != 1 or not funcs[0].body or not isinstance(funcs[0].body[0], ast.If):
        raise ValueError("unique feedback entry guard missing")
    return funcs[0].body[0]

def _guard_expression(line):
    parsed = ast.parse("def _guard():\n" + line + "\n        pass\n")
    return parsed.body[0].body[0].test

def inspect_line(raw, source):
    scope = validate_task(TASK)
    if scope["execution_authorized"] is not False or scope["merge_authorized"] is not False:
        raise ValueError("unsafe task scope")
    if not isinstance(raw, str) or not isinstance(source, str):
        raise ValueError("source and model line required")
    if len(raw) > 350 or not raw or "\x00" in raw or "\r" in raw:
        raise ValueError("unsafe model line")
    line = raw.removesuffix("\n")
    if "\n" in line or not line.startswith("    if ") or not line.endswith(":"):
        raise ValueError("Qwen must output one four-space-indented conditional line")
    if len(source.encode("utf-8")) > 12000 or not source.endswith("\n"):
        raise ValueError("invalid source budget or newline")
    lines = source.splitlines(keepends=True)
    positions = [i for i, existing in enumerate(lines) if existing.rstrip("\n") == ORIGINAL]
    if len(positions) != 1:
        raise ValueError("original feedback source anchor missing or ambiguous")
    try:
        expected_guard = _guard_expression(EXPECTED)
        proposed_guard = _guard_expression(line)
        if ast.dump(proposed_guard, include_attributes=False) != ast.dump(expected_guard, include_attributes=False):
            raise ValueError("candidate must precisely tighten the trusted cycle guard")
        original_ast = ast.parse(source)
        if ast.dump(_feedback_guard(original_ast).test, include_attributes=False) != ast.dump(
                _guard_expression(ORIGINAL), include_attributes=False):
            raise ValueError("original guard does not match trusted baseline")
        updated = list(lines)
        updated[positions[0]] = line + "\n"
        modified = "".join(updated)
        changed_ast = ast.parse(modified)
        # Exclude only the vetted guard expression, proving every other executable
        # AST node in the original file is unchanged.
        _feedback_guard(original_ast).test = ast.Constant(value=True)
        _feedback_guard(changed_ast).test = ast.Constant(value=True)
        if ast.dump(original_ast, include_attributes=False) != ast.dump(changed_ast, include_attributes=False):
            raise ValueError("unexpected source AST changes")
    except (SyntaxError, TypeError) as exc:
        raise ValueError("invalid Python repair") from exc
    n = positions[0] + 1
    patch = (f"diff --git a/{TARGET} b/{TARGET}\n"
             f"--- a/{TARGET}\n+++ b/{TARGET}\n"
             f"@@ -{n} +{n} @@\n-{ORIGINAL}\n+{line}\n")
    return {"status": "bounded_source_proposal", "task_id": TASK["task_id"],
            "target": TARGET, "line_number": n, "patch": patch,
            "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "model_line_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            "source_ast_guard_verified": True,
            "source_executable_condition_changed": True,
            "source_checkout_changed": False, "model_code_executed": False,
            "merge_authorized": False, "requires_disposable_tests": True}

if __name__ == "__main__":
    print("Read-only Python source repair gate; no model or patch execution.")
