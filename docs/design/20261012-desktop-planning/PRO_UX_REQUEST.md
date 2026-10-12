# 전체 도구 화면 교정 요청

요청: PRO-DESKTOP-DESIGN-20261012-06. 실제 전송 여부·대화와 현재 진행은 CURRENT_STATE가 소유한다.

실제 ChatGPT Pro는 전체 도구군의 설계 작성자다. 기존 D1의 핵심 명세와 Qt 소스를
회수했으나 현재 폼의 사용성과 여러 작업 전이가 수용되지 않았다. 기존 D1의 추가 회수와
교정 작업이 같은 파일을 수정하므로, 이번 작성 소유권은 별도 pro-ux/로 제한한다.

## 사용자 결정

Windows 로컬 Qt/PySide6 독립 연구 도구와 FreeCAD native Pre, ParaView native Post다.
웹/localhost/HTML·웹 wrapper로 주 화면을 만들지 않는다. 추가 지출은0원이며 기존
Codex·Pro 사용권과 이미 설치된 PySide6 6.9.1/Matplotlib만 사용한다. 유료 API/구독/
크레딧/UI kit/hosting/결제 trial/LS-OPT는 도입하지 않는다. Penpot은 사용자 지시로 제외했다.
기획·별도 Qt 시제품만 지금 작성하며 제품 본구현은 사용자 검토 뒤 개발 시작 지시를 기다린다.

최근 사용자 원문:

> 알아보기 힘들고 글만 주렁주렁 있는 프로그램이 우리 프로그램은 아니지?
> 90년대 실험장비 프로그램같이 생겨서 혹시나 물어보는거야. 너 빼고 아무도 쓰는법도 모를거 같고

> 요구사항을 듣지도 않았는데 마음대로 만들길래 물어봤어

> 나는 헬퍼 덕지덕지 붙고,•이 기호써서 쭉 파일명이나 제목 길게 가져가는거 질색이야.
> •r2 이런식으로 막 이어가는거 말이야. 그리고 재료 피팅하는 건 유명한 프로그램 그냥 베끼면 되지않아?
> 대표이미지가 왜 필요하지.

> 근데 캐드나 전처리 후처리 솔버 최적화 storm 같은 거 안 만들고 왜 재료 어쩌구 부터해?

재료 예시를 전체 우선순위로 확대하지 않는다. CAD/전처리→solver/Runner→native Post→
최적화와 Co-STORM 연구의 독립 작업·도구 간 전달을 중심에 놓는다. Material 교정이
다른 도구의 선행조건이 아니다. 전체 Data/Material/PDE/Numerical/Runner/Expert/Study와
선택 Workbench, implicit/explicit/contact/failure/constitutive/coupling/inverse/DOE/UQ/
surrogate/MOO/remote/측정·교정 범위를 유지한다. 참고 이미지를 사용자에게 요청하지 않는다.

추가 직접 지시: “뭘 지키고 유지하고 메타데이터 어쩌구가 중요한게 아니라니까”.
형상 만들기·메시/해석 조건·계산·결과 분석·최적화·연구의 대상과 조작/결과가 중심이다.
내부 관리 계약은 기본 동작을 위한 구현 사항이며 화면과 설명의 주요 내용으로 내세우지 않는다.

## 주 화면의 기존 기준

기준 source9a6e308과 D1 core95a2389의 공개 파일을 읽어 실제 재사용·지원 범위를 확인한다.
기존 PRODUCT_PLAN §3의 원형은 이미 정한 기준이다. 새로운 dashboard나 동일 폼으로
대체하지 않는다. 다음 배치는 확정된 기존 요구이며 세부 수정 시안은 검토할 제안이다.

| 도구 | 원형과 주 조작 |
|---|---|
| CAD/FE | FreeCAD native Model/Property/Tasks와3D. 스케치·피처·치수·instance/관절·운동·메시·조건 선택·저장/재개 |
| Post | ParaView native Pipeline/Properties, Apply/Reset, 큰 Render View, 표·곡선 분할·측정·검증된 비교·관리 분석 저장 |
| Numerical | HyperStudy 연구 트리, 변수/응답·후보 표와 선택 후보 곡선·목적·제약. DOE/동정/민감도/UQ/대리/MOO 구별 |
| Runner | Abaqus Job Manager/Monitor의 작업표와 선택 입력·진행·진단/로그·결과. close≠cancel, 요청≠확인된 종료 |
| Expert | 사용자가 지정한 Co-STORM의 논점 지도·다자 발언·reply 대상·하단 사용자 입력, 근거·명시 Plan·실제 결과 후속 논의 |
| Data | Origin workbook의 열 이름·단위·역할·수식, 촘촘한 표와 그래프의 연결 선택 |
| Material | MCalibration Calibrate/Load Case의 좌측 시험·계수, 우측 큰 관측/예측 곡선, 하단 출력. 직접 평가·동정 구별 |
| PDE | COMSOL Model Builder/Settings/Graphics. 트리·선택 식/영역/조건 설정과 동일 대상의 field/mesh |
| Study / Workbench | 독립 질문·경쟁 가설·근거·명시 판단 / 선택 문서·입출력 연결 보기. 다른 owner 편집기·scheduler를 중복 작성하지 않음 |

공개 공식 원형 자료는 PRODUCT_PLAN §3의 링크와 실제 그림을 사용한다.
상용 프로그램의 code/assets 복사·설치·구독·trial 없이 작업 방식과 정보 구조를 참고해
기존 무료 Qt/native 구성으로 직접 작성한다. 개발 Pro relay 사용권을 제품 Expert API
권한으로 추정하지 않는다. provider 미연결/limit은 질문·과거 발언·근거 읽기/저장을 유지한다.

## 작성할 실제 산출물

소유권: docs/design/20261012-desktop-planning/pro-ux/만 쓴다. 원 D1 pro-authored/, main,
제품 코드·CURRENT_STATE·설정·threshold·사용자 파일은 수정하지 않는다. 단순 helper·wrapper를
늘리지 말고 Qt 소스/편집 가능한 화면과 흐름 원본/짧은 README로 유지한다.

전체 도구의 정돈된 실제1440×900 화면을 작업 맥락마다 작성하고, CAD/FE→Runner→Post→
Numerical 후보→원 설계 채택·저장/재열기와 Expert/Study 연구를 클릭·키보드로 끝까지
따라갈 수 있는 별도 Qt 시안을 제공한다. 정적 native 그림은 설계 illustration이고
실제 FreeCAD/ParaView 조작·solver/provider 실행이 아니라는 표시를 간결하게 유지한다.
사용자가 조작할 대상·선택·입력·오류·취소·복구가 없는 설명 화면은 완료로 처리하지 않는다.

짧은 작업명과 자연스러운 파일 이름을 표시한다. 제목·목록에 •r2/generation/hash/state ID를
이어 붙이지 않는다. 정확한 원본 관계와 개정·실패는 이력/근거/진단에서 조회할 수 있어야
한다. 사용자 원파일을 자동 rename하거나 Core 개정 계약을 삭제하는 요구가 아니다.
도킹·창 크기·포커스·단축키·선택 연동·파일 대화상자를 확인 가능하게 하고, 도움말을 계속
읽어야 진행하는 폼·큰 설명 띠·보조 기능/상태 배지 나열은 제거한다.

정확한 같은 문서·개정·결과를 도구 사이에서 유지한다. invalid draft는 저장 가능하지만
required input invalid는 해당 실행/export 차단. 새 입력/attempt는 새ID, 이전 결과·실패와
UNKNOWN/NOT_RELEASED, F05 3.32295e-6 > 1e-6을 보존한다. Core/Domain/Adapter,
기존 owner·native bridge·upstream·JobManager·numerical engine을 재사용한다.

검토에서 확인한 전이 결함도 같은 정확한 문맥으로 교정한다:

- MOO p19의 CAD·Material Apply→owner별 Save/partial retry→group receipt→reopen 부재.
- thermal V-02/r4 및 thermoelastic V-03/r6 저장 후 일반 implicit/explicit V-03로 이동.
- saved Materialr19 참조 수리가 fit base r17/currentr18 채택 충돌로 이동.
- CAL-018r2의 원문 열기가 다른 연구 보고서/Material fit으로 이동.

Material의 dirty Data 제외 누락·범위8행/곡선1점 불일치·Tab trap은 원 D1 작성 작업에
이미 교정 요청했다. 별도 전체 UX 시안에서 이 잘못된 동작을 재현하지 않는다.
시안 값/계산은 합성으로 표시하며 제품 solver가 실제 지원하는 것으로 과장하지 않는다.

## 전달

공개 저장소 pikachu444/autonomous-cae-lab의 별도 design/product-ux-20261012 브랜치에
편집 가능한 핵심 source부터 소규모 커밋으로 게시한다. 원본 SVG/JSON/.drawio와 Qt 소스,
실행 방법, 작업 경로·교정 사항을 제공한다. 대량 PNG/ZIP 전송이나 manifest 작성이
실제 검토를 막지 않게 한다. download가 필요하면 실제 접근 가능한 링크를 제공한다.
계획/접수/파일 개수만 보고하고 끝내지 않는다. 내부 사고 과정 장문은 필요하지 않다.
Codex와 Astra가 실제 파일·화면·조작을 확인한 뒤 사용자에게 검토용으로 제시한다.
