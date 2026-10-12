# 현행 설계 기준과 과거 검증의 적용 범위

2026-10-12 최신 상세 기획 요청에 따른 운영 정리다. 원 ADR·수치·실패·threshold는
바꾸지 않는다. 현재 배정은 [CURRENT_STATE](../CURRENT_STATE.md), 상세 기능은
[제품 계획](PRODUCT_UI_MCP_PLAN.md)에 둔다. 아래 분류는 ADR 전체를 폐기하는 결정이 아니다.

| 역할 | 유지하거나 연결할 내용 | 이번 기획에 적용하는 방법 |
|---|---|---|
| 구조·책임 | ADR0001, 0002, 0003, 0005, 0007의 Core/Domain/Adapter, immutable child, numerical engine; ADR0060–0062의 독립 owner/native GUI/Evaluation/Study | 공유 ID·schema·gates·evidence·provenance는 Core, 물리와 수치 의미는 Domain, native syntax와 경로는 Adapter. 기존 upstream·reader·JobManager·문서 owner 재사용 |
| 문서·실행 의미 | ADR0013/0015/0018/0037/0042/0043–0045/0050 및 ADR0060–0062 | exact source/revision/result, invalid draft 저장, stale 요청 거절, 새 attempt, 취소 요청과 terminal 구별, file/mesh/location 의미, 저장/재열기·참조 복구는 해당 기능의 계약 |
| 과거의 한정된 adapter admission | ADR0004/0006/0010/0012/0017/0019–0036/0046–0049/0051–0059 등 | 그 adapter를 실행할 때 기존 지원/admission 한계 유지. 특정 예제·법칙·모델·provider·mesh가 미래 범용 제품 편집의 상한이나 전체 개발 선행조건은 아님 |
| 과거 실행 근거 | ADR의 당시 source/run/threshold, WORKBENCH_PROGRESS, PREPOST_VERIFICATION, benchmarks/records | 원값과 실패를 그대로 링크한다. 옛 NEXT/active/draft PR/순서는 당시 관측. CURRENT_STATE의 새 배정을 대체하지 않음 |
| 앞으로 필요한 검증 | 참조 재연결, 형식·단위/기저, save/reopen, numerical response, cancel/retry, physical evidence 등 | 관련 기능의 완료 조건에 목적·시점·선행·재사용 source/run·차이를 연결. UI만 바꾸면서 무관한 solver campaign 재실행을 요구하지 않음 |

사용자는 AI/CAD 없이 Data·Material·PDE·Numerical·Runner·Study를 사용할 수 있다.
Expert와 Workbench는 선택적이다. OpenScience/Expert는 질문·계획·해석을 돕고,
수치 라이브러리가 후보를 생성하며 solver가 물리를 계산한다. Pro 협업은 개발 운영이다.
제품 Expert의 inference 인증·범위를 자동 확대하는 허가가 아니다.

사용자 모델 접촉·비선형·explicit·파괴·구성 적분·일반 PDE·UQ/대리모델·원격 계산 요구는
계속 범위에 남긴다. backend가 없으면 편집 가능한 draft와 명시적 실행 차단을 설계한다.
기존 선형 단일 solid나 benchmark 하나의 PASS로 그 기능을 완성했다고 하지 않는다.
미확인 무료 구현 경로는 미결 항목으로 남기며 유료 제품이나 LS-OPT를 필수로 삼지 않는다.

과거 F05 `3.32295e-6 > 1e-6`, 실패한 AMD 시도와 UNKNOWN/NOT_RELEASED는 유지한다.
프로그램 실행·사용성·수치 유효성·공학적 release를 별도로 판단한다. 실제 장비/재료/강도/
내구 요구가 UNKNOWN이면 해당 공학적 release를 막는다. 문서나 CI 성공이 이를 대신하지 않는다.

이번 운영 변경은 본구현·수치 검증·새 provider 권한을 부여하지 않는다. Qt 시제품과 제한된
기술 확인은 사용자 허용 범위이며, 제품 본구현은 전체 설계 검토 뒤 사용자 지시를 기다린다.
새 구조 변경이 필요해지면 그 변경의 이유·대안·요구/계약 영향을 관련 ADR에 기록한다.
현행 경계를 그대로 재사용하는 화면 시안 때문에 새 아키텍처를 만들지는 않는다.
