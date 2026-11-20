# ORIL v2 slot 2 — evidence-bound CPU pair execution order

## Baseline
- main SHA: `8fbecb5e813b653213d6c8d95ce7151868779512`
- stacked on slot 1 Draft PR #303 SHA `9109b7953fb5e95066085181d459b5c92f4f997f`
- slot 1 actual CPU benchmark: 6 pairs / 12 generations with random-weight tiny Qwen2; GitHub Actions [#44816411022](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44816411022) successful.
- Remaining evidence defect: `summarize()` previously **invented** the `pair_orders` array from index parity regardless of actual invocation order. This could falsely claim a balanced experiment for an unbalanced input. No actual GPU LoRA or pretrained Qwen heldout result.

## Change and falsifiable test
- `run()` now records `observed_orders` from the actual invocation list before executing the two model calls, and passes it to `summarize()`.
- `summarize()` does **not** infer or fabricate order when no observed orders are supplied: `pair_orders: null`, `pair_order_observed: false`.
- If observed orders are supplied, enforce exact pair count, allowed labels, and near-equal compact/verbose-first counts. Fail closed on mismatches or imbalance.
- Added 3 regression methods plus strengthened the existing balanced-order assertion. The experiment remains a **toy synthetic CPU inference benchmark**; no training, quality improvement, or cost claim.

**Acceptance:** 10/10 paired benchmark unit tests (7 existing + 3 new) at exact SHA, no skips, then 12 actual tiny Qwen2 CPU generations in an independent GitHub Actions run, and report `pair_order_observed: true` with six balanced labels. If CI fails, classify **개선 없음**, diagnose and revise before promotion.

## Next-slot priority
Stop generating more random-weight synthetic model tests unless a new failure is identified. The next decisive experiment needs an approved **pretrained** Qwen checkpoint, independently frozen heldout task groups (>=30), and actual tokenizer, latency and correctness measurements with paired seeds and no training-data leakage. Real GPU LoRA requires actual optimizer steps, GPU logs, adapter bytes+SHA, and independent heldout evaluation; absent those, status remains **미입증**. Never change protected validators or deployment gates without approval.

## Cycle speed / quality
This change only fixes evidence integrity. Development wall time, model call time, independent evaluation time, cost, and comparable 5–12-cycle medians are not measured in this document. The CI job's wall time is not pure model latency. Speed: **판단불가**. Intelligence quality: **판단불가**.
