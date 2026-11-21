# OFC Independent Evolution v3.1 · Ouroboros

코드 후보를 생성하고 개발 방법·실행 효율·신규 과제 일반화를 개선한다. 동일 조건의 신규 과제 합격률, 회귀율, 개발 시간을 측정한다.

## 단독 실행과 복구

이 저장소가 목표·코드·평가·기억·성공 판정을 소유한다. 자체 실패 기록에서 검증할 과제를 고른다. 다른 개체의 호출은 선택 사항이며 외부 개체가 중단돼도 로컬 과제를 계속한다. 과거의 필수 O→F→C 순서는 SUPERSEDED다.

실행 전 현재 main SHA를 조회한다. [P0 실행 계약](p0-cycle-registry.md)에 따라 inspect → acquire를 수행하고 작업 키를 reserve한다. 운영 원장은 이 저장소의 `ofc-cycle-registry-v1` 브랜치에 있는 `state.json`이다. cycle, owner, generation, source를 함께 사용한다. 결과 식별자를 record하고 checkpoint에 다음 재개 조건을 남긴 뒤 release한다. 충돌이나 미확인 외부 효과가 있으면 해당 개체만 BLOCKED로 기록한다.

## 평가와 기억

가설·실패 조건·분모를 실험 전에 고정한다. 입력과 평가기 버전, 원본 실행 URL, 대상 SHA, 결과 해시를 남긴다. 실패한 가설과 재현된 관측을 구분하고 검증된 경험만 다음 전략의 근거로 쓴다. 보호된 신규 과제에서 동일 기준선과 후보를 독립 재현한 결과로 개선을 판정한다. 실행 증거가 없으면 UNKNOWN 또는 NOT_RUN이다. 문서와 CI 통과는 성능 지표에서 제외한다.

