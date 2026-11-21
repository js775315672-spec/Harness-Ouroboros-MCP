"""Independent P0 recovery audit using disposable local bare Git repositories.

No production remote writes. Runs independently from test_cycle_registry.py.
"""
import concurrent.futures
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import cycle_registry as r


class IndependentP0Audit(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ofc-p0-audit-")
        self.addCleanup(tmp.cleanup)
        self.remote = str(pathlib.Path(tmp.name) / "audit.git")
        r.git("init", "--quiet", "--bare", self.remote)
        self.source = r.git("commit-tree", r.git("mktree", stdin=""), "-m", "isolated base")
        r.git("push", self.remote, self.source + ":refs/heads/main")

    def reserve_expired(self, operation="merge-1"):
        with patch.object(r.time, "time", return_value=100):
            r.transact(self.remote, "acquire", "first", 0, self.source)
            r.transact(self.remote, "reserve", "first", 1, self.source, operation)

    def recover(self, operation="merge-1", evidence="verified", verifier=None):
        return r.recover_verified(self.remote, owner="auditor", source=self.source,
            operation=operation, evidence=evidence,
            verifier=verifier or (lambda *args: True))

    def test_expired_lease_recovery_and_duplicate_fencing(self):
        self.reserve_expired()
        with patch.object(r.time, "time", return_value=800):
            result = self.recover()
            self.assertIsNone(result["pending"])
            self.assertEqual(result["results"]["merge-1"], "verified")
            with self.assertRaises(r.Blocked):
                self.recover()
        self.assertEqual(r.transact(self.remote, "inspect")["results"]["merge-1"], "verified")

    def test_unknown_external_outcome_preserves_pending(self):
        self.reserve_expired()
        with patch.object(r.time, "time", return_value=800):
            with self.assertRaises(r.Blocked):
                self.recover(verifier=lambda *args: False)
        self.assertEqual(r.transact(self.remote, "inspect")["pending"], "merge-1")

    def test_main_drift_blocks_unverified_recovery(self):
        self.reserve_expired()
        newer = r.git("commit-tree", r.git("mktree", stdin=""),
                      "-p", self.source, "-m", "main moved")
        r.git("push", self.remote, newer + ":refs/heads/main")
        with patch.object(r.time, "time", return_value=800):
            with self.assertRaises(r.Blocked):
                self.recover()
        self.assertEqual(r.transact(self.remote, "inspect")["pending"], "merge-1")

    def test_cas_competition_has_single_winner(self):
        self.reserve_expired()
        def contender(i):
            try:
                with patch.object(r.time, "time", return_value=800):
                    return self.recover(evidence="proof-" + str(i))["results"]["merge-1"]
            except (r.Blocked, subprocess.CalledProcessError):
                return None
        # All contenders race the same pending operation; CAS must accept exactly one.
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            wins = [v for v in pool.map(contender, range(6)) if v is not None]
        self.assertEqual(len(wins), 1)
        self.assertEqual(r.transact(self.remote, "inspect")["results"]["merge-1"], wins[0])

    def test_forged_receipt_and_api_outage_fail_closed(self):
        repo = r.REMOTE.removeprefix("https://github.com/").removesuffix(".git")
        intent = {"repository": repo, "pr": 7, "operation_id": "audit-merge-7",
                  "head_sha": "a"*40, "base_sha": "b"*40}
        proof = dict(intent, merge_commit_sha="c"*40)
        actual = {"merged": False, "state": "open", "merge_commit_sha": None,
                  "head": {"sha": "a"*40},
                  "base": {"sha": "b"*40, "repo": {"full_name": repo}}}
        for api in (lambda url: actual,
                    lambda url: (_ for _ in ()).throw(TimeoutError("offline"))):
            with self.assertRaises(r.Blocked):
                r.verify_github_merge(r.REMOTE, json.dumps(intent),
                                      json.dumps(proof), api_fetch=api)

    def test_authenticated_main_transition_with_isolated_git(self):
        self.reserve_expired("merge-intent")
        merged = r.git("commit-tree", r.git("mktree", stdin=""),
                       "-p", self.source, "-m", "verified merge")
        r.git("push", self.remote, merged + ":refs/heads/main")
        intent = {"base_sha": self.source, "operation_id": "audit-merge"}
        receipt = {"merge_commit_sha": merged}
        # Replace the pending key with a canonical JSON intent in a fresh isolated registry.
        # A fresh remote is used to avoid mutating an existing pending operation.
        with tempfile.TemporaryDirectory(prefix="ofc-merge-audit-") as tmp:
            remote = str(pathlib.Path(tmp) / "merge.git")
            r.git("init", "--quiet", "--bare", remote)
            r.git("push", remote, self.source + ":refs/heads/main")
            op = json.dumps(intent, sort_keys=True)
            proof = json.dumps(receipt, sort_keys=True)
            with patch.object(r.time, "time", return_value=100):
                r.transact(remote, "acquire", "worker", 0, self.source)
                r.transact(remote, "reserve", "worker", 1, self.source, op)
            r.git("push", remote, merged + ":refs/heads/main")
            with patch.object(r, "REMOTE", remote), patch.object(
                r, "verify_github_merge", return_value=True
            ), patch.object(r.time, "time", return_value=800):
                result = r.recover_merged_pr(remote, owner="auditor", source=self.source,
                                             operation=op, evidence=proof)
            self.assertIsNone(result["pending"])
            self.assertEqual(result["results"][op], proof)


if __name__ == "__main__":
    unittest.main(verbosity=2)
