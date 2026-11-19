"""Independent replay of stable proposal ID behavior."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from p3l_hydra_next_task import select


class ProposalIdentityTests(unittest.TestCase):
    def proposal(self, run_id, job_id, head, name):
        run = dict(id=run_id, event="push", head_branch="main", status="completed", run_attempt=1, head_sha=head)
        job = dict(id=job_id, name=name, conclusion="failure")
        return select([run], {run_id: [job]})["proposal"]

    def test_recurring_failure_keeps_identity_and_updates_evidence(self):
        first = self.proposal(1, 2, "a" * 40, "Worker a")
        repeated = self.proposal(3, 4, "a" * 40, "Worker a")
        self.assertEqual(first["id"], repeated["id"])
        self.assertTrue(repeated["evidence"].endswith("/runs/3/job/4"))

    def test_new_commit_or_worker_has_its_own_identity(self):
        first = self.proposal(1, 2, "a" * 40, "Worker a")
        self.assertNotEqual(first["id"], self.proposal(3, 4, "b" * 40, "Worker a")["id"])
        self.assertNotEqual(first["id"], self.proposal(3, 4, "a" * 40, "Worker b")["id"])
