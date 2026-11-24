# OFC R1 — durable operation identity and recovery contract

Status: Draft PR only. **Not production authorization.** Each repository (Ouroboros, Cerberus, Fenrir) has its own independent Git registry, operation ledger, SHA, evidence and CI result. No shared ledger or agent state.

## Core identity

- cycle_id identifies one cycle and comes from the current registry state.
- operation_id identifies a logical operation globally within that one agent.
- effect_id identifies the unique external side effect, even if retried or renamed.
- receipt_id identifies completion evidence and may be consumed only once.
- agent and source bind the operation to its independent repository and pinned main SHA.

After acquiring an active lease, reserve the following JSON as the command value:

~~~json
{
  "protocol": "OFC-R1",
  "agent": "REPLACE_WITH_CURRENT_AGENT",
  "cycle_id": "ACTUAL_REGISTRY_CYCLE",
  "operation_id": "unique-operation-00001",
  "effect_id": "external-effect-00001",
  "source": "ACTUAL_PINNED_MAIN_SHA"
}
~~~

**Do not dispatch the external side effect unless the reserve CAS has succeeded.**
Reusing operation_id OR effect_id must fail even in a new cycle.
A pending attempt with unknown outcome remains pending and must not be re-run.

After separate external-evidence validation, the matching owner may record an outcome with the identical intent followed by an equals sign followed by:

~~~json
{
  "protocol": "OFC-R1-RECEIPT",
  "agent": "REPLACE_WITH_CURRENT_AGENT",
  "cycle_id": "ACTUAL_REGISTRY_CYCLE",
  "operation_id": "unique-operation-00001",
  "effect_id": "external-effect-00001",
  "source": "ACTUAL_PINNED_MAIN_SHA",
  "receipt_id": "unique-receipt-00001",
  "proof": "EXTERNAL_EVIDENCE_VERIFIED_BY_CALLER"
}
~~~

The receipt fields must match the reserved intent. A reused receipt ID, different cycle, agent, source, operation or effect is rejected without mutating the Git ledger.

## Persisted per-agent R1 guard

- operations maps operation_id to cycle_id, effect_id, reservation/recorded status and receipt SHA-256
- effects maps effect_id to operation_id, fenced at **reserve** time
- receipts maps receipt_id to operation_id, fenced at **record** time

The new guard is copied across successful cycle rollovers and is stored via the existing Git CAS push. Losing CAS contenders do not authorize any external execution.

After any R1 reservation is registered, plain-string legacy external reservations are blocked to prevent bypass. Structured PR merge recovery remains bound to verified GitHub merge evidence, with global tombstones for PR and merge SHA. An unknown merge result or expired pending lease does not permit blind retry.

## Failures, limitations and safety boundary

An R1 receipt's SHA-256 is an integrity fingerprint, **not an authenticated external proof**. The caller must separately validate its actual external result. This registry does not call or execute models, trades, merges or third-party side effects.

Historical operational data predates R1. Prior generation 24, 20 cycle IDs and 19 completion transitions per agent are not retroactively proved unique external executions, nor AI performance improvements. This guard is prospective for R1 jobs. Historical state.json CR-suffixed filename anomalies remain preserved for read-only audit and are rejected as active registry trees.

The Windows/Linux CI uses disposable bare Git fixtures to reproduce identity forgery, expired unresolved execution, repeated attempts, repeated receipts, CAS concurrency and separate repositories. Do not modify main or production registry refs to test R1. Keep A/B gate BLOCKED and D-stage disabled until all independent operational authority and external-verification requirements are proven.
