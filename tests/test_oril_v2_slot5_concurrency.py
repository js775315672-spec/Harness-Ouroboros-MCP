"""Adversarial stress of telemetry file writes; not a formal race proof.

Stacked on #270: the target script exists only on that PR branch.
Run on POSIX Linux only; no protected production code is changed.
"""
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_phase_trace import run_timed, summarize

SHA = "a" * 40
WORKERS = 8
PER_WORKER = 25


def worker(path, worker_id, count, queue):
    try:
        for _ in range(count):
            code = run_timed("model_call", [sys.executable, "-c", "pass"],
                             path, sha=SHA, run_id=worker_id + 1)
            if code != 0:
                raise AssertionError("subprocess failed")
        queue.put(None)
    except BaseException as exc:
        queue.put(repr(exc))


@unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW")
                     and hasattr(os, "O_DIRECTORY"), "POSIX FD support required")
class ConcurrencyBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_eight_writers_200_records_exact_once_and_parseable(self):
        """8 processes x 25 writes; all records valid, no loss or torn JSONL."""
        target = self.root / "telemetry.jsonl"
        ctx = multiprocessing.get_context("spawn")
        q = ctx.Queue()
        processes = [ctx.Process(target=worker, args=(str(target), i, PER_WORKER, q))
                     for i in range(WORKERS)]
        for p in processes:
            p.start()
        for p in processes:
            p.join(timeout=45)
        try:
            for p in processes:
                self.assertFalse(p.is_alive(), "writer timeout")
                self.assertEqual(p.exitcode, 0)
            results = [q.get(timeout=5) for _ in processes]
            self.assertEqual(results, [None] * WORKERS)
            lines = target.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), WORKERS * PER_WORKER)
            rows = [json.loads(line) for line in lines]
            self.assertEqual({row["actions_run_id"] for row in rows},
                             set(range(1, WORKERS + 1)))
            for i in range(WORKERS):
                self.assertEqual(sum(row["actions_run_id"] == i + 1 for row in rows),
                                 PER_WORKER)
            self.assertTrue(all(row["returncode"] == 0 for row in rows))
            self.assertTrue(all(row["sha"] == SHA for row in rows))
            self.assertEqual(summarize(rows)["sample_counts"]["model_call"],
                             WORKERS * PER_WORKER)
        finally:
            for p in processes:
                if p.is_alive():
                    p.terminate()
                    p.join(timeout=3)

    def test_renamed_parent_never_redirects_into_replacement_symlink(self):
        """100 iterations of parent rename/symlink swap; no victim mutation.

        A failed open is allowed. A successful open must target the originally
        pinned directory inode, not the newly substituted path.
        """
        original = self.root / "active"
        original.mkdir()
        moved = self.root / "moved"
        outside = self.root / "outside"
        outside.mkdir()
        victim = outside / "trace.jsonl"
        victim.write_text("KEEP\n", encoding="utf-8")
        target = original / "trace.jsonl"
        errors = []
        stop = threading.Event()

        def attacker():
            for _ in range(100):
                if stop.is_set():
                    break
                try:
                    if original.exists() and not original.is_symlink():
                        original.rename(moved)
                        original.symlink_to(outside, target_is_directory=True)
                        original.unlink()
                        moved.rename(original)
                except OSError as exc:
                    errors.append(str(exc))
            stop.set()

        t = threading.Thread(target=attacker)
        t.start()
        try:
            for _ in range(100):
                try:
                    run_timed("model_call", [sys.executable, "-c", "pass"],
                              target, sha=SHA, run_id=1)
                except OSError:
                    pass  # valid fail-closed behavior while path is replaced
        finally:
            stop.set()
            t.join(timeout=10)
            self.assertFalse(t.is_alive(), "attacker thread hung")
            if original.is_symlink():
                original.unlink()
            if moved.exists() and not original.exists():
                moved.rename(original)
        self.assertEqual(victim.read_text(encoding="utf-8"), "KEEP\n")
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
