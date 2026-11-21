"""Fail-closed runtime authorization; registry owns the cross-run lock."""
from .contracts import AgentID, ExperimentSpec

class ResourceGovernor:
    def __init__(self, agent_id: AgentID, max_runtime_seconds: int = 900):
        self.agent_id = agent_id
        self.max_runtime_seconds = max_runtime_seconds

    def authorize(self, spec: ExperimentSpec) -> bool:
        return (
            spec.agent_id == self.agent_id
            and 0 < spec.max_runtime_seconds <= self.max_runtime_seconds
            and bool(spec.evaluation_manifest_sha256)
        )
