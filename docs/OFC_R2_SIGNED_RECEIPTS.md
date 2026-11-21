# OFC R2 - Authenticated external receipts

Status: Draft only, NOT production-enabled. Ouroboros, Cerberus and Fenrir use independent operation ledgers, verifiers and trust keys.

## Signed receipt contract

R1 reserves a stable cycle_id, operation_id, effect_id, agent and source SHA before any external side effect. R2 adds an attestation to the resulting OFC-R1-RECEIPT JSON.

attestation fields: scheme = hmac-sha256; key_id = separately provisioned verifier key identifier; signature = lowercase 64-character hex HMAC-SHA256.

The exact HMAC input is a UTF-8 prefix OFC-R2-RECEIPT-V1 followed by one zero byte, the UTF-8 AGENT ID and another zero byte, followed by the canonical JSON of the whole receipt minus attestation. Canonical JSON is sorted keys, ensure_ascii=False and compact comma/colon separators.

Verifier environment parameters: OFC_R2_VERIFIER_KEY_ID and OFC_R2_VERIFIER_KEY. A missing key, mismatched ID, key shorter than 32 UTF-8 bytes, incorrect signature, unsigned receipt or changed payload MUST block. When blocked, leave the pending operation and Git ref unchanged.

Before issuing a signed receipt, an independently controlled verifier must inspect externally authenticated API data or a separately authoritative signed result. Caller-provided text, an arbitrary API URL, a receipt hash or a matching HMAC alone does not prove an external action happened.

IMPORTANT TRUST LIMITATION: HMAC is a shared-secret mechanism. If a worker has the verification secret, it can forge receipts. Do not install any real signing key in PR-triggered Actions or worker environments. For production independent provenance require a separate verifier trust boundary, ideally asymmetric signatures with only a public key on the worker, or an authenticated external read-only API proving the effect.

## Attack checks

Test-only independently seeded fixture keys, on isolated disposable Git registries, exercise: unsigned receipts; wrong key IDs; missing keys; modified proof, source, agent, cycle, operation, effect and receipt ID; cross-agent MAC domain; duplicate receipts after rollover; stale leases and concurrent CAS writes. No real external effects, GitHub merges or production registry mutations.

Historical 114-commit registries, 24 generations, 20 distinct cycle IDs and 19 completion transitions per agent are not backfilled and are not evidence of model improvement. R2 only protects forward-written R1 receipts.

## Remaining gates

Approve verifier identity, secret custody or asymmetric public-key model, independent external result attestation, all Windows/Linux CI results on exact SHA, admin policy and operational authorization before enabling D stage. Otherwise A/B remains BLOCKED and no merge is permitted.