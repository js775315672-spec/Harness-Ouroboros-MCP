"""Fail-closed OFC P0 assertions; existing cycle_registry tests cover concurrency/restart."""
import hashlib
import pathlib
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from evolution_core.contracts import AgentID, Candidate, EvidenceRecord, ExperimentSpec, Verdict, GateDecision
from evolution_core.planner import Planner
from evolution_core.runner import Runner
from evolution_core.resources import ResourceGovernor
from evolution_core.evaluator import Evaluator
from evolution_core.ledger import Ledger
from evolution_core.gate import GrowthGate
from evolution_core.security import require_manual_merge
from evolution_core.dashboard import render_dashboard, replace_region, BEGIN, END

A = "a" * 40
B = "b" * 40
C = "c" * 64
D = "d" * 64

def fixture(agent=AgentID.OUROBOROS, sha=B, checks=("independent", "regression", "security"),
            verdict=Verdict.VERIFIED, evaluator_id="isolated-evaluator", independent=True, metrics=None):
    spec = ExperimentSpec("cycle-1", agent, A, "checkpoint prevents duplicates", "duplicate_rate",
                          C, "1", 60)
    candidate = Candidate("cycle-1", B, "qwen-pinned", C, D)
    record = EvidenceRecord("cycle-1", agent, sha, evaluator_id, "1", C, "sha256:environment",
                            verdict, checks, metrics or {}, D,
                            "https://github.com/example/repo/actions/runs/1", independent)
    return spec, candidate, record

class CoreSafetyTest(unittest.TestCase):
    def test_T01_isolation(self):
        spec, candidate, record = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "ouroboros.sqlite3"
            Ledger(path, AgentID.OUROBOROS).append(record)
            with self.assertRaises(PermissionError):
                Ledger(path, AgentID.CERBERUS)
            other = Ledger(pathlib.Path(tmp) / "cerberus.sqlite3", AgentID.CERBERUS)
            with self.assertRaises(PermissionError):
                other.append(record)

    def test_T02_unrecognized_agent(self):
        with self.assertRaises(ValueError):
            ExperimentSpec("x", "invalid", A, "hyp", "metric", C, "1", 60)

    def test_T03_candidate_sha_mismatch(self):
        s, c, e = fixture(sha=A)
        self.assertFalse(Evaluator().validate(s, c, e))
        self.assertEqual(GrowthGate().decide(s, c, [e]), GateDecision.REJECT)

    def test_T04_missing_mandatory_checks(self):
        s, c, e = fixture(checks=("independent",))
        self.assertEqual(GrowthGate().decide(s, c, [e]), GateDecision.HOLD)

    def test_T05_self_approved_evaluation(self):
        s, c, e = fixture(evaluator_id="ouroboros")
        self.assertEqual(GrowthGate().decide(s, c, [e]), GateDecision.REJECT)

    def test_T06_failed_model_call_never_issues_candidate(self):
        s, _, _ = fixture()
        with self.assertRaisesRegex(RuntimeError, "P1_BLOCKED"):
            Runner().execute(s)

    def test_T07_duplicate_evidence_replay(self):
        _, _, e = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            l = Ledger(pathlib.Path(tmp) / "events.sqlite3", AgentID.OUROBOROS)
            l.append(e)
            with self.assertRaises(sqlite3.IntegrityError):
                l.append(e)
            self.assertTrue(l.verify_chain())

    def test_T09_artifact_tampering(self):
        _, _, e = fixture()
        self.assertFalse(Evaluator.check_artifact(e, b"forged artifact"))

    def test_T10_critical_regression(self):
        s, c, e = fixture(verdict=Verdict.REGRESSION, metrics={"critical_regression": True})
        self.assertEqual(GrowthGate().decide(s, c, [e]), GateDecision.HALT)

    def test_T11_automatic_main_merge_forbidden(self):
        with self.assertRaises(PermissionError):
            require_manual_merge("main")

    def test_T12_missing_readme_evidence(self):
        text = render_dashboard()
        self.assertIn("UNKNOWN", text)
        self.assertIn("NOT_MEASURED", text)
        original = "intro\n" + BEGIN + "\nOLD\n" + END + "\nfooter\n"
        result = replace_region(original, text)
        self.assertTrue(result.startswith("intro\n"))
        self.assertTrue(result.endswith("\nfooter\n"))

    def test_happy_path_requires_review_not_promotion(self):
        s, c, e = fixture()
        self.assertEqual(GrowthGate().decide(s, c, [e]), GateDecision.REVIEW_REQUIRED)

    def test_inconclusive_holds(self):
        s, c, e = fixture(verdict=Verdict.INCONCLUSIVE)
        self.assertEqual(GrowthGate().decide(s, c, [e]), GateDecision.HOLD)

    def test_chain_detects_db_modified_rows(self):
        _, _, e = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "db.sqlite3"
            ledger = Ledger(path, AgentID.OUROBOROS)
            ledger.append(e)
            with sqlite3.connect(path) as db:
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute("UPDATE events SET payload='fake'")
                db.execute("DROP TRIGGER forbid_event_update")
                db.execute("UPDATE events SET payload='fake'")
            self.assertFalse(ledger.verify_chain())

    def test_policy_and_planner_are_scoped(self):
        s, _, _ = fixture()
        self.assertEqual(Planner(AgentID.OUROBOROS).plan(s), s)
        self.assertTrue(ResourceGovernor(AgentID.OUROBOROS, 90).authorize(s))
        self.assertFalse(ResourceGovernor(AgentID.FENRIR, 90).authorize(s))
        with self.assertRaises(PermissionError):
            Planner(AgentID.CERBERUS).plan(s)

if __name__ == "__main__":
    unittest.main()
