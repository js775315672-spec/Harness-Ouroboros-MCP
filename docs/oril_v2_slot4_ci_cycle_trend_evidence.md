# ORIL v2 Slot 4 — CI timing trend evidence, not model speed

**Baseline** main `8fbecb5e813b653213d6c8d95ce7151868779512`. PR #307–#311 introduced actual tiny random-weight CPU experiments, independent arithmetic audits and same-prompt negative control. PR #311 CI success: https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44828664022. Actual pretrained Qwen/LoRA/heldout quality improvement remains **unverified**.

## New distinct improvement

Existing reports repeatedly lacked the last 5–12 cycle median, comparable CI wall/queue time, and source SHA/URL. This isolated **read-only** offline auditor ingests a GitHub REST `actions/runs` response and reports comparable **same workflow + event** timing and failure samples with exact source URLs and SHA. It does not modify model, evaluator, approval gate or deployment.

```bash
# Supply a saved official GitHub Actions API response (e.g. a trusted operator snapshot).
python3 scripts/oril_v2_ci_cycle_trend_audit.py \
  --runs-json actions_runs_snapshot.json \
  --workflow 'ORIL v2 slot3 CPU null-calibrated diagnostic (experimental)' \
  --window 12
```

Results include median elapsed and queue times, newer/older medians, sample n, descriptive change percent, failure fraction, and evidence URLs. **The script never classifies a CI duration change as verified model or development speed improvement**: even within one workflow, commits and test difficulty can differ. `updated_at` is only a completion proxy. Retry rate cannot be measured without attempt-level data; independent improvements/hour requires external review; actual developer/model-call/heldout quality times are unknown.

## Next falsifiable experiment

H1: A trusted Actions snapshot containing at least 6 completed same-workflow and same-event runs yields exact, independently reproducible wall/queue medians and failure fraction, with no invented model metrics. Acceptance: synthetic regression 18/18; exact head SHA and URLs preserved; manually cross-check 2–3 sampled runs against GitHub API timestamps.

H2: after capturing actual independent pretrained model task traces, separately measure model latency and heldout quality for **the same task difficulty and fixed benchmark**; only classify speed as improved when comparable n>=5 and quality is not worse. A 20% token savings target alone does not establish quality.

**Risk:** Public workflow metadata does not attest GPU training, adapter file generation, independent heldout evaluation, real model accuracy, or that a runner's workload was constant. Do not conflate Actions success with intelligence improvement. No evidence -> **개선 없음** for model quality, speed **판단불가**.

**Handoff:** #251, PR #307–#311. Obtain a trusted raw Actions JSON snapshot and validate the 5–12 run trend. Then prioritize real pretrained Qwen + frozen heldout and GPU adapter evidence instead of accumulating synthetic tests. Keep all protected approval gates untouched.
