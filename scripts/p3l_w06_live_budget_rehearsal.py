"""Exercise the W06 stub through the real create-only provider on a draft runner."""
import hashlib
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from test_p3l_w04_local_service import SharedAdmissionTests, serving
from p3l_w04_attempt_registry import AttemptBlocked
import p3l_w04_github_claim as claims


class LiveBudgetRehearsal(SharedAdmissionTests):
    def test_live_budget(self):
        token = os.environ.pop("GH_TOKEN")
        run = int(os.environ["GITHUB_RUN_ID"])
        head = os.environ["REVIEW_HEAD"]
        from dataclasses import replace
        from test_p3l_w04_local_service import w06
        self.inputs = replace(self.inputs, head_sha=head,
                              public_contract_sha256=hashlib.sha256(f"rehearsal:{run}".encode()).hexdigest())
        handoff = {**w06.w02.build(None), "w01_provisional_spec_sha256": self.inputs.public_contract_sha256}
        request = lambda *args: claims.github(token, *args)
        first = self.registry("live-first.sqlite3")
        second = self.registry("live-second.sqlite3")
        from test_p3l_w04_local_service import ROOT, RegistryClient
        with patch.object(claims, "START_REF_PREFIX", "refs/heads/rehearsal/w06-live/"), \
             patch.object(w06, "observed_head", return_value=head), \
             patch.object(w06.w02, "build", return_value=handoff):
            for registry, expected in ((first, True), (second, False)):
                budget = claims.SharedBudget(self.inputs, run, request)
                with serving(registry, shared_budget=budget) as port:
                    client = RegistryClient(port, require_shared=True)
                    lease = client.reserve(self.inputs, "rehearsal", ttl_seconds=60)
                    args = (ROOT, head, run, Path("stub"), Path("stub"), Path("stub"))
                    if expected:
                        result = w06.execute(*args, infer_fn=self.infer, admission=(client, lease))
                    else:
                        with self.assertRaisesRegex(AttemptBlocked, "HTTP 409"):
                            w06.execute(*args, infer_fn=self.infer, admission=(client, lease))
        self.infer.assert_called_once()
        print(json.dumps({"run_id": run, "head": head, "task_key": self.inputs.task_key,
                          "ref": "refs/heads/rehearsal/w06-live/" + self.inputs.semantic_key,
                          "prompt_sha256": result["prompt_sha256"],
                          "result_sha256": result["raw_response_sha256"],
                          "stub_calls": 1, "model_calls": 0, "duplicate_blocked": True}, sort_keys=True))


if __name__ == "__main__":
    unittest.main(defaultTest="LiveBudgetRehearsal.test_live_budget")
