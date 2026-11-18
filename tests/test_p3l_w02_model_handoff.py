"""Offline W02 contract handoff tests; no model call and no source edits."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import p3l_w02_model_handoff as w02


class W02HandoffTests(unittest.TestCase):
    def test_provisional_contract_is_ready_but_not_a_model_result(self):
        r = w02.build(ROOT)
        self.assertEqual(r["schema"], w02.SCHEMA)
        self.assertEqual(r["w01_case_count"], 19)
        self.assertTrue(r["w01_provisional_gate_passed"])
        self.assertFalse(r["merge_authorized"])
        self.assertFalse(r["model_connected"])
        self.assertFalse(r["candidate_produced"])
        self.assertEqual(r["model_calls"], 0)
        self.assertEqual(r["legacy_blob_sha1"], w02.LOCKED_LEGACY_BLOB)

    def test_byte_exact_replay_of_bounded_model_prompt(self):
        first, second = w02.build(), w02.build()
        self.assertEqual(first, second)
        import hashlib
        self.assertEqual(first["prompt_sha256"], hashlib.sha256(first["prompt"].encode()).hexdigest())
        self.assertLessEqual(first["prompt_utf8_bytes"], 7000)
        self.assertIn("fixes=[]", first["prompt"])
        self.assertIn("128 UTF-8 bytes", first["prompt"])
        self.assertIn("256 UTF-8 bytes", first["prompt"])
        self.assertIn("def validate(records):", first["prompt"])
        self.assertNotIn("test_reject_empty_fix_entry", first["prompt"])
        self.assertNotIn("FrozenLedgerInputSecurity", first["prompt"])
        self.assertNotIn("FIRST QWEN SOURCE IMPLEMENTATION", first["prompt"])

    def test_unverified_gate_blocks_w02_handoff(self):
        with patch.object(w02, "gate_exit_code", return_value=2):
            with self.assertRaisesRegex(ValueError, "W01 proposed contract"):
                w02.build()

    def test_immutable_legacy_source_mismatch_blocks_handoff(self):
        with patch.object(w02, "LOCKED_LEGACY_BLOB", "0" * 40):
            with self.assertRaisesRegex(ValueError, "immutable source digest"):
                w02.build()

    def test_missing_or_symlinked_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                w02.read_source(root, w02.LEGACY)
            (root / "fake").symlink_to(ROOT / w02.LEGACY)
            with self.assertRaises(ValueError):
                w02.read_source(root, Path("fake"))

    def test_manifest_and_prompt_do_not_claim_model_execution(self):
        r = w02.build()
        self.assertEqual(r["status"], "ready_for_isolated_model_attempt")
        self.assertFalse(r["model_output_accepted"])
        self.assertFalse(r["fixed_25_modified"])


if __name__ == "__main__":
    unittest.main()
