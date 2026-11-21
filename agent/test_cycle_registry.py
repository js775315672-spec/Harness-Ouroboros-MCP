import concurrent.futures
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cycle_registry import Blocked, REPOSITORY, REF, git, transact
import json


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

    def test_mktree_path_bytes(self):
        blob = git("hash-object", "-w", "--stdin", stdin="{}")
        entry = f"100644 blob {blob}\tstate.json\n"
        # Observe the bytes produced by the legacy text pipe on each platform.
        echo = "import sys; print(sys.stdin.buffer.read().hex())"
        legacy = bytes.fromhex(subprocess.check_output(
            [sys.executable, "-c", echo], input=entry, text=True))
        legacy_tree = subprocess.check_output(["git", "mktree"], input=legacy).strip().decode()
        def path_bytes(tree):
            return subprocess.check_output(["git", "ls-tree", "-z", "--name-only", tree])
        legacy_name = path_bytes(legacy_tree)
        self.assertEqual(legacy_name, b"state.json\r\0" if sys.platform == "win32" else b"state.json\0")
        fixed_name = path_bytes(git("mktree", stdin=entry))
        print(f"legacy stdin={legacy.hex()} path={legacy_name.hex()} fixed path={fixed_name.hex()}")
        self.assertEqual(fixed_name, b"state.json\0")

    def merge_fixture(self, crash=False):
        tree = git("mktree", stdin="")
        head = git("commit-tree", tree, "-p", self.source, "-m", "candidate")
        merged = git("commit-tree", tree, "-p", self.source, "-p", head, "-m", "merge")
        pr = dict(number=42, base=dict(ref="main", repo=dict(full_name=REPOSITORY)),
                  head=dict(sha=head), merged=False, state="open")
        self.call("acquire")
        with patch("cycle_registry.github_pr", return_value=pr):
            self.call("merge_intent", value=json.dumps(dict(operation_key="merge-42",
                      pr_number=42, expected_head_sha=head)))
        if crash:
            worker = """
import os, subprocess, sys
remote, merged = sys.argv[1:]
subprocess.run(["git", "push", remote, merged + ":refs/heads/main"], check=True)
os._exit(23)
"""
            child = subprocess.run([sys.executable, "-c", worker, self.remote, merged])
            self.assertEqual(child.returncode, 23)
        else:
            git("push", self.remote, merged + ":refs/heads/main")
        pr.update(merged=True, state="closed", merge_commit_sha=merged)
        return pr

    def test_merge_receipt_and_duplicate_recovery(self):
        pr = self.merge_fixture()
        with self.assertRaisesRegex(Blocked, "pinned main"):
            self.call("record", value="merge-42=unverified")
        with patch("cycle_registry.github_pr", return_value=pr):
            state = self.call("merge_reconcile", value="merge-42")
        self.assertEqual(state["phase"], "complete")
        self.assertIsNone(state["pending"])
        self.assertEqual(state["results"]["merge-42"]["main_after"], pr["merge_commit_sha"])
        ref = git("ls-remote", self.remote, REF)
        self.assertEqual(self.call("merge_reconcile", value="merge-42"), state)
        self.assertEqual(git("ls-remote", self.remote, REF), ref)

    def test_merge_recovery_after_lost_response_and_cas_failure(self):
        pr = self.merge_fixture(crash=True)
        with patch("cycle_registry.github_pr", side_effect=Blocked("response lost")):
            with self.assertRaises(Blocked):
                self.call("merge_reconcile", value="merge-42")
        def failed_push(*args, **kwargs):
            if args[0] == "push":
                old = git("ls-remote", self.remote, REF).split()[0]
                tree = git("show", "-s", "--format=%T", old)
                contender = git("commit-tree", tree, "-p", old, "-m", "concurrent CAS")
                git("push", f"--force-with-lease={REF}:{old}", self.remote, contender + ":" + REF)
            return git(*args, **kwargs)
        with patch("cycle_registry.github_pr", return_value=pr):
            with patch("cycle_registry.git", side_effect=failed_push):
                with self.assertRaisesRegex(Blocked, "CAS"):
                    self.call("merge_reconcile", value="merge-42")
            self.assertEqual(self.call("inspect")["pending"], "merge-42")
            self.assertIsNone(self.call("merge_reconcile", value="merge-42")["pending"])

    def test_reject_wrong_key_head_owner_expiry_and_external_main(self):
        pr = self.merge_fixture()
        for owner, key, evidence in [
                ("slot", "other", pr), ("other", "merge-42", pr),
                ("slot", "merge-42", dict(pr, head=dict(sha="1"*40)))]:
            with patch("cycle_registry.github_pr", return_value=evidence):
                with self.assertRaises(Blocked):
                    self.call("merge_reconcile", owner, value=key)
        with patch("cycle_registry.time.time", return_value=10**12):
            with self.assertRaisesRegex(Blocked, "lease"):
                self.call("merge_reconcile", value="merge-42")
        next_main = git("commit-tree", git("mktree", stdin=""), "-p", pr["merge_commit_sha"], "-m", "external")
        git("push", self.remote, next_main + ":refs/heads/main")
        with patch("cycle_registry.github_pr", return_value=pr):
            with self.assertRaisesRegex(Blocked, "current main"):
                self.call("merge_reconcile", value="merge-42")
        self.assertEqual(self.call("inspect")["pending"], "merge-42")

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


if __name__ == "__main__":
    unittest.main()
