# ORIL v2.0 Slot 4 — freeze balanced Qwen plan and audit observed calls

## Baseline and collision check

- `main`: `8fbecb5e813b653213d6c8d95ce7151868779512`.
- Slot 2 PR #315 performs **real pretrained CPU** public arithmetic diagnostic; slot 3 PR #316 prepares balanced A/B+A/A order with 30 independent groups and 120 planned calls.
- This slot **does not reimplement** either. It adds a strict read-only *observed-calls-to-plan binding* gate stacked on #316.

## P0–P6

P0: Pin the exact PR #316 plan and record its SHA; do not treat it as a completed run.
P1: Keep reviewed teacher examples separate from independently controlled heldout tasks; never embed hidden answers in this audit.
P2: Use the balanced plan's `group_id`, `block`, `position`, `variant`, `global_sequence`.
P3: Execute the **same pinned pretrained Qwen checkpoint** in this exact sequence, with real measured input/output tokens, latency, prompt digest and run ID.
P4: Audit 120 observations against 120 plan rows; reject missing/reordered calls, model drift, malformed measurements and mismatched A/A prompt digest.
P5: Independent evaluator must separately score correctness on protected heldout cases; this audit **does not score accuracy** or certify model execution.
P6: Only promote after independent noninferiority and measured tokenizer token/latency benefit. No approval/deployment changes in this PR.

## CLI

```sh
python3 scripts/oril_v2_balanced_prompt_run_plan.py --groups groups.json --output plan.jsonl
python3 scripts/oril_v2_slot4_plan_observation_audit.py --plan plan.jsonl --observations actual_observations.jsonl --report audit.json
```

Observation JSONL row: exact five plan fields plus `prompt_sha256` (lowercase 64-hex), `model_revision` (lowercase 40-hex), `input_tokens` (positive integer), `output_tokens` (nonnegative integer), `latency_ms` (positive finite number), `run_id` (one consistent ID). **The values are assertions supplied by the runner, not independently authenticated GPU/CPU evidence.** A/A uses the same digest for the same group/variant; A/B must share pinned model revision. The report sets model authentication, heldout quality and GPU LoRA proof to false.

## Falsifiable next experiment

H1: The existing real Qwen runner can emit all 120 records with the exact plan order and one pinned model revision, and this auditor accepts them without an omitted or duplicate call. Rejection or missing actual calls = **개선 없음**. H2: paired heldout accuracy change >= -2 percentage points and actual input token reduction >=20% with uncertainty assessed on at least 30 groups. Without independently controlled heldout answers, **quality 판단불가**.

No real LoRA optimizer steps or adapter SHA were produced here. Do not count synthetic offline audit tests as new model intelligence. Keep this PR Draft pending independent CI, real run artifacts and user approval.
