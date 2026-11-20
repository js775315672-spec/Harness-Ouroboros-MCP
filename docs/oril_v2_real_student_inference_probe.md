# ORIL v2 — actual paired student inference probe (P0–P6)

## Scope

This is an **executable adapter harness** to bridge ORIL's synthetic data/evidence validation toward **real** model invocation. It runs two separate model-adapter subprocesses for each identical heldout task, records measured wall time, compares exact answers, and writes a report bound to the SHA-256 of the input heldout manifest. It never performs LoRA training or model promotion. The CI tests invoke **synthetic Python stubs**; passing CI is **not** proof of actual Qwen inference.

## Input / adapter contract

Provide a local JSONL manifest with at least two independent heldout groups, exact fields `case_id`, `group_id`, `question`, `expected_answer`, `split: "heldout"`. Do **not** commit confidential heldout questions/answers into public GitHub.

Pass each model adapter as a JSON array command, e.g. `["python3","local_qwen_adapter.py","--model","..."]`. The runner supplies JSON on stdin with **only** `question`, `case_id`, `seed` — never `expected_answer`. The adapter must return JSON `answer`, `input_tokens`, `output_tokens`, `model_id`. The runner measures subprocess wall time using `time.monotonic_ns()`; tokenizer token counts and model IDs remain **unverified claims** until independently cross-checked with tokenizer/model files and a trusted execution trace.

Example invocation:

```sh
python3 scripts/oril_v2_student_real_inference_probe.py \
  --heldout /private/frozen-heldout.jsonl \
  --baseline-cmd-json '["python3","local_baseline_adapter.py"]' \
  --candidate-cmd-json '["python3","local_distilled_adapter.py"]' \
  --timeout 60 --seed 42 --report /private/paired-probe.json
```

Adapters above are illustrative; no real Qwen adapter or GPU environment is provisioned in this PR. Keep the same seed and frozen task manifest, model revision, generation configuration, tokenizer and hardware for both variants. Record command executable hashes and job/run URL in an external trusted evidence ledger; the runner itself does not attest these.

## Gate and next experiment

1. **P0:** independently freeze heldout manifest SHA and model/adapter revision, tokenizer, inference settings.
2. **P1–P2:** verify teacher provenance, split leakage, training example manifest; reuse PR #274–#288 only after reviewing stacked dependency.
3. **P3:** run baseline and candidate adapters against >=30 independent groups with real model calls, record actual token counts, wall time, per-task correctness and error/failure counts. This runner currently uses strict exact-match; semantic scoring requires a separate independently frozen evaluator.
4. **P4:** if genuine GPU available, separately run LoRA optimizer steps, hash adapter bytes, record GPU utilization, checkpoint hash and job logs. Never infer weight learning from this probe.
5. **P5:** independently reproduce the paired heldout evaluation with externally frozen data and compute confidence intervals (PR #279). Adapter-provided token counts are not independently verified.
6. **P6:** user approval before merging any protected evaluator, promotion gate, or deployment.

## Falsifiable hypothesis

H: a distilled context or genuinely trained student uses >=20% fewer **independently verified tokens** with heldout accuracy noninferiority margin -2 percentage points. Reject if confidence lower bound does not pass both conditions; if n<30 or external evidence is missing, record **판단불가**, not improved. A faster synthetic adapter is not model speedup.

## Risk/limitations

- This prototype is an **offline research harness**, not a hardened execution sandbox. Commands are explicitly supplied by a trusted operator, not derived from untrusted datasets. It does not attest model identity, GPU, adapter files, or hidden-evaluator independence.
- Exact-match can underestimate semantic correctness; input manifest and command environment must be independently pinned.
- Subprocess overhead contributes to measured wall time; avoid comparing a resident server against per-call process launch without recording that distinction.
- On any adapter failure the report is not created, and no partial improvement is claimed.

**Next slot:** acquire an authorized actual Qwen adapter and private frozen heldout tasks; otherwise report "실제 모델 개선 없음", preserve the synthetic protocol CI evidence only, and prioritize measuring true model inference before another evidence-only gate.
