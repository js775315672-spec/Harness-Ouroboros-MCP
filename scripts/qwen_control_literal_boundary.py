#!/usr/bin/env python3
"""Narrow opt-in renderer normalization for Qwen code-expression tasks.

Only *physical* NUL/ESC bytes between balanced Python quotes are escaped into
their equivalent textual Python string escape sequence. This does not repair
AST logic, allow model shell commands, or change the standard GGUF path.
Unexpected control bytes (e.g. terminal ANSI outside quoted literals) block.
The independent AST and no-network Docker safety gates are still mandatory.
"""
CONTROL_ESCAPE = {"\x00": r"\x00", "\x1b": r"\x1b"}


def escape_quoted_control_bytes(stdout):
    if not isinstance(stdout, str) or len(stdout.encode("utf-8")) > 6000:
        raise ValueError("invalid bounded model output")
    if "\r" in stdout:
        raise ValueError("carriage returns are forbidden in model output")
    quote = None
    escaped = False
    replacements = 0
    output = []
    for char in stdout:
        if char in CONTROL_ESCAPE:
            if quote is None:
                raise ValueError("control byte outside a Python quoted literal")
            output.append(CONTROL_ESCAPE[char])
            replacements += 1
            escaped = False
            continue
        output.append(char)
        if escaped:
            escaped = False
        elif quote is not None and char == "\\":
            escaped = True
        elif quote is None and char in ("'", '"'):
            quote = char
        elif char == quote:
            quote = None
    if quote is not None:
        raise ValueError("unbalanced model string literal")
    normalized = "".join(output)
    if len(normalized.encode("utf-8")) > 6000:
        raise ValueError("escaped output exceeds model response budget")
    return normalized, replacements
