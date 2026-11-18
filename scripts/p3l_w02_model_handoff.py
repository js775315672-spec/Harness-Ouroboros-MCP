#!/usr/bin/env python3
"""W02: replayable, read-only request for a future coding-model worker.

Coordinator-authored infrastructure, not AI-generated code or W01 approval.
Never calls a model or changes/executes generated code.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path

from p3l_w01_contract_drift import audit, cases, gate_exit_code
from p3l_w01_candidate_validator import validate as isolated_validate
from qwen_chatml_prompt import format_chatml

ROOT = Path(__file__).resolve().parents[1]
LEGACY = Path("scripts/development_ledger.py")
CANDIDATE = Path("scripts/p3l_w01_candidate_validator.py")
SPEC = Path("docs/p3l/W01-ledger-contract.ko.md")
LOCKED_LEGACY_BLOB = "117c04ff95dacfbf7d4542a3dd9ac19563f77356"
SCHEMA = "p3l-w02-provisional-handoff-v1"


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def read_source(root, relative):
    root = Path(root).resolve(strict=True)
    path = root / relative
    if path.is_symlink() or not path.is_file() or not path.resolve(strict=True).is_relative_to(root):
        raise ValueError("unsafe handoff input")
    data = path.read_bytes()
    if not data or len(data) > 20000:
        raise ValueError("missing or oversized handoff input")
    return data


def legacy_function(source):
    tree = ast.parse(source)
    matches = [node for node in tree.body if isinstance(node, ast.FunctionDef)
               and node.name == "validate"]
    if len(matches) != 1:
        raise ValueError("missing unique original function")
    lines = source.splitlines(keepends=True)
    return "".join(lines[matches[0].lineno-1:matches[0].end_lineno])


def build(root=ROOT):
    root = Path(root)
    legacy = read_source(root, LEGACY)
    git_blob = hashlib.sha1(("blob %d\0" % len(legacy)).encode() + legacy).hexdigest()
    if git_blob != LOCKED_LEGACY_BLOB:
        raise ValueError("P3g immutable source digest changed")
    spec = read_source(root, SPEC)
    candidate = read_source(root, CANDIDATE)
    evidence = audit(isolated_validate)
    if gate_exit_code(evidence, require_zero_drift=True) != 0:
        raise ValueError("W01 proposed contract not met; no W02 handoff")
    decisions = [[name, expected] for name, _, expected in cases()]
    if len(decisions) != 19:
        raise ValueError("W01 acceptance set changed unexpectedly")

    # Only original function + the proposed written rules are visible to a model;
    # W03 diagnostics, frozen holdouts and model-failure source are not sent.
    source = legacy.decode("utf-8")
    task = (
        "Return the complete Python def validate(records): with the original checks "
        "and return behavior preserved. Do not mutate records. Change only the "
        "validation at the existing change and fixes sections in the function below.\n"
        "Original function:\n" + legacy_function(source) + "\n"
        "Public W01 implementation checklist (provisional contract):\n"
        "1. change section: keep the existing string and nonblank checks, enforce "
        "256 UTF-8 bytes with len(change.encode('utf-8'))<=256, and reject every "
        "C0/C1 character (ord 0..31 or 127..159, including NUL, LF, ESC).\n"
        "2. fixes section: keep list and item string checks. fixes=[] MUST be valid; "
        "a list containing '' MUST be rejected. Reject len(fixes)>12. "
        "The per-item UTF-8 byte length must be in the inclusive range 1 through "
        "128 (1<=len(item.encode('utf-8'))<=128); zero bytes is invalid. "
        "Apply both bounds to each item. An empty list has no items to validate. "
        "Reject the same C0/C1 characters in each item. Preserve the prior behavior "
        "for a nonempty whitespace-only fixes item and keep the records unchanged.\n"
        "3. Preserve valid Korean text and raise ValueError for invalid records. "
        "Before output, check that the change section explicitly implements both "
        "new change guards and that the fixes section rejects an empty item while "
        "accepting an empty list. Return only the complete function."
    )
    prompt = format_chatml(
        task,
        system="You repair Python code from a public contract. Return one complete "
        "replacement Python function. Do not add imports, Markdown, or explanations.",
    )
    encoded = prompt.encode("utf-8")
    if len(encoded) > 7000:
        raise ValueError("model task too large")
    return {
        "schema": SCHEMA,
        "status": "ready_for_isolated_model_attempt",
        "source_path": LEGACY.as_posix(),
        "legacy_blob_sha1": git_blob,
        "legacy_sha256": sha256(legacy),
        "w01_candidate_sha256": sha256(candidate),
        "w01_provisional_spec_sha256": sha256(spec),
        "w01_case_count": len(decisions),
        "w01_case_manifest_sha256": sha256(json.dumps(decisions, ensure_ascii=False, separators=(",", ":")).encode()),
        "w01_provisional_gate_passed": True,
        "prompt_sha256": sha256(encoded),
        "prompt_utf8_bytes": len(encoded),
        "prompt": prompt,
        "model_calls": 0,
        "model_connected": False,
        "candidate_produced": False,
        "model_output_accepted": False,
        "merge_authorized": False,
        "fixed_25_modified": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = build()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print("PASS: W02 provisional model request, W01 isolated contract 19/19, no model call")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
