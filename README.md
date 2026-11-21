# Harness-Ouroboros-MCP · Autonomous Improvement Lab

> **현재 O→F→C 판정: INCONCLUSIVE / BLOCKED**  
> **FENRIR_VERIFIED=false · CERBERUS_REPLAY=NOT_STARTED · AUTO_MERGE=DISABLED**  
> Hydra는 승인된 작업을 GitHub Actions에서 실행하고, ORIL은 후보 변경의 재현성·독립 검증·승인 이력을 추적한다. **CI 성공은 모델 지능 향상이나 독립 검증 완료를 의미하지 않는다.**

## 통합 개발 대시보드

| 단계 | 실제 확인 상태 | 증거 / 현재 병목 |
|---|---|---|
| **O · OUROBOROS** 후보 | **PARTIAL** — PR #346 소스 커밋 고정, 전체 후보 아티팩트 해시 미확인 | [O Draft PR #346](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/pull/346) · [공용 원장 #347](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/issues/347) |
| **F · FENRIR** 독립 비판 | **DEMO PASS / ACTUAL O REVIEW BLOCKED** — 공개 Qwen 데모 실행 확인, 실제 O 후보에 대한 인증 보고서 미확보 | [독립 F 저장소](https://github.com/js775315672-spec/Fenrir-Agent) · [Qwen 실행 #44895880606](https://github.com/js775315672-spec/Fenrir-Agent/actions/runs/44895880606) |
| **C · CERBERUS** 독립 검증 | **BLOCKED** — 보고서 계약·출처 독립 인증 및 보호된 재현 검증 미완료 | [C 검증 이슈 #2](https://github.com/js775315672-spec/Cerberus/issues/2) · [README 개선 Draft PR #5](https://github.com/js775315672-spec/Cerberus/pull/5) |
| **최종 승인 / 병합** | **NOT APPROVED** | 보호된 검증 완료와 사용자 승인 필요 |

**추적 사이클:** `ORIL-OFC-PR346-001`  
**공유 작업키:** `ORIL-OFC-PR346-001:F_REPORT_CONTRACT`  
**O 후보 참조 커밋:** `083eb00e9efb91c8a951a551a91fcccfb6d2efcb` (공용 원장 기준; 최신 HEAD와 동일함을 보증하지 않음)  
**후보 단일 소스 파일 SHA-256:** `1c77af88c66ffa1a3abbdb7176d328d9d3803687138c43cb24cd749b2e4d7969` — **전체 후보 아티팩트 해시가 아님**.

### 지금 막힌 이유와 다음 인계

1. **O:** 실제 전체 후보 아티팩트의 원본 bytes, SHA-256, 테스트 계약 SHA, 재현 로그와 실행 소유자/원자 lease를 확정한다.
2. **F:** 별도 FENRIR 러너에서 **그 동일한 후보**를 심사하고 원본 보고서, 결함 ID·심각도·재현·반증 조건·증거 URL, 실행 ID와 provenance를 발행한다.
3. **C:** F 보고서의 서명·발행자·후보 해시·중복 재생 방지를 독립 확인한 뒤에만 보호된 별도 환경에서 재현·회귀 검증한다.
4. **승인:** 검증 완료와 사용자 승인 전에는 main 병합·배포·보호된 holdout 공개를 금지한다.

**Fail closed:** O→F→C 단계의 링크가 있다는 사실, 자체 선언된 actor ID, 데모 추론 PASS, CI PASS만으로 다음 단계에 진입하지 않는다.

## 개선 이력 · 실제 성능과 한계

| 기록 | 측정/결과 | 해석 |
|---|---|---|
| [Hydra 과거 승인 기록](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44643574019) | 과거 승인 9건, 공개 워크로드 해시 3건 P0 검산 | 현재 O→F→C 사이클 독립 합격 건수와 구분 |
| [Qwen 공개 추론 PR #330](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/pull/330) | 공개 30그룹에서 세 번째 주기 11→25, 전체 공개 검산 101초 | 가중치 동결; 비공개 일반화·지능 향상 미입증 |
| [BERT Tiny LoRA 별도 실험](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/blob/bfa89dcc28287986e36e5d4f33693e53a8394902/docs/oril/report.ko.md) | 공개 12건에서 6→8, 신규 회귀 3건 | 별도 모델/조건의 결과이며 Qwen과 혼합 비교 금지 |
| [FENRIR 공개 데모](https://github.com/js775315672-spec/Fenrir-Agent/actions/runs/44895880606) | 실제 Qwen 데모 추론 및 보고서 업로드 성공 | O PR #346에 대한 정식 심사 아님 |
| [공용 O 인계 기록](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/issues/347#issuecomment-7061485286) · [C 수신 대기 기록](https://github.com/js775315672-spec/Cerberus/issues/2#issuecomment-7061485628) | 데모 증거 링크 인계 | 독립 인증·보호된 검증 미완료 |

### 속도·품질 추적

| 동종 검증 사이클 비교 항목 | 현재 판정 |
|---|---|
| 완료된 인증 O→F→C 동종 사이클 | `n=0` (현재 추적 계약) |
| 최근 5~12회 중앙값: 모델 / 독립 검증 / 운영 후속 / 전체 | 비교 자료 부족 |
| 시간당 독립 합격 개선 건수 | 산정 불가 |
| 실패·재시도·회귀·롤백률 | 동종 자료 부족 |
| 비공개 품질·일반화 개선 | 미측정 |
| 이전 대비 개발 속도 향상 | **판단 불가** |

공개 검산 101초를 모델 추론 시간이나 O→F→C 전체 주기 시간으로 해석하지 않는다. 역사적 Hydra 기록과 현재 3개체 검증은 서로 다른 표본이다.

## 최근 공개 검산 · 자동 생성 구간

아래 주석은 기존 문서 자동 생성기가 사용하는 경계로 보존한다. **이 구간을 수동으로 삭제하거나 생성기 출력과 혼동하지 않는다.**

<!-- oril-docs:generated -->
최근 공개 검산 [44853120822-3](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/44853120822) · 코드 `e8fa72cc4caecaf5afab952af5d5214baa9c2614` · 공개 오답 5/30 · 소요 101초. 비공개 개선 미입증. 동일 조건 2건, 소요 시간 변화 판단 불가.

[자동 집계](docs/metrics/trends.json) · [로드맵](docs/roadmap.md)

## 설치와 실행

Git, Python 3 및 인증된 GitHub CLI(저장소 Actions 읽기 권한)를 준비한다. 다음 명령은 최근 Hydra 실행을 조회하고 다음 검토 제안을 로컬 JSON으로 저장한다.

```sh
git clone https://github.com/js775315672-spec/Harness-Ouroboros-MCP.git
cd Harness-Ouroboros-MCP
python scripts/p3l_hydra_next_task.py hydra-next-task.json
```

## 구조와 검증 원본

- [아키텍처 · W01~W08](docs/architecture.md)
- [현재 상태](docs/status/current.md)
- [검증 원장](docs/evolution/ledger.jsonl)
- [검증 계약](docs/evolution/README.md)
- [Cycle 01 실행 전 점검](docs/evolution/cycle-01-dispatch-preflight.json)
- [O→F→C 공용 원장 및 차단 이력](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/issues/347)
- [FENRIR 대시보드](https://github.com/js775315672-spec/Fenrir-Agent/blob/feat/independent-qwen-review-v0-1/README.md)
- [CERBERUS 대시보드 제안](https://github.com/js775315672-spec/Cerberus/blob/docs/evidence-dashboard-v1/README.md)

**운영 규칙:** README는 검증 가능한 현황의 스냅샷이다. 실제 원본은 Actions, 아티팩트, SHA와 공용 원장에 남긴다. 자동 갱신·원자 잠금·인증 판정은 README 작성만으로 구현되지 않는다.
