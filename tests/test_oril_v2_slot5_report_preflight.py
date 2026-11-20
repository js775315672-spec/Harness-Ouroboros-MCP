"""Real subprocess regression tests for private, exclusive paired-evaluation reports."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "oril_v2_student_real_inference_probe.py"
CASE = [
    {"case_id": "a", "group_id": "g1", "question": "one", "expected_answer": "yes", "split": "heldout"},
    {"case_id": "b", "group_id": "g2", "question": "two", "expected_answer": "yes", "split": "heldout"},
]


class ReportSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = self.root / "private.jsonl"
        self.manifest.write_text("\n".join(json.dumps(x) for x in CASE) + "\n")
        self.side_effect = self.root / "model-ran.txt"
        self.adapter = self.root / "adapter.py"
        self.adapter.write_text(
            "import json,sys\n"
            "from pathlib import Path\n"
            "Path(sys.argv[1]).write_text('executed')\n"
            "json.load(sys.stdin)\n"
            "print(json.dumps({'answer':'yes','input_tokens':3,"
            "'output_tokens':1,'model_id':'synthetic-stub'}))\n"
        )

    def run_probe(self, report):
        cmd = json.dumps([sys.executable, str(self.adapter), str(self.side_effect)])
        return subprocess.run([
            sys.executable, str(SCRIPT),
            "--heldout", str(self.manifest),
            "--baseline-cmd-json", cmd,
            "--candidate-cmd-json", cmd,
            "--report", str(report),
        ], capture_output=True, text=True, timeout=15)

    def test_existing_report_not_overwritten_and_no_model_call(self):
        path = self.root / "report.json"
        path.write_text("KEEP EXISTING")
        result = self.run_probe(path)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(path.read_text(), "KEEP EXISTING")
        self.assertFalse(self.side_effect.exists())

    def test_symlink_to_private_file_not_overwritten(self):
        victim = self.root / "victim.json"
        victim.write_text("SECRET ORIGINAL")
        link = self.root / "report.json"
        link.symlink_to(victim)
        result = self.run_probe(link)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(victim.read_text(), "SECRET ORIGINAL")
        self.assertFalse(self.side_effect.exists())

    def test_symlink_to_manifest_not_overwritten(self):
        link = self.root / "report.json"
        link.symlink_to(self.manifest)
        original = self.manifest.read_bytes()
        result = self.run_probe(link)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.manifest.read_bytes(), original)
        self.assertFalse(self.side_effect.exists())

    def test_missing_parent_rejects_before_model(self):
        result = self.run_probe(self.root / "missing" / "report.json")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.side_effect.exists())

    def test_new_report_private_and_complete(self):
        report = self.root / "report.json"
        result = self.run_probe(report)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.side_effect.exists())
        payload = json.loads(report.read_text())
        self.assertEqual(payload["cases"], 2)
        self.assertFalse(payload["independent_evaluation_verified"])
        self.assertFalse(payload["gpu_training_verified"])
        if os.name == "posix":
            self.assertEqual(report.stat().st_mode & 0o777, 0o600)

    def test_second_execution_rejects_and_preserves_report(self):
        report = self.root / "report.json"
        first = self.run_probe(report)
        self.assertEqual(first.returncode, 0, first.stderr)
        original = report.read_bytes()
        self.side_effect.unlink()
        second = self.run_probe(report)
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(report.read_bytes(), original)
        self.assertFalse(self.side_effect.exists())

    def test_adapter_failure_does_not_produce_valid_json_report(self):
        self.adapter.write_text("import sys\nsys.exit(4)\n")
        report = self.root / "report.json"
        result = self.run_probe(report)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(report.exists())
        self.assertEqual(report.read_bytes(), b"")

    def test_no_report_created_on_malformed_heldout(self):
        self.manifest.write_text('{"bad":"data"}\n')
        report = self.root / "report.json"
        result = self.run_probe(report)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(report.exists())
        self.assertFalse(self.side_effect.exists())


if __name__ == "__main__":
    unittest.main()
