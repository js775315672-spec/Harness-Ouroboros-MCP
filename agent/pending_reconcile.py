"""Fail-closed external operation reconciliation. DEV-only, no network credentials.

The caller supplies an authenticated read-only lookup and a pinned verifier.
Neither a missing result nor a self-reported receipt can become success.
"""
from dataclasses import dataclass
from typing import Callable
from agent import cycle_registry as registry


@dataclass(frozen=True)
class Observation:
    operation_id: str
    source_sha: str
    status: str
    receipt: str


def reconcile(state: dict, *, owner: str, generation: int, source: str,
              now: float, lookup: Callable[[str], Observation | None],
              verify: Callable[[Observation], bool]) -> dict:
    """Return a new state with verified evidence or raise BLOCKED without mutation.

    Must be committed with the registry's remote CAS; never invoke an operation
    again while reconciliation is pending. A verifier is a trusted, independent
    caller-supplied predicate, not a cryptographic signature implementation.
    """
    pending = state.get("pending")
    if not pending:
        raise registry.Blocked("no pending operation to reconcile")
    if state.get("phase") != "open":
        raise registry.Blocked("cycle is not open")
    if (state.get("owner"), state.get("generation"), state.get("source")) != (
            owner, generation, source):
        raise registry.Blocked("stale lease or source drift")
    if state.get("expires", 0) <= now:
        raise registry.Blocked("expired lease; recovery required before reconciliation")
    if pending in state.get("results", {}):
        raise registry.Blocked("duplicate operation already recorded")
    try:
        observation = lookup(pending)
    except Exception as exc:
        raise registry.Blocked("external lookup failed; outcome unknown") from exc
    if observation is None or not isinstance(observation, Observation):
        raise registry.Blocked("external outcome missing or malformed")
    if (observation.operation_id != pending or observation.source_sha != source
            or observation.status != "confirmed" or not observation.receipt):
        raise registry.Blocked("external outcome is unconfirmed or mismatched")
    try:
        trusted = verify(observation)
    except Exception as exc:
        raise registry.Blocked("receipt verifier failed") from exc
    if trusted is not True:
        raise registry.Blocked("receipt was not independently verified")
    # Copy-on-write: failure never clears pending or corrupts earlier receipts.
    updated = dict(state)
    updated["results"] = dict(state.get("results", {}))
    updated["results"][pending] = observation.receipt
    updated["pending"] = None
    return updated
