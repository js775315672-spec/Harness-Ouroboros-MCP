import copy
import unittest

from scripts.oril_v2_actions_snapshot import assemble

SHA = "b48a720ad54906740a6eeafa93847f9f66e1e824"


def sample():
    run = {"id": 44673810522, "run_attempt": 1, "head_sha": SHA,
           "status": "completed", "conclusion": "success",
           "html_url": "https://github.com/example/test/actions/runs/44673810522"}
    jobs = {"total_count": 1, "jobs": [
        {"id": 136080746677, "run_id": 44673810522, "run_attempt": 1,
         "head_sha": SHA, "status": "completed", "name": "offline-tests",
         "conclusion": "success", "started_at": "2026-11-20T04:21:08Z",
         "completed_at": "2026-11-20T04:21:12Z"}]}
    return run, jobs


class SnapshotTests(unittest.TestCase):
    def test_api_shaped_snapshot_measures_job_only(self):
        run, jobs = sample()
        out = assemble(run, jobs, SHA)
        self.assertEqual(out["run_id"], 44673810522)
        self.assertEqual(out["jobs"][0]["duration_seconds"], 4)
        self.assertEqual(out["independent_verification"], "unverified")
        self.assertEqual(out["snapshot_authenticity"], "unverified")
        self.assertEqual(out["model_quality_change"], "unmeasured")

    def test_wrong_expected_sha_rejected(self):
        run, jobs = sample()
        with self.assertRaises(ValueError):
            assemble(run, jobs, "a" * 40)

    def test_cross_run_job_rejected(self):
        run, jobs = sample()
        jobs["jobs"][0]["run_id"] += 1
        with self.assertRaises(ValueError):
            assemble(run, jobs, SHA)

    def test_cross_attempt_job_rejected(self):
        run, jobs = sample()
        jobs["jobs"][0]["run_attempt"] = 2
        with self.assertRaises(ValueError):
            assemble(run, jobs, SHA)

    def test_job_sha_mismatch_rejected(self):
        run, jobs = sample()
        jobs["jobs"][0]["head_sha"] = "a" * 40
        with self.assertRaises(ValueError):
            assemble(run, jobs, SHA)

    def test_incomplete_pagination_rejected(self):
        run, jobs = sample()
        jobs["total_count"] = 2
        with self.assertRaises(ValueError):
            assemble(run, jobs, SHA)

    def test_extra_unreported_job_rejected(self):
        run, jobs = sample()
        jobs["jobs"].append(copy.deepcopy(jobs["jobs"][0]))
        with self.assertRaises(ValueError):
            assemble(run, jobs, SHA)

    def test_boolean_run_id_rejected(self):
        run, jobs = sample()
        run["id"] = True
        with self.assertRaises(ValueError):
            assemble(run, jobs, SHA)

    def test_missing_attempt_rejected(self):
        run, jobs = sample()
        del run["run_attempt"]
        with self.assertRaises(ValueError):
            assemble(run, jobs, SHA)

    def test_unfinished_job_not_measured(self):
        run, jobs = sample()
        jobs["jobs"][0]["status"] = "in_progress"
        out = assemble(run, jobs, SHA)
        self.assertEqual(out["unmeasured_job_count"], 1)
        self.assertIsNone(out["jobs"][0]["duration_seconds"])

    def test_duplicate_id_rejected(self):
        run, jobs = sample()
        jobs["jobs"].append(copy.deepcopy(jobs["jobs"][0]))
        jobs["total_count"] = 2
        with self.assertRaises(ValueError):
            assemble(run, jobs, SHA)

    def test_no_jobs_rejected(self):
        run, jobs = sample()
        jobs["total_count"] = 0
        jobs["jobs"] = []
        with self.assertRaises(ValueError):
            assemble(run, jobs, SHA)


if __name__ == "__main__":
    unittest.main()
