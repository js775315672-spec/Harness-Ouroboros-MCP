#!/usr/bin/env python3
"""Isolated proposed W01 validator; preserves digest-locked P3g baseline.

Coordinator-authored candidate, not model output and not a promoted validator.
"""
from development_ledger import validate as validate_legacy


def _safe_text(value, max_utf8_bytes, allow_whitespace_only=False):
    if not isinstance(value, str) or not value:
        return False
    if not allow_whitespace_only and not value.strip():
        return False
    # Reject C0/C1 control characters, including NUL, newline, and ESC.
    if any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value):
        return False
    try:
        return len(value.encode("utf-8")) <= max_utf8_bytes
    except UnicodeEncodeError:
        return False


def validate(records):
    """Validate frozen legacy proof first, then W01 UTF-8/controls bounds."""
    count = validate_legacy(records)
    for record in records:
        if not _safe_text(record["change"], 256):
            raise ValueError("invalid change description or UTF-8 length")
        fixes = record["fixes"]
        if len(fixes) > 12 or any(
            not _safe_text(item, 128, allow_whitespace_only=True)
            for item in fixes
        ):
            raise ValueError("invalid fixes, control characters, or UTF-8 length")
    return count
