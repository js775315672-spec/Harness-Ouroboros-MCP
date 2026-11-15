import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from autonomous_loop_controller import transition

STATE = {"cycle": 1, "attempt": 1, "phase": "await_evidence"}
PASS = {"source_changed": True, "commit": "a" * 40,
        "ci_url": "https://github.com/example/repo/actions/runs/123",
        "checks": {"harness": "pass", "ouroboros": "pass",
                   "regression": "pass", "secrets": "pass"}}

class LoopControllerTests(unittest.TestCase):
    def test_initial_wait_does_not_claim_execution(self):
        result = transition(STATE)
        self.assertEqual(result["decision"], "await_external_executor")
        self.assertFalse(result["model_connected"])
        self.assertFalse(result["code_executed"])

    def test_success_advances_only_with_supplied_evidence(self):
        result = transition(STATE, PASS)
        self.assertEqual(result["decision"], "request_next_external_task")
        self.assertEqual(result["state"]["cycle"], 2)
        self.assertFalse(result["independent_ci_attested"])

    def test_verification_only_is_rejected(self):
        with self.assertRaises(ValueError):
            transition(STATE, dict(PASS, source_changed=False))

    def test_missing_check_is_rejected(self):
        with self.assertRaises(ValueError):
            transition(STATE, dict(PASS, checks={"harness": "pass"}))

    def test_failure_requests_fix(self):
        checks = dict(PASS["checks"], regression="fail")
        result = transition(STATE, dict(PASS, checks=checks))
        self.assertEqual(result["decision"], "request_external_fix")
        self.assertEqual(result["state"]["attempt"], 2)

    def test_retry_budget_stops(self):
        checks = dict(PASS["checks"], secrets="fail")
        result = transition(dict(STATE, attempt=5), dict(PASS, checks=checks))
        self.assertEqual(result["decision"], "stop")

    def test_cycle_limit_stops_without_merging(self):
        result = transition(dict(STATE, cycle=30), PASS)
        self.assertEqual(result["decision"], "human_review")
        self.assertFalse(result["merge_authorized"])

    def test_invalid_commit_rejected(self):
        with self.assertRaises(ValueError):
            transition(STATE, dict(PASS, commit="fake"))

    def test_unexpected_state_rejected(self):
        with self.assertRaises(ValueError):
            transition(dict(STATE, privileged=True))

if __name__ == "__main__":
    unittest.main()
