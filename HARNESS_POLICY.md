# Harness / Ouroboros governance v1

## Non-negotiable controls
- No secrets, private keys, paid API calls, or live trading.
- CI has read-only `contents: read` and does not push, approve, deploy, or merge.
- Draft PR first; each merge requires a fresh explicit user approval.
- No auto-merge or unattended trading.
- CI checkout action pinned to an immutable commit SHA.

## Verification scope
- Current implementation: tracked-file secret signature scan and regression tests.
- The scanner checks large files in chunks; unreadable, symlinked and binary files fail closed for review.
- The scan is not comprehensive: pattern-based checks may miss secrets; git history and untracked files are not scanned.
- Blocking gates PLANNED: boundaries, layers, secrets, security, structure, specification, dependencies, mutation.
- Advisory gates PLANNED: complexity, performance, AI anti-patterns.
- Ouroboros workflow PLANNED: interview -> seed -> TRD -> decompose -> run -> evaluate -> evolve, checkpoint and rollback.
- No claim of 35+ patterns, full MCP implementation, or trading profitability validation.

## Consumers
- [AURA-OS](https://github.com/js775315672-spec/AURA-OS)
- [SteadyTrade](https://github.com/js775315672-spec/SteadyTrade)
