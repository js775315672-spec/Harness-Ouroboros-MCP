"""Synthetic evidence audit: test contracts, never claim real training."""
import copy
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from oril_v2_training_evidence_audit import check


class TrainingEvidenceAuditTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        (self.root / "artifacts").mkdir()
        self.adapter = self.root / "artifacts" / "adapter.bin"
        self.adapter.write_bytes(b"synthetic-not-a-real-model")
        self.evidence = self.root / "evidence.json"
        h = lambda b: hashlib.sha256(b).hexdigest()
        self.doc = {
            "schema_version": 1, "run_id": "synthetic-run",
            "model_id": "synthetic-model", "base_model_sha256": h(b"base"),
            "dataset_sha256": h(b"dataset"),
            "gpu": {"device_name": "synthetic-GPU", "cuda_available": True,
                    "training_steps": 2, "duration_seconds": 1.5,
                    "log_sha256": h(b"synthetic-log")},
            "adapter": {"path": "artifacts/adapter.bin",
                        "sha256": h(self.adapter.read_bytes()),
                        "size_bytes": self.adapter.stat().st_size},
            "evaluation": {"dataset_sha256": h(b"dataset"), "split": "heldout",
                           "metric": "accuracy", "direction": "higher",
                           "baseline": 0.5, "candidate": 0.6,
                           "sample_count": 50, "evaluator_sha256": h(b"eval")},
        }
        self.write()

    def write(self):
        self.evidence.write_text(json.dumps(self.doc), encoding="utf-8")

    def result(self):
        return check(self.root, self.evidence)

    def test_consistent_synthetic_evidence_is_not_independent_proof(self):
        r = self.result()
        self.assertTrue(r["evidence_consistent"], r)
        self.assertTrue(r["artifact_verified"], r)
        self.assertAlmostEqual(r["claimed_metric_gain"], 0.1)
        for k in ("gpu_execution_attested", "independent_evaluation_verified",
                  "intelligence_improved", "training_approved", "promotion_approved"):
            self.assertFalse(r[k], k)

    def test_missing_adapter_rejected(self):
        self.adapter.unlink()
        self.assertFalse(self.result()["evidence_consistent"])

    def test_changed_adapter_hash_rejected(self):
        self.adapter.write_bytes(b"tampered")
        self.assertFalse(self.result()["evidence_consistent"])

    def test_symlink_adapter_rejected(self):
        other = self.root / "other.bin"
        other.write_bytes(self.adapter.read_bytes())
        self.adapter.unlink()
        self.adapter.symlink_to(other)
        self.assertFalse(self.result()["evidence_consistent"])

    def test_adapter_path_escape_rejected(self):
        self.doc["adapter"]["path"] = "../outside"
        self.write()
        self.assertFalse(self.result()["evidence_consistent"])

    def test_boolean_steps_rejected(self):
        self.doc["gpu"]["training_steps"] = True
        self.write()
        self.assertFalse(self.result()["evidence_consistent"])

    def test_no_cuda_rejected(self):
        self.doc["gpu"]["cuda_available"] = False
        self.write()
        self.assertFalse(self.result()["evidence_consistent"])

    def test_missing_gpu_log_digest_rejected(self):
        self.doc["gpu"]["log_sha256"] = ""
        self.write()
        self.assertFalse(self.result()["evidence_consistent"])

    def test_evaluation_not_heldout_rejected(self):
        self.doc["evaluation"]["split"] = "train"
        self.write()
        self.assertFalse(self.result()["evidence_consistent"])

    def test_evaluation_dataset_mismatch_rejected(self):
        self.doc["evaluation"]["dataset_sha256"] = "f" * 64
        self.write()
        self.assertFalse(self.result()["evidence_consistent"])

    def test_small_sample_rejected(self):
        self.doc["evaluation"]["sample_count"] = 3
        self.write()
        self.assertFalse(self.result()["evidence_consistent"])

    def test_nonfinite_metric_rejected(self):
        self.evidence.write_text(json.dumps(self.doc).replace('"candidate": 0.6', '"candidate": NaN'))
        self.assertFalse(self.result()["evidence_consistent"])

    def test_duplicate_json_key_rejected(self):
        self.evidence.write_text(json.dumps(self.doc)[:-1] + ',"run_id":"fake"}')
        self.assertFalse(self.result()["evidence_consistent"])

    def test_boolean_schema_rejected(self):
        self.doc["schema_version"] = True
        self.write()
        self.assertFalse(self.result()["evidence_consistent"])

    def test_fake_better_score_does_not_approve_model(self):
        self.doc["evaluation"]["candidate"] = 0.99
        self.write()
        r = self.result()
        self.assertTrue(r["evidence_consistent"])
        self.assertFalse(r["intelligence_improved"])
        self.assertFalse(r["independent_evaluation_verified"])

    def test_cli_exit_code(self):
        args = [sys.executable, str(ROOT / "scripts/oril_v2_training_evidence_audit.py"),
                "--root", str(self.root), "--evidence", str(self.evidence)]
        r = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.adapter.unlink()
        r = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout)


if __name__ == "__main__":
    unittest.main()
