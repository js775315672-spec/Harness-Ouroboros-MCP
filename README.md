# Harness-Ouroboros-MCP

<!-- oril-ofc-dashboard:start -->
## 개발 현황 대시보드 · OUROBOROS → FENRIR → CERBERUS

> **기록 시점: 2026-11-21 16:12 KST** · 아래 표는 검증 근거가 있는 **스냅샷**이며 자동 실시간 갱신 화면이 아닙니다. 신규 실행 확인: [공용 인계 원장 #347](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/issues/347) · [O Actions](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions) · [C Actions](https://github.com/js775315672-spec/Cerberus/actions).

**전체 판정: `BLOCKED / WAITING_FENRIR_REPORT_REPAIR` — Cerberus 독립 검증 `INCONCLUSIVE`. 자동 병합·배포 불가.**

| 단계 | 현재까지 확인된 성과 | 남은 차단 조건 | 근거 |
| --- | --- | --- | --- |
| **O · 개발 후보** | [Draft PR #346](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/pull/346) 고정 커밋 `083eb00e9efb91c8a951a551a91fcccfb6d2efcb`; 지식증류 입력 상한 방어 코드 | 전체 PR/실험 아티팩트 단일 SHA-256, 재현·승인 계약 분리. 커밋 SHA는 아티팩트 해시가 아님 | [PR #346](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/pull/346) |
| **F · 독립 비판** | 별도 Fenrir runner에서 Qwen2.5-Coder-1.5B-Instruct 호출·보고서 아티팩트 수신; 실행 및 출처 검증 경로 확인 | **원본 비판이 절단됨**. F-ID·심각도·확정/가설 구분·재현·PASS/FAIL 기준 누락. `FENRIR_VERIFIED=false` | [실행 #44875233515](https://github.com/js775315672-spec/Cerberus/actions/runs/44875233515) · [원본 감사](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/issues/347#issuecomment-7058820709) |
| **C · 독립 검증** | Fenrir 아티팩트 수신과 계약 처리의 실험적 경로 존재 | 보호된 별도 재현·미공개 평가 **미착수**; F 보고서 계약 통과 전 후보 PASS 금지 | [Cerberus 이슈 #2](https://github.com/js775315672-spec/Cerberus/issues/2) · [Draft PR #3](https://github.com/js775315672-spec/Cerberus/pull/3) |
| **통합·승인** | `cycle_id=ORIL-OFC-PR346-001`로 동일 후보 추적 | 공용 원자 lease/owner 미확인. 독립 승인·배포 없음 | [공용 이슈 #347](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/issues/347) |

### 현재 가장 큰 병목과 다음 작업

**P0: Fenrir 보고서 검증 계약 실패.** 독립 Fenrir 담당자는 현재 절단 원본을 부정 테스트로 보존하고, 실행 출처·동일 후보 SHA에 결속된 구조화 `FENRIR_REPORT`를 발행해야 합니다. 필수 F-ID/심각도/분류/재현/반례/판정 기준/실제 증거 URL 중 하나라도 없으면 차단합니다. **P1:** 공용 원자 잠금·담당자 확인. **P2:** Fenrir 검증 성공 이후에만 Cerberus의 격리 replay와 미공개 평가 시작.

### 이전보다 빨라졌나? · 검증 가능한 수치만

| 지표 | 측정/비교 | 결론 |
| --- | --- | --- |
| 이번 O→F→C 전체 주기 시간 | 미측정; 동일 난이도 완결 주기 n 부족 | **판단불가** |
| 모델 호출·독립 검증·운영 후속 시간 | 단계별 비교 가능 로그 미집계 | **판단불가** |
| 시간당 독립 검증 통과 개선 | 실후보 Cerberus PASS **0건 확인**; 분모(실제 총 작업시간) 미측정 | **산정 불가** |
| 최근 5~12개 **동종** 사이클 중앙값·증감률 | 동일 계약·유형·난이도 완료 표본 부족 | **산정 불가 (n 부족)** |
| 실패/재시도/회귀/롤백률 · 비용·대기시간 | 정규화된 동일 조건 시계열 미확보 | **미측정** |
| 미공개 평가 성능 / 모델 가중치 지능 향상 | 독립 holdout 미완료; 공개 문제 반복 결과는 일반화 증거 아님 | **미입증 / 판단불가** |
| **참고: 과거 공개 Qwen 실험** | [Actions #44853120822](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44853120822)에 30문제 중 25개 정답, 검산 종료까지 101초 기록 | **과거 1회 기록**, O→F→C 속도 기준선이나 모델 학습 증거가 아님 |

**읽는 법:** `CI 성공` ≠ `독립 후보 검증 PASS` ≠ `모델 가중치/지능 향상`. 새 기록은 [인계 이슈 #347](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/issues/347)과 [검증 원장](docs/evolution/ledger.jsonl), [비교 지표](docs/metrics/trends.json)를 원본 출처와 함께 감사하고 README 스냅샷을 별도 PR로 갱신해야 합니다. 이 README는 자동 병합·실시간 갱신을 주장하지 않습니다.
<!-- oril-ofc-dashboard:end -->

Hydra는 승인된 작업을 GitHub Actions에서 실행하고, ORIL은 후보 변경의 재현성·독립 검증·승인 이력을 추적한다. 과거 실험 기준선은 [8fbecb5](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/tree/8fbecb5e813b653213d6c8d95ce7151868779512)이다.

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
과거 공개 검산 [44853120822-3](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44853120822) · 코드 `e8fa72cc4caecaf5afab952af5d5214baa9c2614` · 공개 오답 5/30 · 소요 101초. 비공개 개선 미입증. 동일 조건 2건, 소요 시간 변화 판단 불가.

[자동 집계](docs/metrics/trends.json) · [로드맵](docs/roadmap.md)
