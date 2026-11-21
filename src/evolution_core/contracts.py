"""Immutable experiment and evidence contracts. External JSON is untrusted."""
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping
import re

SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")

class AgentID(str, Enum):
    OUROBOROS = "ouroboros"
    CERBERUS = "cerberus"
    FENRIR = "fenrir"

class Verdict(str, Enum):
    VERIFIED = "VERIFIED"
    INCONCLUSIVE = "INCONCLUSIVE"
    REGRESSION = "REGRESSION"
    INVALID = "INVALID"
    SAFETY_VIOLATION = "SAFETY_VIOLATION"

class GateDecision(str, Enum):
    HOLD = "HOLD"
    REJECT = "REJECT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    HALT = "HALT"

def require_hash(value: str, kind: str) -> None:
    pattern = SHA40 if kind == "git" else SHA256
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError("invalid " + kind + " hash")

@dataclass(frozen=True)
class ExperimentSpec:
    experiment_id: str
    agent_id: AgentID
    baseline_sha: str
    hypothesis: str
    success_metric: str
    evaluation_manifest_sha256: str
    policy_version: str
    max_runtime_seconds: int

    def __post_init__(self):
        if not isinstance(self.agent_id, AgentID):
            raise ValueError("unrecognized agent identity")
        require_hash(self.baseline_sha, "git")
        require_hash(self.evaluation_manifest_sha256, "sha256")
        if not self.experiment_id or not self.hypothesis or not self.success_metric or not self.policy_version:
            raise ValueError("missing preregistration")
        if not 1 <= self.max_runtime_seconds <= 3600:
            raise ValueError("unbounded runtime")

@dataclass(frozen=True)
class Candidate:
    experiment_id: str
    candidate_sha: str
    model_id: str
    model_artifact_sha256: str
    generation_artifact_sha256: str

    def __post_init__(self):
        require_hash(self.candidate_sha, "git")
        require_hash(self.model_artifact_sha256, "sha256")
        require_hash(self.generation_artifact_sha256, "sha256")
        if not self.experiment_id or not self.model_id:
            raise ValueError("missing model provenance")

@dataclass(frozen=True)
class EvidenceRecord:
    experiment_id: str
    agent_id: AgentID
    candidate_sha: str
    evaluator_id: str
    evaluator_version: str
    evaluation_manifest_sha256: str
    environment_digest: str
    verdict: Verdict
    checks: tuple[str, ...]
    metrics: Mapping[str, Any]
    artifact_sha256: str
    run_url: str
    independence_attestation: bool
    failure_reasons: tuple[str, ...] = ()

    def __post_init__(self):
        if not isinstance(self.agent_id, AgentID) or not isinstance(self.verdict, Verdict):
            raise ValueError("invalid identity or verdict")
        require_hash(self.candidate_sha, "git")
        require_hash(self.evaluation_manifest_sha256, "sha256")
        require_hash(self.artifact_sha256, "sha256")
        if not all((self.experiment_id, self.evaluator_id, self.evaluator_version, self.environment_digest)):
            raise ValueError("missing evaluator provenance")
        if not self.run_url.startswith("https://github.com/") or "/actions/runs/" not in self.run_url:
            raise ValueError("run_url must be an Actions run")
        if not isinstance(self.independence_attestation, bool):
            raise ValueError("invalid attestation")
        if not isinstance(self.checks, tuple) or not all(isinstance(c, str) for c in self.checks):
            raise ValueError("invalid checks")
