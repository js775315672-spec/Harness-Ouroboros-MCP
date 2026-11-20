# ORIL v2 slot 4/5: independent *comparison* gate for compact distillation

Baseline: main `8fbecb5e813b653213d6c8d95ce7151868779512`; parallel PR #274 (teacher sample curation), stacked #275 (case-variant group leakage). Do not modify either. This branch is independent and adds a paired **comparison script**, not a trainer.

## Rationale and falsifiable experiment

Hypothesis: given exactly matched heldout task IDs, dataset SHA, task groups and random seeds, the compact candidate reduces actual reported total input+output tokens by at least 20% without decreasing task correctness beyond -2 percentage points. This is **not demonstrated** by synthetic tests. To test, independently execute a real baseline and candidate on the same heldout set (prefer n>=30, more if the confidence interval is wide), freeze the dataset outside the candidate branch, and record original model artifacts. Use identical tokenizer and task scoring rules. Then run:

```bash
python3 scripts/oril_v2_paired_student_eval.py \
  --baseline real_baseline.jsonl --candidate real_compact.jsonl \
  --output comparison.json --min-tasks 30
```

Each input JSONL record requires: `task_id`, `group_id`, `dataset_sha256`, `model_sha256`, `seed`, `correct` (strict boolean), `input_tokens` and `output_tokens` (nonnegative integers), `latency_ms` (finite nonnegative number). The script rejects mismatched task sets, groups, dataset SHA, seeds, duplicate records and malformed numeric fields. It computes paired task accuracy delta, deterministic paired bootstrap CI (2000 resamples), token and latency totals, improvement/regression counts, and a conservative noninferiority flag.

**Important caveats:** This is only a comparison of **user-supplied claims**, not a cryptographic proof of execution, hidden-evaluator provenance, GPU execution or actual LoRA training. A SHA field alone is not attestation. The bootstrap CI is exploratory, can be unstable with small n or correlated tasks, and should be audited by an independent evaluator. Model identity differs between candidates as expected. The reported token counts require an actual identical tokenizer; the script cannot prove this. The result always says `independent_evaluation_attested=false`, `gpu_training_attested=false`. Do not promote or deploy based on this script alone.

## Phase handoff

P0: freeze real baseline/model SHA, task source, independent heldout group, tokenizer. P1: verify PR #274/#275 provenance and no leakage. P2: compile short teacher examples. P3: run baseline/candidate with exact same heldout prompts and seed. P4: optional GPU LoRA only with optimizer step log and adapter bytes+SHA. P5: compare paired accuracy and token usage using this script plus independent evaluator. P6: human approval before merge/deployment. If no real inference logs, **개선 없음** and record a minimal real comparison experiment.

## Known limits

Synthetic CI only establishes parsing and fail-closed comparison invariants; does not prove model improvement, token reduction, time reduction or successful GPU LoRA. Different task difficulty and repeated correlated tasks can inflate confidence. Maintain external reviewer-controlled source digest and signed ledger separately.
