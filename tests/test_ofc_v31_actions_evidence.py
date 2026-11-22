"""Offline read-only GitHub Actions adapter contract and adversarial cases."""
import copy
import unittest
from agent import cycle_registry as registry
from agent.actions_evidence import verify_actions

REPO = "example/isolated"
SHA = "a" * 40
RUN = 123
DIGEST = "sha256:" + "b" * 64


class ActionsEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.responses = {
            f"/repos/{REPO}/actions/runs/{RUN}": {
                "id": RUN, "head_sha": SHA, "repository": {"full_name": REPO},
                "status": "completed", "conclusion": "success"},
            f"/repos/{REPO}/actions/runs/{RUN}/jobs?per_page=100": {
                "total_count": 2, "jobs": [
                    {"id": 11, "run_id": RUN, "status": "completed", "conclusion": "success"},
                    {"id": 12, "run_id": RUN, "status": "completed", "conclusion": "success"}]},
            f"/repos/{REPO}/actions/runs/{RUN}/artifacts?per_page=100": {
                "total_count": 1, "artifacts": [{
                    "id": 41, "expired": False, "size_in_bytes": 10,
                    "digest": DIGEST, "workflow_run": {"id": RUN, "head_sha": SHA}}]},
        }
        self.paths = list(self.responses)

    def query(self, path):
        return copy.deepcopy(self.responses[path])

    def check(self, **kwargs):
        return verify_actions(REPO, RUN, SHA, get=self.query, **kwargs)

    def test_valid_complete_run_jobs_artifact_metadata(self):
        evidence = self.check()
        self.assertEqual(evidence.job_ids, (11, 12))
        self.assertEqual(evidence.artifact_ids, (41,))
        self.assertEqual(evidence.artifact_digests, (DIGEST,))
        self.assertFalse(evidence.artifact_bytes_verified)

    def test_run_sha_drift_rejected(self):
        self.responses[self.paths[0]]["head_sha"] = "c" * 40
        with self.assertRaises(registry.Blocked): self.check()

    def test_run_id_and_repo_mismatch_rejected(self):
        for field, value in [("id", 124), ("repository", {"full_name": "other/repo"})]:
            with self.subTest(field=field):
                original = self.responses[self.paths[0]][field]
                self.responses[self.paths[0]][field] = value
                with self.assertRaises(registry.Blocked): self.check()
                self.responses[self.paths[0]][field] = original

    def test_failed_job_rejected(self):
        self.responses[self.paths[1]]["jobs"][0]["conclusion"] = "failure"
        with self.assertRaises(registry.Blocked): self.check()

    def test_job_pagination_rejected(self):
        self.responses[self.paths[1]]["total_count"] = 101
        with self.assertRaises(registry.Blocked): self.check()

    def test_artifact_missing_or_expired_rejected(self):
        self.responses[self.paths[2]]["artifacts"][0]["expired"] = True
        with self.assertRaises(registry.Blocked): self.check()

    def test_artifact_digest_and_source_rejected(self):
        artifact = self.responses[self.paths[2]]["artifacts"][0]
        for key, bad in [("digest", "sha256:bad"), ("workflow_run", {"id": 999, "head_sha": SHA})]:
            with self.subTest(key=key):
                old = artifact[key]
                artifact[key] = bad
                with self.assertRaises(registry.Blocked): self.check()
                artifact[key] = old

    def test_missing_artifact_requires_explicit_opt_out(self):
        self.responses[self.paths[2]] = {"total_count": 0, "artifacts": []}
        with self.assertRaises(registry.Blocked): self.check()
        self.assertEqual(self.check(require_artifact=False).artifact_ids, ())

    def test_lookup_failure_is_blocked(self):
        def fail(_): raise TimeoutError("offline")
        with self.assertRaises(registry.Blocked):
            verify_actions(REPO, RUN, SHA, get=fail)

    def test_no_mutation_calls(self):
        calls = []
        def get(path):
            calls.append(path)
            return self.query(path)
        verify_actions(REPO, RUN, SHA, get=get)
        self.assertEqual(len(calls), 3)
        self.assertTrue(all("/actions/runs/" in path for path in calls))

if __name__ == "__main__":
    unittest.main()
