# ORIL v2.0 slot2 — P5→P6 feedback memory without unsafe promotion

## Context and evidence

Checkpoint: PR #324 head `caa7642570f47ad8af37cea882fd81ce7e5f4fd9` (stacked on PRs #319–#323). Last successful observed workflows: #44841372111 public Qwen A/B 60 calls, #44843133109 public A/A 60 calls, #44842735795 synthetic audit checks, #44845947932 synthetic cross-run checks, #44847647296 evidence-bundle unit checks. Public model calls are **not** heldout improvement, GPU training, or self-evolution.

This slot adds a distinct missing link: **independent evaluation result → bounded feedback memory → falsifiable next experiment**. The script is intentionally separate from PR #324 evidence bundling and existing independent auditors.

## Contract

Input is JSONL, one record per cycle with exact fields: `cycle_id`, `candidate_sha`, `baseline_sha`, `evaluator_sha`, `heldout_digest`, `evidence_sha256`, `evidence_url` (Actions URL), `independent_review`, `heldout`, `model_weights_changed`, `gpu_training_proven`, `adapter_sha256`, `metric` (accuracy/tokens/latency/safety), `baseline_value`, `candidate_value`, `direction`, `outcome` (pass/fail/inconclusive), `hypothesis`, `experiment`.

Run:
```sh
python3 scripts/oril_v2_slot2_feedback_memory_compiler.py --input independently_reviewed_cycle_outcomes.jsonl --output next_cycle_feedback.jsonl
python3 -m unittest discover -s tests -p 'test_oril_v2_slot2_feedback_memory_compiler.py' -v
```

Fail closed on invalid schema, duplicate cycle, nonfinite numbers, unsupported URLs, or model-weight-change claims without GPU+adapter SHA assertions. Outputs **no heldout prompts, answers, numeric scores, or training data**. Outputs sorted deterministic cycle IDs, source digest, verdict, bounded hypothesis and next experiment. `promotion_allowed=false` for **every** outcome. A `verified_candidate` label only means the *input asserted* independent review + heldout + pass + directionally improved; it is **not cryptographic attestation** and is never a production authorization.

## Actual next cycle

1. Independently retrieve the original public A/B #44841372111 and A/A #44843133109 artifacts; compare source-run SHA and file SHA with #324 bundle, then run PR #323 reconciliation. If artifacts cannot be read, record **개선 없음** for actual artifact attestation.
2. Freeze an *unseen* evaluation set with ≥30 independent task groups, evaluator SHA, baseline and candidate model checkpoint digests; run actual pretrained Qwen with same model/tokenizer settings, log raw paired accuracy, tokens, latency and null-control drift.
3. Only after independent heldout audit, write one actual P5 outcome record and compile P6 memory. The next cycle must attempt the `next_experiment` rather than repeatedly add synthetic tests.
4. Optional LoRA: do not assert learning until real GPU logs, optimizer steps >0, adapter bytes and SHA, and independent heldout evaluation are available.
5. Never change protected validators, approval gates, or deployments. No automatic promotion.

## Falsifiable test

H1: malformed/self-reported/heldout-missing or regressed records cannot authorize promotion or claim proven learning. Acceptance: 20 synthetic positive/negative regression tests pass; all outputs `promotion_allowed=false`; no heldout content in output. H2: the real independently reviewed heldout result can be converted into a reproducible next experiment with immutable evidence SHA. **Not tested until genuine heldout evidence exists.**

## Cycle trend

Comparable end-to-end developer/model/independent evaluator/operator time and token cost: unmeasured. This PR can only measure its own CI job and tests. No improvement to actual model quality is established.
