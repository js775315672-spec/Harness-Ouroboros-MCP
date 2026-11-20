import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_balanced_prompt_run_plan import make_plan
from oril_v2_slot4_plan_observation_audit import audit, read_jsonl


def fixture():
    plan = make_plan([f"g{i:03}" for i in range(30)])
    rows = []
    for p in plan:
        row = dict(p)
        row.update(prompt_sha256=("a" if p["variant"] == "A" else "b") * 64,
                   model_revision="c" * 40, input_tokens=10,
                   output_tokens=3, latency_ms=1.2, run_id="run-001")
        rows.append(row)
    return plan, rows


class PlanBindingTests(unittest.TestCase):
    def test_valid_complete_balanced_run(self):
        p, o = fixture()
        report = audit(p, o)
        self.assertEqual(report["observed_calls"], 120)
        self.assertEqual(report["total_input_tokens"], 1200)
        self.assertFalse(report["external_model_execution_authenticated"])
        self.assertFalse(report["independent_heldout_quality_proven"])
        self.assertFalse(report["gpu_lora_training_proven"])

    def test_missing_call_rejected(self):
        p, o = fixture()
        with self.assertRaisesRegex(ValueError, "missing"):
            audit(p, o[:-1])

    def test_reordered_call_rejected(self):
        p, o = fixture()
        o[0], o[1] = o[1], o[0]
        with self.assertRaisesRegex(ValueError, "diverges"):
            audit(p, o)

    def test_variant_substitution_rejected(self):
        p, o = fixture()
        o[0]["variant"] = "B"
        with self.assertRaisesRegex(ValueError, "diverges"):
            audit(p, o)

    def test_model_drift_rejected(self):
        p, o = fixture()
        o[1]["model_revision"] = "d" * 40
        with self.assertRaisesRegex(ValueError, "revision drift"):
            audit(p, o)

    def test_run_drift_rejected(self):
        p, o = fixture()
        o[1]["run_id"] = "run-002"
        with self.assertRaisesRegex(ValueError, "run ID drift"):
            audit(p, o)

    def test_same_prompt_control_digest_mismatch_rejected(self):
        p, o = fixture()
        idx = next(i for i, r in enumerate(o) if r["block"] == "AA")
        o[idx]["prompt_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "inconsistent prompt"):
            audit(p, o)

    def test_negative_token_rejected(self):
        p, o = fixture()
        o[0]["input_tokens"] = -1
        with self.assertRaisesRegex(ValueError, "token count"):
            audit(p, o)

    def test_bool_token_rejected(self):
        p, o = fixture()
        o[0]["input_tokens"] = True
        with self.assertRaisesRegex(ValueError, "token count"):
            audit(p, o)

    def test_nonfinite_latency_rejected(self):
        p, o = fixture()
        o[0]["latency_ms"] = float("nan")
        with self.assertRaisesRegex(ValueError, "latency"):
            audit(p, o)

    def test_invalid_digest_rejected(self):
        p, o = fixture()
        o[0]["prompt_sha256"] = "not-sha"
        with self.assertRaisesRegex(ValueError, "digest"):
            audit(p, o)

    def test_extra_claim_field_rejected(self):
        p, o = fixture()
        o[0]["gpu_trained"] = True
        with self.assertRaisesRegex(ValueError, "schema"):
            audit(p, o)

    def test_invalid_plan_rejected(self):
        p, o = fixture()
        p[0]["variant"] = "B"
        with self.assertRaisesRegex(ValueError, "balance"):
            audit(p, o)

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.jsonl"
            path.write_text('{"a":1,"a":2}\n')
            with self.assertRaisesRegex(ValueError, "duplicate JSON"):
                read_jsonl(path)

    def test_cli_real_file_run(self):
        p, o = fixture()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            plan, obs, report = (root / x for x in ("plan.jsonl", "obs.jsonl", "report.json"))
            for path, rows in ((plan, p), (obs, o)):
                path.write_text("".join(json.dumps(r) + "\n" for r in rows))
            proc = subprocess.run([
                sys.executable,
                str(Path(__file__).resolve().parents[1] / "scripts/oril_v2_slot4_plan_observation_audit.py"),
                "--plan", str(plan), "--observations", str(obs), "--report", str(report)],
                capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(report.read_text())["observed_calls"], 120)

    def test_output_cannot_overwrite_input(self):
        p, o = fixture()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            plan, obs = root / "plan.jsonl", root / "obs.jsonl"
            for path, rows in ((plan, p), (obs, o)):
                path.write_text("".join(json.dumps(r) + "\n" for r in rows))
            proc = subprocess.run([
                sys.executable,
                str(Path(__file__).resolve().parents[1] / "scripts/oril_v2_slot4_plan_observation_audit.py"),
                "--plan", str(plan), "--observations", str(obs), "--report", str(plan)],
                capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(len(plan.read_text().splitlines()), 120)


if __name__ == "__main__":
    unittest.main()
