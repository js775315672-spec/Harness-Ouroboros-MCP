# Ouroboros 독자 진화 엔진 구현 세부 계약 v1.0
**상태:** PROPOSED — 미구현 설계 항목은 반드시 증명 후 완료 판정.

## A. 정체성/생존 경계
소프트웨어 결함·성능 병목·도구 사용 전략에서 새 문제를 직접 찾고, 코드/프롬프트/워크플로 후보를 격리 생성해 신규 과제 일반화와 개발 효율을 개선한다
이 개체의 자체 과제 입력은 `로컬 이슈·실패 기록·테스트 리포트·과거 채택 후보·연구 출처`, 외부 협업/타 저장소 인계는 OPTIONAL이다.

## B. 자체 목표 생성
- 새 일정 실행 시 `GET own backlog → inspect own prior failures → select one falsifiable goal`.
- 위험점수: `예상 영향도 × 재현 가능성 ÷ 예상 비용; 동일 실패/중복 후보 감점`. 점수 산정 파라미터는 첫 테스트 전에 동결.
- 결과: `goal.json`에 `agent_id, goal_id, hypothesis, rationale, reproducible_input, estimated_cost, stop_condition, success_metric` 포함.
- 중복 발견 기준: `goal_id + base_sha + evaluation_suite_sha`. 같으면 새 작업 발급 금지.
- 사용하지 못하는 외부 연결/로그는 `unavailable`로 기록하되 추측하지 않는다.

## C. 실험 기획/실행
- 실험 근거: 고정된 결함 12개와 미공개 신규 결함: 코드-only/A: README/B: 검증 메모리/C 비교; 동일 난도·모델·실행기·평가기 고정.
- 격리 규칙: 단일 후보 변경, 기존 main 보호, 임시 브랜치 사용, 모델 호출 수·CPU·토큰·경과시간 예산 사전 승인.
- 반증: 후보가 실패하는 최소 반례를 포함하고 실패 이유를 분류한다.
- 통과 선언은 원본 stdout/stderr/exit code/commit/환경/아티팩트 SHA를 갖춘 경우에만 허용.
- 기존 작업이 unfinished면 실험 새로 만들기보다 복구·중복 제거가 먼저.

## D. 평가 방식
| 영역 | 기준 |
|---|---|
| 고유 지표 | 독립 검증 통과율, 보호 평가 점수, 작업 E2E 시간, 신규 결함률, 토큰·CPU 비용 |
| 공개 평가 | 연구/디버깅 용도, 성과 최종 판정 아님 |
| 보호 신규 평가 | 평가 입력과 정답 유출 금지, 평가기 해시·판정 요약 기록 |
| 반복 A/B | 같은 조건, run마다 원본 결과, 실패분모 포함 |
| 정지/거부 | 공개 과제 과적합, 평가기 정보 노출, 성능 측정 누락, 장시간 모델 무한 재시도 |
| 최종 판정 | 보호 신규 과제에서 회귀 0건, 작업당 E2E 및 토큰 절감이 반복 확인되어야 CONFIRMED_GAIN |

## E. 기억/증류
- 사실 목록(verified), 반복 실패(confirmed), 실험 가설(proposed), 외부 주장(untrusted) 4계층 분리.
- `memory/lessons.jsonl` 제안 구조: `lesson_id, cycle_id, issue_signature, observed_failure, evidence_sha, trusted_grade, correction, applicability, next_experiment`.
- 새 교훈은 이전 교훈을 덮어쓰지 않고 수정 이벤트로 연결.
- 컨텍스트에는 검증 가능한 관련 교훈 최대 5개(예시 기본값)를 검색하고 참조 원문 링크와 토큰 수를 출력.
- 실패를 반복하는 경우 비용 절약보다 정확한 원인 분류를 우선한다.

## F. 최소 첫 백로그
1. P0 독립 목표 selector에 3개의 로컬 테스트 샘플 작성.
2. P1 라이브 실행 없이 contract/schema 검사 및 중복 루프 차단.
3. P2 동일 `agent_id` 경계 회귀 테스트, 외부 입력 거부/검역.
4. P3 1개 건조 실행(dry-run)에서 계획→평가→원장→README 투영 완료.
5. P4 승인된 모델 예산에서 실제 1개 자기선택 과제 실행.
6. P5 교차 의존성 없이 3개 실제 연속 사이클을 완수한 로그 감사.
7. P6 README A/B/C 실험 결과를 공유하되 가설과 입증을 분리.

## G. 독자성 검증
- Ouroboros와 Fenrir, Cerberus를 모두 차단해도 로컬 task 1개는 선정·계획·검수·기록이 가능해야 한다.
- 타 개체 보고서의 'success' 문자열만으로 local VERIFIED로 전이되면 실패.
- 다른 개체가 차단되었을 때 교차협업은 WAITING_EXTERNAL이 가능하나 자체 과제는 계속 선택 가능.
- 개체 자체의 평가기가 변경되면 이전 결과 비교를 금지하거나 새 기준선으로 재시작.
- 이전 실험 SHA와 기록의 동일성을 independent self-replay로 재검증.

## H. 알려진 비구현 영역
현재 통과한 것은 Draft PR의 read-only context CI이다. 자율 scheduler, model invocation, 원자 lease, 자기개선/평가 loop, 숨겨진 평가, 오토메이션 연계는 아직 이 문서만으로 검증되지 않는다.
