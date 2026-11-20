"""Adversarial FIFO preflight regression: no reader must not hang or execute commands."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "oril_v2_phase_trace.py"

@unittest.skipUnless(os.name == "posix" and hasattr(os, "mkfifo"), "POSIX FIFO required")
class FIFOTraceTests(unittest.TestCase):
    def test_unread_fifo_fails_fast_without_command_side_effect(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fifo = root / "trace.fifo"
            marker = root / "executed"
            os.mkfifo(fifo, 0o600)
            cmd = [sys.executable, str(SCRIPT), "measure", "--phase", "model_call",
                   "--output", str(fifo), "--", sys.executable, "-c",
                   "from pathlib import Path; Path(%r).write_text('BAD')" % str(marker)]
            for _ in range(5):
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
                self.assertNotEqual(proc.returncode, 0)
                self.assertFalse(marker.exists())
            self.assertTrue(fifo.is_fifo())

if __name__ == "__main__":
    unittest.main()
