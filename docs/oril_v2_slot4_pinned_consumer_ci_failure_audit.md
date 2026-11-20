# ORIL v2 slot 4 — pinned consumer CI failure audit (2026-11-21 KST)

## Baseline
- main: `8fbecb5e813b653213d6c8d95ce7151868779512`
- stacked predecessor Draft PR #285 head: `c7caaa8af8e91a0e0cbde2407d68bb78e8984584`
- actual failed Actions: https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44783597468, job `136452459971`.
- The runner ran **17 pinned-consumer tests in 0.046 seconds**, with **16 passed, 1 failed**, and exited 1 before running the inherited marker and curation suites.

## Root cause, observed
`test_replaced_path_during_open_is_rejected` expected exception text `path replaced`, but `consume()` rejected the malicious path replacement earlier with `ValueError: file changed during snapshot`. This is a **fail-closed rejection** of the swapped path, but the test's exact diagnostic expectation was stale. Do not count the failed CI as a successful gate.

## Narrow patch and falsifiable test
This stacked Draft changes only the one regression test to assert the observed exact fail-closed diagnostic, retaining the malicious rename-and-replace operation and the requirement for an exception. No production code, validator, gate, or deployment changes.

Hypothesis: at this exact SHA, the 17 pinned-consumer tests and inherited pair-marker/teacher-curation tests will pass without skips. If any test fails, report **no verified improvement** and investigate the first failing case; do not silently broaden the expected error to `Exception` or mark security proven. Independently validate on GitHub Actions, record merge checkout SHA distinct from PR head SHA.

## Boundaries
The test checks one deterministic path replacement, not 1,000 races or hostile same-user in-place file writes. No actual student inference, real teacher provenance, LoRA GPU run, adapter SHA, or heldout improvement is evidenced. Treat model quality and speed as unmeasured. Preserve all PR #284/#285 stacking and approval boundaries.

## Next handoff
After CI green, prefer an isolated real student inference baseline/compact pair with frozen heldout task groups and tokenizer telemetry over additional synthetic-only tests. Record exact artifact SHA, GPU evidence if training is actually attempted, latency, accuracy, token counts, and independent reviewer ownership.
