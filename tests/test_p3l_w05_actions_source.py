"""GitHub Actions metadata and archive checks for independent model replay."""
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import p3l_w05_actions_source as source

HEAD = "a" * 40
BASE = f"repos/{source.REPOSITORY}/actions"
RUN = f"{BASE}/runs/123"
JOBS = f"{RUN}/attempts/1/jobs?per_page=100"
ARTIFACT = f"{BASE}/artifacts/456"


def fixture():
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("model-output.json", '{"run_id": 123}')
        zipped.writestr("model-provenance.json", json.dumps({
            "model": "7b", "revision": source.QWEN_REVISION,
            "sha256": source.QWEN_WEIGHTS_SHA256, "secret_or_paid_api_used": False,
        }))
    data = archive.getvalue()
    return {
        RUN: {
            "id": 123, "run_attempt": 1, "path": source.WORKFLOW,
            "event": "pull_request", "head_sha": HEAD, "head_branch": "reviewed",
            "repository": {"id": 42, "full_name": source.REPOSITORY},
            "head_repository": {"full_name": source.REPOSITORY},
        },
        JOBS: {"total_count": 1, "jobs": [{
            "id": 789, "run_id": 123, "name": "actual_qwen_model", "head_sha": HEAD,
            "status": "completed", "conclusion": "success", "steps": [{
                "name": "Keep raw model output and provenance on pass or failure",
                "status": "completed", "conclusion": "success",
            }],
        }]},
        ARTIFACT: {
            "id": 456, "name": "p3l-w06-raw-model-output", "expired": False,
            "size_in_bytes": len(data), "digest": f"sha256:{hashlib.sha256(data).hexdigest()}",
            "workflow_run": {"id": 123, "head_branch": "reviewed", "head_sha": HEAD,
                             "repository_id": 42, "head_repository_id": 42},
        },
        ARTIFACT + "/zip": data,
    }


class GitHubActionsSourceTests(unittest.TestCase):
    def read(self, responses):
        def fetch(path):
            data = responses[path]
            return data if type(data) is bytes else json.dumps(data).encode()

        return source.read_model_archive(123, HEAD, 456, fetch=fetch)

    def test_expected_archive_is_bound_to_external_run_and_job(self):
        receipt, origin = self.read(fixture())
        self.assertEqual(receipt["run_id"], 123)
        self.assertEqual(origin["model_job_id"], 789)
        self.assertEqual(origin["head_sha"], HEAD)

    def test_wrong_workflow_head_and_retry_are_blocked(self):
        for key, value in (("head_sha", "b" * 40), ("path", "other.yml"),
                           ("run_attempt", True), ("run_attempt", 2), ("id", 123.0)):
            responses = fixture()
            responses[RUN][key] = value
            with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, "workflow run"):
                self.read(responses)

    def test_wrong_job_or_unsuccessful_upload_is_blocked(self):
        responses = fixture()
        responses[JOBS]["jobs"][0]["run_id"] = 456
        with self.assertRaisesRegex(ValueError, "model job"):
            self.read(responses)
        responses = fixture()
        responses[JOBS]["jobs"][0]["steps"][0]["conclusion"] = "skipped"
        with self.assertRaisesRegex(ValueError, "upload"):
            self.read(responses)

    def test_cross_run_and_cross_repository_artifacts_are_blocked(self):
        for key, value in (("id", 456), ("repository_id", 42.0), ("head_repository_id", 43),
                           ("head_sha", "b" * 40)):
            responses = fixture()
            responses[ARTIFACT]["workflow_run"][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "artifact source"):
                self.read(responses)

    def test_zip_with_forged_bytes_is_blocked(self):
        responses = fixture()
        responses[ARTIFACT + "/zip"] = responses[ARTIFACT + "/zip"][:-1] + b"a"
        with self.assertRaisesRegex(ValueError, "artifact bytes"):
            self.read(responses)
