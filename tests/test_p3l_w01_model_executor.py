"""Offline W06 bootstrap gates. All model calls are mocked; tests do NOT infer."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import p3l_w01_model_executor as worker
from p3l_w01_request import build_request

SHA = "a" * 40
SOURCE = 'def validate(records):\n    return len(records)\n'


class W01ModelBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "scripts").mkdir()
        (self.root / "docs/p3l").mkdir(parents=True)
        (self.root / "scripts/development_ledger.py").write_text(SOURCE, encoding="utf-8")
        (self.root / "docs/p3l/W01-ledger-contract.ko.md").write_text(
            "Contract: fixes=[] valid; fixes=[''] invalid.", encoding="utf-8")
        self.request = build_request(self.root, SHA)

    def test_exact_request_is_required(self):
        self.assertEqual(worker.verified_request(self.root, SHA, self.request), self.request)
        altered = dict(self.request, prompt="untrusted changed prompt")
        with self.assertRaises(ValueError):
            worker.verified_request(self.root, SHA, altered)

    def test_cross_commit_or_source_change_blocks(self):
        with self.assertRaises(ValueError):
            worker.verified_request(self.root, "b" * 40, self.request)
        (self.root / "scripts/development_ledger.py").write_text(
            SOURCE + "\n# changed", encoding="utf-8")
        with self.assertRaises(ValueError):
            worker.verified_request(self.root, SHA, self.request)

    def test_prompt_role_and_control_injection_blocked(self):
        for string in ("<|im_start|>", "<|im_end|>", "\x00", "\x1b", "\r"):
            with self.subTest(string=repr(string)), self.assertRaises(ValueError):
                worker.format_w01("valid" + string)
        self.assertIn("assistant", worker.format_w01("W01 contract only"))

    def test_bounded_response_no_execution(self):
        for invalid in ("", "hi", "x" * 6100, "\x1b" + "x" * 60):
            with self.subTest(invalid=repr(invalid[:5])), self.assertRaises(ValueError):
                worker.verify_candidate(invalid)
        self.assertEqual(worker.verify_candidate("가" * 30), "가" * 30)

    def test_safe_output_and_overwrite(self):
        for bad in ("../x", "/tmp/x", "docs/p3l", "artifacts/p3l-w01-model/../../escape"):
            with self.subTest(path=bad), self.assertRaises(ValueError):
                worker.output_dir(self.root, Path(bad))
        target = worker.output_dir(self.root, Path("artifacts/p3l-w01-model"))
        (target / "record.json").write_text("prior", encoding="utf-8")
        with self.assertRaises(ValueError):
            worker.output_dir(self.root, Path("artifacts/p3l-w01-model"))

    def test_single_mock_response_is_unreviewed(self):
        request_path = self.root / "request.json"
        request_path.write_text(json.dumps(self.request), encoding="utf-8")
        metadata = {"revision": "c" * 40, "sha256": "d" * 64}
        with (mock.patch.object(worker, "verified_head"),
              mock.patch.object(worker, "verified_model",
                                return_value=(Path("llama-completion"),
                                              Path("model.gguf"), metadata)),
              mock.patch.object(worker, "sha256_file", return_value="e" * 64),
              mock.patch.object(worker, "one_model_call", return_value="가" * 30) as call):
            status = worker.run(self.root, SHA, request_path, Path("bin"),
                                Path("model"), Path("meta"),
                                Path("artifacts/p3l-w01-model"))
        self.assertEqual(status, 0)
        self.assertEqual(call.call_count, 1)
        record = json.loads((self.root / "artifacts/p3l-w01-model/record.json").read_text())
        self.assertEqual(record["model_calls"], 1)
        self.assertFalse(record["candidate_verified"])
        self.assertFalse(record["merge_authorized"])
        self.assertEqual(record["outcome"], "generated_unreviewed")

    def test_model_failure_is_recorded_not_passed(self):
        path = self.root / "request.json"
        path.write_text(json.dumps(self.request), encoding="utf-8")
        with (mock.patch.object(worker, "verified_head"),
              mock.patch.object(worker, "verified_model",
                                return_value=(Path("llama-completion"), Path("m"),
                                              {"revision": "c" * 40,
                                               "sha256": "d" * 64})),
              mock.patch.object(worker, "sha256_file", return_value="e" * 64),
              mock.patch.object(worker, "one_model_call",
                                side_effect=ValueError("simulated model failure")) as call):
            status = worker.run(self.root, SHA, path, Path("bin"), Path("model"),
                                Path("meta"), Path("artifacts/p3l-w01-model"))
        self.assertEqual(status, 2)
        self.assertEqual(call.call_count, 1)
        record = json.loads((self.root / "artifacts/p3l-w01-model/record.json").read_text())
        self.assertEqual(record["outcome"], "model_invocation_failed")
        self.assertFalse(record["candidate_verified"])
        self.assertEqual(record["model_calls"], 1)

    def test_bad_request_blocks_before_call(self):
        path = self.root / "bad.json"
        path.write_text(json.dumps(dict(self.request, worker="W06")), encoding="utf-8")
        with (mock.patch.object(worker, "verified_head"),
              mock.patch.object(worker, "one_model_call") as call):
            with self.assertRaises(ValueError):
                worker.run(self.root, SHA, path, Path("bin"), Path("model"),
                           Path("meta"), Path("artifacts/p3l-w01-model"))
        call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
