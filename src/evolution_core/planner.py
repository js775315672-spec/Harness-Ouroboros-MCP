"""P0: preregistered plans only; no unstated autonomous planning claims."""
from .contracts import AgentID, ExperimentSpec

class Planner:
    def __init__(self, agent_id: AgentID):
        self.agent_id = agent_id

    def plan(self, spec: ExperimentSpec) -> ExperimentSpec:
        if spec.agent_id != self.agent_id:
            raise PermissionError("another agent's experiment")
        return spec
