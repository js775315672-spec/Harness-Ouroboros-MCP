# ORIL v2.0 — Slot 1/5: token budget preflight before local Qwen weight allocation

**Baseline:** main SHA `8fbecb5e813b653213d6c8d95ce7151868779512`; stacked on slot5 Draft PR #297 SHA `44135dd795d8e6dd007c402c14ce395ee85be123`. No existing slot PRs or protected approval gates modified.

## Falsifiable hypothesis

The local Qwen adapter used to load potentially large model weights before checking the tokenized input length. Although the request has a 4,000-character limit, subword tokenization may produce more than 4,096 tokens, wasting model initialization time and memory before rejecting the request.

**H1:** if tokenization yields >4,096 tokens, zero-length input, multi-batch tensors, or mismatched attention masks, the adapter must reject the request *before* `AutoModelForCausalLM.from_pretrained`. New tests assert weight load count **0** for five invalid inputs and **1** for two valid cases. No GPU or model files are needed for this narrow contract test.

**H2 (future real measurement):** for oversized inputs on a real approved local checkpoint, fail-fast time and peak resident memory should be lower than the previous load-first behavior. Compare same checkpoint, same tokenizer, 10 warm/cold repetitions each, record p50/p95 time, peak RSS, GPU memory, tokens, model hash and execution source. No speed or cost gain is claimed until measured.

## Scope and evidence

Only `scripts/oril_v2_local_qwen_adapter.py` changes: tokenizer and token/mask shape validation occur before model loading; device transfer follows load. Adds `tests/test_oril_v2_slot1_token_preflight.py` and a read-only Ubuntu CI workflow that also runs inherited adapter/path/config tests. This is a safety and *potential* efficiency optimization, not actual student learning.

**Not measured:** real Qwen inference, actual GPU memory/time savings, LoRA optimizer steps, adapter bytes/SHA, independent heldout accuracy. Those remain explicitly **미측정/미입증**. This PR must remain Draft and must not merge/deploy without approval.

## Next-cycle handoff

Prioritize an approved real Qwen checkpoint and frozen heldout >=30 groups, run paired verbose vs distilled prompts, record actual tokenizer token usage, correctness, latency, and resource costs. If no real checkpoint is available, record **모델 지능 개선 없음** and investigate resource provisioning rather than adding more synthetic model-quality claims. Retain existing PR #262 GPU evidence contract, PR #274 distillation curation and independent evaluator boundaries.
