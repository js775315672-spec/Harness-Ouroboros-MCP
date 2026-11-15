#!/usr/bin/env python3
"""Build a scoped, single-line diff from a model's untrusted source-line proposal.

This builder does not read or write any repository files, execute model code,
approve patch application, or authorize merging.
"""
import re

TARGET_PATH="tests/test_model_feedback_loop.py"
MAX_REPLACEMENT_CHARS=500

def build_single_line_diff(raw,old_line,line_number):
    if not isinstance(raw,str) or not isinstance(old_line,str):
        raise ValueError("replacement and source must be strings")
    if type(line_number) is not int or line_number<1:
        raise ValueError("invalid source line number")
    if len(raw)>MAX_REPLACEMENT_CHARS or "\r" in raw or "\x00" in raw:
        raise ValueError("unsafe or oversized replacement")
    if raw.endswith("\n"):
        raw=raw[:-1]
    if "\n" in raw or not raw:
        raise ValueError("model must propose exactly one source line")
    match=re.fullmatch(r"(?: {8})?answer[ \t]*=[ \t]*(.+)",raw)
    if not match or len(match.group(1))<2 or not (match.group(1).startswith('"') and match.group(1).endswith('"')):
        raise ValueError("proposal must be one quoted answer assignment")
    raw="        answer="+match.group(1)
    if raw==old_line:
        raise ValueError("proposal must change the existing answer assignment")
    if "\n" in old_line or "\r" in old_line or not old_line.startswith("        answer="):
        raise ValueError("unsafe original source line")
    path=TARGET_PATH
    return (f"diff --git a/{path} b/{path}\n"
            f"--- a/{path}\n+++ b/{path}\n"
            f"@@ -{line_number} +{line_number} @@\n"
            f"-{old_line}\n+{raw}\n")
