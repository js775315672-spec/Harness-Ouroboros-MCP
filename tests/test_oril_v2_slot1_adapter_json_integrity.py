"""Adversarial adapter JSON contract. Synthetic subprocesses, NOT model evidence."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_student_real_inference_probe import invoke

RUNNER = Path(__file__).resolve().parents[1] / "scripts" / "oril_v2_student_real_inference_probe.py"


def command(payload):
    return [sys.executable, "-c", "import sys;sys.stdout.write(" + repr(payload) + ")"]


def valid(**changes):
    value = {"answer": "OK", "input_tokens": 3, "output_tokens": 1,
             "model_id": "synthetic-adapter"}
    value.update(changes)
    return json.dumps(value)


class AdapterJSONIntegrityTests(unittest.TestCase):
    def test_duplicate_answer_key_fails_closed(self):
        data = valid()[:-1] + ',"answer":"FORGED"}'
        with self.assertRaisesRegex(ValueError, "duplicate JSON"):
            invoke(command(data), "q", "c", 0, 3)

    def test_duplicate_token_key_fails_closed(self):
        data = valid()[:-1] + ',"input_tokens":0}'
        with self.assertRaisesRegex(ValueError, "duplicate JSON"):
            invoke(command(data), "q", "c", 0, 3)

    def test_duplicate_model_identity_fails_closed(self):
        data = valid()[:-1] + ',"model_id":"fake"}'
        with self.assertRaisesRegex(ValueError, "duplicate JSON"):
            invoke(command(data), "q", "c", 0, 3)

    def test_nested_duplicate_key_fails_closed(self):
        data = valid()[:-1] + ',"extra":{"x":1,"x":2}}'
        with self.assertRaisesRegex(ValueError, "duplicate JSON"):
            invoke(command(data), "q", "c", 0, 3)

    def test_nonfinite_token_count_fails_closed(self):
        data = valid().replace('"input_tokens": 3', '"input_tokens": NaN')
        with self.assertRaisesRegex(ValueError, "nonfinite JSON"):
            invoke(command(data), "q", "c", 0, 3)

    def test_valid_adapter_response_still_works(self):
        result, elapsed = invoke(command(valid()), "q", "c", 0, 3)
        self.assertEqual(result["answer"], "OK")
        self.assertEqual(result["input_tokens"], 3)
        self.assertGreaterEqual(elapsed, 0)

    def test_malformed_adapter_creates_no_published_report(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            heldout = root / "heldout.jsonl"
            rows = [
                {"case_id": f"c{i}", "group_id": f"g{i}",
                 "question": f"q{i}", "expected_answer": "OK",
                 "split": "heldout"} for i in range(2)
            ]
            heldout.write_text("\n".join(json.dumps(x) for x in rows) + "\n")
            report = root / "report.json"
            run = subprocess.run([
                sys.executable, str(RUNNER), "--heldout", str(heldout),
                "--baseline-cmd-json", json.dumps(command(valid())),
                "--candidate-cmd-json", json.dumps(command(valid()[:-1] + ',"answer":"FORGED"}')),
                "--report", str(report)
            ], text=True, capture_output=True, timeout=15)
            self.assertNotEqual(run.returncode, 0)
            self.assertFalse(report.exists())
            self.assertIn("duplicate JSON", run.stderr)


if __name__ == "__main__":
    unittest.main()
