"""Offline tests of the AST microtask generation + provenance gate."""
import hashlib
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from qwen_source_microtask import (EXPECTED, KINDS, MAX_ATTEMPTS_PER_KIND,
                                  build_candidate, normalize_fragment,
                                  run_microtask_trials)
from qwen_source_disposable_compare import verify_and_stage
from qwen_source_guard import TARGET, TASK
from qwen_source_trial import MODEL


class QwenMicrotaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / TARGET).read_text(encoding="utf-8")

    def test_both_fragments_are_ast_validated_and_assembled(self):
        trial = run_microtask_trials(lambda kind, prompt: EXPECTED[kind], self.source)
        self.assertEqual(trial["status"], "accepted_for_disposable_review")
        self.assertEqual(trial["model_calls"], 2)
        self.assertEqual([r["kind"] for r in trial["attempts"]], list(KINDS))
        self.assertEqual(trial["candidate"]["generation_mode"], "ast_microfragments_v1")
        self.assertIn('proposal["cycle"] < 1:', trial["candidate"]["line"])

    def test_type_bool_semantic_shortcut_rejected(self):
        with self.assertRaises(ValueError):
            normalize_fragment("type", 'isinstance(proposal.get("cycle"), int) is False')

    def test_side_effect_and_injection_rejected(self):
        for raw in ('__import__("os").system("id")',
                    EXPECTED["type"] + "\nimport os",
                    'type(proposal.get("cycle")) is not int or True'):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    normalize_fragment("type", raw)

    def test_fenced_single_expression_is_allowed(self):
        fence = chr(96) * 3
        raw = fence + "python\n" + EXPECTED["type"] + "\n" + fence
        self.assertEqual(normalize_fragment("type", raw), EXPECTED["type"])

    def test_max_retries_stops_without_candidate(self):
        calls = []
        def always_bad(kind, prompt):
            calls.append(kind)
            return "True"
        trial = run_microtask_trials(always_bad, self.source)
        self.assertEqual(trial["status"], "model_proposal_rejected")
        self.assertIsNone(trial["candidate"])
        self.assertEqual(calls, ["type"] * MAX_ATTEMPTS_PER_KIND)

    def test_failed_first_attempt_can_recover(self):
        calls = {"type": 0, "range": 0}
        def retry_once(kind, prompt):
            calls[kind] += 1
            return "True" if calls[kind] == 1 else EXPECTED[kind]
        trial = run_microtask_trials(retry_once, self.source)
        self.assertEqual(trial["status"], "accepted_for_disposable_review")
        self.assertEqual(trial["model_calls"], 4)
        self.assertEqual([a["status"] for a in trial["attempts"]],
                         ["rejected", "accepted", "rejected", "accepted"])

    def test_missing_fragment_fails_closed(self):
        with self.assertRaises(ValueError):
            build_candidate({"type": EXPECTED["type"]}, self.source)

    def _evidence(self, directory, trial):
        candidate = trial["candidate"]
        content = json.dumps(candidate, sort_keys=True, indent=2) + "\n"
        candidate_path = pathlib.Path(directory) / "candidate.json"
        candidate_path.write_text(content, encoding="utf-8")
        report = {"status": trial["status"], "model": MODEL,
                  "task_id": TASK["task_id"], "model_calls": trial["model_calls"],
                  "attempts": trial["attempts"],
                  "source_sha256": candidate["source_sha256"],
                  "candidate_sha256": hashlib.sha256(content.encode()).hexdigest(),
                  "source_checkout_modified": False, "model_code_executed": False,
                  "merge_authorized": False}
        report_path = pathlib.Path(directory) / "inference.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return report_path, candidate_path

    def test_microtask_evidence_stages_disposable_patch(self):
        trial = run_microtask_trials(lambda kind, prompt: EXPECTED[kind], self.source)
        with tempfile.TemporaryDirectory() as directory:
            inference, candidate = self._evidence(directory, trial)
            original = (ROOT / TARGET).read_bytes()
            staged = pathlib.Path(directory) / "stage"
            result = verify_and_stage(ROOT, inference, candidate, staged)
            self.assertTrue(result["disposable_patch_only"])
            self.assertIn(trial["candidate"]["line"],
                          (staged / "candidate" / TARGET).read_text())
            self.assertEqual(original, (ROOT / TARGET).read_bytes())

    def test_tampered_microtask_response_is_blocked(self):
        trial = run_microtask_trials(lambda kind, prompt: EXPECTED[kind], self.source)
        with tempfile.TemporaryDirectory() as directory:
            inference, candidate = self._evidence(directory, trial)
            data = json.loads(candidate.read_text())
            data["microtask_responses"][0]["raw_response"] = "True"
            changed = json.dumps(data, sort_keys=True, indent=2) + "\n"
            candidate.write_text(changed)
            report = json.loads(inference.read_text())
            report["candidate_sha256"] = hashlib.sha256(changed.encode()).hexdigest()
            inference.write_text(json.dumps(report))
            with self.assertRaises(ValueError):
                verify_and_stage(ROOT, inference, candidate,
                                 pathlib.Path(directory) / "stage")

    def test_forged_accepted_attempt_hash_is_blocked(self):
        trial = run_microtask_trials(lambda kind, prompt: EXPECTED[kind], self.source)
        with tempfile.TemporaryDirectory() as directory:
            inference, candidate = self._evidence(directory, trial)
            report = json.loads(inference.read_text())
            report["attempts"][0]["response_sha256"] = "0" * 64
            inference.write_text(json.dumps(report))
            with self.assertRaises(ValueError):
                verify_and_stage(ROOT, inference, candidate,
                                 pathlib.Path(directory) / "stage")


if __name__ == "__main__":
    unittest.main()
