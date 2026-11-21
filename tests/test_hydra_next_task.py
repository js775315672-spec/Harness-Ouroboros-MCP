import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import p3l_hydra_next_task as planner


def run(number):
    return dict(id=number, event="push", head_branch="main", status="completed",
                run_attempt=1, head_sha="a" * 40)


def job(number, name, conclusion):
    return dict(id=number, name=name, conclusion=conclusion)


class PlannerTests(unittest.TestCase):
    def test_recovery_and_order(self):
        runs = [run(12), run(13)]
        jobs = {12: [job(1, "admit", "failure"), job(2, "Worker peer", "failure")],
                13: [job(3, "admit", "success"), job(4, "Worker peer", "skipped")]}
        result = planner.select(runs, jobs)
        self.assertEqual(result["proposal"]["job_id"], 2)
        self.assertEqual(planner.select(list(reversed(runs)), jobs), result)
        jobs[13].append(job(5, "Worker peer", "success"))
        self.assertEqual(planner.select(runs, jobs)["decision"], "no_unresolved_failure")

    def test_admission_failure_needs_only_newest_eligible_run(self):
        runs = [run(i) for i in range(13)]
        runs[-1]["run_attempt"] = 2
        with patch.object(planner, "run_jobs", return_value=[job(5, "admit", "timed_out")]) as read:
            result = planner.select_from(runs, read)
        read.assert_called_once_with(11)
        self.assertEqual(result["proposal"]["job_id"], 5)

    def test_paged_evidence(self):
        jobs = [job(i, "admit", "success") for i in range(101)]
        for tail in ([jobs[-1]], [jobs[0]], []):
            pages = [dict(total_count=101, jobs=jobs[:100]), dict(total_count=101, jobs=tail)]
            with patch.object(planner, "fetch", side_effect=pages) as read:
                if tail == [jobs[-1]]:
                    self.assertEqual(planner.run_jobs(9), jobs)
                else:
                    with self.assertRaises(ValueError):
                        planner.run_jobs(9)
                self.assertTrue(read.call_args.args[0].endswith("&page=2"))

    def test_cli_feedback(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "result.json"
            with patch.object(planner, "fetch", return_value={"workflow_runs": []}):
                planner.main(output)
            result = json.loads(output.read_text())
            self.assertIsNone(result["proposal"])
            self.assertIn(result["model_review"]["task"], {"independent_evaluation", "review_training_errors"})
            source = "docs/evolution/cycle-01-dispatch-preflight.json"
            record = json.loads((Path(__file__).resolve().parents[1] / source).read_text())
            if record["status"].startswith("blocked_") and record["dispatch_count"] == 0:
                self.assertEqual(result["next_review"]["task"], record["required_next_evidence"])
            else:
                self.assertNotIn("next_review", result)
