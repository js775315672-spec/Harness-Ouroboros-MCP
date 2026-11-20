# ORIL v1.1 evidence and baseline

Specification [#231](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/issues/231). Historical source [audit #230](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/pull/230) and [Actions 44615918955](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44615918955).

The historical import verifies raw model and grade archive contents, the final chain, and each approved candidate file at its exact commit. Cycle 3 also uses the separate compatibility regrade at run 44563477087. Cycle 7 uses the original model worker and separate successful grade run. Rollback count is reported as zero in the historical record. End-to-end time, CPU, RAM and speedup are unavailable for a matched comparison. Stage medians are 46, 11 and 25 seconds. Their sum of 82 seconds does not represent an end-to-end median.

## Ledger contract

Append one UTF-8 JSON object per line. Corrections append a new record referencing the superseded record. Historical rows use source historical and never count toward ORIL. Audit status is verified, reported or unverified. Preserve field-level provenance. A prospective row must record its unique cycle and predecessor IDs, hypothesis, authorization, baseline identities, fixed workload IDs, model run and output SHA, candidate commit and file SHA, independent run and grade, operation run if approved, A/B measurements, failures, rollbacks, and the next task rationale. Null measurements require a reason. A successful grade and a demonstrated improvement are distinct fields.

## Baseline and execution gates

The repository source and three public workload files are pinned. The public workload commit is separate because main contains standing orchestration and approval receipts. No prospective baseline is frozen until independent grader and hidden-suite digests, runner image digest, CPU affinity, cache protocol and CPU cap are independently reviewed and pinned. Hidden evaluation contents stay outside worker inputs.

The existing W01–W08 interfaces remain in place. W01/W02 cover input contracts and provenance. W03/W04 cover diagnosis and one-call controls. W05 has a separate detector/replay validator, W06 a model execution path, W07 candidate and rollback gates, and W08 a separate independent handoff. Historical success covers the audited Hydra path. This draft does not constitute P1 instrumentation, P2 benchmark validation, P3 execution or P4 final audit.

For P2, compare baseline and candidate in balanced ABBA order on the same runner, with at least five paired observations per workload and cache condition before a confirmatory claim. Require independent PASS, no critical regressions and a reproducible gain before inheriting a candidate baseline. When no gain is established, use NO_DEMONSTRATED_GAIN.

The current standing approval is for the already spent historical cycle-nine replay. The ORIL approval budget is zero. Request explicit approval for cycle 01 Qwen invocation and a numerical CPU cap after the execution manifest is frozen. Request operational replay approval separately once that candidate passes.
