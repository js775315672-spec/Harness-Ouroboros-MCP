# Slot 4/5 — invisible Unicode in distilled evaluation questions

## Baseline and collision check
- Stack only on PR #280 (SHA `2b2160439cd4136c0500a8fc162433b347530654`), which adds NFKC normalization; avoid PR #279 grouped token confidence and all protected evaluation/approval/deployment paths.
- PR #280 synthetic curation CI: https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44773761058 (success).
- No GPU LoRA optimizer steps, adapter bytes/SHA, independent student heldout score, real tokenizer tokens, or verified teacher review available.

## Falsifiable defect
NFKC normalization does not remove Unicode format characters (`Cf`), including zero-width space U+200B, zero-width joiner U+200D and right-to-left override U+202E. A train question `repair dependency boundary` and heldout question `repair<U+200B> dependency boundary` can evade exact normalized question equality. They are potentially the same semantic task, contaminating claims of independent evaluation.

## Narrow remediation
Reject any question containing a Unicode `Cf` character **before** hashing/split checking. Do not silently strip: this would alter text and hide the source anomaly. Keep teacher answers unchanged. Four regressions test zero-width space, bidi override, joiner and ordinary Korean questions.

## Acceptance and limits
- Expected inherited CI: existing 25 + 4 = 29 tests; exact count must be confirmed in GitHub Actions for final SHA, zero skips.
- This is a **synthetic dataset integrity guard**, not improved model intelligence or proof of actual training. Unicode confusables from other scripts, semantic paraphrases, source review authenticity, actual student accuracy and tokenizer savings remain unverified.
- Over-rejection risk: legitimate emoji ZWJ sequences inside questions are refused; upstream curator must manually review/normalize in a controlled dataset pipeline, not auto-rewrite heldout prompts.
- No protected validators, approval gates or deployment altered.

## Next cycle minimum experiment
Freeze independently sourced and reviewed n>=30 heldout task families and input SHA; run actual student baseline vs compact teacher examples with tokenizer-verified tokens, latency and paired quality CI. Require group-bootstrap lower token-saving CI >=20% and quality noninferiority lower CI >= -2pp. If no verified real examples, mark **개선 없음** for model quality and register source acquisition blocker. GPU LoRA must produce actual optimizer steps and adapter SHA/bytes before claiming weight training.

## Cycle speed reporting
Record full wall-time, model-call, independent-check, operational-follow-up times with SHA/log URLs for >=5 comparable cycles. Until comparable observations exist, speed/quality trend = 판단불가; synthetic test count is not model throughput.
