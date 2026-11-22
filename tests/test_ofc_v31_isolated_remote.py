"""Offline integration tests: isolated temporary bare Git remote, never production refs."""
import json
import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from agent import cycle_registry as registry


def git(*args, cwd=None, check=True, stdin=None):
    return subprocess.run(["git", *map(str, args)], cwd=cwd, input=stdin,
                          text=True, capture_output=True, check=check)


class IsolatedRemoteCAS(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.remote = root / "isolated.git"
        self.work = root / "work"
        git("init", "--bare", self.remote)
        git("init", self.work)
        git("config", "user.name", "OFC isolated test", cwd=self.work)
        git("config", "user.email", "test@example.invalid", cwd=self.work)
        (self.work / "seed.txt").write_text("seed\n")
        git("add", ".", cwd=self.work)
        git("commit", "-m", "seed", cwd=self.work)
        git("branch", "-M", "main", cwd=self.work)
        git("remote", "add", "origin", self.remote, cwd=self.work)
        git("push", "origin", "main", cwd=self.work)
        self.source = git("rev-parse", "HEAD", cwd=self.work).stdout.strip()
        self.old_cwd = os.getcwd()
        os.chdir(self.work)
        self.addCleanup(os.chdir, self.old_cwd)

    def test_remote_cas_two_writers_one_winner(self):
        # Real git push against a local bare remote; not a GitHub production CAS test.
        barrier = threading.Barrier(2)
        results = []
        def writer(i):
            obj = git("hash-object", "-w", "--stdin", cwd=self.work,
                      stdin=f"writer-{i}\n").stdout.strip()
            tree = git("mktree", cwd=self.work,
                       stdin=f"100644 blob {obj}\tstate.json\n").stdout.strip()
            commit = git("commit-tree", tree, "-m", f"writer-{i}", cwd=self.work).stdout.strip()
            barrier.wait(timeout=20)
            result = git("push", "--porcelain",
                         f"--force-with-lease={registry.REF}:",
                         str(self.remote), f"{commit}:{registry.REF}",
                         cwd=self.work, check=False)
            results.append(result.returncode)
        threads = [threading.Thread(target=writer, args=(i,)) for i in range(2)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=30)
        self.assertEqual(len(results), 2)
        self.assertEqual(sorted(results), [0, 1])
        self.assertTrue(git("ls-remote", self.remote, registry.REF).stdout.strip())

    def test_expired_lease_pending_preserved(self):
        state = dict(schema=1, agent=registry.AGENT, cycle="existing",
                     source=self.source, phase="open", owner="prior",
                     generation=3, expires=0, checkpoint="saved",
                     pending="external-unknown", results={"done": "receipt"})
        with self.assertRaises(registry.Blocked):
            registry.transition(state, "acquire", "new", 0, self.source, "", 100, 60)
        self.assertEqual(state["pending"], "external-unknown")
        self.assertEqual(state["results"], {"done": "receipt"})

    def test_source_drift_rejected_before_remote_mutation(self):
        before = git("ls-remote", self.remote, registry.REF).stdout
        with self.assertRaises(registry.Blocked):
            registry.transact(str(self.remote), "acquire",
                              owner="isolated-test", source="0" * 40)
        self.assertEqual(git("ls-remote", self.remote, registry.REF).stdout, before)

    def test_receipt_survives_reacquire(self):
        state = dict(schema=1, agent=registry.AGENT, cycle="existing",
                     source=self.source, phase="open", owner="prior",
                     generation=3, expires=0, checkpoint="saved",
                     pending=None, results={"done": "receipt"})
        next_state, changed = registry.transition(state, "acquire", "new", 0,
                                                  self.source, "", 100, 60)
        self.assertTrue(changed)
        self.assertEqual(next_state["results"]["done"], "receipt")
        self.assertEqual(next_state["generation"], 4)
        with self.assertRaises(registry.Blocked):
            registry.transition(next_state, "reserve", "prior", 3,
                                self.source, "another", 101, 60)


if __name__ == "__main__":
    unittest.main()
