# ORIL v2 P0–P6 slot 3: CPU null-calibrated latency diagnostic

## Baseline and rationale
- main SHA `8fbecb5e813b653213d6c8d95ce7151868779512`.
- Stacked on slot 2 PR #310 SHA `9a03ba6aaa31558edf223041db2f3242d8953311` (already passed Actions #44827242106).
- #307 captures 6 real **random-weight** Qwen2 CPU prompt pairs with per-call sidecar; #309 captures 6 same-prompt negative-control pairs; #310 audits their null arithmetic. All are toy CPU benchmarks, **not pretrained Qwen or LoRA training**.
- Problem: arithmetic correctness does not indicate whether observed latency difference is larger than subprocess cold-start noise.

## Implemented change
`scripts/oril_v2_cpu_noise_calibrated_diagnostic.py` loads the raw paired report, paired sidecar, and same-prompt null report; invokes *both* independent arithmetic audits; requires identical checkpoint config SHA-256; and compares the paired median `verbose_elapsed - compact_elapsed` to the **maximum absolute null difference**. If effect does not exceed null maximum, mark `noise_could_explain_observed_effect=true`. If it exceeds, mark only `effect_exceeds_observed_null_max=true`, **never** speed gain verified.

This threshold is a conservative **descriptive screen**, not a significance test, confidence interval, causal inference, or an acceptance gate. Runs may be on different machines, different loads, or different days; matching config SHA is not matching model weights or runner provenance. Even if threshold passes, speed improvement remains **unproven**.

## Usage
```bash
python3 scripts/oril_v2_cpu_noise_calibrated_diagnostic.py \
  --paired-report paired-report.json --paired-sidecar raw-sidecar.json \
  --null-report same-prompt-control.json
```
No protected validator, deployment or approval logic is modified. CI uses synthetic negative tests only. Do not publish private heldout answers.

## Next falsifiable experiment
- P0: freeze **pretrained** Qwen model files and tokenizer SHA; record host, CPU, memory, runner, threads and sampling settings; keep heldout group manifest externally frozen.
- P1–P2: independently review 5–16 real teacher examples; curate train-only compact examples; reject any split overlap.
- P3: same runner, same checkpoint, same tokenization and randomized balanced A/B order; interleave null A/A controls in the **same** measurement session; warm model once to remove repeated cold starts; log every per-call latency, token count and execution order.
- P4: optional GPU LoRA only if actual GPU optimizer steps >0, adapter bytes and SHA exist; otherwise report `모델 학습 미실행`.
- P5: independent heldout paired accuracy evaluation with grouped confidence intervals and explicit baseline; use >=30 groups where feasible, no quality claim on random weights.
- P6: require lower confidence bound on actual token savings >=20%, quality difference lower bound >= -2 percentage points, no protected gate change and explicit approval; otherwise `개선 없음` or `판단불가`.

### Falsifiable hypothesis
H: once same-session null controls are interleaved and model reloading excluded, a measured compact-prompt latency effect remains larger than null noise with stable sign across order strata. Minimum test: 30 balanced pairs + 30 same-session null pairs, same runner and checkpoint; report distribution, stratified medians, 95% paired bootstrap confidence intervals and all raw evidence SHA. Failure: order-specific reversal, null noise covering effect, quality regression, or missing model provenance. Do **not** promote even a successful toy diagnostic as intelligence gain.

### Explicit status
- New code: conservative diagnostic only.
- Pretrained Qwen evaluation: **not performed**.
- Real LoRA GPU training/adapter: **not performed**.
- Independent hidden quality change: **not measured**.
- Developer cycle speed improvement: **not measured**.
