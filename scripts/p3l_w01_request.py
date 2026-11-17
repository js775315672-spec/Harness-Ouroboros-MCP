#!/usr/bin/env python3
"""Prepare a hash-bound W01 worker request, without executing a model.

Coordinator-authored bootstrap (not an Ouroboros/model-generated patch).
No GitHub writes, tests exposure, model execution, network, or credentials.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SOURCE = "scripts/development_ledger.py"
SPEC = "docs/p3l/W01-ledger-contract.ko.md"
OUTPUT = "docs/p3l/ledger-input-contract.ko.md"
MAX_SOURCE_BYTES = 20_000
MAX_SPEC_BYTES = 12_000
MAX_PROMPT_BYTES = 5_000


def digest(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def read_bound(root, path, maximum):
    file = root / path
    if file.is_symlink() or not file.is_file() or not file.resolve().is_relative_to(root):
        raise ValueError(f"unsafe W01 input: {path}")
    contents = file.read_bytes()
    if not contents or len(contents) > maximum:
        raise ValueError(f"invalid W01 input size: {path}")
    return contents


def original_validate(source):
    tree = ast.parse(source)
    matches = [node for node in tree.body if isinstance(node, ast.FunctionDef)
               and node.name == "validate"]
    if len(matches) != 1 or matches[0].decorator_list or matches[0].end_lineno is None:
        raise ValueError("exactly one undecorated validate function required")
    function = matches[0]
    if (len(function.args.args) != 1 or function.args.args[0].arg != "records"
            or function.args.defaults or function.args.kwonlyargs or function.args.vararg
            or function.args.kwarg or function.args.posonlyargs):
        raise ValueError("unexpected validate signature")
    return "".join(source.splitlines(keepends=True)[function.lineno-1:function.end_lineno])


def build_request(root, review_sha):
    root = Path(root).resolve(strict=True)
    if not isinstance(review_sha, str) or not SHA40.fullmatch(review_sha):
        raise ValueError("review commit must be an exact 40-hex SHA")
    source_bytes = read_bound(root, SOURCE, MAX_SOURCE_BYTES)
    spec_bytes = read_bound(root, SPEC, MAX_SPEC_BYTES)
    source = source_bytes.decode("utf-8", errors="strict")
    spec = spec_bytes.decode("utf-8", errors="strict")
    fn = original_validate(source)
    prompt = (
        "W01: Draft Korean Markdown for docs/p3l/ledger-input-contract.ko.md only. "
        "Do NOT modify the original function or any test. For each validation rule "
        "show one valid and one invalid case with all other fields valid. "
        "Explain current behavior versus the desired contract; unresolved policy "
        "must be labelled as requiring reviewer decision. "
        "Explicitly distinguish fixes=[] (valid) from fixes=[''] (invalid), "
        "maximum 12 fixes, UTF-8 byte limits fixes=128 and change=256, "
        "Korean byte boundaries, and NUL/LF/ESC controls. "
        "Hand off a concise summary to W02/W03. No claims of executed tests.\n\n"
        "W01 reviewed specification:\n" + spec + "\n"
        "Original (unmodified) repository function:\n" + fn
    )
    prompt_bytes = prompt.encode("utf-8")
    if len(prompt_bytes) > MAX_PROMPT_BYTES or any(c in prompt for c in ("\x00", "\x1b", "\r")):
        raise ValueError("W01 prompt exceeds fixed budget or contains controls")
    result = {
        "schema": "p3l-worker-request-v1", "worker": "W01", "issue": 38,
        "review_commit": review_sha, "source_path": SOURCE,
        "source_sha256": digest(source_bytes), "spec_path": SPEC,
        "spec_sha256": digest(spec_bytes), "allowed_output": [OUTPUT],
        "prompt": prompt, "prompt_sha256": digest(prompt_bytes),
        "prompt_bytes": len(prompt_bytes), "model_calls": 0,
        "model_id": None, "model_response_sha256": None,
        "executor_connected": False, "candidate_verified": False,
        "merge_authorized": False, "status": "PREPARED_AWAITING_EXECUTOR_AND_REVIEW",
        "generated_by": "GPT-6 bootstrap coordinator; NOT model-generated W01 output",
    }
    result["request_sha256"] = digest(canonical(result))
    return result


def verified_head(root, expected):
    p = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                       text=True, capture_output=True, check=True, timeout=10)
    if p.stdout.strip() != expected:
        raise ValueError("review SHA does not match checkout HEAD")
    p = subprocess.run(["git", "-C", str(root), "diff", "--quiet", "HEAD", "--", SOURCE, SPEC],
                       check=False, timeout=10)
    if p.returncode != 0:
        raise ValueError("reviewed input file has uncommitted changes")


def save_request(root, output, request):
    root = Path(root).resolve(strict=True)
    output = Path(output)
    if output.is_absolute() or ".." in output.parts or output.parts[:1] != ("artifacts",):
        raise ValueError("output must be within artifacts/")
    destination = root / output
    if any(x.is_symlink() for x in (destination, *list(destination.parents)[:-1])):
        raise ValueError("symlink destination forbidden")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.resolve().is_relative_to(root):
        raise ValueError("output path escapes checkout")
    contents = json.dumps(request, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if destination.exists():
        if destination.read_text(encoding="utf-8") == contents:
            return  # idempotent same-SHA replay
        raise ValueError("existing request differs; refuse to overwrite")
    with destination.open("x", encoding="utf-8") as handle:
        handle.write(contents)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--out", type=Path, default=Path("artifacts/p3l-w01/request.json"))
    opts = parser.parse_args()
    try:
        root = opts.root.resolve(strict=True)
        verified_head(root, opts.head_sha)
        request = build_request(root, opts.head_sha)
        save_request(root, opts.out, request)
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"BLOCK: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": request["status"], "worker": request["worker"],
                      "request_sha256": request["request_sha256"],
                      "model_calls": request["model_calls"],
                      "executor_connected": request["executor_connected"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
