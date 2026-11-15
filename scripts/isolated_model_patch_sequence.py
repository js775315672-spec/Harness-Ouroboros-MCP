#!/usr/bin/env python3
"""Two bounded, independent Docker test phases for a model-authored source patch.

The archived, AST-verified patch is actually applied to a disposable checkout
using 'git apply' (fixed argv, shell=False). No source file in the GitHub checkout
is altered. Phase 2 is deterministic extended testing, not new AI-generated code.
The Ouroboros queue is always pending; neither phase is a CI-attested task
completion, a merge authorization or an unbounded coding agent.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from model_task_queue_bridge import verify as verify_handoff
from qwen_source_guard import TARGET, ORIGINAL
from qwen_source_disposable_compare import FILES, _safe_file, _test
from qwen_semantic_disposable_compare import EXTENDED_NEGATIVE_TEST
from verified_model_patch_review import inspect_proposal

REPO = "js775315672-spec/Harness-Ouroboros-MCP"
EVIDENCE = "proposals/feedback_cycle_guard_7b.json"
MAX_PATCH_BYTES = 4096
FOLLOWUP_TEST = '''import unittest
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from feedback_controller import feedback
from task_selector import select

OK = {name: {"status":"pass", "log":""} for name in
      ("harness","ouroboros","regression","secrets")}

class ExtendedCycleGuard(unittest.TestCase):
    def test_large_positive_ints_remain_valid(self):
        for value in (1, 2, 10**12):
            with self.subTest(value=value):
                self.assertEqual(feedback(dict(select(), cycle=value), OK)["decision"], "review")

    def test_wrong_types_and_nonpositive_values_blocked(self):
        for value in (False, True, -100, 0, -1, 0.5, 2.0, "2", [], {}, (1,)):
            with self.subTest(value=repr(value)):
                with self.assertRaises(ValueError):
                    feedback(dict(select(), cycle=value), OK)

    def test_absent_cycle_or_none_blocked(self):
        for proposal in ({"decision":"propose"}, dict(select(), cycle=None)):
            with self.assertRaises(ValueError):
                feedback(proposal, OK)
'''


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _strict_patch(root, handoff_dir, commit):
    status = verify_handoff(root, Path(root) / EVIDENCE, handoff_dir, commit,
                            require_docker=True)
    if (status.get("status") != "verified_review_handoff"
            or status.get("completed_tasks") != 0
            or status.get("merge_authorized") is not False
            or status.get("code_applied") is not False
            or status.get("docker_replay_receipt") is not True):
        raise ValueError("handoff must be uncompleted and independently replayed")
    data = (Path(handoff_dir) / "candidate.patch").read_bytes()
    if not 0 < len(data) <= MAX_PATCH_BYTES or sha256(data) != status["patch_sha256"]:
        raise ValueError("untrusted patch bytes")
    record, inspected = inspect_proposal(root, Path(root) / EVIDENCE)
    if record["candidate_line_sha256"] != inspected["line_sha256"]:
        raise ValueError("model candidate changed")
    return data, record


def stage_patch(root, patch, record, destination):
    """Apply exactly one verified source guard line inside disposable workspace."""
    root = Path(root).resolve(strict=True)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("stage must be absent and unlinked")
    destination.mkdir(mode=0o700)
    source = _safe_file(root, TARGET).read_bytes()
    if sha256(source) != record["source_sha256"]:
        raise ValueError("untrusted original checkout")
    for rel in FILES:
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_safe_file(root, rel).read_bytes())
    args = ["git", "apply", "--check", "--whitespace=nowarn", "-"]
    for command in (args, ["git", "apply", "--whitespace=nowarn", "-"]):
        trial = subprocess.run(command, cwd=destination, input=patch, capture_output=True,
                               timeout=15, shell=False, check=False)
        if trial.returncode != 0:
            raise ValueError("scoped patch could not be applied in disposable workspace")
    expected = source.decode("utf-8").replace(
        ORIGINAL + "\n", record["candidate_line"] + "\n", 1).encode("utf-8")
    staged = (destination / TARGET).read_bytes()
    if staged != expected or staged == source:
        raise ValueError("git apply did not reproduce exact model source change")
    if sha256(record["candidate_line"].encode("utf-8")) != record["candidate_line_sha256"]:
        raise ValueError("model line digest mismatch")
    if _safe_file(root, TARGET).read_bytes() != source:
        raise ValueError("host checkout changed")
    (destination / "tests/test_semantic_cycle_guard.py").write_text(
        EXTENDED_NEGATIVE_TEST, encoding="utf-8")
    (destination / "tests/test_extended_cycle_guard.py").write_text(
        FOLLOWUP_TEST, encoding="utf-8")
    for directory in (destination, destination / "scripts", destination / "tests"):
        os.chmod(directory, 0o755)
    for rel in list(FILES) + ["tests/test_semantic_cycle_guard.py",
                              "tests/test_extended_cycle_guard.py"]:
        os.chmod(destination / rel, 0o644)
    return {"applied_sha256": sha256(staged), "source_sha256": sha256(source)}


def run_phase(root, handoff_dir, commit, phase, previous=None):
    if type(phase) is not int or phase not in (1, 2):
        raise ValueError("unbounded/unknown task")
    root = Path(root).resolve(strict=True)
    patch, record = _strict_patch(root, handoff_dir, commit)
    with tempfile.TemporaryDirectory(prefix="ouroboros-isolated-phase-") as tmp:
        # Docker uses an unprivileged UID; grant traverse permission only on
        # this ephemeral parent, like the existing disposable verifier does.
        # The container itself still mounts code read-only with --network none.
        os.chmod(tmp, 0o755)
        staged = Path(tmp) / "workspace"
        source_hashes = stage_patch(root, patch, record, staged)
        if phase == 2:
            if (not isinstance(previous, dict)
                    or previous.get("status") != "isolated_phase_passed"
                    or previous.get("phase") != 1
                    or previous.get("commit") != commit
                    or previous.get("patch_sha256") != sha256(patch)
                    or previous.get("applied_sha256") != source_hashes["applied_sha256"]
                    or previous.get("all_checks_passed") is not True
                    or previous.get("host_source_modified") is not False
                    or previous.get("merge_authorized") is not False):
                raise ValueError("missing verified prerequisite phase")
        patterns = (("test_feedback_controller.py", "test_semantic_cycle_guard.py")
                    if phase == 1 else ("test_extended_cycle_guard.py",))
        checks = {}
        expected_counts = {"test_feedback_controller.py": 8,
                           "test_semantic_cycle_guard.py": 3,
                           "test_extended_cycle_guard.py": 3}
        for pattern in patterns:
            result = _test(staged, pattern)
            if (not isinstance(result, dict) or
                    result.get("passed") is not True or
                    result.get("tests_run") != expected_counts[pattern] or
                    result.get("network_disabled") is not True or
                    result.get("filesystem_read_only") is not True or
                    result.get("privileges_dropped") is not True):
                raise ValueError("isolated Docker suite failed: " + pattern)
            checks[pattern] = result["tests_run"]
        if sha256(_safe_file(root, TARGET).read_bytes()) != source_hashes["source_sha256"]:
            raise ValueError("checkout changed during isolated tests")
        return {"status": "isolated_phase_passed", "phase": phase,
                "commit": commit, "task": ("apply_model_patch" if phase == 1
                                          else "boundary_regression_followup"),
                "patch_sha256": sha256(patch),
                "applied_sha256": source_hashes["applied_sha256"],
                "docker_tests": checks, "all_checks_passed": True,
                "source_applied_in_disposable_checkout": True,
                "host_source_modified": False,
                "ouroboros_queue_completed_tasks": 0,
                "model_generated_followup": False, "merge_authorized": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--phase", type=int, choices=(1, 2), required=True)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = {"status": "blocked", "merge_authorized": False}
    try:
        previous = None
        if args.phase == 2:
            if (args.previous is None or args.previous.is_symlink()
                    or not args.previous.is_file() or args.previous.stat().st_size > 5000):
                raise ValueError("missing or untrusted phase-1 receipt")
            previous = json.loads(args.previous.read_text(encoding="utf-8"))
        result = run_phase(args.root, args.handoff, args.commit, args.phase,
                           previous=previous)
    except (ValueError, TypeError, OSError, UnicodeError,
            subprocess.SubprocessError, json.JSONDecodeError) as exc:
        result["error_type"] = type(exc).__name__
        # Fixed adapter diagnostics only; never include raw model/Docker output.
        if isinstance(exc, ValueError):
            result["error_code"] = str(exc)[:160]
    if args.report.exists() or args.report.is_symlink():
        raise SystemExit("refusing to overwrite prior receipt")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "isolated_phase_passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
