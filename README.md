# Harness-Ouroboros-MCP

Hydra는 승인된 작업을 GitHub Actions에서 실행하고, ORIL은 후보 변경의 재현성·독립 검증·승인 이력을 추적한다. 현재 기준선은 [main 8fbecb5](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/tree/8fbecb5e813b653213d6c8d95ce7151868779512)이다.

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
