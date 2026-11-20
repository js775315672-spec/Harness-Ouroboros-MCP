"""Synthetic adapters exercise the real subprocess runner; NOT a model benchmark."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_student_real_inference_probe import read_manifest, evaluate, invoke

ADAPTER = """
import json,sys
x=json.load(sys.stdin)
print(json.dumps({"answer":x["question"],"input_tokens":10,"output_tokens":2,"model_id":"synthetic-fixture"}))
"""
BAD = """print("not json")"""
SLOW = """import time;time.sleep(5)"""


def cmd(code):
    return [sys.executable, "-c", code]


def heldout(root):
    path = root / "heldout.jsonl"
    path.write_text("\n".join(json.dumps({
        "case_id": f"c{i}", "group_id": f"g{i}",
        "question": f"answer{i}", "expected_answer": f"answer{i}",
        "split": "heldout"}) for i in range(2)) + "\n")
    return path


class InferenceProbeTests(unittest.TestCase):
    def test_real_subprocess_paired_metrics_without_false_attestation(self):
        with tempfile.TemporaryDirectory() as t:
            rows, digest = read_manifest(heldout(Path(t)))
            result = evaluate(rows, digest, cmd(ADAPTER), cmd(ADAPTER))
            self.assertEqual(result["cases"], 2)
            self.assertEqual(result["baseline_accuracy"], 1)
            self.assertEqual(result["candidate_accuracy"], 1)
            self.assertEqual(result["accuracy_delta_pp"], 0)
            self.assertGreater(result["baseline_wall_seconds"], 0)
            self.assertFalse(result["independent_evaluation_verified"])
            self.assertFalse(result["gpu_training_verified"])
            self.assertFalse(result["adapter_weights_verified"])
            self.assertFalse(result["tokenizer_counts_independently_verified"])
            self.assertFalse(result["improvement_approved"])

    def test_heldout_answers_never_passed_to_adapter(self):
        code = """
import json,sys
x=json.load(sys.stdin)
assert set(x)=={"question","case_id","seed"}
assert "secret" not in json.dumps(x)
print(json.dumps({"answer":"wrong","input_tokens":3,"output_tokens":1,"model_id":"stub"}))
"""
        with tempfile.TemporaryDirectory() as t:
            path = heldout(Path(t))
            text = path.read_text().replace("answer0\",\"split", "secret\",\"split")
            path.write_text(text)
            rows, digest = read_manifest(path)
            report = evaluate(rows, digest, cmd(code), cmd(code))
            self.assertEqual(report["cases"], 2)
            self.assertEqual(report["candidate_accuracy"], 0)

    def test_reject_nonheldout(self):
        with tempfile.TemporaryDirectory() as t:
            path = heldout(Path(t))
            path.write_text(path.read_text().replace('"heldout"', '"train"'))
            with self.assertRaisesRegex(ValueError, "only heldout"):
                read_manifest(path)

    def test_reject_correlated_groups(self):
        with tempfile.TemporaryDirectory() as t:
            path = heldout(Path(t))
            path.write_text(path.read_text().replace('"g1"', '"g0"'))
            with self.assertRaisesRegex(ValueError, "duplicate"):
                read_manifest(path)

    def test_invalid_adapter_json_rejected(self):
        with self.assertRaisesRegex(ValueError, "JSON"):
            invoke(cmd(BAD), "a", "1", 0, 2)

    def test_timeout_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "timed out"):
            invoke(cmd(SLOW), "a", "1", 0, 0.05)

    def test_invalid_token_types_rejected(self):
        bad = ADAPTER.replace('"input_tokens":10', '"input_tokens":True')
        with self.assertRaisesRegex(ValueError, "token count"):
            invoke(cmd(bad), "a", "1", 0, 2)

    def test_command_failure_rejected(self):
        with self.assertRaisesRegex(ValueError, "failed"):
            invoke(cmd("import sys;sys.exit(3)"), "a", "1", 0, 2)

    def test_reject_same_report_path_before_run(self):
        with tempfile.TemporaryDirectory() as t:
            path = heldout(Path(t))
            script = str(Path(__file__).resolve().parents[1] / "scripts" /
                         "oril_v2_student_real_inference_probe.py")
            run = subprocess.run([
                sys.executable, script, "--heldout", str(path),
                "--report", str(path),
                "--baseline-cmd-json", json.dumps(cmd(ADAPTER)),
                "--candidate-cmd-json", json.dumps(cmd(ADAPTER))],
                capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("must not overwrite", run.stderr)
            self.assertEqual(len(path.read_text().splitlines()), 2)

    def test_failed_adapter_leaves_no_report(self):
        with tempfile.TemporaryDirectory() as t:
            path = heldout(Path(t))
            report = Path(t) / "report.json"
            script = str(Path(__file__).resolve().parents[1] / "scripts" /
                         "oril_v2_student_real_inference_probe.py")
            run = subprocess.run([
                sys.executable, script, "--heldout", str(path),
                "--report", str(report),
                "--baseline-cmd-json", json.dumps(cmd(ADAPTER)),
                "--candidate-cmd-json", json.dumps(cmd(BAD))],
                capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertFalse(report.exists())


if __name__ == "__main__":
    unittest.main()
