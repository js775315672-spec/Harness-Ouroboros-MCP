# ORIL v2 slot 5/5 — actual CPU raw timing sidecar integration

Baseline: main `8fbecb5e813b653213d6c8d95ce7151868779512`; stacked on #306 SHA `1caac2164c5226c310f73814b1cb7e4cf0b9d731`. #306 introduced an auditor but **did not** run a new real benchmark producing its expected sidecar. This cycle connects actual 12 CPU Qwen2 random-weight generations to that independent arithmetic auditor without changing the auditor.

## Reproduction

```bash
python scripts/oril_v2_tiny_qwen_cpu_paired_benchmark.py --report synthetic_cpu_paired_report.json --sidecar synthetic_cpu_raw_sidecar.json
python scripts/oril_v2_cpu_raw_latency_sidecar_audit.py synthetic_cpu_paired_report.json synthetic_cpu_raw_sidecar.json
```

The six pair records capture elapsed seconds, input tokens and actual observed execution order directly from the invocation results. A SHA-256 digest binds the raw sidecar to the exact canonical summary. CI runs 6 new regression tests, existing raw auditor and benchmark tests, then the **real** synthetic CPU benchmark and auditor, publishing three artifacts. Historical reports without sidecars are **not** retroactively verified.

## Evidence scope and explicit non-claims

- Real CPU execution of a **random-weight tiny Qwen2**, synthetic prompts and toy tokenizer; not pretrained inference, GPU fine-tuning, or LoRA.
- A matching digest is self-reported and **not a signed or independent provenance attestation**. The independent runner checks arithmetic but cannot prove source provenance beyond its own logs and artifact association.
- No actual teacher knowledge distilled, no experience memory quality improvement, no hidden heldout evaluation. The measured compact/verbose prompt difference is a synthetic-token proxy, not an improvement in intelligence.
- Raw per-call elapsed values reflect cold-start subprocess overhead and variable runner conditions; no causal speed-up claims from this experiment.
- Output paths refuse existing files and direct symlinks; not a full atomic multi-file publish or directory-race protection. Keep artifacts in isolated ephemeral CI working directory.
- Do not merge Draft PRs, modify protected validators, approval gates, or deploy.

## Falsifiable next step

H1: for six balanced pairs, every observed raw timing and token vector matches the summary arithmetic. Accept if all tests and exact-SHA CI pass, no skips, 12 actual generations and 6 raw records, and no unsupported model claims. Otherwise mark **개선 없음** and isolate failure.

H2 (not executed): approved pretrained Qwen checkpoint with pinned SHA, frozen independent heldout >=30 groups, paired verbose/distilled prompts and exact tokenizer counts; quality lower confidence bound >= -2 percentage points and measured token reduction >=20%. If unavailable, report **판단불가** rather than extrapolate from synthetic CPU data.

H3 (not executed): actual GPU LoRA optimizer steps >0, adapter file bytes/SHA, independent heldout quality evaluation and explicit approval. No GPU or adapter evidence in this PR.

## Cycle trend measurement requirements

Compare same-task independent Actions job durations and exact SHA, n and medians; record total wall time, model call time, independent CI time, operational followup, throughput, retries, failures, regressions, rollbacks, and waiting. If any metric is absent mark 미측정. No invented improvement rates. Next bottleneck is pretrained Qwen + trusted heldout, not additional synthetic safety tests.
