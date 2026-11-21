# ORIL v2.0 slot4 — independent public Qwen A/A null audit

P0 reference: main `8fbecb5e813b653213d6c8d95ce7151868779512`. This PR is stacked **on PR #321 head `7cc6d2b61531507ce6db2ea1310577b7429da1c4`**, and does not modify slot1 #319, slot2 #320 or slot3 #321 source files.

## Why

Slot3 #321 executes 30 *public* arithmetic questions twice each using identical compact prompts on pretrained Qwen CPU, and emits a self-reported latency null-control report. The experiment's own `audit_null` cannot count as independent verification. This slot adds a separate, import-free consumer that recomputes 30-group raw A/A signed and absolute drift medians, call median, token totals, public labels, task SHA, and rejects false LoRA/heldout/speed assertions. No extra model call is needed. This is a **measurement integrity** improvement, not model intelligence improvement.

## P1–P3 usage

```sh
python3 scripts/oril_v2_slot4_public30_aa_independent_audit.py \
  --input actual_public_aa_report.json \
  --output independently_recomputed_public_aa.json
```

Do not use a synthetic fixture to claim real Qwen execution. The real report must be obtained from the completed slot3 Actions artifact, not invented or manually reconstructed. GitHub CI test uses synthetic adversarial inputs to check the audit logic only.

## P4–P6 acceptance

- Unit tests: 16/16, 0 skipped on exact PR SHA, plus **actual slot3 raw JSON artifact** audited independently.
- If the artifact is not accessible, mark actual A/A cross-check **미측정**; do not claim complete independent audit.
- Record both upstream #321 Actions URL and this PR's audit CI URL, model revision and SHA. Never treat self-reported weight hash metadata as proof of locally verified weights.
- Do not claim A/A timing drift demonstrates compact-vs-verbose speed causality. The null-control is a *noise reference*, not a speedup benchmark.
- Independent hidden evaluation and real GPU LoRA remain separate gated tasks; no promotion or merge without user approval.

## Next hypothesis

**H:** the 30 real public A/A pairs contain enough run-to-run timing variation to make a naive compact/verbose speed claim unreliable. **Minimal test:** obtain authentic raw A/A and A/B JSON artifacts from #321 and #319, audit each independently, compute paired per-group A/B differences relative to A/A null drift; report effect size and bootstrap CI (resampling groups, not calls). **Pass:** consistent hashes/model revision, valid raw observations, nonzero real sample, and uncertainty reported. **Fail/unknown:** missing artifacts or unpaired conditions; report `판단불가`. Do not claim model accuracy improvement from public arithmetic alone.

## Cycle accounting

Changes in this PR: independent source, 16 synthetic regression tests, read-only workflow, documentation. Actual Qwen calls **0 in this PR**; GPU optimizer steps **0**; new adapters **0**; hidden tasks **0**. Total development duration and model quality delta not measured. Keep the prior 5–12-cycle comparison as `판단불가` until homogeneous raw evidence is available.
