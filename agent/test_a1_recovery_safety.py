"""A1 fail-closed regression tests; no live GitHub calls or registry writes."""
import json
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import cycle_registry as registry


class A1RecoverySafety(unittest.TestCase):
    def state(self):
        return dict(schema=1, agent=registry.AGENT, phase="open", pending="merge-op",
                    source="a"*40, expires=100, generation=3, owner="old",
                    results={"previous": "proof"}, checkpoint="safe")

    def test_recovery_is_copy_on_write_and_fenced(self):
        original = self.state()
        recovered = registry.reconcile_expired(original, owner="new", source="a"*40,
            operation="merge-op", evidence="verified", verified=True, now=101)
        self.assertEqual(original["pending"], "merge-op")
        self.assertEqual(original["results"], {"previous": "proof"})
        self.assertIsNone(recovered["pending"])
        self.assertEqual(recovered["generation"], 4)
        self.assertEqual(recovered["results"]["previous"], "proof")
        self.assertEqual(recovered["checkpoint"], "safe")

    def test_rejects_untrusted_or_conflicting_recovery(self):
        cases = [
            ({"verified": False}, None),
            ({"evidence": ""}, None),
            ({"operation": "other"}, None),
            ({"source": "b"*40}, None),
            ({"ttl": 0}, None),
            ({"ttl": 3601}, None),
            ({}, {"expires": 102}),
            ({}, {"phase": "blocked"}),
            ({}, {"agent": "other"}),
            ({}, {"pending": None}),
            ({}, {"results": {"merge-op": "prior"}}),
        ]
        for overrides, state_overrides in cases:
            with self.subTest(overrides=overrides, state=state_overrides):
                state = self.state()
                if state_overrides:
                    state.update(state_overrides)
                before = json.dumps(state, sort_keys=True)
                args = dict(owner="new", source="a"*40, operation="merge-op",
                            evidence="verified", verified=True, now=101, ttl=600)
                args.update(overrides)
                with self.assertRaises(registry.Blocked):
                    registry.reconcile_expired(state, **args)
                self.assertEqual(json.dumps(state, sort_keys=True), before)

    def test_verifier_rejects_false_pr_identity_and_unavailable_api(self):
        repo = registry.REMOTE.removeprefix("https://github.com/").removesuffix(".git")
        intent = dict(repository=repo, pr=3, operation_id="merge-op-3",
                      head_sha="a"*40, base_sha="b"*40)
        receipt = dict(intent, merge_commit_sha="c"*40)
        response = dict(merged=True, state="closed", merge_commit_sha="c"*40,
                        head={"sha": "a"*40},
                        base={"sha": "b"*40, "repo": {"full_name": repo}})
        for mutation in [
            {"merged": False}, {"state": "open"},
            {"merge_commit_sha": "d"*40},
            {"head": {"sha": "d"*40}},
            {"base": {"sha": "b"*40, "repo": {"full_name": "attacker/repo"}}},
        ]:
            with self.subTest(mutation=mutation):
                with self.assertRaises(registry.Blocked):
                    registry.verify_github_merge(registry.REMOTE,
                        json.dumps(intent), json.dumps(receipt),
                        api_fetch=lambda url, mutation=mutation: dict(response, **mutation))
        with self.assertRaises(registry.Blocked):
            registry.verify_github_merge(registry.REMOTE,
                json.dumps(intent), json.dumps(receipt),
                api_fetch=lambda url: (_ for _ in ()).throw(TimeoutError()))

if __name__ == "__main__":
    unittest.main()
