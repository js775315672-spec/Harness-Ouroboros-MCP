"""Offline adversarial tests for opt-in quoted NUL/ESC normalization."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from qwen_control_literal_boundary import escape_quoted_control_bytes
from gguf_cpu_runtime import CPUInference, MODELS
from qwen_second_task_trial import normalize_expression


class QuotedControlsTests(unittest.TestCase):
    def test_only_physical_controls_between_balanced_quotes_are_escaped(self):
        raw = "'" + chr(0) + "' in log or '" + chr(27) + "' in log"
        clean, count = escape_quoted_control_bytes(raw)
        self.assertEqual(clean, r"'\x00' in log or '\x1b' in log")
        self.assertEqual(count, 2)
        self.assertEqual(normalize_expression(clean), clean)

    def test_existing_textual_escaped_expressions_are_unchanged(self):
        raw = r"'\x00' in log or '\x1b' in log"
        normalized, count = escape_quoted_control_bytes(raw)
        self.assertEqual(normalized, raw)
        self.assertEqual(count, 0)
        self.assertEqual(normalize_expression(normalized), raw)

    def test_ansi_and_unquoted_control_bytes_fail_closed(self):
        for raw in (chr(27) + "[31m", "prefix " + chr(0), "x '" + chr(0),
                    "x '" + chr(27), "print(1)\r"):
            with self.subTest(raw=repr(raw)):
                with self.assertRaises(ValueError):
                    escape_quoted_control_bytes(raw)

    def test_converted_bad_model_code_still_fails_ast(self):
        unsafe = "__import__('os').system('" + chr(0) + "')"
        clean, count = escape_quoted_control_bytes(unsafe)
        self.assertEqual(count, 1)
        with self.assertRaises(ValueError):
            normalize_expression(clean)

    def test_real_adapter_requires_optin_and_audits_raw_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            cli = Path(temp) / "llama-completion"
            cli.write_bytes(b"test")
            cli.chmod(0o755)
            weights = Path(temp) / MODELS["0.5b"]["filename"]
            with weights.open("wb") as f:
                f.write(b"GGUF")
                f.truncate(300_000_000)
            raw = "'" + chr(0) + "' in log or '" + chr(27) + "' in log [end of text]"
            response = SimpleNamespace(returncode=0, stdout=raw, stderr="")
            with patch("gguf_cpu_runtime.subprocess.run", return_value=response):
                default = CPUInference("0.5b", cli, weights, timeout_seconds=30)
                with self.assertRaises(ValueError):
                    default.generate("test")
                optin = CPUInference("0.5b", cli, weights, timeout_seconds=30,
                                     escape_quoted_controls=True)
                result = optin.generate("test")
            self.assertEqual(result, r"'\x00' in log or '\x1b' in log")
            self.assertEqual(optin.calls[0]["quoted_control_bytes_escaped"], 2)
            self.assertTrue(optin.calls[0]["terminal_marker_stripped"])
            self.assertEqual(normalize_expression(result), result)

    def test_nonboolean_mode_argument_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            cli = Path(temp) / "llama-completion"
            cli.write_bytes(b"test")
            cli.chmod(0o755)
            weights = Path(temp) / MODELS["0.5b"]["filename"]
            with weights.open("wb") as f:
                f.write(b"GGUF")
                f.truncate(300_000_000)
            with self.assertRaises(ValueError):
                CPUInference("0.5b", cli, weights, escape_quoted_controls="yes")


if __name__ == "__main__":
    unittest.main()
