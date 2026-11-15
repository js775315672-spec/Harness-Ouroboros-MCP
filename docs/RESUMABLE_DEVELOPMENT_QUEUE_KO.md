# AURA Ouroboros: 재시작 가능한 개발 작업 큐 v1

현재 상태: **외부 실행 증거를 검증하는 읽기/복원 컨트롤러**. 본 모듈은 실제로 AI 모델을 실행하거나 소스 코드를 수정하지 않는다.

## 구현 범위

- 순서가 지정된 1~30개 작업, 현재 작업 위치, 재시도 횟수를 저장
- 잘못된 상태, 중복 커밋, 엉뚱한 작업/저장소의 증거, 비정상 체크포인트 차단
- JSON 체크포인트를 잠금 파일 + 임시 파일 + fsync + 원자적 교체로 저장
- 이전 체크포인트 해시가 일치하는 경우에만 갱신
- 기존 autonomous_loop_controller의 전이와 재시도 제한을 재사용
- GitHub에서 성공한 **Harness safety checks** 워크플로와 커밋을 확인한 작업만 완료 처리
- 최종 판정 human_review. 자동 Git 푸시, PR 병합, 실거래, 유료 API는 수행하지 않음

**보안 범위의 한계:** 로컬 JSON SHA-256은 우발적인 변조 감지이지 암호학적으로 서명된 원격 증명은 아님. 동일 파일시스템 밖의 병렬 실행은 별도 조정이 필요하다. GitHub CI 확인은 지정 커밋의 워크플로 결과를 확인하지만, 요구사항 충족이나 실제 코드 변경량을 독립적으로 증명하지는 않는다.

## 사용 예시

작업 목록 파일 tasks.json:

~~~json
[
  {"id": "step-01", "description": "Implement a narrowly scoped parser change"},
  {"id": "step-02", "description": "Add regression tests"}
]
~~~

초기화:

~~~bash
python3 scripts/resumable_task_queue.py init \
  --tasks tasks.json \
  --repo js775315672-spec/Harness-Ouroboros-MCP \
  --commit "$(git rev-parse HEAD)" \
  --checkpoint artifacts/resumable-queue.json

python3 scripts/resumable_task_queue.py inspect \
  --checkpoint artifacts/resumable-queue.json
~~~

inspect 결과의 autonomous_coding_connected는 false이며 실행이나 외부 API 호출이 발생하지 않는다.

외부의 격리된 코딩 실행기에서 소스 변경과 CI를 완료한 후 evidence.json을 제출한다:

~~~json
{
  "task_id": "step-01",
  "source_changed": true,
  "commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "ci_url": "https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/123456789",
  "checks": {
    "harness": "pass",
    "ouroboros": "pass",
    "regression": "pass",
    "secrets": "pass"
  }
}
~~~

위 커밋/실행 번호는 **형식 예시**이며 실제 검증 증거가 아니다.

~~~bash
python3 scripts/resumable_task_queue.py advance \
  --checkpoint artifacts/resumable-queue.json \
  --evidence evidence.json
~~~

GitHub에서 올바른 저장소와 커밋의 Harness safety checks 실행 완료 및 성공이 확인되지 않으면 진행하지 않는다.

## 검사

~~~bash
python3 -m unittest discover -s tests -p 'test_resumable_task_queue.py' -v
python3 scripts/governance.py
python3 scripts/harness_check.py
~~~

## 장시간 개발을 위한 다음 단계

1. GGUF 모델 실행기와 1개 작업 계약 연결. 제안 패치는 AST 검증 후 폐기 가능한 샌드박스에서만 실행
2. GitHub Actions 간 체크포인트 Artifact 전달과 복원 검증
3. 총 실행 시간·시도·CPU 사용량 예산, 중단/재개 규칙, 재실행 트리거 구성
4. 검증된 소스 변경량, 테스트 통과율과 회귀 실패율 측정
5. 분리된 평가를 통과한 전략만 채택; Harness/승인 규칙은 모델이 수정하지 못하도록 보호

이 모듈 하나만으로 몇 시간 동안 코딩을 이어가는 완성형 자율 개발 엔진은 되지 않는다.
