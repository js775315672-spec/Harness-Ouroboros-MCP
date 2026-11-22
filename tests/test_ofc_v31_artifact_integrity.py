"""Offline archive-byte integrity and tamper tests, without GitHub credentials."""
import hashlib
import io
import unittest
import zipfile
from agent import cycle_registry as registry
from agent.artifact_integrity import verify_zip

REPO = "sample/independent"
SHA = "a" * 40
RUN = 91

def archive():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("evidence.json", '{"verified":true}')
    return out.getvalue()

class ArtifactIntegrity(unittest.TestCase):
    def setUp(self):
        self.data = archive()
        self.artifact = {
            "id": 17, "expired": False, "size_in_bytes": len(self.data),
            "digest": "sha256:" + hashlib.sha256(self.data).hexdigest(),
            "workflow_run": {"id": RUN, "head_sha": SHA},
        }
        self.calls = []

    def fetch(self, url):
        self.calls.append(url)
        return self.data

    def check(self, **kwargs):
        return verify_zip(self.artifact, repo=REPO, run_id=RUN,
                          head_sha=SHA, fetch=self.fetch, **kwargs)

    def test_valid_zip_hash_and_pinned_url(self):
        self.assertEqual(self.check(), self.artifact["digest"])
        self.assertEqual(self.calls, [
            f"https://api.github.com/repos/{REPO}/actions/artifacts/17/zip"])

    def test_tamper_detected(self):
        self.data = self.data[:-1] + bytes([self.data[-1] ^ 1])
        with self.assertRaises(registry.Blocked): self.check()

    def test_truncated_bytes_detected(self):
        self.data = self.data[:-4]
        with self.assertRaises(registry.Blocked): self.check()

    def test_missing_digest_blocks_before_download(self):
        self.artifact.pop("digest")
        with self.assertRaises(registry.Blocked): self.check()
        self.assertEqual(self.calls, [])

    def test_expired_archive_blocks(self):
        self.artifact["expired"] = True
        with self.assertRaises(registry.Blocked): self.check()

    def test_source_drift_blocks(self):
        self.artifact["workflow_run"]["head_sha"] = "b" * 40
        with self.assertRaises(registry.Blocked): self.check()

    def test_run_id_mismatch_blocks(self):
        self.artifact["workflow_run"]["id"] = RUN + 1
        with self.assertRaises(registry.Blocked): self.check()

    def test_nonzip_with_valid_digest_blocks(self):
        self.data = b"not-a-zip"
        self.artifact["size_in_bytes"] = len(self.data)
        self.artifact["digest"] = "sha256:" + hashlib.sha256(self.data).hexdigest()
        with self.assertRaises(registry.Blocked): self.check()

    def test_oversized_metadata_blocks_without_download(self):
        self.artifact["size_in_bytes"] = 999999999
        with self.assertRaises(registry.Blocked): self.check()
        self.assertEqual(self.calls, [])

    def test_network_failure_blocks(self):
        def fail(_): raise TimeoutError("offline")
        with self.assertRaises(registry.Blocked):
            verify_zip(self.artifact, repo=REPO, run_id=RUN,
                       head_sha=SHA, fetch=fail)

if __name__ == "__main__":
    unittest.main()
