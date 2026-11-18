"""Offline-only tests; no model calls and no untrusted code execution."""
import hashlib
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import p3l_w06_public_contract_lint as lint


def receipt(raw):
    return {
        "schema": "p3l-w06-one-shot-output-v1",
        "run_id": 123,
        "raw_response": raw,
        "raw_response_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "candidate_source_sha256": "a" * 64,
    }


class PublicContractLintTests(unittest.TestCase):
    def test_missing_public_guards_are_only_advisory_not_accepted(self):
        raw = """```python
def validate(records):
    for record in records:
        fixes = record['fixes']
        if any(not isinstance(x, str) or len(x) > 128 for x in fixes):
            raise ValueError('invalid fixes')
    return len(records)
```"""
        result = lint.diagnose(receipt(raw))
        self.assertEqual(set(result["not_detected"]), set(lint.RULES))
        self.assertFalse(result["model_code_executed"])
        self.assertFalse(result["candidate_passed"])
        self.assertEqual(result["model_calls"], 0)

    def test_syntax_markers_never_imply_candidate_success(self):
        raw = """def validate(records):
    for record in records:
        fixes = record['fixes']
        if len(fixes) > 12: raise ValueError('max')
        if any(not x or len(x.encode('utf-8')) > 128 for x in fixes): raise ValueError('item')
        if len(record['change'].encode('utf-8')) > 256: raise ValueError('change')
    return len(records)
"""
        result = lint.diagnose(receipt(raw))
        self.assertEqual(result["not_detected"], [])
        self.assertFalse(result["candidate_passed"])
        self.assertFalse(result["independent_replay_completed"])

    def test_tampered_raw_sha_fails_closed(self):
        data = receipt("def validate(records):\n    return len(records)\n")
        data["raw_response"] += "#tampered"
        with self.assertRaisesRegex(ValueError, "SHA mismatch"):
            lint.diagnose(data)

    def test_import_and_top_level_extra_code_are_rejected(self):
        for raw in ("import os\ndef validate(records): return 1\n", "x=1\ndef validate(records): return 1\n"):
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(ValueError, "function only"):
                    lint.diagnose(receipt(raw))

    def test_unsafe_call_is_rejected(self):
        raw = "def validate(records):\n    return eval('1')\n"
        with self.assertRaisesRegex(ValueError, "forbidden"):
            lint.diagnose(receipt(raw))


if __name__ == "__main__":
    unittest.main()
