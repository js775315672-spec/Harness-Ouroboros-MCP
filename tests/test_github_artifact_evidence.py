"""Mocked transport tests; live GitHub verification requires a read token."""
import io
import json
import unittest
from unittest.mock import patch
from agent.github_artifact_evidence import verify_actions_artifact

REPO = "owner/example"
HEAD = "a"*40
class Response(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *args): self.close()

def transport(*, conclusion="success", sha=HEAD, bound=42, expired=False, zip_bytes=b"PK\\x03\\x04example"):
    def open_url(req, timeout=30):
        url = req.full_url
        if url.endswith("/runs/42"):
            obj = {"repository":{"full_name":REPO},"head_sha":sha,
                   "status":"completed","conclusion":conclusion}
        elif url.endswith("/artifacts/7"):
            obj = {"workflow_run":{"id":bound},"expired":expired,"size_in_bytes":100}
        elif url.endswith("/artifacts/7/zip"):
            return Response(zip_bytes)
        else:
            raise AssertionError(url)
        return Response(json.dumps(obj).encode())
    return open_url

class EvidenceTests(unittest.TestCase):
    def call(self, **kwargs):
        return verify_actions_artifact(REPO,42,7,HEAD,"read-only-token",
            opener=transport(**kwargs))
    def test_verified_zip_digest(self):
        self.assertEqual(self.call()["run_conclusion"],"success")
        self.assertEqual(len(self.call()["zip_sha256"]),64)
    def test_reject_failed_or_wrong_head(self):
        for kwargs in ({"conclusion":"failure"},{"sha":"b"*40},
                       {"bound":99},{"expired":True},{"zip_bytes":b"forged"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(RuntimeError):
                self.call(**kwargs)
    def test_reject_missing_token(self):
        with self.assertRaises(RuntimeError):
            verify_actions_artifact(REPO,42,7,HEAD,"",opener=transport())

if __name__ == "__main__":
    unittest.main()
