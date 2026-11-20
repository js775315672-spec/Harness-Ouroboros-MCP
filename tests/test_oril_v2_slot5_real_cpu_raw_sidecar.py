"""Contract tests for raw timings collected during actual paired invoke calls."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import oril_v2_tiny_qwen_cpu_paired_benchmark as benchmark
from oril_v2_cpu_raw_latency_sidecar_audit import audit


class RawIntegration(unittest.TestCase):
    def fake_invoke(self, adapter, model_dir, question):
        short = question == benchmark.SHORT
        return {
            "input_tokens": 4 if short else 15,
            "output_tokens": 2,
            "elapsed_seconds": 0.25 if short else 0.75,
        }

    def test_invoke_raw_values_and_independent_auditor(self):
        with patch.object(benchmark, "build_tiny_checkpoint", return_value="a" * 64), \
             patch.object(benchmark, "invoke", side_effect=self.fake_invoke) as call:
            report, sidecar = benchmark.run(n_pairs=6, include_raw=True)
        self.assertEqual(call.call_count, 12)
        self.assertEqual(report["pair_orders"], ["compact_first", "verbose_first"] * 3)
        self.assertEqual(len(sidecar["pairs"]), 6)
        self.assertEqual(sidecar["pairs"][0]["compact_elapsed_seconds"], 0.25)
        self.assertEqual(sidecar["pairs"][0]["verbose_elapsed_seconds"], 0.75)
        self.assertTrue(audit(report, sidecar)["individual_latency_medians_arithmetic_verified"])
        self.assertFalse(audit(report, sidecar)["provenance_attested"])

    def test_tampered_raw_latency_rejected(self):
        with patch.object(benchmark, "build_tiny_checkpoint", return_value="a" * 64), \
             patch.object(benchmark, "invoke", side_effect=self.fake_invoke):
            report, sidecar = benchmark.run(n_pairs=6, include_raw=True)
        sidecar["pairs"][0]["compact_elapsed_seconds"] += 0.1
        with self.assertRaises(ValueError):
            audit(report, sidecar)

    def test_tampered_report_hash_rejected(self):
        with patch.object(benchmark, "build_tiny_checkpoint", return_value="a" * 64), \
             patch.object(benchmark, "invoke", side_effect=self.fake_invoke):
            report, sidecar = benchmark.run(n_pairs=6, include_raw=True)
        report["n_real_generations"] = 500
        with self.assertRaisesRegex(ValueError, "SHA mismatch"):
            audit(report, sidecar)

    def test_legacy_summary_still_works(self):
        with patch.object(benchmark, "build_tiny_checkpoint", return_value="a" * 64), \
             patch.object(benchmark, "invoke", side_effect=self.fake_invoke):
            report = benchmark.run(n_pairs=2)
        self.assertIsInstance(report, dict)
        self.assertEqual(report["n_real_generations"], 4)

    def test_order_is_recorded_from_actual_call_sequence(self):
        calls = []
        def track(adapter, model_dir, question):
            calls.append("compact" if question == benchmark.SHORT else "verbose")
            return self.fake_invoke(adapter, model_dir, question)
        with patch.object(benchmark, "build_tiny_checkpoint", return_value="a" * 64), \
             patch.object(benchmark, "invoke", side_effect=track):
            report, sidecar = benchmark.run(n_pairs=4, include_raw=True)
        self.assertEqual(calls, ["compact", "verbose", "verbose", "compact"] * 2)
        self.assertEqual([x["order"] for x in sidecar["pairs"]],
                         ["compact_first", "verbose_first"] * 2)

    def test_no_model_quality_or_lora_claims(self):
        with patch.object(benchmark, "build_tiny_checkpoint", return_value="a" * 64), \
             patch.object(benchmark, "invoke", side_effect=self.fake_invoke):
            report, sidecar = benchmark.run(n_pairs=2, include_raw=True)
        self.assertFalse(report["gpu_used"])
        self.assertFalse(report["pretrained_weights"])
        self.assertFalse(report["lora_adapter_created"])
        self.assertIsNone(report["model_intelligence_gain"])
        self.assertFalse(audit(report, sidecar)["gpu_lora_verified"])


if __name__ == "__main__":
    unittest.main()
