import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_cpu_raw_latency_sidecar_audit import audit, load_json


def fixture():
    pairs = [
        {"order": "compact_first", "compact_elapsed_seconds": 1.1,
         "verbose_elapsed_seconds": 1.3, "compact_input_tokens": 5,
         "verbose_input_tokens": 10},
        {"order": "verbose_first", "compact_elapsed_seconds": 1.5,
         "verbose_elapsed_seconds": 1.6, "compact_input_tokens": 6,
         "verbose_input_tokens": 12},
    ]
    report = {
        "n_pairs": 2, "compact_elapsed_seconds_median": 1.3,
        "verbose_elapsed_seconds_median": 1.45,
        "paired_verbose_minus_compact_seconds_median": 0.15,
        "paired_elapsed_differences_seconds": [0.2, 0.1],
        "compact_input_tokens": [5, 6], "verbose_input_tokens": [10, 12],
        "input_token_reduction_pct_median": 50.0,
        "pair_orders": ["compact_first", "verbose_first"],
        "pair_order_observed": True,
        "pretrained_weights": False, "gpu_used": False, "optimizer_steps": 0,
        "lora_adapter_created": False, "independent_heldout_evaluation": False,
        "performance_gain_verified": False, "model_intelligence_gain": None,
    }
    digest = hashlib.sha256(json.dumps(report, sort_keys=True,
                          ensure_ascii=False, separators=(",", ":"),
                          allow_nan=False).encode()).hexdigest()
    sidecar = {"schema_version": 1, "report_sha256": digest,
               "measurement_kind": "synthetic_random_weight_qwen2_cpu_subprocess",
               "pairs": pairs}
    return report, sidecar


def bound(report, sidecar):
    sidecar["report_sha256"] = hashlib.sha256(json.dumps(
        report, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        allow_nan=False).encode()).hexdigest()


class RawLatencyAuditTests(unittest.TestCase):
    def test_all_medians_reconstructed(self):
        report, sidecar = fixture()
        result = audit(report, sidecar)
        self.assertTrue(result["individual_latency_medians_arithmetic_verified"])
        self.assertFalse(result["provenance_attested"])
        self.assertFalse(result["gpu_lora_verified"])
        self.assertIsNone(result["model_intelligence_gain"])

    def test_compact_median_forgery(self):
        report, sidecar = fixture()
        report["compact_elapsed_seconds_median"] = 0.1
        bound(report, sidecar)
        with self.assertRaisesRegex(ValueError, "compact_elapsed_seconds_median"):
            audit(report, sidecar)

    def test_verbose_median_forgery(self):
        report, sidecar = fixture()
        report["verbose_elapsed_seconds_median"] = 0.1
        bound(report, sidecar)
        with self.assertRaisesRegex(ValueError, "verbose_elapsed_seconds_median"):
            audit(report, sidecar)

    def test_paired_median_forgery(self):
        report, sidecar = fixture()
        report["paired_verbose_minus_compact_seconds_median"] = 9
        bound(report, sidecar)
        with self.assertRaisesRegex(ValueError, "paired_verbose_minus_compact"):
            audit(report, sidecar)

    def test_raw_pair_difference_mismatch(self):
        report, sidecar = fixture()
        report["paired_elapsed_differences_seconds"] = [0.5, 0.1]
        bound(report, sidecar)
        with self.assertRaisesRegex(ValueError, "paired latency differences"):
            audit(report, sidecar)

    def test_token_vector_forgery(self):
        report, sidecar = fixture()
        report["compact_input_tokens"] = [1, 6]
        bound(report, sidecar)
        with self.assertRaisesRegex(ValueError, "token vectors"):
            audit(report, sidecar)

    def test_order_forgery(self):
        report, sidecar = fixture()
        report["pair_orders"] = ["verbose_first", "compact_first"]
        bound(report, sidecar)
        with self.assertRaisesRegex(ValueError, "order differs"):
            audit(report, sidecar)

    def test_missing_raw_pair_rejected(self):
        report, sidecar = fixture()
        sidecar["pairs"].pop()
        with self.assertRaisesRegex(ValueError, "missing raw"):
            audit(report, sidecar)

    def test_raw_report_digest_mismatch(self):
        report, sidecar = fixture()
        sidecar["report_sha256"] = "a" * 64
        with self.assertRaisesRegex(ValueError, "SHA mismatch"):
            audit(report, sidecar)

    def test_fake_lora_claim(self):
        report, sidecar = fixture()
        report["optimizer_steps"] = 1
        bound(report, sidecar)
        with self.assertRaisesRegex(ValueError, "unsupported"):
            audit(report, sidecar)

    def test_invalid_nan_or_bool_elapsed(self):
        for invalid in (float("nan"), float("inf"), -1, True):
            with self.subTest(invalid=str(invalid)):
                report, sidecar = fixture()
                sidecar["pairs"][0]["compact_elapsed_seconds"] = invalid
                with self.assertRaisesRegex(ValueError, "raw numeric"):
                    audit(report, sidecar)

    def test_unbalanced_order_rejected(self):
        report, sidecar = fixture()
        sidecar["pairs"][1]["order"] = "compact_first"
        report["pair_orders"][1] = "compact_first"
        bound(report, sidecar)
        with self.assertRaisesRegex(ValueError, "unbalanced"):
            audit(report, sidecar)

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.json"
            p.write_text('{"n_pairs":2,"n_pairs":3}')
            with self.assertRaisesRegex(ValueError, "duplicate JSON"):
                load_json(p)

    def test_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.json"
            p.write_text('{"x":NaN}')
            with self.assertRaisesRegex(ValueError, "nonfinite"):
                load_json(p)

    def test_oversized_file_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.json"
            p.write_text(" " * 262145)
            with self.assertRaisesRegex(ValueError, "oversized"):
                load_json(p)


if __name__ == "__main__":
    unittest.main()
