"""Synthetic tests: arithmetic diagnostic, NOT actual pretrained inference."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_cpu_noise_calibrated_diagnostic import diagnose
from oril_v2_tiny_qwen_cpu_paired_benchmark import summarize
from oril_v2_cpu_same_prompt_negative_control import summarize_negative_control

SHA = "a" * 64


def fixtures(effect=0.2, noise=0.05):
    pairs = []
    raw = []
    null_pairs = []
    for i in range(6):
        order = "compact_first" if i % 2 == 0 else "verbose_first"
        pairs.append({
            "compact": {"input_tokens": 5, "output_tokens": 2, "elapsed_seconds": 1.0},
            "verbose": {"input_tokens": 10, "output_tokens": 2,
                        "elapsed_seconds": 1.0 + effect},
        })
        raw.append({
            "order": order, "compact_elapsed_seconds": 1.0,
            "verbose_elapsed_seconds": 1.0 + effect,
            "compact_input_tokens": 5, "verbose_input_tokens": 10,
        })
        null_pairs.append({
            "order": "a_first" if i % 2 == 0 else "b_first",
            "a": {"input_tokens": 5, "output_tokens": 2, "elapsed_seconds": 1.0},
            "b": {"input_tokens": 5, "output_tokens": 2,
                  "elapsed_seconds": 1.0 + noise},
        })
    report = summarize(pairs, SHA, observed_orders=[r["order"] for r in raw])
    canonical = json.dumps(report, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"), allow_nan=False)
    sidecar = {
        "schema_version": 1,
        "measurement_kind": "synthetic_random_weight_qwen2_cpu_subprocess",
        "report_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "pairs": raw,
    }
    null = summarize_negative_control(null_pairs)
    null["config_sha256"] = SHA
    return report, sidecar, null


class NoiseCalibratedTests(unittest.TestCase):
    def test_null_noise_larger_than_effect_blocks_speed_claim(self):
        r = diagnose(*fixtures(effect=.1, noise=.3))
        self.assertTrue(r["noise_could_explain_observed_effect"])
        self.assertFalse(r["speed_gain_verified"])

    def test_larger_effect_is_only_diagnostic_not_speed_proof(self):
        r = diagnose(*fixtures(effect=.4, noise=.1))
        self.assertTrue(r["effect_exceeds_observed_null_max"])
        self.assertFalse(r["speed_gain_verified"])
        self.assertFalse(r["causal_interpretation_permitted"])

    def test_negative_effect_not_speed(self):
        r = diagnose(*fixtures(effect=-.2, noise=.1))
        self.assertTrue(r["noise_could_explain_observed_effect"])

    def test_equal_effect_is_not_exceeding(self):
        r = diagnose(*fixtures(effect=.2, noise=.2))
        self.assertFalse(r["effect_exceeds_observed_null_max"])

    def test_config_mismatch_rejected(self):
        a, b, c = fixtures()
        c["config_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "checkpoint"):
            diagnose(a, b, c)

    def test_missing_config_rejected(self):
        a, b, c = fixtures()
        del c["config_sha256"]
        with self.assertRaisesRegex(ValueError, "checkpoint"):
            diagnose(a, b, c)

    def test_corrupt_paired_sidecar_rejected(self):
        a, b, c = fixtures()
        b["pairs"][0]["compact_elapsed_seconds"] = 999
        with self.assertRaises(ValueError):
            diagnose(a, b, c)

    def test_corrupt_null_summary_rejected(self):
        a, b, c = fixtures()
        c["b_minus_a_seconds_median"] = 999
        with self.assertRaises(ValueError):
            diagnose(a, b, c)

    def test_forged_training_claim_rejected(self):
        a, b, c = fixtures()
        a["gpu_used"] = True
        with self.assertRaises(ValueError):
            diagnose(a, b, c)

    def test_forged_null_speed_claim_rejected(self):
        a, b, c = fixtures()
        c["speed_gain_verified"] = True
        with self.assertRaises(ValueError):
            diagnose(a, b, c)

    def test_wrong_experiment_rejected(self):
        a, b, c = fixtures()
        a["experiment"] = "not a Qwen experiment"
        canonical = json.dumps(a, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":"), allow_nan=False)
        b["report_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
        with self.assertRaisesRegex(ValueError, "wrong paired"):
            diagnose(a, b, c)

    def test_both_runs_remain_unverified_for_intelligence(self):
        r = diagnose(*fixtures())
        self.assertIsNone(r["model_intelligence_improved"])
        self.assertFalse(r["heldout_quality_verified"])
        self.assertFalse(r["gpu_lora_verified"])
        self.assertEqual((r["paired_n"], r["null_n"]), (6, 6))


if __name__ == "__main__":
    unittest.main()
