# 현재 작업과 제품 상태

갱신: 2026-10-18. 현재 배정·진행·다음 행동은 이 파일 한 곳에서 관리한다.
제품 목적은 [PRODUCT_PLAN](docs/PRODUCT_PLAN.md), 상세 사용자 작업은
[PRODUCT_UI_MCP_PLAN](docs/PRODUCT_UI_MCP_PLAN.md), 세부 개발·지원·종료조건은
[DEVELOPMENT_ITEMS](docs/DEVELOPMENT_ITEMS.md), 운영은 [CODEX_WORKFLOW](docs/CODEX_WORKFLOW.md)를 따른다.

## 현재 목표와 작업 방식

### 최신 요청 — 실제 에이전트 배정과 첫 호출부터의 통합 (2026-10-18)

사용자가 복구안의 실제 오케스트레이션과 제안 계획의 구현을 지시했다. 계획 모드의
읽기 전용 준비를 끝내고 아래 네 구현 담당을 실제 가동했다. 기존 진단을 반복하거나
새 Goal·Codex 작업을 만들지 않는다. 공통 파일은 Codex만 수정하고 첫 실제 문서·명령
호출부터 함께 확인한다. 현재는 구현 진행 중이며 아래 완료 조건을 통과했다고 보고하지 않는다.

| 담당 | 단독 쓰기 범위 | 이번 종료 조건 |
|---|---|---|
| desktop_specialist / Sol-high | `appearance.py`, 신규 `apps/research/common/commands.py`와 공통 UI 검사 | 같은 QAction·초점별 Undo/Redo를 실제 창에 연결하고 일반/좁은 창·한국어·선택·키보드를 확인 |
| data_impl / Sol-high | 신규 `native/data_labplot/` 연결·빌드·고지·검사와 Data 전용 창/검사 | 실제 원표·원행 선택·편집·Undo·단계별 저장·재열기·정확한 Material 전달. LabPlot 판정 실패 시 확정된 PySide6 대안 적용 |
| native_impl / Sol-high | Pre의 FEM/재료/연결/저장, Post의 navigation/comparison_native, Runner 전용 경로·검사·사용법 | 기존 공개 roller_support의 Tasks 취소/수락→동결 입력→두 실행→native Post 비교→원 설계 복귀·새 프로세스 재개 |
| material_numerical_impl / Sol-high | Material/Numerical 창·계획 패널·동일 변수 편집 부품과 전용 검사·사용법 | 두 fit 시험과 별도 holdout→같은 계획→실제 동정/확인→정확 후보 채택→저장·재개 |
| Codex / root | 공통 Core·reader·owner·API·dispatch·registry·provenance·desktop.py·통합·현재 상태·게시 | 전체 원표 읽기 API와 첫 호출부터의 문서/입력/결과 연결, 영향 검사·의미 있는 독립 검토·전체 인도 마감 |

기준은 `ee0608d`, pinned fixture는 `3e48bf6`이다. 미추적 첨부와 개인 초안 이미지는
보존하며 게시하지 않는다. 첫 Data 호출은 전체 원표 읽기→원행 선택→`data.update`
한 건이고, import와 정확한 보존 결과 전달은 별도로 확인한다. Material과 독립 Numerical의
서로 다른 변수표를 기존 같은 편집 부품으로 연결한다. 기존 SPEC·MoAI 기록을 재사용하며
옛 picked 목록을 현재 팀으로 취급하지 않는다.

native의 합성 연결 시험은 기존 등방성 fixture의 E=1000 MPa, ν=0.25, 바닥 Fixed,
saddle 면 전역 −Z Force 10→20 N이다. 실제 BRep 면·CLOAD 합력·원 입력을 확인한다.
CAE adviser와 native 담당이 기존 소스로 합의했으며 orthotropic 지그 계산과의 동등성이나
공학 적합성은 주장하지 않는다. 독립 검토는 의미 있는 통합 인도에서 Astra/xhigh가 맡는다.
정확한 첫 실행·결과·남은 장애는 이 절을 같은 작업에서 갱신한다.

첫 실제 연결에서 전체 원표 HTTP 조회·한 건 적용·보존 원문 새 프로세스 재열기를 확인했다.
Data 창의 정렬 뒤 원행 선택·로컬 Undo·명시 import와 부분 보기 저장 복구도 연결 중이다.
FreeCAD 1.1.4의 script module 이름 때문에 실행되지 않던 두 worker 진입을 adapter에서
교정해 기존 공개 지그 생성과 실제 메시 준비까지 진행했다. 첫 `pre.freeze`는 실제 C3D10
Jacobian gate에서 실패해 입력·응답을 보존했고 solver를 실행하지 않았다. 같은 모델의
진단을 CAE 자문과 확인하며 허용치를 바꾸지 않는다. 첫 전체 창 캡처의 빈 3D 영역도
시각 인수로 수용하지 않고 재확인한다. LabPlot은 고정 소스로 무료 Windows SDK를
격리 준비 중이며 빌드/실행·채택 판정은 아직 미완료다.

### 완료된 선행 작업 — 개발 복구 방법과 공학 GUI 기반 확정 (2026-10-18)

이번 배정은 개발 실패의 개선 방법·제품 청사진·새 세션 인계를 확정하는 것이다.
실제 Pro 교정안과 같은 Astra Extra High의 최종 독립 검토를 회수해
[공학 데스크톱 개발 복구안](docs/GUI_RECOVERY_PLAN_KO.md)에 통합했다.
다른 GUI 대화 두 건의 원문까지 읽고 사용자 결정과 assistant 추천을 구분했다.
현재 제품 구현 재개나 새 Codex 작업/Goal 생성으로 확대하지 않는다.

| 확정한 방향 | 실제 범위 |
|---|---|
| CAD/FE·Post | FreeCAD·ParaView native 작업 환경과 기존 계산·문서·결과 연결을 유지한다. 새 전후처리기를 만들지 않는다. |
| Data 기반 | LabPlot의 실제 탐색·표·곡선·속성·명령·도킹을 한정된 뼈대에서 Core와 연결해 판정한다. Data만 C++/Qt/KDE로 바꿀 후보이며 현재 제품 도입 완료나 사용자 채택으로 표시하지 않는다. |
| 나머지 Research | PySide6·기존 엔진을 유지하고 긴 폼 화면층을 앱별 작업면으로 교체한다. 공통 UI는 같은 데스크톱 담당 한 writer, 공통 Core/API/dispatch는 Codex가 소유한다. |
| 첫 제품 인도 | 기존 공개 지그의 FreeCAD 편집→지원 정적 해석→Runner→ParaView 기준/변경 비교→원 설계 복귀·재개를 닫는다. Data 기반 확인과 병행한다. |
| Research 인도 | 두 시험 자료→Material·동일 Numerical 계획→동정/별도 확인→후보 채택·재개. native 작업의 선행 관문이 아니다. |

정적 SVG/PNG 확장은 중단했다. 반려된 네 시안은 공개 승인본으로 게시하지 않고
`_workspace/gui-recovery-plan/rejected-drafts/`에 보존했다. 다음 기술 확인은 빈 창·고정
그래프가 아니라 실제 선택·편집·Undo·저장·다른 도구 전달이 연결된 프로그램이다.
LabPlot의 핵심 동작을 대부분 버리거나 Core를 광범위하게 다시 써야 하면 Data도 PySide6
작업면 교체로 합친다. 같은 후보 조사와 정적 시안을 다시 순환하지 않는다.

Pro는 기존 GUI 보수의 우위를 미리 확정한 첫 결론을 철회했다. Astra는 수정된 기반·인도
순서를 수용하고, 실제 소스에서 로컬 Undo·부분 저장 실패·전체 자료 읽기·원행·설정 적용과
실제 import 결과의 전달 계약을 보완했다. 이 보완까지 공개 복구안에 넣어 설계 쟁점을 닫았다.
실제 LabPlot 채택과 GUI 사용성은 정해진 기술 확인에서 판단한다.

작성 기준은 main `55efacb`, 제품 소스는 `7847c33`이다. 이번에는 문서와 로컬 에이전트
설정을 바꿨으며 제품 코드는 바꾸지 않았다. 옛 W1–W5·reviewer high·SPEC의 영구 승인 대기
충돌을 정리했고, 다른 역할의 모델·권한과 사용자 파일은 보존했다. MoAI MCP와 설치된
계획/동기화 절차를 사용했으며 옛 picked 목록을 현재 실행 중인 팀으로 세지 않는다.
새 앱·solver·provider 실행, donor 소스 반입·설치·빌드는 하지 않았다. 기존 지원·수치
실패·허용치·요구 완료 상태도 이번 설계 게시로 올리지 않는다.

다음 행동은 이 복구안을 기준으로 사용자의 구현 재개 배정을 이어받는 것이다.
새 Codex 세션을 권고하되 자동 생성하지 않으며 [CODEX_START](CODEX_START.txt)로 인계한다.
같은 전체 진단을 다시 시켜 보고만 받고 멈추는 단계를 추가하지 않는다. 구현이 배정되면
정해진 한정 뼈대와 native/Research 인도를 일상 재승인 없이 끝낸다.
협의 원문은 `_workspace/gui-recovery-plan/`에 있고 공개 인계에 필요한 결정·계약은
위 복구안에 담았다. 아래 과거 배정·완료 기록은 자동 재개할 새 작업 큐가 아니다.

### 완료된 선행 작업 — 개발 및 GUI 실패 원인 독립 진단

사용자는 Astra Extra High 독립 에이전트와 새 실제 ChatGPT Pro 대화에, 개발 지연·지시
불이행·낮은 custom GUI 품질과 반복 교정의 원인을 각각 물으라고 지시했다. 이번 배정은
진단과 교정 권고이며 새 GUI 구현·리팩토링·solver 캠페인 재개의 지시로 확대하지 않는다.
기준 소스는 `7847c33`이고 실제 제출 화면은 보관된 10월 중순 캡처임을 명시한다.
Astra/xhigh `gui_delivery_diagnosis`의 독립 진단을 회수했다. 제공 자료와 비교할 질문은
`_workspace/gui-delivery-diagnosis/brief.md`, 결과는 같은 폴더의 `astra-review.md`다.
실제 14개 화면과 관련 소스·문서의 대조 결과이며 새 OS 실행 인수는 아니다.
Pro 요청 `PRO-GUI-DIAG-20261018`은 계정 불러오기 오류를 UI 재시도로 복구한 뒤
새 실제 [Pro 대화](https://chatgpt.com/g/g-p-6abbcb200108819193174a8715322a59/c/6ad39954-12e0-83ee-9960-947860b283ab)에 전송했다.
실제 UI의 Pro/파워 5, 소스·문서·전체 14 화면을 담은 ZIP과 대표 9 이미지의 첨부,
요청 본문의 새 사용자 메시지 표시와 최종 응답 완료를 확인해 회수했다. Pro의 완료 응답
요약은 `_workspace/gui-delivery-diagnosis/pro-review.md`, 두 결과의 통합 진단은
[GUI와 개발 인도 실패 진단](docs/GUI_DELIVERY_REVIEW_KO.md)에 있다. 사용자 지시는 구체적이었으나
내부 구조 중심 편집, 실제 업무 인수 미마감, 앱별 조작 불일치와 현재 지시 충돌이 남았다는
판단이다. 공통 테마·기존 서비스 기반을 없다고 하거나 모델의 불변 무능으로 설명하지 않는다.
Codex는 재귀 폼·취소 명칭·사본 재열기 안내·테마를 현재 소스에서 대조했고, Data는 현재
설정 접기 개선을 반영해 과거 사진의 문제를 모든 최신 상태로 일반화하지 않았다.
두 검토자의 다음 Research 인도 제안은 권고로 기록하며 새 구현 배정으로 채택하지 않았다.
아래 기존 완료 기록과 하단 기능 배정은 이번 진단의 새 구현 대기열이 아니다.

Windows 로컬의 독립 공학 도구와 전체 연결을 완성한다. FreeCAD FEM·Gmsh·설치된
솔버·ParaView의 native 기능을 재사용하며 전후처리기를 새로 만드는 과제가 아니다.
Data·Material·PDE·Numerical·Runner·Expert·Study는 필요한 외부 도구만 요구한다.
Workbench는 선택 연결 보기다. 제품 주 화면을 웹으로 바꾸지 않고, WSL을 모든 앱의
필수조건으로 삼지 않는다. 추가 지출·유료 API·추가 구독은 0원이다.

2026-10-16 사용자가 "니 맘대로 해봐. 리팩토링인지 뭔지"라고 지시해 리팩토링을 재개했다.
기존 개발 중지 이후의 질문들을 구현 허가로 취급하지 않았으며, 이 최신 지시부터 코드 수정·
영향 검사·통합·커밋을 진행한다. 현재 Goal 도구에는 등록된 Goal이 없고 새 Goal은 만들지 않는다.
우선 범위는 기존 native 전처리 재사용, 제품의 예제 의존 제거와 순수 결과 writer의 앱 역의존
제거다. 기존 조사 결과를 재사용하며 새 전처리기·범용 프레임워크·수치 엔진은 만들지 않는다.
당시 배정은 아래 재개 작업과 미커밋 통합 정리에 한정했다. 현재 배정은 상단의 최신 청사진
요청이며 하단의 기존 기능 배정 전체를 자동 재개하지 않는다. 사용자 파일·비공개 자료는 보존하고, 우리가 남긴 구현 후보는 현재
소스와 대조해 연결·검사·통합까지 마무리한다. 남겨 두는 것 자체를 완료로 보고하지 않는다.

### 미커밋 통합 정리 — 이번 결과

사용자가 리팩토링 뒤 남은 코드를 직접 해결하게 떠넘기지 말라고 지적했다. 현재 기준은
`faa296f`이며 기존 감사의 구체 결함을 재사용한다. 새 제품 기능을 추가하지 않고 아래 세
묶음을 정리했다. 취득·Post와 해석창의 잘못된 초안 처리 수정을 커밋하고 원격 main 반영을
확인했다. 기존 native GUI 직접 인수는 Windows 잠금으로 별도 남는다.

| 소유 | 마무리할 범위와 완료조건 |
|---|---|
| pending_acquisition_integration / Sol-high | 기록 취득의 저장 상태·교정 원본 보존·시계 초기화 후 지연 표본·원문 선택 오류를 수정해 통합. 다른 폴더/새 프로세스의 저장본 재개와 실제 HTTP·Qt 경로 확인. 실장비 제어는 포함하지 않음 |
| pending_thermal_integration / Sol-high | 사용자 지적 뒤 기존 native 온도와 별도 FELUPE 연구 확장을 구분. 새 helper는 통합하지 않고 미완성 3D 확장의 제품 hook·파일을 제거. 기존 2D P1/native FE 동작을 확인. B4.5/B6.3 요구는 별도 미완료 유지 |
| vtu_boundary_refactor / Sol-high | 고차면 Post 선택·적분·metadata·Data/계획 인계와 저장 재열기를 통합. 누락된 면 평균/두 점 시간 이력의 곡선 목록·원 성분·시각·mask 전달을 수정. 수치 규칙·허용치는 유지 |
| Codex / root | 공통 evaluation/Workbench 경계·위 세 후보의 호환·상태·문서·선택적 커밋/게시 책임. private 첨부·초안 사진은 제외 |
| audit_pre / CAE 자문, architecture_diagnosis / Astra | 필요한 온도/요소 의미를 담당자와 직접 합의하고 세 묶음의 의미 있는 통합을 독립 검토. 이전 전체 감사를 반복하지 않음 |

미완료 코드를 사용자에게 넘기는 대신 실제 호출과 저장까지 닫는다. 기존 API 호환을 유지한
리팩토링이 모든 후보를 자동으로 망가뜨렸다고 추정하지 않으며 새 충돌과 기존 결손을 구분한다.
이번 Astra 통합 검토에서 취득 계획의 오래된 전체 초안이 최신 편집을 덮는 문제와, 취득창이
다른 Data 문서로 잘못 전환되는 문제를 고쳤다. 수정 소스를 재검토한 최종 판정은 PASS이며
검토 범위의 남은 코드 차단 지적은 없다. 이는 OS 직접 조작·실장비·공학적 승인 판정이 아니다.
취득 관련 37개, Post 관련 137개, 기존 온도 경로 58개와 해석창 9개의 집중 검사가 통과했다.
관련 Qt 렌더와 실제 loopback 통신, 별도 Python 저장본 재개를 확인했고 소유 테스트 프로세스는
정리했다. 변경하지 않은 전체 solver 캠페인은 실행하지 않았다.
온도 정리는 추측에 따른 삭제가 아니다. 설치 FreeCAD의 초기/최종 온도·CTE/Tref writer를
확인했고, 430줄 thermal_regions 후보는 기본 native 온도 설정이 아닌 별도 재료 연구다.
이를 일반 온도 연결 수리로 가져오지 않았다. 자체 실험의 여섯 전용 tracked 파일과 두 공통
hook을 기준본으로 복구하고, 네 untracked 실험 파일은 검증된 복구 사본을 남긴 뒤 제품에서
제거했다. `_workspace/retired-temperature-experiment-20261017/`은 배포·실행 경로가 아니다.
독립 재료 Case C와 물리시간 절점 온도장을 받는 native consumer는 이 정리로 완료되지 않는다.
원격 코드 반영과 Space 요약 갱신을 확인했다. 남겨 둔 제품 코드 미커밋은 없도록 정리하며,
비공개 첨부 폴더와 별도 개인 초안 사진은 게시하거나 삭제하지 않는다. 다음 직접 인수는
잠금 해제 후 기존 FreeCAD Tasks의 편집·수락/취소→실제 입력 생성→저장/재열기다.

### 재개 작업

| 범위 | 이번 결과와 쓰기 경계 |
|---|---|
| native Pre | 중복 탄성 물성·기존 고정/힘 값 폼을 FreeCAD Tasks 진입으로 교체해 커밋. 대상 확인·형상 변경 후 방향 복구·지정 변위·Lab 전용 편집 보존. 실제 FreeCAD 수락/취소·입력 생성·저장 재열기 인수는 미완료 |
| Expert 자료 팩 | 제품 loader와 원문·라이선스를 패키지로 이관해 커밋. GUI의 예제 의존 세 곳 제거, 예제 CLI 호환 유지. 예제가 없는 추출 wheel의 자료와 실제 Qt 목록 읽기 확인 |
| 순수 결과 writer | `caelab/adapters/vtu.py`로 이관해 커밋. 여섯 library 호출부 전환, 기존 앱 import 호환과 이관 전후 XML 바이트 일치 확인 |
| 솔버별 기존 전처리 | 실행기 조사를 마침. 현재 검색/선택기는 FreeCAD·ParaView만 등록하며 SALOME-MECA/AsterStudy·OpenCourant 외부 전처리 연결은 미구현. 이번에 새 연결을 구현했다고 표시하지 않음 |

MoAI의 run 절차로 범위·독립 계획 검토·단독 파일 소유·관련 최소 검사를 적용한다.
Astra의 재개 계획·통합 검토를 거쳐 세 수정 범위를 커밋했다. native 편집의 실제 실행 입력
반영과 취소 불변은 다음 직접 인수에서 확인한다. 자료 팩은 원문·라이선스·manifest 바이트를
유지했고, VTU는 이관 전후 출력 바이트와 기존 import 호환을 확인했다.
세부 변경 계약은 [구조 정리안](docs/CODE_STRUCTURE.md)의 재개 작업을 따른다.

### 앞선 리팩토링의 확인 기록

Sol 세 담당이 파일을 나눠 작성하고 native 담당과 CAE 자문이 직접 협의했다. Astra가 계획과
실제 반영본을 독립 검토했으며, 방향 복구 경로 누락과 숨겨진 이전 방향의 재주입을 고친 뒤
검토한 변경의 남은 코드 차단 지적은 0건이다. 작은 변경의 새 Pro 요청은 보내지 않았다.
MoAI run 절차와 실제 decision/integration CLI를 사용했고 모델·권한 설정은 바꾸지 않았다.

native 관련 네 검사 파일 93개, 자료 팩/Qt 집중 검사 9개, writer 관련 검사 14개가 통과했다.
Qt 보조 패널의 좁은/넓은 배치와 자료 팩 창을 이미지로 확인했으나 OS 직접 조작 인수는 아니다.
추출 wheel 확인은 배포 자료 포함 검사이며 당시 작업 중인 소스를 포함한 wheel을 출시하지 않았다.
별도 dynamic cold-open 한 검사는 `frozen_input/contact.inp`의 exact-attempt pin 오류로 실패했고,
원래 HEAD writer를 넣어도 동일했다. 이번 추출의 회귀로 숨기거나 고치지 않았다.

다음 최소 인수는 설치 FreeCAD에서 재료·고정·힘 Task 편집과 수락/취소, 대상 변경/복구,
기존 입력 생성의 값 반영과 저장·새 프로세스 재열기다. 현재 Windows 캡처가 지문 잠금 화면이라
입력을 중단했고 native 테스트 앱을 새로 열지 않았다. 잠금 해제 후 이 경로부터 이어간다.
앞선 리팩토링에서는 취득·온도 전달·고차면 초안을 분리했고, 위의 후속 통합 정리에서 처리했다.
코드 두 커밋은 원격 main 반영을 확인했다. Space의 현행 요약도 같은 수정 범위와 native
직접 인수 미완료로 갱신했다. 당시 남았던 기능 상태표도 이번 통합 결과에 맞게 갱신한다.

### 재개 전 조사 기록

아래는 개발 중지 중에 수행한 감사 기록이다. 당시의 '미수정·중지' 표시는 위 재개 작업의
현재 진행 상태와 구분한다.

읽기 전용 분석 결과는 [코드 상태 보고서](_workspace/code-state-audit-20261016/STATUS_KO.md)와
[코드 연결도](_workspace/code-state-audit-20261016/CODE_MAP.svg)에 있다. 온도 전달의
실행 경로 결손과 취득의 저장·시간 구간·선택 문제 등을 확인했으며 제품 교정은 하지 않았다.
사용자의 전체 코드 조사 지시에 따라 [전체 분석 보고서](_workspace/code-state-audit-20261016/full/REPORT_KO.md)와
[파일·함수 탐색기](_workspace/code-state-audit-20261016/full/CODE_EXPLORER.html)로 범위를 넓혔다.
전체 저장소 인벤토리와 1,678개 Python/매크로 구문 분석, 221개 파일의 관련 본문 검토를
구분했다. 신규 기능·복구 결함 15건, 사용성 정책 미적용 2건, 추가 확인 후보 2건이다.
최신 원격 CI는 Windows 한 검사 실패와 Linux 전체 검사 중 crash로 실패했으며
후속 native 계열 검사는 건너뛰었다. 감사 당시 수정·재실행·게시는 하지 않았다.
소스 배치·책임·의존 방향과 기존 파일의 단계별 이동은 [코드 구조 초안](docs/CODE_STRUCTURE.md)에
정리했다. 당시 적용 전 검토안이며 새 폴더 생성·제품 파일 이동·구현 재개는 하지 않았다.
Astra/xhigh의 구조 검토, Sol/high의 소스 교차 검토와 GUI·권한 경계 검토를 마쳤다.
[독립 코드 리뷰와 수정 범위 제안](_workspace/code-state-audit-20261016/architecture/REVIEW_KO.md)에
기존 설계의 재사용 근거, 확인된 결합 다섯 가지와 한정 수정 단위를 정리했다. 전면 재작성이나
폴더 일괄 이동을 권고하지 않는다. ‘패턴이 거의 없다’는 앞선 설명을 교정했다.
같은 보고서에 예제의 사용자 학습·개발 검사·제품의 잘못된 의존·미통합 후보를 구분했다.
대표 실패 주입/제작 응답 코드와 실제 제품 호출을 읽었으며 예제 삭제·이동·실행은 하지 않았다.
사용자가 지적한 전처리의 중복 자체 설정 UI·입력 변환 축소를 같은 수정안의 우선 항목으로
반영했다. 기존 FreeCAD Tasks·native writer 재사용을 기준으로 대체 가능한 코드를 줄이고,
필요한 연구 연계·미제공 요구 기능을 구분했다. 이 시점에는 문서만 반영했다.
개발 중에는 영향을 받은 최소 실행·단위 확인을 수행하며 변경하지 않은 솔버 캠페인을
반복하지 않는다. 테스트로 연 프로그램은 해당 Windows Job/PID만 정리한다.
사용자 세션을 이름으로 종료하지 않는다.
대화 캡처·전달 기록·해시 목록을 사용자에게 진행 성과로 제출하지 않는다.

**역할:** Pro는 전체 설계·상세 명세·중요 판단, Sol 담당은 의미 있는 기능의 코드·GUI·
검사·사용법, Codex는 공통 경계·실행 확인·통합·게시, Astra는 핵심 통합의 독립 검토다.
MoAI는 SPEC·배정·진행 관리 도구다. 작은 교정마다 Pro를 부르지 않는다. 최근 전체
설계 요청 한 건은 완료·회수했고 Astra의 여섯 필수 교정을 반영해 채택했다.
Pro 원문과 Codex/Astra 교정은 저작을 구별한다. 새 Pro 구현 요청은 보내지 않았다.

## 종료 범위와 남은 수

[세부 개발 목록](docs/DEVELOPMENT_ITEMS.md)의 **71개 고유 인도단위**로 종료를 관리한다.
기준 분류는 **개발 및 인수 D 29 / 기존 구현 인수 A 38 / 외부 인수 E 4**다.
이는 같은 크기의 기능 71개나 제품 완료율이 아니다. 기존 소스의 대부분을 재개발한다는
뜻도 아니다. D에 포함된 구현·사용 인수를 다시 별도 A로 더하지 않는다. 기존 44개 부모,
74개 FN, 52개 원요구 절, 22개 Pre 항목, 17개 UC와 다섯 통합장면은 대응 범위이며
개수에 더하지 않는다. 이번 목록의 CLOSED는 아직 선언하지 않았다.
현재 D 29개 중 **7개는 본코드 통합과 한정 확인을 마쳤고, 22개는 추가 개발이 남았다.**
중단 직전의 기능 배정은 아래에 보존한다. 이번 재개는 위 리팩토링 범위이며,
기존 기능 묶음의 작성을 자동 재개한 것은 아니다.
일곱 항목의 미실행 범위와 최종 사용자 인수는 같은 ID 안에서 닫으며 별도 기능으로 더하지 않는다.

각 ID의 입력→조작→결과·단위, 지원 solver/요소/법칙/환경, 수정 코드, 의존,
실패·취소·저장·새 프로세스 재개와 완료조건은 상세 목록 §3–5에 있다.
소프트웨어 인도는 67개 비외부 항목 및 연결된 필수 사용 흐름을 닫으면 종료한다.
나머지 E는 장비 한 건과 승인 SSH/Slurm/OpenPBS 실제 환경 세 건이다.
장비 없이 가능한 수집 경계 개발이나 Windows 배포를 외부 대기로 넘기지 않는다.
공학적 승인·물성·강도·durability UNKNOWN은 프로그램 성공과 별도로 유지한다.
후속 확장을 현재 종료조건에 조용히 더하지 않고, 필수 요구를 미지원 표시만으로 닫지 않는다.

### 중단 전 기능 배정 — 아래 작업은 자동 재개하지 않음

| 담당 | 현재 결과와 쓰기 소유 |
|---|---|
| post_windows_build_fix / Sol-high | 적층 셸 인도 완료. 다음 B6.3.L03: 기존 CCX 지지 반력→정확 TRI6 대응→보존 하중 전달. `_workspace/conservative-load-delivery/`만 작성 |
| inverse_delivery / Sol-high | 스프링·댐퍼 인도 완료. 다음 B1.5.L01: 기존 Aster native hard contact를 사용자 모델의 면 선택·조건·실행·결과에 연결. `_workspace/aster-hard-contact-delivery/`만 작성 |
| dynamic_reprocess_gui / Sol-high | 체결 인도 완료. 다음 B1.4.L02: 기존 native 온도·초기 응력/변형 조건 편집과 실행 연결. `_workspace/initial-fields-delivery/`만 작성 |
| native_post_delivery / Sol-high | 변형률 측도 비교 인도 완료. 다음 B3.3.L01: 고차면 선택과 면 측정. `_workspace/quadratic-surface-delivery/`만 작성 |
| connector_code_review / Sol-high | 관측 불확실성 인도 완료. 다음 B4.5.L02: 기존 FELUPE Hex8의 다영역 열·Maxwell 조건과 지연 복귀. `_workspace/thermal-regions-delivery/`만 작성 |
| acquisition_delivery / Sol-high | B7.6.L01: 실제 기록 CSV의 취득·sequence·부분자료·중단/재개를 기존 Data owner에 연결. `_workspace/acquisition-delivery/`만 작성. 실제 장비 binding은 별도 외부 인수 |
| whole_closeout_review / Astra-xhigh | 전체 설계와 E3/E5/E6 통합 독립 검토 완료. 지적 F1–F5 교정 확인, 해당 범위 차단 결함 0 |
| pde_transfer_review / Astra-xhigh | B3.2.L02/B7.3.L01 통합 독립 검토 완료. 행렬 선할당·미선택 채널 간섭 교정 확인, 명시 범위 차단 결함 0 |
| cae_engineering / CAE 자문 | native 접촉·초기장·보존 하중·고차면·열변형의 필요한 계약만 담당자와 직접 논의. 독립 최종 검토나 제품 Expert와 구별 |
| Codex | B6.3.L04: 기존 P1 온도 전달을 실제 3D Hex8 절점·온도 history port에 연결. Core/registry/owner/public 경계·공통 GUI/저장·문서·Git 통합. 전용 모듈은 담당 작성물을 검토해 반영 |

전용 작성은 각 `_workspace/*-delivery/`에서 분리하고 root가 실제 공통 파일에 병합한다.
담당자들은 구체 설계 문제를 직접 논의할 수 있다. 팀 일곱 개는 소유영역이며 고정 동시
일곱 호출 의무가 아니다. 새 배정은 이미 정한 71개 안의 작업이며 범위를 추가한 것이 아니다.

## 이번 체크포인트

- 앞서 게시한 `bb31834`: 완료 native 입력을 새 계산 없이 기존 Simulation 문서로 열고,
  같은 입력 모델을 FreeCAD로 다시 연다. HTTP/CLI/Python/MCP 소스는 같은 문서를 쓴다.
  중복 요청·응답 유실·재시작에서 미저장 편집을 보존하며 공개 data_id 검증 뒤 실행 시 한 번만 해소한다.
- 적층 셸: S8R COMPOSITE 2–16층 입력·층 순서/재료·층별 결과와 실행 메뉴를 제품 트리에
  통합했다. 실제 원 CCX 자료의 DAT 128 IP/FRD 16층 solid를 읽고 FreeCAD·Simulation
  재열기를 확인했다. 원 수집 FAILED는 유지하며 보정 reader의 읽기 성공과 구별한다.
  실제 broker 버튼 전체 왕복과 ParaView 시각화는 아직 수용하지 않았다.
- 스프링·댐퍼: Windows OpenCourant TYPE13·기존 실제 C3D4 FE 영역/RBODY 연결을 통합했다.
  한 실제 Engine 실행에서 힘/모멘트/상대운동 채널을 회수하고 Simulation 재열기와
  원 FreeCAD 계수 편집·저장·새 프로세스 재열기를 확인했다. 일반 implicit static이나
  모든 연결요소 법칙의 지원으로 확대하지 않는다.
- 체결: C3D10의 조임→길이 유지→외력, 절단면 선택과 결과 읽기를 통합했다.
  실제 선택 절단면 절점력 합 599.9996 N은 지지 600 N과 일치한다. SOF −1200.021 N은
  복구 응력 면적분이며 다른 물리량이다. 원값·원 실패를 보존하고 일반 RF/contact force로
  확대하지 않는다. cold 선택의 원 subshape 결속도 같은 원 BRep로 확인한다.
- 세 native 기능의 원 모델 재열기·공개 입력 단일 해소·Ctrl+S/닫기/재연결·미적용 raw
  보관·별도 솔버 메뉴 조건 누락을 교정했다. root 최종 집중 161개 확인 통과, 소유 Job 정리.
  Astra가 실제 반영 소스와 해당 결과를 대조해 다섯 지적을 닫았다. 체결의 새 raw 초안은
  controlled fresh editor에서 확인했으며 실제 새 raw `.caepre` cold 실행으로 바꿔 말하지 않는다.
- 변형률 비교: total E/e/material H를 같은 기준 E로 변환하고 원 측도·행·mask를 유지한다.
  e는 F 필수, E/H는 선택이다. 실제 ParaView 수치 경로·보존본 재열기와 정상/좁은 Qt를
  확인했고 root 37개 집중 확인, 기존 응력/비교 경로 회귀가 통과했다. 사용자 C-bound는
  native 정확도 인증으로 승격하지 않는다.
- 관측 불확실성: 원 교정식·게이지·단축 응력·시간 오프셋을 기존 전파 엔진과 Plan/Study/
  Report에 연결했다. 실제 HTTP 저장·보존본 재열기, root 24개와 후속 2개 경계 확인 및
  QWindows 확인을 마쳤다. 긴 원자료의 N² 선할당과 긴 미선택 채널 간섭을 교정했다.
  두 연구 기능은 Astra의 명시 범위 검토를 마쳤다. 전체 앱의 최종 사용 인수·공학 승인은 별도다.

## 항목별 현재 진도

아래는 제품 기능별 진도이며 이번 진단의 구현 배정 목록이 아니다. 개발 대기는 이미 있는 부분까지 없다는 뜻이 아니며,
기존 구현 인수는 기존 자료를 먼저 연결하고 필요한 사용자 경로만 확인한다.
각 행의 구체 완료조건은 같은 ID의 [상세 명세](docs/DEVELOPMENT_ITEMS.md#5-leaf-별-유한한-인도-명세)에 있다.

| ID | 사용자 결과 | 분류 | 현재 상태 | 담당 |
|---|---|---|---|---|
| B1.2.L01 | 다변수 기구·중첩 occurrence 의 마지막 native 인수 | A | 기존 구현 인수 대기 | T1 |
| B1.3.L01 | 곡면·영역별 S8 와 B32R 원출력의 지원 내 왕복 | A | 기존 구현 인수 대기 | T1 |
| B1.3.L02 | B32R native 일반화 회전·완전 지지반력·50IP 관측 완결 | D | 개발 대기 | T1 |
| B1.4.L01 | E3 적층 셸의 층별 입력·출력 | D | 구현 통합·한정 확인 완료 | post_windows_build_fix / Codex |
| B1.4.L02 | E4 온도·초기 응력/변형 상태의 native 편집 | D | 구현 중 | dynamic_reprocess_gui |
| B1.4.L03 | E5 병진·회전 spring/damper | D | 구현 통합·한정 확인 완료 | inverse_delivery / Codex |
| B1.4.L04 | E6 조임→길이 유지→사용 하중 | D | 구현 통합·한정 확인 완료 | dynamic_reprocess_gui / Codex |
| B1.5.L01 | C1 진짜 hard 접촉 | D | 구현 중 | inverse_delivery |
| B1.5.L02 | C2 implicit cohesive 와 압축 재접촉 | D | 개발 대기 | T2 |
| B1.5.L03 | C3 곡면·모서리·연쇄 tie 조정 | D | 개발 대기 | T2 |
| B1.5.L04 | C5 단계 활성과 접합 해제의 native 상태 연속 | D | 개발 대기 | T2 |
| B1.5.L05 | C4 small/large sliding 과 실제 법선·쌍 교환 | D | 개발 대기 | T2 |
| B1.5.L06 | C6 병진·회전 주기 경계의 지원 내 인수 | A | 기존 구현 인수 대기 | T2 |
| B1.6.L01 | 새 implicit 조합의 pair 장·합력·기준점 모멘트 | D | 개발 대기 | T2 |
| B1.6.L02 | 기존 J2+기하+linear/Coulomb 접촉 사용자 인수 | A | 기존 구현 인수 대기 | T2 |
| B1.6.L03 | S2 Code_Aster 사용자 모델의 비선형 실행 | D | 개발 대기 | T2 |
| B2.1.L01 | U/V·밀도·감쇠의 실제 초기 상태 | A | 기존 구현 인수 대기 | T2 |
| B2.2.L01 | 정적 preload→동적 상태 carry | A | 기존 구현 인수 대기 | T2 |
| B2.3.L01 | 시간 stream·부분 실패·명시 재후처리 | A | 기존 구현 인수 대기 | T2 |
| B2.4.L01 | Windows WRITE→READ 실제 restart | A | 기존 구현 인수 대기 | T2 |
| B2.5.L01 | 계층 INP 의 기존 flat 물리 범위 합류 | D | 개발 대기 | T2 |
| B2.5.L02 | native RAD 의 LAW36/INIEVO·LAW117 명시 편집 | D | 개발 대기 | T2 |
| B2.6.L01 | LAW36/INIEVO 실제 손상·삭제·에너지 인수 | A | 기존 구현 인수 대기 | T2 |
| B2.6.L02 | LAW117 부분 손상 unload–compression–reopen | D | 개발 대기 | T2 |
| B2.6.L03 | 완전 삭제 후 bulk-face 재접촉·재개구 | D | 개발 대기 | T2 |
| B2.6.L04 | pair force·표본 impulse·질량·에너지의 최종 선택 연결 | A | 기존 구현 인수 대기 | T2 |
| B2.6.L05 | 기존 ε–N·SWT·critical-plane 피로의 실제 작업 인수 | A | 기존 구현 인수 대기 | T2 |
| B3.1.L01 | 실제 ParaView 주창·선택 설정의 OS 작업 인수 | A | 기존 구현 인수 대기 | T3 |
| B3.1.L02 | managed ParaView 저장·File→Exit 네 경로 | A | 기존 구현 인수 대기 | T7 |
| B3.2.L01 | 네 원응력→공통 Cauchy 비교 | A | 기존 구현 인수 대기 | T3 |
| B3.2.L02 | 변형률의 유한한 측도 비교 | D | 구현 통합·한정 확인 완료 | native_post_delivery |
| B3.2.L03 | TET/HEX 고차 공간 비교 | D | 개발 대기 | T3 |
| B3.3.L01 | 고차면 측정 | D | 본코드 통합·한정 확인 완료, OS 직접 인수 별도 | vtu_boundary_refactor |
| B3.3.L02 | 다중 block 측정·원 leaf 복귀 | D | 개발 대기 | T3 |
| B3.3.L03 | 실제 현재 형상 면적·법선으로 측정 | D | 개발 대기 | T3 |
| B3.4.L01 | 원 결과 복구·변경 branch·정확한 원 선택 반환 | A | 기존 구현 인수 대기 | T3 |
| B4.1.L01 | 처리 recipe·재표본 계보·큰 Data 작업 인수 | A | 기존 구현 인수 대기 | T4 |
| B4.2.L01 | 단축·동축 유한변형 관측→같은 측도 예측 | A | 기존 구현 인수 대기 | T4 |
| B4.3.L01 | 혼합 F/stress 제어의 법칙별 인수 | A | 기존 구현 인수 대기 | T4 |
| B4.4.L01 | 후보 상세 보존·새 평가·채택 충돌 | A | 기존 구현 인수 대기 | T4 |
| B4.5.L01 | 사례 A: 기존 J2 와 DP 의 같은 물리시험 비교 | A | 기존 구현 인수 대기 | T4 |
| B4.5.L02 | 사례 C 의 다영역 열·점탄성 FE 경로 | D | 별도 후보 미통합, 연구 요구 미완료 | 미배정 |
| B5.1.L01 | 혼합변수 DOE 의 실제 domain binding | A | 기존 구현 인수 대기 | T5 |
| B5.3.L01 | 일반 역해석의 고정 관측·feasible 후보 왕복 | A | 기존 구현 인수 대기 | T5 |
| B5.4.L01 | 필수 사례별 미분법 선택·기존 adjoint 인수 | A | 기존 구현 인수 대기 | T5 |
| B5.6.L01 | 보존 대리모델·다목적·Picard/MDO 한 정의 | A | 기존 구현 인수 대기 | T5 |
| B6.1.L01 | 사용자 MFront→한 실제 FE interface | D | 개발 대기 | T4 |
| B6.1.L02 | 구성식 increment·접선·FE IP 원값 인수 | A | 기존 구현 인수 대기 | T4 |
| B6.2.L01 | 독립 PDE 의 선언 모델별 입력·실제 해·재개 | A | 기존 구현 인수 대기 | T5 |
| B6.3.L01 | 변위 vector → 구조 Dirichlet port | D | 개발 대기 | T5 |
| B6.3.L02 | 초기 응력 tensor port | D | 개발 대기 | T5 |
| B6.3.L03 | CCX 고정 지지 RF 에서 다른 C3D10 경계로 보존 하중 전달 | D | 구현 중 | post_windows_build_fix |
| B6.3.L04 | 기존 P1 온도에서 3D 이중층·계면까지 | D | 미완성 실험 제품 경로 제거, native 수신기 미구현 | 미배정 |
| B7.1.L01 | 문헌 원문·독립 Study·판단 보존 | A | 기존 구현 인수 대기 | T6 |
| B7.2.L01 | 기존 3 역할 Expert 의 중단·한도·부분응답 재개 | A | 기존 구현 인수 대기 | T6 |
| B7.3.L01 | B−A 비교 불확실성 | D | 구현 통합·한정 확인 완료 | connector_code_review |
| B7.4.L01 | 기존 robust/DE 최종 perturbation→다음 시험 | A | 기존 구현 인수 대기 | T6 |
| B7.5.L01 | 실제 3D 장면·판단·수치가 들어간 한 보고서 | A | 기존 구현 인수 대기 | T6 |
| B7.6.L01 | 장비 없이 닫는 공통 취득·sequence·종료 소프트웨어 | D | 본코드 통합·한정 확인 완료, 실장비는 L02 | pending_acquisition_integration |
| B7.6.L02 | 실제 장비 한 종류의 binding·권한·물리 stop 인수 | E | 외부 입력 대기 | T6 |
| B8.1.L01 | 모든 독립 앱·파일의 정확 owner 열기 | A | 기존 구현 인수 대기 | T7 |
| B8.2.L01 | 여러 owner 의 편집·부분저장·복구초안 | A | 기존 구현 인수 대기 | T7 |
| B8.3.L01 | 이동 사본 전체 선언 문서의 cold 편집 | A | 기존 구현 인수 대기 | T7 |
| B8.4.L01 | 외부 batch·remote 공통 소프트웨어 계약 인수 | A | 기존 구현 인수 대기 | T2 |
| B8.4.L02 | SSH 직접 실행 실제 승인 호스트 인수 | E | 외부 입력 대기 | T2 |
| B8.4.L03 | Slurm 실제 승인 호스트 인수 | E | 외부 입력 대기 | T2 |
| B8.4.L04 | OpenPBS 실제 승인 호스트 인수 | E | 외부 입력 대기 | T2 |
| B8.5.L01 | 연결 graph/list·관계 수정의 실제 GUI 왕복 | A | 기존 구현 인수 대기 | T7 |
| B8.6.L01 | 새 Windows PC 설치·native 발견·소스/라이선스 폐쇄 | A | 기존 구현 인수 대기 | T7 |
| B8.6.L02 | GUI/CLI/Python/MCP 동일 명령·owner | A | 기존 구현 인수 대기 | T7 |
| B8.6.L03 | 전체 앱의 종료 가능한 실제 사용 동선 | A | 기존 구현 인수 대기 | T7 |

## 다음 행동

1. 최신 요청의 Astra 독립 결과와 새 실제 Pro 진단을 회수·대조하고 확인한 원인과 권고를 사용자에게 설명한다.
2. 이 진단 요청을 새 GUI 작성·일곱 기능 병렬 개발·범용 리팩토링의 시작 지시로 확대하지 않는다.
   기존의 일곱 인도 자동 재개 문구는 현재 배정과 충돌해 이 목록에서 제거했다. 원 개발 요구와
   지원 범위는 DEVELOPMENT_ITEMS에 남아 있으며 완료·취소로 바꾸지 않는다.
3. 결과와 확인 한계를 기록하고 검토한 문서 변경만 커밋·게시한다. 사용자 미추적 자료는 제외한다.

기존 배포 미완료 사실: Windows SDK CI는 호스팅 runner 통신 단절로 실패했다. 로그 ZIP·artifact·
해당 draft release가 없어 회수/증분 재개는 불가능했다. 구체 자원 원인을 추정해 SDK를 바꾸거나
같은 긴 빌드를 자동 반복하지 않는다. stock ParaView 사용을 막지 않는다. 배포·새 PC 인수는 남는다.

## 기준 소스·보존·관련 자료

- 상세 종료목록 게시: `6de7c44`. native 세 기능 통합: `e2c2e43`.
  두 연구 기능 게시: `9c001eb`. 실제 HEAD/원격은 새 세션에서
  Git으로 확인하며, 로컬 커밋과 원격 게시를 구별한다.
- pinned upstream: `plugins/fixture_design/upstream`의
  `3e48bf6138f495299f45b1af254bfb4aaff307b8`, 변경 없음.
- 사용자 미추적 자료 `.codex-remote-attachments/`,
  `docs/images/manual/evaluation-case02-draft.png`는 보존하고 이번 커밋에 넣지 않는다.
- MoAI 실제 MCP SPEC 목록 14개를 확인했다. 기존 t3/t25 카드를 사용하며 이 문서와
  경쟁하는 별도 진도표를 만들지 않는다. 주어진 모델·무료 사용권·기존 설정을 유지한다.
- 실제 Pro 전체 원문·Astra 검토·원 자료는 `_workspace/closeout-20261016/`에 보존했다.
  공개 개발 범위는 `docs/DEVELOPMENT_ITEMS.md`이고 전달 회수 기록은 제품 결과가 아니다.
- 실제 native 한정 자료·원 실패·프로세스 정리는 각 `_workspace/native-*-delivery/`에 있다.
  `_workspace/`는 공개 배포 파일이 아니다. 필요한 공개 원 fixture·사용법은 제품 docs/tests에 둔다.
- [한국어 설치](docs/INSTALL_KO.md), [첫 사용](docs/USER_GUIDE_KO.md),
  [후처리](docs/native-project/POST_KO.md), [적층 셸](docs/composite-shell/USAGE_KO.md),
  [체결 하중](docs/PRETENSION_KO.md), [스프링·댐퍼](docs/CONNECTOR_KO.md),
  [변형률 비교](apps/research/POST_NUMERICAL.md),
  [관측 불확실성](docs/experiment_expert/OBSERVATION_UNCERTAINTY_KO.md),
  [기존 실행계획](docs/IMPLEMENTATION_DELIVERIES.md).
- 이전의 누적 상태 원문은 [보존본](docs/history/20261016-before-closeout/CURRENT_STATE.md)에
  바이트 그대로 남겼다. 그 안의 옛 담당·다음 행동·견적은 현재 작업 지시가 아니다.
  기존 실패·측정값·허용치와 유효한 계약/ADR은 해당 원기록을 계속 따른다.
