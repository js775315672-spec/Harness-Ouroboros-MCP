# ORIL v2.0 — 모델 가중치 학습 증거 계약 (제안, 비활성)

Status: **PROPOSAL_ONLY / NO_TRAINING_DISPATCH / NO_PROMOTION**. This document does not authorize a model call, GPU spend, training, or production promotion. ORIL v1.1 issue #231 explicitly excludes weight training; this proposal is a separately gated extension, not a silent scope change.

## Why this exists
The current ORIL Cycle 01 PR #233 records an isolated baseline and successful CI checks but explicitly states **no model call or replay was started**. A green Actions badge, generated candidate, prompt update, or adapter-shaped filename must never be counted as a model-weight update. The v2 system must distinguish software self-improvement from actual trainable-parameter changes.

## Required evidence for one real training attempt
A training attempt is **VERIFIED_TRAINING** only when an independent reviewer can reproduce the evidence chain below:

1. **Authorization**: immutable user-approved training scope, compute budget, model family and checkpoint license, maximum GPU hours, data handling limits, expiry, and revocation mechanism; default deny.
2. **Input provenance**: source model name/revision and SHA-256 (or signed immutable digest), tokenizer revision/digest, training config (PEFT/LoRA rank, alpha, targets, optimizer, seed, precision, epochs/steps), framework versions, dataset manifest with license/consent and deduplication, split hashes, and held-out isolation proof.
3. **Actual execution**: training run ID, workflow/job URL, UTC timestamps, runner/GPU device type, process exit status, trainer logs with optimizer steps > 0, GPU usage or independently attested accelerator telemetry, exact model invocation and budget consumption. A dry run, mocked output, or pre-existing checkpoint is not sufficient.
4. **Result artifact**: produced adapter/checkpoint bytes accessible to independent verifier, byte length > 0, SHA-256 computed from actual bytes, immutable artifact location, trainer output references, and an explicit base-model/adapter compatibility check.
5. **Independent evaluation**: same held-out task set, frozen grader hash, comparable inference environment, baseline and candidate measurements with n, seeds, confidence/uncertainty, critical regression count, contamination audit, and evaluator identity separated from training writer.
6. **Promotion gate**: status remains `TRAINED_NOT_PROMOTED` until independently evaluated and explicitly approved. Never modify protected tests, evaluation gates, or production model aliases from the training worker.

## State machine
`PROPOSED -> AUTHORIZED -> TRAINING_STARTED -> TRAINING_COMPLETED_UNVERIFIED -> VERIFIED_TRAINING -> INDEPENDENTLY_EVALUATED -> APPROVED_FOR_PROMOTION -> PROMOTED`.

Any missing or contradictory evidence -> `BLOCKED_MISSING_EVIDENCE`; failed quality or safety -> `REJECTED`; revoked budget -> `STOPPED`. No transition skips. A separate audit event records each transition with prior state, timestamp, actor, source SHA, artifact SHA and supporting URL.

## Minimum machine-readable manifest (example schema, not evidence)

```json
{
  "schema_version": "oril-v2-training-evidence-0.1",
  "status": "PROPOSED",
  "source_commit_sha": null,
  "authorization_ref": null,
  "model_base_digest": null,
  "tokenizer_digest": null,
  "training_dataset_digest": null,
  "heldout_dataset_digest": null,
  "trainer_config_digest": null,
  "run_url": null,
  "optimizer_steps": null,
  "gpu_telemetry_ref": null,
  "adapter_sha256": null,
  "adapter_size_bytes": null,
  "independent_eval_ref": null,
  "promotion_approval_ref": null
}
```

All nulls above are intentional: **no training has been evidenced by this proposal**. Never infer missing evidence from success status of unrelated workflows.

## Acceptance tests to implement before any dispatch
- Reject `VERIFIED_TRAINING` with missing approval, 0 optimizer steps, no actual adapter bytes, invalid SHA, missing GPU provenance, or reused output from another run.
- Reject a mismatched base-model/adapter digest or contaminated held-out split.
- Reject `PROMOTED` without independent evaluator evidence and explicit user approval.
- Accept a fully attested *synthetic fixture only as a validator unit test*, not as evidence of real training.
- Confirm fail-closed behavior on absent/unavailable external artifact and duplicate run ID.

## Comparable cycle metrics
Record worker wall seconds, model inference seconds, independent verification seconds, operations seconds, end-to-end elapsed, queue wait, retries, rollbacks, comparable-task pass rate, and GPU-hours. Report medians with n and source links. Historical Hydra worker/verify/operations stage medians (46/11/25 s) are user-reported and **must not be summed as an end-to-end median or interpreted as a speedup**. A speed or intelligence improvement claim requires matched tasks, evaluator, and hardware with repeated A/B runs.

## Next smallest safe experiment
Implement an **offline-only** JSON manifest validator plus unit tests covering missing, forged, duplicate and valid synthetic evidence. CI may test the validator without any Qwen call, GPU training, paid service, or artifact promotion. After independent review, seek explicit authorization for one real bounded LoRA experiment. This document alone is not that authorization.

## Handoff
- Current main baseline at authoring: `8fbecb5e813b653213d6c8d95ce7151868779512`.
- In-flight work: PR #233 (ORIL Cycle 01), PR #230 (Hydra audit), issue #231 (v1.1 measured self-improvement).
- Do not edit the same files as PR #233. Merge only after review; keep this separate from model execution.
