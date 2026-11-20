"""Offline protocol checks only; synthetic adapter is NOT a real Qwen inference."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from oril_v2_paired_prompt_variant_adapter import (
    prepare_request, read_prefix, run, parse_json,
)

FAKE_ADAPTER = [
    sys.executable, "-c",
    "import sys,json; x=json.load(sys.stdin);"
    "print(json.dumps({'answer':'OK','input_tokens':len(x['question']),"
    "'output_tokens':1,'model_id':'synthetic-not-qwen'}))",
]


def request(question="What is 1+1?"):
    return json.dumps({"question": question, "case_id": "case1", "seed": 0})


class PromptVariantTests(unittest.TestCase):
    def test_exact_sha_bytes_and_read(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "prefix.txt"
            p.write_text("Teacher examples only", encoding="utf-8")
            sha = hashlib.sha256(p.read_bytes()).hexdigest()
            self.assertEqual(read_prefix(p, sha), "Teacher examples only")

    def test_wrong_sha_fails_before_adapter(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "prefix.txt"
            p.write_text("sample")
            with self.assertRaisesRegex(ValueError, "SHA mismatch"):
                read_prefix(p, "0" * 64)

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "prefix.txt"
            p.write_text("sample")
            link = Path(d) / "alias"
            link.symlink_to(p)
            with self.assertRaisesRegex(ValueError, "symlink"):
                read_prefix(link, hashlib.sha256(p.read_bytes()).hexdigest())

    def test_bounded_prefix(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "prefix.txt"
            p.write_bytes(b"x" * 3001)
            with self.assertRaisesRegex(ValueError, "3000"):
                read_prefix(p, hashlib.sha256(p.read_bytes()).hexdigest())

    def test_bad_utf8_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "prefix.txt"
            p.write_bytes(b"\xff")
            with self.assertRaises(UnicodeDecodeError):
                read_prefix(p, hashlib.sha256(p.read_bytes()).hexdigest())

    def test_duplicate_keys_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            parse_json('{"question":"x","question":"y"}')

    def test_nonfinite_json_rejected(self):
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            parse_json('{"seed":NaN}')

    def test_request_preserves_case_and_seed(self):
        q = json.loads(prepare_request(request(), "Example: 2+2=4"))
        self.assertEqual(q["case_id"], "case1")
        self.assertEqual(q["seed"], 0)
        self.assertIn("Question:\nWhat is 1+1?", q["question"])

    def test_context_budget_rejected(self):
        with self.assertRaisesRegex(ValueError, "4000-character"):
            prepare_request(request("a" * 3999), "short")

    def test_invalid_request_schema(self):
        with self.assertRaisesRegex(ValueError, "schema"):
            prepare_request('{"question":"x"}', "sample")

    def test_invalid_seed(self):
        with self.assertRaisesRegex(ValueError, "seed"):
            prepare_request(json.dumps({"question":"x","case_id":"id","seed":True}), "sample")

    def test_synthetic_subprocess_observes_different_context_lengths(self):
        a = run(request(), "short", FAKE_ADAPTER, 5)
        b = run(request(), "A longer teacher example to test context", FAKE_ADAPTER, 5)
        self.assertEqual(a["answer"], b["answer"])
        self.assertLess(a["input_tokens"], b["input_tokens"])
        self.assertEqual(a["model_id"], "synthetic-not-qwen")

    def test_fake_response_is_not_evaluation_evidence(self):
        result = run(request(), "sample", FAKE_ADAPTER, 5)
        self.assertEqual(result["model_id"], "synthetic-not-qwen")
        self.assertEqual(result["output_tokens"], 1)

    def test_invalid_adapter_command(self):
        with self.assertRaisesRegex(ValueError, "command"):
            run(request(), "sample", "python -c unsafe", 5)

    def test_bad_adapter_response_rejected(self):
        bad = [sys.executable, "-c", "print('{}')"]
        with self.assertRaisesRegex(ValueError, "schema"):
            run(request(), "sample", bad, 5)

    def test_timeout_budget_rejected(self):
        with self.assertRaisesRegex(ValueError, "timeout"):
            run(request(), "sample", FAKE_ADAPTER, 0)

    def test_nonfinite_claim_rejected(self):
        bad = [sys.executable, "-c", "print('{\"answer\":\"x\",\"input_tokens\":NaN,\"output_tokens\":1,\"model_id\":\"m\"}')"]
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            run(request(), "sample", bad, 5)

    def test_oversized_request_rejected(self):
        with self.assertRaisesRegex(ValueError, "request too large"):
            prepare_request("x" * 65537, "sample")


if __name__ == "__main__":
    unittest.main()
