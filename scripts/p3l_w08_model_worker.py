"""Bind one W08 model invocation to its reviewed inputs and coordinator receipt."""
import hashlib
import os
import re

from p3l_w04_attempt_registry import AttemptBlocked
from p3l_w04_github_claim import create_once
from p3l_w05_actions_source import LLAMA_REVISION, QWEN_REVISION, QWEN_WEIGHTS_SHA256
from p3l_w07_revision_isolation import git
from p3l_w08_attempt_rehearsal import CONTRACT_SHA
from p3l_w08_evidence_handoff import PROMPT_SHA256, encode, sha
from p3l_w08_verify_test import CANDIDATE_COMMIT, TARGET
from p3l_w08_w07_gate import W07_RUN


def authorization(inputs, run_id, binary_sha, *, rehearsal):
    return {
        "schema": "p3l-w08-coordinator-start-v1", "task_key": inputs.task_key,
        "semantic_key": inputs.semantic_key, "run_id": run_id, "base_sha": inputs.base_sha,
        "review_head": inputs.head_sha, "prompt_sha256": inputs.prompt_sha256,
        "llama_revision": LLAMA_REVISION, "binary_sha256": binary_sha,
        "w07_run": W07_RUN, "started": True, "rehearsal": rehearsal,
    }


def claim_budget(inputs, run_id, binary_sha, request, *, approved_head, rehearsal):
    """The trusted coordinator calls this only after its separate approval gate."""
    if approved_head != inputs.head_sha or type(rehearsal) is not bool:
        raise AttemptBlocked("W08 approval does not authorize the worker SHA")
    if (type(run_id) is not int or run_id < 1 or type(binary_sha) is not str
            or re.fullmatch(r"[0-9a-f]{64}", binary_sha) is None):
        raise AttemptBlocked("invalid W08 coordinator execution identity")
    prefix = "refs/heads/rehearsal/w08-model/" if rehearsal else "refs/heads/p3l-w08/started/"
    ref = prefix + inputs.semantic_key
    created, _, _ = create_once(ref, inputs.head_sha, request)
    if not created:
        raise AttemptBlocked("W08 shared budget was already recorded")
    return encode(authorization(inputs, run_id, binary_sha, rehearsal=rehearsal))


def model_receipt(inputs, run_id, binary_sha, grant_sha, proposal, *, rehearsal):
    return {
        **authorization(inputs, run_id, binary_sha, rehearsal=rehearsal),
        "schema": "p3l-w08-worker-rehearsal-v1" if rehearsal else "p3l-w08-model-output-v1",
        "model_revision": QWEN_REVISION, "gguf_sha256": QWEN_WEIGHTS_SHA256,
        "inference_config_sha256": inputs.inference_config_sha256,
        "proposal_sha256": hashlib.sha256(proposal).hexdigest(),
        "coordinator_receipt_sha256": grant_sha, "target": TARGET.as_posix(),
        "model_calls": 0 if rehearsal else 1,
    }


def validate_model_receipt(raw, proposal, inputs, run_id, binary_sha, grant, grant_sha, *, rehearsal):
    if type(proposal) is not bytes or not 1 <= len(proposal) <= 6000:
        raise AttemptBlocked("invalid bounded W08 model output")
    if (type(rehearsal) is not bool or sha(grant) != grant_sha
            or grant != encode(authorization(inputs, run_id, binary_sha, rehearsal=rehearsal))):
        raise AttemptBlocked("W08 independent verification received a wrong coordinator receipt")
    expected = model_receipt(inputs, run_id, binary_sha, grant_sha, proposal, rehearsal=rehearsal)
    if raw != encode(expected):
        raise AttemptBlocked("W08 independent verification received a wrong model receipt")
    return expected


def execute(registry, checkout, inputs, run_id, prompt, preflight, grant, grant_sha, binary_sha, invoke,
            *, rehearsal):
    if (inputs.task_type != "w08-checkpoint-cas" or inputs.public_contract_sha256 != CONTRACT_SHA
            or inputs.base_sha != CANDIDATE_COMMIT or inputs.prompt_sha256 != PROMPT_SHA256
            or inputs.model_revision != QWEN_REVISION or inputs.gguf_sha256 != QWEN_WEIGHTS_SHA256
            or sha(prompt) != PROMPT_SHA256):
        raise AttemptBlocked("W08 reviewed input identity differs")
    required = {"candidate_sha": CANDIDATE_COMMIT, "prompt_sha256": PROMPT_SHA256,
                "target": TARGET.as_posix(), "w07_run": W07_RUN,
                "w07_evidence_verified": True, "model_calls": 0}
    if any(type(preflight.get(k)) is not type(v) or preflight[k] != v for k, v in required.items()):
        raise AttemptBlocked("W07 preflight does not authorize this input identity")
    if type(run_id) is not int or run_id < 1 or re.fullmatch(r"[0-9a-f]{64}", binary_sha) is None:
        raise AttemptBlocked("invalid W08 execution identity")
    if (type(rehearsal) is not bool or sha(grant) != grant_sha
            or grant != encode(authorization(inputs, run_id, binary_sha, rehearsal=rehearsal))):
        raise AttemptBlocked("W08 coordinator receipt differs from the verified job output")
    if os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
        raise AttemptBlocked("model worker inherited coordinator credentials")
    observed = git(checkout, "rev-parse", "HEAD").decode().strip()
    if observed != inputs.head_sha or git(checkout, "status", "--porcelain", "--untracked-files=no"):
        raise AttemptBlocked("W08 worker checkout is not the reviewed revision")
    lease = registry.reserve(inputs, "w08-model-worker", ttl_seconds=30)
    registry.start(lease, observed_head=observed, run_id=run_id)
    proposal = invoke(prompt)
    if type(proposal) is not bytes or not 1 <= len(proposal) <= 6000:
        raise AttemptBlocked("invalid bounded W08 model output")
    result = model_receipt(inputs, run_id, binary_sha, grant_sha, proposal, rehearsal=rehearsal)
    return proposal, result
