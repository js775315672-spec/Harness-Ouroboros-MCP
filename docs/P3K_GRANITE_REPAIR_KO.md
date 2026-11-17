# P3k · 실패 요약을 사용한 개발 원장 수정 실험

P3j는 IBM Granite 8B Code Instruct에 이전 실패 구현을 보여줬다. Granite가 이미 거부된 구현과 같은 Python 구문 트리를 생성해 후보 검사를 시작하기 전에 멈췄다. [P3j 실행 기록](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions/runs/43990760806).

P3k는 같은 모델과 IBM 입력 형식에 저장소 원본 `validate(records)`와 실패 동작의 요약을 준다. 이전 모델 코드 전문은 프롬프트에서 제외한다. 감독자는 이전 출력의 해시와 구문 트리를 계속 확인한다. P3j와 비교할 때 달라진 사항은 모델에 보여주는 코드가 이전 실패본에서 원본 함수로 바뀌었다는 점이다.

## 검증 기준

- 같은 모델 리비전, 가중치 SHA-256, 생성 설정 및 고정 검사 25개를 사용한다. 코드 변경 범위는 `scripts/development_ledger.py`의 `validate(records)` 함수 하나다.
- 기준 코드의 기존 회귀 통과와 홀드아웃 실패를 먼저 재현한다. 새 출력이 정적 검사를 통과하면 격리 Docker에서 검사 25개를 실행하고, 별도 러너에서 같은 소스와 묶음별 검사 결과를 재검증한다.
- 최종 합격에는 고정 검사 25개와 독립 재검증이 모두 필요하다. 실험은 한 번의 모델 호출을 수행한다. 후보의 실제 승격과 다음 개발 과제는 별도 검증 단계다.

## 재현과 검토

이 브랜치의 `P3k IBM Granite ledger repair from failure summary` 워크플로에서 최종 `candidate_acceptance_gate`를 확인한다. GitHub 실행의 `p3k-actual-granite-source-patch-and-negative-tests`에는 원본 모델 기록과 생성된 패치가, `p3k-independent-real-repo-patch-replay`에는 별도 검증의 판정이 담긴다.

사전검사는 모델 없이 다시 실행할 수 있다.

```bash
python3 scripts/p3g_qwen_ledger_feedback_repair.py preflight \
  --retry-p3g --model granite-code-8b --omit-prior-code \
  --head-sha "$(git rev-parse HEAD)" --output artifacts/p3k/preflight.json
```
