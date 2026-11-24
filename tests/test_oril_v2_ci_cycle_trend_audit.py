"""Independent, synthetic negative tests for read-only Actions timing trend."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_ci_cycle_trend_audit import analyze, unique

WORKFLOW = "ORIL test"


def make_run(i, *, event="pull_request", status="completed", conclusion="success",
             wall=12, queue=3, name=WORKFLOW):
    base = datetime(2026, 11, 20, tzinfo=timezone.utc) + timedelta(minutes=30 * i)
    def iso(dt):
        return dt.isoformat().replace("+00:00", "Z")
    return {
        "id": 10000 + i, "name": name, "event": event, "status": status,
        "conclusion": conclusion, "head_sha": "a" * 40,
        "html_url": f"https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/{10000+i}",
        "created_at": iso(base),
        "run_started_at": iso(base + timedelta(seconds=queue)),
        "updated_at": iso(base + timedelta(seconds=queue+wall)),
    }


class TrendTests(unittest.TestCase):
    def test_homogeneous_sample_medians_and_sources(self):
        payload = {"workflow_runs": [make_run(i, wall=10+i, queue=i) for i in range(1, 9)]}
        result = analyze(payload, WORKFLOW)
        self.assertEqual(result["n"], 8)
        self.assertEqual(result["median_wall_seconds"], 14.5)
        self.assertEqual(result["median_queue_seconds"], 4.5)
        self.assertEqual(result["newer_median_wall_seconds"], 16.5)
        self.assertEqual(result["older_median_wall_seconds"], 12.5)
        self.assertEqual(result["verdict"], "판단불가")
        self.assertEqual(len(result["sources"]), 8)

    def test_failures_not_counted_as_improvements(self):
        p = {"workflow_runs": [make_run(i, conclusion="failure" if i % 2 else "success")
                               for i in range(1, 7)]}
        result = analyze(p, WORKFLOW)
        self.assertEqual(result["failed_cancelled_or_timed_out"], 3)
        self.assertEqual(result["failure_fraction"], 0.5)
        self.assertIsNone(result["independent_improvements_per_hour"])

    def test_different_workflow_is_excluded(self):
        p = {"workflow_runs": [make_run(1), make_run(2, name="different")]}
        self.assertEqual(analyze(p, WORKFLOW)["n"], 1)

    def test_other_event_is_not_mixed(self):
        p = {"workflow_runs": [make_run(i) for i in range(1, 7)] +
             [make_run(i+10, event="schedule") for i in range(1, 3)]}
        result = analyze(p, WORKFLOW)
        self.assertEqual(result["n"], 6)
        self.assertEqual(result["event"], "pull_request")

    def test_incomplete_is_excluded(self):
        p = {"workflow_runs": [make_run(1), make_run(2, status="in_progress")]}
        self.assertEqual(analyze(p, WORKFLOW)["n"], 1)

    def test_duplicate_run_id_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            analyze({"workflow_runs": [make_run(1), make_run(1)]}, WORKFLOW)

    def test_url_spoof_rejected(self):
        with self.assertRaisesRegex(ValueError, "URL"):
            analyze({"workflow_runs": [dict(make_run(1), html_url="bad")]}, WORKFLOW)

    def test_negative_queue_rejected(self):
        row = make_run(1)
        row["run_started_at"] = "2026-11-19T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "negative"):
            analyze({"workflow_runs": [row]}, WORKFLOW)

    def test_negative_wall_rejected(self):
        row = make_run(1)
        row["updated_at"] = "2026-11-19T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "negative"):
            analyze({"workflow_runs": [row]}, WORKFLOW)

    def test_invalid_sha_rejected(self):
        with self.assertRaisesRegex(ValueError, "SHA"):
            analyze({"workflow_runs": [dict(make_run(1), head_sha="123")]}, WORKFLOW)

    def test_missing_runs_response_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid GitHub"):
            analyze({"bad": []}, WORKFLOW)

    def test_insufficient_n_never_invents_speed(self):
        p = {"workflow_runs": [make_run(i) for i in range(1, 3)]}
        r = analyze(p, WORKFLOW)
        self.assertEqual(r["verdict"], "판단불가")
        self.assertIsNone(r["newer_vs_older_wall_pct"])

    def test_no_completed_matches(self):
        r = analyze({"workflow_runs": [make_run(1, status="queued")]}, WORKFLOW)
        self.assertEqual(r["n"], 0)
        self.assertEqual(r["verdict"], "판단불가")

    def test_zero_baseline_no_percentage(self):
        p = {"workflow_runs": [make_run(i, wall=0) for i in range(1, 7)]}
        self.assertIsNone(analyze(p, WORKFLOW)["newer_vs_older_wall_pct"])

    def test_invalid_window_rejected(self):
        with self.assertRaisesRegex(ValueError, "window"):
            analyze({"workflow_runs": []}, WORKFLOW, window=0)

    def test_model_claims_remain_unknown(self):
        r = analyze({"workflow_runs": [make_run(i) for i in range(1, 8)]}, WORKFLOW)
        self.assertFalse(r["gpu_training_verified"])
        self.assertFalse(r["adapter_created_verified"])
        self.assertIsNone(r["model_quality_change"])
        self.assertIsNone(r["retry_rate"])

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON"):
            json.loads('{"a":1,"a":2}', object_pairs_hook=unique)

    def test_cli_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "runs.json"
            src.write_text(json.dumps({"workflow_runs": [make_run(i) for i in range(1, 7)]}))
            run = subprocess.run([sys.executable,
                                  str(Path(__file__).resolve().parents[1] / "scripts" /
                                      "oril_v2_ci_cycle_trend_audit.py"),
                                  "--runs-json", str(src), "--workflow", WORKFLOW],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout)["n"], 6)


if __name__ == "__main__":
    unittest.main()
