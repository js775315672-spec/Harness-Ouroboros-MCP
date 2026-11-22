# OFC R3 - Ed25519 public-key receipt verification

Status: Draft PR only; no production key, signing service, protected key registry, external effect or operating-ledger mutation is configured in this change.

## Independent trust boundary

Each of Ouroboros, Cerberus and Fenrir has its own independent registry, AGENT domain, public-key trust configuration and receipt history. The verifier inside agent/cycle_registry.py imports only Ed25519PublicKey; it never imports/loads a private signing key. The private signer exists exclusively in disposable isolated CI test fixtures. Real private keys must belong to a separately authorized evidence-verification service, not any executor, PR workflow or LLM development worker.

An Ed25519 signature only attests possession of the corresponding private key and payload integrity. It does not prove external-world execution unless the independent signer actually authenticates that outcome against a trustworthy external API or an externally verifiable record.

## Trust configuration (deployment-controlled, not receipt-controlled)

The executor/verifier accepts OFC_R3_TRUSTED_KEYS_JSON ONLY from a separately protected configuration, not from a PR event, user submission, signed receipt or untrusted code path.

Example public-key-only configuration (placeholders, NOT actual keys):

    {
      "agent": "ACTUAL_AGENT",
      "keys": {"independent-verifier-key-0001": "BASE64_32_BYTE_RAW_ED25519_PUBLIC_KEY"},
      "revoked": []
    }

The trusted agent must equal the local AGENT. Each key ID must be explicitly present in the trusted keys map, and not on revoked. A missing, malformed or mismatched trust root fails closed. Removing a key blocks old signatures; revoking a key blocks it even if retained in keys. A genuinely new verifier key is accepted only after an operator-protected public-key registry update. Store no private keys, signing secrets or credentials in this repository.

## Exact wire protocol

An R1 receipt retains agent, cycle_id, operation_id, effect_id, source, receipt_id and proof. Its attestation has exactly three fields: scheme = ed25519, key_id = trusted issuer identifier, signature = base64 of 64 raw Ed25519 signature bytes.

The signed message is: ASCII prefix OFC-R3-RECEIPT-V1 then one NUL byte, ASCII local AGENT identifier then one NUL byte, then UTF-8 canonical JSON of the receipt WITH the attestation field removed. Canonical JSON uses sorted keys, ensure_ascii=False and separators=(comma, colon), without extra whitespace. Public keys are base64 encoding of the 32 raw Ed25519 public key bytes.

No algorithm negotiation, HMAC downgrade or receipt-supplied public key is accepted. The old R2 HMAC shared-secret verification path is removed. Signatures and JSON fields are verified before a CAS-protected R1 result and its global receipt tombstone are recorded.

## Replay, key rotation and concurrency

R1 remains responsible for stable cycle/effect/operation IDs, reserve-before-execute, exact agent/source binding, persistent global tombstones, CAS single-winner updates and indefinite pending when an external outcome is unknown. A valid old signature does not allow execution twice or bypass a revoked key. In tests, revoked or unknown IDs, replaced public keys, edited proof fields and cross-agent signature attempts fail without updating the simulated Git ref.

## Dependency and CI evidence

GitHub Actions P0 installs the pinned cryptography==46.0.5 package on Windows and Linux; it runs the existing P0/C2/R1 tests plus isolated Ed25519 signing fixtures. Test-only private keys are generated in memory and discarded. GitHub Actions never receives a real R3 private key.

## Explicit missing production gates

An independent verifier service and its protected private-key storage are NOT delivered here. Real external API evidence validation, trusted deployment key ownership/rotation, branch protection, administrative Actions policies and verified merge authority must be independently approved. The existing operational registry is not migrated; A/B is BLOCKED and D-stage automation/merging stays disabled.