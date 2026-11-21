# ORIL 슬롯 3: 공개 사이클 속도·품질 주장 분리 감사

기준: main `8fbecb5e813b653213d6c8d95ce7151868779512`. PR #330의 공개 3×2 주기 보고를 대상으로 한다. 이 PR은 독립 평가기·승인 게이트·배포·기존 실험 코드를 변경하지 않는다.

`python -m unittest discover -s tests -p 'test_oril_slot3_public_cycle_trend_audit.py'`

`python scripts/oril_slot3_public_cycle_trend_audit.py cycles.json`

입력은 각 주기 campaign, cycle, task_id, group_digest, model_revision, duration_s, baseline_correct, candidate_correct, n_groups, input_tokens_base, input_tokens_candidate, source_url를 포함한다. 보고서에서 사람이 전사한 값은 독립 검증된 원시 측정으로 인정하지 않는다. 동일 공개 문제 재사용은 독립 heldout n을 늘리지 않는다. 지연시간 중앙값은 서로 다른 실행의 추세나 속도 향상을 증명하지 않는다. 결과는 항상 promotion_allowed=false, 미공개 품질 판단불가다.

## 최소 반증 실험 / 다음 인계
1. #330의 두 Actions 아티팩트를 별도 읽기 권한으로 취득하고 ZIP digest와 각 주기 원시 JSON을 검증한다.
2. 원시 시작·종료 timestamp로 주기별 duration을 독립 재계산하고 이 감사기의 결과와 대조한다. 불일치 1건이라도 있으면 실패.
3. 동일 환경의 새로운 미공개 그룹을 독립 평가자가 고정해 정확도·회귀·실행시간을 재평가한다. 공개 성적 20/27/25 대 11은 일반화 증거가 아니다.
4. 모델 GPU 학습을 주장하려면 실제 GPU 로그, optimizer steps > 0, 어댑터 바이트와 SHA, 독립 평가가 모두 필요하다.

**현재 결과:** 코드 작성은 증거 판정 기능의 후보 개선일 뿐 모델 개선 없음. 속도 향상 판단불가.
