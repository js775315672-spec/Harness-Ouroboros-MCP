#!/usr/bin/env python3
"""Paired prompt-context wrapper for the SAME local student model adapter.

Reads the existing ORIL adapter request on stdin and prepends a pinned,
bounded public teacher-example context. Does not load/train weights, authenticate
the teacher, or evaluate heldout tasks independently.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

from oril_v2_bounded_adapter_capture import capture_adapter


def strict(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def parse_json(raw):
    return json.loads(raw, object_pairs_hook=strict,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def read_prefix(path, expected_sha):
    """Pin the exact bytes, reject symlink ancestry, require operator-provided SHA."""
    if not isinstance(expected_sha, str) or len(expected_sha) != 64 or any(c not in "0123456789abcdef" for c in expected_sha):
        raise ValueError("expected SHA-256 must be lowercase 64-hex")
    p = Path(path).absolute()
    for item in (p, *p.parents):
        if item.is_symlink():
            raise ValueError("symlinked prompt path rejected")
    if not p.is_file():
        raise ValueError("prompt prefix must be a regular local file")
    with p.open("rb") as f:
        raw = f.read(3001)
    if len(raw) > 3000 or not raw:
        raise ValueError("prompt prefix must be 1..3000 bytes")
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError("prompt prefix SHA mismatch")
    prefix = raw.decode("utf-8")
    if "\x00" in prefix or not prefix.strip():
        raise ValueError("invalid prefix")
    return prefix


def prepare_request(raw_request, prefix):
    if len(raw_request) > 65536:
        raise ValueError("request too large")
    req = parse_json(raw_request)
    if not isinstance(req, dict) or set(req) != {"question", "case_id", "seed"}:
        raise ValueError("invalid adapter request schema")
    if (not isinstance(req["question"], str) or not req["question"].strip()
            or len(req["question"]) > 4000 or "\x00" in req["question"]):
        raise ValueError("invalid question")
    if (not isinstance(req["case_id"], str) or not 0 < len(req["case_id"]) <= 128
            or type(req["seed"]) is not int or not 0 <= req["seed"] <= 2147483647):
        raise ValueError("invalid case ID or seed")
    # Prefix may be a compact teacher example pack; it must not contain heldout answers.
    # This is an operator provenance obligation, not something this script can attest.
    combined = prefix.rstrip() + "\n\nQuestion:\n" + req["question"]
    if len(combined) > 4000:
        raise ValueError("combined question exceeds downstream 4000-character limit")
    req["question"] = combined
    return json.dumps(req, ensure_ascii=False, sort_keys=True)


def run(raw_request, prefix, command, timeout):
    if (not isinstance(command, list) or not command or
            not all(isinstance(s, str) and s for s in command)):
        raise ValueError("adapter command must be JSON string array")
    if type(timeout) not in (int, float) or not 0 < timeout <= 3600:
        raise ValueError("invalid timeout")
    request = prepare_request(raw_request, prefix)
    # No shell; bounded output and time through the existing ORIL capture helper.
    stdout = capture_adapter(command, request, timeout, max_stdout=200000)
    result = parse_json(stdout)
    if not isinstance(result, dict) or set(result) != {"answer", "input_tokens", "output_tokens", "model_id"}:
        raise ValueError("downstream adapter response schema invalid")
    if (not isinstance(result["answer"], str) or len(result["answer"]) > 20000
            or not isinstance(result["model_id"], str) or not result["model_id"]
            or any(type(result[x]) is not int or result[x] < 0 for x in ("input_tokens", "output_tokens"))):
        raise ValueError("downstream adapter response invalid")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prefix-file", required=True)
    p.add_argument("--prefix-sha256", required=True)
    p.add_argument("--adapter-cmd-json", required=True)
    p.add_argument("--timeout", type=float, default=30)
    args = p.parse_args()
    prefix = read_prefix(args.prefix_file, args.prefix_sha256)
    command = parse_json(args.adapter_cmd_json)
    raw = sys.stdin.buffer.read(65537).decode("utf-8")
    print(json.dumps(run(raw, prefix, command, args.timeout),
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
