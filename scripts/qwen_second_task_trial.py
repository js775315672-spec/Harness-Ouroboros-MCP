#!/usr/bin/env python3
"""Second independent Qwen GGUF coding task, bounded and independently tested.

Task 1: immutable archived Qwen7B cycle-guard proposal is staged in a sandbox.
Task 2: a NEW Qwen7B invocation writes a distinct log-control guard expression.
Both edits exist only in temporary isolated test copies, never in the checkout.
Never commit, merge, deploy, grant network to Docker, or mark queue complete.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import resource
import tempfile
import time

try:
    from .gguf_cpu_runtime import CPUInference, approved_model, sha256_file
    from .qwen_source_guard import ORIGINAL, TARGET
    from .qwen_source_disposable_compare import FILES, _safe_file, _test
    from .verified_model_patch_review import inspect_proposal
except ImportError:
    from gguf_cpu_runtime import CPUInference, approved_model, sha256_file
    from qwen_source_guard import ORIGINAL, TARGET
    from qwen_source_disposable_compare import FILES, _safe_file, _test
    from verified_model_patch_review import inspect_proposal

TASK_ID = "feedback_log_control_guard"
LOG_ORIGINAL = ('        if status not in ("pass","fail") or not isinstance(log,str) '
                'or len(log)>MAX_LOG_CHARS:')
CONTROLS = {chr(0), chr(27)}
MAX_ATTEMPTS = 3
BASE_TEST = "test_feedback_controller.py"
NEGATIVE_TEST = "test_model_log_control_negative.py"
NEGATIVE_SUITE = r'''import pathlib, sys, unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from feedback_controller import feedback
from task_selector import select

def checks(log):
    return {name: {"status":"pass", "log":log} for name in
            ("harness","ouroboros","regression","secrets")}

class ModelLogControlNegative(unittest.TestCase):
    def test_reject_nul(self):
        with self.assertRaises(ValueError):
            feedback(select(), checks("ok" + chr(0) + "bad"))
    def test_reject_escape(self):
        with self.assertRaises(ValueError):
            feedback(select(), checks("ok" + chr(27) + "[31m"))
    def test_allow_normal_multiline_log(self):
        self.assertEqual(feedback(select(), checks("한국어 log\nsecond line"))["decision"],
                         "review")
'''

PROMPT = (
    "A Python function validates a variable named log (which is already a string). "
    "Write ONE Python boolean expression that evaluates True if log contains either "
    "the NUL control character (Unicode U+0000) OR the ESC control character "
    "(Unicode U+001B); otherwise False. Use only the name log, the 'in' operator, "
    "'or', and escaped Python string literals. A downstream safe patcher appends "
    "your expression to an existing validation condition. "
    "Write only the expression: no statement, no Markdown, no quotes around "
    "the entire expression, no explanation."
)
FEEDBACK = {
    "ast_scope_rejected": (
        "Output was not one safe Python boolean expression. Use two string-"
        "membership comparisons joined with the logical or operator. "
        "Use Python backslash escape notation for the control characters. "
        "Do not write if, return, code fences, a function, or explanation."),
    "second_patch_test_failed": (
        "Isolated tests show your expression did not reject both NUL and ESC "
        "while accepting normal multiline logs. The expression must cover "
        "both distinct characters and must not reject ordinary newlines."),
}


def hash_data(value):
    return hashlib.sha256(value).hexdigest()


def normalize_expression(response):
    if not isinstance(response, str) or not 1 <= len(response.encode("utf-8")) <= 400:
        raise ValueError("invalid bounded model expression")
    text = response.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) != 3 or lines[0] not in ("```python", "```") or lines[-1] != "```":
            raise ValueError("invalid fenced expression")
        text = lines[1].strip()
    if text.startswith("`") or text.endswith("`"):
        if (len(text) < 3 or not text.startswith("`") or not text.endswith("`")
                or text.count("`") != 2):
            raise ValueError("ambiguous inline formatting")
        text = text[1:-1].strip()
    if (not text or len(text) > 220 or "\n" in text or "\r" in text
            or "\x00" in text or "\x1b" in text or "`" in text):
        raise ValueError("unsafe model formatting/control bytes")
    try:
        node = ast.parse(text, mode="eval").body
    except SyntaxError as exc:
        raise ValueError("invalid Python expression") from exc
    if (not isinstance(node, ast.BoolOp) or not isinstance(node.op, ast.Or)
            or len(node.values) != 2):
        raise ValueError("two independent OR membership checks required")
    found = set()
    for part in node.values:
        if (not isinstance(part, ast.Compare) or
                not isinstance(part.left, ast.Constant)
                or type(part.left.value) is not str
                or len(part.ops) != 1 or not isinstance(part.ops[0], ast.In)
                or len(part.comparators) != 1 or
                not isinstance(part.comparators[0], ast.Name)
                or part.comparators[0].id != "log"):
            raise ValueError("expression outside scoped AST allowlist")
        found.add(part.left.value)
    if found != CONTROLS:
        raise ValueError("both independently specified log controls required")
    return text


def make_candidate(source, first_line, expression):
    if not isinstance(source, str) or source.count(ORIGINAL + "\n") != 1:
        raise ValueError("missing cycle-guard original source anchor")
    if source.count(LOG_ORIGINAL + "\n") != 1:
        raise ValueError("missing independent log-guard source anchor")
    if not first_line.startswith("    if ") or not first_line.endswith(":"):
        raise ValueError("invalid archived first line")
    expr = normalize_expression(expression)
    first = source.replace(ORIGINAL + "\n", first_line + "\n", 1)
    second_line = LOG_ORIGINAL[:-1] + " or (" + expr + "):"
    candidate = first.replace(LOG_ORIGINAL + "\n", second_line + "\n", 1)
    if candidate == first or first == source:
        raise ValueError("code was not independently changed")
    before_ast = ast.parse(first)
    after_ast = ast.parse(candidate)
    number = next(i for i,l in enumerate(source.splitlines(), 1) if l == LOG_ORIGINAL)
    def without_target(tree):
        match = [n for n in ast.walk(tree) if isinstance(n, ast.If)
                 and getattr(n, "lineno", None) == number]
        if len(match) != 1:
            raise ValueError("target guard is not unique")
        match[0].test = ast.Constant(value=True)
        return ast.dump(tree, include_attributes=False)
    if without_target(before_ast) != without_target(after_ast):
        raise ValueError("source mutation outside scoped log guard")
    return first, candidate, second_line


def stage(root, first, candidate, destination):
    root = Path(root).resolve(strict=True)
    destination = Path(destination)
    destination.mkdir()
    source_original = _safe_file(root, TARGET).read_bytes()
    for label, content in (("first_patch_only", first), ("first_plus_second", candidate)):
        base = destination / label
        for relative in FILES:
            origin = _safe_file(root, relative)
            output = base / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(origin.read_bytes())
        (base / TARGET).write_text(content, encoding="utf-8")
        (base / "tests" / NEGATIVE_TEST).write_text(NEGATIVE_SUITE, encoding="utf-8")
        for folder in (base, base / "scripts", base / "tests"):
            os.chmod(folder, 0o755)
        for relative in FILES + ("tests/" + NEGATIVE_TEST,):
            os.chmod(base / relative, 0o644)
    if _safe_file(root, TARGET).read_bytes() != source_original:
        raise ValueError("source checkout modified during staging")


def evaluate(root, first_line, expression, expected_original_sha):
    root = Path(root).resolve(strict=True)
    source_path = _safe_file(root, TARGET)
    original = source_path.read_bytes()
    if hash_data(original) != expected_original_sha:
        raise ValueError("trusted original source mismatch")
    source = original.decode("utf-8")
    first, candidate, line = make_candidate(source, first_line, expression)
    with tempfile.TemporaryDirectory(prefix="qwen-second-task-") as tmp:
        os.chmod(tmp, 0o755)
        folder = Path(tmp) / "sandbox"
        stage(root, first, candidate, folder)
        baseline1 = _test(folder / "first_patch_only", BASE_TEST)
        baseline2 = _test(folder / "first_patch_only", NEGATIVE_TEST)
        if (baseline1.get("passed") is not True or baseline1.get("tests_run") != 8
                or baseline2.get("passed") is not False or
                baseline2.get("tests_run") != 3 or baseline2.get("exit_code") != 1):
            outcome, after1, after2 = "baseline_or_negative_control_invalid", None, None
        else:
            after1 = _test(folder / "first_plus_second", BASE_TEST)
            after2 = _test(folder / "first_plus_second", NEGATIVE_TEST)
            outcome = "second_patch_passed" if (
                after1.get("passed") is True and after1.get("tests_run") == 8
                and after2.get("passed") is True and after2.get("tests_run") == 3
                and all(x.get("network_disabled") is True
                        and x.get("filesystem_read_only") is True
                        and x.get("privileges_dropped") is True
                        for x in (baseline1, baseline2, after1, after2))) else "second_patch_test_failed"
    if source_path.read_bytes() != original:
        raise ValueError("checkout modified during Docker review")
    return {"outcome": outcome,
            "first_patch_sha256": hash_data(first.encode("utf-8")),
            "second_patch_sha256": hash_data(candidate.encode("utf-8")),
            "second_line_sha256": hash_data(line.encode("utf-8")),
            "docker_comparisons": 1,
            "baseline_regression": baseline1,
            "baseline_negative_control": baseline2,
            "candidate_regression": after1,
            "candidate_negative_control": after2,
            "source_checkout_modified": False, "merge_authorized": False}


def trial(root, inference):
    root = Path(root).resolve(strict=True)
    record, _ = inspect_proposal(root, root / "proposals/feedback_cycle_guard_7b.json")
    source = _safe_file(root, TARGET).read_bytes()
    if hash_data(source) != record["source_sha256"]:
        raise ValueError("first task baseline changed")
    attempts, seen, seen_responses = [], set(), set()
    final = None
    result = "ast_scope_rejected"
    for i in range(1, MAX_ATTEMPTS + 1):
        prompt = PROMPT if i == 1 else PROMPT + " " + FEEDBACK.get(result, FEEDBACK["ast_scope_rejected"])
        raw = inference.generate(prompt)
        response_digest = hash_data(raw.encode())
        row = {"attempt": i, "prompt_sha256": hash_data(prompt.encode()),
               "response_sha256": response_digest,
               "response_preview": raw[:160]}
        if response_digest in seen_responses:
            row["status"] = "duplicate_response_blocked"
            attempts.append(row)
            result = row["status"]
            break
        seen_responses.add(response_digest)
        try:
            expression = normalize_expression(raw)
            first, candidate, line = make_candidate(source.decode("utf-8"),
                                                    record["candidate_line"], expression)
            digest = hash_data(line.encode())
            row["candidate_line_sha256"] = digest
            if digest in seen:
                row["status"] = "duplicate_candidate_blocked"
                attempts.append(row)
                result = row["status"]
                break
            seen.add(digest)
        except (ValueError, SyntaxError) as exc:
            row["status"] = "ast_scope_rejected"
            row["reason_type"] = type(exc).__name__
            attempts.append(row)
            result = row["status"]
            continue
        compared = evaluate(root, record["candidate_line"], expression,
                            record["source_sha256"])
        final = compared
        row["status"] = compared["outcome"]
        attempts.append(row)
        result = row["status"]
        if result == "second_patch_passed":
            return {"outcome": "second_patch_passed", "candidate_line": line,
                    "candidate_line_sha256": digest, "attempts": attempts,
                    "model_calls": len(attempts),
                    "docker_comparisons": sum(1 for a in attempts if a["status"]
                                              in ("second_patch_passed", "second_patch_test_failed",
                                                  "baseline_or_negative_control_invalid")),
                    "last_comparison": final,
                    "first_task": record["task_id"], "second_task": TASK_ID,
                    "source_checkout_modified": False,
                    "model_generated_second_task": True, "merge_authorized": False}
        if result == "baseline_or_negative_control_invalid":
            break
    return {"outcome": result, "candidate_line": None,
            "attempts": attempts, "model_calls": len(attempts),
            "docker_comparisons": sum(1 for a in attempts if a["status"]
                                      in ("second_patch_passed", "second_patch_test_failed",
                                          "baseline_or_negative_control_invalid")),
            "last_comparison": final, "first_task": record["task_id"],
            "second_task": TASK_ID, "source_checkout_modified": False,
            "model_generated_second_task": False, "merge_authorized": False}


def benchmark(model, cli, gguf, metadata, root=Path("."), timeout=150):
    spec = approved_model(model)
    meta = json.loads(Path(metadata).read_text(encoding="utf-8"))
    if (not isinstance(meta, dict) or meta.get("model") != model
            or meta.get("repository") != spec["repo"]
            or meta.get("filename") != spec["filename"]
            or meta.get("license") != "apache-2.0"
            or meta.get("quantization") != "Q4_K_M"
            or sha256_file(gguf) != meta.get("sha256")):
        raise ValueError("untrusted official model provenance")
    inference = CPUInference(model, cli, gguf, timeout_seconds=timeout)
    begin = time.perf_counter()
    state = trial(root, inference)
    state.update({
        "schema_version": 1, "model": model, "engine": "llama.cpp",
        "model_repo": spec["repo"], "gguf_sha256": meta["sha256"],
        "total_elapsed_seconds": round(time.perf_counter() - begin, 3),
        "peak_child_rss_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        "inference_calls": inference.calls, "paid_api_used": False,
        "secret_required": False, "source_checkout_modified": False,
        "merge_authorized": False, "human_merge_approval_required": True,
        "statistical_success_established": False,
    })
    return state


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", choices=["7b"], required=True)
    p.add_argument("--cli", type=Path, required=True)
    p.add_argument("--gguf", type=Path, required=True)
    p.add_argument("--download-metadata", type=Path, required=True)
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--timeout", type=int, default=150)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    report = {"outcome": "blocked", "model": args.model, "merge_authorized": False,
              "source_checkout_modified": False}
    try:
        report = benchmark(args.model, args.cli, args.gguf, args.download_metadata,
                           args.root, args.timeout)
    except (ValueError, OSError, TypeError, KeyError, SyntaxError,
            json.JSONDecodeError) as exc:
        report["error_type"] = type(exc).__name__
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({k:report.get(k) for k in
        ("outcome","model_calls","docker_comparisons","merge_authorized")},
        sort_keys=True))
    return 2 if report["outcome"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
