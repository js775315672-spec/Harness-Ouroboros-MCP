#!/usr/bin/env python3
"""Compare a model-proposed executable source guard only in locked-down Docker.

Never applies a patch to the checkout. Replays saved real-model evidence and
requires baseline tests to pass, baseline negative control to fail, and the
candidate to pass both suites. All generated source executes only in Docker.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

try:
    from .qwen_source_guard import TARGET, TASK, inspect_line
    from .qwen_source_trial import MODEL, normalize_model_line
    from .qwen_source_microtask import KINDS, MODE, MAX_ATTEMPTS_PER_KIND, build_candidate
    from .disposable_regression_compare import _docker_command, _unique_json_pairs
except ImportError:
    from qwen_source_guard import TARGET, TASK, inspect_line
    from qwen_source_trial import MODEL, normalize_model_line
    from qwen_source_microtask import KINDS, MODE, MAX_ATTEMPTS_PER_KIND, build_candidate
    from disposable_regression_compare import _docker_command, _unique_json_pairs

FILES = (TARGET, "scripts/task_selector.py", "scripts/evolution_planner.py",
         "tests/test_feedback_controller.py")
TRUSTED_NEGATIVE_TEST = '''import pathlib
import sys
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from feedback_controller import feedback
from task_selector import select

class SourceCycleNegativeControl(unittest.TestCase):
    def test_reject_invalid_cycle_values(self):
        checks = {name: {"status": "pass", "log": ""} for name in
                  ("harness", "ouroboros", "regression", "secrets")}
        for invalid in (None, 0, -1, False, "1"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    feedback(dict(select(), cycle=invalid), checks)
'''

def _hash(data):
    return hashlib.sha256(data).hexdigest()

def _json(path):
    data = Path(path).read_bytes()
    if not data or len(data) > 120000:
        raise ValueError("evidence size invalid")
    obj = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_json_pairs)
    if not isinstance(obj, dict):
        raise ValueError("evidence must be an object")
    return obj, _hash(data)

def _safe_file(root, rel):
    path = root / rel
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError("unsafe file: " + rel)
    if path.stat().st_size > 20000:
        raise ValueError("file exceeds trusted source budget")
    return path

def verify_and_stage(root, inference_path, candidate_path, workspace):
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("checkout required")
    inference, _ = _json(inference_path)
    candidate, candidate_sha = _json(candidate_path)
    micro_mode = candidate.get("generation_mode") == MODE
    limit = len(KINDS) * MAX_ATTEMPTS_PER_KIND if micro_mode else 2
    if (inference.get("status") != "accepted_for_disposable_review" or
            inference.get("model") != MODEL or inference.get("task_id") != TASK["task_id"] or
            type(inference.get("model_calls")) is not int or not 1 <= inference["model_calls"] <= limit or
            inference.get("source_checkout_modified") is not False or
            inference.get("model_code_executed") is not False or
            inference.get("merge_authorized") is not False):
        raise ValueError("untrusted model provenance")
    if candidate_sha != inference.get("candidate_sha256"):
        raise ValueError("model candidate hash mismatch")
    common_fields = {"provider", "status", "task_id", "line", "source_patch",
                     "source_sha256", "model_line_sha256"}
    legacy_fields = common_fields | {"raw_response"}
    micro_fields = common_fields | {"generation_mode", "microtask_responses"}
    if set(candidate) != (micro_fields if micro_mode else legacy_fields):
        raise ValueError("unexpected candidate fields")
    if (candidate["provider"] != "qwen" or candidate["status"] != "proposal" or
            candidate["task_id"] != TASK["task_id"]):
        raise ValueError("unexpected model task")
    original = _safe_file(root, TARGET).read_text(encoding="utf-8")
    attempts = inference.get("attempts")
    if not isinstance(attempts, list) or len(attempts) != inference["model_calls"]:
        raise ValueError("model attempt trace is incomplete")
    if micro_mode:
        responses = candidate["microtask_responses"]
        if (not isinstance(responses, list) or len(responses) != len(KINDS) or
                any(not isinstance(item, dict) or
                    set(item) != {"kind", "raw_response"} or
                    item["kind"] != kind or
                    not isinstance(item["raw_response"], str)
                    for item, kind in zip(responses, KINDS))):
            raise ValueError("unexpected model microtask response contract")
        rebuilt = build_candidate({item["kind"]: item["raw_response"]
                                   for item in responses}, original)
        if candidate != rebuilt:
            raise ValueError("model fragments do not reconstruct the source patch")
        stage, count = 0, 0
        for row in attempts:
            if not isinstance(row, dict) or stage >= len(KINDS):
                raise ValueError("unexpected microtask attempt")
            kind = KINDS[stage]
            count += 1
            if (row.get("kind") != kind or
                    type(row.get("attempt")) is not int or row["attempt"] != count or
                    count > MAX_ATTEMPTS_PER_KIND or
                    row.get("status") not in ("rejected", "accepted")):
                raise ValueError("microtask attempt sequence is invalid")
            if row["status"] == "accepted":
                raw = responses[stage]["raw_response"]
                if (row.get("response_sha256") != _hash(raw.encode("utf-8")) or
                        row.get("response_length") != len(raw)):
                    raise ValueError("accepted model fragment provenance mismatch")
                stage += 1
                count = 0
            elif row.get("reason_type") != "expression_ast_rejected":
                raise ValueError("missing bounded rejection category")
        if stage != len(KINDS) or attempts[-1].get("status") != "accepted":
            raise ValueError("model fragments not completed")
    else:
        if (not isinstance(candidate["raw_response"], str) or
                not isinstance(candidate["line"], str) or
                normalize_model_line(candidate["raw_response"]) != candidate["line"]):
            raise ValueError("model response cannot be replayed to the guarded line")
        if (not attempts or attempts[-1].get("status") != "accepted" or
                attempts[-1].get("response_sha256") !=
                _hash(candidate["raw_response"].encode("utf-8"))):
            raise ValueError("model response does not match accepted attempt")
    inspection = inspect_line(candidate["line"], original)
    if (inspection["patch"] != candidate["source_patch"] or
            inspection["source_sha256"] != candidate["source_sha256"] or
            inspection["source_sha256"] != inference.get("source_sha256") or
            inspection["model_line_sha256"] != candidate["model_line_sha256"]):
        raise ValueError("source or model response provenance mismatch")
    workspace = Path(workspace)
    for label in ("baseline", "candidate"):
        base = workspace / label
        for rel in FILES:
            dest = base / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(_safe_file(root, rel).read_bytes())
        (base / "tests/test_source_cycle_guard.py").write_text(
            TRUSTED_NEGATIVE_TEST, encoding="utf-8")
    candidate_root = workspace / "candidate"
    for flag in ("--check", ""):
        args = ["git", "apply"] + ([flag] if flag else []) + ["--unidiff-zero", "-"]
        check = subprocess.run(args, input=inspection["patch"], text=True,
                               cwd=candidate_root, capture_output=True, timeout=10)
        if check.returncode:
            raise ValueError("disposable git apply failed")
    # Match the exact verified source text so git fuzz cannot redirect the edit.
    original_lines = original.splitlines(keepends=True)
    original_lines[inspection["line_number"] - 1] = candidate["line"].removesuffix("\n") + "\n"
    if (candidate_root / TARGET).read_text(encoding="utf-8") != "".join(original_lines):
        raise ValueError("disposable patch differs from AST-verified replacement")
    if _safe_file(root, TARGET).read_text(encoding="utf-8") != original:
        raise ValueError("working checkout modified")
    for label in ("baseline", "candidate"):
        base = workspace / label
        for directory in (base, base / "scripts", base / "tests"):
            os.chmod(directory, 0o755)
        for rel in FILES + ("tests/test_source_cycle_guard.py",):
            os.chmod(base / rel, 0o644)
    return {"source_sha256": inspection["source_sha256"],
            "model_line_sha256": inspection["model_line_sha256"],
            "model_calls": inference["model_calls"],
            "source_checkout_modified": False,
            "disposable_patch_only": True}

def _test(workspace, pattern):
    command = _docker_command(workspace, "python:3.11-slim",
                              ["-m", "unittest", "discover", "-s", "tests",
                               "-p", pattern, "-v"])
    result = subprocess.run(command, capture_output=True, text=True, timeout=100)
    output = (result.stdout + "\n" + result.stderr)[-3500:]
    found = re.search(r"Ran (\d+) tests?", output)
    return {"tests_run": int(found.group(1)) if found else None,
            "passed": result.returncode == 0 and found is not None,
            "exit_code": result.returncode,
            "network_disabled": True, "filesystem_read_only": True,
            "privileges_dropped": True}

def compare(root, inference_path, candidate_path):
    with tempfile.TemporaryDirectory(prefix="qwen-source-trial-") as temp:
        provenance = verify_and_stage(root, inference_path, candidate_path, temp)
        original_regression = _test(Path(temp) / "baseline", "test_feedback_controller.py")
        candidate_regression = _test(Path(temp) / "candidate", "test_feedback_controller.py")
        original_negative = _test(Path(temp) / "baseline", "test_source_cycle_guard.py")
        candidate_negative = _test(Path(temp) / "candidate", "test_source_cycle_guard.py")
        passed = (original_regression["passed"] is True and
                  candidate_regression["passed"] is True and
                  original_regression["tests_run"] == candidate_regression["tests_run"] and
                  original_negative["passed"] is False and
                  original_negative["tests_run"] == 1 and
                  candidate_negative["passed"] is True and
                  candidate_negative["tests_run"] == 1)
        return {"status": "isolated_source_repair_passed" if passed else "regression_failed",
                "provenance": provenance, "baseline_regression": original_regression,
                "candidate_regression": candidate_regression,
                "baseline_negative_control": original_negative,
                "candidate_negative_control": candidate_negative,
                "model_generated_code_executed_in_disposable_container": True,
                "source_checkout_modified": False, "merge_authorized": False}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("."))
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = {"status": "blocked", "source_checkout_modified": False, "merge_authorized": False}
    try:
        if args.source.is_symlink():
            raise ValueError("unsafe source link")
        report = compare(args.source, args.inference, args.candidate)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, subprocess.SubprocessError) as exc:
        report["error_type"] = type(exc).__name__
        report["reason"] = str(exc)[:180]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "isolated_source_repair_passed" else 2

if __name__ == "__main__":
    sys.exit(main())
