#!/usr/bin/env python3
"""Advisory, AST-only diagnostics for a W06 model output.

Never executes model-authored code; not a candidate acceptance or a replacement
for frozen 25 tests and independently attested no-network Docker replay.
"""
import argparse
import ast
import hashlib
import json
import re
from pathlib import Path

SCHEMA = "p3l-w06-public-contract-lint-v1"
RULES = ("fixes_nonempty_elements", "fixes_max_12", "fixes_utf8_128", "change_utf8_256")


def extract_function(raw):
    if type(raw) is not str or not raw.strip() or len(raw.encode("utf-8")) > 6000:
        raise ValueError("missing or oversized model source")
    stripped = raw.strip()
    fenced = re.fullmatch(r"```(?:python)?\s*\n(.*?)\n```", stripped, flags=re.S | re.I)
    if fenced:
        stripped = fenced.group(1)
    tree = ast.parse(stripped)
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef) or tree.body[0].name != "validate":
        raise ValueError("expected one validate function only")
    if tree.body[0].decorator_list:
        raise ValueError("decorated function not allowed")
    if any(isinstance(n, (ast.Import, ast.ImportFrom)) or
           isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in {"eval", "exec", "compile", "__import__"}
           for n in ast.walk(tree)):
        raise ValueError("model source contains forbidden import or execution construct")
    return tree


def _len_input(expr):
    if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name) and expr.func.id == "len" and len(expr.args) == 1:
        return expr.args[0]
    return None


def _is_utf8_bytes(expr):
    return (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute) and
            expr.func.attr == "encode" and len(expr.args) == 1 and
            isinstance(expr.args[0], ast.Constant) and
            isinstance(expr.args[0].value, str) and
            expr.args[0].value.lower().replace("-", "") == "utf8")


def _has_numeric_guard(tree, limit, byte_length=False, fixes_count=False):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        terms = [node.left, *node.comparators]
        if not any(isinstance(v, ast.Constant) and type(v.value) is int and v.value == limit for v in terms):
            continue
        for t in terms:
            inner = _len_input(t)
            if inner is None:
                continue
            if byte_length and _is_utf8_bytes(inner):
                return True
            if fixes_count:
                # Advisory only: a limit on record["fixes"] or fixes variable.
                name = ast.unparse(inner)
                if "fixes" in name:
                    return True
    return False


def _has_empty_item_guard(tree):
    # A syntactic hint only. `not x` is not necessarily tied to fixes.
    for n in ast.walk(tree):
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not) and isinstance(n.operand, ast.Name):
            if n.operand.id not in {"records", "record", "fixes"}:
                return True
        if isinstance(n, ast.Compare) and any(isinstance(c, ast.Constant) and c.value == "" for c in [n.left, *n.comparators]):
            return True
    return False


def diagnose(report):
    if type(report) is not dict or report.get("schema") != "p3l-w06-one-shot-output-v1":
        raise ValueError("unsupported model output receipt")
    raw = report.get("raw_response")
    if type(raw) is not str or type(report.get("raw_response_sha256")) is not str:
        raise ValueError("missing original response proof")
    observed = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    if observed != report["raw_response_sha256"]:
        raise ValueError("raw model response SHA mismatch")
    tree = extract_function(raw)
    detected = {
        "fixes_nonempty_elements": _has_empty_item_guard(tree),
        "fixes_max_12": _has_numeric_guard(tree, 12, fixes_count=True),
        "fixes_utf8_128": _has_numeric_guard(tree, 128, byte_length=True),
        "change_utf8_256": _has_numeric_guard(tree, 256, byte_length=True),
    }
    return {
        "schema": SCHEMA,
        "run_id": report.get("run_id"),
        "raw_response_sha256": observed,
        "candidate_source_sha256": report.get("candidate_source_sha256"),
        "advisory_syntax_markers": detected,
        "not_detected": [name for name in RULES if not detected[name]],
        "model_calls": 0,
        "model_code_executed": False,
        "independent_replay_completed": False,
        "candidate_passed": False,
        "promotion_eligible": False,
        "note": "Heuristic presence-only inspection; missing markers are hints, presence is NOT proof. Frozen 25 and independent replay mandatory.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = diagnose(json.loads(args.input.read_text(encoding="utf-8")))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("W06 syntax-only diagnostic; candidate NOT accepted; absent markers:", ", ".join(report["not_detected"]) or "none")


if __name__ == "__main__":
    main()
