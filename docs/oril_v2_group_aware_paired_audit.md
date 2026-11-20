# ORIL v2 slot 5/5 — grouped paired heldout evaluation audit

## Starting point and collision avoidance

- Base: PR #276 exact SHA `6ccd955e60817274b56cb2cf7e6ace58d6e5ebaf`, 19/19 synthetic evaluator tests passed: https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44765684881
- Related PRs #274 (compact example curation) and #275 (case-variant group leakage), separate and untouched.
- Main SHA: `8fbecb5e813b653213d6c8d95ce7151868779512`.
- This is a stacked **Draft** PR targeting #276's branch, not main. No protected verifier, approval gate or deployment changed.

## Counterexample to previous acceptance logic

The evaluator in #276 computes paired bootstrap confidence bounds by resampling **task rows**, then checks n >= 30. If 40 tasks are paraphrases or variants of **one underlying task group**, they are not 40 independent evaluation cases. In synthetic data with all 40 correct and 25% reported token savings, the previous script returns `향상`, although there is just one independent group. This is an *evaluation false-positive risk*, not evidence of an actual model error.

## Implementation

`scripts/oril_v2_group_aware_paired_audit.py` adds a conservative, explicitly **unattested** group-aware audit:

- Validate the original exact paired schema and task/seed/dataset alignment.
- Canonicalize group labels by case-folding and trimming; count unique group families.
- Require at least 30 independent-group **proxies** before accepting noninferiority; correlated rows do not increase this count.
- Compute equally weighted per-group accuracy deltas and deterministic cluster bootstrap confidence bounds (2000 resamples), instead of row-wise bootstrap.
- Report actual claimed input+output token totals and reduction; do not confuse tokens with execution time, GPU compute, or cost.
- All input rows, grouping labels, correctness and token counts remain **untrusted claims**. `independent_evaluation_attested=false`, `gpu_training_attested=false`, `model_quality_gain_attested=false`. Even 30 distinct labels are not proof of independent tasks.

Usage after independently collecting actual baseline and student responses:

```bash
python3 scripts/oril_v2_group_aware_paired_audit.py \
  --baseline real_baseline.jsonl \
  --candidate real_candidate.jsonl \
  --output grouped_report.json \
  --min-groups 30
```

## Falsifiable next-cycle experiment

Hypothesis: row-wise bootstrap can falsely pass 40 highly correlated examples; group-aware audit must reject (effective n=1). Minimal reproduction: 40 synthetic tasks, all share group_id `family`, all correct, candidate reported tokens 25% lower. Expected old `status=향상`, new `status=판단불가`. For genuinely independent, verified heldout group IDs n>=30, require group-clustered CI lower bound >=-2 percentage points **and** >=20% actual token savings. If independent source verification or tokenizer logs are missing, report `개선 없음` for actual model quality and `판단불가` for speed.

Do not treat successful CI, synthetic data, a LoRA manifest or candidate-provided scores as real model improvement. Actual GPU training requires independent runner evidence, optimizer steps, adapter bytes and SHA, and independent heldout assessment. This PR only improves the **evaluation design**, not model weights.


## Slot 1 follow-up: Unicode and whitespace alias adversarial guard

The prior group-aware evaluator collapsed casing only. Forty correlated rows split across visually equivalent labels such as `Family Alpha`, `Family  Alpha`, `family alpha`, `Ｔｅａｍ １２` and their ASCII equivalents could inflate the group count and produce a false quality gate. Normalize labels using Unicode NFKC, whitespace collapse and casefold **before** group counting and bootstrap. Three new adversarial regression tests cover aliases and unchanged distinct-group behavior. This is conservative and can merge genuinely different group labels; group labels remain untrusted claims, not externally attested independent families. It does not solve semantic paraphrase duplicates, hidden test contamination, real GPU training, or actual Qwen quality measurement. A follow-up experiment must compare evaluator outputs on independently reviewed family IDs and verify that neither alias inflation nor over-merging changes the correct holdout family count. No automatic promotion.
