# ORIL v2 slot 3 — independent arithmetic audit of real CPU *synthetic* Qwen reports

Baseline: main `8fbecb5e813b653213d6c8d95ce7151868779512`; latest stacked slot 2 PR #304 `d116caeb6d83117622c9c4fd2da6475fbfa4196b` with independent CPU runner success [Actions #44818104026](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44818104026). PR #303 generated 6 paired / 12 real CPU forward calls on **random tiny Qwen2 weights**; this is not pretrained Qwen or LoRA.

## Hypothesis and measurable experiment

H: A synthetic CPU benchmark JSON can be accidentally edited or tampered with to inflate claimed token savings or latency improvement even though its raw token vectors / paired differences disagree. A separate verifier should reject mismatches **without trusting the benchmark summary function**.

New `scripts/oril_v2_cpu_pair_report_audit.py` recomputes tokenizer-input savings and paired latency median from recorded vectors, rejects unsupported model learning and GPU claims, validates bounded schema, counts and observed order. Run: `python scripts/oril_v2_cpu_pair_report_audit.py synthetic_cpu_paired_report.json`. A separate CI suite tests deliberately falsified reports and checks round-trip compatibility with #304.

**Critical limits:** The report contains no raw per-variant latency vectors, so individual compact/verbose median latencies cannot be independently reconstructed. Source data are self-reported and not signed; this audit does not prove actual CPU execution, weights provenance, independent heldout quality, or model training. It explicitly outputs `provenance_attested=false`, `model_quality_verified=false`, `real_gpu_lora_verified=false`.

## Next P0–P6 handoff

- P0/P1: Freeze an approved pretrained Qwen checkpoint, real reviewed teacher examples (5–16, <=6000 chars), and independently sealed heldout >=30 groups; otherwise report unavailable.
- P2/P3: Add raw per-call elapsed time, prompt digest, tokenizer SHA, input/output token vectors, observed order and exact workflow run SHA to a **separate signed or independently pinned manifest**. Verify medians from raw values; never accept a summary alone.
- P4: Only if a real GPU is present, run LoRA with optimizer steps >0 and SHA/size of actual adapter files; do not infer training from CPU inference.
- P5: Compare verbose/compact prompts on identical pretrained student with frozen heldout tasks; report paired accuracy and token savings with confidence intervals.
- P6: Require noninferiority, independent review and user approval before promotion. No protected gate or deployment modifications.

If the new CI fails, mark **개선 없음**, record exact failed test and SHA, and hand off a minimal reproducer. A successful arithmetic audit is an evidence-quality improvement only, never intelligence gain.
