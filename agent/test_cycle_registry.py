import concurrent.futures
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cycle_registry import Blocked, git, transact


class RegistryTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.remote = str(pathlib.Path(temp.name) / "origin.git")
        git("init", "--quiet", "--bare", self.remote)
        self.source = git("commit-tree", git("mktree", stdin=""), "-m", "fixture baseline")
        git("push", self.remote, self.source + ":refs/heads/main")

    def call(self, command, owner="slot", gen=1, value=""):
        return transact(self.remote, command, owner, gen, self.source, value)

    def test_ten_contenders(self):
        def acquire(i):
            try:
                return self.call("acquire", str(i))["owner"]
            except (Blocked, subprocess.CalledProcessError):
                return None

        with concurrent.futures.ThreadPoolExecutor(10) as pool:
            winners = [owner for owner in pool.map(acquire, range(10)) if owner is not None]
        self.assertEqual(winners, [self.call("inspect")["owner"]])

    def test_recover_and_fence(self):
        with patch("cycle_registry.time.time", return_value=100):
            initial = self.call("acquire")
            self.call("checkpoint", value="tested")
        resumed = self.call("acquire", owner="next")
        self.assertEqual((resumed["cycle"], resumed["checkpoint"]), (initial["cycle"], "tested"))
        with self.assertRaises(Blocked):
            self.call("complete")
        self.call("complete", "next", 2)

    def test_crash_after_external_effect(self):
        effect = pathlib.Path(self.remote).parent / "receipt"
        worker = """
import os, pathlib, sys
from unittest.mock import patch
from cycle_registry import transact
remote, source, effect = sys.argv[1:]
with patch('cycle_registry.time.time', return_value=100):
    transact(remote, 'acquire', 'slot', 0, source)
    transact(remote, 'reserve', 'slot', 1, source, 'model-1')
    pathlib.Path(effect).write_text('executed')
    os._exit(23)
"""
        child = subprocess.run([sys.executable, "-c", worker, self.remote, self.source, str(effect)],
                               cwd=pathlib.Path(__file__).resolve().parent)
        self.assertEqual(child.returncode, 23)
        self.assertEqual(effect.read_text(), "executed")
        with self.assertRaisesRegex(Blocked, "unresolved"):
            self.call("acquire", "next")
        self.assertEqual(self.call("inspect")["pending"], "model-1")

    def test_repository_isolation(self):
        sibling = str(pathlib.Path(self.remote).parent / "sibling.git")
        git("clone", "--bare", self.remote, sibling)
        self.call("acquire")
        self.call("stop")
        transact(sibling, "acquire", "slot", 0, self.source)
        self.assertEqual(transact(sibling, "complete", "slot", 1, self.source)["phase"], "complete")
        self.assertEqual(self.call("inspect")["phase"], "blocked")

    def test_recorded_effect_and_source_conflict(self):
        self.call("acquire")
        for key in ("pr", "model", "artifact"):
            self.call("reserve", value=key)
            self.call("record", value=key + "=receipt")
            with self.assertRaises(Blocked):
                self.call("reserve", value=key)
        before = self.call("inspect")
        with self.assertRaises(Blocked):
            transact(self.remote, "complete", "slot", 1, "wrong")
        self.assertEqual(self.call("inspect"), before)
        self.call("stop")
        with self.assertRaises(Blocked):
            self.call("acquire", "next")


class ExpiredLeaseRecoveryTest(RegistryTest):
    def test_authenticated_recovery_and_fencing(self):
        from cycle_registry import recover_verified
        with patch("cycle_registry.time.time", return_value=100):
            self.call("acquire")
            self.call("reserve", value="merge-pr-1")
        with patch("cycle_registry.time.time", return_value=800):
            result = recover_verified(self.remote, owner="recovery", source=self.source,
                operation="merge-pr-1", evidence="authenticated-merge-sha",
                verifier=lambda remote, op, ev: remote == self.remote and op == "merge-pr-1" and ev == "authenticated-merge-sha")
        self.assertEqual(result["generation"], 2)
        self.assertIsNone(result["pending"])
        self.assertEqual(result["results"]["merge-pr-1"], "authenticated-merge-sha")
        with self.assertRaises(Blocked):
            self.call("complete", "slot", 1)
        with self.assertRaises(Blocked):
            recover_verified(self.remote, owner="other", source=self.source, operation="merge-pr-1",
                evidence="authenticated-merge-sha", verifier=lambda *args: True)

    def test_unknown_outcome_is_blocked_and_preserved(self):
        from cycle_registry import recover_verified
        with patch("cycle_registry.time.time", return_value=100):
            self.call("acquire")
            self.call("reserve", value="merge-pr-1")
        before = self.call("inspect")
        with patch("cycle_registry.time.time", return_value=800):
            with self.assertRaises(Blocked):
                recover_verified(self.remote, owner="recovery", source=self.source, operation="merge-pr-1",
                    evidence="unknown", verifier=lambda *args: False)
        self.assertEqual(before, self.call("inspect"))

    def test_active_lease_and_wrong_operation_blocked(self):
        from cycle_registry import recover_verified
        with patch("cycle_registry.time.time", return_value=100):
            self.call("acquire")
            self.call("reserve", value="merge-pr-1")
            with self.assertRaises(Blocked):
                recover_verified(self.remote, owner="recovery", source=self.source, operation="merge-pr-1",
                    evidence="proof", verifier=lambda *args: True)
        with patch("cycle_registry.time.time", return_value=800):
            with self.assertRaises(Blocked):
                recover_verified(self.remote, owner="recovery", source=self.source, operation="wrong",
                    evidence="proof", verifier=lambda *args: True)


if __name__ == "__main__":
    unittest.main()
