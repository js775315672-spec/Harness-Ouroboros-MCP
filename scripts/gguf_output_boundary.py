#!/usr/bin/env python3
"""Narrow, fail-closed cleanup of a known llama-completion terminal renderer marker.

This function removes one exact terminal presentation suffix, never changes Python
expressions, never converts invalid program text into a repaired candidate, and
does not bypass the AST or disposable Docker verification gates.
"""

TERMINATOR = "[end of text]"


def extract_completion(stdout, max_output_bytes=6000):
    if not isinstance(stdout, str):
        raise ValueError("completion output must be text")
    if type(max_output_bytes) is not int or not 1 <= max_output_bytes <= 6000:
        raise ValueError("invalid output budget")
    if len(stdout.encode("utf-8")) > max_output_bytes:
        raise ValueError("model output exceeded capped response budget")
    if "\x00" in stdout or "\x1b" in stdout or "\r" in stdout:
        raise ValueError("control bytes are not permitted in completion output")
    clean = stdout.strip()
    marker_stripped = False
    if clean.endswith(TERMINATOR):
        body = clean[:-len(TERMINATOR)]
        if not body or not body[-1].isspace():
            raise ValueError("completion marker lacks a word boundary")
        clean = body.strip()
        marker_stripped = True
    if not clean or TERMINATOR in clean:
        raise ValueError("empty or ambiguous completion output")
    return clean, marker_stripped
