"""CPU-only contract tests; synthetic mocks are NOT real model inference."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_local_qwen_adapter import (
    ensure_local_model, parse_request, render_question, run_inference,
)


def req(**updates):
    d = {"question": "What is 1+1?", "case_id": "case-1", "seed": 0}
    d.update(updates)
    return d


class MockTensor:
    def __init__(self, tokens):
        self.tokens = tokens
        self.shape = (1, len(tokens))
    def to(self, device):
        return self
    def __getitem__(self, key):
        if isinstance(key, tuple):
            return MockTensor(self.tokens[key[1]])
        return MockTensor(self.tokens[key])


class MockTokenizer:
    chat_template = None
    @classmethod
    def from_pretrained(cls, *args, **kwargs):
        assert kwargs == {"local_files_only": True, "trust_remote_code": False}
        return cls()
    def __call__(self, text, return_tensors):
        assert return_tensors == "pt"
        return {"input_ids": MockTensor([1, 2, 3])}
    def decode(self, ids, skip_special_tokens):
        assert skip_special_tokens
        return "2"


class MockModel:
    @classmethod
    def from_pretrained(cls, *args, **kwargs):
        assert kwargs == {"local_files_only": True, "trust_remote_code": False}
        return cls()
    def to(self, device):
        return self
    def eval(self):
        return self
    def generate(self, **kwargs):
        assert kwargs["do_sample"] is False
        return MockTensor([1, 2, 3, 4])


class FakeInference:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


class LocalAdapterTests(unittest.TestCase):
    def test_valid_request(self):
        self.assertEqual(parse_request(json.dumps(req()).encode().decode()), req())

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate request"):
            parse_request('{"question":"a","question":"b","case_id":"x","seed":0}')

    def test_unknown_field_rejected(self):
        with self.assertRaisesRegex(ValueError, "schema"):
            parse_request(json.dumps(req(expected_answer="private")))

    def test_negative_seed_rejected(self):
        with self.assertRaisesRegex(ValueError, "seed"):
            parse_request(json.dumps(req(seed=-1)))

    def test_bool_seed_rejected(self):
        with self.assertRaisesRegex(ValueError, "seed"):
            parse_request(json.dumps(req(seed=True)))

    def test_question_size_bounded(self):
        with self.assertRaisesRegex(ValueError, "question"):
            parse_request(json.dumps(req(question="x" * 4001)))

    def test_nonfinite_rejected(self):
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            parse_request('{"question":"a","case_id":"b","seed":NaN}')

    def test_local_model_requires_config(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, "config"):
                ensure_local_model(root)
            (Path(root) / "config.json").write_text("{}")
            self.assertEqual(ensure_local_model(root), str(Path(root).resolve()))

    def test_symlinked_model_dir_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            model = Path(root) / "real"
            model.mkdir()
            (model / "config.json").write_text("{}")
            link = Path(root) / "link"
            link.symlink_to(model, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "non-symlink"):
                ensure_local_model(link)

    def test_plain_and_chat_template(self):
        class Chat:
            chat_template = "template"
            def apply_chat_template(self, messages, **kwargs):
                self.messages = messages
                return "chat-prompt"
        self.assertEqual(render_question("hello", MockTokenizer()), "hello")
        obj = Chat()
        self.assertEqual(render_question("hello", obj), "chat-prompt")
        self.assertEqual(obj.messages, [{"role": "user", "content": "hello"}])

    def test_inference_protocol_with_mock_only(self):
        fake_torch = types.SimpleNamespace(
            manual_seed=lambda _: None, inference_mode=FakeInference,
            cuda=types.SimpleNamespace(is_available=lambda: False))
        fake_tf = types.SimpleNamespace(
            AutoTokenizer=MockTokenizer, AutoModelForCausalLM=MockModel)
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "config.json").write_text("{}")
            with patch.dict(sys.modules, {"torch": fake_torch, "transformers": fake_tf}):
                result = run_inference(req(), model_dir=root)
        self.assertEqual(result["answer"], "2")
        self.assertEqual(result["input_tokens"], 3)
        self.assertEqual(result["output_tokens"], 1)
        self.assertTrue(result["model_id"].startswith("local:"))

    def test_cuda_without_gpu_fails_closed(self):
        fake_torch = types.SimpleNamespace(
            manual_seed=lambda _: None,
            cuda=types.SimpleNamespace(is_available=lambda: False))
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "config.json").write_text("{}")
            with patch.dict(sys.modules, {"torch": fake_torch, "transformers": types.SimpleNamespace(AutoTokenizer=MockTokenizer, AutoModelForCausalLM=MockModel)}):
                with self.assertRaisesRegex(RuntimeError, "CUDA"):
                    run_inference(req(), model_dir=root, device="cuda")

    def test_invalid_generation_budget(self):
        with self.assertRaisesRegex(ValueError, "generation budget"):
            run_inference(req(), model_dir="/does-not-exist", max_new_tokens=0)

    def test_cli_rejects_heldout_answer_before_loading_dependencies(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "config.json").write_text("{}")
            run = subprocess.run([
                sys.executable,
                str(Path(__file__).resolve().parents[1] / "scripts" /
                    "oril_v2_local_qwen_adapter.py"),
                "--model-dir", root],
                input=json.dumps(req(expected_answer="SECRET")), text=True,
                capture_output=True, timeout=5)
            self.assertNotEqual(run.returncode, 0)
            self.assertEqual(run.stdout, "")
            self.assertNotIn("SECRET", run.stderr)


if __name__ == "__main__":
    unittest.main()
