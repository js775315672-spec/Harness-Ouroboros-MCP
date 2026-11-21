# ORIL v2 P0–P6 slot 1 — 30 public arithmetic groups, 60 pretrained Qwen CPU calls

## Why
Slot 2 PR #315 ran only four public arithmetic tasks (8 actual calls). Slot 5 PR #318 independently recomputed their public labels. Slots 3–4 PR #316–#317 separately implement a frozen A/B+A/A plan and observation binding for future heldout tasks. **This PR does not duplicate or modify any of those interfaces**. It adds a larger *real* public Qwen CPU diagnostic to reveal whether the four-task findings generalize even within one narrow public task family.

## P0–P6
- P0: pin exact base #318 SHA `94ce36cdd83c89c3c2a7cb34c7105f2277191466`, model ID, resolved Hugging Face revision, weight-file SHA256 and runner SHA.
- P1: deterministically generate 30 unique, *public* addition tasks. Never call them hidden/heldout, never put private data into public CI.
- P2: reuse the already reviewed compact and verbose prompt templates and explicit attention mask from #315; 30 pairs, balanced order, model loaded once.
- P3: run actual pretrained Qwen2.5-0.5B-Instruct CPU inference for 60 observations; capture raw generated strings, tokenizer input token counts, inference-only seconds and checkpoint metadata. No training.
- P4: recompute expected public arithmetic answers and token totals from raw observations in a separate CI step, rejecting missing, reordered or mislabeled records. This is not external execution attestation.
- P5: report public exact matches (out of 30 each), input token savings and descriptive median inference latency. No confidence claim from repeated arithmetic patterns; A/A controls and hidden quality evaluation are absent.
- P6: Draft only. No promotion, model improvement or GPU LoRA claim; protected verifier, deployment and approval gates unchanged.

## Falsifiable test
Hypothesis: the 4-public-task token savings and answer-match observations may fail to generalize to 30 deterministic public arithmetic groups. Minimum success is 15/15 offline regression tests, 60/60 real pretrained calls, full raw JSON artifact, and independently recomputed public labels. Failure or missing artifacts = **개선 없음**. Even success only establishes a narrow public diagnostic, not an intelligence gain.

## Commands
```bash
python3 -m unittest discover -s tests -p test_oril_v2_slot1_30_public_qwen_pairs.py -v
python3 scripts/oril_v2_slot1_30_public_qwen_pairs.py --output public_30_pairs.json
```

## Risks and next handoff
Public questions are all simple addition, correlated and visible in source. They cannot establish independent heldout correctness or knowledge distillation quality. The actual model is pre-trained but unmodified, and CPU performance depends on runner hardware. The script relies on the remote model registry at run time; a resolved revision is captured but not frozen before run. A successful CPU run must not be reported as GPU training or LoRA adapter creation.

Next: obtain independently reviewed teacher examples and 30+ **private** frozen task families, use PR #316/#317 A/B+A/A plan, measure actual tokenizer tokens, latency, independent paired correctness, then (only with GPU and user approval) run LoRA with real adapter bytes and SHA. Do not infer gain from 30 public arithmetic questions.
