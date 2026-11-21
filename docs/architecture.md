# 아키텍처와 작업 소유권

main의 [Hydra standing](../.github/workflows/hydra-standing.yml)은 승인된 작업을 실행한다. [다음 작업 선택기](../scripts/p3l_hydra_next_task.py)는 완료된 실행과 작업 이력에서 미해결 실패를 찾는다. 운영 승인은 별도 경로로 이뤄진다.

| 기존 작업자 | 책임 |
|---|---|
| W01 / W02 | 원장 입력 계약 / 모델 후보와 출처 |
| W03 / W04 | 진단 / 재시도와 호출 예산 |
| W05 / W06 | 독립 재생 검증 / 모델 실행과 CI |
| W07 / W08 | 후보 승격·롤백 검토 / 후속 사이클 인계 |

[고정된 작업자별 명세](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/tree/1261e99c25d18b7a116935b550e9950234202ba6/docs/p3l) · [main 검증 계약](evolution/README.md)

v3의 공개 실험에서 P0는 소스와 모델을 고정하고 P1은 입력 출처를 확인한다. P2는 기준선과 후보를 실행하고 P3는 관측을 별도로 검산한다. P4는 가중치 학습 등 개선 주장의 증거를 확인하고 P5는 후속 독립 평가를 정의한다. P6에서 승격 여부를 검토한다. 단계별 세부 실험 조건은 [해당 실험 계약](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/blob/bfa89dcc28287986e36e5d4f33693e53a8394902/docs/oril_v2_slot2_public30_independent_audit.md)을 따른다.
