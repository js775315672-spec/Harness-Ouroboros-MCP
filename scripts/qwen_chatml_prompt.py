#!/usr/bin/env python3
"""Bounded Qwen2.5 ChatML wrapper for llama-completion without free-form roles.

All task text is untrusted; callers cannot inject ChatML role delimiters.
No model output, shell commands or source patch are executed here.
"""

BEGIN = "<|im_start|>"
END = "<|im_end|>"
SYSTEM = (
    "You are a careful Python code repair assistant. "
    "Follow the exact task and return only the required Python expression, "
    "not explanations, examples, function bodies, or Markdown."
)


def format_chatml(task, *, system=SYSTEM):
    if (not isinstance(task, str) or not 1 <= len(task.encode("utf-8")) <= 5000
            or not isinstance(system, str) or not system.strip()):
        raise ValueError("invalid bounded ChatML task")
    if any(token in task or token in system for token in (BEGIN, END, "\x00", "\x1b", "\r")):
        raise ValueError("task includes disallowed role or control marker")
    result = (
        BEGIN + "system\n" + system + END + "\n"
        + BEGIN + "user\n" + task + END + "\n"
        + BEGIN + "assistant\n"
    )
    if len(result.encode("utf-8")) > 6000:
        raise ValueError("formatted ChatML exceeds context budget")
    return result
