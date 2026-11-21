# ORIL v2 slot 5/5 — 30 public Qwen A/B vs A/A cross-run reconciliation

## Starting point
- main: `8fbecb5e813b653213d6c8d95ce7151868779512`
- slot1 #319 real public 30 A/B pairs: [Actions #44841372111](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44841372111) successful.
- slot2 #320 independent A/B audit: [Actions #44842735795](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44842735795) successful.
- slot3 #321 real public A/A null: [Actions #44843133109](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44843133109) successful.
- slot4 #322 independent A/A audit: [Actions #44845194043](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44845194043) successful.

These are **public** arithmetic tasks, not independent heldout. A GitHub Actions success is not automatically proof that archived raw JSON was independently retrieved and inspected.

## New isolated integration
`scripts/oril_v2_slot5_public_ab_aa_reconciliation.py` imports only the two independent audit functions, never the experimental producer's summarizers. It rejects differences in model ID, resolved revision, task digest, exact weight names/bytes/SHA, group order/questions, and compact tokenizer input count. It computes descriptive A/B median compact-minus-verbose CPU seconds and A/A median absolute same-prompt drift; never claims causal speed or intelligence gains. **Cross-run timing comparison is not a matched experiment.**

After obtaining the *real* JSON artifacts from #319 and #321 (not synthetic examples):

```bash
python3 scripts/oril_v2_slot5_public_ab_aa_reconciliation.py \
  --ab public30-ab-raw.json --aa public30-aa-raw.json \
  --output public30-crossrun-audit.json
```

The tool is deliberately fail-closed if exact model weights/revisions or tokenization differ. No arbitrary fabricated numbers are accepted as empirical results. Metadata are producer assertions; independent evidence retrieval and cryptographic provenance are still required.

## P0–P6 next cycle
1. P0: freeze real source Actions URLs, exact head SHAs, model checkpoint and public task digest; save artifact SHA256 and runner provenance.
2. P1: independently download both 7-day artifacts and verify source run/head SHA before passing to the tool. If expired or inaccessible, mark **개선 없음** for cross-run empirical evidence.
3. P2–P3: run both independent raw audits, then cross-run reconciliation, capture exact errors and output SHA. Treat public descriptive token savings as measured only if raw artifacts are real.
4. P4: actual student LoRA is a separate GPU experiment; require CUDA execution, optimizer steps >0, adapter bytes and SHA, and fixed baseline. No synthetic training claims.
5. P5: run a *single-session*, counterbalanced, frozen **independent heldout** A/B+A/A design with >=30 independent task groups, identical checkpoint, actual tokenizer tokens, latency and paired correctness; report CI and regression.
6. P6: record validated evidence and failure hypotheses in #251. Never self-approve or deploy.

**Falsifiable next hypothesis:** cross-run model revision/weight hash/tokenization can differ despite separately green CIs. If so, fail closed rather than combining the results. If all match, the public diagnostics can be reconciled, but causal speed and hidden quality remain **판단불가**. A/A same-session drift is a necessary negative control for a future causal experiment, not sufficient evidence from separate Actions jobs.

This PR adds only a standalone reconciliation script, tests, CI and docs; it does not change protected validators, approval gates, training or deployment.
