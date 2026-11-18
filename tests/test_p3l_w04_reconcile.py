"""Exercise duplicate, late, and invalid completion deliveries against a real registry."""
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from p3l_w04_attempt_registry import AttemptBlocked, AttemptInput, AttemptRegistry
from p3l_w04_reconcile import reconcile
from p3l_w05_actions_source import LLAMA_REVISION, QWEN_REVISION, QWEN_WEIGHTS_SHA256
from test_p3l_w05_actions_source import ARTIFACT, HEAD, JOBS, fixture

TASK = AttemptInput("ledger-text", "b" * 64, "1" * 40, HEAD, QWEN_REVISION,
                    QWEN_WEIGHTS_SHA256, "c" * 64, "d" * 64)


def responses(*, prompt=TASK.prompt_sha256):
    data = fixture()
    archive = io.BytesIO()
    raw = "def validate(records):\n    return len(records)\n"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("model-output.json", json.dumps({
            "schema": "p3l-w06-one-shot-output-v1", "runner_role": "model_inference",
            "run_id": 123, "model_calls": 1, "merge_authorized": False,
            "prompt_sha256": prompt, "raw_response": raw,
            "raw_response_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        }))
        zipped.writestr("model-provenance.json", json.dumps({
            "model": "7b", "revision": QWEN_REVISION, "sha256": QWEN_WEIGHTS_SHA256,
            "secret_or_paid_api_used": False, "llama_cpp_revision": LLAMA_REVISION,
            "prompt_sha256": prompt, "inference_config_sha256": TASK.inference_config_sha256,
            "llama_binary_sha256": "e" * 64,
        }))
    payload = archive.getvalue()
    data[ARTIFACT + "/zip"] = payload
    data[ARTIFACT].update(size_in_bytes=len(payload),
                          digest=f"sha256:{hashlib.sha256(payload).hexdigest()}")
    return data


class AttemptReconcileTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "attempts.sqlite3"
        self.now = 100
        self.registry = AttemptRegistry(self.path, clock=lambda: self.now)
        self.lease = self.registry.reserve(TASK, "runner-a", ttl_seconds=5)
        self.registry.start(self.lease, observed_head=TASK.head_sha, run_id=123)

    def deliver(self, data, *, run_id=123):
        def fetch(path):
            value = data[path]
            return value if type(value) is bytes else json.dumps(value).encode()

        reconcile(self.registry, TASK, self.lease, run_id=run_id, artifact_id=456, fetch=fetch)

    def test_late_duplicate_delivery_records_one_artifact_after_restart(self):
        self.now = 106
        self.registry = AttemptRegistry(self.path, clock=lambda: self.now)
        self.assertEqual(self.registry.status(TASK)["state"], "UNVERIFIED")
        data = responses()
        self.deliver(data)
        saved = self.registry.status(TASK)
        self.deliver(data)
        self.assertEqual(self.registry.status(TASK), saved)
        self.assertEqual(saved["state"], "MODEL_GENERATED")
        self.assertEqual(saved["receipt_sha256"], data[ARTIFACT]["digest"].split(":")[1])
        with self.assertRaises(AttemptBlocked):
            self.registry.reserve(replace(TASK, prompt_sha256="f" * 64), "runner-b", ttl_seconds=5)

    def test_wrong_run_and_wrong_prompt_do_not_record_a_receipt(self):
        with self.assertRaises(AttemptBlocked):
            self.deliver({}, run_id=124)
        with self.assertRaisesRegex(AttemptBlocked, "does not match the admitted inputs"):
            self.deliver(responses(prompt="f" * 64))
        self.assertEqual(self.registry.status(TASK)["state"], "STARTED")

    def test_incomplete_remote_job_remains_unverified_after_expiry(self):
        self.now = 106
        data = responses()
        data[JOBS]["jobs"][0]["status"] = "in_progress"
        with self.assertRaisesRegex(ValueError, "did not complete successfully"):
            self.deliver(data)
        self.assertEqual(self.registry.status(TASK)["state"], "UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
