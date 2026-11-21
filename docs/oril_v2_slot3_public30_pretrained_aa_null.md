# ORIL v2 slot 3 — real pretrained public30 A/A null control

## Baseline and collision check (2026-11-21 KST)
- main `8fbecb5e813b653213d6c8d95ce7151868779512`.
- PR #274 prepares teacher-example curation; #316 prepares a frozen future 120-call A/B+A/A heldout plan; #317 binds observations; #319 actually ran 30 **public** Qwen2.5-0.5B A/B pairs, 60 CPU calls; #320 independently audits those public pairs.
- This stacked PR adds the **missing actual pretrained same-prompt A/A null control** on the same 30 public questions, 60 additional CPU calls. No duplicated hidden evaluator or LoRA implementation.

## Hypothesis, measurements, evidence boundaries
- H0: repeating the **identical compact prompt** twice per public question produces nonzero CPU inference timing drift even though input tokens are exactly equal. A/A measured noise is a *descriptive confound baseline*, not a statistically calibrated null distribution for separate A/B experiments.
- Measure 30 groups, two identical compact prompts per group, single loaded model, exact pretrained model revision and weight SHA, per-call actual input/generated tokens, raw decoded output, latency and execution order (first/second).
- Recompute signed second-minus-first latency median, median absolute A/A drift and total compact input tokens from raw observations. Refuse contradictory per-pair token counts, incorrect public labels, nonfinite timing and mismatched group/question.
- 16 offline mutation tests + independent Ubuntu Actions that **runs the real pretrained model**. The CI artifact retains public raw evidence for seven days. The CI is the actual execution source; local unit tests use synthetic fixtures only.
- No external hidden labels, no independent quality certification, no model intelligence/speed gain, no GPU/LoRA training, no adapter weights, no new operating approval. Public arithmetic is correlated and cannot prove student generalization.

## P0–P6 integration
P0 freeze exact source SHA/model revision and audit #319/#320 before running. P1 reject private or unreviewed teacher data. P2 run public A/A repeated inference as a baseline separate from train/heldout. P3 independently verify raw observations. P4 no GPU/adapter claims. P5 next run frozen independent heldout A/B+A/A at identical model revision, randomized/interleaved blocks, >=30 groups and actual tokenizer counts; compute group-paired CI, noninferiority and actual latency uncertainty. P6 no merge/promotion without reviewer approval.

**Next handoff:** do not compare latency from separate Actions runners as causal improvement. First inspect exact-SHA CI, raw artifact and metadata, then execute #316/#317 frozen design on independently curated heldout groups. If real data are unavailable, mark model quality **판단불가** and do not manufacture teacher review evidence.
