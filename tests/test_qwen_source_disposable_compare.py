import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from qwen_source_guard import EXPECTED, TARGET, TASK, inspect_line
from qwen_source_trial import MODEL, evaluate_response, normalize_model_line
from qwen_source_disposable_compare import verify_and_stage, compare

def artifacts(workspace):
    source = (ROOT / TARGET).read_text(encoding="utf-8")
    proposal = inspect_line(EXPECTED, source)
    candidate = {"provider": "qwen", "status": "proposal",
                 "task_id": TASK["task_id"], "raw_response": EXPECTED,
                 "line": EXPECTED,
                 "source_patch": proposal["patch"],
                 "source_sha256": proposal["source_sha256"],
                 "model_line_sha256": proposal["model_line_sha256"]}
    candidate_path = pathlib.Path(workspace) / "candidate.json"
    serialized = json.dumps(candidate, indent=2, sort_keys=True) + "\n"
    candidate_path.write_text(serialized, encoding="utf-8")
    inference = {"status": "accepted_for_disposable_review", "model": MODEL,
                 "task_id": TASK["task_id"], "model_calls": 1,
                 "source_checkout_modified": False, "model_code_executed": False,
                 "merge_authorized": False, "source_sha256": proposal["source_sha256"],
                 "candidate_sha256": hashlib.sha256(serialized.encode()).hexdigest(),
                 "attempts": [{"status": "accepted", "response_sha256":
                               proposal["model_line_sha256"]}]}
    inference_path = pathlib.Path(workspace) / "inference.json"
    inference_path.write_text(json.dumps(inference), encoding="utf-8")
    return inference_path, candidate_path

class RealSourceRepairTests(unittest.TestCase):
    def test_source_guard_trial_accepts_real_executable_condition(self):
        source = (ROOT / TARGET).read_text(encoding="utf-8")
        result = evaluate_response(EXPECTED, source)
        self.assertEqual(result["status"], "accepted_for_disposable_review")
        self.assertFalse(result["patch_applied_to_checkout"])

    def test_fenced_single_source_line_normalized_without_changing_semantics(self):
        raw = chr(96) * 3 + "python\n" + EXPECTED.lstrip() + "\n" + chr(96) * 3
        self.assertEqual(normalize_model_line(raw), EXPECTED)
        source = (ROOT / TARGET).read_text(encoding="utf-8")
        self.assertEqual(evaluate_response(raw, source)["status"],
                         "accepted_for_disposable_review")

    def test_fenced_multiple_lines_still_rejected(self):
        raw = chr(96) * 3 + "python\n" + EXPECTED.lstrip() + "\\nimport os\\n" + chr(96) * 3
        with self.assertRaises(ValueError):
            normalize_model_line(raw)

    def test_source_guard_trial_rejects_irrelevant_model_code(self):
        source = (ROOT / TARGET).read_text(encoding="utf-8")
        with self.assertRaises(ValueError):
            evaluate_response("    import os", source)

    def test_staging_changes_only_disposable_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            inference, candidate = artifacts(temp)
            checkout = (ROOT / TARGET).read_bytes()
            result = verify_and_stage(ROOT, inference, candidate,
                                      pathlib.Path(temp) / "staged")
            staged = pathlib.Path(temp) / "staged"
            original = (staged / "baseline" / TARGET).read_text(encoding="utf-8")
            modified = (staged / "candidate" / TARGET).read_text(encoding="utf-8")
            self.assertIn(EXPECTED, modified)
            self.assertNotIn(EXPECTED, original)
            self.assertEqual((ROOT / TARGET).read_bytes(), checkout)
            self.assertTrue(result["disposable_patch_only"])

    def test_tampered_candidate_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            inference, candidate = artifacts(temp)
            obj = json.loads(candidate.read_text(encoding="utf-8"))
            obj["line"] = "    if True:"
            candidate.write_text(json.dumps(obj), encoding="utf-8")
            with self.assertRaises(ValueError):
                verify_and_stage(ROOT, inference, candidate, pathlib.Path(temp) / "stage")

    def test_forged_model_invocation_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            inference, candidate = artifacts(temp)
            obj = json.loads(inference.read_text(encoding="utf-8"))
            obj["model_calls"] = 0
            inference.write_text(json.dumps(obj), encoding="utf-8")
            with self.assertRaises(ValueError):
                verify_and_stage(ROOT, inference, candidate, pathlib.Path(temp) / "stage")

    def test_duplicate_evidence_keys_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            inference, candidate = artifacts(temp)
            candidate.write_text('{"status":"proposal","status":"proposal"}')
            with self.assertRaises(ValueError):
                verify_and_stage(ROOT, inference, candidate, pathlib.Path(temp) / "stage")

    def test_negative_control_required_even_if_regression_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            inference, candidate = artifacts(temp)
            def fake_test(workspace, pattern):
                if pattern == "test_feedback_controller.py":
                    return {"passed": True, "tests_run": 8}
                return {"passed": True, "tests_run": 1}
            with patch("qwen_source_disposable_compare._test", side_effect=fake_test):
                result = compare(ROOT, inference, candidate)
            self.assertEqual(result["status"], "regression_failed")
            self.assertFalse(result["merge_authorized"])

    def test_baseline_failure_candidate_success_passes_isolated_comparison(self):
        with tempfile.TemporaryDirectory() as temp:
            inference, candidate = artifacts(temp)
            def fake_test(workspace, pattern):
                if pattern == "test_feedback_controller.py":
                    return {"passed": True, "tests_run": 8}
                return {"passed": "candidate" in str(workspace),
                        "tests_run": 1}
            with patch("qwen_source_disposable_compare._test", side_effect=fake_test):
                result = compare(ROOT, inference, candidate)
            self.assertEqual(result["status"], "isolated_source_repair_passed")
            self.assertTrue(result["model_generated_code_executed_in_disposable_container"])
            self.assertFalse(result["source_checkout_modified"])
            self.assertFalse(result["merge_authorized"])

if __name__ == "__main__":
    unittest.main()
