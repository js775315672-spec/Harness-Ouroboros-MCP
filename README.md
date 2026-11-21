# Harness-Ouroboros-MCP

## 독립 운영 계약 v3.1

Ouroboros는 코드 후보를 생성하고 개발 방법·실행 효율·신규 과제 일반화를 개선한다. 동일 조건의 신규 과제 합격률, 회귀율, 개발 시간을 측정한다.

[운영 명세와 원장 사용법](docs/ofc-v3.1.md)

현재 기준 커밋은 실행 시 `git ls-remote origin refs/heads/main`으로 조회한다.

## 설치와 실행

Git, Python 3 및 인증된 GitHub CLI(저장소 Actions 읽기 권한)를 준비한다. 저장소 루트에서 아래 명령은 최근 Hydra 실행을 조회하고 다음 검토 제안을 로컬 JSON으로 저장한다.

```sh
git clone https://github.com/js775315672-spec/Harness-Ouroboros-MCP.git
cd Harness-Ouroboros-MCP
python scripts/p3l_hydra_next_task.py hydra-next-task.json
```

[아키텍처와 W01~W08](docs/architecture.md) · [현재 상태](docs/status/current.md) · [검증 원장](docs/evolution/ledger.jsonl) · [검증 계약](docs/evolution/README.md)

## HISTORICAL · 공개 실험

main의 P0 검산은 과거 Hydra 승인 9건과 공개 워크로드 해시 3건을 확인했다. Cycle 01은 독립 러너의 기준선 증거를 기다린다. [검산 실행](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44643574019) · [실행 전 점검](docs/evolution/cycle-01-dispatch-preflight.json)

[Draft PR #330](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/pull/330)의 Qwen2.5-0.5B 공개 추론은 가중치를 동결했다. 세 번째 주기에서 공개 30그룹 정답이 11→25개였고 추론 시작부터 공개 검산 종료까지 101초였다. 별도 BERT Tiny LoRA 실험은 공개 12건에서 6→8건, 신규 회귀 3건을 기록했다. 모델 자체의 지능 향상은 **미입증**, 개발 속도 변화는 **미측정**이다. [Qwen 실행](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44853120822) · [코드·측정 조건과 LoRA 출처](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/blob/bfa89dcc28287986e36e5d4f33693e53a8394902/docs/oril/report.ko.md)

<!-- OFC-DASHBOARD-BEGIN -->
## OFC independent agent dashboard (P0)

| Metric | Evidence-based status |
| --- | --- |
| Real model execution | UNKNOWN |
| Independent improvement | UNKNOWN |
| Improvement throughput | NOT_MEASURED |
| Comparable speed trend | NOT_MEASURED |
| Generalization | NOT_VERIFIED |
| Most recent blocker | P1 real model run + protected independent evaluation not yet connected |

Registry and contract unit tests are **not** model improvements.
<!-- OFC-DASHBOARD-END -->

<!-- oril-docs:generated -->
최근 공개 검산 [44853120822-3](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44853120822) · 코드 `e8fa72cc4caecaf5afab952af5d5214baa9c2614` · 공개 오답 5/30 · 소요 101초. 비공개 개선 미입증. 동일 조건 2건, 소요 시간 변화 판단 불가.

[자동 집계](docs/metrics/trends.json) · [로드맵](docs/roadmap.md)
