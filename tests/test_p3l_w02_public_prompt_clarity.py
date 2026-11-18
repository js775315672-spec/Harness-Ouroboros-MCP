"""W02 public-contract checklist tests; never invoke a model."""
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import p3l_w02_model_handoff as w02
import p3l_w04_one_call_gate as w04


class PublicChecklistPromptTests(unittest.TestCase):
    def test_public_rules_are_explicit_without_hidden_oracle(self):
        handoff = w02.build()
        prompt = handoff["prompt"]
        for required in (
            "fixes=[] MUST be valid",
            "containing '' MUST be",
            "len(fixes)>12",
            "len(item.encode('utf-8'))<=128",
            "len(change.encode('utf-8'))<=256",
            "NUL, LF, ESC",
            "C0/C1",
            "Preserve valid Korean text",
        ):
            with self.subTest(required=required):
                self.assertIn(required, prompt)
        self.assertNotIn("heldout_p3f_development_ledger", prompt)
        self.assertNotIn("test_reject_empty_fix_entry", prompt)
        self.assertNotIn("FrozenLedgerInputSecurity", prompt)

    def test_prompt_sha_and_w04_one_attempt_are_bound_to_same_input(self):
        handoff = w02.build()
        gate = w04.plan()
        self.assertEqual(handoff["prompt_sha256"], hashlib.sha256(handoff["prompt"].encode("utf-8")).hexdigest())
        self.assertEqual(gate["prompt_sha256"], handoff["prompt_sha256"])
        self.assertEqual(gate["decision"], "allow_one_model_call")
        self.assertEqual(gate["model_calls"], 0)
        self.assertFalse(gate["model_invoked"])
        self.assertFalse(handoff["candidate_produced"])
        self.assertFalse(handoff["merge_authorized"])
        self.assertLessEqual(handoff["prompt_utf8_bytes"], 7000)


if __name__ == "__main__":
    unittest.main()
