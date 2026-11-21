"""No promotion API exists here: REVIEW_REQUIRED requires separate human approval."""
from .contracts import AgentID, Candidate, EvidenceRecord, ExperimentSpec, GateDecision, Verdict
from .evaluator import Evaluator

class GrowthGate:
    REQUIRED = frozenset({"independent", "regression", "security"})

    def decide(self, spec: ExperimentSpec, candidate: Candidate, evidence: list[EvidenceRecord]) -> GateDecision:
        if not evidence:
            return GateDecision.HOLD
        if candidate.experiment_id != spec.experiment_id:
            return GateDecision.REJECT
        if any(x.verdict == Verdict.SAFETY_VIOLATION or
               (x.verdict == Verdict.REGRESSION and x.metrics.get("critical_regression") is True) for x in evidence):
            return GateDecision.HALT
        if any(not Evaluator().validate(spec, candidate, x) for x in evidence):
            return GateDecision.REJECT
        if any(x.verdict in (Verdict.INVALID, Verdict.REGRESSION) for x in evidence):
            return GateDecision.REJECT
        if any(x.verdict != Verdict.VERIFIED for x in evidence):
            return GateDecision.HOLD
        checks = {c for x in evidence for c in x.checks}
        if not self.REQUIRED.issubset(checks):
            return GateDecision.HOLD
        return GateDecision.REVIEW_REQUIRED
