"""End-to-end CLI checks with independent sha256sum oracle on Linux CI.

Unlike the bridge unit tests, these spawn the actual CLI process with the
three pinned validators installed by the integration workflow.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def sha256sum(path):
    result = subprocess.run(["sha256sum", str(path)], check=True,
                            capture_output=True, text=True)
    return result.stdout.split()[0]


class DatasetBridgeCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest = {"schema_version": 1, "splits": {}}
        for split in ("train", "validation", "test"):
            path = self.root / (split + ".txt")
            path.write_bytes(("sample " + split).encode("utf-8"))
            self.manifest["splits"][split] = [{
                "sample_id": split,
                "content_sha256": sha256sum(path),
                "group_id": "group-" + split,
                "source_id": "source-" + split,
                "relative_path": path.name,
            }]
        self.path = self.root / "manifest.json"

    def invoke(self, expected=None):
        raw = json.dumps(self.manifest, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False)
        self.path.write_text(raw, encoding="utf-8")
        expected = expected if expected is not None else hashlib.sha256(raw.encode()).hexdigest()
        return subprocess.run(
            [sys.executable, "-m", "scripts.oril_v2_dataset_contract_bridge",
             str(self.path), "--root", str(self.root), "--expected-sha256", expected],
            capture_output=True, text=True, check=False)

    def test_cli_pass_matches_external_sha256sum(self):
        proc = self.invoke()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "pass")
        self.assertFalse(result["training_approved"])
        self.assertFalse(result["promotion_approved"])
        for split in ("train", "validation", "test"):
            item = self.manifest["splits"][split][0]
            self.assertEqual(item["content_sha256"], sha256sum(self.root / item["relative_path"]))

    def test_cli_rejects_tampered_raw_bytes(self):
        (self.root / "test.txt").write_bytes(b"tampered")
        proc = self.invoke()
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["failed_stage"], "raw_sample_integrity")

    def test_cli_rejects_wrong_manifest_pin(self):
        proc = self.invoke(expected="0" * 64)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["failed_stage"], "manifest_pin")

    def test_cli_rejects_cross_split_duplicate_content(self):
        train = self.manifest["splits"]["train"][0]
        test = self.manifest["splits"]["test"][0]
        test["content_sha256"] = train["content_sha256"]
        test["relative_path"] = train["relative_path"]
        proc = self.invoke()
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["failed_stage"], "split_integrity")

    def test_cli_rejects_path_traversal(self):
        self.manifest["splits"]["test"][0]["relative_path"] = "../outside.txt"
        proc = self.invoke()
        self.assertNotEqual(proc.returncode, 0)
        # Strict validation may raise ValueError rather than emit a JSON failure.
        self.assertTrue("ValueError" in proc.stderr or
                        (proc.stdout and json.loads(proc.stdout).get("status") == "fail"))


if __name__ == "__main__":
    unittest.main()
