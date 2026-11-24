# ouroboros — P0 expired-lease recovery amendment (proposal)

Status: BLOCKED / design-only. This document is not a claim of an implemented recovery fix.

## Reproduced risk from prior audit
A valid execution lease can record a merge receipt, but after lease expiry an unresolved pending operation cannot be reconciled. Preserve the existing fail-closed behavior until an authenticated recovery path is independently verified.

## Proposed recovery contract
1. Read immutable merge intent and current registry generation from this repository's own registry ref. Never accept another agent's state.
2. Verify repository identity, PR number, expected head SHA, pre-merge main SHA, operation ID, and authenticated provenance before considering reconciliation.
3. Re-read authoritative GitHub PR merge status and merge commit; reject unknown, changed, ambiguous, or contradictory responses.
4. Under a fresh lease and compare-and-swap generation, append a reconciliation receipt referring to the original operation ID. An expired lease must never authorize a write.
5. If merge is not independently confirmed, leave pending blocked. Never infer success from a CI green check or a missing branch.
6. Retry is idempotent: the same operation cannot create duplicate receipts or repeat external mutations. Concurrent recovery attempts must have at most one winner.
7. Preserve the full prior results ledger and audit trail; reject cross-repository, mismatched SHA, replayed token, and stale generation inputs.

## Required independent tests (not yet executed)
- valid lease, valid receipt -> PASS; expired lease with pending -> BLOCKED
- expired lease + independently verified merged PR + fresh recovery lease -> one reconciliation receipt
- expired lease + unmerged/unknown PR -> BLOCKED, no mutation
- wrong repository, PR, head, base, merge SHA, or operation ID -> BLOCKED
- two concurrent recoveries -> one append, no lost ledger entries
- repeated recovery -> idempotent, no duplicate receipts
- simulated API timeout/partial response -> BLOCKED
- Linux and Windows registry CI on exact candidate SHA
- merge-then-expire bootstrap using a temporary Git registry clone

## Release gate
No main update, no automatic merge, no live external mutation. A-stage verification of CI, registry head, and audit evidence remains outstanding. B-stage is NOT complete until executable implementation, tests, independent reproduction, and reviewed Draft PR all pass.
