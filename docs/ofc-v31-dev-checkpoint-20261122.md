# Ouroboros DEV checkpoint — OFC v3.1

Scope: DEV only. Base main SHA: `6b44c67a4f69cdc7cbbd983356e5795a551b48fc`. Independent objective: reproducible implementation and generalization improvement; no OPS lease or protected evaluator access.

## Falsifiable P0 hypothesis
A recovery implementation can pass its local unit tests while failing on real remote Git CAS contention or on Windows CRLF paths. Disprove by showing two competing writers where at most one succeeds and all pending/results survive; repeat on Linux and Windows.

## Existing review target
- Draft PR #356: https://github.com/js775315672-spec/Harness-Ouroboros-MCP/pull/356
- CI evidence must be attached to the **exact PR head SHA**, including Windows and Linux jobs. An unrelated successful documentation workflow does not count.
- Check ORIL README marker generation for duplicate/missing markers and unexpected README overwrites.

## Required test cases (not yet executed in this DEV checkpoint)
1. Two remote CAS writers with the same expected ref: exactly one success.
2. Expired lease plus pending receipt: pending is preserved; no reissue of side effect.
3. Main source changes between inspect and CAS: abort, no false PASS.
4. Windows CRLF registry paths: canonical parsing, no spurious tree entries.
5. Repeated identical attempt: idempotent, with original receipt retained.

## Evidence gate
Record workflow run URL, head/base SHA, command, exit code, artifact digest, runtime, cost and comparison baseline. Until verified: `CI=UNKNOWN`, `MODEL=NOT_RUN`, `INDEPENDENT_EVAL=NOT_RUN`, `IMPROVEMENT=UNPROVEN`.

Next single action: run Windows/Linux negative tests on #356 exact head and publish evidence. Do not merge or change main/OPS.
