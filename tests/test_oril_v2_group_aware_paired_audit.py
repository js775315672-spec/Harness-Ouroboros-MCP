import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_group_aware_paired_audit import group_audit
from oril_v2_paired_student_eval import evaluate

D = "a" * 64
A = "b" * 64
B = "c" * 64

def rows(n=40, *, model=A, token=100, correct=True, group=None):
    return [dict(task_id=f"t-{i}", group_id=(group if group is not None else f"g-{i}"),
                 dataset_sha256=D, model_sha256=model, seed=17,
                 correct=correct, input_tokens=token, output_tokens=20,
                 latency_ms=100.0) for i in range(n)]

class GroupAwareAuditTests(unittest.TestCase):
    def test_distinct_groups_40_25pct_savings_pass(self):
        a, b = rows(), rows(model=B, token=70)
        report = group_audit(a, b)
        self.assertEqual(report["independent_groups_proxy"], 40)
        self.assertEqual(report["token_reduction_pct"], 25)
        self.assertEqual(report["status"], "향상")
        self.assertFalse(report["independent_evaluation_attested"])
        self.assertFalse(report["model_quality_gain_attested"])

    def test_correlated_variants_fail_minimum_despite_40_rows(self):
        a, b = rows(group="family"), rows(model=B, token=70, group="family")
        self.assertEqual(evaluate(a, b)["status"], "향상")
        report = group_audit(a, b)
        self.assertEqual(report["independent_groups_proxy"], 1)
        self.assertEqual(report["max_rows_per_group"], 40)
        self.assertEqual(report["status"], "판단불가")
        self.assertFalse(report["quality_noninferiority_pass"])

    def test_case_variant_group_ids_are_same_group(self):
        a, b = rows(), rows(model=B, token=70)
        for i in range(40):
            a[i]["group_id"] = b[i]["group_id"] = "Family" if i % 2 else "family"
        self.assertEqual(group_audit(a, b)["independent_groups_proxy"], 1)

    def test_group_weighting_does_not_hide_regression(self):
        a, b = rows(39, group="large"), rows(39, model=B, token=70, group="large")
        a.append(dict(rows(1)[0], task_id="extra", group_id="small", correct=True))
        b.append(dict(rows(1, model=B, token=70)[0], task_id="extra", group_id="small", correct=False))
        report = group_audit(a, b, min_groups=2)
        self.assertEqual(report["group_mean_accuracy_delta"], -0.5)
        self.assertEqual(report["status"], "악화")

    def test_mismatched_dataset_rejected(self):
        a, b = rows(), rows(model=B)
        b[0]["dataset_sha256"] = "d" * 64
        with self.assertRaises(ValueError):
            group_audit(a, b)

    def test_unpaired_seed_rejected(self):
        a, b = rows(), rows(model=B)
        b[0]["seed"] = 22
        with self.assertRaisesRegex(ValueError, "mismatch"):
            group_audit(a, b)

    def test_mismatched_groups_rejected(self):
        a, b = rows(), rows(model=B)
        b[0]["group_id"] = "other"
        with self.assertRaisesRegex(ValueError, "mismatch"):
            group_audit(a, b)

    def test_duplicate_tasks_rejected(self):
        a, b = rows(), rows(model=B)
        a.append(dict(a[0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            group_audit(a, b)

    def test_nonfinite_and_bool_settings_rejected(self):
        a, b = rows(), rows(model=B)
        for settings in ({"min_groups": True}, {"samples": 0},
                         {"noninferiority_margin": float("nan")},
                         {"token_target": True}):
            with self.subTest(settings=settings):
                with self.assertRaisesRegex(ValueError, "settings"):
                    group_audit(a, b, **settings)

    def test_zero_token_baseline_is_unknown(self):
        a, b = rows(token=0), rows(model=B, token=0)
        for row in a+b:
            row["output_tokens"] = 0
        report = group_audit(a, b)
        self.assertIsNone(report["token_reduction_pct"])
        self.assertFalse(report["token_saving_pass"])

    def test_actual_regressions_fail_quality_gate(self):
        a, b = rows(), rows(model=B, token=70, correct=False)
        report = group_audit(a, b)
        self.assertEqual(report["status"], "악화")
        self.assertFalse(report["quality_noninferiority_pass"])

    def test_small_n_unknown(self):
        report = group_audit(rows(5), rows(5, model=B, token=70))
        self.assertEqual(report["status"], "판단불가")

    def test_reproducible_bootstrap(self):
        a, b = rows(), rows(model=B, token=70)
        b[0]["correct"] = False
        self.assertEqual(group_audit(a, b), group_audit(a, b))

    def test_cli_json_output_and_unattested_flags(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            ap, bp, op = root / "a.jsonl", root / "b.jsonl", root / "report.json"
            ap.write_text("".join(json.dumps(r)+"\n" for r in rows()))
            bp.write_text("".join(json.dumps(r)+"\n" for r in rows(model=B, token=70)))
            proc = subprocess.run([sys.executable,
                str(Path(__file__).resolve().parents[1] / "scripts" / "oril_v2_group_aware_paired_audit.py"),
                "--baseline", str(ap), "--candidate", str(bp), "--output", str(op)],
                capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            report = json.loads(op.read_text())
            self.assertEqual(report["independent_groups_proxy"], 40)
            self.assertFalse(report["gpu_training_attested"])

if __name__ == "__main__":
    unittest.main()
