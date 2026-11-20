# ORIL v2 — slot 3/5: paired prompt variant execution bridge

Baseline: `main=8fbecb5e813b653213d6c8d95ce7151868779512`, stacked on Draft PR #299 (`f7bce18924b3b90537ac890523b50e13b217867d`). PR #289–#299 contain the paired student probe, bounded subprocess capture, Qwen local adapter and real-model readiness audit. Existing CI remains mock-only. **No actual model checkpoint, GPU LoRA training or independent heldout evaluation has been proven.**

## What this change solves

The paired evaluator `oril_v2_student_real_inference_probe.py` invokes two commands on the same question, but the local Qwen adapter `oril_v2_local_qwen_adapter.py` did not accept a separately selected verbose-vs-distilled context. This wrapper adds **pinned, bounded prompt prefix files** to both commands without changing the protected evaluator or training a model.

Both commands MUST call the **same verified checkpoint SHA** and differ only in context prefix. The wrapper passes exactly the original `case_id`, `seed`, and question, adding only the prefix. It does not access heldout answers. The context file must contain reviewed, public, non-sensitive teacher examples; do not copy hidden evaluation questions, answers, credentials, private traces, or chain-of-thought into it.

Example for operator (requires real local checkpoint and private heldout manifest):

```bash
# Independently verify each context source and file hash before running.
sha256sum verbose_examples.txt compact_examples.txt
python3 scripts/oril_v2_student_real_inference_probe.py \
  --heldout /private/heldout.jsonl \
  --baseline-cmd-json '["python3","scripts/oril_v2_paired_prompt_variant_adapter.py","--prefix-file","verbose_examples.txt","--prefix-sha256","<VERBOSE_SHA256>","--adapter-cmd-json","[\"python3\",\"scripts/oril_v2_local_qwen_adapter.py\",\"--model-dir\",\"/trusted/qwen\"]"]' \
  --candidate-cmd-json '["python3","scripts/oril_v2_paired_prompt_variant_adapter.py","--prefix-file","compact_examples.txt","--prefix-sha256","<COMPACT_SHA256>","--adapter-cmd-json","[\"python3\",\"scripts/oril_v2_local_qwen_adapter.py\",\"--model-dir\",\"/trusted/qwen\"]"]' \
  --report /private/paired_results.json
```

Placeholders are intentional. Do not claim the above command was executed. The evaluator invokes a fresh Qwen model process per case, so end-to-end time includes repeated model loading. Distinguish loading time from inference latency in a future persistent-model benchmark.

## Falsifiable next experiment

1. Freeze and externally pin teacher example source SHA, both prompt prefix hashes, model weights/tokenizer hash, private heldout manifest SHA, and group membership (>=30 independent groups preferred).
2. Run the **same** local model checkpoint with baseline verbose prefix and candidate compact prefix, equal `max_new_tokens`, same seed and evaluator cases.
3. Record actual tokenizer input/output counts, subprocess wall time, per-case exact-match and group-aware bootstrap confidence intervals. Adapter-reported counts are *claims*, not independent tokenizer attestation.
4. Pass only if actual token savings confidence lower bound >=20%, heldout accuracy delta confidence lower bound >=-2 percentage points, no data leakage, and reviewer approval. Otherwise mark `판단불가` or `개선 없음`.
5. LoRA is a separate optional gated experiment: require GPU optimizer steps >0, actual adapter bytes+SHA, and independently heldout model improvement. Never infer LoRA from an adapter path, CI pass, or synthetic mocks.

**Limitations:** SHA pins context bytes but does not authenticate who reviewed the examples; static symlink checks are not an atomic filesystem trust boundary; the same model identity is an operator responsibility; prefix injection is not proof of increased intelligence. This PR touches only new script/test/docs/workflow and does not alter protected gates or deployment.

**Handoff:** run CI first, fix actual failures, then acquire approved checkpoint and private heldout. Do not keep adding synthetic guards instead of collecting real evidence.
