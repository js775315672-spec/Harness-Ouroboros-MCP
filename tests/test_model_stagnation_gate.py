"""Adversarial model-response stagnation tests; no model or network calls."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from model_stagnation_gate import evaluate
from feedback_controller import feedback
from task_selector import select

def sha(data):
    return hashlib.sha256(data.encode("utf-8")).hexdigest()

TASK = sha("p3a:actual-existing-repo-policy-code")
MODEL = sha("Qwen2.5-Coder-7B:official-Q4_K_M-v1")
BASE = sha("real-existing-source-before-patch")
CHANGED = sha("candidate-source-v2")
CTX = {"task_sha256": TASK, "model_sha256": MODEL,
       "baseline_source_sha256": BASE}

def row(attempt, raw="def policy(...): pass", outcome="static_rejected",
        reason="model source changed nothing", candidate=None):
    return {
        "attempt": attempt, **CTX, "raw_response": raw,
        "response_sha256": sha(raw), "candidate_source_sha256": candidate,
        "outcome": outcome, "rejection_reason": reason,
        "independent_replay": True
    }

def checks(failed=("regression",)):
    names = ("harness","ouroboros","regression","secrets")
    return {x:{"status":"fail" if x in failed else "pass",
               "log":"check failed" if x in failed else ""} for x in names}


class ModelStagnationGateTests(unittest.TestCase):
    def test_fresh_scope_permits_only_one_call(self):
        r=evaluate([], **CTX)
        self.assertEqual(r["decision"],"allow_one_model_call")
        self.assertEqual(r["next_attempt"],1)
        self.assertIs(r["model_call_performed"],False)
        self.assertIs(r["external_ci_attested"],False)

    def test_single_noop_gets_one_distinct_feedback_chance(self):
        r=evaluate([row(1)],**CTX)
        self.assertEqual(r["decision"],"allow_one_model_call")
        self.assertEqual(r["next_attempt"],2)

    def test_duplicate_p3a_p3b_source_stops_before_third_model_call(self):
        # Reproduces the real P3a/P3b observed behavior in isolated, synthetic records.
        history=[row(1),row(2)]
        result=evaluate(history,**CTX)
        self.assertEqual(result["decision"],"stop")
        self.assertEqual(result["reason"],"duplicate_model_response")
        self.assertIs(result["model_call_performed"],False)
        self.assertIs(result["merge_authorized"],False)

    def test_distinct_raw_responses_both_noop_also_stop(self):
        history=[row(1),row(2,raw="def policy( proposal, branch ): pass")]
        r=evaluate(history,**CTX)
        self.assertEqual(r["reason"],"repeated_unchanged_source")

    def test_two_distinct_failed_source_changes_permit_one_last_call(self):
        history=[row(1,raw="candidate-a",outcome="candidate_failed",
                     reason="",candidate=CHANGED),
                 row(2,raw="candidate-b",outcome="candidate_failed",
                     reason="",candidate=sha("candidate-b-source"))]
        r=evaluate(history,**CTX)
        self.assertEqual(r["decision"],"allow_one_model_call")
        self.assertEqual(r["next_attempt"],3)

    def test_three_distinct_failures_exhaust_budget(self):
        history=[row(i,raw="v%d"%i,outcome="candidate_failed",
                     reason="",candidate=sha("code%d"%i))
                 for i in range(1,4)]
        r=evaluate(history,**CTX)
        self.assertEqual(r["reason"],"retry_budget_exhausted")

    def test_candidate_passed_is_review_not_new_call(self):
        r=evaluate([row(1,"good source","candidate_passed","",CHANGED)],**CTX)
        self.assertEqual(r["decision"],"stop")
        self.assertEqual(r["reason"],"passing_candidate_requires_human_review")
        self.assertFalse(r["merge_authorized"])
        self.assertFalse(r["external_ci_attested"])

    def test_subsequent_model_call_after_reported_pass_rejected(self):
        h=[row(1,"passing source","candidate_passed","",CHANGED),row(2)]
        with self.assertRaises(ValueError):
            evaluate(h,**CTX)

    def test_raw_sha_forgery_rejected(self):
        h=row(1);h["response_sha256"]="f"*64
        with self.assertRaises(ValueError):evaluate([h],**CTX)

    def test_evidence_bound_to_exact_task(self):
        h=row(1);h["task_sha256"]=sha("other task")
        with self.assertRaises(ValueError):evaluate([h],**CTX)

    def test_evidence_bound_to_exact_model(self):
        h=row(1);h["model_sha256"]=sha("replacement model")
        with self.assertRaises(ValueError):evaluate([h],**CTX)

    def test_evidence_bound_to_exact_base_source(self):
        h=row(1);h["baseline_source_sha256"]=sha("new checked out source")
        with self.assertRaises(ValueError):evaluate([h],**CTX)

    def test_independent_replay_is_explicitly_required(self):
        h=row(1);h["independent_replay"]=False
        with self.assertRaises(ValueError):evaluate([h],**CTX)

    def test_skipped_attempt_number_rejected(self):
        with self.assertRaises(ValueError):evaluate([row(1),row(3)],**CTX)

    def test_bool_attempt_rejected(self):
        h=row(1);h["attempt"]=True
        with self.assertRaises(ValueError):evaluate([h],**CTX)

    def test_unexpected_privilege_field_rejected(self):
        h=row(1);h["merge_authorized"]=True
        with self.assertRaises(ValueError):evaluate([h],**CTX)

    def test_static_rejection_cannot_include_candidate_source(self):
        h=row(1);h["candidate_source_sha256"]=CHANGED
        with self.assertRaises(ValueError):evaluate([h],**CTX)

    def test_failed_candidate_cannot_equal_original_source(self):
        h=row(1,"failed","candidate_failed","",BASE)
        with self.assertRaises(ValueError):evaluate([h],**CTX)

    def test_failed_candidate_must_have_real_source(self):
        h=row(1,"failed","candidate_failed","",None)
        with self.assertRaises(ValueError):evaluate([h],**CTX)

    def test_passed_candidate_must_not_have_failure_reason(self):
        h=row(1,"passed","candidate_passed","bad",CHANGED)
        with self.assertRaises(ValueError):evaluate([h],**CTX)

    def test_raw_response_length_bounded(self):
        h=row(1,raw="x"*6001)
        with self.assertRaises(ValueError):evaluate([h],**CTX)

    def test_raw_response_control_bytes_rejected(self):
        for raw in ("x\x00","x\x1b","x\r"):
            with self.subTest(raw=repr(raw)):
                with self.assertRaises(ValueError):
                    evaluate([row(1,raw=raw)],**CTX)

    def test_boolean_max_attempts_forbidden(self):
        with self.assertRaises(ValueError):evaluate([],**CTX,max_attempts=True)

    def test_history_never_mutated(self):
        h=[row(1)]
        original=copy.deepcopy(h)
        evaluate(h,**CTX)
        self.assertEqual(h,original)

    def test_optional_feedback_integration_stops_duplication(self):
        r=feedback(select(),checks(),attempt=2,
                   model_history=[row(1),row(2)],model_context=CTX)
        self.assertEqual(r["decision"],"stop")
        self.assertEqual(r["reason"],"duplicate_model_response")
        self.assertFalse(r["model_call_performed"])

    def test_optional_feedback_integration_requests_one_fix(self):
        r=feedback(select(),checks(failed=()),attempt=1,
                   model_history=[row(1)],model_context=CTX)
        self.assertEqual(r["decision"],"request_fix")
        self.assertIn("model_candidate",r["failed_checks"])
        self.assertEqual(r["model_retry_gate"]["next_attempt"],2)
        self.assertFalse(r["model_call_performed"])

    def test_optional_context_without_history_fail_closed(self):
        with self.assertRaises(ValueError):
            feedback(select(),checks(),model_context=CTX)

    def test_no_new_context_preserves_existing_feedback_behavior(self):
        r=feedback(select(),checks(failed=()),attempt=1)
        self.assertEqual(r["decision"],"review")
        self.assertNotIn("model_retry_gate",r)

    def test_cli_stops_with_nonzero_on_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            evidence=folder/"prior.json"
            evidence.write_text(json.dumps([row(1),row(2)]),encoding="utf-8")
            cmd=[sys.executable,str(ROOT/"scripts/model_stagnation_gate.py"),
                 "--history",str(evidence),"--task-sha256",TASK,
                 "--model-sha256",MODEL,"--baseline-source-sha256",BASE,
                 "--output",str(folder/"verdict.json")]
            proc=subprocess.run(cmd,capture_output=True,text=True,timeout=10)
            self.assertEqual(proc.returncode,2)
            r=json.loads((folder/"verdict.json").read_text())
            self.assertEqual(r["decision"],"stop")

    def test_cli_fresh_model_call_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            evidence=folder/"prior.json"
            evidence.write_text("[]",encoding="utf-8")
            cmd=[sys.executable,str(ROOT/"scripts/model_stagnation_gate.py"),
                 "--history",str(evidence),"--task-sha256",TASK,
                 "--model-sha256",MODEL,"--baseline-source-sha256",BASE]
            proc=subprocess.run(cmd,capture_output=True,text=True,timeout=10)
            self.assertEqual(proc.returncode,0)
            self.assertIn("allow_one_model_call",proc.stdout)


if __name__ == "__main__":
    unittest.main()
