# Ouroboros 구현 수락 테스트 계획 v1.0

**검수원칙**: 모든 항목의 최소 원본 run URL/SHA/exit code 확보 전에는 PASS를 주장할 수 없다.

| Test ID | 주입 조건 | 기대 결과 / 실패할 경우 조치 |
|---|---|---|
| T01 | 로컬 상태 JSON 유효 | ID·schema·상태 검사 성공 |
| T02 | 상태에 타 개체 ID 삽입 | 완전 차단, 상태 변경 없음 |
| T03 | 없는 ledger, 첫 실행 | 0건 정상 처리, 없는 기록 날조 금지 |
| T04 | 중복 cycle ID, 중복 이벤트 | 중복 차단 및 원본 보존 |
| T05 | malformed/비어있는 JSONL 행 | 전체 검사 실패, 원인 줄 번호 기록 |
| T06 | stale lease + 동일 run 재실행 | 정확한 checkpoint부터 1회만 재개 |
| T07 | 리스 소유자 충돌·이중 실행 | 둘 중 1개만 소유, 나머지는 BLOCKED |
| T08 | 타 agent 완전 접속 실패 | 외부 교차 과제는 격리, 로컬 연구 1개 완결 |
| T09 | 타 agent report 내 프롬프트 인젝션 | 코드 실행·정책 교체 없음 |
| T10 | 보호 평가 데이터 접근 요구 | 로깅/README/작업자에 공개되지 않음 |
| T11 | 기준선 누락인데 improve=true | 확정 개선 판정 차단 |
| T12 | 공개 점수 상승, 비공개 점수 null | 미입증 또는 INCONCLUSIVE |
| T13 | 검증기/runner 조건 변경 | speedup 비교 비활성화 |
| T14 | failing regression/보안 테스트 | 후보 반려 + 이전 기준선 유지 |
| T15 | 해시 불일치·원본 미확보 | FAIL_CLOSED 및 차단 |
| T16 | PR/메모리 문서만 변경 | self-improvement 성과 0건 |
| T17 | 2회 연속 스케줄 실행 중 이전 run 진행 | 충돌 방지, 중복 모델 호출 0건 |
| T18 | 시간·토큰·예산 cap 도달 | 즉시 중단, 다음 체크포인트 명시 |
| T19 | 실험 중 모델/평가기/정책 자가수정 시도 | 별도 승인 요구, 자동 승인 불가 |
| T20 | 세 개체 단독 3회 실험 | 각각 own repo에 독립 3개 cycle/run + 원본 증거 |
| T21 | README projection 수행 | 검증된 값만 노출, 없는 값은 미측정 |
| T22 | README A/B/C 비교 | 사전 고정 조건과 랜덤 균형, 신규 보호 평가 |
| T23 | 프로덕션/main 자동 승격 요청 | 사용자 승인 없으면 불허 |

## 수락 단계
- Gate G0: README/AGENTS/상태 파일과 read-only CI (현재 Draft에서 통과 가능한 영역)
- Gate G1: T01~T05 + JSON schema, 원장 이벤트 immutable
- Gate G2: T06~T10 + 독립성/보안 정책
- Gate G3: T11~T19 + 모델·평가기 실행/예산·복구
- Gate G4: T20~T23 + 독립 루프와 원본 검증, 승인
- **합격 표기:** 검증 run URL과 작업 SHA 없으면 UNVERIFIED; 일부만 통과하면 PARTIAL; 진화/속도 개선은 별도 실측이 있어야 한다.
