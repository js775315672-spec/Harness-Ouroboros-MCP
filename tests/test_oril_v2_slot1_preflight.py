"""Fail-closed preflight contract; side effects must not run on invalid trace output."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_phase_trace import run_timed

@unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"), "POSIX required")
class TracePreflightTests(unittest.TestCase):
    def test_rejected_output_does_not_execute_command(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            marker = root / "side-effect"
            output = root / "public.jsonl"
            output.write_text("KEEP\n")
            output.chmod(0o644)
            for _ in range(20):
                with self.assertRaises(PermissionError):
                    run_timed("model_call", [sys.executable, "-c", "from pathlib import Path; Path(%r).write_text('BAD')" % str(marker)], output)
                self.assertFalse(marker.exists())
            self.assertEqual(output.read_text(), "KEEP\n")

    def test_valid_output_executes_and_records(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            marker = root / "side-effect"
            output = root / "trace.jsonl"
            for _ in range(20):
                self.assertEqual(run_timed("model_call", [sys.executable, "-c", "from pathlib import Path; Path(%r).write_text('OK')" % str(marker)], output), 0)
            self.assertEqual(marker.read_text(), "OK")
            import json
            rows = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual(len(rows), 20)
            self.assertTrue(all(row["returncode"] == 0 for row in rows))

if __name__ == "__main__":
    unittest.main()
