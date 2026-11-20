"""External manifest pin must remain fixed across content and metadata tampering.

The original CLI suite recalculates its expected hash on each invocation.
This independent negative suite freezes the baseline pin before any mutation.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class FrozenExternalPinTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.manifest = {"schema_version": 1, "splits": {}}
        for split in ("train", "validation", "test"):
            name = split + ".txt"
            payload = ("original-" + split).encode()
            (self.root / name).write_bytes(payload)
            self.manifest["splits"][split] = [{
                "sample_id": split, "content_sha256": hashlib.sha256(payload).hexdigest(),
                "group_id": "group-" + split, "source_id": "source-" + split,
                "relative_path": name,
            }]
        self.path = self.root / "manifest.json"
        self._write()
        self.frozen_pin = hashlib.sha256(self.path.read_bytes()).hexdigest()

    def _write(self):
        self.path.write_text(json.dumps(self.manifest, ensure_ascii=False,
                             sort_keys=True, separators=(",", ":"), allow_nan=False),
                             encoding="utf-8")

    def _invoke(self, pin):
        return subprocess.run([
            sys.executable, "-m", "scripts.oril_v2_dataset_contract_bridge",
            str(self.path), "--root", str(self.root), "--expected-sha256", pin,
        ], capture_output=True, text=True, check=False)

    def test_frozen_pin_allows_original_manifest(self):
        result = self._invoke(self.frozen_pin)
        self.assertEqual(result.returncode, 0, result.stderr)
        parsed = json.loads(result.stdout)
        self.assertEqual(parsed["status"], "pass")
        self.assertFalse(parsed["training_approved"])

    def test_rehashed_tampered_raw_sample_still_fails_frozen_pin(self):
        payload = b"tampered-and-rehashed"
        (self.root / "test.txt").write_bytes(payload)
        self.manifest["splits"]["test"][0]["content_sha256"] = hashlib.sha256(payload).hexdigest()
        self._write()
        result = self._invoke(self.frozen_pin)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["failed_stage"], "manifest_pin")

    def test_metadata_change_fails_frozen_pin(self):
        self.manifest["splits"]["test"][0]["source_id"] = "changed-source"
        self._write()
        result = self._invoke(self.frozen_pin)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["failed_stage"], "manifest_pin")

    def test_self_recomputed_pin_is_not_independent_attestation(self):
        self.manifest["splits"]["test"][0]["source_id"] = "changed-source"
        self._write()
        forged_pin = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.assertNotEqual(forged_pin, self.frozen_pin)
        result = self._invoke(forged_pin)
        self.assertEqual(result.returncode, 0, result.stderr)
        parsed = json.loads(result.stdout)
        self.assertEqual(parsed["dataset_provenance"], "unverified")
        self.assertFalse(parsed["training_approved"])
        self.assertFalse(parsed["promotion_approved"])


if __name__ == "__main__":
    unittest.main()
