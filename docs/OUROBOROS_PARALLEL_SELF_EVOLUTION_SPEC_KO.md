# Ouroboros Parallel Self-Evolution Engine — Implementation Specification v1

Status: **design + read-only eight-lane CI smoke pilot**; general-purpose autonomous coding, remote experiment branches, CI-attested promotion, and recurring execution are **NOT implemented** by this specification alone.

## 1. Mission and exact target

The Ouroboros/Harness/MCP repository develops **itself**, not AURA-OS or SteadyTrade. Eight independent development agents receive the **same high-level goal**, each with a deliberately different architecture hypothesis. Every proposal begins at the same pinned base commit, runs in its own Git branch/worktree and independent GitHub Actions runner, and is judged against the same frozen evaluation contract. The system may prepare Draft PR proposals, but must not merge them without the owner's separate, explicit approval.

Repository: https://github.com/js775315672-spec/Harness-Ouroboros-MCP

Baseline before this design: an existing Qwen 7B bounded two-task worker, isolated AST/Docker checks, and checkpoint verification exist on the development PR chain. This is evidence for **two narrowly scoped tasks**, not an eight-agent generalized autonomous code author.

## 2. Operating cadence: hourly outside, five minutes inside

- **Hour H, minute 00**: read previous completed artifacts; pin source SHA, goal SHA and evaluation/test-set SHA; select **at most eight** approved candidate tasks. Use a durable checkpoint; if the prior round is incomplete, resume or block rather than duplicating it.
- **Minute 00–50**: each selected agent gets **at most 3,000 seconds** of coding/repair budget. Use independent runners/worktrees; no shared writable checkout. An internal checkpoint or heartbeat may be attempted every **five minutes**, but must not be treated as an exact-time guarantee.
- **Minute 50–55**: independent Harness, security, regression, reproducibility and performance checks; record timeouts and missing metrics as failures/unknown, never passes.
- **Minute 55–60**: publish bounded artifacts, checkpoint the promotion queue, produce a ranking and up to eight next-step contracts. The **next** hour reviews the completed epoch; clock delays do not grant extra budget.
- The **GitHub workflow timeout** should be greater than the **3,000-second worker cap** to allow setup and final verification. All limits are enforced independently. Run start latency is not controllable.
- GitHub Actions schedules are only effective when the workflow is on the default branch, and can run late or be dropped. Initial delivery is **workflow_dispatch + PR validation only**. Do not enable a recurring self-writing cron before a separate approval and security review.

## 3. Eight alternative architecture lanes — one goal

All eight agents solve: “Build a safe, bounded, recoverable, auditable, end-to-end autonomous code-change cycle for this repository.” They are **competing architecture alternatives**, not permission to touch arbitrary subsystems.

| Lane | Alternative approach | Main design distinction |
| --- | --- | --- |
| 01 | Centralized controller | Single deterministic orchestration state machine |
| 02 | Event-sourced controller | Append-only events and replay-based restoration |
| 03 | Dependency DAG | Typed tasks, dependencies, and verified edge transitions |
| 04 | Message/actor orchestration | Bounded mailboxes and explicit actor handoffs |
| 05 | Immutable artifact pipeline | Content-addressed input/output stage chain |
| 06 | Git-native checkpoints | Immutable commits/refs plus external run attestations |
| 07 | Planner/executor/verifier separation | Three isolated trust domains and contracts |
| 08 | Beam-search portfolio | Limited candidate frontier with novelty/diversity checks |

Exact machine-readable initial hypotheses and safe contracts: **configs/self-evolution-8lanes.json**.

## 4. Recursive branching without exponential execution

- Generation 0: eight alternatives (8 candidates).
- Generation 1: **each independently verified parent may propose up to eight children**. This permits a **theoretical maximum of 64 proposed children**, not 64 simultaneously running workers.
- Generation 2: those children may propose further descendants; **8^N is a proposal space, not an execution entitlement**.
- Only a *verified* parent may spawn children. Failed, timed-out, unverified or forged candidates spawn zero.
- Keep **max_active_workers = 8**; pending candidate growth is capped at **64 per epoch**, and the scheduler selects no more than eight per subsequent hour using frozen metrics plus diversity controls. Others are rejected/archived, not silently executed.
- Preserve at least one architecture-diverse contender when verified evidence permits; don't optimize solely for code length or PR count. No automatic merging, no passing based on repeated identical tests, and no artificial “successful evolution” counters.
- Bound total epochs, inference calls, retries, disk/artifact sizes, per-run wall time and concurrency. Stop when budgets are exhausted or no improvement over the frozen baseline can be verified.

## 5. Isolation and safety trust boundary

1. **Pinned base**: each job starts from the same source commit and immutable contract version. Branch name pattern: exp/ouroboros/<run-id>/<lane-id>/<generation>. A worktree branch is **local-only** unless a later authorized publishing step explicitly pushes a reviewed candidate. A local branch alone is not a GitHub remote branch.
2. **Untrusted model**: local CPU GGUF/llama.cpp or an explicitly approved free, local inference adapter only. No external paid APIs, account secrets, personal access tokens, exchange keys or inherited credential environment. Model output is *data* until AST/diff/path and test gates pass.
3. **Disposable execution**: test untrusted patches only in an independently configured no-network, non-root, read-only or tightly sandboxed runtime, with CPU/memory/process/time limits. No direct shell commands generated by the model. Prevent workspace escape, symlink tricks and forbidden paths.
4. **Protected control plane**: model-generated edits to .github/workflows, harness-policy.json, Harness gate code, approval code, action permissions, and the test oracle cannot be allowed to relax the gate that judges themselves. Such proposals require separate maintainer review against a frozen baseline and must never be self-accepted.
5. **No write permission for the worker**: GitHub Actions job has contents: read, checkout persist-credentials: false. The initial pilot does **not** push code, create remote branches, create PRs or call models. A future separate publisher may create **Draft PRs only**, under explicitly approved permissions; publishing is not merging. It must never approve/merge its own proposals.
6. **No real-world side effects**: no trading, deployments, privileged Docker, service secrets, or repository administration.

## 6. Checkpoint & idempotency contract

Minimum fields: schema version, repo, source SHA, goal SHA, frozen oracle/test digest, epoch, lane ID, parent candidate hash, generation, attempts, elapsed/CPU budgets, prompt/model version and license provenance, patch SHA, current phase, trial results, artifact URI, unique run/attempt ID, and human_approval_required=true.

- Write JSON atomically with fsync and generation compare-and-swap in each workspace.
- Publish digest-checked artifacts between jobs; SHA-256 detects accidental alteration but is **not a remote authenticity signature**.
- Resume only when the frozen source SHA, task ID, oracle SHA and checkpoint lineage match; otherwise block.
- Never count repeated CI verification on an unchanged commit as newly authored code.
- Execution retries must be bounded and idempotent. Missing or ambiguous CI evidence is failure-to-attest.

## 7. Frozen cross-lane evaluation

Every candidate must face the **same independent tests**, measured on the same CPU runner type and frozen baseline commit. Passing alone is necessary, not proof of architectural superiority.

Blocking gates: existing Harness eight blocking checks, secret scanner, AST/scoped diff/path policy, actual source change, existing regression suite, adversarial negative tests, no regressions, source-specific test assertions, external CI attestation tied to the exact head SHA, and reproducible clean rerun.

Measured/compared: success rate by *new* independently tested coding task, test coverage/change, reproducibility, wall-clock and CPU time, peak RSS, artifact size, number of model calls, distinct code-change evidence, code complexity, performance deviation versus baseline, and rollback ability.

Rank **only attested candidates**. A candidate without performance data is **unknown**, not fastest. Rank is lexicographic: all mandatory gates pass → independently repeated test pass → no regressions → resource efficiency → architectural diversity. Report Pareto tradeoffs where metrics conflict. False evidence, leaked credentials, forbidden-path edits or post-budget work are blocked regardless of score.

Each lane publishes raw log digests, JSON metrics, trial patch/diff digest, failure categories and a readable report. The orchestrator publishes a ranked report and never labels a read-only smoke test as AI-authored development.

## 8. Draft PR & human approval

- Phase 1 produces **review-only Draft PRs** for design and test infrastructure, based on the latest development branch, not main.
- Phase 2 stages reviewed model patches in disposable workspaces and emits patch artifacts. Candidate source commits and CI attestations must be independently confirmed before creating any candidate Draft PR.
- Each candidate Draft PR must contain: parent/base SHA, exact task, alternative architecture, model provenance/license, diff, test IDs, per-gate result, timing and memory, comparison baseline, checkpoint/artifact links, known limits, and **manual approval required**.
- A failed or unverified candidate **cannot** become an implementation PR or a parent of further coding branches.
- Never auto-merge, auto-approve, alter required review protections or treat Draft PR creation as merge consent.

## 9. Implementation phases and verifiable exits

**P0 — self-development contract + eight-runner smoke (this PR).** Store this spec, the eight pinned task contracts, and a workflow that creates eight independent **local** Git worktree branches in a GitHub Actions matrix (max-parallel 8), runs the same baseline Harness/regression checks, uploads eight read-only reports and aggregates completeness. **No model calls or source edits.** Exit: eight distinct lane IDs, separate workspace branches, shared source SHA and oracle, valid evidence reports; no false coding claims.

**P1 — model-authoring adapter.** Generalize the existing narrowly scoped bounded-Qwen worker into a per-lane, tested task-contract executor. Offline fake-model negative tests first. Exit: eight genuinely distinct model requests, inspected outputs, no privileged execution, independent patch replay with security tests. Resource-failure remains reported failure, not success.

**P2 — verified generation selection.** Create immutable candidate evidence, independently attest CI, score and select parents; propose up to eight children per accepted parent, enqueue at most 64, dispatch at most eight. Exit: forked lineage and wrong-commit/forged-evidence/replay/duplicate tests all block.

**P3 — hourly bounded operation.** After security approval and main-branch availability, enable one-hour scheduler with 50-minute capped work and five-minute checkpoint events, stop/resume semantics, budget kill switch. Exit: at least two epochs with distinct new model outputs, exact source diff verification, independent CI attestations and successful crash recovery. Continuous coding is **not demonstrated** until this exit is met.

**P4 — Draft PR publisher and ChatGPT reviewer.** Separate publisher under explicitly approved scoped permissions, never self-merge; hourly ChatGPT automation reviews artifacts and proposes eight new directions if available. Exit: created Draft PR evidence, permissions audit, manual acceptance gate, and no write action when permissions are unavailable.

## 10. Absolute acceptance criteria

- Same repo self-development scope, eight distinct independent architectures, common frozen baseline/test set.
- Maximum 8 simultaneous runners, hourly generation, 50-minute worker wall-clock cap, five-minute checkpoint *attempts*.
- Verified-only 8-way spawning, at most 64 pending child proposals per epoch, bounded cost/resources.
- Secret-free and paid-API-free; no agent-controlled merge, approvals, deployment or protected-gate weakening.
- Clear **not-tested / smoke-only / attested model patch / accepted by human** status distinctions.
- On any unknown evidence: **BLOCK / request human review**, not pass.

## 11. Current user-visible success definition

This initial PR is complete only if the read-only eight-lane workflow and its evidence pass actual CI. Even then, it **does not mean** the 50-minute general self-coding loop works. The owner must review subsequent phases and give separate approval before enabling recurrent runs, any new GitHub write permission, or a candidate merge.
