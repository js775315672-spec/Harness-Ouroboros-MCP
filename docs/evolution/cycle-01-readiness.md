# ORIL Cycle 01 readiness

Status **BLOCKED BEFORE DISPATCH**. ORIL completion 0/12, new Qwen calls 0, independent passes 0, demonstrated gains 0.

P0 replay [44643574019](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44643574019) verified nine historical approvals and three public workload hashes. Historical W05 replay [44288613606](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44288613606/job/134750667622) establishes a separate verifier in a previous task. Its verdict does not establish an ORIL holdout or grader configuration. The matched CPU rehearsal at 184d8e4fac981212a3920b7fbcaacb63dd8a94d3 is a reference for runner setup.

## Proposed first task

Measure the cost of appending and validating one evidence record with the pinned public evidence workload. Test the hypothesis that duplicate reads can be reduced while preserving verdicts and failure reporting. Before inference, identify the actual measurement target and failure or bottleneck, pin the independent grader and private holdout digests, record the runner image and affinity, and freeze cold and warm cache handling. Use balanced A/B observations on the same runner and require independent confirmation with zero critical regressions.

## Approval request

Proposed Cycle 01 limit is one invocation of the existing CPU Qwen model and 1,200 aggregate CPU seconds across the model, grading and benchmark jobs. This is a proposed cap, with no authorized run yet. Agree the cap and bind the approval to the final manifest and input SHA before dispatch. Operational replay is subject to separate approval after an independent pass. No model or operational jobs were started.
