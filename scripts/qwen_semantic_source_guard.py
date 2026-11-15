#!/usr/bin/env python3
"""AST-only gate for a model-authored, non-templated feedback guard repair.

The model may propose different expressions. No known-good solution line is
given to the generator or compared here. Only one original guard is replaceable.
Untrusted code is never run in this module.
"""
import ast
import hashlib

try:
    from .qwen_source_guard import ORIGINAL, TARGET
except ImportError:
    from qwen_source_guard import ORIGINAL, TARGET

MAX_LINE = 350
ALLOWED_NAMES = {"proposal", "int", "bool", "isinstance", "type"}
ALLOWED_CONSTANTS = {"cycle", None, False, True, -1, 0, 1, 2}
ALLOWED_NODES = (ast.BoolOp, ast.UnaryOp, ast.Compare, ast.Call,
                 ast.Name, ast.Attribute, ast.Subscript, ast.Constant,
                 ast.List, ast.Tuple, ast.Load, ast.Or, ast.And, ast.Not,
                 ast.USub, ast.Eq, ast.NotEq, ast.Is, ast.IsNot,
                 ast.In, ast.NotIn, ast.Lt, ast.LtE, ast.Gt, ast.GtE)


def _guard_test(line):
    tree = ast.parse("def _example():\n" + line + "\n        pass\n")
    fn = tree.body[0]
    if len(fn.body) != 1 or not isinstance(fn.body[0], ast.If):
        raise ValueError("expected a single if statement")
    return fn.body[0].test


def _entry_guard(tree):
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef)
             and n.name == "feedback"]
    if len(funcs) != 1 or not funcs[0].body or not isinstance(funcs[0].body[0], ast.If):
        raise ValueError("feedback entry guard missing")
    return funcs[0].body[0]


def _safe_extension(node):
    for part in ast.walk(node):
        if not isinstance(part, ALLOWED_NODES):
            raise ValueError("unsafe AST node in generated expression")
        if isinstance(part, ast.UnaryOp) and isinstance(part.op, ast.USub):
            if not (isinstance(part.operand, ast.Constant) and
                    type(part.operand.value) is int and
                    part.operand.value in (1, 2)):
                raise ValueError("only small negative integer literals allowed")
        if isinstance(part, (ast.List, ast.Tuple)):
            if len(part.elts) > 8:
                raise ValueError("oversized literal collection")
            for item in part.elts:
                if isinstance(item, ast.Constant):
                    if type(item.value) not in (int, bool, str, type(None)):
                        raise ValueError("nonliteral collection item")
                elif not (isinstance(item, ast.UnaryOp) and
                          isinstance(item.op, ast.USub) and
                          isinstance(item.operand, ast.Constant) and
                          type(item.operand.value) is int and
                          item.operand.value in (1, 2)):
                    raise ValueError("only simple literal collection items permitted")
        if isinstance(part, ast.Name) and part.id not in ALLOWED_NAMES:
            raise ValueError("unsafe name in generated expression")
        if isinstance(part, ast.Constant):
            if type(part.value) not in (str, type(None), bool, int):
                raise ValueError("unsafe constant type")
            if part.value not in ALLOWED_CONSTANTS:
                raise ValueError("unsafe constant value")
        if isinstance(part, ast.Attribute):
            if not (part.attr == "get" and isinstance(part.value, ast.Name)
                    and part.value.id == "proposal"):
                raise ValueError("unsafe attribute access")
        if isinstance(part, ast.Subscript):
            if not (isinstance(part.value, ast.Name) and
                    part.value.id == "proposal" and
                    isinstance(part.slice, ast.Constant) and
                    part.slice.value == "cycle"):
                raise ValueError("unsafe subscript")
        if isinstance(part, ast.Call):
            fn = part.func
            if part.keywords:
                raise ValueError("keyword calls disallowed")
            if isinstance(fn, ast.Name):
                if not ((fn.id == "type" and len(part.args) == 1) or
                        (fn.id == "isinstance" and len(part.args) == 2)):
                    raise ValueError("only type/isinstance calls allowed")
            elif isinstance(fn, ast.Attribute):
                if not (fn.attr == "get" and
                        isinstance(fn.value, ast.Name) and
                        fn.value.id == "proposal" and len(part.args) == 1 and
                        isinstance(part.args[0], ast.Constant) and
                        part.args[0].value == "cycle"):
                    raise ValueError("only proposal.get(cycle) allowed")
            else:
                raise ValueError("unsafe call target")


def inspect_semantic_line(line, source):
    if not isinstance(line, str) or not isinstance(source, str):
        raise ValueError("source and model line must be text")
    if (not line.startswith("    if ") or not line.endswith(":") or
            not 0 < len(line) <= MAX_LINE or "\n" in line or
            "\r" in line or "\x00" in line):
        raise ValueError("exactly one bounded conditional line required")
    if (not source.endswith("\n") or len(source.encode("utf-8")) > 12000 or
            source.splitlines().count(ORIGINAL) != 1):
        raise ValueError("source baseline is missing or ambiguous")
    try:
        original = _guard_test(ORIGINAL)
        proposed = _guard_test(line)
        if not (isinstance(original, ast.BoolOp) and
                isinstance(original.op, ast.Or) and
                len(original.values) == 2 and
                isinstance(proposed, ast.BoolOp) and
                isinstance(proposed.op, ast.Or) and
                len(proposed.values) > 2 and len(proposed.values) <= 7):
            raise ValueError("original guard must be extended by OR conditions")
        for index in range(2):
            if (ast.dump(original.values[index], include_attributes=False) !=
                    ast.dump(proposed.values[index], include_attributes=False)):
                raise ValueError("original reject conditions must be preserved")
        for extra in proposed.values[2:]:
            _safe_extension(extra)
        original_tree = ast.parse(source)
        original_guard = _entry_guard(original_tree)
        if (ast.dump(original_guard.test, include_attributes=False) !=
                ast.dump(original, include_attributes=False)):
            raise ValueError("trusted source guard changed")
        replacement = source.replace(ORIGINAL + "\n", line + "\n", 1)
        patched_tree = ast.parse(replacement)
        original_guard.test = ast.Constant(value=True)
        _entry_guard(patched_tree).test = ast.Constant(value=True)
        if (ast.dump(original_tree, include_attributes=False) !=
                ast.dump(patched_tree, include_attributes=False)):
            raise ValueError("other executable code changed")
    except SyntaxError as exc:
        raise ValueError("invalid Python syntax") from exc
    return {"status": "ast_scoped_candidate", "target": TARGET,
            "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "line_sha256": hashlib.sha256(line.encode("utf-8")).hexdigest(),
            "source_modified": False, "merge_authorized": False}
