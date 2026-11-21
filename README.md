# Harness-Ouroboros-MCP

Hydra는 승인된 작업을 GitHub Actions에서 실행하고, ORIL은 후보 변경의 재현성·독립 검증·승인 이력을 추적한다. 현재 기준선은 [main 8fbecb5](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/tree/8fbecb5e813b653213d6c8d95ce7151868779512)이다.

## 독립 개체 성장 연구 — Ouroboros

Ouroboros는 Fenrir/Cerberus의 지휘 시스템이 아니라 자체 문제 발굴·코드 생성·최적화·검증을 소유하는 독립적인 탐색·개발형 개체다. 외부 협업은 선택적이며, 신규 개선 성공은 별도 비공개·반복 검증 없이는 주장하지 않는다.

| 항목 | 현재 연구 기준 (2026-11-21) |
| --- | --- |
| 상태 | 연구 설계 작성 (Draft 브랜치, 운영 자율실행 아님) |
| 고유 성장 목표 | 독립 문제 해결·개발 효율·일반화 성능 |
| 성능 개선 | 미입증 (신규 독립 평가 필요) |
| 다음 실험 | 기준선 고정 후 문서 컨텍스트 A/B/C 비교 |

[독립 정체성](docs/evolution/identity.md) · [기계 판독 상태](docs/evolution/independent-state.json) · [README 기억 실험 설계](docs/evolution/readme-memory-study.md) · [독립 기억 점검 스크립트](scripts/evolution_context.py)

기존 `python scripts/oril_docs.py context`는 계속 유효하다. 추가 연구용 읽기 전용 검사: `python scripts/evolution_context.py check` / `python scripts/evolution_context.py context`.

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


### 독립 자율진화 상세 개발 명세

- [독립 자율개선 루프 상세 계약 v2.0](docs/evolution/standalone-autonomy-spec-v2.md) — 내부 12개 모듈, 상태 기계, 증거 계약, 구현 단계
- [ouroboros 전용 구현 계약](docs/evolution/ouroboros-implementation-spec-v1.md) — 독자 목표, 평가 및 자체 개선 방법
- [23개 수락 테스트 계획](docs/evolution/acceptance-test-plan-v1.md) — 완료/차단 판정 조건
- [예약 자동개발 지속 프롬프트](docs/evolution/AUTOMATION_CONTINUITY_PROMPT.md) — 매 회차 이전 checkpoint 복구·중복 방지·한 가지 실제 개선

**현재 단계:** 개발 상세 설계 및 읽기 전용 검사 CI. 실제 무인 자기개선 루프와 숨겨진 평가 성과는 미검증이다.

<!-- oril-docs:generated -->
최근 공개 검산 [44853120822-3](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44853120822) · 코드 `e8fa72cc4caecaf5afab952af5d5214baa9c2614` · 공개 오답 5/30 · 소요 101초. 비공개 개선 미입증. 동일 조건 2건, 소요 시간 변화 판단 불가.

[자동 집계](docs/metrics/trends.json) · [로드맵](docs/roadmap.md)
