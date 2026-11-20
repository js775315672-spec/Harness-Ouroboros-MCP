import unittest
from scripts.oril_v2_job_telemetry import extract, seconds

SHA = "a" * 40


class JobTelemetryTests(unittest.TestCase):
    def test_valid_duration(self):
        self.assertEqual(seconds("2026-11-20T01:00:00Z", "2026-11-20T01:00:12Z"), 12)

    def test_invalid_or_negative_duration_is_unmeasured(self):
        self.assertIsNone(seconds("2026-11-20T01:00:12Z", "2026-11-20T01:00:00Z"))
        self.assertIsNone(seconds(None, "2026-11-20T01:00:00Z"))

    def test_sha_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            extract({"head_sha": "b" * 40, "jobs": []}, SHA)

    def test_missing_jobs_rejected(self):
        with self.assertRaises(ValueError):
            extract({"head_sha": SHA}, SHA)

    def test_unfinished_job_not_fabricated(self):
        data = {"head_sha": SHA, "run_id": 10, "jobs": [
            {"id": 2, "name": "verify", "status": "in_progress", "conclusion": None,
             "started_at": "2026-11-20T01:00:00Z", "completed_at": None}
        ]}
        out = extract(data, SHA)
        self.assertEqual(out["unmeasured_job_count"], 1)
        self.assertIsNone(out["jobs"][0]["duration_seconds"])
        self.assertEqual(out["model_quality_change"], "unmeasured")

    def test_completed_job_measured_not_independently_verified(self):
        data = {"head_sha": SHA, "jobs": [
            {"id": 1, "name": "test", "status": "completed", "conclusion": "success",
             "started_at": "2026-11-20T01:00:00Z",
             "completed_at": "2026-11-20T01:00:09Z"}
        ]}
        out = extract(data, SHA)
        self.assertEqual(out["jobs"][0]["duration_seconds"], 9)
        self.assertEqual(out["independent_verification"], "unverified")


    def test_non_hex_sha_rejected(self):
        with self.assertRaises(ValueError):
            extract({"head_sha": "z" * 40, "jobs": []}, "z" * 40)

    def test_duplicate_job_id_rejected(self):
        with self.assertRaises(ValueError):
            extract({"head_sha": SHA, "jobs": [{"id": 7}, {"id": 7}]}, SHA)

    def test_boolean_job_id_rejected(self):
        with self.assertRaises(ValueError):
            extract({"head_sha": SHA, "jobs": [{"id": True}]}, SHA)

    def test_running_job_with_end_timestamp_is_not_measured(self):
        result = extract({"head_sha": SHA, "jobs": [{
            "id": 5, "status": "in_progress",
            "started_at": "2026-11-20T01:00:00Z",
            "completed_at": "2026-11-20T01:00:12Z"}]}, SHA)
        self.assertIsNone(result["jobs"][0]["duration_seconds"])


if __name__ == "__main__":
    unittest.main()
