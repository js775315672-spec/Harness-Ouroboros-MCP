"""Bounded subprocess output regression; synthetic adapters, not Qwen/GPU evidence."""
import os
from pathlib import Path
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_bounded_adapter_capture import capture_adapter
from oril_v2_student_real_inference_probe import invoke

@unittest.skipUnless(os.name == "posix", "POSIX subprocess group boundary")
class BoundedAdapterTests(unittest.TestCase):
    def command(self, code):
        return [sys.executable, "-c", code]

    def test_small_valid_json(self):
        cmd = self.command('import json;print(json.dumps({"answer":"ok","input_tokens":3,"output_tokens":1,"model_id":"stub"}))')
        result, elapsed = invoke(cmd, "q", "id", 0, 3)
        self.assertEqual(result["answer"], "ok")
        self.assertGreaterEqual(elapsed, 0)

    def test_large_stdout_rejected(self):
        cmd = self.command("import sys;sys.stdout.write('x'*4000000);sys.stdout.flush()")
        with self.assertRaisesRegex(ValueError, "excessive output"):
            invoke(cmd, "q", "id", 0, 3)

    def test_stdout_overflow_terminates_quickly(self):
        cmd = self.command("import sys,time;sys.stdout.write('x'*4000000);sys.stdout.flush();time.sleep(10)")
        start = time.monotonic()
        with self.assertRaisesRegex(ValueError, "excessive output"):
            invoke(cmd, "q", "id", 0, 3)
        self.assertLess(time.monotonic() - start, 3)

    def test_timeout_terminates_quickly(self):
        cmd = self.command("import time;time.sleep(10)")
        start = time.monotonic()
        with self.assertRaisesRegex(ValueError, "timed out"):
            invoke(cmd, "q", "id", 0, 0.2)
        self.assertLess(time.monotonic() - start, 2)

    def test_invalid_utf8_rejected(self):
        cmd = self.command("import sys;sys.stdout.buffer.write(b'\\xff')")
        with self.assertRaisesRegex(ValueError, "invalid UTF-8"):
            invoke(cmd, "q", "id", 0, 3)

    def test_nonzero_exit_rejected(self):
        cmd = self.command("import sys;sys.exit(4)")
        with self.assertRaisesRegex(ValueError, "adapter failed"):
            invoke(cmd, "q", "id", 0, 3)

    def test_exact_boundary_accepted_by_capture(self):
        cmd = self.command("import sys;sys.stdout.write('x'*1024)")
        self.assertEqual(len(capture_adapter(cmd, "{}", 3, max_stdout=1024)), 1024)

    def test_boundary_plus_one_rejected(self):
        cmd = self.command("import sys;sys.stdout.write('x'*1025)")
        with self.assertRaisesRegex(ValueError, "excessive output"):
            capture_adapter(cmd, "{}", 3, max_stdout=1024)

    def test_large_request_fails_before_launch(self):
        cmd = self.command("print('SHOULD_NOT_RUN')")
        with self.assertRaisesRegex(ValueError, "64 KiB"):
            capture_adapter(cmd, "a"*65537, 3)

    def test_adapter_duplicate_key_still_rejected(self):
        cmd = self.command('print(\'{"answer":"ok","answer":"fake","input_tokens":1,"output_tokens":1,"model_id":"stub"}\')')
        with self.assertRaisesRegex(ValueError, "duplicate JSON"):
            invoke(cmd, "q", "id", 0, 3)

    def test_adapter_nonfinite_still_rejected(self):
        cmd = self.command('print(\'{"answer":"ok","input_tokens":NaN,"output_tokens":1,"model_id":"stub"}\')')
        with self.assertRaisesRegex(ValueError, "nonfinite JSON"):
            invoke(cmd, "q", "id", 0, 3)

if __name__ == "__main__":
    unittest.main()
