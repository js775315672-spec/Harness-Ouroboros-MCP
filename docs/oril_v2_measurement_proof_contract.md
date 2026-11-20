# ORIL v2.0 evidence-backed cycle reporting (experimental)

This is a measurement **system**, not a claim that model capability improved. The independent evaluator, approval gate, protected branches, and deployment are unchanged. Never infer model intelligence from a green CI job.

## What is automatically measurable now

Run the evidence bridge from a CI runner with a read-only `GITHUB_TOKEN` having `actions: read` permission:

```bash
python3 scripts/oril_v2_actions_proof_report.py \
  --repo js775315672-spec/Harness-Ouroboros-MCP \
  --workflow 'ORIL v2 single SHA offline integration (experimental)' \
  --event pull_request --window 12 --output oril-v2-ci-proof-report.json
```

Output carries source run URLs/IDs, head commit SHA and separately job API `head_sha` (which is **not** evidence of the actual checked-out commit; obtain that from the checkout step log), CI queue time, measured Job wall-clock, Job sum time, workflow rerun-rate proxy, recent CI failure fraction, successful CI run throughput, and same-workflow/event median (minimum 5 comparable *prior* successful runs required for a latency verdict).

The source is currently the **latest 100** Actions runs only, so older runs may be absent. A matched workflow name/event does not guarantee identical workload difficulty. Never relabel this CI speed verdict as end-to-end agent speed.

Previously overlooked real evidence:
- PR #266: [push run #44736057650](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44736057650), SHA `474fa42099c09f26a78fca6d8cc41552562d9693`: job logs include 3+12 tests successful.
- PR #267: [push run #44738509006](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44738509006), SHA `63e202cb934f597a7a8e7a12a63bcdee0e94d611`: job logs include 6+3+12 tests successful. These runs had **event=push**, not pull_request. The earlier reports that described these tests as unverified were incomplete.

## Capturing future measured model and development phases

Wrap the **real command** in the runner; do not time synthetic actions and call them model-worker evidence:

```bash
python3 scripts/oril_v2_phase_trace.py measure --phase model_call \
  --output oril-v2-phase-spans.jsonl -- python3 your_real_worker.py
python3 scripts/oril_v2_phase_trace.py measure --phase independent_verification \
  --output oril-v2-phase-spans.jsonl -- python3 your_separate_evaluator.py
python3 scripts/oril_v2_phase_trace.py measure --phase operational_followup \
  --output oril-v2-phase-spans.jsonl -- python3 your_followup.py
python3 scripts/oril_v2_phase_trace.py measure --phase whole_cycle \
  --output oril-v2-phase-spans.jsonl -- python3 your_cycle_orchestrator.py
python3 scripts/oril_v2_phase_trace.py summarize oril-v2-phase-spans.jsonl
```

`GITHUB_SHA` in a `pull_request` runner may identify a **temporary merge commit**; never conflate it with `github.event.pull_request.head.sha`. `GITHUB_RUN_ID` binds timing to a source run. The tracer logs only phase metadata, not commands, tokens, environment contents, or user data. A successful wrapper span is a measured monotonic duration, **not proof** that the wrapped command was genuinely a model call, independent evaluation, or operations. The trace is explicitly **unattested** and must be matched to GitHub run logs and independently verified artifacts before promotion.

## Evidence completion matrix: conditions for changing '미측정' to measured

| Report field | Evidence required | If missing |
|---|---|---|
| CI job wall/queue | Actions run/job timestamps + ID + SHA | null |
| Actual end-to-end cycle time | orchestrator `whole_cycle` span on same run, time sync + job log corroboration | null |
| Model call duration | `model_call` span covering actual model runtime, model ID, runner log + trusted execution provenance | null |
| Independent verification duration | `independent_verification` span from separately operated evaluator; match runner job/trace | null |
| Operational follow-up duration | `operational_followup` span including the real approved follow-up | null |
| Waiting/bottleneck | CI queue measured separately; other waits need explicit timestamped workflow events | null |
| Cost | GitHub billing usage and external GPU/API provider usage/receipts, currency & unit prices | null |
| Retry/failure | complete cycle attempts, statuses, and denominators; Actions reruns are **not** agent retries | null |
| Regression/rollback | independent regression records and audited rollback ledger, exact commits, denominators | null |
| Improvements/hour | individually accepted changes with independent approval/evaluation IDs + whole-cycle observation window | null |
| Experience-memory gain | locked memory retrieval task set, prior version, changed version, independent held-out quality and leakage controls | null |
| Dataset-quality gain | immutable dataset version hashes and independent data quality/leakage audits | null |
| Actual GPU training | trusted device/driver usage log, optimizer steps, model/adapter fingerprints, loss metrics & logs, independently fixed hashes | null |
| Adapter creation | actual adapter binary with independent SHA-256, size, model baseline, provenance and load/retest evidence | null |
| Held-out model quality | *independently controlled hidden* test data/labels, baseline & candidate run on identical cases, confidence intervals, regression and leak review | null |

**Comparison rule:** compare only the same task type, difficulty, model baseline and evaluation contract, with 5–12 eligible prior cycles, n/median/delta/source. If source evidence is missing or comparator task difficulty differs, verdict must be **판단불가**. A faster run with worse held-out quality must not be accepted as an improvement.

**Trust rule:** a candidate branch's self-produced hash, source trace, or synthetic GPU log is not an independent anchor. Independent signing/permission-segregated pin storage is still unresolved (issue #251). Never write `provenance_verified=true`, `training_approved=true`, or `promotion_approved=true` solely because a report script or CI succeeded.

## Next experiments / hard gates

1. Run `model_call` and `whole_cycle` around a real, permitted model-worker execution in an approved isolated runner; compare output logs with measured spans. Check separately operated evaluator + operations traces. Validate that a missing phase remains null and a failed phase does not count as successful.
2. Require independent verifier and approval logs to enumerate each accepted improvement with SHA & held-out score before calculating verified improvements/hour or regression rate.
3. Create an independently pinned hidden evaluation set and baseline benchmark, test for memorization/contamination, rerun across seeds and publish confidence intervals. Do not use GitHub runner CI success as model gain.
4. Collect actual GPU/adapter job provenance on approved hardware before claiming weight updates; never manufacture artifacts or execution proof.
5. Link tool output to the already open comparator PR #236/#243 and telemetry PR #237/#239 only after isolated code review, without merging dependent Draft PRs without approval.

The evidence bridge and tracer are *opt-in instrumentation*. They do not modify any protected verifier or deployment path.
