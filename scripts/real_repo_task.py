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
        "Fix only the answer assignment in the existing "
        "tests/test_model_feedback_loop.py test_reject_multiple_fences. "
        "The string currently uses literal backslash-n; the corrected "
        "Python assignment must evaluate to actual newline characters. "
        "Output one complete answer= assignment line. "
        "Never generate a diff, additional files, code execution or secrets."
    )
    return {"task":TASK,"contract":contract,"prompt":prompt,
            "model_called":False,"patch_applied":False,
            "requires_human_review":True}
