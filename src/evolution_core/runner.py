"""Model execution is intentionally disabled until P1 provenance wiring."""
from .contracts import ExperimentSpec

class Runner:
    def execute(self, spec: ExperimentSpec):
        raise RuntimeError("P1_BLOCKED: no authenticated model invocation or receipt; no candidate produced")
