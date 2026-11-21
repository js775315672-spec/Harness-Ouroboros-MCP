"""Cross-run consistency tests; mocks only for upstream auditors.

The real upstream independent audits run before reconciliation in production.
"""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_slot5_public_ab_aa_reconciliation import reconcile, read_unique

WEIGHT = [{"name": "model.safetensors", "bytes": 100, "sha256": "a"*64}]


def fixtures():
    common = {"model_id": "Qwen/Qwen2.5-0.5B-Instruct",
              "resolved_revision": "b"*40, "public_tasks_sha256": "c"*64,
              "weight_files": copy.deepcopy(WEIGHT)}
    ab = {**copy.deepcopy(common), "rows": []}
    aa = {**copy.deepcopy(common), "rows": []}
    for i in range(30):
        group = {"group_id": f"public-arithmetic-{i+1:02d}",
                 "question": f"Question {i}", "expected": str(i)}
        a = {"variant": "compact", "input_tokens": 12, "elapsed_seconds": 1.0,
             "output": str(i)}
        b = {"variant": "verbose", "input_tokens": 24, "elapsed_seconds": 1.2,
             "output": str(i)}
        ab["rows"].append({**group, "observations": [a, b]})
        aa["rows"].append({**group, "observations": [
            {**a, "elapsed_seconds": 1.05},
            {**a, "elapsed_seconds": 1.15},
        ]})
    return ab, aa


def checked(ab, aa):
    with patch("oril_v2_slot5_public_ab_aa_reconciliation.audit_ab",
               return_value={"raw_calls": 60, "token_saving_pct_descriptive": 50.0}), \
         patch("oril_v2_slot5_public_ab_aa_reconciliation.audit_aa",
               return_value={"reported_calls": 60}):
        return reconcile(ab, aa)


class CrossRunTests(unittest.TestCase):
    def test_valid_comparison_is_not_speed_claim(self):
        result = checked(*fixtures())
        self.assertEqual(result["public_groups"], 30)
        self.assertEqual(result["ab_reported_calls"], 60)
        self.assertEqual(result["aa_reported_calls"], 60)
        self.assertEqual(result["ab_compact_minus_verbose_median_seconds"], -0.2)
        self.assertEqual(result["aa_absolute_pair_drift_median_seconds"], 0.1)
        self.assertEqual(result["ab_delta_to_aa_drift_ratio_descriptive"], 2.0)
        self.assertFalse(result["causal_speed_gain_proven"])
        self.assertFalse(result["independent_heldout_quality_proven"])
        self.assertFalse(result["student_weights_updated"])
        self.assertEqual(result["decision"], "판단불가")

    def test_revision_mismatch_rejected(self):
        a, b = fixtures()
        b["resolved_revision"] = "d"*40
        with self.assertRaisesRegex(ValueError, "revision"):
            checked(a, b)

    def test_model_mismatch_rejected(self):
        a, b = fixtures()
        b["model_id"] = "another"
        with self.assertRaisesRegex(ValueError, "model_id"):
            checked(a, b)

    def test_task_hash_mismatch_rejected(self):
        a, b = fixtures()
        b["public_tasks_sha256"] = "f"*64
        with self.assertRaisesRegex(ValueError, "public_tasks"):
            checked(a, b)

    def test_weight_hash_mismatch_rejected(self):
        a, b = fixtures()
        b["weight_files"][0]["sha256"] = "e"*64
        with self.assertRaisesRegex(ValueError, "weight hashes"):
            checked(a, b)

    def test_weight_duplicate_rejected(self):
        a, b = fixtures()
        b["weight_files"].append(copy.deepcopy(b["weight_files"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate weight"):
            checked(a, b)

    def test_group_reorder_rejected(self):
        a, b = fixtures()
        b["rows"].reverse()
        with self.assertRaisesRegex(ValueError, "group mismatch"):
            checked(a, b)

    def test_tokenization_drift_rejected(self):
        a, b = fixtures()
        b["rows"][0]["observations"][0]["input_tokens"] = 13
        with self.assertRaisesRegex(ValueError, "tokenization drift"):
            checked(a, b)

    def test_missing_variant_rejected(self):
        a, b = fixtures()
        a["rows"][0]["observations"][1]["variant"] = "compact"
        with self.assertRaisesRegex(ValueError, "variants"):
            checked(a, b)

    def test_zero_null_drift_is_unknown_not_infinity(self):
        a, b = fixtures()
        for row in b["rows"]:
            row["observations"][1]["elapsed_seconds"] = row["observations"][0]["elapsed_seconds"]
        result = checked(a, b)
        self.assertIsNone(result["ab_delta_to_aa_drift_ratio_descriptive"])

    def test_upstream_audit_failure_propagates(self):
        a, b = fixtures()
        with patch("oril_v2_slot5_public_ab_aa_reconciliation.audit_ab",
                   side_effect=ValueError("raw summary invalid")):
            with self.assertRaisesRegex(ValueError, "raw summary invalid"):
                reconcile(a, b)

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "raw.json"
            p.write_text('{"a":1,"a":2}')
            with self.assertRaisesRegex(ValueError, "duplicate JSON"):
                read_unique(p)


if __name__ == "__main__":
    unittest.main()
