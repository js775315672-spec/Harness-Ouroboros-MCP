# P3d — 모델 반복 정체 감지 게이트 및 안전한 CPU 빌드 재사용 연구

## 재현된 실패와 해결 대상
실험 P3a(모델 호출 1회)와 P3b(새 모델 호출 1회)는 같은 실제 저장소 scripts/sandbox_policy.py 함수 수정을 요청했음에도 **모델이 기존 원본 함수를 완전히 동일하게 다시 출력**했다.
- P3a run: 43877024866, static_rejected / model source changed nothing.
- P3b run: 43878709609, static_rejected / model source changed nothing.
- 두 원본 출력 SHA-256 모두 **28bd5c7164432571c2a3353a33c5ff8e7aadd39a88f3444e1071f53a95f2316c**.
- 독립 재검증도 두 번 모두 정적 거부를 재현했고, 필수 model candidate acceptance CI는 두 번 모두 실패함.
- Qwen 모델 단독 실제 소스 패치 합격은 이 과제에서 0/2. 세 번째 동일 설정 호출에 대한 과학적 근거가 없으므로 중단.

## 새 코드 변경
1. scripts/model_stagnation_gate.py: 엄격한 SHA-256 태스크/모델/기준 소스 바인딩과 원본 응답 해시 검증, 연속 시도 번호, 최대 5회 재시도 상한, 독립 재검증 표시(자체 선언)에 대한 fail-closed 형식 검사.
2. 동일 소스/동일 모델/동일 과제에서 **동일 응답을 두 번 반환하면 'duplicate_model_response' 정지**. 서로 다른 응답이지만 두 번 모두 AST 원본 무변경으로 검증되었다면 'repeated_unchanged_source' 정지.
3. 검증된 후보가 한 번이라도 통과하면 추가 생성 대신 'passing_candidate_requires_human_review' 정지. 최대 허용 시도 수 소진도 정지.
4. 실험의 실패 로그·원본 응답·후보 해시가 누락·변조됐거나 범위를 벗어나면 예외/CLI 비정상 종료하여 **모델 호출 자체를 허용하지 않음**.
5. scripts/feedback_controller.py: 기존 입력 형식은 보존. 선택적으로 model_history + task/model/base 해시를 제공받으면, 모델 답안 실패를 녹색 하네스 검사와 별도로 감지하고 정체 발생 시 재시도 중단.
6. tests/test_model_stagnation_gate.py: 정체·원본 소스 무변경·중복·해시 위조·임의 필드·권한 상승·기존 feedback 호환·CLI 종료 코드 등에 대한 30개 사전 검증.

## 무엇이 증명되고 무엇이 아닌가?
이 게이트는 **모델 호출을 하지 않는 순수 상태 판정기**다. 입력으로 제공된 'independent_replay=True'는 외부의 CI가 실제 독립 검증을 수행했다는 암호학적 증거가 아니다. 모델 응답 원본 SHA를 검증하더라도 CI 실행 완료·GitHub 커밋과의 연결은 별도 정확 SHA attestation으로 확인해야 한다.

- 이 모듈은 '다음 모델 호출 가능 여부'만 판정하고 직접 실행하지 않는다.
- 만약 출력이 성공이라도 코드 커밋/PR 병합/실거래/새 에이전트 생성을 자동 승인하지 않는다.
- 다수의 전혀 다른 과제에서 모델 실패가 한 번 있었다고 모델 전체를 금지하지 않는다. 태스크·모델·기준 코드 해시가 다르면 새 고립된 시도로 판단한다.
- 인프라 녹색과 모델 코드의 합격을 별도로 판정하는 기존 P3a/P3b CI 게이트를 유지한다.

## CPU 빌드 캐시 보안 감사 및 설계
2026년 GitHub Actions는 캐시 쓰기 권한과 저장된 빌드 산출물의 신뢰 경계를 중요하게 다룬다. 외부 PR에서 복원된 **서명되지 않은 바이너리 캐시**를 무검증 실행하면 cache-poisoning에 의한 코드 실행 위험이 있다. 공개 캐시에는 비밀키, 유료 API 인증정보, 모델 원본 자격증명을 저장하지 않는다.

안전한 1차 최적화 우선순위:
1. **같은 workflow-run에서 llama.cpp를 한 번 빌드**하고 정확한 pinned 소스 commit 및 빌드 manifest SHA-256을 남긴다.
2. 8개 레인은 별도의 GitHub Actions artifact로 배포된 빌드를 다운로드하되, 해당 run에서 생성된 manifest/실행 파일 해시를 검증한 후 사용한다.
3. GitHub 저장소 간/PR 간 binary cache 복원은 일단 사용하지 않는다. 별도 신뢰된 빌드·서명·보안 검증 및 복원 범위 제한이 입증될 때만 허용.
4. 4~6 GB GGUF 모델을 각 GitHub 캐시에 저장하는 것은 저장용량·보안·공개 다운로드 조건을 검증하기 전까지 보류. 지금은 공식 모델 출처·SHA 검증 및 읽기전용 토큰을 유지.
5. 각 실행에서 download/build/inference/holdout 초와 cache hit/miss를 정확히 기록해 중복 CPU 절감 효과를 측정한다.

## 이번 PR의 통합 경로
PR #31(검토·보완된 실제 소스 수정) → 이번 P3d Draft(추가 읽기전용 모델 정체 게이트).
실패했던 PR #29·#30의 모델 원본 출력 및 빨간 acceptance CI는 증거로 유지한다.
모델 출력 재사용을 새 모델 독립 호출로 계산하지 않으며, 병합은 사용자 명시적 승인 전 수행하지 않는다.

## 한계
P3d는 아직 8×8 재귀 자동개발·연속 50분 무인코딩·모델 단독 코드 수정 성공률 향상을 실증한 것이 아니다. 비밀키·유료 API·자동 push/merge·실제 매매는 계속 금지된다.
