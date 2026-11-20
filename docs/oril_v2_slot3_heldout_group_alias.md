# ORIL v2 heldout group-alias gate (slot 3/5)

Baseline: main `8fbecb5e813b653213d6c8d95ce7151868779512`; stacked on PR #289 `89dedd7f5113d46acaf1d64d564c29653690a69a`. PR #289 adds actual subprocess inference protocol but its `read_manifest` only rejects **byte-exact** repeated `group_id`. Variants such as `g0`, `ｇ０`, `G\u200b0` or `g 0` can be counted as separate heldout groups and falsely inflate independence and confidence.

## Narrow patch
- Canonicalize group IDs with NFKC, casefold, whitespace and Unicode format character filtering **for duplicate detection only**.
- Reject empty canonical groups.
- Five regression tests: fullwidth, invisible format character, whitespace, invisible-only, distinct valid groups.
- Keep the original raw group ID in the report for audit; no protected verifier, approval or deployment change.

## Evidence boundaries
The runner's unit tests use **synthetic subprocess adapters**, not a Qwen model. Group canonicalization does **not** detect semantic duplicates, paraphrases, or hidden train/heldout overlap; independently frozen provenance remains mandatory. No GPU training, adapter weights, real tokenizer, quality improvement, or LoRA claim. Model improvement = **개선 없음(미입증)** until actual independent paired evaluation.

## Falsifiable follow-up
1. Run exact SHA GitHub CI and ensure 15/15 tests (10 inherited + 5 new) with no skips; failures are not success.
2. Freeze a private heldout manifest of >=30 independently distinct groups with a separate evaluator; hash manifest, baseline/candidate model revisions and actual tokenizer.
3. Run real Qwen subprocess adapters and measure paired quality CI, wall time, tokenizer tokens and cost. Acceptance: lower 95% token savings bound >=20% and quality delta lower bound >= -2pp, or **판단불가** if n insufficient.
4. LoRA only with actual GPU optimizer steps >0, adapter bytes/SHA and independently verified heldout comparison.
