# ORIL v2 슬롯 1/5 — CPU paired benchmark order-confounding audit

## Baseline and distinct scope
Base PR #307 SHA `673aedaccdf2fa7b596f929ba9d6d79d83c0886b`. PR #306 independently checks arithmetic from raw sidecar; PR #307 creates real random-weight CPU raw timings. Neither determines whether the **observed sign of latency difference changes when prompt order changes**. This additive audit does not modify #306 or #307's existing files.

## New audit
`scripts/oril_v2_cpu_pair_order_confound_audit.py` calls the existing independent sidecar arithmetic audit first, then splits real observed `verbose_elapsed_seconds - compact_elapsed_seconds` differences by `compact_first` and `verbose_first`, reports per-order median and counts, and flags whether the signs agree. It refuses to claim latency gain or pretrained quality improvement even when signs agree. A minimum two samples per order is required to compute a directional consistency verdict; this is a **diagnostic only**, not significance testing.

Run: `python3 scripts/oril_v2_cpu_pair_order_confound_audit.py report.json sidecar.json`.

## Falsifiable hypothesis and next minimum experiment
H1: subprocess cold-start and execution order can confound a naive compact/verbose latency comparison. Using #307 actual raw sidecar, compare the two order-stratified median differences. A sign disagreement => observed order sensitivity, disallow any speed claim. Sign agreement => **not enough** to claim speed gain; require a pretrained frozen Qwen checkpoint, same fixed task set, >=30 paired independent groups, warm model, alternating order, repeated runs, token counts, latency and heldout quality with uncertainty. Evidence should be attached to the exact Action SHA. Without actual GPU optimizer steps and adapter file bytes+SHA, mark LoRA **not demonstrated**.

## Limits
The raw sidecar hash is self-reported and not a provenance attestation. This tests CPU random-weight synthetic inference only, not model intelligence or GPU learning. Tests are developer-authored and require independent CI execution. No protected gate, deployment, or validator changed. Draft only.

## Handoff
1. Confirm CI at exact SHA, eight regression tests no skips.
2. Obtain #307 actual run report/sidecar and run this auditor. Publish exact SHA and per-order medians, or mark `미측정` if artifacts inaccessible.
3. Stop adding synthetic validators without a measurable need. Prioritize pretrained Qwen and independent heldout evidence, then optional real LoRA with GPU logs and adapter SHA.
