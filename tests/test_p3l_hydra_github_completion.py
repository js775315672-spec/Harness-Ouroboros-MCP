"""Check trusted producer approval without network or repository writes."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from p3l_hydra_github_completion import verify_completion


class TrustedProducerTests(unittest.TestCase):
    def setUp(self):
        self.repo = "owner/repo"
        self.workflow = ".github/workflows/producer.yml"
        self.event = dict(task="first", head="a" * 40, run_id=12, job_id=34)
        self.approval = ("main", self.event["head"], 56)
        self.run = dict(id=12, repository={"full_name": self.repo},
                        head_repository={"full_name": self.repo}, path=self.workflow,
                        event="push", head_sha=self.event["head"], run_attempt=1,
                        head_branch="main", workflow_id=56, status="completed", conclusion="success")
        self.step = dict(name="Verify", status="completed", conclusion="success")
        self.job = dict(id=34, run_id=12, head_sha=self.event["head"], name="source",
                        status="completed", conclusion="success", steps=[self.step])

    def verify(self, approval):
        def fetch(path):
            return {f"repos/{self.repo}/actions/runs/12": self.run,
                    f"repos/{self.repo}/actions/jobs/34": self.job}[path]
        return verify_completion(self.event, repository=self.repo, workflow=self.workflow,
                                 job_name="source", required_step="Verify", fetch=fetch,
                                 trusted_push=approval)

    def test_accepts_exact_push_only_with_approval(self):
        self.assertTrue(self.verify(self.approval)["passed"])
        with self.assertRaises(ValueError):
            self.verify(None)
        with self.assertRaises(ValueError):
            self.verify(("main", "b" * 40, 56))

    def test_rejects_wrong_run_provenance_or_result(self):
        for key, value in dict(head_branch="other", workflow_id=57, run_attempt=2,
                               event="pull_request", status="in_progress", conclusion="failure",
                               head_sha="b" * 40, head_repository={"full_name": "fork/repo"}).items():
            with self.subTest(key=key):
                original = self.run[key]
                self.run[key] = value
                with self.assertRaises(ValueError):
                    self.verify(self.approval)
                self.run[key] = original

    def test_rejects_wrong_job_and_missing_required_step(self):
        self.job["run_id"] = 13
        with self.assertRaises(ValueError):
            self.verify(self.approval)
        self.job["run_id"] = 12
        self.job["steps"] = []
        with self.assertRaises(ValueError):
            self.verify(self.approval)

    def test_pull_request_default_preserves_existing_proof(self):
        self.run["event"] = "pull_request"
        self.assertTrue(self.verify(None)["passed"])
        with self.assertRaises(ValueError):
            self.verify(self.approval)
