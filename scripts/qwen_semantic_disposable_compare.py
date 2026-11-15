#!/usr/bin/env python3
"""Compare bounded model-authored Python source in disposable no-network Docker.

Never mutates the working checkout. Neither a successful Docker comparison
nor a passing candidate authorizes merge, deployment, or autonomous execution.
"""
import hashlib
import os
from pathlib import Path
import tempfile

try:
    from .qwen_semantic_source_guard import inspect_semantic_line
    from .qwen_source_guard import TARGET, ORIGINAL
    from .qwen_source_disposable_compare import FILES, _safe_file, _test
except ImportError:
    from qwen_semantic_source_guard import inspect_semantic_line
    from qwen_source_guard import TARGET, ORIGINAL
    from qwen_source_disposable_compare import FILES, _safe_file, _test

EXTENDED_NEGATIVE_TEST = '''import pathlib
import sys
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from feedback_controller import feedback
from task_selector import select

CHECKS = {name: {"status": "pass", "log": ""} for name in
          ("harness", "ouroboros", "regression", "secrets")}

class CycleGuardRegression(unittest.TestCase):
    def test_reject_invalid_cycle(self):
        for invalid in (None, False, True, 0, -1, "1", 1.0, [], {}, 0.0):
            with self.subTest(invalid=repr(invalid)):
                with self.assertRaises(ValueError):
                    feedback(dict(select(), cycle=invalid), CHECKS)

    def test_reject_missing_cycle(self):
        p = dict(select())
        p.pop("cycle", None)
        with self.assertRaises(ValueError):
            feedback(p, CHECKS)

    def test_accept_positive_integer_cycle(self):
        for valid in (1, 2, 100):
            with self.subTest(valid=valid):
                result = feedback(dict(select(), cycle=valid), CHECKS)
                self.assertEqual(result["decision"], "review")
'''


def _stage(root, stage, line, source):
    for label in ("baseline", "candidate"):
        target = stage / label
        for relative in FILES:
            src = _safe_file(root, relative)
            dest = target / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
        (target / "tests/test_semantic_cycle_guard.py").write_text(
            EXTENDED_NEGATIVE_TEST, encoding="utf-8")
    candidate = stage / "candidate" / TARGET
    if candidate.read_text(encoding="utf-8") != source:
        raise ValueError("candidate source mismatch before modification")
    candidate.write_text(source.replace(ORIGINAL + "\n", line + "\n", 1),
                         encoding="utf-8")
    for label in ("baseline", "candidate"):
        target = stage / label
        for directory in (target, target / "scripts", target / "tests"):
            os.chmod(directory, 0o755)
        for relative in FILES + ("tests/test_semantic_cycle_guard.py",):
            os.chmod(target / relative, 0o644)
    os.chmod(stage, 0o755)
    if _safe_file(root, TARGET).read_text(encoding="utf-8") != source:
        raise ValueError("checkout changed during disposable stage")


def compare_line(root, line):
    if Path(root).is_symlink():
        raise ValueError("source directory symlink forbidden")
    root = Path(root).resolve(strict=True)
    source = _safe_file(root, TARGET).read_text(encoding="utf-8")
    inspection = inspect_semantic_line(line, source)
    with tempfile.TemporaryDirectory(prefix="qwen-semantic-") as tmp:
        stage = Path(tmp)
        _stage(root, stage, line, source)
        regression_base = _test(stage / "baseline", "test_feedback_controller.py")
        negative_base = _test(stage / "baseline", "test_semantic_cycle_guard.py")
        if (regression_base["passed"] is not True or
                regression_base["tests_run"] != 8):
            status = "baseline_regression_failed"
            regression_candidate = None
            negative_candidate = None
        elif (negative_base["passed"] is not False or
              negative_base["tests_run"] != 3 or
              negative_base["exit_code"] != 1):
            status = "negative_control_invalid"
            regression_candidate = None
            negative_candidate = None
        else:
            regression_candidate = _test(stage / "candidate", "test_feedback_controller.py")
            negative_candidate = _test(stage / "candidate", "test_semantic_cycle_guard.py")
            if (regression_candidate["passed"] is not True or
                    regression_candidate["tests_run"] != regression_base["tests_run"]):
                status = "candidate_regression_failed"
            elif (negative_candidate["passed"] is not True or
                  negative_candidate["tests_run"] != negative_base["tests_run"]):
                status = "candidate_negative_failed"
            else:
                status = "isolated_source_repair_passed"
        if _safe_file(root, TARGET).read_text(encoding="utf-8") != source:
            raise ValueError("checkout changed during Docker comparison")
        return {
            "status": status, "baseline_regression": regression_base,
            "baseline_negative_control": negative_base,
            "candidate_regression": regression_candidate,
            "candidate_negative_control": negative_candidate,
            "source_sha256": inspection["source_sha256"],
            "candidate_line_sha256": inspection["line_sha256"],
            "model_code_executed_in_disposable_container":
                regression_candidate is not None,
            "source_checkout_modified": False,
            "network_disabled": True, "filesystem_read_only": True,
            "merge_authorized": False,
        }
