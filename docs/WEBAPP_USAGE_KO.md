# Claude / Gemini 웹앱에서 Harness-Ouroboros 사용하기

## 현재 가능한 것 (2026-11-15)

- GitHub 저장소 코드를 Claude/Gemini 대화에 제공해 **읽기 전용으로 분석**하고 개발 요구사항을 명세할 수 있습니다.
- GitHub Actions에서 **Qwen 0.5B CPU 모델**이 **정해진 단일 테스트 데이터 문자열 수정안**을 생성합니다. 임의 프로그램 제작 모델이 아닙니다.
- 수정안은 원본 저장소에 반영하지 않고, 제한된 Docker 환경에서 테스트와 오류 주입 검증을 수행합니다.
- 검증 증거가 완전할 때만 `ready_for_human_review` 상태를 출력합니다. 이는 PR 승인이나 자동 병합이 아닙니다.
- 유료 LLM API 키나 별도의 사용자 비밀키가 필요하지 않습니다. GitHub Actions 실행 시간은 계정/저장소 정책에 따라 과금될 수 있습니다.

## 모바일 웹앱 사용

1. Claude/Gemini에서 저장소 URL과 개발 브랜치 `feat/harness-governance-v1`을 알려줍니다.
2. AI에 **저장소 파일을 실제로 읽었는지** 확인하고, 실행 불가 시 명확하게 표시하도록 지시합니다.
3. GitHub 웹사이트에서 [Actions](https://github.com/js775315672-spec/Harness-Ouroboros-MCP/actions) → **One-shot PR cloud Qwen CPU inference** 실행 기록을 확인합니다.
4. 성공한 실행의 `one-shot-qwen-inference-evidence` 아티팩트를 다운로드해 `review-decision.json`과 `disposable-regression-compare.json`을 확인합니다.
5. 이 결과를 Claude/Gemini에 첨부하여 검토를 요청합니다.

### 직접 실행 버튼

`one-shot-cloud-inference.yml`에 `workflow_dispatch` 수동 실행 트리거를 추가했습니다.
**GitHub는 일반적으로 수동 실행 대상 워크플로 파일이 기본 브랜치에 있어야 Actions의 Run workflow 버튼을 표시합니다.**
현재 기능이 PR 개발 브랜치에만 존재한다면 버튼이 보이지 않을 수 있습니다.
기본 브랜치 반영은 별도 사용자 병합 승인 후 진행합니다. **이 가이드는 수동 실행 버튼이 이미 활성화되었다고 주장하지 않습니다.**

수동 실행이 아직 불가능할 때는 기존 PR synchronize 기반의 자동 검증 결과를 사용하세요. 검증을 위해 무의미한 커밋을 반복하지 마세요.

## Claude / Gemini 지시문

> Harness-Ouroboros-MCP 저장소의 `feat/harness-governance-v1`을 참고해 내가 요청한 프로그램의 요구사항, 위험, 테스트 계획을 만들어 주세요. GitHub Actions에서 실제 실행한 로그/증거를 확인하기 전에는 검증 성공이라고 주장하지 마세요. 현재 Qwen은 범용 코딩이 아니라 제한된 테스트 문자열 수정에만 연결되어 있습니다. 웹앱에서 GitHub Actions 실행 권한이 없다면 사용자가 눌러야 할 UI 절차를 알려 주세요. 유료 API·비밀키·자동 병합은 금지합니다.

## 아직 구현되지 않은 기능

- Claude/Gemini **일반 웹채팅에서** GitHub Actions를 직접 호출하는 범용 인터페이스
- 자연어 요구사항을 받아 **임의 프로젝트를 자동 생성하는 범용 코딩 에이전트**
- 각 웹앱에 Harness 규칙이 자동 주입되는 설치형 커넥터
- PR 병합 및 운영 환경 배포의 자동 승인

웹앱은 분석·명세·증거 검토에 사용하고, 실제 실행은 GitHub Actions가 담당합니다. 완전한 웹앱 직접 실행을 위해서는 해당 서비스의 지원되는 커넥터/API 권한과 명시적 사용자 승인이 별도로 필요합니다.
