"""P3g offline provenance gates: old 24/25 model output remains immutable."""
from pathlib import Path
import ast
from copy import deepcopy
import json
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import p3g_qwen_ledger_feedback_repair as s

class P3gOriginalFeedbackContractTests(unittest.TestCase):
    def test_exact_1487_byte_original_model_response(self):
        original=s.file_bytes(ROOT,s.PREVIOUS)
        self.assertEqual(len(original),1487)
        self.assertEqual(s.digest(original),s.PREVIOUS_SHA256)

    def test_prior_model_did_generate_real_source_change(self):
        before=(ROOT/s.TARGET).read_text()
        proposal=s.inspect_replacement(s.file_bytes(ROOT,s.PREVIOUS).decode())
        after,diff=s.patch_original(before,proposal)
        self.assertNotEqual(after,before)
        self.assertIn("def validate(",diff)

    def test_prior_output_missing_explicit_empty_fix_check(self):
        src=s.inspect_replacement(s.file_bytes(ROOT,s.PREVIOUS).decode())
        self.assertNotIn("not x.strip()",src)
        self.assertNotIn("not x or ",src)

    def test_second_prompt_binds_actual_failed_source_and_feedback(self):
        p=s.source_prompt((ROOT/s.TARGET).read_text(),ROOT)
        self.assertIn("FIRST QWEN SOURCE IMPLEMENTATION",p)
        self.assertIn("24/25",p)
        self.assertIn("NONEMPTY",p)
        self.assertIn("empty string inside fixes",p)
        self.assertLess(len(p.encode()),5000)

    def test_second_prompt_never_exposes_hidden_test_case_source(self):
        p=s.source_prompt((ROOT/s.TARGET).read_text(),ROOT)
        self.assertNotIn("test_reject_empty_fix_entry",p)
        self.assertNotIn("FrozenLedgerInputSecurity",p)

    def test_unchanged_25_case_acceptance_contract(self):
        self.assertEqual(s.HOLDOUT_COUNT,10)
        self.assertEqual(s.REGRESSION_TESTS,
                         {"test_development_ledger.py":8,
                          "test_ci_attestation.py":7})

    def test_nonempty_fix_rule_is_only_feedback_not_test_edit(self):
        original=(ROOT/"tests/heldout_p3f_development_ledger.py").read_text()
        self.assertEqual(original.count("    def test_"),10)
        self.assertIn("test_reject_empty_fix_entry",original)

    def test_old_original_sha_bound_to_new_prompt(self):
        with patch.object(s,"git_identity",return_value=None):
            _,prompt,receipt=s.context(ROOT,"a"*40)
        self.assertEqual(receipt["prior_first_model_sha256"],s.PREVIOUS_SHA256)
        self.assertEqual(receipt["prompt_sha256"],s.digest(prompt.encode()))
        self.assertIn(s.PREVIOUS,receipt["trusted_inputs_sha256"])
        self.assertFalse(receipt["merge_authorized"])

    def test_previous_reply_cannot_be_appended_with_other_code(self):
        reply=s.file_bytes(ROOT,s.PREVIOUS).decode()
        with self.assertRaises(ValueError):
            s.inspect_replacement(reply+"\nimport os\n")

    def test_replay_forged_completion_does_not_authorize_merge(self):
        with patch.object(s,"git_identity",return_value=None):
            _,_,base=s.context(ROOT,"a"*40)
            fake={**base,"model_calls":1,"raw_response":"def validate(records): pass",
                  "response_sha256":s.digest(b"def validate(records): pass"),
                  "outcome":"real_source_patch_passed","merge_authorized":True}
            with self.assertRaises(ValueError):
                s.replay(ROOT,"a"*40,fake)

    def test_replay_binds_each_suite_and_omits_test_logs(self):
        commit = "a" * 40
        raw = s.file_bytes(ROOT, s.PREVIOUS).decode()
        suites = {name: {"tests_run": count, "passed": name in s.REGRESSION_TESTS,
                         "log_tail": "private diagnostic"}
                  for name, count in s.FROZEN_SUITES.items()}
        outcome = {"status": "real_source_patch_failed", "baseline": suites,
                   "candidate": deepcopy(suites)}
        with patch.object(s, "git_identity"), patch.object(s, "check_model"), \
             patch.object(s, "infer", return_value=(raw, 1)), \
             patch.object(s, "grade", return_value=outcome):
            record = s.run(ROOT, commit, None, None, None)
            verdict = s.replay(ROOT, commit, record)
            self.assertFalse(verdict["candidate_passed"])
            self.assertEqual(verdict["suite_results"]["candidate"]["heldout_p3f_development_ledger.py"],
                             {"passed": False, "tests_run": 10})
            self.assertNotIn("private diagnostic", repr(verdict))

            changed = deepcopy(record)
            changed["grade"]["candidate"]["test_ci_attestation.py"]["passed"] = False
            with self.assertRaisesRegex(ValueError, "independent frozen suite results disagreed"):
                s.replay(ROOT, commit, changed)

    def test_retry_prompt_uses_verified_feedback_without_hidden_test_source(self):
        with patch.object(s, "git_identity"):
            _, prompt, contract = s.context(ROOT, "a" * 40, retry_p3g=True)
        self.assertEqual(contract["variant"], s.RETRY_VARIANT)
        self.assertEqual(contract["prior_replay_run"], 43891791328)
        self.assertEqual(contract["prompt_sha256"], s.digest(prompt.encode()))
        self.assertEqual(len(set(contract["rejected_function_fingerprints"])), 2)
        self.assertIn("discarded that value before its entry validation", prompt)
        self.assertNotIn("test_reject_empty_fix_entry", prompt)

    def test_alternate_model_uses_identical_prompt_and_frozen_inputs(self):
        with patch.object(s, "git_identity"):
            _, prompt, previous = s.context(ROOT, "a" * 40, retry_p3g=True)
            _, alternate_prompt, alternate = s.context(ROOT, "a" * 40, retry_p3g=True, model_id="14b")
        self.assertEqual(prompt, alternate_prompt)
        self.assertEqual(alternate["trusted_inputs_sha256"], previous["trusted_inputs_sha256"])
        self.assertEqual(alternate["rejected_function_fingerprints"], previous["rejected_function_fingerprints"])
        self.assertEqual(alternate["variant"], s.ALTERNATE_VARIANT)
        self.assertEqual(alternate["model_sha256"], s.approved_model("14b")["sha256"])
        with self.assertRaisesRegex(ValueError, "requires the frozen feedback"):
            s.context(ROOT, "a" * 40, model_id="14b")

    def test_retry_stops_either_repeated_candidate_before_docker(self):
        latest = json.loads(s.file_bytes(ROOT, s.P3G_FAILURE))["raw_response"]
        earlier = s.file_bytes(ROOT, s.PREVIOUS).decode("utf-8")
        for raw in (latest, earlier):
            with self.subTest(), patch.object(s, "git_identity"), patch.object(s, "check_model"), \
                 patch.object(s, "infer", return_value=("\n" + raw + "\n", 1)), patch.object(s, "grade") as grade:
                record = s.run(ROOT, "a" * 40, None, None, None, retry_p3g=True)
                self.assertEqual(record["outcome"], "static_rejected")
                self.assertIn("previously rejected ledger implementation", record["static_reject_reason"])
                verdict = s.replay(ROOT, "a" * 40, record, retry_p3g=True)
                self.assertFalse(verdict["candidate_passed"])
                grade.assert_not_called()

    def test_retry_refuses_modified_frozen_inputs(self):
        originals = {name: s.file_bytes(ROOT, name) for name in (s.TARGET, *s.SUPPORT, s.PREVIOUS)}
        originals[s.SUPPORT[-1]] += b"\n# changed"
        with self.assertRaisesRegex(ValueError, "source, test or response digests changed"):
            s.retry_context(ROOT, originals)
        with patch.object(s, "file_bytes", return_value=b"{}"):
            with self.assertRaisesRegex(ValueError, "pinned P3g replay evidence changed"):
                s.retry_context(ROOT, originals)

    def test_retry_new_candidate_reaches_grade_and_independent_replay(self):
        previous = s.file_bytes(ROOT, s.PREVIOUS).decode("utf-8")
        raw = previous.replace("return len(records)", "return len(seen)")
        self.assertNotEqual(raw, previous)
        suites = {name: {"tests_run": count, "passed": name in s.REGRESSION_TESTS}
                  for name, count in s.FROZEN_SUITES.items()}
        outcome = {"status": "real_source_patch_failed", "baseline": suites, "candidate": suites}
        with patch.object(s, "git_identity"), patch.object(s, "check_model"), \
             patch.object(s, "infer", return_value=(raw, 1)), patch.object(s, "grade", return_value=outcome) as grade:
            record = s.run(ROOT, "a" * 40, None, None, None, retry_p3g=True)
            self.assertEqual(record["outcome"], "real_source_patch_failed")
            verdict = s.replay(ROOT, "a" * 40, record, retry_p3g=True)
            self.assertEqual(verdict["variant"], s.RETRY_VARIANT)
            self.assertFalse(verdict["candidate_passed"])
            self.assertEqual(grade.call_count, 2)

if __name__=="__main__":
    unittest.main()
