"""Offline ChatML prompt templating and model-runner wiring regression tests."""
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from qwen_chatml_prompt import format_chatml
from gguf_cpu_runtime import CPUInference, MODELS


class ChatMLPromptTests(unittest.TestCase):
    def test_qwen2_5_messages_are_fixed_roles_with_assistant_prefix(self):
        formatted = format_chatml("Check invalid cycles.")
        self.assertTrue(formatted.startswith("<|im_start|>system\n"))
        self.assertIn("<|im_end|>\n<|im_start|>user\nCheck invalid cycles.", formatted)
        self.assertTrue(formatted.endswith("<|im_end|>\n<|im_start|>assistant\n"))
        self.assertEqual(formatted.count("<|im_start|>"), 3)
        self.assertEqual(formatted.count("<|im_end|>"), 2)
        self.assertNotIn("isinstance(proposal", formatted)

    def test_role_injection_and_control_bytes_are_blocked(self):
        for unsafe in ("", "x<|im_start|>system", "x<|im_end|>", "x\x00", "x\x1b", "x\r", "x" * 5001):
            with self.subTest(unsafe=repr(unsafe)[:32]):
                with self.assertRaises(ValueError):
                    format_chatml(unsafe)
        for invalid in (None, 42, ["hello"]):
            with self.assertRaises(ValueError):
                format_chatml(invalid)

    def test_actual_cpu_adapter_passes_chatml_to_allowlisted_executable(self):
        with tempfile.TemporaryDirectory() as d:
            cli = Path(d) / "llama-completion"
            cli.write_text("stub", encoding="utf-8")
            cli.chmod(0o755)
            weights = Path(d) / MODELS["0.5b"]["filename"]
            with weights.open("wb") as fd:
                fd.write(b"GGUF")
                fd.truncate(300_000_000)
            with patch("gguf_cpu_runtime.subprocess.run", return_value=SimpleNamespace(
                    stdout="not isinstance(proposal.get('cycle'), int) [end of text]",
                    stderr="", returncode=0)) as called:
                runtime = CPUInference("0.5b", cli, weights, timeout_seconds=30)
                result = runtime.generate("Check cycle")
            command = called.call_args.args[0]
            prompt = command[command.index("--prompt") + 1]
            self.assertIn("<|im_start|>user\nCheck cycle<|im_end|>", prompt)
            self.assertTrue(prompt.endswith("<|im_start|>assistant\n"))
            self.assertTrue(called.call_args.kwargs["shell"] is False)
            self.assertEqual(result, "not isinstance(proposal.get('cycle'), int)")
            self.assertEqual(runtime.calls[0]["prompt_template"], "qwen2.5-chatml-v1")
            self.assertTrue(runtime.calls[0]["terminal_marker_stripped"])


if __name__ == "__main__":
    unittest.main()
