# 데스크톱 설계 검토

전체 제품의 기능 명세, 화면·작업 흐름, 실제 Qt 상호작용 시제품을 함께 검토하는 입구다.
현재 제출 상태는 [CURRENT_STATE](../../../CURRENT_STATE.md)에서 관리한다.
본제품 개발은 화면 검토 뒤 사용자의 개발 시작 지시를 기다린다.

**[화면을 보고 시제품 실행하기](REVIEW_GUIDE.md)**에서 시작한다.
CAD/FE → Simulation → Runner → Post → 최적화와 Expert → 연구 결과 → Study를
우선 경로로 구성했다. Data·Material·PDE는 각각 독립적으로 사용한다.

## 화면 보기

[CAD 피처](preview/cad-features.png) · [메시](preview/cad-mesh.png) ·
[해석 단계](preview/simulation-implicit.png) · [Runner](preview/runner-convergence.png) ·
[Post 측정](preview/post-gauge.png) · [최적화 후보](preview/numerical-moo.png) ·
[Expert 토론](preview/expert-discussion.png) · [Study 판단](preview/study-judgment.png) ·
[Data](preview/data-workbook.png) · [Material](preview/material-fit.png) · [PDE](preview/pde-weak-form.png) ·
[보고서](preview/report-preview.png) · [수집 채널](preview/acquisition-channels.png).
실제 Qt 소스에서 Windows 글꼴로 렌더한 창 내부 시안이며, 편집 원본은 아래 SVG/JSON/Qt다.

## 설계와 개발 자료

| 자료 | 용도 |
|---|---|
| [현재 화면 설계](pro-ux/DESIGN.md), [Qt 실행·조작 안내](pro-ux/README.md) | 도구별 실제 대상, 편집·선택·결과·오류·저장·재개 |
| [상태별 편집 화면](pro-ux/screens/README.md), [상태 원본](pro-ux/screen_states.json) | 실제 Qt에서 만든 SVG와 같은 상태를 재현하는 입력·선택·전환 |
| [작업 흐름 원본](pro-ux/Workflows.drawio) | 형상/해석/채택, 연구/토론/판단, 시험 자료/교정, 보고서/수집의 편집 도면 |
| [전체 기능 명세](pro-authored/FUNCTION_SPEC.md), [상세 화면·상태 계약](pro-authored/SCREEN_SPEC.md) | 제품 전체 범위와 구현자가 따라야 할 구체적 작업·입력·출력 |
| [요구 대응표](pro-authored/REQUIREMENT_COVERAGE.csv), [구현·화면 연결표](pro-ux/implementation_map.csv) | 요구 → 기능 → 화면 → 기존/추가 코드 → 완료·검증 조건 |
| [기능별·최종 통합 검증](pro-authored/VERIFICATION_PLAN.md), [실제 GUI 검토](GUI_REVIEW.md) | 앞으로 할 제품 검증과 현재 시제품에서 실제 확인한 범위 |
| [무료 도구·라이선스](TOOLS_AND_LICENSES.md), [MoAI 인계](pro-ux/MOAI_HANDOFF.md) | 추가 지출0원 조건, 기존 SPEC과 승인 뒤 개발 단위 |
| [현행 ADR 적용](../../ADR_APPLICABILITY.md), [기존 코드 재사용](SOURCE_REUSE.md) | 유효한 설계 기준과 역사 근거, 다시 만들지 않을 구현 |

실제 ChatGPT Pro가 주 설계·Qt 소스·상태 원본을 작성했다. Astra/xhigh는 핵심 설계와
수정된 작업을 독립 검토했고, Sol/high는 제한된 코드·입력 검사를, Luna/high는 기존 코드와
구현 대응을 조사했다. Codex가 실제 실행·시각 확인과 교정 요청·통합을 담당했다.
[최신 전달 요구](PRO_UX_REQUEST.md)와 [검토 기록](GUI_REVIEW.md)에서 구분한다.

## 실행

기존 Windows Python3.13/PySide6를 사용한다. 추가 설치나 계정 없이 실행한다.

    Set-Location C:\SourceCodes\autonomous-cae-lab
    py -3.13 docs/design/20261012-desktop-planning/pro-ux/qt_prototype.py --tool cad

Window 메뉴에서 다른 도구를 같은 세션으로 연다. File → Save review session…으로
여러 도구의 검토 작업을 저장한 뒤 --session 옵션으로 다시 연다.
각 도구 직접 실행, 일반 파일 저장·재열기, 단축키는 [실행 안내](pro-ux/README.md)에 있다.

시안의 형상·메시·수치·provider 발언은 공개 합성 예시다. 실제 solver·optimizer·장비·
provider는 실행하지 않는다. Qt 시제품은 제품 저장 형식이나 새 Core를 제안하는 코드가 아니다.
기획 서비스는 제품 필수 실행 환경에 포함하지 않는다. Penpot은 사용자 지시로 제외했다.

## 보존한 참고 자료

이전 [D1 검토](D1_REVIEW.md), [초기 Qt 조작 확인](QT_REVIEW.md),
[운영 도면](ownership-and-gates.drawio)과 [전체 연결 도면](research.drawio)은 근거로 남긴다.
초기 D1 폼이나 옛 PDF를 현재 제품 화면의 수용 근거로 사용하지 않는다.
[도구 연결 기록](tool_connection.json)과 [MoAI MCP 검사](moai_mcp_probe.json)는 설치·연결의
근거이며, 실제 사용성이나 제품 구현 완료를 뜻하지 않는다.
