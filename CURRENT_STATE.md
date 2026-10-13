# 현재 작업과 제품 상태

갱신: 2026-10-13. 이 파일이 현재 사실·맡긴 작업·다음 행동의 유일한 원본이다.
제품 목표는 [PRODUCT_PLAN](docs/PRODUCT_PLAN.md), 상세 기능은
[PRODUCT_UI_MCP_PLAN](docs/PRODUCT_UI_MCP_PLAN.md), 역할·갱신 규칙은
[CODEX_WORKFLOW](docs/CODEX_WORKFLOW.md)를 따른다.

## 현재 결정과 맡긴 작업

**기획·Qt 시제품을 바탕으로 본제품의 기능 단위 구현에 착수한다.** 사용자의
“왜 말만 하고 아무것도 안 하고 있는 것처럼 보이지?”와 시작 주체에 대한 후속 지시를
작업 진행 권한으로 받아 다음 별도 문구를 기다리지 않는다. 제가 과제를 배정·시작·검증·
통합하며 MoAI는 제가 사용하는 SPEC·작업 관리 도구다. 기존 전체 배정은 운영 지침의
충돌 정리, 전체 개발 명세·작업 목록, 편집 가능한 작업/화면/상태 설계와 상호작용 시안,
Qt 조작 확인, 실제 Pro 작성과 Astra 독립 검토다. Windows 로컬 Qt/PySide6·FreeCAD·
ParaView와 추가 지출0원을 유지한다. 과거 문서의 기획 완료·다음 구현은 이번 수용 근거가 아니다.

2026-10-13 사용자가 전체 명세에 따른 독립 도구·전체 연계 구현과 통합을 지속 목표로
등록했다. 각 도구는 데스크톱앱이며 이를 묶는 선택적 연결 화면은 웹 또는 데스크톱으로
제공할 수 있다. 기능 개발이 우선이고 개별 도구는 실행 가능 여부와 필요한 단위 검사만
확인한다. 넓은 통합·수치 검증은 관련 구현 이후다. 미완료 기능이 있으면 같은 작업을
계속하며, 작은 검토·교정마다 재승인이나 전체 solver 검증을 기다리지 않는다.

최근 사용자 지시는 CAD/전처리→solver/Runner→native Post→최적화와 Co-STORM 연구의
독립 작업·도구 연결을 중심으로 완성하는 것이다. Material 예시를 전체 우선순위로 확대하지
않으며 그 교정이 다른 도구를 기다리게 하지 않는다. Data/Material/PDE/Numerical/Runner/
Expert/Study·선택 Workbench와 넓은 물리·수치 범위는 그대로 유지한다.

이전 설명문·보조 기능이 많은 Qt 폼은 **사용성 미수용 초안**으로 보존했다. 새 Qt 시안은
모델·표·곡선과 선택한 작업을 중심으로 교정해 **사용자 검토본**으로 통합했다.
[화면과 시제품 검토](docs/design/20261012-desktop-planning/REVIEW_GUIDE.md)에서 시작한다.
설계 작성·통합, 사용자 화면 수용과 제품 구현 완료는 구별한다. 사용자 화면 피드백은
구현 중에도 반영하며 시제품을 본제품으로 복사하거나 합성 계산을 실제 계산으로 바꾸지 않는다.
최신 사용자 설명: **“그냥 물어본건데 혼자서 잘못한걸 찾네. 제발 전체 과제 맥락에서
유기적으로 생각해. 독립 프로그램으로도 사용가능하지만 전체 시스템에서 연계도 되어야해.”**
Codex는 앞선 중립 질문을 결함·재설계 요구로 확대해석한 것을 바로잡았다. 현재 목표는
각 독립 도구의 직접 사용과 모델→해석/Runner→Post→응답→최적화→설계 적용,
Expert→계획→결과 근거→후속 논의/Study의 전체 연결을 함께 설명·설계하는 것이다.
Workbench는 선택적 연결 보기이며 강제 진입점이 아니다. 기존 시제품·조작 검사·기능
명세를 재사용한다. 독립 사용과 전체 연결을 함께 구현한다.
같은 실제 Pro의 `UX-REVIEW-CLARITY-01`에 최신 사용자 원문과 해석 교정을 전달했다.
Pro `5b9ae1c`의 DESIGN/README 교정을 확인해 통합했다. 내용은 독립+전체 연계의 맥락
설명이며 추가 결함 찾기나 별도 재설계 과제가 아니다. Qt 소스·시안·기능/작업표·조작
검사 상태는 유지했다. MoAI SPEC 조회와 실제 Pro 연결을 다시 확인했다.

첫 제품 작업 `PRO-IMPL-DESKTOP-20261013-01`의 Windows 기본 데스크톱 진입과 기존
문서·서비스를 사용하는 독립 도구 실행을 구현·검증했다. 기본 browser Workbench
진입을 기존 native Qt Runner로 바꾸고 각 Research 도구에 직접 들어간다. CLI/direct
native Pre/Post와 공유 저장소를 재사용하며 새 문서·서비스를 강제로 만들지 않는다.
Luna는 시작·서비스 수명, Sol은 Numerical/Expert의 실제 명령 연결을 읽기 전용 조사했다.
실제 Pro가 제품 코드·테스트를 주작성하고 Astra가 독립 설계·코드 검토를 맡는다.
다음 기능 단위는 기존 Numerical Plan의 변수·응답·방법 중심 편집과 Expert/Study의
정확한 결과 왕복이다. 전체 제품을 첫 진입 기능으로 완료 처리하지 않는다.
사용자는 긴 제목·파일명에
`• r2` 등 내부 접미사를 이어 붙이는 표시를 싫어한다. 주 화면은 짧은 작업명·값·단위·선택·
상태·다음 조작을 보여주고, 정확한 원본/개정/실패는 이력·근거·진단에서 조회한다.
이미 지정한 FreeCAD/ParaView/HyperStudy/Co-STORM/Origin/MCalibration/COMSOL 원형은
[PRODUCT_PLAN §3](docs/PRODUCT_PLAN.md#3-화면마다-주-기준을-고정한다)을 따른다.
참고 이미지를 사용자에게 요청하지 않는다. 세부 화면 시안은 검토용 제안이며 사용자 결정과 구별한다.

첫 구현 전 제품 source는 `9a6e3083037630b45694b812b135dc1cd63cf95a`, upstream은 아래 핀이다.
첫 제품 코드·테스트는 실제 Pro `9d6d780`을 통합해 Windows에서 확인했다.
solver/provider 실행은 시작하지 않았다. 사용자
`.codex-remote-attachments/`와 기존 설정·AGENTS를 보존한다.

### 실제 Pro 원고와 검토

실제 Pro/GPT-6·power5/5를 UI에서 확인하고 원문 요구·기준 source를 전달했다.
[원 D1 대화](https://chatgpt.com/c/6acca3ab-15b0-83ee-8ca3-25ff00e335c5)의
[기능·구현 명세](docs/design/20261012-desktop-planning/pro-authored/README.md)를 회수했다.
이 원고는 전체 제품 설계의 자료이며 새 GUI 수용을 대신하지 않는다.
같은 [실제 Pro 대화](https://chatgpt.com/c/6accef3a-e650-83ee-89e2-3f48a60dd17a)에 첫 제품
구현 요청 `PRO-IMPL-DESKTOP-20261013-01`을 전달하고 수신을 확인했다. 작성 브랜치는
`codex/desktop-tools-20261013`, 기준은 `c2e506b`다. Pro는 시작 스크립트·최소 desktop
진입 연결·관련 테스트/사용 안내를 소유하고 Codex는 현황/SPEC/통합을 소유한다.
앞선 기획 요청06의 소유권은 `pro-ux/`, 작성 브랜치는 `design/product-ux-20261012`였다.

최종 Qt view와 상태/도면 연결은 Pro `dd43015`다. Report/Acquisition 추가 `600f9f8`,
문서/작업 대응 `a2e20b8`, scatter 교정 `0b9da54`, 정확 선택/출력 교정 `9e313e5`를 포함한다.
최종 검사 helper 두 줄과 Pro의 Windows 인계 기록은 `20291b3`으로 회수했다.
CAD/FE·Simulation·Runner·Post·Numerical·Expert·Study와
Data/Material/PDE/Evaluation/선택 Workbench의 Qt 창을 실제로 렌더링했다.
[GUI 실제 검토](docs/design/20261012-desktop-planning/GUI_REVIEW.md)에 source별
Pro 작성, Astra/xhigh 독립 검토, Sol/high의 실제 입력 검사와 Codex 통합 확인을 구별한다.
지수 입력·Undo/Redo·잘못된 입력의 보존/실행 차단·수정, 새 연구 계획의 변수/응답 정의,
Post의 시간/필드 연동과 CAD→Simulation→Runner의 합성 결과→Post→MOO 명시 적용/
개별 저장→저장 실패 재시도→새 창 재열기를 확인했다. 실제 계산이나 engineering 승인이 아니다.

Astra의 `48cbac3` 재검토는 스케치 선 삭제, saved 자세/instance·비교 형상,
selected step, inverse train/holdout 및 방법별 결과→후속 논의의 잔여를 찾았다.
같은 Pro에 UX-FIX-04로 전달했고 최신 core의 집중 Qt 검사에서 sketch 보존·saved 형상/
selected step·Post ordinary file 재열기·방법별 결과→Expert→Study 경로를 확인했다.
상태 SVG/JSON과 작업 흐름 drawio, 기존74task의 새 화면 연결을 회수했다.
Astra의 최종 changed-path 검토는 step 이름 변경 시 입력 유실, 같은 결과의 발언별
locator 혼합, Numerical 기능/화면 대응 오류를 찾았다. UX-FIX-06/UX-MAP-01로 같은 Pro에
교정을 맡겼다. Luna의 독립 대응 검토는 FN-01/32/34/35의 전용 경로·기존 상세 계약 참조가
불명확한 것을 찾아 UX-MAP-02로 전달했다. 원74task/기존열·52요구 상태는 유지됐다.
Windows 글꼴과 Post 비교값 잘림은 UX-FIX-05/UX-VISUAL-01로 교정됐고 정상 글자와
0.31/0.29mm 첫 표시를 실제 렌더에서 확인했다. 무료 기존 폰트를 읽으며 배포하지 않는다.
`049bbbc`의 입력/발언 근거 두 문제는 root 실제 Qt 검사와 Astra 독립 재현에서 해소됐다.
`60a4fab`의 task/state 대응 교정은 Luna의 제한된 재검토로 확인됐다.
Pro의 원격 Linux 실행 환경이 끊겼으나 GitHub 연결로 Report/Acquisition 소스를 계속
주작성·게시했다. root Windows에서 새 4상태의 실제 Qt 렌더를 확인했다. Sol/high는
PDF/Markdown·보고서 일반 저장/cold reopen, 채널 Cancel/단위변환/표곡선/부분입력 차단/
저장/cold reopen과 unavailable live guards를 실제로 확인했다. Astra는 구조·시각을 검토했다.
선택 .02s 보고서가 끝 .04s 값 .31을 쓰는 오류, 미리보기 페이지와 source 열기 불일치,
출력 근거 참조·F05 역사 적용범위·Use Study 교체·Acquisition 종료 표시를 같은 Pro에
UX-REPORT-FIX-01/02로 전달했다. `9e313e5` 교정은 독립 Sol/high의 정확 시각/출력/
Cancel/Undo/cold reopen과 Astra/xhigh의 페이지/출처/역사 적용범위/6행 표시 검사에서
닫혔다. `dd43015`의 supported gauge·Surface 복원/overflow 이동은 Sol 제한 소스 검토와
root Windows의 변경 경로 Qt 검사에서 확인했다. 숫자 delegate로 보였던 검사 실패는
offscreen 모달 종료 뒤 검사 창 활성화 누락이었다. 기존 delegate는 생성됐고 올바른
창 활성화 뒤 부분 입력·수정·저장/재열기가 작동했다. root는 ignored 검사 사본의
포커스만 보완했으며 제품 작성자로 대체하지 않았다.

최종 56상태 SVG와 화면 미리보기는 같은 Pro 소스를 root가 Windows Qt에서 재생성했다.
같은 원본의 네 작업 흐름 페이지를 draw.io Desktop에서 export했고 PDF의 정확 .02s/
.2294mm 표·곡선·글자·출처를 Poppler로 렌더해 확인했다. 실행 안내, 전체 명세/작업표,
MoAI 인계와 연결해 검토본으로 저장했다. 숫자는 합성 예시이며 실제 계산 통과가 아니다.
최종 전달의 Git 게시 결과와 사용자 수용을 구별한다.

Edge 연결 소실 후 공식 task 조회로 요청06과 원 UI의 같은 turn을 대조해 후속 연결을
복구했다. 작성 task는 `01a13087-154b-7343-ad70-1f882d9fc0af`/durable,
turn은 `01a13087-26c6-7536-b617-db0dbef22557`다.
공식 전송 뒤 수신 userMessage의 UX-FIX-04/05/06, UX-MAP-01/02,
UX-VISUAL-01/UX-COMPLETE-01 본문·끝 경계를 확인했다.
새 모델·유료 API 또는 다른 작성자로 대체하지 않는다. 최신 사용자 요구와 실제 원고의
전달 요약은 [PRO_UX_REQUEST](docs/design/20261012-desktop-planning/PRO_UX_REQUEST.md)다.
Space 제품 입구에도 GUI/우선순위 결정과 같은 Pro/Qt 링크를 반영·재조회했다.
기존 과거 원문·ZIP 참조를 보존하며 현행 상태의 원본은 이 파일이다.

### 도구와 실제 확인 범위

MoAI `3.2.0-dev.2aab5f7`의 공식 Codex 초기화를 분리해 확인한 뒤 필요한 설정만 병합했다.
실제 skill catalog의 MoAI5개, local stdio initialize/tools와 현재 host MCP4개를 확인했고
이번 재개에서도 `spec_progress`로 SPEC을 조회했다. [기획 SPEC](.moai/specs/SPEC-DESKTOP-001/spec.md)은
기능·화면·작업표·수용 조건에 연결하며 현재 큐를 중복하지 않는다. strict lint는 구조 검사이며
사용성 통과가 아니다. hook trust는 미확인이다. CLI0.146.1의 기존 global context_management
map 호환 오류는 read-only 검사에만 임시 override를 사용했고 사용자 설정을 덮어쓰지 않았다.
첫 제품 구현은 [SPEC-DESKTOP-002](.moai/specs/SPEC-DESKTOP-002/spec.md)에 연결했다.
Astra의 독립 검토에서 모드별 서비스 준비/UI 억제, PrepareOnly 실패의 비대화형 처리,
새 runtime의 ResearchUI 설치를 명시했다. CMD pause·축약 옵션·환경 경계와 실제
WinPS 5.1 readiness 인수 손상을 같은 Pro가 교정했다. 실제 기본 CMD의 native Runner
창, 저장된 Data ID의 native 창과 같은 서비스 PID 재사용을 확인했다. 관련 진입·
Windows 경로·native argv 검사가 통과했고 source guard가 기존 서비스를 유지하는
오류 경로도 확인했다. 정확한 소스·대역/실제 실행·잔여 한계는
[진입 기능의 검증 기록](.moai/specs/SPEC-DESKTOP-002/acceptance.md)에 있다.

기존 사용자 Python3.13에는 PySide6 6.9.1·Matplotlib3.10.1·Designer와 Qt SVG가 있다.
앞선 기존 Research runtime의 PySide6 미설치와 별도로 이번 진입 검증용 private
runtime에 프로젝트의 Qt 의존성을 설치했다. 새 D1 Qt 프로세스/접근성 구조는 확인했지만
창 활성화 실패와 검은 캡처 때문에 native 입력을 중단했다. Segoe UI offscreen 렌더링·
QTest의 범위만 기록한다. 이전 [Qt spike 검토](docs/design/20261012-desktop-planning/QT_REVIEW.md)의
CSV/저장 chooser·선택·채택·Undo/Redo·dock Float·새 프로세스 재열기 근거가 새 D1을 대신하지 않는다.
앞선 제한된 경로 검색 이후 `runs/prepost-session-20261008-01/tools`에서 기존 portable
FreeCAD1.1.4와 ParaView6.2.0을 찾았다. 새 설치 없이 ParaView의 실제 pvpython으로 공개
합성 3시각 자료의 한 점 시간 측정을 Apply·sample·저장했다. 실제 표의 Time은 0/.5/1s,
명시적으로 고른 `avg(U (2))`는 0/1/2mm다. 이 자료는 새 Post→Numerical 연결 확인용이며
solver 계산·native 마우스 조작·공학적 검증이 아니다. FreeCAD는 실행 파일 존재만 확인했다.
정확한 경로·재사용 자료는 [Post 연결 실행 준비](.moai/specs/SPEC-POST-NUMERICAL-001/acceptance.md#native-input-prepared-on-windows)에 있다.
이 실행 파일 둘을 기존에 없던 사용자 `LOCALAPPDATA/AutonomousCAELab/workbench-config.json`의
desktop 설정에 연결했다. 다음 서비스 시작부터 적용하며 열린 서비스/문서는 중단하지 않았다.
소유한 개발 runtime에는 기존 `install-windows.ps1 -ResearchUI -Documents`로 프로젝트에
고정된 pypdf6.10.0을 추가해 PDF reader import를 확인했다. BSD 라이선스 원문을 확인했으며
provider 설정·인증·추가 비용은 없다. 실제 Expert 파일 가져오기는 다음 구현에서 연결한다.

draw.io Desktop32.4.1의 기존 portable 무료 도구로 Codex의 소유권·상태 도면을 열기/export했다.
Pro 계약에서 작성한 [전체 연결 원본](docs/design/20261012-desktop-planning/research.drawio)은
CAD/FE 준비·실행/Post·최적화/채택·Co-STORM/Study 경로를 연결하며 CLI export/렌더링을 확인했다.
프로그램 화면 또는 solver 실행의 대체물이 아니다. Desktop 해당 버전 라이선스는 GPLv3로 교정했다.
Penpot은 계정이 없어 제외하라는 사용자 결정으로 닫고 무시하며 계정·편집·export를 완료 gate로 두지 않는다.
[무료 도구 기록](docs/design/20261012-desktop-planning/TOOLS_AND_LICENSES.md)을 따른다.

주 Codex는 사용자 변경 이후 실제 실행 기록에서 Sol/xhigh를 확인했다. 변경 전 Sol/high
기록을 소급 변경하지 않는다. 핵심 독립 검토 Astra/xhigh, bounded 코드 Sol/high,
코드 조사 Luna/high를 사용했다. 실제 Pro UI 설정과 Codex의 추론 수준은 별개다.
브라우저의 기존 대화 회수 장애를 공식 파일/저장소 작업 전체의 금지로 확대하지 않는다.
수동 다운로드 요청은 공식 회수 경로가 동작한 뒤 철회했고 추가 사용자 조작을 기다리지 않는다.

### 이어서 할 작업

첫 진입 기능은 원격 main에 반영했다. 실제 Pro `39c5fb0`의 Numerical 변수·응답·방법
편집과 원래 Expert/Study 결과 전달, `43ef92f`·`433d681`의 교정을 로컬 `d010303`까지
통합했다. 컴파일과 작은 실제 DOE·최적화, 정밀/부분 입력 저장·재열기를 확인했다.
첫 fixture의 5초 제한 초과, Expert 소켓 응답 실패와 Windows venv PID 가정 오류는
보존했다. Pro가 같은 프로세스의 결과 전달을 GUI 스레드에서 처리하도록 고쳤고
Expert/Study/독립 대상 선택/이전 결과 선택 4개 단위 검사가 통과했다. 별도 프로세스의
실제 Qt 창에 Attach하고 기존 편집을 보존하는 검사도 통과했다. 실제 desktop 진입에서
1440×900 generic worksheet Qt 렌더를 확인했다. 검사별 소스·한계는
[Numerical 구현 기록](.moai/specs/SPEC-NUMERICAL-001/acceptance.md)에 둔다.
이 단위의 기본 실행을 확인했으며 전체 제품 수용·넓은 통합 검증은 아직 남아 있다.
Astra/xhigh의 좁은 소스 검토에는 새 blocking/data-loss 지적이 없었다. 실행 결과와는
별개이며 표시 개선 두 건은 후속 UX로 남긴다. Codex가 Windows 실행·통합을 맡는다. 열린
원 창의 미적용 편집을 보존하고 pending 결과를 사용자 확인 후 추가해야 한다.
같은 문서를 새로 열거나 새 X/S를 만들며 왕복 완료로 표시하지 않는다.
원 구현 요청은 `PRO-IMPL-NUMERICAL-20261013-01`, 작성 브랜치는
`codex/numerical-workflow-20261013`, 기준 main은 `edcc1fb`다.
범위와 완료 조건은 [SPEC-NUMERICAL-001](.moai/specs/SPEC-NUMERICAL-001/spec.md)에 연결한다.
첫 진입 기능과 배정 기록은 원격 main `c6e7f2e` 게시 후 같은 SHA를 확인했다.
Luna/high가 기존 native CAD/FE→Runner→Post 연결과 Post→Numerical의 빠진 연결을
읽기 전용으로 조사했다. 같은 Pro에 `PRO-IMPL-POST-NUMERICAL-20261013-01`을 전달했다.
Numerical 교정 커밋 후 `codex/post-numerical-20261013`을 만들고 저장된 Post 측정의
실제 표·곡선을 Numerical 관측/응답으로 가져와 편집·저장·재열기하는 제품 기능을 작성한다.
원래 native 편집기·JobManager·Data/evaluation/Numerical owner를 재사용한다. 기존 Plan의
미적용 편집을 보존하며 새 후보 계산과 측정값 가져오기를 구별한다. shared Core 변경은
Codex가 통합하며 같은 소스의 작성자는 Pro 한 명이다. 범위는
[SPEC-POST-NUMERICAL-001](.moai/specs/SPEC-POST-NUMERICAL-001/spec.md)에 연결했다.
Pro `f313bb1`의 backend와 `1456e29`의 Qt 선택·관측 화면, 문자열 손상을 고친 `4563ec8`을
로컬 `7325175`까지 통합했다. 처음 UI 소스는 문법 오류로 collection 실패했고 같은 Pro가
즉시 교정했다. 변경 경로 검사 6개가 통과했고 실제 native 자료를 넣은 1100×780 Qt
대화상자의 표·곡선·선택 연동을 렌더로 확인했다. 앞선 ParaView6.2 owner의 실제 측정 추출과
UI의 native transport 대역은 구별한다. Astra가 지적한 물리 선언·무효 행 품질 두 문제도
교정 소스에서 해소됐다. 확인 범위와 원 실패는 SPEC의 acceptance에 남긴다.
같은 대화상자에서 기존 Plan을 직접 선택하고 미적용 편집에 관측값만 검토 후 추가하는
경로도 Pro `3d730ff/f015825/f966b52`를 로컬 `0759f86`까지 통합했다. 처음 테스트 대역이
Numerical 문서 읽기를 잘못 거절했으나 Pro가 실제 Workbench 위임으로 교정했다.
Astra가 찾은 검토창 중 자동 갱신 경합과 프로세스 생성 전 실패 뒤 재시도 차단도
교정했다. Root의 최신 변경 경로 4개 검사는 6.24초에 통과했다. 실제 Qt 검토창에서
자동 갱신 중 Cancel/Append, 기존 편집·명시 저장·중복 전달, 실행 실패 후 재시도를
확인했다. native transport는 명시적 대역이며 실제 OS 입력/전체 native 왕복은 아직이다.
짧은 행 표시의 제품 Qt 렌더도 확인했다. SPEC은 implemented이며 전체 제품/공학 수용은
아니다. 기존 실패와 정확한 확인 범위는 acceptance에 보존했다.
MoAI MCP의 실제 SPEC 조회와 CLI의 상태 갱신·해당 SPEC lint를 사용했다. lint의 구조
오류는 수정했으며 표에 연결한 수용 조건을 인식하지 못한 coverage 등 경고는 남아 있다.
문서 lint 결과를 실제 제품 기능이나 테스트 통과로 바꾸지 않는다.
추가 MoAI `ast-grep` 호출은 실행기와 검사 규칙이 없어 실제 scan NOT_RUN이었다.
도구 목록의 존재를 검사 실행으로 기록하지 않으며 개발을 멈추는 조건으로 삼지 않는다.
이어지는 Expert 작업은 [SPEC-EXPERT-001](.moai/specs/SPEC-EXPERT-001/spec.md)의 로컬
자료 가져오기·선택·본문/인용 열기다. Luna/high가 기존 역할·개입·저장·Plan 연결을 확인했고,
Codex가 첫 파일 가져오기와 선택한 문서/개정의 검색·위임 경계까지 범위를 보완했다.
`PRO-IMPL-EXPERT-20261013-01`을 같은 실제 Pro 대화에 전달했고 실제 userMessage
`01a1339c-bc53-773b-b783-4d0c7729cf5e`에서 수신을 확인했다. Post 교정 커밋 후
별도 재승인 없이 Expert를 작성하도록 맡겼다. SPEC은 in-progress이며 작성 브랜치는
`codex/expert-sources-20261013`이다. 기존 KnowledgeStore와 문서 owner를 재사용하고 무료 inference가
실제로 가능한지는 별도 확인한다. 자료 선택·저장은 provider 연결을 기다리지 않는다.
Pro의 첫 자료 연결 커밋 `7090d1c`를 `c409665`로 통합했다. 선택한 문서의 정확한
개정 읽기·검색, 논의 이력·하위 전문가·OpenScience의 같은 선택 범위와 파일 업로드
클라이언트를 포함한다. Astra/xhigh는 변경 8개 파일을 독립 소스 검토해 실질적 결함을
찾지 못했다. Codex의 `tests/test_expert_sources.py`는 Windows에서 4 PASS/5.42s였다.
모델/호스트는 명시적 검사 대역이며 실제 inference는 실행하지 않았다.
이어 Pro `5037e46`의 파일 선택·본문 미리보기·첨부 화면을 `1170af4`로 통합했다.
실제 loopback HTTP/자료 저장소를 쓰는 Qt 검사4개가 6.57s에 통과했고 새 legacy 이력
검사도 1 PASS/1.75s였다. 종료 후 남은 worker의 Signal source deleted 예외는 같은 Pro에
교정 요청했다. 공개 Markdown/text PDF/CSV3개를 실제 import한 Qt 렌더에서도 원문과
질문·자료3개가 보였다. 다만 재열기 직후 원문 읽기와 제목 조회가 겹쳐 Source1/2/3으로
남는 문제, Astra가 찾은 주기 갱신 때 선택 해제와 다른 논의에 이전 원문이 남는 문제도
같은 Pro에 전달했다. Pro `5d6b970`을 `e1903e6`로 통합했고 자동 갱신·원문/과거 인용·
문서 전환·늦은 worker 종료를 포함한 수정 Qt 검사4개가 6.50s에 통과했다. 종료 예외도
재발하지 않았다. 최신 `expert-preview-886155b1`의 실제 Qt 렌더에서 자료3개의 파일명과
선택 원문을 확인했다. 교정 종료는 Codex의 소스/실행 확인이며 Astra 재통과 주장이 아니다.
MoAI CLI로 로컬 자료 기능 SPEC은 implemented, 후속 접촉 SPEC은 in-progress로 갱신했다.
`runs/product-development/20261013/expert-preview-63bea349`에 실제 화면/receipt가 있다.
모델 미설정 상태의 로컬 자료 작업이며 실제 inference/OS 입력을 확인한 것은 아니다.
첫 렌더 helper는 등록 역할이 반드시 있다고 잘못 가정해 대기했고, 그 가정만 제거한 뒤
정상 렌더했다. 제품의 역할 목록을 가짜로 채우지 않았다. Expert 전체 완료는 아직이다.
MoAI sync의 SPEC/코드 차이 대조와 관련 문서 갱신 절차를 적용했다. 전체 자동 sync나
추가 모델 호출을 실행한 것으로 표시하지 않으며, 기존 사용자 지시대로 변경 경로만 확인한다.
후속 CAD/FE 접촉 조사에서는 native 면 선택·참조 복구는 있으나 사용자 모델의 접촉쌍과
일반 solver 전달이 없는 점을 확인했다. 고정된 Code_Aster 기준 예제를 사용자 모델 경로로
대체하지 않는다. FN-14의 접촉 편집부터 solver/Post 결과까지 전체 요구는 계속 미완료다.
이를 [SPEC-CONTACT-001](.moai/specs/SPEC-CONTACT-001/spec.md)에 후속 구현으로 구체화했다.
기존 FreeCAD contact 객체·입력 작성기를 재사용하고 여러 면·마찰·간극·참조 수리와
Runner/Post 결과까지 연결한다. 별도 설정의 FreeCADCmd로 공개 합성 두 박스의 접촉 객체를
생성·FCStd 저장·재열기해 면 참조 보존을 확인했다. 메시·solver는 실행하지 않았으며
제품 접촉 UI/계산 구현은 아직이다. 전체 작업표의 여섯 진행 상태만 실제 부분 구현에 맞췄다.
후속 Astra 검토에서 두 body의 메시/재생성, 법선·sliding·step의 실제 deck 대응이 빠진
점을 보완했다. Luna는 접촉 압력/침투/마찰 변위의 FRD와 pair 힘의 DAT를 기존 parser에
연결할 위치를 조사했다. 두 출력의 부호/association이 다르며 양수 gap은 FRD COPEN만으로
얻을 수 없어 명세에 미해결 구현으로 남겼다. 넓은 수치 검증은 선행하지 않았다.
다음 실제 Pro 요청 `PRO-IMPL-CONTACT-20261013-01`을 같은 대화에 전송했고 실제
userMessage `01a133bc-eb27-77f4-98b1-455457d0f371`의 본문에서 수신을 확인했다.
기준은 main `08ecb55`의 SPEC-CONTACT-001/FN-14/C05와 관련 기존 native 코드다.
현재 Expert 교정을 게시한 뒤 추가 승인을 기다리지 않고 사용자 모델의 접촉 편집·메시·
해석/Runner·Post 연결을 작성하도록 맡긴다. 새 작성 브랜치는
`codex/contact-workflow-20261013`; Pro가 제품 코드·관련 검사/사용 안내를 쓰고 Codex는
공유 계약 통합·CURRENT_STATE/SPEC/Windows 실행을 소유한다. 첫 접촉 편집/분리 메시
준비 코드 `e916a32`를 main `d5fdcb5`에 통합했다. 실제 FreeCAD 검사에서 preview가 원본
형상의 내부 상태를 바꿔 참조를 무효화하는 문제를 재현했고, Astra가 입력 보존·법선 비교·
suppressed 메시 처리의 세 문제를 찾았다. 같은 Pro의 `PRO-CONTACT-FIX-01` 교정
`37916e8`을 `71f3e03`으로 통합했다. FreeCAD의 형상 복사 API를 사용해 preview를 만들고
표시/취소 때 편집 중인 값을 보존한다. 수정된 접촉/Qt 검사 6건은 통과했다.
실제 FreeCAD 1.1.4에서는 공개 두 발 모델의 여러 면 선택→잘못된 초안 보존→값 수정→
두 물체의 빈 native Gmsh 객체 준비→접촉 저장/재열기까지 통과했다. 형상·접촉·메타데이터는
실제 native 객체이며 GUI 존재/선택 조회만 대역이다. 메시 생성·solver·실제 창 입력 검사는
아직 하지 않았다. 해당 기록은 `runs/product-development/20261013/contact-editor-9e3f7ed8/receipt.json`.
Pro의 export/Runner/Post 연결 `8d350ab`을 `bdc9fb9`에 통합하고 원격 main에 게시했다. 기존 native 면/하중
매핑·접촉 writer, JobManager와 FRD/VTU 경로를 확장한다. 첫 집중 검사16건은 통과했고
3건은 테스트 fixture가 Windows CRLF를 써서 실패했다. 실제 export는 LF를 명시한다.
Astra가 찾은 원 native 세션 종료 뒤 원본 열기 누락, Force 표의 이중 단위 변환,
구속면 변경 뒤 오래된 이름 기반 mesh group을 사용하는 문제를
`PRO-CONTACT-EXEC-FIX-01`로 같은 Pro에 전달했다. 교정 `b19c8f1`을 `6175e90`으로
통합했고 변경된 contact/native export/원본 이동/FEM 단위 검사66건이 통과했다. 실제
FreeCAD의 두 면100N 하중을 내보낸 결과 합력이 -Z100N으로 보존됐고, export는11.484초에
완료됐다. 근거는 `runs/product-development/20261013/contact-export-402e8ca7/receipt.json`.
교정 확인은 Codex의 소스·실행 확인이며 Astra 재검토 통과 주장은 아니다.

이 입력을 실제 CalculiX 2.22와 제품 adapter로 실행해 41.703초에 성공했다. 10개 증분의
변위·접촉 응답과 pair 힘을 읽었고 원 FRD/DAT를
`runs/product-development/20261013/contact-run-0b93d1b2/attempt/`에 보존했다.
Runner 화면을 통한 제출이나 공학적 정확성 승인은 아니다. 실제 ParaView 열기에서는
ASCII VTU의 비유한 GeomGap 값을 읽지 못하는 오류가 발생했다. 별도 native VTK 확인에서
NaN 대소문자 변경은 실패하고, inline binary Float64는 NaN/±Inf를 그대로 읽었다.
같은 Pro의 `PRO-CONTACT-POST-FIX-01` 교정 `5744079`를 `b97ae6b`로 통합했다.
변경 경로 검사10건이 통과했고, 보존된 FRD/DAT에서 별도 Post 파일만 재생성했다.
실제 ParaView는10개 프레임의 모든 PointData를 읽었으며 NaN과 유효성 배열도 보존됐다.
접촉 압력(MPa)과 정적 하중 단계1.0을 선택해 프로젝트를 저장했고 새 pvpython 프로세스에서
같은 선택과3403절점/1654요소를 복원했다. 근거는
`runs/product-development/20261013/contact-post-8096fa28/receipt.json`과 `reopen-receipt.json`이다.
원 계산과 실패한 VTU를 보존했고 솔버는 반복 실행하지 않았다. 마우스 입력이나 공학적
정확성 승인은 아니다. 다음 기능은 이 결과에서 접촉쌍·면을 선택하고 힘/간극/압력 이력을
살핀 뒤 기존 Post 측정과 Numerical로 이어가는 사용자 조작이다. Luna가 native Post의
기존 `bridge.py`/`workspace.py`, Research 측정과 `post_numerical.py`의 Plan 검토/추가
경로를 조사했다. 현재 whole-mesh PVD에는 pair별 선택이 없고 실제 pair 힘 sidecar도
화면/측정에 연결되지 않았다. `PRO-CONTACT-INSPECT-01`을 같은 Pro 대화로 전송했고
실제 사용자 메시지와 새 작업 턴 `01a1340a-8fc3-72ac-8a6e-fd2b2d7446f3`의 진행을 확인했다.
기준은 원격 main `a2ae3f6`이며 Pro의 `5744079`를 포함한다. Pro는 기존 native Post 안에서
pair/면/증분 선택과 압력·간극·힘 이력, 저장/재열기와 선택 응답의 기존 Numerical Plan
추가를 소유한다. Codex는 공통 계약/등록 경계 검토, 최소 Windows 실행과 문서 통합을 맡고
Astra는 산출물의 핵심 의미·사용자 흐름을 독립 검토한다. 새 solver 실행은 맡기지 않는다.

Pro 접촉 검사 산출물 `1edd036`~`50c7340`을 로컬 `7f27e12`~`0ddd758`로 통합했다.
변경된 contact inspection/Qt/native guard/execution 검사33건이24.75초에 통과했다.
기존 FRD/DAT에서 새 inspection bundle25개 파일을 생성·등록하고 native 프로젝트를 열었다.
실제 Show faces에서는 ParaView6.2의 `ColorBy(display, None)`가 초기 association `NONE`을
거부해 실패했다. 별도 native 확인에서 명시적인 empty POINTS association 또는
`SetScalarColoring(None, 0)`는 동작했다. Astra는 bundle 누락 시 partial restore가
제거된 overlay reader를 healthy로 검사해 복구창 진입을 막는 소스 결함도 찾았다.
같은 Pro에 `PRO-CONTACT-INSPECT-FIX-01`로 두 교정을 전송했고 진행을 확인했다.
ColorBy 오류만 우회한 별도 진단에서는 실제 접촉면·10행 힘 측정·저장이 성공했다.
제품 통과로 표시하지 않는다. 새 프로세스 재열기에서 두 Threshold의 SelectedComponent가
저장 전 빈 문자열에서0으로 바뀌는 실제 default 정규화를 추가 확인해 같은 Pro에 전달했다.
다른 graph 차이는 없었으며 생성 시 명시적 설정 등 국소 교정을 요청했다. 실제 결과를
넣은 Qt 결과 창의194개 접촉면 절점·10개 증분 표/곡선도 렌더했다. native 통신은 이 렌더의
검사 범위가 아니며 원본은 `runs/product-development/20261013/contact-inspect-bb998593/`이다.
Pro 교정 `6e22066`을 로컬 `193845a`로 통합했다. 실제 Show faces의 ColorBy 예외는
해소됐으나 native 검사 자체가 ParaView EnumerationProperty를 정수와 직접 비교해
중단됐다. 별도 native 조회에서는 SelectedComponent의 실제 원시 값이0이었다.
수정된 guard 검사9건은 통과했고 새 partial restore 검사는 UTF-8 저장 파일을 Windows
기본 cp949로 읽어 실패했다. 같은 요청의 후속으로 두 검사 코드 교정을 Pro에 전달했다.
검사 교정 `26d3b55`를 `c4fc7b4`로 통합했고 guard10건이0.68초에 통과했다.
제품을 바꾸지 않고 검사 assertion만 원시 native 속성 조회로 바꾼 root helper에서는
접촉면·10행 힘 측정·저장이 성공했다. 새 프로세스 재열기는 여전히 두 SelectedComponent의
저장 전 빈 문자열/복원0 차이로 거부됐다. native 원시 값과 enum label 표현 차이를
안정적으로 기록하도록 같은 Pro에 추가 교정을 요청했다. 입력/솔버 재실행은 없다.
추가 교정 `5cb083c`를 `b6dc2d6`로 통합했다. 접촉 overlay만 원시 integer 속성을 기록하고
기존 일반 분석의 저장 형식은 유지한다. 변경 guard17건이0.82초에 통과했다. 수정 없는
제품과 검사 스크립트로 실제 ParaView6.2의 접촉면 표시→10행 힘 측정→저장 및 별도
새 프로세스 재열기가 통과했으며 restore 문제 목록은 비어 있다. 근거는 같은 실행 폴더의
`checked-enum-inspection.json`과 그 saved 프로젝트다. 기존 실패·진단 저장본은 보존한다.
Astra의 이 공통 속성 처리 변경에 대한 읽기 전용 독립 검토는 추가 구체적 결함을
찾지 않았다. 실행 통과는 root의 결과이며 Astra 실행 주장과 구별한다. 이번 묶음은
`e7c9b32`로 원격 main에 직접 게시했고 원격 SHA 일치를 확인했다. Space의 현행 안내도
이 통합과 다음 CAD/Numerical 배정으로 갱신·재조회했다. 강제 push나 PR 우회는 없다.

병행 조사에서 다음 연결의 실제 빈틈도 확인했다. 현재 Pre 변수 등록은 길이 치수에
한정되고, 접촉 adapter는 이미 고정된 snapshot만 실행한다. 기존 Numerical 후보 저장과
JobManager는 재사용할 수 있지만 사용자 CAD의 후보별 형상/메시/조건 생성과 편집 가능한
FreeCAD 문서로의 명시적 채택이 아직 없다. Astra가 이 후속 설계의 단위·참조 복구·재메시·
실패/취소·원본 보존 경계를 읽기 전용 검토했다. 권고를
[사용자 CAD 후보 계산·채택 명세](.moai/specs/SPEC-CAD-NUMERICAL-001/spec.md)에 반영했다.
형상뿐 아니라 하중·변위·재료·접촉 계수의 typed 변수, 후보별 면 대응/재메시,
binding 실패 이전의 시도 보존, 계산 당시 editable 모델에서 새 분기 열기를 포함한다.
기존 Simulation recipe·Numerical·JobManager·native opener를 재사용하고 pinned worker의
단일 fixture 전체 생성 경로를 일반 사용자 모델로 간주하지 않는다.
`PRO-CAD-NUMERICAL-01`을 같은 실제 Pro에 전송했고 본문과 끝 경계의 수신을 확인했다.
Pro가 `codex/cad-numerical-20261013`을 접촉 교정본 `5cb083c`에서 만들었다. 사용자 CAD
변수→후보 준비/해석→실제 후보 모델의 새 분기 열기를 작성한다. Pro는 제품·관련
검사/사용 안내, root는 현재 상태·SPEC·공통
계약 통합·실행, Astra는 중요한 후보/참조/취소/채택 경계의 독립 검토를 맡는다.
Pro의 첫 구현 `4beca42`를 로컬 `0ff9c5e`로 회수했다. 아직 원격 main에 게시하지
않았다. 변경 단위 검사에서 6건 통과·2건 실패이며 실패는 재열기 검사 호출의
`kind='numerical'` 누락이다. 별도로 실제 Python import에서 Pre bridge의
`RESEARCH_OPERATIONS`/`ResearchInputs` import 누락으로 시작이 실패했다.
`PRO-CAD-NUMERICAL-FIX-01` 교정 요청을 같은 Pro 대화에 전송했고 Astra에
이 첫 구현의 후보·참조·취소·새 설계 채택 경계를 읽기 전용 검토 배정했다.
독립 검토는 시작 import 누락 외에 같은 native target의 이름 변경/중복 등록으로
두 변수가 같은 값을 덮어쓰는 문제와 native FEM에서 바꾼 접촉 정의를 후보가
이전 metadata로 되돌리는 문제를 찾았다. 근거를 확인해 같은 Pro에
`PRO-CAD-NUMERICAL-FIX-02`로 전송했다. FIX-01의 교정 소스는 아래와 같이 회수했고
FIX-02는 공식 전송 도구 접수 후 교정본을 기다린다. 기존 응답을 중단하거나
중복 재전송하지 않는다. MoAI spec_progress도 구현 진행 상태로 다시 조회했다.
Pro의 시작 교정 `945a61e`를 로컬 `c22c0c2`로 통합했고 관련 단위 검사9건이
2.48초에 통과했다. 실제 FreeCAD GUI owner에서 공개 모델 사본의 치수·하중·강제변위·
탄성계수·접촉 강성을 등록하고 `pre.research.prepare`로 CAEPRE 저장까지 확인했다.
`runs/product-development/20261013/cad-capture-ad346f8e/receipt.json`에 성공과 원본
보존을 남겼다. OS 입력·broker·후보 계산·solver 실행·새 설계 채택의 증거는 아니다.
첫 capture 실패는 root helper가 Force 없는 옛 예제를 참조한 것으로 입력을 교정했다.
Windows의 패키지 루트 FreeCAD.exe가 즉시 종료하고 bin/freecad.exe 자식이 남는 것을
확인했다. bin 실행으로 위 capture를 마쳤고, 후보 adapter의 실제 실행 파일 선택과
Windows 자식 Gmsh 취소 범위도 Pro에 교정 검토 요청했다. 기존 종료 helper의
Windows 경로는 leader만 종료하므로 전체 process tree 취소 통과로 표시하지 않는다.
원격 main 확인값은 `b423e37`이다. 첫 소스 회수와 사용 가능한 구현 완료를 구별한다.
별도 native Post→Qt 실제 broker 연결 시도는
`runs/product-development/20261013/contact-handoff-83394326/receipt.json`에 실패로
남겼다. ParaView의 restore 진입 이후 60초 안에 broker 등록이 없어 중단했으며
실제 Qt 왕복 통과로 기록하지 않는다. 기존 pvpython 저장·재열기 통과는 유지하고
이 연결 진단이 CAD 기능 작성을 기다리게 하지 않는다.
Luna가 설치된 FreeCADCmd1.1.4에서 공개 모델 사본의 mapped-element API를 확인했다.
Bridge의 치수/Notch 위치 변경과 저장·재열기에서 두 mapped face가 유지됐고, 사라진 면과
분할 면은 `?Face`/lookup 실패 또는 다중 후손으로 구별됐다. primitive Box에는 map이
없어 FaceN 반환을 이력으로 오인하면 안 된다. 이 실제 관측과 정확한 API를 Pro에
전달했고 [기존 연동 조사](docs/research/OPEN_SOURCE_CONTACT_INTEGRATION.md#native-face-correspondence-for-cad-candidates)에
통합했다. 후보 실행기의 완료가 아니며 메시·solver를 돌리지 않았다.
Pro의 별도 실행 전 검사 수정
`1b37942`는 `02ed0ae`로 통합했다. 두-body contact를 단일 메시 조건으로 잘못 거부하지
않고 기존 export 검사 경로를 재사용한다. 변경된 native API 단위 검사1건이 통과했다.

편집 단계 이후 실제 FreeCAD GUI에서 기존 `pre.fem.mesh_generate`를 호출해 두 물체의
Gmsh 메시를 생성·저장했다. Base1147절점/532요소, Bridge2256절점/1122요소이고 접촉
참조 진단은 비어 있다. `runs/product-development/20261013/contact-mesh-350b4d63/receipt.json`과
`contact-meshed.FCStd`에 남겼다. 마우스·키보드 입력이나 solver 검사가 아니다. 앞선
FreeCADCmd 시도는 Qt 비동기 대기와 없는 ViewObject 때문에 실패했고 GUI 경로로 확인했다.
그 실제 메시 사본에 재료·Base 지지·Bridge 상면의 -0.3mm 강제 변위를 적용해 새 native
contact export도 완료했다. 설치된 writer와의 입력 비교, editable FCStd·mesh·deck·manifest를
`runs/product-development/20261013/contact-export-bf12e0c8/`에 보존했다. 예제 설정이며 물리
정확성·solver 실행의 증거가 아니다. 공통 FRD reader의 변경 영향 검사34건과 추가 FEM Qt
4건도 통과했다. 첫 export는 수분이 걸렸으며 요소마다 native.Nodes 전체 사전을 반복해서
읽는 기존 quality 경로를 확인했다. 같은 호출에서 절점표를 한 번 읽는 Pro 교정을
통합해 위의11.484초 export를 확인했다. 원래 측정이 정밀한 성능 benchmark는 아니므로
배율 개선을 주장하지 않는다. 수치 기준을 생략하거나 넓은 benchmark를 선행하지 않는다.
사용자 추가 지시에 따라 기존 오픈소스 전후처리기·solver 연동 코드와 이슈를 병행 조사해
현재 구현에 적용한다. [기존 연동 코드·이슈 조사](docs/research/OPEN_SOURCE_CONTACT_INTEGRATION.md)에
PrePoMax의 면/접촉 법칙 분리와 writer, ccx2paraview의 시간 이력 변환과 누락값·NaN을
0으로 만드는 처리, FreeCAD의 다중 메시 제약을 정리했다. 기존 converter의 재사용과
현재 reader 확장을 비교해 실제 부족한 연결만 구현한다. GPL을 무료 재사용 배제 이유로
삼지 않으며 배포 조건은 선택한 방식에 맞춘다. 조사 때문에 제품 작성을 중단하지 않는다.

접촉 구현의 실제 입력으로 [두 발 CAD 예제](examples/contact/README.md)를 추가했다.
FreeCAD의 편집 가능한 Boolean 형상이며 두 접촉면·0.2 mm 간극·받침을 저장/재열기했다.
이 추적 예제 자체는 입력 형상이며 생성된 접촉 선언·메시·계산은 위의 실행 기록에 따로
보존한다. 설치된 `ccx.exe -v`는 2.22를 반환했다.
Pro는 물체별 메시를 생성하고 export에서 절점/요소 번호를 분리하는 구현 방향을 선택했다.
Astra는 원본 물체 메시에서 면/하중을 먼저 매핑하고, 합칠 때 총하중·재료 배정과 역매핑을
보존해야 한다고 검토했다. 이 조건을 Pro에게 전달했으며 별도 solver 검증을 선행시키지 않는다.
실제 데스크톱 캡처는 Windows 잠금 화면이어서 해제를 요청했다. 창 입력 확인만 대기하며
Pro 작성과 코드 통합은 계속한다. 공개 PDF/Markdown/CSV의 첫 자료 가져오기 예제도 준비했다.
첫 통합 경로는 CAD/FE→Simulation→Runner→native Post→최적화와
Expert→Numerical→결과→Study이며
Data/Material/PDE는 독립 병행한다. 별도의 개발 시작 문구를 기다리지 않는다.
사용자는 [검토 안내](docs/design/20261012-desktop-planning/REVIEW_GUIDE.md)의 화면과
Qt 조작에 피드백을 줄 수 있다. 이를 반복 인터뷰나 과거 solver 전수 검증으로 바꾸지 않는다.
화면 수용과 지원 backend/장비/Expert 무료 연결은 해당 기능의 사용자 검토·기술 확인에
연결된 미완료 항목으로 유지한다.
현재 시제품은 정밀 입력·저장·재열기·선택·도킹 등 Qt 조작을 확인한 planning source다.
native OS/DPI·실제 FreeCAD/ParaView 연결·solver/provider/device는 미확인으로 남는다.
기획 요청의 원요구52개 추적표는 TRACED_NOT_IMPLEMENTED_BY_THIS_REQUEST를 보존한다.
새 기능 구현 현황은 해당 SPEC과 실행 기록에서 판단하며 원요구 전체 완료로 확대하지 않는다.
과거 수치 실패·UNKNOWN과 원 허용치는 그대로 유지한다.

### 앞선 통합 기록

사용자는 Codex와 실제 ChatGPT Pro가 문서 정리와 작업 방식을 토론해 **확정하고 반영**하도록
지시했다. 제안·상태 보고만 반복하거나 일상 반영을 위해 다시 승인을 기다리는 단계가 아니다.
맡긴 현행 문서/진입점 정리, Pro/Codex 책임 확정, Space 안내와 Git 기준 연결은 **완료**했다.
문서 통합 커밋 `6b0c2ed14f9d61204cabfe3c47288f2438202798`을 원격 main에 게시하고
같은 SHA를 확인했다. 관련 Space 6개 Page의 갱신·본문 재조회·기존 첨부 보존도 확인했다.
앞선 통합에 남은 문서 승인이나 제안 확정 단계는 없다. 아래 제품 방향의 본구현은
2026-10-12 당시 상세 기획 검토와 개발 시작 지시를 기다렸으며, 현재 배정은 위의
2026-10-13 기능 단위 구현이다.

다음 제품 작업은 아래 **독립 도구군의 실제 작업 완성**으로 확정한다. 특정 C3D10 메시나
F05 진단을 전체 제품 개발의 우선 과제 또는 선행조건으로 두지 않는다. 제품 구현 자체를
완료로 선언하거나 원래 수치·물리 요구를 없애는 결정은 아니다. 이번 문서 정리 중 새 제품
구현·native 계산·provider 실행은 시작하지 않았다.

## 기준 버전과 근거

- 검토한 기준: `b3fa9188490ea42399974ae07c10e83521f14d1d` (문서 정리 전 main).
- 제품 통합: [PR #7](https://github.com/pikachu444/autonomous-cae-lab/pull/7),
  merge `92a51fd7967ba1127b5a56755ebef6a46f41f04e`. 사용자는 알려진 F05 실패를
  이 개발 통합에 대해 수용했다. 병합 전 진단을 다시 선행조건으로 되살리지 않는다.
- 실제 확인한 CI: source `385818bab785bfbf2c1e5880371970e475c90d68`,
  [run 38159523618](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/38159523618),
  9 jobs pass / Code_Aster failure. 원 측정과 제한은
  [정확한 실행 기록](benchmarks/records/20261012-stabilization-s5-ci-native-continuation.json)에 있다.
  뒤의 문서 커밋과 병합은 새 solver 검증이 아니다.
- pinned upstream: `3e48bf6138f495299f45b1af254bfb4aaff307b8`.
- 아래 현황은 해당 코드와 기존 실행 기록을 대조한 것이다. 이번 문서 정리에서 새 GUI·
  solver·실제 AI 계산을 실행한 것으로 읽지 않는다.

## 전체 제품 현황

전체 구성은 FreeCAD CAD/FE, ParaView Post, 독립 Research 도구와 선택 Workbench로
정해져 있다. 상당한 구현과 부분 실행 근거가 있으나 전체 제품·사용성·배포는 미완료다.
구성·기존 구현을 재사용하되 최신 요청의 상세 화면·사용성 기획은 다시 검토한다.

| 영역 | 현재 구현/근거 | 남은 주요 제품 작업 |
|---|---|---|
| CAD/FE Pre | native 치수·Assembly·FEM 명령, 관리형 저장, 지원 계산 제출, 결과/원 설계 이동 | 실제 사용자 모델의 편집·선택·오류 복구·저장/재개를 포함한 전체 화면 작업. 넓은 접촉·비선형 지원은 별도 범위 |
| Post | 외부 결과 열기, 필터·측정·지원 비교, Apply/Undo, 원자료 수리, 부분 저장·재열기. 실제 ParaView의 제한된 실행 근거 | 실제 화면에서 대상·필드·위치·시간을 다루는 작업, 지원 비교 범위와 도구 이동 |
| Data | CSV/NPZ, 채널·축·단위·매핑·구간/mask, 보존 응답 비교, 실제 HTTP/Qt 저장·재시작 | 표·그래프 연동 선택, 처리 정의 편집과 큰 자료의 조작성 |
| Material | FELUPE 및 일부 MFront 법칙, 계수·이력, 평가·보존 응답·Plan/채택 연결 | 법칙·시험·관측·계수·상태 연구의 화면과 범용 protocol/FE 연결. 대역 UI 검사는 실제 native 물리 수용과 구별 |
| PDE | 선언된 모델의 편집·지원 검사·평가·보존 결과와 Post/Plan 이동 | 식·영역·조건·결과의 편집 깊이와 일반 ODE/약형식·solver 설정 등 지원 범위 |
| Numerical / Evaluation | Material/범용 Request Plan, 변수·응답·방법·후보·채택, 단계/전달/반복 정의와 일부 실제 수치/연성 실행 | 내부 key/value 중심 편집 개선, 방법별 의미·결과 해석, 지원 조합·재개 범위 |
| Runner | 실제 job 입력·상태·진단·취소·결과와 원 문서/Post/Study 이동 | 실제 배포 환경의 실패·취소·재접속·장시간 실행과 도구 이동 |
| Expert | 역할·논점·reply·개입·pause/resume·근거·Plan, 실제 provider/callback 기반. 이전 웹 화면의 실제 연구 왕복 기록 | 새 독립 Qt 화면의 자료/모델 설정부터 실제 대화→계획→계산→결과 후속 논의까지 연결·확인 |
| Study / 선택 Workbench | 질문·가설·근거·판단과 참조/도구 이동 | 별도로 계획한 문서·연결 그래프, 개정·변경 영향 화면. 기존 서비스 이름은 이 UI의 완성 근거가 아님 |
| 공통 GUI/CLI/Python/MCP | 같은 HTTP 서비스·문서 owner·명령·결과, native 명령 경로 | 실제 열린 native GUI와의 교차 작업, 지원 기능 노출과 클라이언트 사용 |
| 설치/독립 실행 | 기본 CMD의 native Qt Runner 진입, Research 도구별 직접 실행, 저장 문서와 같은 서비스 재사용을 구현·확인 | 전체 배포 패키징, 모든 파일 연결·복구와 여러 창의 종료/재실행 사용성 |

코드 위치는 `apps/desktop_pre`, `apps/desktop_post`, `apps/research`,
`caelab/workbench*`, `caelab/adapters`, `scripts/start_cae_research.ps1` 및 기존
설치/실행 스크립트다. [실행 기록](docs/WORKBENCH_PROGRESS.md)의 S1/S2와 후속 교정에서
이미 고친 Pre/Post Save, 초안, 선택·응답 읽기 결함을 새 미해결 과제로 복사하지 않는다.

## 진행 중인 제품 구현 방향

**목표:** 사용자가 원하는 독립 도구에서 자기 자료·모델을 열고 주요 편집과 필요한 계산을
수행하며, 같은 개정·결과를 다른 도구에서 이어 보고, 저장·종료 후 다시 연구를 계속한다.
제품 작성자는 Pro, 독립 검토·환경 확인·통합은 Codex가 맡는다.

진행할 범위:

1. 기존 실행 helper를 제품 진입에 연결한다. 도구·문서 선택, 올바른 창 열기, 서비스
   시작/재접속, 저장 후 새 프로세스 재열기를 완성한다. 계산 backend가 없어도 독립적인
   자료·문서·기존 결과 읽기는 계속 가능해야 한다.
2. Data·Material·PDE·Numerical의 주요 편집을 각 작업의 표·곡선·모델·변수/응답 중심으로
   보완하고, 기존 Pre/Post native 작업과 Runner를 연결한다. 내부 JSON/key를 사용자가
   알아야만 대표 작업을 끝낼 수 있는 부분을 남기지 않는다.
3. Expert에서 자료·모델·역할을 고르고 실제 대화와 개입을 진행한다. 제안된 Plan을
   사용자가 편집해 실행하고 실제 결과를 읽어 후속 논의를 이어간다. 이전 provider와
   공통 도구 구현을 재사용한다. 새 단독 화면의 실제 전체 흐름은 별도로 확인한다.

독립된 도구 보완은 병행할 수 있다. 모든 backend 설치, 선택 Workbench 그래프,
전체 원요구 재감사, C3D10 비교 수정이 다른 도구의 착수를 막는 전제는 아니다.
범용 구성식·PDE·연성·접촉·외부 solver 등의 확장은 제품 범위에 계속 남긴다. 이번
작업의 지원 범위를 명시하면서 확장하며, 첫 연결의 완료를 전체 물리 범위 완료로 바꾸지 않는다.

사용자 관점의 완료 기준:

- 원하는 도구로 직접 들어가 자기 파일/문서를 열고 대상과 관련 설정을 실제로 편집한다.
- 지원 입력은 실제 평가/계산과 결과로 이어지고, invalid 입력은 고칠 위치를 알려 주며 실행을 막는다.
- 다른 도구로 이동해도 같은 문서·개정·선택 결과를 사용한다. 과거 결과는 바뀐 입력과 구별해 남는다.
- 저장·닫기·새 프로세스 재열기 후 편집 내용, 결과와 연구 맥락이 이어진다. 누락 파일·실패·취소는 복구 가능하게 설명한다.
- Expert는 실제 provider와 도구 결과에 근거해 논의한다. 대역 답변·고정 숫자·옛 웹 검증으로 새 화면의 완료를 대신하지 않는다.
- 설치 후 시작/재실행 안내가 실제 동작과 맞고, GUI·CLI·Python·선택 MCP의 지원 범위가 일치한다.

Pro에게는 이 절과 제품 계획·관련 코드의 동일 기준 버전, 미반영 사용자 결정·산출물,
실제 확인 범위를 함께 전달한다. 이번에는 전체 기능과 화면/상태에 연결한 개발 명세와
구현 작업표를 보완한다. 기본 문서 소유와 native 재사용 경계를 임의로 교체하지 않는다.

## 문서와 새 세션 운영

현행 계획·상태·협업은 Git, 사용자 결정·이유·원자료는
[Space](https://chatgpt.com/space/page_6ac6e5e8d7688191a58c5760fda2d2d9)에서 보존한다.
Codex가 의미 있는 변경의 관련 Page 요약/링크까지 맞춘다. 자동 동기화는 없다.
최신 사용자 결정은 Git 반영 전에도 유효하다. Pro와 Codex는 각각 새 세션에서 같은
기준 자료로 작업하며 [시작문](CODEX_START.txt)과 [운영 규칙](docs/CODEX_WORKFLOW.md)을 쓴다.

현재 미반영 제품 코드 산출물은 없다. 앞선 Pro 대화는 문서·우선순위 결정이며 새 구현이
아니다. [실제 Pro 협의](https://chatgpt.com/c/6acc2538-ed3c-83ee-8e6b-6b98c52ea109)를 출처로 남긴다.
기존 `.codex-remote-attachments/`는 사용자 로컬 untracked 자료로 보존한다.
새 세션은 현재 프로세스·설치·인증·ignored 산출물의 존재를 다시 확인하며 가정하지 않는다.

문서 반영 확인(2026-10-12): 원래 52개 ID/설명 일치, 보존본 3개의 Git 저장 바이트와
SHA256 일치, 새 로컬 문서 링크, `git diff --check`를 확인했다. 제품 코드는 바꾸지 않았다.
Page 저장본은 [제품 입구](https://chatgpt.com/space/page_6ac6e5e8d7688191a58c5760fda2d2d9) 13,
[제품 설계·원문](https://chatgpt.com/space/page_d99abd5a046c8191b16263e448c8d8ee) 19,
[결정 기록](https://chatgpt.com/space/page_6ac6e6a501508191913070f4ef51eae9) 7,
[이전 상세기획](https://chatgpt.com/space/page_6ac6e67d6efc8191af147db299b3cf3b) 13,
[검토 원자료](https://chatgpt.com/space/page_6ac79c9b17c48191a63e2775c75fa1d2) 5,
[화면 도면](https://chatgpt.com/space/page_e314876e22bc8191b562de881de7f3b6) 24다.
수정 대상 외 본문과 첨부 참조를 보존했다. 확인 범위는 저장본문과 참조이며 앱 미리보기
요청은 응답하지 않아 렌더링 검토를 추가로 주장하지 않는다.

## 남겨 두는 수치·공학 한계와 기록

F05 원 측정 `3.32295e-6 > 1e-6`과 별도 실패한 AMD 시도는 그대로 남는다. 해당 실패를
이번 문서 정리나 PR 병합으로 통과시키지 않는다. 알려진 실패는 필요한 후속 수치 작업에서
다루며 전체 앱 구성의 선행조건으로 재시작하지 않는다. 물리·재료·강도·내구·회사 배포
승인은 별도이며 UNKNOWN/NOT_RELEASED를 유지한다.

이전 상세 상태/인계는 [보존 원문](docs/history/20261012-before-consolidation/README.md),
실제 실행은 [WORKBENCH_PROGRESS](docs/WORKBENCH_PROGRESS.md),
[PREPOST_VERIFICATION](docs/PREPOST_VERIFICATION.md), `benchmarks/records/`에서 찾는다.
원시 CI ZIP/로컬 runs는 Git clone에 포함되지 않으며 보존 기한과 위치는 해당 기록에 있다.
