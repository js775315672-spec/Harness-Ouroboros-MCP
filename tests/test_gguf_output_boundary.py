"""Offline regression tests for GGUF output cleanup and AST/Docker separation."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gguf_output_boundary import extract_completion
from gguf_cpu_runtime import CPUInference, MODELS
from qwen_semantic_repair_loop import normalize_candidate, run_loop, build_prompt
from qwen_source_guard import TARGET


class GGUFBoundaryTests(unittest.TestCase):
    def test_clean_recorded_05_output_without_rewriting_program(self):
        recorded = "```python\nproposal = {\n    'cycle': 'missing'\n}\n``` [end of text]"
        cleaned, flag = extract_completion(recorded)
        self.assertEqual(cleaned, "```python\nproposal = {\n    'cycle': 'missing'\n}\n```")
        self.assertTrue(flag)
        source = (ROOT / TARGET).read_text(encoding="utf-8")
        with self.assertRaises(ValueError):
            normalize_candidate(cleaned, source)

    def test_clean_recorded_15_output_but_semantics_still_rejected(self):
        recorded = (
            "```python\nnot (proposal.get('cycle') in "
            "[None, False, 'invalid', 0, -1])\n``` [end of text]")
        cleaned, flag = extract_completion(recorded)
        self.assertTrue(flag)
        self.assertTrue(cleaned.startswith("```python"))
        source = (ROOT / TARGET).read_text(encoding="utf-8")
        with self.assertRaises(ValueError):
            normalize_candidate(cleaned, source)

    def test_ast_safe_but_semantically_wrong_still_requires_docker(self):
        source = (ROOT / TARGET).read_text(encoding="utf-8")
        recorded = (
            "```python\nnot (proposal.get('cycle') in "
            "[None, False, 0, -1])\n``` [end of text]")
        cleaned, _ = extract_completion(recorded)
        candidate, inspected = normalize_candidate(cleaned, source)
        self.assertEqual(inspected["status"], "ast_scoped_candidate")
        self.assertIn("not (proposal.get('cycle')", candidate)
        evaluations = []
        def reject(line):
            evaluations.append(line)
            return {"status": "candidate_negative_failed"}
        result = run_loop(source, lambda _: cleaned, reject)
        self.assertEqual(result["status"], "stalled_duplicate_candidate")
        self.assertEqual(result["model_calls"], 2)
        self.assertEqual(result["docker_comparisons"], 1)
        self.assertIsNone(result["candidate"])
        self.assertFalse(result["merge_authorized"])
        self.assertEqual(evaluations, [candidate])

    def test_terminal_marker_must_be_only_one_bounded_suffix(self):
        for output in (
            "", "  ", "[end of text]", "x[end of text]",
            "x [end of text]\nmore", "x [end of text] [end of text]",
            "x \x1b[0m", "x\r", "x\x00"
        ):
            with self.subTest(output=output):
                with self.assertRaises(ValueError):
                    extract_completion(output)
        with self.assertRaises(ValueError):
            extract_completion("abcd", max_output_bytes=3)
        with self.assertRaises(ValueError):
            extract_completion("ok", max_output_bytes=True)
        self.assertEqual(extract_completion("x")[0], "x")
        self.assertFalse(extract_completion("x")[1])

    def test_mocked_runtime_logs_raw_and_clean_hashes_without_bypass(self):
        with tempfile.TemporaryDirectory() as d:
            cli = Path(d) / "llama-completion"
            cli.write_text("dummy", encoding="utf-8")
            cli.chmod(0o755)
            weights = Path(d) / MODELS["0.5b"]["filename"]
            with weights.open("wb") as fd:
                fd.write(b"GGUF")
                fd.truncate(300_000_000)
            raw = "proposal.get('cycle') is None [end of text]\n"
            with patch("gguf_cpu_runtime.subprocess.run", return_value=SimpleNamespace(
                    returncode=0, stdout=raw, stderr="")):
                engine = CPUInference("0.5b", cli, weights, timeout_seconds=30)
                cleaned = engine.generate("test prompt")
            self.assertEqual(cleaned, "proposal.get('cycle') is None")
            self.assertTrue(engine.calls[0]["terminal_marker_stripped"])
            self.assertEqual(engine.calls[0]["stdout_sha256"],
                             hashlib.sha256(raw.encode("utf-8")).hexdigest())
            self.assertNotEqual(engine.calls[0]["stdout_sha256"],
                                engine.calls[0]["response_sha256"])

    def test_prompt_improves_strategy_without_giving_exact_solution(self):
        prompt = build_prompt()
        self.assertIn("finite list", prompt)
        self.assertIn("short-circuit", prompt)
        self.assertNotIn('type(proposal.get("cycle")) is not int', prompt)
        self.assertNotIn('isinstance(proposal.get("cycle"), bool)', prompt)


if __name__ == "__main__":
    unittest.main()
