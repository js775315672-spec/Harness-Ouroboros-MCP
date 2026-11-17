#!/usr/bin/env python3
"""P3g: independent second Qwen ledger patch from frozen 24/25 security failure feedback in an isolated repository copy.

Original real source: scripts/development_ledger.py, function validate. This is NOT
a toy solve(data) benchmark. Model writes a complete implementation; the
harness patches exactly one existing function into a disposable copy and
tests existing integrations + a previously failing frozen security holdout.
Never mutates git checkout, pushes, commits, merges or spawns agents.
"""
import argparse
import ast
import copy
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

from disposable_regression_compare import _docker_command
from gguf_cpu_runtime import approved_model, sha256_file, verify_paths
from gguf_output_boundary import extract_completion
from qwen_chatml_prompt import format_chatml

ROOT = Path(__file__).resolve().parents[1]
TARGET = "scripts/development_ledger.py"
SUPPORT = ("scripts/ci_attestation.py",
           "tests/test_development_ledger.py",
           "tests/test_ci_attestation.py",
           "tests/heldout_p3f_development_ledger.py")
VARIANT = "p3g-feedback-ledger-empty-fix-repair-v1"
PREVIOUS = "proposals/p3f_first_qwen_ledger_response.txt"
PREVIOUS_SHA256 = "d526bb30b6b5be5cb2baa88ed86977b8a6dcbc4d043e265595a9d3707bad6de7"
P3G_FAILURE = "proposals/p3h_verified_p3g_failure.json"
P3G_FAILURE_SHA256 = "8cb7203a0e38c8b3d7b61ed45a88a9749e046e81cb07cd7125a83c2a7e6d2264"
RETRY_VARIANT = "p3h-verified-p3g-feedback-v1"
ALTERNATE_VARIANT = "p3i-14b-frozen-feedback-v1"
SHA40 = re.compile(r"[a-f0-9]{40}\Z")
MAX_RESPONSE = 6000
MODEL = "Qwen2.5-Coder-7B-Instruct-Q4_K_M"
SOURCE_FILE_LIMIT = 20000
REGRESSION_TESTS = {"test_development_ledger.py": 8,
                    "test_ci_attestation.py": 7}
HOLDOUT_COUNT = 10
FROZEN_SUITES = {**REGRESSION_TESTS, "heldout_p3f_development_ledger.py": HOLDOUT_COUNT}
SAFE_CALLS = {"isinstance", "type", "len", "ord", "any", "all",
              "ValueError", "str", "dict", "range", "bool", "set", "enumerate"}
SAFE_METHODS = {"get", "strip", "startswith", "fullmatch", "encode", "add"}
BANNED = (ast.Import, ast.ImportFrom, ast.ClassDef, ast.AsyncFunctionDef,
          ast.With, ast.AsyncWith, ast.Global, ast.Nonlocal, ast.Delete,
          ast.Lambda, ast.Yield, ast.YieldFrom, ast.Await, ast.Try,
          ast.While, ast.NamedExpr)
BLOCKED_NAME = {"open", "exec", "eval", "compile", "__import__",
                "getattr", "setattr", "delattr", "globals", "locals", "vars"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_bytes(root, relative):
    root = Path(root).resolve(strict=True)
    path = root / relative
    if (path.is_symlink() or not path.is_file()
            or not path.resolve(strict=True).is_relative_to(root)
            or path.stat().st_size > SOURCE_FILE_LIMIT):
        raise ValueError("unsafe source/holdout file")
    return path.read_bytes()


def git_identity(root, commit):
    if not SHA40.fullmatch(commit):
        raise ValueError("invalid reviewed GitHub commit")
    run = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                         capture_output=True, text=True, timeout=10)
    if run.returncode != 0 or run.stdout.strip() != commit:
        raise ValueError("checkout HEAD differs from reviewed commit")
    dirty = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", TARGET,
                            *SUPPORT, PREVIOUS], cwd=root, timeout=10)
    if dirty.returncode != 0:
        raise ValueError("reviewed source or frozen test is dirty")


def original_function(source):
    tree = ast.parse(source)
    nodes = [x for x in tree.body if isinstance(x, ast.FunctionDef)
             and x.name == "validate"]
    if len(nodes) != 1 or not nodes[0].end_lineno:
        raise ValueError("reviewed ledger validate function anchor missing")
    return nodes[0]


def source_prompt(source, root=ROOT):
    """Second fresh inference sees frozen prior model reply and Docker failure."""
    fn=original_function(source)
    old="".join(source.splitlines(keepends=True)[fn.lineno-1:fn.end_lineno])
    if len(old.encode())>3200:
        raise ValueError("existing source exceeds bounded model prompt")
    first_bytes=file_bytes(root,PREVIOUS)
    if digest(first_bytes)!=PREVIOUS_SHA256:
        raise ValueError("prior first model response source has been altered")
    first=first_bytes.decode("utf-8")
    # Only AST inspection; the prior model code is not run on the host.
    inspect_replacement(first)
    patch_original(source,inspect_replacement(first))
    return (
        "SECOND FRESH Qwen coding-model attempt to repair a REAL existing "
        "development_ledger.py validate(records) function. "
        "First Qwen attempt produced a genuine new source diff, independently "
        "passed all 15 legacy regression cases and 9/10 new security methods, "
        "but FAILED the frozen security rule requiring every fixes-list "
        "item be a NONEMPTY string. Empty string '' wrongly passed validation. "
        "Do not change any tests, imports, module globals, other functions "
        "or existing successful validation behavior. "
        "Write ONLY one COMPLETE replacement def validate(records): "
        "plain Python source, no Markdown, comments, other helpers or prose. "
        "Preserve original checks for record schema, sequential integer cycle, "
        "unique lowercase 40-hex commit, GitHub CI URL, exact four passing "
        "checks, and list of fixes. Require change description to be a "
        "nonempty safe string of <=256 UTF-8 bytes, with no control characters "
        "ord<32 or 127..159. Require fixes list <=12 items and **every** fix "
        "to be nonempty, safe string of <=128 UTF-8 bytes, no control "
        "ord<32 or 127..159. Do not reject valid Korean descriptions. "
        "Original repository function:\n"+old+
        "\nFIRST QWEN SOURCE IMPLEMENTATION (24/25; empty-fix bug):\n"+first+
        "\nINDEPENDENT DOCKER FEEDBACK: The only failed security method "
        "was rejection of an empty string inside fixes. The first output "
        "already handled all other frozen cases. Correct that ONE omission "
        "without removing previous safeguards. Output source code only."
    )


def unfence(raw):
    if (not isinstance(raw, str) or not 20 <= len(raw.encode()) <= MAX_RESPONSE
            or any(char in raw for char in ("\r", "\x1b", "\x00"))):
        raise ValueError("invalid or dangerous model source transport")
    stripped = raw.strip()
    mark = chr(96) * 3
    if mark not in stripped:
        return stripped + "\n"
    if (not stripped.startswith(mark + "python\n")
            or not stripped.endswith("\n" + mark)
            or stripped.count(mark) != 2):
        raise ValueError("unrecognized source Markdown envelope")
    return stripped[len(mark + "python\n"):-len("\n" + mark)].strip() + "\n"


def inspect_replacement(raw):
    """Parse untrusted proposed code; never exec/compile it on the host."""
    source = unfence(raw)
    if len(source.splitlines()) > 75:
        raise ValueError("candidate function too large")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError("invalid Python source") from exc
    if len(tree.body) != 1 or type(tree.body[0]) is not ast.FunctionDef:
        raise ValueError("one replacement function required")
    fn = tree.body[0]
    args = fn.args
    if (fn.name != "validate" or fn.decorator_list or fn.returns is not None
            or fn.type_comment or getattr(fn, "type_params", ())
            or args.posonlyargs or len(args.args) != 1
            or [a.arg for a in args.args] != ["records"]
            or any(a.annotation for a in args.args)
            or args.kwonlyargs or args.vararg or args.kwarg
            or args.defaults or args.kw_defaults):
        raise ValueError("function signature changed")
    for node in ast.walk(tree):
        if isinstance(node, BANNED):
            raise ValueError("unapproved AST construct")
        if isinstance(node, ast.Name):
            if node.id in BLOCKED_NAME or "__" in node.id:
                raise ValueError("unsafe global or dunder access")
            if isinstance(node.ctx, ast.Store) and node.id == "records":
                raise ValueError("protected input rebound")
        if isinstance(node, ast.Attribute) and ("__" in node.attr
                                                or node.attr not in SAFE_METHODS):
            raise ValueError("unapproved attribute read")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id not in SAFE_CALLS:
                    raise ValueError("unapproved global call")
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr not in SAFE_METHODS:
                    raise ValueError("unapproved method call")
            else:
                raise ValueError("dynamic callable forbidden")
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(not isinstance(x, ast.Name) for x in targets):
                raise ValueError("input mutation or dynamic assignment")
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store):
            raise ValueError("input mutation forbidden")
    return source


def patch_original(original, replacement):
    """Only the existing validate function's source span may change."""
    old_tree = ast.parse(original)
    current = original_function(original)
    new_fn = ast.parse(replacement).body[0]
    assert isinstance(new_fn, ast.FunctionDef)
    old_lines = original.splitlines(keepends=True)
    proposed = "".join(old_lines[:current.lineno-1]) + replacement + "".join(
        old_lines[current.end_lineno:])
    new_tree = ast.parse(proposed)
    actual = original_function(proposed)
    before = copy.deepcopy(old_tree)
    after = copy.deepcopy(new_tree)
    for parsed in (before, after):
        for idx, node in enumerate(parsed.body):
            if isinstance(node, ast.FunctionDef) and node.name == "validate":
                parsed.body[idx] = ast.Pass()
    if ast.dump(before, include_attributes=False) != ast.dump(
            after, include_attributes=False):
        raise ValueError("source outside target function was changed")
    if ast.dump(actual, include_attributes=False) == ast.dump(
            current, include_attributes=False):
        raise ValueError("model source changed nothing")
    delta = "".join(difflib.unified_diff(
        original.splitlines(keepends=True), proposed.splitlines(keepends=True),
        fromfile="a/" + TARGET, tofile="b/" + TARGET))
    if not delta or len(delta.encode("utf-8")) > 12000:
        raise ValueError("unbounded or missing source patch")
    return proposed, delta


def check_model(gguf, metadata, model_id="7b"):
    model = approved_model(model_id)
    meta = json.loads(Path(metadata).read_text(encoding="utf-8"))
    if (meta.get("model") != model_id or meta.get("repository") != model["repo"]
            or meta.get("filename") != model["filename"]
            or meta.get("license") != "apache-2.0"
            or meta.get("quantization") != "Q4_K_M"
            or ("revision" in model and meta.get("revision") != model["revision"])
            or ("sha256" in model and meta.get("sha256") != model["sha256"])
            or sha256_file(gguf) != meta.get("sha256")):
        raise ValueError("official model GGUF provenance mismatch")


def infer(cli, gguf, prompt, model_id="7b"):
    _, binary, weights = verify_paths(model_id, cli, gguf)
    if len(prompt.encode()) > 5000:
        raise ValueError("model prompt too large")
    cmd = [str(binary), "--model", str(weights),
           "--prompt", format_chatml(prompt),
           "--n-predict", "800", "--ctx-size", "3072",
           "--threads", "4", "--temp", "0", "--seed", "42",
           "--no-display-prompt", "--simple-io", "--single-turn",
           "--jinja", "--offline", "--log-verbosity", "1", "--color", "off"]
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp",
           "LANG": "C.UTF-8", "OMP_NUM_THREADS": "4"}
    started = time.monotonic()
    result = subprocess.run(cmd, capture_output=True, text=True,
                            errors="replace", timeout=420 if model_id == "14b" else 240, env=env,
                            shell=False)
    if result.returncode != 0:
        raise ValueError("bounded model invocation failed")
    raw, _ = extract_completion(result.stdout, max_output_bytes=6000)
    return raw, round(time.monotonic() - started, 3)


def docker_suite(stage, filename):
    cmd = _docker_command(stage, "python:3.11-slim", [
        "-m", "unittest", "discover", "-s", "tests", "-p", filename, "-v"])
    if not all(flag in cmd for flag in (
            "--network=none", "--read-only", "--cap-drop=ALL",
            "--security-opt=no-new-privileges", "--user=65534:65534")):
        raise ValueError("Docker isolation flags missing")
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True,
                              timeout=100, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Docker suite timeout") from exc
    output = (proc.stdout + "\n" + proc.stderr)[-4200:]
    found = re.search(r"Ran (\d+) tests?", output)
    total = int(found.group(1)) if found else None
    return {"passed": proc.returncode == 0, "tests_run": total,
            "exit_code": proc.returncode, "log_tail": output[-1200:]}


def stage_one(folder, bytes_by_rel, replacement_source):
    folder = Path(folder)
    for rel, data in bytes_by_rel.items():
        target = folder / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        os.chmod(target, 0o644)
    patched = folder / TARGET
    patched.write_text(replacement_source, encoding="utf-8")
    os.chmod(patched, 0o644)
    os.chmod(folder, 0o755)
    for directory in ("scripts", "tests"):
        os.chmod(folder / directory, 0o755)


def grade(root, replacement_source):
    original = file_bytes(root, TARGET)
    data = {rel: file_bytes(root, rel) for rel in (TARGET, *SUPPORT)}
    if original != data[TARGET]:
        raise ValueError("source is not anchored")
    with tempfile.TemporaryDirectory(prefix="p3f-source-patch-") as temp:
        os.chmod(temp, 0o755)
        report = {}
        for label, source in (("baseline", original.decode("utf-8")),
                              ("candidate", replacement_source)):
            stage = Path(temp) / label
            stage_one(stage, data, source)
            checks = {}
            for test, expected in FROZEN_SUITES.items():
                result = docker_suite(stage, test)
                if result["tests_run"] != expected:
                    raise ValueError("frozen regression/holdout test count changed")
                checks[test] = result
            report[label] = checks
    baseline = report["baseline"]
    candidate = report["candidate"]
    if not (all(baseline[x]["passed"] for x in REGRESSION_TESTS)
            and not baseline["heldout_p3f_development_ledger.py"]["passed"]):
        raise ValueError("trusted baseline did not reproduce genuine defect")
    legacy_ok = all(candidate[x]["passed"] for x in REGRESSION_TESTS)
    passed = legacy_ok and candidate["heldout_p3f_development_ledger.py"]["passed"]
    return {"status": "real_source_patch_passed" if passed
            else "real_source_patch_failed",
            "baseline_legacy_green": True,
            "baseline_security_red": True,
            "candidate_legacy_green": legacy_ok,
            "candidate_security_green": passed,
            "baseline": baseline, "candidate": candidate,
            "checkout_modified": False, "merge_authorized": False}


def function_fingerprint(source):
    return digest(ast.dump(ast.parse(source), include_attributes=False).encode())


def retry_context(root, originals):
    evidence_bytes = file_bytes(root, P3G_FAILURE)
    if digest(evidence_bytes) != P3G_FAILURE_SHA256:
        raise ValueError("pinned P3g replay evidence changed")
    evidence = json.loads(evidence_bytes)
    inputs = {path: digest(data) for path, data in originals.items()}
    raw = evidence["raw_response"]
    if inputs != evidence["trusted_inputs_sha256"] or digest(raw.encode()) != evidence["response_sha256"]:
        raise ValueError("P3g source, test or response digests changed")
    latest = inspect_replacement(raw)
    earlier = inspect_replacement(originals[PREVIOUS].decode("utf-8"))
    original = originals[TARGET].decode("utf-8")
    candidate, _ = patch_original(original, latest)
    if digest(candidate.encode()) != evidence["source_sha256"]:
        raise ValueError("P3g patch cannot be reconstructed")
    prompt = (
        "Repair the actual development ledger validate(records) function. Return only one complete "
        "replacement Python function. Preserve all existing schema, cycle, commit, CI URL and "
        "check validation, list limits, UTF-8 byte limits and control-character restrictions. "
        "The last two proposals passed 24 of 25 frozen tests. Independent replay rejected the "
        "latest proposal. A fixes list containing an empty string was accepted because the latest "
        "proposal discarded that value before its entry validation. Every supplied entry must "
        "be validated, and an empty fixes list must still be accepted. Preserve valid Korean text. "
        "Check the distinction between no entries and one invalid empty entry before replying. "
        "The previous failed implementation follows:\n" + latest
    )
    return prompt, {
        "variant": RETRY_VARIANT,
        "prior_replay_run": evidence["run_id"],
        "prior_replay_evidence_sha256": P3G_FAILURE_SHA256,
        "rejected_function_fingerprints": [function_fingerprint(earlier), function_fingerprint(latest)],
    }


def context(root, commit, retry_p3g=False, model_id="7b"):
    if model_id != "7b" and (model_id != "14b" or not retry_p3g):
        raise ValueError("alternate ledger model requires the frozen feedback experiment")
    git_identity(root, commit)
    originals = {rel: file_bytes(root, rel) for rel in (TARGET, *SUPPORT, PREVIOUS)}
    existing = originals[TARGET].decode("utf-8")
    prompt, retry = retry_context(root, originals) if retry_p3g else (source_prompt(existing, root), {})
    if model_id == "14b":
        spec = approved_model(model_id)
        retry.update(variant=ALTERNATE_VARIANT, model="Qwen2.5-Coder-14B-Instruct-Q4_K_M",
                     model_revision=spec["revision"], model_sha256=spec["sha256"])
    return originals, prompt, {
        "schema": 1, "variant": VARIANT, "commit": commit, "target": TARGET,
        "target_before_sha256": digest(originals[TARGET]),
        "trusted_inputs_sha256": {rel: digest(data) for rel, data in originals.items()},
        "prompt_sha256": digest(prompt.encode()),
        "prior_first_model_sha256": PREVIOUS_SHA256,
        "model": MODEL, "checkout_modified": False,
        "ci_attested_model_source_commits": 0,
        "model_remote_push_authorized": False,
        "merge_authorized": False,
        **retry,
    }


def proposed_change(originals, raw, base):
    replacement = inspect_replacement(raw)
    rejected = base.get("rejected_function_fingerprints", ())
    if rejected and function_fingerprint(replacement) in rejected:
        raise ValueError("model repeated a previously rejected ledger implementation")
    proposed, patch = patch_original(originals[TARGET].decode("utf-8"), replacement)
    return replacement, proposed, patch


def run(root, commit, cli, gguf, metadata, retry_p3g=False, model_id="7b"):
    originals, prompt, base = context(root, commit, retry_p3g, model_id)
    check_model(gguf, metadata, model_id)
    raw, seconds = infer(cli, gguf, prompt, model_id)
    out = {**base, "model_calls": 1, "model_seconds": seconds,
           "raw_response": raw, "response_sha256": digest(raw.encode()),
           "replacement_sha256": None, "proposed_source_sha256": None,
           "unified_diff": None, "unified_diff_sha256": None,
           "outcome": "static_rejected", "grade": None}
    try:
        replacement, proposed, patch = proposed_change(originals, raw, base)
    except ValueError as exc:
        out["static_reject_reason"] = str(exc)[:160]
    else:
        out["replacement_sha256"] = digest(replacement.encode())
        out["proposed_source_sha256"] = digest(proposed.encode())
        out["unified_diff"] = patch
        out["unified_diff_sha256"] = digest(patch.encode())
        out["grade"] = grade(root, proposed)
        out["outcome"] = out["grade"]["status"]
    return out


def suite_results(grade_report):
    """Extract comparable verdicts without including hidden test logs."""
    results = {}
    for label in ("baseline", "candidate"):
        suites = grade_report.get(label)
        if not isinstance(suites, dict) or suites.keys() != FROZEN_SUITES.keys():
            raise ValueError("incomplete frozen suite evidence")
        results[label] = {}
        for name, expected in FROZEN_SUITES.items():
            row = suites[name]
            if (not isinstance(row, dict) or type(row.get("passed")) is not bool
                    or type(row.get("tests_run")) is not int or row["tests_run"] != expected):
                raise ValueError("invalid frozen suite evidence")
            results[label][name] = {"passed": row["passed"], "tests_run": row["tests_run"]}
    return results


def replay(root, commit, report, retry_p3g=False, model_id="7b"):
    originals, _, base = context(root, commit, retry_p3g, model_id)
    if not isinstance(report, dict):
        raise ValueError("report must be object")
    if any(type(report.get(k)) is not type(v) or report[k] != v
           for k, v in base.items()):
        raise ValueError("exact reviewed source/contract mismatch")
    if type(report.get("model_calls")) is not int or report["model_calls"] != 1:
        raise ValueError("no real model call evidence")
    raw = report.get("raw_response")
    if (not isinstance(raw, str) or
            digest(raw.encode()) != report.get("response_sha256")):
        raise ValueError("response bytes changed")
    try:
        replacement, proposed, patch = proposed_change(originals, raw, base)
    except ValueError:
        if (report.get("outcome") != "static_rejected"
                or report.get("grade") is not None
                or report.get("replacement_sha256") is not None):
            raise ValueError("static rejection falsely labeled")
        return {"status": "source_patch_static_rejection_replayed",
                "variant": base["variant"], "candidate_passed": False,
                "merge_authorized": False}
    checks = {
        "replacement_sha256": digest(replacement.encode()),
        "proposed_source_sha256": digest(proposed.encode()),
        "unified_diff": patch, "unified_diff_sha256": digest(patch.encode()),
    }
    if any(report.get(k) != v for k, v in checks.items()):
        raise ValueError("model-authored source patch not reproducible")
    outcome = grade(root, proposed)
    if (report.get("outcome") != outcome["status"]
            or not isinstance(report.get("grade"), dict)
            or report["grade"].get("status") != outcome["status"]):
        raise ValueError("independent Docker regression disagreed")
    verified_suites = suite_results(outcome)
    if suite_results(report["grade"]) != verified_suites:
        raise ValueError("independent frozen suite results disagreed")
    return {"status": "source_patch_replayed",
            "variant": base["variant"],
            "candidate_passed": outcome["status"] == "real_source_patch_passed",
            "target": TARGET, "source_sha256": checks["proposed_source_sha256"],
            "model_calls_verified": 1, "ci_attested_model_source_commits": 0,
            "suite_results": verified_suites,
            "merge_authorized": False}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=("preflight", "run", "replay"))
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--head-sha", required=True)
    p.add_argument("--cli", type=Path)
    p.add_argument("--gguf", type=Path)
    p.add_argument("--metadata", type=Path)
    p.add_argument("--retry-p3g", action="store_true")
    p.add_argument("--model", choices=("7b", "14b"), default="7b")
    p.add_argument("--input", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise SystemExit("refuse to overwrite evidence")
    try:
        if args.mode == "preflight":
            original, prompt, contract = context(args.root, args.head_sha, args.retry_p3g, args.model)
            if not all(len(v) > 0 for v in original.values()):
                raise ValueError("missing existing modules or frozen tests")
            result = {"status": "reviewed_real_repo_source_contract",
                      "source_sha256": contract["target_before_sha256"],
                      "variant": contract["variant"],
                      "test_count": 25,
                      "model_calls": 0, "merge_authorized": False}
        elif args.mode == "run":
            if args.cli is None or args.gguf is None or args.metadata is None:
                raise ValueError("real model requires approved executable inputs")
            result = run(args.root, args.head_sha,
                         args.cli, args.gguf, args.metadata, args.retry_p3g, args.model)
        else:
            if (args.input is None or args.input.is_symlink()
                    or not args.input.is_file()
                    or args.input.stat().st_size > 60000):
                raise ValueError("invalid raw evidence file")
            record = json.loads(args.input.read_text(encoding="utf-8"))
            result = replay(args.root, args.head_sha, record, args.retry_p3g, args.model)
    except (ValueError, OSError, TypeError, KeyError,
            json.JSONDecodeError, subprocess.SubprocessError) as exc:
        result = {"status": "blocked", "error_type": type(exc).__name__,
                  "error": str(exc)[:220], "merge_authorized": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False,
                                      sort_keys=True, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({k: result.get(k) for k in (
        "status", "outcome", "model_calls", "candidate_passed",
        "proposed_source_sha256", "merge_authorized")}, sort_keys=True))
    return 2 if result.get("status") == "blocked" else 0


if __name__ == "__main__":
    sys.exit(main())
