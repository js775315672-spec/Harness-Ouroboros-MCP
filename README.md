# Harness-Ouroboros-MCP

Hydra는 승인된 작업을 GitHub Actions에서 실행하고, ORIL은 후보 변경의 재현성·독립 검증·승인 이력을 추적한다. 현재 기준선은 [main 8fbecb5](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/tree/8fbecb5e813b653213d6c8d95ce7151868779512)이다.

## 설치와 실행

Git, Python 3 및 인증된 GitHub CLI(저장소 Actions 읽기 권한)를 준비한다. 저장소 루트에서 아래 명령은 최근 Hydra 실행을 조회하고 다음 검토 제안을 로컬 JSON으로 저장한다.

```sh
git clone https://github.com/js775315672-spec/Harness-Ouroboros-MCP.git
cd Harness-Ouroboros-MCP
python scripts/p3l_hydra_next_task.py hydra-next-task.json
```

[아키텍처와 W01~W08](docs/architecture.md) · [현재 상태](docs/status/current.md) · [검증 원장](docs/evolution/ledger.jsonl) · [검증 계약](docs/evolution/README.md)

## 개발 및 검증 현황

main의 P0 검산은 과거 Hydra 승인 9건과 공개 워크로드 해시 3건을 확인했다. Cycle 01은 독립 러너의 기준선 증거를 기다린다. [검산 실행](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44643574019) · [실행 전 점검](docs/evolution/cycle-01-dispatch-preflight.json)

[Draft PR #330](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/pull/330)의 Qwen2.5-0.5B 공개 추론은 가중치를 동결했다. 세 번째 주기에서 공개 30그룹 정답이 11→25개였고 추론 시작부터 공개 검산 종료까지 101초였다. 별도 BERT Tiny LoRA 실험은 공개 12건에서 6→8건, 신규 회귀 3건을 기록했다. 모델 자체의 지능 향상은 **미입증**, 개발 속도 변화는 **미측정**이다. [Qwen 실행](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44853120822) · [코드·측정 조건과 LoRA 출처](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/blob/bfa89dcc28287986e36e5d4f33693e53a8394902/docs/oril/report.ko.md)

<!-- oril-docs:generated -->
최근 공개 검산 [44853120822-3](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44853120822) · 코드 `e8fa72cc4caecaf5afab952af5d5214baa9c2614` · 공개 오답 5/30 · 소요 101초. 비공개 개선 미입증. 동일 조건 2건, 소요 시간 변화 판단 불가.

[자동 집계](docs/metrics/trends.json) · [로드맵](docs/roadmap.md)


## OFC DEV 12-cycle expansion (unverified)

- Scope: isolated DEV branch only; no OPS registry, main merge, holdout or protected edits.
- Runner: `agent/dev_cycle_12.py` (maximum 12 sequential candidate/verifier command pairs, wall-clock budget, atomic local checkpoint, stable operation keys).
- Safety: ambiguous pending blocks replay; failure stops the track; independent command exit 0 is **not** evidence of model intelligence improvement.
- Tests: `tests/test_dev_cycle_12.py`; Windows/Linux workflow `.github/workflows/ofc-dev-12-cycle.yml`.
- Evidence: this Draft PR and its head SHA / Actions checks. Current CI outcome: UNKNOWN until completed. Real Qwen runs: NOT_RUN. Protected independent evaluation: NOT_RUN. OPS cycle IDs: UNKNOWN.
- Limitations: no actual Qwen orchestration or artifact-backed independent evaluation; monetary cost cannot be enforced by this runner, so use only approved zero-cost commands. The runner must not be used for external side effects until operation reconciliation and source provenance gates are verified.
- Next single action: validate Windows/Linux regression and independently audit pending/restart behavior before enabling any real candidate commands.


## OFC D-plan: adaptive 120-cycle DEV planner (verification pending)

- A gate: 12-cycle Linux/Windows safety CI passed on the pre-expansion PR head. This is **not** proof of independent model improvement.
- B DEV files: `agent/adaptive_dev_120.py`, `tests/test_adaptive_dev_120.py`, `.github/workflows/ofc-dev-120-cycle.yml`. Maximum 10 batches × 12 cycles, stable keys, fail-closed pending, bounded budget counters, and independent-evaluation receipt fields.
- Status: planner committed to this independent Draft PR; new 120-cycle Windows/Linux CI must pass before promotion. The code is a **planner/receipt ledger**, not an external model executor or trusted evaluator. It does not automatically enforce third-party spending or cryptographically authenticate evaluator evidence.
- C gate: real approved free Qwen calls NOT_RUN; model hash, candidate SHA, evaluator SHA, actual run ID, artifact digest and independent holdout evaluation remain UNKNOWN/NOT_RUN. No OPS lease acquired; no main/protected/registry writes.
- Next single action: verify 120-cycle CI and harden evidence authentication and real-cost metering before any Qwen execution.


## OFC A-gate 120-cycle CI evidence — 2026-11-23

- Verification target before this documentation commit: `ee1b15c850047adcd4363addd43351754ad3e740` (Draft PR, DEV-only).
- Workflow: `OFC DEV 120-cycle planner safety`; run: https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/45047644895.
- Linux: **QUEUED**; Windows: **QUEUED** at inspection time. Do not treat queued as passed or failed.
- A-gate: **BLOCKED pending both operating systems**.
- Evidence limitations: test suite checks deterministic planner bounds, pending replay block, independent-agent ledger separation, fail-closed receipts and budget counters. It does not prove real Qwen inference, authenticated evaluation artifacts, real spend enforcement, or intelligence gains.
- New README commit changes PR head: verify the new head separately before final gate promotion.
- OPS registry / PROTECTED / main: unchanged. No automatic merge.
