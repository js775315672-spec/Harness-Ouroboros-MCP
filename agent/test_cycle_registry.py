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
    def test_legacy_callback_bypass_rejected(self):
        from cycle_registry import recover_verified
        with patch("cycle_registry.time.time", return_value=100):
            self.call("acquire")
            self.call("reserve", value="merge-pr-1")
        before = self.call("inspect")
        with self.assertRaisesRegex(Blocked, "arbitrary verifier"):
            recover_verified(self.remote, owner="attacker", source=self.source,
                             operation="merge-pr-1", evidence="forged",
                             verifier=lambda *args: True)
        self.assertEqual(before, self.call("inspect"))

    def test_structured_merge_cannot_use_generic_record(self):
        import json
        with patch("cycle_registry.time.time", return_value=100):
            self.call("acquire")
            op = json.dumps({"repository": "example/repo", "pr": 1})
            self.call("reserve", value=op)
            before = self.call("inspect")
            with self.assertRaisesRegex(Blocked, "authenticated recovery"):
                self.call("record", value=op + "=forged")
            self.assertEqual(before, self.call("inspect"))


class GitHubMergeVerifierTest(unittest.TestCase):
    def test_confirmed_merge_and_tampering(self):
        import json
        from cycle_registry import REMOTE, Blocked, verify_github_merge
        repo = REMOTE.removeprefix("https://github.com/").removesuffix(".git")
        head, base, merge = "a"*40, "b"*40, "c"*40
        intent = {"repository": repo, "pr": 123, "operation_id": "merge-123",
                  "head_sha": head, "base_sha": base}
        receipt = dict(intent, merge_commit_sha=merge)
        response = {"merged": True, "state": "closed", "merge_commit_sha": merge,
                    "head": {"sha": head}, "base": {"sha": base, "repo": {"full_name": repo}}}
        encode = lambda obj: json.dumps(obj, sort_keys=True)
        self.assertTrue(verify_github_merge(REMOTE, encode(intent), encode(receipt),
                        api_fetch=lambda url: response))
        for bad in [
            dict(response, merged=False), dict(response, merge_commit_sha="d"*40),
            dict(response, head={"sha": "d"*40}),
            dict(response, base={"sha": base, "repo": {"full_name": "other/repo"}})
        ]:
            with self.assertRaises(Blocked):
                verify_github_merge(REMOTE, encode(intent), encode(receipt),
                                    api_fetch=lambda url, bad=bad: bad)
        with self.assertRaises(Blocked):
            verify_github_merge(REMOTE, encode(intent), encode(receipt),
                                api_fetch=lambda url: (_ for _ in ()).throw(TimeoutError()))
        with self.assertRaises(Blocked):
            verify_github_merge("https://github.com/other/repo.git", encode(intent),
                                encode(receipt), api_fetch=lambda url: response)



class MergeMainTransitionTest(RegistryTest):
    def test_verified_merge_after_main_advance(self):
        import json
        from unittest.mock import patch
        import cycle_registry as registry
        from cycle_registry import git
        with patch("cycle_registry.time.time", return_value=100):
            self.call("acquire")
            intent = {"repository": "test/repo", "pr": 1, "operation_id": "merge-test-1",
                      "head_sha": "a"*40, "base_sha": self.source}
            new_main = git("commit-tree", git("mktree", stdin=""), "-p", self.source, "-m", "merged")
            receipt = dict(intent, merge_commit_sha=new_main)
            op, proof = json.dumps(intent, sort_keys=True), json.dumps(receipt, sort_keys=True)
            self.call("reserve", value=op)
        git("push", self.remote, new_main + ":refs/heads/main")
        with patch.object(registry, "REMOTE", self.remote), patch.object(registry, "verify_github_merge", return_value=True), patch("cycle_registry.time.time", return_value=800):
            result = registry.recover_merged_pr(self.remote, owner="recovery", source=self.source,
                                                operation=op, evidence=proof)
        self.assertIsNone(result["pending"])
        self.assertEqual(result["results"][op], proof)
        self.assertEqual(result["generation"], 2)
        with patch.object(registry, "REMOTE", self.remote), patch.object(registry, "verify_github_merge", return_value=True):
            with self.assertRaises(Blocked):
                registry.recover_merged_pr(self.remote, owner="retry", source=self.source,
                                           operation=op, evidence=proof)

    def test_unknown_or_unrelated_main_is_blocked(self):
        import json
        from unittest.mock import patch
        import cycle_registry as registry
        with patch("cycle_registry.time.time", return_value=100):
            self.call("acquire")
            intent = {"repository": "test/repo", "pr": 1, "operation_id": "merge-test-2",
                      "head_sha": "a"*40, "base_sha": self.source}
            op = json.dumps(intent, sort_keys=True)
            self.call("reserve", value=op)
        proof = json.dumps(dict(intent, merge_commit_sha="f"*40), sort_keys=True)
        before = self.call("inspect")
        with patch.object(registry, "REMOTE", self.remote), patch.object(registry, "verify_github_merge", return_value=True):
            with self.assertRaises(Blocked):
                registry.recover_merged_pr(self.remote, owner="recovery", source=self.source,
                                           operation=op, evidence=proof)
        self.assertEqual(self.call("inspect"), before)
if __name__ == "__main__":
    unittest.main()
