"""Fail-closed tests for GitHub Actions proof and trend collection."""
import pathlib
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_actions_proof_report import collect, report, seconds, summarize_run


def sample(n=1, duration=15, *, workflow="ORIL v2 single SHA offline integration (experimental)",
           event="pull_request", conclusion="success", attempt=1, checkout=None):
    when = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc) + timedelta(minutes=n * 10)
    started = when + timedelta(seconds=3)
    ended = started + timedelta(seconds=duration)
    stamp = lambda t: t.isoformat().replace("+00:00", "Z")
    run = {
        "id": 40000000000 + n, "head_sha": "a" * 40, "status": "completed",
        "conclusion": conclusion, "created_at": stamp(when), "run_attempt": attempt,
        "name": workflow, "event": event, "html_url": "https://github.com/test/repo/actions/runs/" + str(n)
    }
    jobs = [{
        "id": 90000000 + n, "head_sha": checkout or "b" * 40, "status": "completed",
        "conclusion": conclusion, "started_at": stamp(started), "completed_at": stamp(ended),
    }]
    return run, jobs


class SourceProofTests(unittest.TestCase):
    def test_elapsed_utc(self):
        self.assertEqual(seconds("2026-11-20T00:00:00Z", "2026-11-20T00:00:04Z"), 4)

    def test_elapsed_negative_or_naive_not_measured(self):
        self.assertIsNone(seconds("2026-11-20T00:01:00Z", "2026-11-20T00:00:00Z"))
        self.assertIsNone(seconds("2026-11-20T00:00:00", "2026-11-20T00:00:03"))

    def test_measures_queue_job_and_distinguishes_merge_sha(self):
        run, jobs = sample()
        row = summarize_run(run, jobs)
        self.assertEqual(row["queue_seconds"], 3)
        self.assertEqual(row["ci_job_wall_seconds"], 15)
        self.assertEqual(row["job_api_head_shas"], ["b" * 40])
        self.assertIsNone(row["actual_checkout_sha"])
        self.assertEqual(row["head_sha"], "a" * 40)
        self.assertNotEqual(row["head_sha"], row["job_api_head_shas"][0])

    def test_missing_timestamps_are_null_not_zero(self):
        run, jobs = sample()
        jobs[0]["completed_at"] = None
        row = summarize_run(run, jobs)
        self.assertIsNone(row["ci_job_wall_seconds"])
        self.assertIsNone(row["queue_seconds"])

    def test_no_job_evidence_is_failure(self):
        with self.assertRaisesRegex(ValueError, "job evidence"):
            summarize_run(sample()[0], [])

    def test_rejects_wrong_run_sha(self):
        run, jobs = sample()
        run["head_sha"] = "not-a-sha"
        with self.assertRaisesRegex(ValueError, "SHA"):
            summarize_run(run, jobs)

    def test_requires_completed_run(self):
        run, jobs = sample()
        run["status"] = "queued"
        with self.assertRaisesRegex(ValueError, "completed"):
            summarize_run(run, jobs)

    def test_does_not_invent_model_or_cost_or_quality(self):
        row = summarize_run(*sample())
        for field in ("model_call_seconds", "whole_cycle_seconds", "usd_cost",
                      "accepted_independent_improvements", "heldout_quality_delta",
                      "gpu_training_attested", "adapter_created_attested"):
            self.assertIsNone(row[field], field)

    def test_workflow_event_comparable_only(self):
        rows = [summarize_run(*sample(i)) for i in range(1, 8)]
        rows.append(summarize_run(*sample(8, duration=100, event="push")))
        rows.append(summarize_run(*sample(9, duration=100, workflow="unrelated")))
        result = report(rows, "ORIL v2 single SHA offline integration (experimental)", "pull_request")
        self.assertEqual(result["selection"]["n"], 7)
        self.assertEqual(result["ci_speed"]["previous_median_seconds"], 15)
        self.assertEqual(result["ci_speed"]["change_pct"], 0)
        self.assertEqual(result["ci_speed"]["verdict"], "유지")

    def test_speed_change_requires_five_previous_successful(self):
        rows = [summarize_run(*sample(i)) for i in range(1, 5)]
        result = report(rows, "ORIL v2 single SHA offline integration (experimental)", "pull_request")
        self.assertIsNone(result["ci_speed"]["change_pct"])
        self.assertEqual(result["ci_speed"]["verdict"], "판단불가")

    def test_speed_verdict_better_with_enough_comparable(self):
        rows = [summarize_run(*sample(i)) for i in range(1, 7)]
        rows.append(summarize_run(*sample(7, duration=9)))
        result = report(rows, rows[0]["workflow_name"], "pull_request")
        self.assertEqual(result["ci_speed"]["change_pct"], -40)
        self.assertEqual(result["ci_speed"]["verdict"], "향상")
        self.assertEqual(result["developer_speed_verdict"], "판단불가")

    def test_failed_run_excluded_from_speed_median_but_in_rate(self):
        rows = [summarize_run(*sample(i)) for i in range(1, 8)]
        rows.append(summarize_run(*sample(8, duration=1, conclusion="failure")))
        r = report(rows, rows[0]["workflow_name"], "pull_request")
        self.assertEqual(r["observed_ci_failure_rate"], 0.125)
        self.assertIsNone(r["ci_speed"]["change_pct"])
        self.assertEqual(r["ci_speed"]["verdict"], "판단불가")

    def test_rerun_rate_is_workflow_not_agent_retry(self):
        rows = [summarize_run(*sample(i, attempt=(2 if i == 7 else 1))) for i in range(1, 8)]
        r = report(rows, rows[0]["workflow_name"], "pull_request")
        self.assertAlmostEqual(r["observed_workflow_rerun_rate"], 1 / 7)
        self.assertIsNone(r["agent_retry_rate"])

    def test_rejects_duplicate_or_invalid_window(self):
        with self.assertRaisesRegex(ValueError, "window"):
            report([], "suite", "push", window=2)

    def test_collect_filters_nonmatching_events_and_has_provenance(self):
        a, ja = sample(1, event="push")
        b, jb = sample(2)
        c, jc = sample(3)
        jobs_by_id = {b["id"]: jb, c["id"]: jc}
        urls = []
        def fake_api(url, token):
            urls.append(url)
            if url.endswith("/actions/runs?per_page=100"):
                return {"workflow_runs": [c, a, b]}
            for rid, jobs in jobs_by_id.items():
                if url.endswith("/actions/runs/" + str(rid) + "/jobs?per_page=100"):
                    return {"jobs": jobs, "total_count": len(jobs)}
            raise AssertionError(url)
        r = collect("test/repo", b["name"], "pull_request", api=fake_api)
        self.assertEqual(r["selection"]["n"], 2)
        self.assertEqual(r["run_ids"], [b["id"], c["id"]])
        self.assertEqual(len(urls), 3)
        self.assertFalse(r["collection"]["older_history_exhaustive"])

    def test_refuses_pagination_omissions(self):
        run, jobs = sample()
        def fake_api(url, token):
            if "jobs" in url:
                return {"jobs": jobs, "total_count": 2}
            return {"workflow_runs": [run]}
        with self.assertRaisesRegex(ValueError, "pagination incomplete"):
            collect("test/repo", run["name"], run["event"], api=fake_api)

    def test_refuses_invalid_repo(self):
        with self.assertRaisesRegex(ValueError, "owner/repo"):
            collect("../evil", "suite", "push", api=lambda *_: None)

    def test_unverifiable_quality_always_unknown(self):
        rows = [summarize_run(*sample(i)) for i in range(1, 9)]
        r = report(rows, rows[0]["workflow_name"], "pull_request")
        self.assertIsNone(r["heldout_quality_change"])
        self.assertIsNone(r["independent_accepted_improvements_per_hour"])
        self.assertEqual(r["model_quality_verdict"], "판단불가")


if __name__ == "__main__":
    unittest.main()
