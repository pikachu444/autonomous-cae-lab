# Autonomous CAE Lab 인수인계

현재 구현·맡긴 작업·우선순위·다음 행동은 **[CURRENT_STATE.md](CURRENT_STATE.md)** 한 곳에서 관리한다.
이 파일에 별도 작업 목록이나 누적 진행 기록을 만들지 않는다.

## 새 세션에서 시작

1. [AGENTS.md](AGENTS.md), [현재 상태](CURRENT_STATE.md),
   [제품 목적](docs/PRODUCT_PLAN.md), [협업 규칙](docs/CODEX_WORKFLOW.md)을 읽는다.
2. 현재 Git 기준·로컬 변경·서브모듈과 맡긴 범위를 확인한다.
3. 해당 작업의 [상세 제품 설계](docs/PRODUCT_UI_MCP_PLAN.md), 유효한 ADR/계약,
   코드·실행 근거만 추가로 읽고 중단 지점부터 이어간다.

복사해서 전달할 Codex 시작문은 [CODEX_START.txt](CODEX_START.txt),
Pro 시작 방식은 [협업 규칙의 새 세션 절](docs/CODEX_WORKFLOW.md#새-세션과-인계)에 있다.
Pro와 Codex 모두 같은 기준 버전·최신 사용자 결정·미반영 산출물을 전달받는다.

## 사용법과 과거 근거

- [데스크톱 설계·Qt 시제품 검토](docs/design/20261012-desktop-planning/REVIEW_GUIDE.md),
  [전체 명세와 편집 원본](docs/design/20261012-desktop-planning/README.md).
- [한국어 설치](docs/INSTALL_KO.md), [첫 사용 예제](docs/USER_GUIDE_KO.md),
  [Windows 상세 안내](docs/WINDOWS_QUICKSTART.md), [독립 Research 실행](apps/research/README.md),
  [로컬 실행과 backend](docs/LOCAL_EXECUTION.md).
- [제품 상세기획](docs/PRODUCT_UI_MCP_PLAN.md), [사용 사례](docs/WORKBENCH_USE_CASES.md),
  [원요구 기록](PROJECT_SCOPE.md), [요구 해석](docs/REQUIREMENTS_VALIDITY_REVIEW.md).
- [세부 개발 목록과 지원·종료조건](docs/DEVELOPMENT_ITEMS.md).
- [이번 리팩토링의 실제 코드 경계와 장기 배치 후보](docs/CODE_STRUCTURE.md).
- [날짜별 구현·검증 기록](docs/WORKBENCH_PROGRESS.md),
  [전처리·후처리 수용 기록](docs/PREPOST_VERIFICATION.md), `benchmarks/records/`.
- [문서 통합 전 CURRENT_STATE/HANDOFF 원문](docs/history/20261012-before-consolidation/README.md).

과거 파일·ZIP·CI 산출물은 새 PC에 자동으로 생기지 않는다. 재현에 필요한 자료의
실제 위치·보존 기한·실행 환경은 해당 기록에서 확인한다. 역사 문서의 당시 다음 행동은
현재 명령이 아니며, 문서 정리나 Git 병합은 새 수치·GUI 실행의 근거가 아니다.
