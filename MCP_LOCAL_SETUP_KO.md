# Harness-Ouroboros MCP: 로컬 연결 안내

현재 구현은 **로컬 stdio 기반 읽기 전용 MCP 어댑터**입니다. 원격 HTTP 서버나 ChatGPT 앱 설치용 플러그인이 아닙니다.

## 실행 전제
- Python 3.10 이상, Git 설치
- GitHub 저장소를 로컬에 복제
- 저장소 루트에서 정책 파일 `harness-policy.json` 유지
- 비밀키, 거래소 API 키, 유료 API 불필요

## 실행
저장소 루트에서:

```bash
python3 scripts/mcp_bridge.py
```

Windows PowerShell에서는 `python scripts/mcp_bridge.py`를 사용할 수 있습니다.

MCP 클라이언트가 표준입출력으로 프로세스를 실행하도록 설정합니다. 클라이언트별 설정 파일 위치와 JSON 형식은 해당 클라이언트의 공식 문서를 확인해야 합니다. 예시 실행 명령은 `python3`, 인자는 절대 경로의 `scripts/mcp_bridge.py`입니다.

## 제공 도구
- `harness.evaluate`: 현재 저장소의 8개 정책 게이트를 읽기 전용 평가합니다.
- `ouroboros.recover_latest`: `artifacts/ouroboros-history.json`의 SHA-256 연결 이력을 검사하고 현재 Git HEAD와 커밋이 일치할 때만 마지막 체크포인트를 반환합니다.

## 동작 제한
- 도구 인자는 빈 객체만 허용합니다. 임의 경로 입력은 허용하지 않습니다.
- 외부 명령 실행, 코드 수정, 배포, 실거래 주문, 자동 병합 기능은 제공하지 않습니다.
- 체크포인트 복구는 **상태 조회**이며 자동 코드 롤백·작업 재시작이 아닙니다.
- 체크포인트 이력 파일은 별도 작성 도구가 만들어야 합니다. 파일이 없으면 조회는 오류로 차단됩니다.
- 해시 연결은 전체 이력을 재작성하는 공격을 막는 디지털 서명이 아닙니다.
- 로컬 신뢰 경계 안에서만 실행하세요. 임의 저장소를 열어 정책 파일이나 코드를 신뢰하지 마세요.
- 이 어댑터는 전체 MCP 상호운용성 인증이나 ChatGPT 앱 설치 검증을 완료하지 않았습니다.

## 개발 검증
```bash
python3 -m unittest discover -s tests -v
python3 scripts/governance.py
python3 scripts/evaluation.py
python3 scripts/harness_check.py
```

PR 병합은 사용자의 명시적 승인이 필요합니다.
