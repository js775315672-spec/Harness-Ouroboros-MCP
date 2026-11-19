"""Exercise the one-call W08 admission and receipt path with a fixture only."""
from p3l_w04_attempt_registry import AttemptBlocked, AttemptInput
from p3l_w07_revision_isolation import git
from p3l_w08_evidence_handoff import PROMPT_SHA256, rehearsal_receipt, sha
from p3l_w08_verify_test import CANDIDATE_COMMIT, TARGET, append_test

TASK = "w08-checkpoint-cas-rehearsal"
CONTRACT_SHA = sha(b"w08: preserve the first checkpoint and reject a stale second writer")


def rehearse(root, registry, prompt, fixture, *, run_id, workflow_sha, invoke):
    if sha(prompt) != PROMPT_SHA256:
        raise AttemptBlocked("W08 public prompt differs from the reviewed input")
    head = git(root, "rev-parse", "HEAD").decode().strip()
    if head != CANDIDATE_COMMIT:
        raise AttemptBlocked("W08 checkout differs from the reviewed candidate")
    original = git(root, "show", f"{CANDIDATE_COMMIT}:{TARGET.as_posix()}")
    append_test(original, fixture)
    inputs = AttemptInput(TASK, CONTRACT_SHA, head, head, "0" * 40, "0" * 64,
                          sha(b"local fixture; no model"), PROMPT_SHA256)
    lease = registry.reserve(inputs, "w08-rehearsal", ttl_seconds=30)
    observed = git(root, "rev-parse", "HEAD").decode().strip()
    registry.start(lease, observed_head=observed, run_id=run_id)
    proposal = invoke(fixture)
    if type(proposal) is not bytes or proposal != fixture:
        raise AttemptBlocked("W08 rehearsal returned unexpected fixture bytes")
    return proposal, rehearsal_receipt(proposal, run_id, workflow_sha)
