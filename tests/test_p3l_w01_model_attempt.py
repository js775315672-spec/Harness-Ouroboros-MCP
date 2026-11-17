#!/usr/bin/env python3
"""Offline safety tests for coordinator-authored W01 one-call model transport."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from p3l_w01_model_attempt import (digest, execute, fixed_command, make_receipt,
                                  render)
from p3l_w01_request import canonical


def request():
    row = {
        "schema": "p3l-worker-request-v1",
        "worker": "W01", "issue": 38,
        "review_commit": "a" * 40,
        "source_sha256": "b" * 64,
        "spec_sha256": "c" * 64,
        "allowed_output": ["docs/p3l/ledger-input-contract.ko.md"],
        "prompt": "Write Korean Markdown for the ledger input contract. fixes=[] is valid.",
        "model_calls": 0,
        "executor_connected": False,
        "merge_authorized": False,
        "candidate_verified": False,
    }
    row["prompt_sha256"] = digest(row["prompt"].encode("utf-8"))
    row["prompt_bytes"] = len(row["prompt"].encode("utf-8"))
    row["request_sha256"] = digest(canonical(row))
    return row


class W01ModelAttemptTests(unittest.TestCase):
    def test_prompt_bytes_repeat_and_match_hash(self):
        first, second = render(request()), render(request())
        self.assertEqual(first.encode(), second.encode())
        self.assertTrue(first.startswith("Question:\n"))
        self.assertTrue(first.endswith("\n\nAnswer:\n"))

    def test_altered_request_fails_closed(self):
        row = request()
        row["source_sha256"] = "d" * 64
        with self.assertRaisesRegex(ValueError, "hash"):
            render(row)

    def test_prompt_hash_mismatch_fails_closed(self):
        row = request()
        row["prompt_sha256"] = "f" * 64
        row["request_sha256"] = digest(canonical({k: v for k, v in row.items()
                                                  if k != "request_sha256"}))
        with self.assertRaisesRegex(ValueError, "prompt"):
            render(row)

    def test_scope_and_execution_flags_are_immutable(self):
        for key, val in [("allowed_output", ["scripts/development_ledger.py"]),
                         ("model_calls", 1), ("merge_authorized", True),
                         ("candidate_verified", True), ("executor_connected", True)]:
            row = request()
            row[key] = val
            row["request_sha256"] = digest(canonical({k: v for k, v in row.items()
                                                      if k != "request_sha256"}))
            with self.subTest(key=key), self.assertRaises(ValueError):
                render(row)

    def test_role_injection_or_controls_rejected(self):
        for fragment in ("\x00", "\x1b", "\r", "\nQuestion:\n", "\nAnswer:\n"):
            row = request()
            row["prompt"] += fragment
            row["prompt_sha256"] = digest(row["prompt"].encode("utf-8"))
            row["prompt_bytes"] = len(row["prompt"].encode("utf-8"))
            row["request_sha256"] = digest(canonical({k: v for k, v in row.items()
                                                      if k != "request_sha256"}))
            with self.subTest(fragment=repr(fragment)), self.assertRaises(ValueError):
                render(row)

    def test_fixed_model_command_has_no_shell_or_network(self):
        command = fixed_command("llama-completion", "weights.gguf", "prompt")
        self.assertEqual(command[:2], ["llama-completion", "--model"])
        self.assertIn("--offline", command)
        self.assertIn("--n-predict", command)
        self.assertNotIn("--server", command)
        self.assertNotIn("--api-key", command)

    def test_mock_model_output_receipt_only_no_repo_changes(self):
        row = request()
        meta = {"revision": "1" * 40, "sha256": "2" * 64}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "artifacts").mkdir()
            path = root / "model-meta.json"
            path.write_text(json.dumps(meta), encoding="utf-8")
            out = root / "artifacts" / "w01"
            with (patch("p3l_w01_model_attempt.verified_head"),
                  patch("p3l_w01_model_attempt.build_request", return_value=row),
                  patch("p3l_w01_model_attempt.validate_assets", return_value=({}, "3" * 64)),
                  patch("p3l_w01_model_attempt.subprocess.run",
                        return_value=SimpleNamespace(returncode=0,
                                                     stdout="모델이 새로 작성한 W01 계약 초안입니다. " * 8,
                                                     stderr="")) as runner):
                rc = execute(root, "a" * 40, "llama-completion", "model.gguf",
                             path, root / "binary.json", out)
                self.assertEqual(rc, 0)
                self.assertTrue(runner.call_args.kwargs["shell"] is False)
            receipt = json.loads((out / "receipt.json").read_text(encoding="utf-8"))
            raw = (out / "raw_model_response.txt").read_text(encoding="utf-8")
            self.assertEqual(receipt["status"], "RAW_MODEL_RESPONSE_PENDING_REVIEW")
            self.assertEqual(receipt["model_calls"], 1)
            self.assertFalse(receipt["model_authored_document_verified"])
            self.assertFalse(receipt["model_patch_applied"])
            self.assertFalse(receipt["merge_authorized"])
            self.assertEqual(receipt["response_sha256"], digest(raw.strip().encode()))

    def test_mock_model_failure_fail_closed(self):
        row = request()
        meta = {"revision": "1" * 40, "sha256": "2" * 64}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "artifacts").mkdir()
            path = root / "meta.json"
            path.write_text(json.dumps(meta), encoding="utf-8")
            out = root / "artifacts" / "w01"
            with (patch("p3l_w01_model_attempt.verified_head"),
                  patch("p3l_w01_model_attempt.build_request", return_value=row),
                  patch("p3l_w01_model_attempt.validate_assets", return_value=({}, "3" * 64)),
                  patch("p3l_w01_model_attempt.subprocess.run",
                        return_value=SimpleNamespace(returncode=1, stdout="", stderr="oops"))):
                rc = execute(root, "a" * 40, "llama-completion", "model.gguf",
                             path, root / "binary.json", out)
            self.assertEqual(rc, 3)
            receipt = json.loads((out / "receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "MODEL_PROCESS_FAILED")
            self.assertEqual(receipt["model_calls"], 1)
            self.assertFalse((out / "raw_model_response.txt").exists())


if __name__ == "__main__":
    unittest.main()
