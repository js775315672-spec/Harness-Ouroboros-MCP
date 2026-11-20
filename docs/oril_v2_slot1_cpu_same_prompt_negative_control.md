# ORIL v2 P0–P6 — CPU same-prompt negative control (slot 1/5)

## Baseline, non-duplication
- Main SHA: `8fbecb5e813b653213d6c8d95ce7151868779512`.
- Slot 5 PR #307 SHA `673aedaccdf2fa7b596f929ba9d6d79d83c0886b`: actual tiny **random-weight** Qwen2 CPU pairs and raw timings.
- Slot 1 PR #308 SHA `fd800d4a5c842bd6da4f829101fc5c5282b8137b`: order-stratified diagnostics.
- This PR is **additive** atop #308 and does not modify the order auditor, existing benchmark, protected validators, or deployment.

## New falsifiable experiment
H0: when both A and B use the **same prompt and same tiny random-weight Qwen2 checkpoint**, their measured CPU cold-start times can still differ due to subprocess startup, scheduling and call order. This can mimic a prompt speed effect. Execute 6 balanced pairs, 12 actual independent subprocess generations, and record raw elapsed seconds, per-order medians and absolute paired noise. A/B use exactly `SHORT`; no prompt optimization, no accuracy change.

- Unit tests use mocks and only validate arithmetic, bounds, balanced order, honest claim flags.
- Separate CI job installs CPU torch/transformers, executes actual CPU subprocess calls and uploads raw JSON.
- If negative-control median absolute difference is material compared with #307's compact/verbose median difference, mark apparent speed benefit **confounded**; if smaller, **still do not claim** speed gain because sample size is tiny and execution is cold-start.
- This is a **negative control**, not a threshold-based pass/fail speed certification. `negative_control_passed=null` intentionally.

## Interpretation / next cycle
P0 freeze exact checkpoint SHA and runtime versions. P1–P2 keep reviewed train examples isolated from heldout. P3 measure real CPU baseline and negative control. P4 actual LoRA requires GPU training logs, optimizer steps >0 and real adapter bytes+SHA; none are provided here. P5 requires frozen independent heldout cases and pretrained model. P6 only allow improvement claims after matched independent evaluation and user approval.

Run locally:
```bash
python3 -m unittest discover -s tests -p test_oril_v2_cpu_same_prompt_negative_control.py -v
python3 scripts/oril_v2_cpu_same_prompt_negative_control.py --output negative_control.json --pairs 6
```

Do not use self-reported SHA or CI success as proof of model improvement. Report actual CPU execution time, artifact URL, model class and SHA. Compare the order-specific noise with the earlier paired timing only if runner/versions/checkpoint and workload are comparable. Otherwise **판단불가**. Missing pretrained checkpoint, GPU adapter and independent heldout are explicit blockers, not evidence of failure of LoRA itself.

Next minimal experiment: fixed pretrained small Qwen checkpoint, >=30 matched heldout groups, same prompt/order seed, warm model, exact tokenizer token counts, latency median/p95 and quality uncertainty; only accept >=20% token reduction with heldout correctness noninferiority lower bound >=-2pp.
