import concurrent.futures
import unittest

from oril.lease import owner
from oril.orchestrator import plan


class CampaignTests(unittest.TestCase):
    def test_five_contenders_share_one_commit_owner_after_restart(self):
        runs = [dict(id=i, event="pull_request", head_sha="a", pull_requests=[{"base":{"sha":"b"}}])
                for i in range(20,25)]
        def claim(run):
            return owner(runs, "a", "b", run["id"]) == run["id"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as workers:
            self.assertEqual(list(workers.map(claim, reversed(runs))), [False]*4 + [True])
        self.assertTrue(claim(runs[0]))
        with self.assertRaises(ValueError):
            owner(runs, "a", "different-base", 20)

    def test_feedback_selects_an_untried_experiment(self):
        self.assertEqual(plan({"tried":[], "candidate_errors":0}), "remove_redundancy")
        memory = {"tried":["remove_redundancy"], "candidate_errors":10}
        self.assertEqual(plan(memory), "integer_format")
        self.assertEqual(plan(dict(memory, candidate_errors=0)), "check_sum")
        memory["tried"].append("integer_format")
        self.assertEqual(plan(memory), "check_sum")
