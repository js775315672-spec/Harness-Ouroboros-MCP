# ORIL v2 slot 4/5 — local Qwen checkpoint path preflight

## Baseline and overlap avoidance
- main `8fbecb5e813b653213d6c8d95ce7151868779512`
- Stacked on slot3 PR #295 head `e20781596157ee423134a0d53c137c277befc3ce`, which added a local-only Qwen inference adapter. Other active PR #292–#294 concern inference report reservation, adapter JSON and bounded subprocess stdout, and are untouched.
- Slot3 CI initially failed twice at SHA `1f070605...` then passed twice at `e207815...`: https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44801356996

## Falsifiable threat
`ensure_local_model()` rejected a symlink at the final model directory but accepted an ancestor symlink or symlinked `config.json`. Therefore the local model path could point outside the operator's intended checkpoint tree even with `local_files_only=True`. A strict no-symlink path policy should reject those cases before importing torch or loading any weights.

## Change
- Reject symlink components in the model path ancestry, including the model directory.
- Reject symlinked `config.json` while retaining normal nested directories.
- Seven synthetic filesystem regression tests; CI runs seven new plus fourteen inherited local adapter tests on a separate Ubuntu runner.
- No protected validators, approvals, deployment, or training weights changed.

## Limitations
This is **not** an atomic filesystem security boundary. A concurrent rename or swap after preflight, or malicious symlinked weight files inside the checkpoint directory, may still redirect loading. It does not prove checkpoint provenance, GPU use, actual Qwen inference, real LoRA training or intelligence gains. Future safe loading requires pinned directory descriptors / controlled immutable checkpoint snapshot and trusted artifact hashes; never claim that static `Path.is_symlink()` defeats races.

## Next P0–P6 experiment
1. P0–P2: obtain approved immutable checkpoint, tokenizer SHA, and real reviewed teacher examples, freeze private heldout >=30 groups.
2. P3: compare verbose vs distilled student context on identical heldout groups with actual tokenizer token counts and end-to-end latency (including cold start), record model SHA and environment.
3. P4: optional GPU LoRA only with real optimizer steps, GPU job log and generated adapter bytes+SHA; no synthetic claims.
4. P5: independent evaluator verifies model outputs and paired correctness / regression with confidence intervals; no heldout answer leakage.
5. P6: do not merge protected gates or deploy without approval. If no GPU/checkpoint/heldout is available, mark **model improvement: none/unverified** and register a minimum measurable run.

### Acceptance
Seven new tests plus 14 inherited tests must pass at the exact head SHA, no skips. Record all failures and retries; CI success only proves offline contract tests, not model performance.
