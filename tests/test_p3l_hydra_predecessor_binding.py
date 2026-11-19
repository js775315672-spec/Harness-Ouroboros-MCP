"""Offline replay of the verified campaign predecessor relationship."""
import base64
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from p3l_hydra_campaign_continuity import next_sequence, REPO


class PredecessorTests(unittest.TestCase):
    def setUp(self):
        self.head = "a" * 40
        self.row = dict(sequence=1, run=10, job=20, head=self.head, task="memory-replay-30", model_result_run=30)

    def read(self, path):
        repo = {"full_name": REPO}
        if "/contents/" in path:
            self.assertTrue(path.endswith("?ref="+self.head))
            raw=json.dumps({"approvals":[{"id":self.row["task"], "model_result_run":30}]}).encode()
            return dict(type="file",encoding="base64",content=base64.b64encode(raw).decode())
        if path.endswith("/runs/10"):
            return dict(id=10,repository=repo,workflow_id=423685918,head_branch="main",head_sha=self.head,run_attempt=1,status="completed",conclusion="success",event="push")
        if path.endswith("/jobs/20"):
            return dict(id=20,run_id=10,head_sha=self.head,status="completed",name="Worker "+self.row["task"],conclusion="success")
        return dict(id=int(path.rsplit("/",1)[-1]),repository=repo,status="completed",conclusion="success")

    def checkpoint(self):
        return dict(schema="hydra-nine-cycle-checkpoint-v1",campaign="hydra-nine-cycle",requested=9,completed=[self.row])

    def test_real_approval_identity_allows_next_sequence(self):
        self.assertEqual(next_sequence(self.checkpoint(), self.read)["next_sequence"], 2)

    def test_unrelated_success_never_advances(self):
        self.row["model_result_run"] = 40
        with self.assertRaisesRegex(ValueError, "approved predecessor"):
            next_sequence(self.checkpoint(), self.read)
