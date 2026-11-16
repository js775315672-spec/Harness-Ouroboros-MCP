# P3e — Qwen CPU 엔진 1회 빌드·8개 독립 러너 재사용 실증

## 왜 추가했는가
P1d/P1e의 8개 Qwen 모델 레인은 각각 pinned llama.cpp 소스를 받아 GPU 없는 CPU 실행 파일을 개별 컴파일했다. 소스 패치 성공률이 낮은 상태에서 **8개 러너가 매번 같은 컴파일**을 수행하면 GitHub Actions CPU와 다운로드 비용만 증가한다. 이 실험은 모델 코딩 성능이 아니라 *컴파일 중복을 제거하는 실행 인프라*를 증명하려는 것이다.

## 비교 실험 범위
- 최초 빌드 러너 **1개**: upstream ggml-org/llama.cpp **4e5116f47619dac4180c3007ef02a383f347554c**의 실제 커밋을 검증하고, -DGGML_CUDA=OFF/-DLLAMA_CURL=OFF/-DGGML_NATIVE=OFF/-DBUILD_SHARED_LIBS=OFF로 CPU llama-completion만 컴파일한다.
- 패키징: 실행 파일 SHA-256, 정확한 검토 대상 GitHub 소스 HEAD, pinned upstream SHA, model_calls=0, repo_writes_authorized=false, merge_authorized=false를 provenance.json으로 기록. 같은 run에 GitHub Actions artifact로 업로드.
- **서로 다른 8개 GitHub 러너**: 각각 같은 run 안에서 동일한 아티팩트를 다운로드하고 원본 출처 및 바이너리 SHA를 확인한 다음에만 별도 시험 실행. 모델 가중치 다운로드/추론은 없음.
- 최종 집계: 빌드 성공, 모든 8개 분리된 consumer job 성공을 함께 요구한다. 하나라도 실패하면 전체 실증도 실패.
- 기존 회귀 테스트로 워크플로의 cache-mode:none, upstream 40자리 SHA, SHA 검증 순서, 불변 review SHA, 비밀키/쓰기 권한 없음 등 16개 구조 게이트를 검사한다.

## 캐싱 전략과 보안
이 방식은 엄밀히 GitHub Actions cross-run 캐시가 아니라 **동일 워크플로 내부에서의 일회성 컴파일 결과 배포**다. GitHub 캐시는 암호학적 서명이 없는 컴파일된 바이너리를 공유하므로, 무신뢰 PR이 복원할 수 있는 캐시를 곧바로 실행하지 않는다. 이번 워크플로에는 **cache-mode:none**을 설정하고 actions/cache를 아예 사용하지 않는다.

동일 run의 아티팩트도 독립 서명이 아니므로 모든 소비자가 SHA와 출처를 검증한다. 빌드 작업 자체를 신뢰할 수 없는 코드로부터 격리하는 작업, 바이너리 서명/재현 가능성, 실제 빌드 시간을 보고하는 작업은 후속 단계다. artifact에 약 4~6GB의 GGUF 파일, API 키/토큰, 비밀번호, 모델 프롬프트는 저장하지 않는다.

## 결과를 과장하지 않는 기준
- 성공 시 입증되는 것: pinned CPU 컴파일 1회가 8개 별도 runner에서 동일한 SHA의 실행 파일로 재사용 가능하다는 점.
- 성공해도 입증되지 않는 것: Qwen 추론 8회, 코드 수정 성공, 추론 품질 향상, 8×8 실제 AI 자율 진화, GPU 확장, Actions 비용 무료 보장.
- 이전 P3d 독립 모델 정체 게이트 PR #32 위에 쌓인 Draft이며 병합하지 않는다.

## 다음 운영 방향
이 워크플로가 통과하면 이후의 **새로운 실제 소스 코딩 과제**에서 각 러너가 별도로 llama.cpp를 컴파일하는 대신 검증된 동일 run 아티팩트를 사용하는 편이 합리적이다. 다만 기존 P1d/P1e 이미 검증된 연구 기록을 수정하지 않고, 다음 독립 실험에서 명시적으로 채택한다. CPU 재사용이 실제로 몇 분을 절약하는지 확인하려면 동일한 러너/소스 조건의 타이밍 비교가 필요하다.
