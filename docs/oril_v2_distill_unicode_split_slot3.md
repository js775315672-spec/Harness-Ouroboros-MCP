# ORIL v2 slot 3/5 — Unicode compatibility leakage in distilled teacher examples

## Starting baseline and isolation
- `main`: `8fbecb5e813b653213d6c8d95ce7151868779512`.
- Stacked on PR #275 HEAD `c074fa31a47e35fe0ab97c602821c4d8d79589fd` (previous synthetic CI 21/21).
- Other active branches #276–#279 modify paired-evaluation/token confidence code. This PR only changes the teacher example compiler and its existing tests, avoiding those files.
- Current #279 CI: https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44771896461 (synthetic test execution, not actual model improvement).

## Falsifiable finding
The original compiler normalized question whitespace and case, but did **not** normalize Unicode compatibility characters. Thus a `train` question `Fix dependency boundary` and a `heldout` question `Ｆｉｘ dependency boundary` could be treated as different question digests despite being visually and semantically the same. A `ﬁ` ligature could similarly bypass the validation split check. A downstream training set could then expose evaluation task text to the student.

## Implementation
- `scripts/oril_v2_teacher_distillation_pack.py`: use `unicodedata.normalize("NFKC", value)` before whitespace folding and casefold in `norm`. Existing SHA-256 question fingerprint now uses this canonical representation.
- `tests/test_oril_v2_teacher_distillation_pack.py`: four additional synthetic tests: fullwidth train/heldout cross-split rejection, ligature train/validation rejection, within-train deduplication, and distinct-question preservation.
- Existing read-only CI for the distillation compiler is reused. No protected validators, approval, model weights or deployment modified.

## Scope and limits
NFKC does **not** solve paraphrase leakage, semantic equivalence, visually confusable mixed-script homoglyphs, contaminated hidden evaluator answers, or unverified review provenance. Real teacher examples, GPU LoRA logs, adapter bytes/SHA and independent heldout model evaluation remain absent. Test count and CI success are not intelligence improvements.

## Next falsifiable experiment
1. At exact PR HEAD SHA run all compiler tests and verify 25/25 (original 19 + PR #275 2 + this PR 4), skipped=0. Explicitly capture GitHub Actions URL and job log.
2. Construct 40 synthetic Unicode-variant cross-split pairs and verify 40/40 are rejected without losing genuinely distinct questions. If any pass, minimize counterexample and extend normalization/semantic leakage policy.
3. Do not claim actual token/quality gains. Collect verified teacher records and real frozen student paired heldout n>=30 independently sourced groups; record model/dataset SHA, actual tokenizer tokens, latency, correctness, and bootstrap CIs. Only real GPU optimizer steps and adapter file SHA count as LoRA.
4. If no real examples or GPU are available, record **개선 없음 (모델 성능)**, explicit missing inputs and next minimal reproducible test in issue #251.

## Speed comparison
Record wall time and test internal time separately. CI wall time of this PR is not comparable with different workflows, and no model inference timing exists. No median or percentage speed gain may be claimed from n=1.
