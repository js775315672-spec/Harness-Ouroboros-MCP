# ORIL v2 slot 2/5 — real Qwen/LoRA readiness audit

## Baseline and purpose
Base: PR #298 head `2eb874847af5e0ec8049b44c3b18795394872a00`, main `8fbecb5e813b653213d6c8d95ce7151868779512`. Previous PR #295–#298 built a local Qwen inference adapter and hardened its preflight, but their CI tests use synthetic mocks. **No actual GPU optimizer steps, adapter SHA, or independent heldout evaluation were established.**

The critical bottleneck is not another synthetic preflight test: it is a **measurable inventory of real execution prerequisites**. This read-only probe reports whether the environment has an actual local checkpoint directory with config/weight files, a nonempty heldout input, and an optional LoRA adapter directory. It checks GPU presence via `nvidia-smi` (with 5s timeout), not by synthetic torch mocks.

```bash
python3 scripts/oril_v2_real_model_readiness_audit.py \
  --checkpoint /approved/local/qwen \
  --heldout /private/frozen/heldout.jsonl \
  --adapter /approved/adapter \
  --output readiness.json
```

Do not put private heldout answers, model weights, user paths or credentials into GitHub. Only non-sensitive boolean metadata and config SHA are exported.

## Important evidence boundary
- Local files can be forged; their presence does not establish an actual model or correct inference.
- `nvidia-smi` detects a device, not GPU training, torch compatibility or actual model utilization.
- `ready_for_proven_lora_training` is **always false** in this audit. It requires independently anchored actual optimizer-step logs, device usage, adapter bytes/hash, and separate heldout evaluator results.
- CI on GitHub-hosted runner is a **real environment probe**, not an actual Qwen invocation. The artifact is evidence of that runner's prerequisites only, not the user's local machine.

## Falsifiable next experiment
H1: Current standard CI runner cannot perform real Qwen evaluation because no local model checkpoint/heldout data is present. Run the new read-only workflow, inspect `readiness.json` artifact, and count missing prerequisites; H1 is falsified if the runner reports both a real checkpoint file and heldout file (note: content authenticity still needs review).

H2: A separate explicitly authorized GPU environment with approved checkpoint and frozen private heldout data can execute one real paired inference cycle. Measure actual model SHA, tokenizer tokens, wall time, device memory and exact heldout pass/fail; require >=30 independent groups before quality noninferiority claims. Record missing GPU/model/data separately, never substitute synthetic fixtures.

H3: Actual LoRA training is possible only after optimizer steps >0 and a real adapter with bytes and SHA exists; external independent heldout assessment must be compared against baseline. A model mock or a GPU-presence boolean is not sufficient.

## P0–P6 handoff
P0 freeze model, dataset and reviewer identifiers. P1 inventory available local files and devices. P2 keep distilled training records private and separated from heldout. P3 run a real model only on an approved runner. P4 optional GPU LoRA with verified logs. P5 independent heldout scoring. P6 promotion remains blocked pending explicit user approval.

**No changes** to protected validators, approval gates, production deploy, or model weights. If prerequisites remain absent, report `개선 없음` for model quality and switch next-cycle effort to obtaining real approved execution resources rather than more mock-only tests.
