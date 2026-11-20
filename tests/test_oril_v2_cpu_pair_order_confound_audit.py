import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_cpu_pair_order_confound_audit import stratified_order_audit


def evidence(diffs, orders):
    import statistics
    raw = []
    for d, order in zip(diffs, orders):
        raw.append({
            "order": order, "compact_elapsed_seconds": 1.0,
            "verbose_elapsed_seconds": 1.0 + d,
            "compact_input_tokens": 2, "verbose_input_tokens": 4,
        })
    report = {
        "n_pairs": len(diffs), "pair_order_observed": True,
        "pair_orders": orders,
        "compact_input_tokens": [2] * len(diffs),
        "verbose_input_tokens": [4] * len(diffs),
        "paired_elapsed_differences_seconds": diffs,
        "compact_elapsed_seconds_median": 1.0,
        "verbose_elapsed_seconds_median": round(statistics.median([1 + x for x in diffs]), 3),
        "paired_verbose_minus_compact_seconds_median": round(statistics.median(diffs), 3),
        "input_token_reduction_pct_median": 50.0,
        "pretrained_weights": False, "gpu_used": False,
        "optimizer_steps": 0, "lora_adapter_created": False,
        "independent_heldout_evaluation": False,
        "performance_gain_verified": False, "model_intelligence_gain": None,
    }
    canonical = json.dumps(report, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"), allow_nan=False)
    sidecar = {
        "schema_version": 1,
        "report_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "measurement_kind": "synthetic_random_weight_qwen2_cpu_subprocess",
        "pairs": raw,
    }
    return report, sidecar


class OrderAuditTests(unittest.TestCase):
    def test_consistent_positive_sign_not_verified_speed(self):
        report, sidecar = evidence([0.3, 0.2, 0.4, 0.1],
            ["compact_first", "verbose_first"] * 2)
        r = stratified_order_audit(report, sidecar)
        self.assertTrue(r["both_orders_replicated"])
        self.assertTrue(r["order_direction_consistent"])
        self.assertFalse(r["latency_gain_verified"])
        self.assertIsNone(r["pretrained_model_quality_gain"])

    def test_order_confounded_opposite_signs(self):
        report, sidecar = evidence([0.4, -0.3, 0.2, -0.1],
            ["compact_first", "verbose_first"] * 2)
        r = stratified_order_audit(report, sidecar)
        self.assertFalse(r["order_direction_consistent"])
        self.assertEqual(r["counts"], {"compact_first": 2, "verbose_first": 2})

    def test_insufficient_strata_never_assumes_direction(self):
        report, sidecar = evidence([0.1, 0.2],
            ["compact_first", "verbose_first"])
        r = stratified_order_audit(report, sidecar)
        self.assertFalse(r["both_orders_replicated"])
        self.assertIsNone(r["order_direction_consistent"])

    def test_all_zero_not_positive_speed(self):
        report, sidecar = evidence([0, 0, 0, 0],
            ["compact_first", "verbose_first"] * 2)
        r = stratified_order_audit(report, sidecar)
        self.assertFalse(r["order_direction_consistent"])

    def test_tampered_report_rejected(self):
        report, sidecar = evidence([0.1, 0.2, 0.3, 0.4],
            ["compact_first", "verbose_first"] * 2)
        report["compact_elapsed_seconds_median"] = 100
        with self.assertRaisesRegex(ValueError, "SHA mismatch"):
            stratified_order_audit(report, sidecar)

    def test_self_consistent_forgery_is_not_attested(self):
        report, sidecar = evidence([0.1, 0.2, 0.3, 0.4],
            ["compact_first", "verbose_first"] * 2)
        r = stratified_order_audit(report, sidecar)
        self.assertFalse(r["provenance_attested"])
        self.assertFalse(r["lora_training_verified"])

    def test_invalid_negative_elapsed_rejected(self):
        report, sidecar = evidence([-1.1, 0.2, 0.3, 0.4],
            ["compact_first", "verbose_first"] * 2)
        with self.assertRaisesRegex(ValueError, "negative or zero"):
            stratified_order_audit(report, sidecar)

    def test_invalid_unbalanced_order_rejected(self):
        report, sidecar = evidence([0.1, 0.2, 0.3, 0.4],
            ["compact_first"] * 4)
        with self.assertRaisesRegex(ValueError, "unbalanced"):
            stratified_order_audit(report, sidecar)


if __name__ == "__main__":
    unittest.main()
