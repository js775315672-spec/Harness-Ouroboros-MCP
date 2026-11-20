# ORIL v2 slot 2/5 — uncertainty-aware compact-student token savings

## Starting evidence and conflict avoidance

- Main SHA: `8fbecb5e813b653213d6c8d95ce7151868779512`.
- Latest slot 1 Draft PR #278 SHA `2a7bb84e9efc76c380c09be62733c8439b1c40c1`, CI https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44768915279: developer-authored synthetic tests 36/36. Stacked on #278, leaving #274–#278 unchanged.
- Related independent-evaluation design: PR #276 (paired quality+point token savings), PR #277 (clustered quality CI), PR #278 (group label normalization).

## Falsifiable counterexample

Previous `group_audit` could label a compact student as `향상` when **only one exceptionally long heldout group** supplied all claimed token savings. The aggregate point estimate might exceed 20%, but the effect is not robust across independent task groups.

Minimal synthetic reproduction: 40 independent group IDs; baseline 100 tokens per group, except one 2000-token group; candidate matches baseline for 39 groups and uses 0 tokens for the outlier. Aggregate point estimate = 2000/5900 = 33.90%, but group-clustered bootstrap lower 95% CI is below 20%. Expected: old point-only gate may pass; new robust gate must reject the improvement claim.

## Implementation

`scripts/oril_v2_token_confidence_audit.py` wraps the existing group-aware paired audit, preserving its quality CI and canonical group handling. Resample **whole groups** with replacement, calculate token reduction as ratio of resampled group totals, and require the **lower 95% bootstrap percentile** >=20% along with the independent group minimum and quality noninferiority. Zero-baseline resamples fail closed (no CI). Expose both point-estimate pass and robust pass, and keep all attestation flags false.

`tests/test_oril_v2_token_confidence_audit.py` tests outlier false positives, robust uniform savings, group aliases, sample insufficiency, quality regressions, zero denominators, CLI and deterministic output.

## Limitations and next step

- No actual Qwen/GPT inference was run; model, tokenizer, token counts and group IDs are **untrusted assertions**. This does not prove speedup, LoRA, or independent heldout quality.
- The group bootstrap is exploratory; 30 groups is a heuristic and not a power analysis. Group IDs can still be fabricated or semantically correlated. Dataset trust root and provenance remain external.
- Next cycle must obtain real independently reviewed heldout groups (n>=30), actual tokenizer/inference logs, frozen model SHA, seeds, measured latencies, GPU evidence/adapter bytes if LoRA is claimed.
- Acceptance: actual tokenizer saving lower group-bootstrap CI >=20%, paired quality lower CI >=-2 percentage points, no regressions in protected gates. If unavailable, **개선 없음** for model and **판단불가** for speed.
- No protected verifier, approval gate, deployment, or model weights changed.
