"""Run W07 regression tests at the revision their assertions describe."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HISTORICAL = "f2c8c5d37c7f4fe79a658cc25a6b0ec126972578"
CANDIDATE = "3cbbf0adb1bc3e958e0a7430fbcfea3fa710e267"
HISTORICAL_MODULES = {
    "test_ledger_rule_diagnostics", "test_p3g_qwen_ledger_feedback_repair",
    "test_p3l_w02_model_handoff", "test_p3l_w02_public_prompt_clarity",
    "test_p3l_w04_one_call_gate", "test_p3l_w05_replay_evidence",
    "test_p3l_w06_actual_model_once", "test_p3l_w01_zero_drift_gate",
}


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], timeout=30).decode().strip()


def cases(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from cases(test)
        else:
            yield test


def run_side(root, historical):
    if git(root, "rev-parse", "HEAD") != (HISTORICAL if historical else CANDIDATE):
        raise ValueError("wrong W07 regression checkout")
    sys.path[:0] = [str(root), str(root / "scripts"), str(root / "tests")]
    tests = list(cases(unittest.defaultTestLoader.discover(str(root / "tests"))))
    ids = {test.id() for test in tests}
    selected = [test for test in tests
                if (test.id().split(".", 1)[0] in HISTORICAL_MODULES) == historical]
    expected = 66 if historical else 692
    if len(tests) != 758 or len(ids) != 758 or len(selected) != expected:
        raise ValueError(f"unexpected W07 test inventory: {len(tests)=}, {len(ids)=}, {len(selected)=}, {expected=}; imports={unittest.defaultTestLoader.errors}")
    result = unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(selected))
    return 0 if result.wasSuccessful() and result.testsRun == expected and not result.skipped else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--side", choices=("historical", "candidate"))
    parser.add_argument("--cycles", type=Path)
    args = parser.parse_args()
    root = Path.cwd()
    if args.side:
        return run_side(root, args.side == "historical")
    if git(root, "rev-parse", "HEAD") != CANDIDATE:
        raise ValueError("wrong W07 candidate")
    script = Path(__file__).resolve()
    with tempfile.TemporaryDirectory(prefix="w07-history-") as directory:
        checkout = Path(directory) / "baseline"
        git(root, "worktree", "add", "--detach", str(checkout), HISTORICAL)
        try:
            def paired(**options):
                outputs = [subprocess.run([sys.executable, "-B", str(script), "--side", side],
                                          cwd=path, **options)
                           for side, path in (("historical", checkout), ("candidate", root))]
                return next((result for result in outputs if result.returncode), outputs[-1])

            if args.cycles is None:
                return paired(timeout=90).returncode
            sys.path.insert(0, str(root / "scripts"))
            from verification_cycles import run
            def run_step(command, *, cwd, **options):
                if command[1:] == ["-m", "unittest", "discover", "-s", "tests", "-q"]:
                    return paired(**options)
                return subprocess.run(command, cwd=cwd, **options)
            return run(30, root=root, runner=run_step, report_path=args.cycles)
        finally:
            git(root, "worktree", "remove", str(checkout))


if __name__ == "__main__":
    raise SystemExit(main())
