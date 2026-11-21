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

    def recover(self, operation="merge-1", evidence="proof", verifier=None):
        """Exercise the intentionally disabled legacy callback entrypoint."""
        return r.recover_verified(self.remote, owner="auditor", source=self.source,
                                  operation=operation, evidence=evidence,
                                  verifier=verifier or (lambda *args: True))

    def test_legacy_callback_is_rejected_and_pending_preserved(self):
        self.reserve_expired()
        with patch.object(r.time, "time", return_value=800):
            with self.assertRaisesRegex(r.Blocked, "arbitrary verifier"):
                self.recover()
        self.assertEqual(r.transact(self.remote, "inspect")["pending"], "merge-1")

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

    def test_cas_competition_cannot_bypass_authenticated_recovery(self):
        self.reserve_expired()
        def contender(i):
            try:
                with patch.object(r.time, "time", return_value=800):
                    self.recover(evidence="proof-" + str(i))
                return True
            except (r.Blocked, subprocess.CalledProcessError):
                return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            wins = list(pool.map(contender, range(6)))
        self.assertFalse(any(wins))
        self.assertEqual(r.transact(self.remote, "inspect")["pending"], "merge-1")

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



class AuthenticatedMergeRecoveryAudit(unittest.TestCase):
    """Black-box recovery tests against a disposable bare Git repository.

    The GitHub response is a controlled fixture. These tests exercise the
    verifier's complete checks, rather than patching it to always return True.
    They do not claim that any real GitHub pull request was merged.
    """

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ofc-authenticated-")
        self.addCleanup(tmp.cleanup)
        self.remote = str(pathlib.Path(tmp.name) / "merge.git")
        r.git("init", "--quiet", "--bare", self.remote)
        tree = r.git("mktree", stdin="")
        self.source = r.git("commit-tree", tree, "-m", "base")
        self.head = r.git("commit-tree", tree, "-p", self.source, "-m", "PR head")
        self.merged = r.git("commit-tree", tree, "-p", self.source,
                            "-p", self.head, "-m", "synthetic merge")
        r.git("push", self.remote, self.source + ":refs/heads/main")
        r.git("push", self.remote, self.head + ":refs/heads/proposed")
        repo = self.remote.removeprefix("https://github.com/").removesuffix(".git")
        self.intent = dict(repository=repo, pr=77, operation_id="audit-merge-00077",
                           head_sha=self.head, base_sha=self.source)
        self.operation = json.dumps(self.intent, sort_keys=True)
        self.receipt = json.dumps(dict(self.intent, merge_commit_sha=self.merged),
                                  sort_keys=True)
        self.api_data = {
            "number": 77, "merged": True, "state": "closed",
            "merge_commit_sha": self.merged,
            "head": {"sha": self.head},
            "base": {"sha": self.source, "repo": {"full_name": repo}},
        }
        with patch.object(r.time, "time", return_value=100):
            r.transact(self.remote, "acquire", "original", 0, self.source)
            r.transact(self.remote, "reserve", "original", 1, self.source,
                       self.operation)
        # Advance only the disposable bare repository's main ref.
        r.git("push", self.remote, self.merged + ":refs/heads/main")

    def fetch_confirmed(self, url):
        self.assertTrue(url.endswith("/pulls/77"))
        return self.api_data

    def recover(self, **kwargs):
        return r.recover_merged_pr(
            self.remote, owner="authenticated-auditor", source=self.source,
            operation=self.operation, evidence=self.receipt,
            api_fetch=self.fetch_confirmed, **kwargs)

    def registry_tip(self):
        return r.git("ls-remote", self.remote, r.REF).split()[0]

    def test_valid_receipt_expired_lease_and_duplicate_rejection(self):
        with patch.object(r, "REMOTE", self.remote):
            result = self.recover()
            self.assertEqual(result["generation"], 2)
            self.assertIsNone(result["pending"])
            self.assertEqual(result["results"][self.operation], self.receipt)
            tip = self.registry_tip()
            self.assertEqual(r.transact(self.remote, "inspect"), result)
            with self.assertRaises(r.Blocked):
                self.recover()
            self.assertEqual(self.registry_tip(), tip)

    def test_active_lease_is_not_recovered(self):
        before = self.registry_tip()
        with patch.object(r, "REMOTE", self.remote), patch.object(
                r.time, "time", return_value=150):
            with self.assertRaises(r.Blocked):
                self.recover()
        self.assertEqual(self.registry_tip(), before)
        self.assertEqual(r.transact(self.remote, "inspect")["pending"],
                         self.operation)

    def test_forged_github_response_fails_closed(self):
        before = self.registry_tip()
        bad_responses = [
            {"merged": False},
            {"merge_commit_sha": "f" * 40},
            {"head": {"sha": "f" * 40}},
            {"base": {"sha": self.source,
                      "repo": {"full_name": "attacker/repository"}}},
            {"number": 78},
        ]
        with patch.object(r, "REMOTE", self.remote):
            for update in bad_responses:
                original = self.api_data
                self.api_data = dict(original, **update)
                try:
                    with self.assertRaises(r.Blocked):
                        self.recover()
                    self.assertEqual(self.registry_tip(), before)
                finally:
                    self.api_data = original

    def test_api_outage_preserves_pending_and_tip(self):
        before = self.registry_tip()
        with patch.object(r, "REMOTE", self.remote), patch.object(
                self, "fetch_confirmed", side_effect=TimeoutError("offline")):
            with self.assertRaisesRegex(r.Blocked, "GitHub merge status unavailable"):
                self.recover()
        self.assertEqual(self.registry_tip(), before)

    def test_main_drift_rejected(self):
        later = r.git("commit-tree", r.git("mktree", stdin=""),
                      "-p", self.merged, "-m", "later main change")
        r.git("push", self.remote, later + ":refs/heads/main")
        before = self.registry_tip()
        with patch.object(r, "REMOTE", self.remote):
            with self.assertRaisesRegex(r.Blocked, "main is not"):
                self.recover()
        self.assertEqual(self.registry_tip(), before)

    def test_cas_competition_only_one_authenticated_recovery(self):
        def contender(index):
            try:
                return r.recover_merged_pr(
                    self.remote, owner="auditor-" + str(index),
                    source=self.source, operation=self.operation,
                    evidence=self.receipt, api_fetch=self.fetch_confirmed)
            except (r.Blocked, subprocess.CalledProcessError):
                return None
        with patch.object(r, "REMOTE", self.remote):
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
                outcomes = list(pool.map(contender, range(6)))
        winners = [outcome for outcome in outcomes if outcome is not None]
        self.assertEqual(len(winners), 1)
        state = r.transact(self.remote, "inspect")
        self.assertEqual(state["generation"], 2)
        self.assertIsNone(state["pending"])
        self.assertEqual(state["results"][self.operation], self.receipt)

    def test_production_api_callback_cannot_forge_verification(self):
        # Do not contact, merge or write to the production repository.
        with self.assertRaisesRegex(r.Blocked, "API response injection"):
            r.recover_merged_pr(
                r.REMOTE, owner="forger", source=self.source,
                operation=self.operation, evidence=self.receipt,
                api_fetch=lambda url: self.api_data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
