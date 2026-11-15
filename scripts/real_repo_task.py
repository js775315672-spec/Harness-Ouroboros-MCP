#!/usr/bin/env python3
"""Deterministic, bounded prompt for a real repository regression task.

This prepares a task for Qwen; it does not invoke a model or apply its output.
"""
try:
    from .coding_task_contract import validate_task
except ImportError:
    from coding_task_contract import validate_task

TASK={
 "task_id":"feedback_parser_regression",
 "goal":"Improve regression coverage for the existing model feedback parser. Add a test that rejects two separate Python fenced blocks, and preserve existing behavior.",
 "allowed_files":["tests/test_model_feedback_loop.py"],
 "acceptance_tests":["tests/test_model_feedback_loop.py"],
 "max_attempts":2,
}

def prepare():
    contract=validate_task(TASK)
    prompt=(
        "You are proposing a minimal change to a Python repository. "
        "Return ONLY a unified git diff, no Markdown fences or explanation. "
        "Do not execute code or request secrets. "
        "Change exactly tests/test_model_feedback_loop.py, NOT scripts/model_feedback_loop.py. "
        "Fix the EXISTING test_reject_multiple_fences assignment so it produces actual newline characters at runtime instead of literal backslash-n. "
        "Replace ONLY that one line, without changing the method name or other code. "
        "Return precisely six lines: diff --git header, --- marker, +++ marker, @@ one-line hunk header, one original - line, one corrected + line. "
        "No extra files, hunks, prose or code fences. End with newline. If unable, output REJECT."
    )
    return {"task":TASK,"contract":contract,"prompt":prompt,
            "model_called":False,"patch_applied":False,
            "requires_human_review":True}
