# 시험 불확실성 · 최종점 진단 · 중단 토론

PRO-EXPERIMENT-EXPERT-20261015-02의 실제 전용 구현이다. 시험 원값에서 명시
제공 불확실성 전파 또는 보존 최종 후보의 일반 residual Jacobian 진단을 실행하고,
판단·다음 시험 질문을 Study/Report로 저장한다. 기존 owner/JobManager/evaluator를
그대로 사용하며 읽기/재열기로 새 평가를 시작하지 않는다.

먼저 `APPLY_KO.md`로 신규 파일과 공통 hunk의 적용 순서를 확인한다. 사용자
동선은 `WORKFLOW_KO.md`, 기능/수치 보호는 `FEATURE_SPEC_KO.md`, 정확 API는
`API_KO.md`, 실제 실행과 미실행 경계는 `VERIFICATION_KO.md`에 있다.
`DEVICE_BOUNDARY_KO.md`는 실장비에 필요한 미제공 정보를 파일 작업과 분리한다.

Data/Numerical C2와 Sol 소유 GUI를 교체하지 않는다. 이번 ZIP의 source는 새
전용 파일뿐이며 공유 소스는 패치로만 전달한다. 현재 main에서의 최종 native
인수, C2 CAS 완료, 실제 계정/provider/장비 호출을 완료로 표시하지 않는다.
