# Autonomous CAE Lab 전체 제품 상세기획

작성 기준일: 2026-10-11  
용도: 구현 작업 분담, UI 설계 대조, 기존 코드와의 차이 검토  
상태: 제품 설계 제안. 제품 구현·배포·수치 검증·사용자 업무 수용·공학 승인을 뜻하지 않는다.

## 0. 이번 기획의 결론과 근거 범위

전체 제품의 첫 연결은 **FreeCAD에서 편집 가능한 모델을 만들고 바꾸어 메시·조건·실제 계산을 거친 뒤 ParaView에서 결과를 읽고 비교하고, 다시 설계를 수정하는 작업**으로 잡는다. **외부 결과만 여는 Post와 독립 연구 도구의 구현도 병행한다.** Material의 작은 편집–평가 단위는 이들 중 하나이며 다른 도구의 착수를 막는 선행조건이 아니다.

이번 문서는 이전의 “첫 Material 단위 인계 가능”을 전체 제품 기획 완료로 확대했던 순서를 바로잡는다. 문서 소유, 정확한 입력·결과 연결, invalid draft, 과거 결과 보존 등의 유효한 계약은 유지한다. 사용자에게 같은 범위·독립성·CAD 깊이·AI 역할을 다시 선택하도록 요구하지 않는다.

직접 확인한 자료:

- 제품 Page 저장본16과 화면·조작 Page 저장본21을 실제로 조회했다. 제품 구조, CAD/FE·Post, 연결 명령, 구현 순서, 52개 요구와 17개 사용 사례의 관련 본문을 읽었다. 모든 첨부를 새로 실행·검증한 것은 아니다.
- 공개 저장소 main의 확인 시점 커밋은 a10f2023a2084512839b5e0af8ab0adc0aeb9293이다. MCP/HTTP/서비스/CLI와 native Pre·Post 등의 관련 원문을 읽었다.
- FreeCAD 공식 FEM 안내와 실제 그림, ParaView 6.2 공식 안내서와 그 안의 GUI 그림, Origin·MCalibration·COMSOL·HyperStudy·Co-STORM·Workbench의 아래 명시 자료를 확인했다.
- 최신 로컬 커밋4fd9cea의 파일은 제공받지 못했다. 해당 커밋을 공개 main과 동일하다고 가정하지 않는다.
- 이 작업에서는 제품 코드, native GUI, mesher, solver를 실행하지 않았다. 보고된 FreeCAD 클라우드 시험은 별도 기존 근거다.

이 문서의 “신규 명령”, 화면 크기, 파일 묶음, MCP 확장과 작업표는 **지금 구현할 설계**다. 기존 기능으로 쓰려면 아래 재사용 표에 확인된 근거가 있어야 한다.

---

## 1. 사용자가 각 도구에서 끝낼 수 있어야 하는 일

| 도구 | 독립적으로 끝낼 작업 | 자기 문서가 소유하는 것 | 다른 도구로 전달하는 것 |
|---|---|---|---|
| CAD/FE Pre | 부품 설계·조립·운동·경로, 해석용 형상, 메시 개선, 영역·재료·조건, 계산 입력 검사, 설계 변경 | native CAD/Assembly/FEM 편집 문서, 해석용 표현, 영역·조건·수치 설정, 변수 대상 | 정확한 형상/mesh/입력 개정, 실행 요청, 계산 결과 열기 |
| Post | 외부 결과 탐색·필터·측정·시간/경로 곡선·비교·차이/변화율·보고용 출력 | reader·filter·측정·비교 recipe·보기와 결과 참조 | 원값/파생 응답·표/곡선·그림, 계산 근거 |
| Data | ASCII/표/시험 자료의 열·단위·구간·mask·변환과 관측 정의 | 원자료 사본/참조, 채널·축·시험 metadata, 처리 정의 | 정확한 관측·함수·가중치용 자료 참조 |
| Material | 구성법칙·계수·초기상태·시험 이력·직접 평가·구성 적분 연구 | law/구현 선택, 계수와 근거, protocol, 상태·적분 설정 | 평가기, 응답, 검증된 law의 FE 할당 자료 |
| PDE | 수학적 domain·식/약형식·field/space·BC/IC·이산화·기준해 비교 | 방정식과 수학적 모델, mesh 참조, 수치 설정 | 지원 평가 입력·field·오차/응답 |
| Numerical | 다중 시험 동정, 실제 DOE·영향도, 최적화, UQ·대리모델·다목적 연구 | Numerical Plan, 자유/고정·공유 변수, 응답·잔차·예산·방법·학습/holdout | 후보와 실제 평가 기록, owner별 채택 제안 |
| Runner | 준비된 지원 입력 제출·상태·로그·취소·재시도·결과 열기 | 실행 위치·자원·attempt·실행 기록 | 동일 고정 입력의 결과와 진단 |
| Expert | 질문·경쟁 가설·근거 검토·다자 토론·사용자 반론·다음 연구 | 논점·발언·출처·질문·계획 제안·토론 상태 | 편집 가능한 Plan 초안, 실제 결과에 근거한 해석 |
| Workbench, 선택 | 여러 문서·계산·근거의 연결 탐색과 변경 영향 확인 | 연결 참조와 연구 묶음의 보기 | 정확한 owner 문서 열기, 연결 개정 |

Study는 연구 질문·가설·근거·판단을 묶는 객체다. Numerical Plan은 계산 계획이다. 이를 같은 “Study 편집기”라는 말로 섞지 않는다. 한 Study가 여러 Plan과 여러 분야 문서를 참조할 수 있다. 독립 토론의 질문·논점·발언은 Discussion이 소유한다. Study에 채택한 연구 질문·가설·판단은 Study가 소유하며 Expert/Workbench에서도 같은 Study 편집 명령을 쓴다. 새 발언이 채택된 판단을 자동 변경하지 않으며 Study 연결 없이도 토론을 시작한다.

특정 지그, Maxwell, 낙하, J2/DP 등의 예제는 수용 사례다. 범용 편집기의 문서 구조나 화면 메뉴를 그 예제의 고정 파라미터로 만들지 않는다.

### 1.1 유지할 연구 영역

선형/비선형 implicit 구조, explicit 충격·낙하, 접촉·파괴·계면, 재료점·구성 적분·접선, ODE/PDE·연성, 외부 시험/해석 자료, inverse/DOE/최적화/UQ/대리모델/다목적, 원격 계산과 실험 교정의 연결을 보존한다. 세 사례 A/B/C로 이 범위를 대체하지 않는다.

Code_Aster/SALOME-MECA의 nonlinear implicit 주력 후보, CalculiX의 보조 경로, OpenRadioss explicit 방향, 기존 PDE·MFront 후보 검토도 유지한다. 최초 연결에 실제 지원되는 CalculiX 경로를 쓰는 것과 solver 전략을 그것으로 축소하는 것은 별개다. 현재 지원 여부는 설치·adapter·입출력·검증을 각각 확인해 표시한다.

---

## 2. 실행·문서·창 구성

### 2.1 물리 배포 권고

우선 검증할 세 실행 호스트는 **FreeCAD native 확장, ParaView native 확장, 로컬 Research 앱**이다. 이 수는 독립 도구 수나 최종 exe/process 수를 뜻하지 않는다.

- FreeCAD: native 문서 탭과 작업대 전환을 사용한다. 스케치부터 Assembly·FEM까지 같은 창에서 계속 편집한다.
- ParaView: 한 native session이 한 PostDocument를 소유한다. 여러 source와 Layout은 같은 분석 문서 안에 둘 수 있다. 두 번째 독립 분석 문서는 새 session/창으로 연다.
- Research: Data·Material·PDE·Numerical·Runner·Expert 각각의 Windows 시작 메뉴 항목·직접 실행·파일 열기를 제공한다. 각 도구는 별도 문서 창을 허용한다. 같은 편집기를 다른 문서 옆에 도킹할 수 있다.
- Workbench: 연결을 보고 싶을 때 직접 연다. 문서 생성·실행·저장의 입장권이 아니다.
- 기존 공통 서비스는 Lab 기능에 필요한 때 시작한다. 사용자에게 웹 대시보드나 계정 로그인을 먼저 요구하지 않는다.

Research의 Qt Widgets를 첫 구현 후보로 삼되 실제 Windows 표/차트·파일·창 수명·native 연결 결과로 확정한다. 기술 선택을 사용자에게 떠넘기지 않는다. FreeCAD·ParaView의 bundled Python/Qt와 Research Python/Qt는 별도 환경으로 유지한다.

### 2.2 문서 직접 열기와 여러 창

원 native FCStd와 지원 결과 파일은 기존 형식을 유지한다. Lab 편집 문서는 문서 종류·식별자·저장 개정·의존 파일을 기록하는 작은 manifest를 가진다. 새 universal solver schema를 만들지 않는다.

파일 연결은 한 공통 .caelab 문서 진입 형식을 사용하는 방안을 권고한다. 내부 kind로 owner를 선택하고 FCStd·PVSM·표·배열은 원래 형식으로 보관한다. 정확한 확장자와 묶음 포장은 기존 포맷 migration 확인 후 확정해도 된다. 파일 더블클릭→맞는 편집기가 바로 열린다는 행동은 지금 확정한다.

같은 문서를 두 창에서 보는 경우 같은 owner에 연결한다. 두 프로세스가 동일 문서를 독립 편집자로 잡으면 두 번째는 기존 창 연결·읽기 전용·새 분기 중 명시한 경로만 제공한다. 조용히 두 저장본으로 갈라지지 않는다.

제목줄에는 도구·문서명·미저장 표시를 둔다. 상태 상세에는 문서 ID, 현재 개정, 작업 세션과 연결 상태를 복사할 수 있게 한다. 긴 ID를 상시 화면 대부분에 반복하지 않는다.

### 2.3 저장·닫기·다시 열기

- 저장은 원문·유효하지 않은 초안·진단·필요한 입력/결과·연결·보기를 보존한다.
- 필수 파일을 완성한 뒤 마지막에 committed 참조를 게시한다. JSON 한 파일의 원자적 쓰기가 여러 파일 저장을 보장한다고 보지 않는다.
- 저장 실패 시 현재 미저장 초안과 이전 정상 저장본을 모두 유지한다. 필요하면 사용자가 이전 저장본을 별도로 연다. 성공 알림을 먼저 띄우지 않는다.
- 닫기는 미저장 편집과 진행 중 계산을 따로 다룬다. 창을 닫는 것이 job 취소가 아니다.
- 서비스가 계산을 계속 보유하면 문서 창을 닫아도 계산 기록은 남는다. 현재 구조가 service 종료까지 견디는 자동 재접속을 지원한다고 약속하지 않는다.
- 새 owner 프로세스에서 재열어 편집·결과 확인을 계속한다. 열기 자체로 solver·최적화·LLM을 다시 실행하지 않는다.
- 이동한 원파일은 이전 경로·찾은 경로·내용 확인값·영향받는 항목을 표로 보여준다. 내용이 같으면 위치 수리, 내용이 다르면 새 입력 개정으로 등록한다.
- 버전이 새롭거나 adapter가 없는 문서도 가능한 원문·과거 결과는 읽는다. 의미를 보존할 수 없는 편집은 읽기 전용으로 남기고 원본을 덮어쓰지 않는다.

### 2.4 Windows·입력장치·큰 자료

기본 검토 화면은 1440×900과 1920×1080이다. 100/125/150% 배율에서 실제 사용 가능한 창 영역으로 대조하고, 200%는 접근성/잘림 확인에 포함한다. 아래 폭은 논리 픽셀(DIP)이며 물리 픽셀에 맞추려고 글자를 축소하지 않는다.

연구 표는 가상 스크롤·고정 열·찾기·범위 선택·붙여넣기·열 폭 조절을 제공한다. 큰 표 전체를 매 편집마다 다시 읽거나 그리지 않는다. 많은 곡선은 표시 축약을 표시하고 원값 조회·계산은 전체 자료를 사용한다. 3D의 표시 간소화도 계산 mesh와 구별한다.

Research 공통 제안 단축키: Ctrl+O/S/Shift+S/W, Ctrl+Z/Y, Ctrl+Tab, F6/Shift+F6 패널 이동, 표 F2/Enter/Tab, 입력 취소 Esc. Native 편집 단축키는 유지한다. Lab 관리 CAD의 저장 경로와 Post의 Save Data 단축키 충돌은 아래 저장 규칙대로 명시 조정한다. 드래그만으로 가능한 필수 기능을 만들지 않고 메뉴/키보드 대안을 둔다.

---

## 3. 실제 화면 원형과 UI 변경 규칙

별첨 화면 배치도 UI01–UI12는 이 문서의 설계 그림이다. 공식 참조 화면이나 구현된 화면으로 표시하지 않는다. 각 그림의 번호는 해당 요소 설명과 연결된다.

| 작업 | 확인한 원형 | 그대로 유지 | 추가·변경과 이유 |
|---|---|---|---|
| CAD/FE | FreeCAD 공식 2025-09 FEM 안내의 Tasks·Gmsh·Force 이미지, 1.1.4 명령 소스 | native Model/Property/Tasks, 큰 3D, 작업대·선택·피처 이력 | 연결 상태·영역 복구·품질표·공통 실행/결과 연결을 dock로 추가 |
| Post | ParaView 6.2 안내서와 GUIOverview 그림 | 왼쪽 Pipeline/Properties, Apply/Reset, 큰 Render View, 필요할 때 View 분할 | 물리 의미·저장 측정·검증된 비교·분석 저장을 추가 |
| Data | Origin 공식 workbook 그림/GUI 설명 | 열 머리글 metadata, 촘촘한 표, 그래프 문서, 선택 연동 | 원자료·처리·관측의 소유와 mask를 명시 |
| Material | MCalibration Quick Tutorial 5·12쪽, 화면6.0.0 | 왼쪽 시험/계수, 오른쪽 큰 곡선/출력, 직접 평가와 동정 구별 | 동일 Numerical Plan 편집과 결과 보존·적분 상세 |
| PDE | COMSOL6.3 Figure2-1/Weak Form 문서 | Model Builder–Settings–Graphics, 하단 진단 | 지원 adapter·정확한 mesh·식 검사와 실행 분리 |
| Numerical | HyperStudy2024 workspace | Explorer/Directory, 변수·응답·후보 표, Messages | 실패/holdout/채택 owner를 명시, 강제 Back/Next 제거 |
| Runner | Abaqus2018 공식 job/monitor 설명 | job 표와 선택 job monitor라는 구조 | 상세 배치는 우리 설계. 현행 공식 버튼 배열 확인을 주장하지 않음 |
| Expert | Co-STORM 논문v2 Figure15 | 논점 지도·다자 발언·선택 연결·사용자 참여 | 원문/실제 계산/편집 Plan·중지/재개 연결 |
| Workbench | Ansys2026R1 객체 조작·셀 그림 | 객체 선택/도구 열기/연결 조작 | 정확한 개정·끊긴 연결·영향 표시 |

ParaView6.2 안내서의 GUIOverview 이미지 창 제목은 5.12.0-RC3이다. 이는 공식 안내서가 사용하는 native 화면 구조의 근거이며 6.2를 이번에 실행한 증거가 아니다. FreeCAD 공식 2025 화면도 1.1.4를 이번에 조작한 화면이 아니다.

**원형 대조 규칙**

1. 구현 작업마다 해당 원형의 버전·URL·작업 상태·주요 조작을 붙인다.
2. 원형과 실제 제품에서 같은 객체 수, 같은 작업 단계, 같은 창 크기/배율로 대조한다.
3. selection·Task/Property·표 밀도·곡선/3D 면적·직접 편집·비교 배치를 확인한다. 색이나 아이콘 유사도만 평가하지 않는다.
4. 정보 소유·정확한 비교·저장·지원 범위상 필요한 변화만 이유를 적는다. native 입력폼을 이유 없이 새 긴 폼으로 다시 만들지 않는다.
5. 실제 controller와 연결된 최종 기술 화면으로 검토한다. 별도 HTML 목업, 하드코딩된 응답, screenshot만으로 작업 완료를 선언하지 않는다.
6. native 기능을 그대로 쓰는 부분은 다시 그리지 않는다. 우리 추가 UI는 정확한 연결·검사·복구·비교·연구 편집에 집중한다.

---

## 4. FreeCAD CAD/FE 상세 UI와 작업

### 4.1 UI01 — 부품·스케치·피처 설계

**배치:** ① 상단 native 메뉴·작업대·도구막대. ② 왼쪽 260–320DIP Model/Property 또는 작업 중 Tasks. ③ 중앙 대부분은 native 2D/3D. ④ 하단 문서 탭·단위/선택/재계산 상태. ⑤ Lab 진단 dock는 오류나 명시 요청 때만 열린다. 모든 편집에서 오른쪽 Task 패널을 강제하지 않는다.

빈 문서는 새 부품·기존 모델 열기의 실제 명령 위치를 보여준다. 지그 예제를 자동 생성하지 않는다. 문서명, 미저장, 활성 Body/Part, 작업대, 선택 종류/개수는 항상 알 수 있다.

**메뉴·직접 조작**

1. native File의 New/Open/Save로 시작한다. FCStd는 피처 이력을 보존한다. STEP/IGES 등 지원 가져오기는 원파일 사본·단위·본체 수·형상 유효성부터 확인한다. 없는 스케치 이력을 복구했다고 표시하지 않는다.
2. Body·기준평면 또는 면을 선택하고 native 스케치 생성 명령을 실행한다. 기하·치수·구속은 Sketcher의 실제 도구와 구속 목록에서 편집한다.
3. 구속 목록 선택↔해당 기하/치수 강조를 유지한다. 치수 더블클릭, 점/선 복수 선택, 상자 선택, native 입력 취소를 사용한다.
4. Pad/Pocket/Revolve/Groove 등 지원 피처를 native Tasks에서 만든다. 이력의 피처를 다시 열어 치수·방향·범위 등을 수정하고 재계산한다.
5. 트리의 부품 이름 변경과 내부 객체 식별자를 구별한다. 활성 Body가 다른 상태에서 피처를 만들면 대상 Body를 보여주고 잘못된 객체에 넣지 않는다.
6. Lab “연구 변수로 등록”은 선택한 실제 치수/속성의 정확한 객체·경로·단위·타입·유효 범위·의존식을 등록한다. 수치 탐색 범위는 Numerical Plan이 소유한다.
7. 후보 값을 시험 적용할 때 변경 전후 형상·치수·검사 결과로 실제 효과를 확인한다. 변수를 바꿨는데 형상/응답에 영향을 주지 않으면 그 상태를 남긴다.

**오류·취소:** 과구속/미구속은 native 의미대로 표시하고, invalid shape나 실패 피처는 해당 이력에서 수정한다. 마지막 정상 형상이 화면에 남아 있으면 “이전 정상 형상”으로 표시한다. invalid draft 저장은 허용하되 이를 최신 정상 모델로 export/실행하지 않는다. native Task가 열린 동안 충돌하는 AI 편집은 BUSY_EDIT를 반환한다.

### 4.2 UI02 — 부품 정의·배치·조립·관절·운동

**배치:** ① native Assembly 도구막대. ② 왼쪽 부품 정의/배치된 Link/관절/운동 트리와 Tasks. ③ 큰 3D. ④ 운동을 다룰 때만 하단 재생·시간·frame·추적점/경로 표. 설계 모델을 작은 미리보기로 줄이지 않는다.

**native 명령 근거:** 읽은 FreeCAD1.1.4 소스에서 New Assembly(A), Component(I), Revolute Joint(R), Simulation(V)를 확인했다. archived wiki의 Create Simulation(S) 표기와 다르므로 실제 pin의 명령 정의를 따른다. 최종 설치 언어에 따른 표시는 native 번역을 사용한다.

**조작 순서**

1. 같은 창에서 부품을 만들거나 기존 native 부품 문서를 연다. 부품 정의와 여러 배치 인스턴스를 트리에서 구별한다.
2. 조립에 Component를 넣고 기준 부품을 고정한다. 정의 수정의 모든 배치 영향과 특정 Link 배치 수정을 구별한다.
3. 두 대상과 축/점/면을 선택해 지원 관절을 만든다. Tasks에는 양쪽 소속 부품·참조·축·offset·지원 한계가 보이고 3D에서 강조된다.
4. 잘못 선택한 한쪽만 목록에서 교체한다. 같은 면 번호·가까운 위치로 자동 재연결하지 않는다.
5. Simulation에서 구동 대상·식·시간 범위·출력 간격을 정하고 실제 frame을 계산·재생한다. 생성된 frame과 표시 중인 frame을 구별한다.
6. Lab “추적점 추가”는 부품 로컬 좌표나 정확한 점 참조를 저장한다. 각 frame의 실제 배치를 사용해 세계 좌표 경로와 시간 표를 계산·보존한다. 경로의 3D 점과 표 행을 연결한다.
7. 관절 한계·조립 불능 frame은 시간과 대상 관절로 이동한다. 성공한 구간은 남기되 실패 구간을 선으로 메우지 않는다.

운동학 결과는 배치·자유도·경로의 결과다. 접촉력·충돌 충격·응력·구동 토크를 계산한 것으로 표시하지 않는다. CAD 조립의 기구학적 고정과 FEM 하중/구속도 서로 자동 대체하지 않는다.

### 4.3 UI03 — 해석용 형상·영역·재료·조건

같은 창에서 FEM으로 이동한다. 트리에는 설계 CAD/Assembly와 **해석에 사용할 형상**, Analysis, Mesh, 영역, 재료/단면, 조건을 구별해 둔다. 이는 또 다른 외부 CAD 프로그램으로 이동하는 흐름이 아니다.

공식 FEM 안내의 단일 meshing object·혼합 차원 제한은 실제 사용할 pin/adapter에서 확인한다. 조립을 무조건 fuse해서 접촉면과 재료 구분을 없애지 않는다. 공유 절점으로 붙일 경계, 분리할 접촉/tie 경계, 해석에 포함/제외할 부품을 해석용 표현에 기록한다. 단순화해도 원 설계 이력은 남긴다.

**선택과 영역**

- 본체/면/모서리/점 필터를 선택한다. 트리·3D 강조·속성의 대상이 일치한다.
- Lab “영역 만들기”는 이름, 대상 차원, 소속 부품/인스턴스, 정확한 형상 개정, 대상 목록을 저장한다.
- 모델 전체·현재 Analysis·선택 범위의 검사 구분을 표시한다. 여러 Analysis가 있으면 활성 해석을 상시 표시한다.
- 집합 선택은 Ctrl/Shift 및 목록의 Add/Remove로 한다. 모호한 화면 클릭만으로 조건이 어디에 걸렸는지 판단하게 하지 않는다.

**재료와 조건의 직접 편집**

| 작업 | 입력/화면 | 완료·오류 |
|---|---|---|
| FE 재료/단면 | native 재료 Tasks, 대상 solid/shell/beam, 값·단위·두께/단면 | 누락/중복 할당 위치 표시. 구성모델 연구 편집기를 여기서 복제하지 않음 |
| 힘/압력/변위/고정 | native 대상 Add/Remove, 크기·단위·성분·좌표계·방향 | 대상 면과 화살표 강조. 총 힘/면압을 구별 |
| 접촉/tie | 두 면 집합·방향·법칙·초기 간극·지원 solver | 반대/누락 면·미지원 법칙은 해당 조건에 표시 |
| 시간/초기 조건 | 물리 step·진폭/이력·초기속도·온도 등 지원 속성 | 단위·범위·step 연결 확인. 지원되지 않는 카드를 정상 입력으로 내보내지 않음 |
| solver 수치 설정 | Analysis의 solver 객체/도메인 설정에서 증분·수렴·안정화·출력 | Runner의 CPU/host 설정과 분리 |

재료점에서 동정한 모델을 FE에 넣을 때는 law/응력 척도/내부상태/계수 변환이 검증된 adapter만 사용한다. “재료 가져오기” 한 버튼으로 임의 구성법칙이 모든 solver에서 지원되는 것처럼 표시하지 않는다.

### 4.4 메시 개선 화면

① native Gmsh Tasks, ② 큰 3D mesh, ③ 하단 약180–260DIP의 “메시 검사” 표/분포를 사용한다. 속성/Task를 다시 만든 웹 폼으로 대체하지 않는다.

1. Mesh From Shape by Gmsh에서 차원·요소 차수·전체 최대/최소 크기와 지원 설정을 정한다.
2. Apply로 생성한다. mesher 로그와 실제 준비/생성/읽기 단계를 보여주며 총량이 없으면 백분율을 만들지 않는다.
3. Mesh Refinement에서 면/모서리/점 또는 지원 solid를 Add/Remove하고 국부 크기를 입력한다.
4. 설정을 바꾼 뒤 부모 mesh에서 Apply로 재생성한다. 설정만 바뀐 mesh는 최신으로 표시하지 않는다.
5. 품질표는 요소 ID·부품/영역·지표·값·기준·판정을 가진다. 분포 구간/행 복수 선택→실제 나쁜 요소 강조→줌/격리→주변 영역 확인으로 연결한다.
6. 국부 크기·분할 또는 형상 단순화를 수정하고 다시 생성한다. 전후 요소 수·품질 분포·설정·검사 정의를 비교한다.
7. 실패한 새 mesh는 기존 실행용 mesh를 자동 대체하지 않는다. old mesh와 검사 결과를 보존한다.

요소 종류별로 실제 계산·검증한 품질만 노출한다. 요소 개수 출력, 일부 Jacobian 샘플, “mesher exit0”를 전체 요소 품질 통과로 부르지 않는다. 직접 절점 이동/요소 재연결은 후속 검토이며 이 첫 개선 작업의 대안이 아니다.

### 4.5 형상 변경 뒤 연결 복구

피처 재계산 뒤 mesh·영역·조건·접촉·관절의 연결을 검사한다. 아래 표는 오류 dock의 구체적 내용이다.

| 영향 대상 | 화면의 상태 | 복구 조작 |
|---|---|---|
| 이전 mesh | “형상이 바뀜, 이전 mesh” | 변경 설정 확인→재생성 |
| 영역/조건 대상 | 유지/끊김/모호함·이전 대상·영향 해석 | 행 선택→이전 형상 반투명 보기→대상 다시 선택 |
| 관절 참조 | 영향을 받은 Link·축/면·실패 frame | 관절 Tasks에서 해당 참조 교체 |
| 물리 재료/출력 | 새 부품 미할당·영역 불일치 | 해당 재료/출력 정의로 바로 이동 |

새 대상 적용 전에는 부품·개수·면적·위치·방향·변경 목록을 보여준다. 면 번호가 같다는 이유로 유지하지 않는다. 확실한 대응을 검증할 수 없는 연결만 명시 복구 대상으로 남기며 정상 연결까지 전부 수작업으로 다시 하게 만들지 않는다.

### 4.6 검사·실행·Post·저장

Lab 신규 메뉴 “계산 검사 / 실행 / 결과 열기 / 변경 영향”을 native Analysis와 연결한다. 동일 계산을 native solver 버튼과 Runner 양쪽에서 중복 제출하지 않는다. Lab에서 관리하는 실행은 기존 adapter의 입력 생성/solver 경로를 공통 Runner로 연결한다. native에서 독립 수행한 결과를 가져올 때는 외부 결과라는 실행 근거를 유지한다.

검사 표는 잘못된 형상, 미할당 영역, 충돌 조건, 미지원 카드, mesh 문제, 필요한 파일을 객체별로 보여준다. 행 더블클릭은 해당 Task/셀/3D 대상으로 이동한다. invalid 입력은 그 실행/내보내기만 차단한다. 제조/장착 기준 미확인 등 engineering UNKNOWN은 연구 계산의 유효성과 구별하고 제작/사용 승인에 반영한다.

제출은 현재 유효 입력을 고정한다. 계산 중 편집한 draft와 늦게 도착한 결과를 섞지 않는다. Runner dock와 독립 Runner 창은 같은 job이다. 결과 열기는 정확한 result ID와 출발 입력을 Post로 전달한다.

Lab 관리 CAD 문서의 File Save/Ctrl+S/닫을 때 저장은 같은 Lab 저장 관문을 호출한다. native FCStd 직렬화를 재사용하되 외부 Link 의존 문서, mesh 설정·조건·Lab 연결과 보존 결과 참조를 함께 묶는다. 단순 FCStd 사본 저장은 별도 native 사본 내보내기로 구별한다. 관리 문서의 native File Export와 Lab 입력 내보내기도 같은 대상·유효성 검사에 연결한다. draft 보존용 native 저장과 실행용 형상/deck 내보내기는 구별한다. staging 저장이 현재 문서 경로와 Link 상대 경로를 바꾸지 않는지는 실제 통합 시험으로 확인한다. 새 프로세스에서 열어 피처·관절·mesh 설정·조건을 재편집해야 통과다. STEP와 결과 그림만 남는 것은 통과가 아니다.

---

## 5. ParaView Post 상세 UI와 작업

### 5.1 UI04 — 독립 결과 열기·필드·시간

기본 배치는 ① native 상단 메뉴/필드·성분·time·선택 도구, ② 왼쪽280–320DIP Pipeline Browser와 Properties/Information, ③ 중앙 하나의 큰 Render View, ④ 필요할 때 하단 Spreadsheet/Line Chart, ⑤ 상태/오류다. 처음부터 A/B 두 화면을 강제하지 않는다.

항상 현재 분석 문서·선택 source/filter·활성 View·field/component·값의 위치(point/cell 등)·단위·실제 시간/step을 식별할 수 있다. 좌표계와 응력 종류는 상세에 두되 비교 설정에서는 필수로 노출한다.

**열기**

1. Post 바로가기, 지원 파일 열기 또는 Runner의 결과 열기에서 시작한다. CAD/solver/AI/Workbench가 없어도 가능하다.
2. native File → Open(Ctrl+O)으로 파일이나 시리즈를 고른다. 여러 독립 결과 선택과 한 시계열 그룹을 구별한다.
3. reader 후보가 여러 개면 Open Data With…에서 선택한다. MCP도 reader 후보를 조회하고 같은 선택을 명시한다.
4. Properties에서 block/field 등을 정하고 Apply한다. 실패하면 reader 노드와 오류를 남겨 설정 변경/다른 reader 선택으로 복구한다.
5. Information에서 배열·point/cell 수·범위·time 목록을 확인한다. 단위 없는 파일은 미지정이다. 이름 Stress만 보고 MPa/Cauchy로 추정하지 않는다.
6. field·성분·표현·범례·카메라는 native 도구를 쓴다. 원 좌표와 변형 표시 좌표, 변위 배율을 구별한다.

지원 포맷은 실제 reader/필드/시간을 시험한 목록으로 관리한다. 확장자 목록만으로 지원 완료를 선언하지 않는다. 원 solver 없이 열기는 필요한 reader/plugin이 설치됐다는 전제이지 모든 포맷을 자동 지원한다는 뜻이 아니다.

### 5.2 필터·적용·되돌리기

| 기능 | 실제 native 명령 | 직접 편집 | 표시와 데이터의 관계 |
|---|---|---|---|
| 절단면 | Slice | 원점·법선·3D plane widget | 입력 source 아래 출력 노드. Apply 후 결과 |
| 잘라내기 | Clip | 형상·방향·안/밖 | 원 결과 유지, 출력 영역 변화 |
| 변형 표시 | Warp By Vector | 변위 배열·Scale Factor | 배율 표시, 이미 변형된 좌표의 중복 변형 방지 |
| 등고선 | Contour | scalar·등위값 목록 | 배열 위치 변환은 명시 노드로 남김 |
| 표시/범례 | Display/Color Map Editor | field·range·색·legend·representation | 즉시 표시 변경. 별도 계산 Apply 강제 안 함 |

필터 속성은 native Apply/Reset을 사용한다. 입력 중인 값과 마지막 적용 출력은 구별한다. Lab 기본은 Auto Apply와 Auto Convert Properties를 끄는 것으로 정한다. 비용 큰 계산과 point↔cell 변환/성분 추출이 묵시적으로 실행되지 않도록 필요한 변환을 실제 pipeline 노드에 남긴다.

GUI와 MCP의 Apply는 같은 명령과 대상 노드 집합을 사용한다. GUI에도 적용 대상을 표시하고 범위 밖의 미확정 편집은 자동 적용하지 않는다. 전체 적용을 제공할 때는 별도의 명시된 적용 범위로 처리한다. 이는 native 기능 호출 전 범위를 정하는 연결이며 필터 계산을 다시 구현하는 뜻이 아니다. 필터 실패는 그 branch만 오류로 남기고 원 reader와 다른 정상 branch는 계속 쓴다.

Delete는 필터 제거이며 원파일 삭제가 아니다. 문서 Undo와 view/camera 되돌리기는 native 의미를 표시한다. 추가 metadata·측정·비교도 native 변경과 같은 사용자 작업으로 되돌아가도록 연결한다.

### 5.3 원값 선택·저장 측정·곡선

원 절점/요소 선택, 좌표 보간 probe, 조건으로 매번 선택하는 집합을 구별한다.

- 선택 필터는 point/cell과 표면/깊이 포함을 명시한다. 3D 선택↔표 행↔source가 맞아야 한다.
- 원 ID 배열이 없으면 VTK 내부 index라고 표시한다. solver 원 절점 번호로 부르지 않는다.
- Find Data는 source·element type·ID 배열·조건을 사용한다. 잘못된 source의 같은 숫자 ID를 가져오지 않는다.
- Lab “측정 대상으로 저장”은 source 개정, ID/좌표, 기준/변형 위치, 좌표계, 대상 집합, 추적 의미를 보존한다.
- 시간곡선은 Plot Selection Over Time, 경로곡선은 Plot Over Line을 활용한다. 끝점·분할·방향·시간과 유효구간을 편집하고 3D widget/표를 연결한다.
- 같은 요소 추적과 매 시점 최대값 위치 추적을 구별한다. Freeze Selection은 현재 조건을 ID 선택으로 고정할 때 사용한다.
- 현재 active selection만 저장했다고 간주하지 않는다. 저장 측정은 Extract Selection 등의 실제 입력과 Lab 정의로 보존한다.
- 곡선 선택은 source·측정·성분·시각을 연결한다. 유효 대응이 있을 때 같은 위치를 3D에서 강조한다. 표시를 축약한 곡선에서도 정확한 원표로 이동해 조회한다. 가까운 원 sample을 대신 선택하면 그 사실을 표시하고 정확한 위치 선택으로 부르지 않는다.

점 선택 정보에는 source/result, 원 ID 또는 probe임, association, 좌표·단위, 실제 time, 값·단위, 유효 여부가 함께 표시된다. 영역 밖 probe는 빈 구간과 사유를 남긴다.

최대/최소·평균·분포는 대상 집합·시각·성분·가중 방식을 저장한다. 절점 수 단순 평균과 면적/체적 가중 평균, 현재 frame 최대와 전 이력 최대를 같은 항목으로 표시하지 않는다.

### 5.4 UI05 — 비교·차이값·변화율

두 source 또는 저장한 측정을 선택하고 Lab “비교 만들기”를 실행한다. 새 Comparison 노드와 native 비교 Layout을 만든다.

① 기존 Pipeline/Properties, ② 상단 A/B Render View, ③ 하단 곡선/원값·차이표, ④ 선택 비교의 대응 설정, ⑤ 상태를 사용한다. 화면에 필요하면 A/B/차이 View를 탭/분할로 전환한다. 카메라 연결·공통 범례·물리 시간 연결을 각각 켜고 끈다.

**비교 설정의 필수 입력**

| 항목 | 사용자가 확인/선택하는 값 | 계산 불가 시 화면 |
|---|---|---|
| A/B | 기준·비교의 정확 source/result revision | 빠진 source 행에서 위치 복구 |
| 물리량 | quantity·단위·성분·응력 척도 | 단위/measure 미지정 셀로 이동 |
| 기저/위치 | 좌표 방향·point/cell/integration 위치 | 명시 변환/투영 설정 또는 차이 차단 |
| 시간 | 실제 sample 대응, 명시 보간 방법·공통 구간 | 대응 없는 시간 표시. 가까운 frame을 exact로 부르지 않음 |
| 공간 | 같은 mesh 확인 또는 검증된 mapping·유효영역 | 나란히 보기 가능, field 차이 불가 사유 |
| 계산 | B−A 또는 100×(B−A)/abs(A), mask·연산 순서 | A=0/결측/영역 밖은 undefined |

Resample With Dataset은 계산 수단이며 대응 검증이 아니다. 어떤 dataset의 값을 어떤 위치로 옮기는지 명시하고, source/destination 이름이 Python proxy와 GUI에서 다를 수 있으므로 실제 배열과 좌표로 확인한다. point/cell 자동 변환을 비교의 일부로 숨기지 않는다.

같은 메시라도 숫자 ID만 비교하지 않는다. 정확 mesh identity·위치·연결·association을 확인한다. remesh/형상 변경이 있으면 검증된 mapping 없이 장 전체 차분은 차단한다. 원 결과 두 개의 나란히 보기와 동일 정의 게이지/반력/강성 응답 비교는 계속 가능하다.

선택 위치의 표는 A 원값, B 원값, B−A, 변화율, 단위, 실제 A/B 시간·위치, 유효/불가 사유를 보여준다. 계산식과 recipe 개정을 저장한다. A/B를 교환하면 식·분모·결과도 새 개정이다.

단위·기저 변환, 공간/시간 대응, 성분 추출·norm, mask의 순서를 기록한다. norm의 차이와 벡터 차이의 norm을 혼동하지 않는다. Cauchy와 first Piola 등은 명시 변환과 필요한 상태 없이 차분하지 않는다.

숨김은 표시 상태다. 목적함수·통계 제외와 별도다. 결측·NaN·0분모를0으로 채우지 않는다. Post 시간 보간은 명시 방법/공통 유효구간만 허용하고 외삽·gap 연결을 금지한다. fitting의 별도 보간 규칙과 혼합하지 않는다.

### 5.5 분석 저장·출력·파일 복구

Lab Post에서는 File에 “분석 프로젝트 열기/저장/다른 이름으로 저장/닫기”를 추가한다. **관리 문서의 Ctrl+S는 분석 저장**으로 연결하고, native Save Data는 데이터 내보내기 명령으로 계속 제공하되 충돌 단축키를 제거한다. 이것은 저장 대상 혼동을 해결하기 위한 의도된 UI 변경이며 stock ParaView 전체 설정을 바꾸지 않는다.

Save Data, Save Screenshot, Save Animation, Save State는 각각 데이터/그림/동영상/native state 내보내기다. PVSM만으로 Lab 분석 저장을 완료했다고 하지 않는다.

분석 저장에는 source 확인값·reader 설정, pipeline/PVSM, 미적용 draft/진단, 측정·비교·보존 파생 결과, view/layout/camera/legend가 포함된다. native Load State의 파일 위치 선택은 재사용하되 내용 확인·부분 복구는 Lab이 맡는다.

B 파일이 없어도 정상 A와 이전 저장된 근거를 연다. B 의존 결과는 무엇이 누락됐는지 표시한다. 내용이 바뀐 파일을 기존 source로 가장하지 않는다. 새 프로세스에서 같은 원값/측정/비교가 복원되어야 한다. 보존된 수치를 여는 것과 캐시 없는 후처리 필터를 다시 계산하는 것은 화면에서 구별하고 solver 재실행은 하지 않는다.

---

## 6. 독립 연구 도구의 전체 UI

### 6.1 UI06 — Data

**배치:** 상단 File/Edit/Data/Transform/Plot/Window, 왼쪽200–260DIP 자료·sheet·처리 목록, 중앙 큰 workbook/graph 문서, 필요 시 우측 처리 상세, 하단 선택 범위·진단. 표와 그래프는 기본 상하60:40 분할 또는 사용자가 최대화/나란히 배치한다.

열 머리글에서 이름·단위·X/Y/error 등 역할을 직접 편집한다. 원 행/ID는 고정 열이다. 열 순서를 바꿔도 채널 ID는 유지한다.

1. “자료 가져오기” 또는 드롭→구분자·인코딩·헤더·소수점 미리보기→열 역할·단위 지정→원자료와 해석 표 보관.
2. 열 복수 선택→“선택 열 그리기”. 그래프의 구간 선택↔표 행 범위를 연결하고 행 기반/실제 축 구간 기반을 명시한다.
3. 변환 선택→입력·설정·출력 열과 전후 미리보기→적용. 처리 결과와 recipe는 작성한 Data 문서가 소유한다.
4. 처리 이력 더블클릭→이전 입력/설정 확인→수정 시 새 revision. 원파일을 덮어쓰지 않는다.
5. “관측으로 연결/함수로 연결”은 Material/PDE/Plan에 정확 채널·단위·구간·개정을 전달한다.

원자료 품질 mask, 연산 유효성 mask, Plan의 연구 선택/잔차·weight/holdout, Post의 표시 숨김은 다른 것이다. 같은 곡선/표/변환 엔진을 Data·Post·Material·Numerical이 재사용하되 recipe owner는 하나다. 다른 도구의 recipe 수정은 해당 owner 편집기로 연결한다.

시험 metadata에는 시편·로트·장비·센서/교정·장착·좌표/방향·영점·시험 이력·관측 시점·불확실성 자료의 존재 여부와 원문을 둔다. 모든 항목을 강제하는 긴 입장 폼은 만들지 않고 사용하는 판단에 필요한 항목을 진단한다.

결측/비단조 축/단위 미상은 해당 셀에서 수정하거나 초안으로 보존한다. 엄격한 기존 reader의 제한을 그대로 새 편집기의 저장 금지로 확대하지 않는다.

### 6.2 UI07 — Material

**배치:** MCalibration 원형처럼 왼쪽 약35% 위 시험 목록/아래 계수표, 오른쪽 약65% 위 큰 관측·예측 곡선/아래 실제 Runtime Output·진단·보존 결과. 상단은 모델 선택·직접 평가·Plan·저장이다.

시험 목록은 관측 유무·protocol·온도·평가 상태를 보여준다. 계수는 이름·단위·현재값·값의 근거(추정/외부 고정/미식별)를 직접 편집한다. Numerical Plan이 선택되면 같은 표 옆에 하한·상한·고정/자유·공유 여부를 보여준다.

**Plan 열 편집은 같은 PlanVariablesTable과 같은 Plan owner로 보낸다.** 선택 Plan 이름/개정이 머리글에 표시된다. 창 이동을 강제하거나 Material에 중복 범위를 저장하지 않는다. Plan이 없으면 해당 열은 연결 없음이며 직접 평가에는 Plan을 생성하지 않는다. 현재값의 편집/Undo는 Material, 범위·자유/공유 셀의 편집/Undo는 Plan이 담당한다. Undo 메뉴에는 대상 문서와 되돌릴 명령을 표시한다. 여러 owner 열을 가로지르는 붙여넣기는 대상별 변경을 미리 구별해 적용하고 부분 실패를 전체 성공으로 표시하지 않는다.

시험 더블클릭은 이력 편집을 연다. 시간·제어량·성분·온도 표와 이력 곡선을 나란히 두고 구간 선택/붙여넣기/행 추가·삭제를 지원한다. 초기상태·적분 설정은 같은 시험의 접을 수 있는 상세다.

“직접 평가”는 유효 snapshot으로 기존 evaluator를 호출한다. 원 입력·응력/변형률 척도·내부상태·곡선·진단을 결과와 연결한다. 편집 중 도착한 결과는 출발 입력에 남고 현재 결과로 자동 채택하지 않는다.

“이전 결과 비교”는 보존 결과의 곡선/잔차/원값을 연다. 상세 곡선이 없으면 새 evaluation임을 명시해 평가한다. 결과 선택만으로 숨은 재계산을 하지 않는다.

구성 연구 상세는 상태변수·증분·적분 오차·consistent/continuum tangent·독립 기준 비교를 다루는 별도 보기다. FE card 목록으로 축소하지 않는다. 현재 FELUPE linear_elastic/neo_hooke와 J2/DP/MFront 지원 과제를 구별한다.

### 6.3 UI08 — PDE

**배치:** COMSOL형 Model Builder 약20%, Settings 약28%, Graphics 약52%, 하단15–25% Messages/Progress/Log. 이 작업에서만 필요한 세 열 구조다.

트리는 domain, field/function space, 함수/계수, 방정식, BC/IC, mesh/이산화, solver, 평가, 결과다. node 선택↔Settings↔실제 영역 강조를 연결한다.

1. CAD 없이 새 PDE 문서를 만든다. 지원 수학적 영역을 정의하거나 정확한 mesh revision을 가져온다.
2. 방정식/약형식 입력에서 선언 변수·성분·연산·단위/차원과 backend 지원 범위를 검사한다. 식 검사를 실행과 분리한다.
3. BC/IC node에서 대상 차원·영역 필터로 선택하고 이름·개수·mesh 개정을 표시한다.
4. space·차수·이산화·비선형/시간 solver·수렴/출력을 편집한다. Runner에서는 host/자원만 고른다.
5. 실제 지원 adapter로 평가하고 기준해·다른 mesh/solver 결과를 같은 오차 정의로 비교한다.
6. field는 Research의 지원 field 보기 또는 ParaView로, 1D 응답은 공통 곡선으로 본다. COMSOL을 내장한다는 뜻이 아니다. 복잡한 후처리는 정확한 결과를 ParaView에 연다.

ODE도 독립 변수/상태/초기조건을 같은 equation 연구 영역에서 표현한다. 이를 CAD prep 문서로 강제하지 않는다. 임의 Python 텍스트를 입력 즉시 실행하는 editor로 만들지 않는다. 사용자 구현은 명시 등록된 adapter/모듈·버전·입출력 계약과 별도 실행 경로로 다룬다.

mesh의 geometry/좌표·차원·order·connectivity·영역 태그 의미·단위·경계 대응을 함께 확인한다. CAD 없어도 domain/mesh가 있으면 작업한다. reader/solver가 없는 상태에서도 식·자료·과거 결과를 연다.

### 6.4 UI09 — Numerical

**배치:** HyperStudy형 왼쪽20–25% Plan/평가절차/변수/응답/방법/실행 트리, 중앙 조밀한 설정/후보 표, 하단 선택 후보의 곡선·분포와 Messages. 변수/목표 요약을 실행 중에도 유지한다.

평가절차는 단계·입력 문서·adapter·전달·출력/추출 응답의 트리/표로 편집한다. 정확한 참조를 실제 문서에 남긴다. 초기부터 범용 그래프 실행기를 만들지 않으며 Workbench graph와도 중복하지 않는다.

변수표: 원 owner/대상, 단위, 현재값, 범위, 고정/자유, 공유/시험별, 타입/제약. 관측표: 자료 개정, 채널/구간, 잔차, 가중치, 정규화, train/holdout, 누락·실패 규칙.

“기준 평가 / 모델 동정 / DOE / 최적화 / 영향도”를 구별한다. 대리모델 학습을 모델 동정과 같은 fit 버튼으로 섞지 않는다. UQ·대리모델·다목적의 UI도 같은 변수/응답/후보 표를 재사용한다. 구현 전 가짜 결과는 표시하지 않는다.

| 방법 node | Settings/직접 표 입력 | 결과와 선택 연결 |
|---|---|---|
| UQ | 분포·계수·범위·상관/독립 가정·표본 설정 | 응답 분포/구간·실패 표본, 선택 표본의 실제 입력/결과 |
| 대리모델 학습 | 학습/검증 자료·입력 범위·모델 설정 | 예측–관측/오차 그림, 원 solver 결과와 대리 예측 구별 |
| 다목적 | 목표별 최소/최대 방향·단위·제약/허용치·목적축 | Pareto 점↔후보표↔정확한 결과, infeasible 후보/사유 보존 |
| 최적화/영향도 | 방법·예산·중지 기준·대상 변수/응답 | 실제 반복·제약·국부 영향/분석 범위, 선택 반복의 원 입력 |

후보표는 실제 후보 ID·입력·응답·유효 여부·실패·검색 penalty·유효 목적값·원 결과를 별도 열로 둔다. Ctrl/Shift 선택은 해당 곡선/원 입력을 함께 강조한다. 결과가 없는 후보는 값이 없는 상태로 남긴다.

채택은 owner별 변경 목록과 현재 입력과의 차이를 보인 뒤 해당 owner의 새 revision/분기로 전달한다. 다중 owner 변경은 모두 준비한 후 묶음 참조를 게시한다. 선택/정렬만으로 채택하지 않는다.

이번 실행 전체 취소는 새 후보 제출을 멈추고 진행 작업 종료를 추적한다. 선택 job 취소와 구별한다. 늦은 결과를 보존하되 탐색/자동 채택을 재개하지 않는다. 기존 엔진의 재개 기능이 없는 방법은 새 실행으로 표시한다.

후보 점수 비교에 쓸 관측/mask/가중치/정규화/누락 규칙은 실행 전에 고정한다. DOE 표준화 다변수 최소제곱은 표본·제외·rank/condition·범위를 보여주며 Sobol 민감도나 인과 증명으로 부르지 않는다.

### 6.5 UI10 — Runner

**배치:** 상단 작업 메뉴/제출·검사·취소, 위쪽 약45–55% job 표, 아래 선택 job의 입력/진행/진단/로그/결과 탭. monitor는 별도 창으로 분리할 수 있다. 이 상세 배치는 우리 설계이며 현행 Abaqus 버튼을 확인한 것처럼 쓰지 않는다.

기본 열은 이름·고정 입력·backend·host·상태·시작/경과·attempt·결과 유무다. 같은 이름도 job ID로 구별한다. wall time과 물리 시간/증분·수렴 상태를 구분한다.

물리 step·적분/수렴/안정화·출력은 원 domain에서 편집한다. Runner는 host/queue/workdir·전송·CPU/memory/실행 수명만 소유한다. 실제 binary/build/library/thread/GPU/precision은 실행 기록으로 남긴다.

로그는 따라가기/일시정지/찾기/원파일 열기를 제공한다. 실패 진단은 가능한 원 객체/셀로 이동한다. cancel 요청과 실제 종료를 구별한다. 지원하지 않는 즉시 중단은 “요청 기록, 중단 가능 지점 대기”로 표시한다.

재시작으로 추적이 끊긴 작업은 현재 계약대로 INTERRUPTED다. 기존 입력/로그/부분 결과를 열고 명시 재실행은 새 attempt다. 중단된 외부 프로세스가 실제로 종료됐는지 알 수 없다면 “종료 미확인”을 함께 표시하며 동일 작업 폴더를 재사용하지 않는다.

인프라 재시도는 같은 입력의 새 attempt, 수치 정책 변경은 새 입력/Run이다. 짧은 material/in-memory 평가 모두를 별도 영구 job으로 만들지 않는다. 상위 fit/DOE와 작은 evaluation ID의 관계를 유지한다.

### 6.6 UI11 — Expert

**배치:** Co-STORM처럼 왼쪽230–300DIP 논점 지도/토론 목록, 중앙 가장 넓은 실제 다자 발언, 하단 고정 사용자 입력·reply 대상·첨부 근거, 필요할 때 오른쪽 근거/Plan 상세. 상단에는 참여 역할·진행 상태·대화/정리 보기.

직접 질문·자료·기존 결과에서 시작한다. 참여 역할·자료 범위를 설정하고 실제 발언의 작성 주체를 남긴다. 정적 페르소나 카드나 KPI 대시보드로 대체하지 않는다.

발언 클릭↔논점 강조, 논점 클릭↔관련 발언 이동, reply 대상 지정, 원문 위치/동일 결과 열기, 사용자 반론/새 관측 첨부를 제공한다. 가정·관측·계산·미확인을 구별한다.

“계산 계획으로 작성”은 옆의 실제 Numerical Plan 초안을 연다. 변수·평가기·응답·범위·예산을 편집한 뒤 명시 실행한다. 이미 허용된 연구 범위 안에서 매 후보마다 재승인을 요구하지 않는다. 실제 job/result가 발언에 연결되고 후속 질문은 그 결과를 읽는다.

토론 일시정지는 후속 발언/새 제안을 멈춘다. 진행 solver 취소는 해당 실행의 범위로 따로 한다. 중간 발언은 중단 상태로 남긴다. provider 오류 시 원 발언·근거를 보존하고 재개/새 요청을 명시한다.

전체 다자 발언·논점 지도·reply·사용자 개입·pause/resume는 제품 UI 설계에 포함한다. 기존 ExpertRuntime.plan/ask를 이 전체 기능의 구현으로 확대하지 않는다. AI가 없어도 과거 토론과 질문 초안은 열고 저장한다.

### 6.7 UI12 — 선택 Workbench

**배치:** 기본 문서/연결 목록, 연결 보기에서는 왼쪽 도구·문서 목록, 중앙 연결도, 오른쪽 선택 문서/연결 상세. 필요할 때만 그래프를 사용한다.

클릭은 선택, 더블클릭은 정확한 owner 문서/결과 열기다. 문맥 메뉴는 열기/연결 정보/다른 revision 연결/연결 해제다. drag는 가능한 입력과 전달될 개정을 미리 보여주고 Esc로 취소한다. 목록과 메뉴로도 같은 연결을 만든다.

연결은 자료→관측, mesh→PDE, Material→지원 FE 할당, 고정 입력→job, 결과→비교처럼 실제 참조다. 변환/mapping/추출이 있으면 그것을 소유한 문서/recipe로 연결한다. 그래프 자체가 새 계산 엔진이 아니다.

원 문서가 바뀌어도 연결된 이전 개정은 유지한다. “새 개정 있음”과 “참조 끊김”은 다르다. 연결 갱신은 영향과 owner별 준비 상태를 보인 뒤 게시한다. 다른 도구의 원본을 그래프에서 몰래 수정하지 않는다.

---

## 7. 화면 상태와 실제 복구

| 상태 | 보여줄 대상·표시 | 사용자의 실제 다음 행동 |
|---|---|---|
| 빈 문서 | 빈 트리/표/3D, 새 객체·열기 위치 | 자신의 파일 열기/객체 추가 |
| 직접 편집 | 변경 셀/객체·미저장·현재 선택 | Enter/Task 확인, Esc 취소, Undo |
| 적용 전 | pending 속성과 마지막 적용 입력/출력 구별 | Apply/Reset. 다른 pending 작업 자동 적용 금지 |
| 잘못된 입력 | 해당 셀/식/피처/조건에 오류와 이동 가능한 진단 | 대상 수정/연결 복구/invalid draft 저장 |
| 계산 중 | 출발 snapshot, 실제 단계·로그, 현재 초안 변경 여부 | 다른 초안 편집/상세 상태/범위에 맞는 취소 |
| 취소 중 | 취소 범위·새 제출 중지·아직 종료 안 된 작업 | 종료 확인, 부분 결과 열기 |
| 실패 | 실패한 객체/후보/attempt·진단·부분 결과 | 원 입력 열기/수정 후 새 입력 또는 명시 retry |
| 결과 도착 | 어느 입력의 결과인지, 성공/부분/invalid | 원값 확인/이전 결과 비교/명시 채택 |
| 입력 변경 후 오래된 결과 | 결과 입력과 현재 초안의 차이 | 이전 결과 유지/새 평가. 자동 바꿔치기 금지 |
| 저장 실패 | 미저장 유지·실패 파일·이전 저장본 | 경로 수정/다시 저장/이전본 열기 |
| 파일 이동/내용 변경 | 이전 경로·일치 여부·영향받는 branch | 같은 내용 위치 수리 또는 새 입력 개정 |
| 연결 끊김 | host/session 상태·마지막 관측 시각 | native 창 재연결/다시 조회. 성공 응답 금지 |
| 미지원 backend/버전 | 지원되는 읽기/편집과 막힌 실행 위치 | 문서·과거 결과 사용, 지원 실행 환경 선택 |

메시/곡선/이미지의 표시 축약, solver 종료 상태, 결과 유효성, 공학 승인 상태는 서로 다른 표시다. UNKNOWN/NOT_RELEASED는 필요한 기준이 없는 판단에 남기며 원 결과를 지우거나 숫자0으로 바꾸지 않는다.

---

## 8. 사용자에게 보여줄 세 연속 작업

아래 순서는 수용 장면이다. 다른 진입점을 막는 고정 wizard가 아니다.

### 8.1 지그 설계·변경 → 계산 → Post 비교 → 설계로 복귀

| 장면 | 사용자의 실제 조작 | 다음 화면으로 전달/유지되는 것 |
|---|---|---|
| 1. 직접 시작 | Pre에서 자신의 FCStd 또는 지원 CAD 열기, 원본/편집본 확인 | 문서 ID, native 이력, 원파일과 단위 |
| 2. 설계 | 스케치 지지 간격·두께 등 실제 치수 수정→피처 재계산 | 선택 피처, 새 설계 generation, 변경 검사 |
| 3. 조립 | 부품 배치→기준 고정→관절 축·한계→운동과 필요 경로 | 부품 정의/Link, 관절/시간/추적점 |
| 4. 해석 준비 | 같은 창에서 Analysis와 해석용 표현, 포함/제외·공유/접촉 경계 지정 | 설계 개정과 해석용 형상의 대응 |
| 5. 대상 지정 | 지지면·하중면·측정점/게이지 구간 영역 지정 | 실제 대상 강조, 방향·측정 정의 |
| 6. mesh 개선 | 전체/국부 크기→생성→나쁜 요소 선택→설정 변경·재생성 | mesh 개정, 품질표, 영역 연결 |
| 7. 조건·검사 | 재료/단면/조건·출력 설정→오류 행 수정→실행 검사 | 유효 입력 snapshot, 미확인 공학 기준 별도 |
| 8. 실제 실행 | 지원 backend 제출→진행/실패/취소 확인 | 동일 input/job/attempt/result |
| 9. 기준안 관찰 | 정확한 결과를 Post에 열기→변형/반력/게이지 곡선·저장 측정 | 기준 결과 A, 측정/비교 정의 |
| 10. 설계 변경 | Post의 입력 문서 열기→새 개정에서 지지·형상·지원 체결 조건 수정 | 기준 입력은 보존, 변경안 draft |
| 11. 재연결·계산 | 끊긴 면/관절 참조 수리→재mesh/조건 검사→변경안 실행 | 변경 입력과 결과 B |
| 12. 비교·판단 | 같은 게이지·반력·강성·측정오차의 A/B·차이·변화율, field 나란히 | 실제 값과 입력 차이, 채택/보류·근거 |
| 13. 저장·재개 | 관련 문서 저장→owner 종료→다시 열기→피처/조건 편집 계속 | native 편집성, 두 결과, 계산식·판단 보존 |

첫 수치 왕복은 기존 단일 최종 solid·10절점 사면체·지원 하중/구속 경로로 연결할 수 있다. 이것으로 조립/접촉/체결 지그 연구 전체를 통과시켰다고 하지 않는다. **조립·관절·운동과 일반 CAD 편집은 동시에 제품 기능으로 연결하며**, 실제 다부품 지그의 하중 전달·접촉·장비 장착 검토는 해당 adapter가 지원하는 범위를 추가로 닫는다.

변경 mesh의 field 차이를 급조하지 않도록 수용을 나눈다. 같은 mesh의 기준 쌍에서는 field 차이/변화율을 실제 검증한다. 실제 형상이 바뀐 지그에서는 동일 정의 응답의 차이/변화율과 field 나란히 보기를 통과시킨다. 이후 검증된 공간 mapping을 지원한 경우에만 해당 장 차이를 추가한다.

### 8.2 외부 결과만 열기 → 측정·비교 → 저장

1. Post 직접 시작, 외부 시계열 A를 native reader로 열고 실제 time/field/단위를 확인한다.
2. Slice plane을 드래그하고 원점·법선을 숫자로 고쳐 Apply한다. 원 source는 남긴다.
3. 원 절점/요소를 선택하고 표에서 ID·좌표·값을 확인해 저장 측정으로 만든다.
4. Plot Selection Over Time, Plot Over Line으로 곡선을 만든다. 실제 시각/경로·보간·gap을 확인한다.
5. 결과 B를 추가한다. A/B·unit·기저·위치·시간 대응을 정하고 가능한 field/curve의 차이·변화율을 계산한다.
6. 선택 위치의 A/B 원값과 계산식을 확인한다. 표/곡선/field/그림을 각각 내보낸다.
7. 분석 프로젝트를 저장하고 새 ParaView owner에서 연다. 원 solver 없는 환경에서도 보존 결과와 분석 정의를 확인한다.
8. 원파일 하나를 이동한 조건에서 정상 branch를 먼저 열고 같은 내용으로 경로를 복구한다.

이 장면은 Pre·Material·Data 문서를 만들지 않고 통과해야 한다.

### 8.3 독립 연구 → 수치 탐색 → 실제 결과 → 전문가 논의

Data에서 다른 열 순서·단위의 두 시험을 연다. 열/구간을 선택해 Material의 관측 또는 PDE의 함수로 연결한다. Material은 계수·이력의 직접 평가를, PDE는 식·space·BC의 직접 평가를 수행한다.

같은 Numerical Plan 편집기에서 변수·응답·학습/holdout·예산을 편집한다. 실제 다중 시험 동정과 별도 복수 변수 DOE를 실행하고 실패 후보·원 결과·영향도를 연다. 후보 채택은 원 domain의 새 revision이다.

선택 결과를 Expert에 근거로 첨부한다. 논점/발언을 선택하고 사용자가 반론·추가 관측을 넣는다. 다음 Plan을 편집해 실행한다. 닫고 다시 열어도 동일 결과·논점·Plan을 볼 수 있어야 한다.

PDE 단독 또는 기존 결과→Numerical 분석→Expert로도 시작한다. 외부 batch는 기존 입력/출력 manifest를 이용해 파일·후보·단위·성공/실패를 대응하며 원 solver가 설치됐다고 전제하지 않는다.

### 8.4 세 사례의 역할과 물리 수용

| 사례 | 제품에서 실제 해야 할 비교 | 기술 검증과 실제 업무 판단의 경계 |
|---|---|---|
| A. J2/von Mises 대 DP | 인장·압축·구속·제하의 재료점, 동일 FE 조건, p–q 경로·항복·소성/잔류변형 | 정확한 DP variant·부호·유동/경화·응력 척도, 계수 식별/고정/미식별, holdout, 증분/mesh 오차를 구별. 항복=불량 아님 |
| B. 재료와 지그 영향 | 장비/게이지 응답, 마찰·강성·편심·지원 체결 가정, 실제 지그 변경안 | 게이지 상대점·방향·길이·영점, 장착→체결→하중→제하 상태 유지. 단일 총 변위 곡선만으로 원인 식별하지 않음 |
| C. 열팽창·계면·뒤틀림 | 완전접합/탄성/손상 계면, 온도 이력·곡률·개구·잔류변형 | 무응력 온도, 손상·재닫힘/압축 전달, 점탄성 회복/관측 시점, 벌크 소성과 계면 손상 구별. 단일 주기를 피로 수명으로 확대하지 않음 |

합성/해석해/공개 자료로 구현을 검증하는 장면과 사용자 실제 재료·장비·공차·불량 기준으로 유효성을 판단하는 장면을 별도 기록한다. 실제 기준이 없으면 공학 판단 UNKNOWN이다. 이를 화면·수치 기능 미구현을 숨기는 표식으로 사용하지 않는다.

---

## 9. MCP와 실제 열린 문서의 연결

### 9.1 확인한 기존 경로와 확장 구조

현재 확인된 경로:

~~~text
openscience/workbench_mcp.py
    → caelab/workbench_client.py
    → apps/lab/server.py / workbench_routes.py
    → 기존 Workbench 서비스 / JobManager / adapter
~~~

현재 MCP는 FastMCP의 stdio를 사용한다. CAELAB_SERVICE_URL을 읽으며 MCP 프로세스 자체가 새 Lab controller를 만들지 않는다. client는 localhost/127.0.0.1의 HTTP에 제한되어 있고 기본 server port는8766이다. 이 경로는 계산·자료·결과·자문 API이며 열린 FreeCAD/ParaView 문서 편집까지 구현됐다는 뜻이 아니다.

**확장 그림**

~~~mermaid
flowchart TB
  AI["OpenScience / 허용된 로컬 AI 클라이언트"] <--> MCP["기존 stdio MCP"]
  MCP <--> HTTP["기존 Client / 로컬 HTTP"]
  HTTP <--> SVC["기존 공통 서비스 + 문서 라우팅"]
  SVC <--> CAD["FreeCAD 내부 bridge / 열린 CAD 문서"]
  SVC <--> POST["ParaView 내부 bridge / 열린 Post 문서"]
  SVC <--> RES["Research 문서 owner / 실제 편집기"]
  SVC <--> RUN["기존 JobManager / 수치 엔진 / adapter"]
  RUN --> OUT["고정 입력 / 실제 결과 / 실행 기록"]
  OUT --> POST
  OUT --> RES
~~~

새 부분은 **문서·host 등록/라우팅과 native bridge**다. 계산 엔진이나 작업 관리기를 새로 만들지 않는다. native bridge가 별도 파일 복사본을 편집하거나 GUI 밖 FreeCADCmd/pvpython을 실행해 현재 창을 제어했다고 응답하면 실패다.

### 9.2 owner·프로세스·주 스레드

| 대상 | 실제 owner | 실행 위치 | 서비스의 역할 |
|---|---|---|---|
| CAD/Assembly/FEM | 해당 FreeCAD 프로세스의 열린 문서 | native GUI 주 스레드의 명령/transaction | 정확한 host/doc로 라우팅, 입력/결과 등록 |
| Post pipeline/view | 해당 ParaView 프로세스/session | native GUI 주 스레드의 proxy/명령 | 명령 라우팅, reader/result/비교 참조 |
| Data/Material/PDE/Plan | 기존 로컬 서비스에 붙인 문서 owner | 문서별 직렬 처리 | draft·generation·저장·도메인 명령 |
| 수치 실행 | 기존 수치 엔진/JobManager | 계산 worker·지원 solver | 실행 수명·로그·취소·결과 보존 |

FreeCAD/ParaView Python 모듈을 Research 환경에 억지로 import하지 않는다. native bridge는 각 앱의 Python/Qt·plugin 방식에 맞춘 얇은 확장이다. Python으로 필요한 native Undo/selection/GUI thread 접근이 안 되면 해당 bridge만 native plugin으로 구현한다. 이 기술 시험이 전체 UI를 웹으로 바꾸는 이유가 되어서는 안 된다.

**로컬 통신의 구체적 권고**

1. launcher가 기존 service의 상태·store를 확인하고 없으면 해당 사용자 권한으로 시작한다.
2. native 시작 확장이 service에 host_id, process-start session, app/version, doc 목록과 지원 명령을 등록한다.
3. 별도 native 외부 포트를 열지 않는다. bridge의 가벼운 I/O worker가 기존 loopback HTTP에서 자기 명령을 가져오고 상태/결과를 돌려보내는 방식을 우선 구현한다.
4. 가져온 명령은 Qt queue를 통해 GUI 주 스레드에 전달한다. native 객체를 I/O thread에서 바꾸지 않는다.
5. 실제 native handler를 호출하고 native 객체/proxy에서 결과를 다시 읽은 뒤 성공 응답을 낸다. 화면 렌더 완료와 모델 변경 완료가 다르면 구별한다.
6. native 사람이 수행한 변경/Undo/Redo도 observer가 같은 문서 상태에 반영한다. MCP 읽기는 필요할 때 owner에 직접 재조회하여 최신성을 확인한다.

제안 endpoint: hosts/register, hosts/{id}/commands/next, hosts/{id}/events, documents, documents/{id}/commands, commands/{id}. 모두 기존 /api/workbench 아래에 추가할 후보다. 실제 route를 추가한 것으로 기록하지 않는다. 단순 전달 대기열은 JobManager를 대체하는 새 scheduler가 아니다.

긴 mesh 계산은 frozen 형상을 기존 worker에서 처리하고 결과를 GUI thread의 한 적용 명령으로 가져올 수 있다. 이것은 계산 분리다. 다른 복사본에서 끝낸 문서 편집을 현재 열린 문서의 성공으로 대신하면 안 된다. native filter의 취소 가능성은 실제 기능에 맞춰 표시한다.

### 9.3 동일 명령의 의미와 대상 선택

GUI 버튼/셀과 MCP wrapper는 **같은 owner의 같은 typed domain handler**를 호출한다. native GUI에서는 기존 QAction/Task/Property의 실제 편집 기능을 사용하고, MCP는 그 기능의 프로그램 입력 경로를 호출한다. native 기능을 MCP 안에서 또 구현하지 않는다.

각 변경 명령은 다음을 가진다.

~~~json
{
  "document_id": "doc-fixture-01",
  "host_id": "freecad-host-02",
  "session_id": "owner-start-epoch",
  "expected_generation": 41,
  "command_id": "unique-command-uuid",
  "target": {"object_id": "stable-object-id", "property": "Length"},
  "value": {"number": 12, "unit": "mm"}
}
~~~

이는 예시이며 현재 API에 이 구조가 구현돼 있다는 뜻이 아니다. 대상은 표시명이나 active document가 아니라 정확한 문서·객체·인스턴스/속성이다. native 내부 이름도 형상 개정과 함께 사용한다.

- generation은 편집 내용의 증가 번호다. Undo로 되돌아가도 번호를 되감지 않는다.
- 선택·카메라 같은 보기 변화는 별도 view 상태/일련번호로 추적해 값 읽기를 명확히 하되, 카메라 이동만으로 수치 입력 전체를 stale로 만들지 않는다.
- 변경 직전에 **owner에서** generation과 target을 다시 확인한다. service cache 검사만으로 끝내지 않는다.
- 사람이 Task/셀을 미확정 편집 중이면 그 상태를 읽기 결과에 알린다. 겹치는 변경은 BUSY_EDIT, 오래된 값은 STALE_DOCUMENT다. AI가 사용자의 편집을 자동 닫거나 덮어쓰지 않는다.
- document_read의 최신 조회는 owner 응답을 기다린다. 연결이 끊겼으면 마지막 관측 시각과 cached 상태를 구별하고 현재 값이라고 반환하지 않는다.
- 다른 창을 앞으로 가져오는 동작은 명시 activate 요청에 한정한다. read마다 초점을 빼앗지 않는다.
- command_id로 중복 적용을 막는다. 응답이 끊겼다면 command status를 먼저 조회하고 결과 미확인 상태에서 변경 명령을 자동 재전송하지 않는다.
- 재시작 전 session은 거절한다. host가 다시 등록한 뒤 열린 문서를 대조하여 새 session으로 읽는다.

### 9.4 GUI ↔ MCP 기능 대응표

아래에서 **기존**은 실제 읽은 MCP tool 이름이다. **신규**는 제안한 tool 이름이며 각 도메인 handler를 호출하는 얇은 wrapper다. 이름을 확정할 때 기존 등록 명령과 중복을 제거한다.

모든 신규 편집 입력에는 위 문서/session/generation이 공통으로 붙는다. 반환에는 실제 적용 상태·새 generation·바뀐 대상·진단이 붙는다.

| GUI 실제 작업 | MCP 이름·상태 | 주요 입력 | 바뀌는 문서/화면·반환 |
|---|---|---|---|
| 설치/지원 계산 목록 | backends_list, 기존 | 없음/지원 범위 | backend 설치·지원 목록. GUI에서는 같은 표 |
| 열린 창/문서 목록 | documents_list, 신규 | store/host/kind 필터 | doc/host/session/dirty/지원 기능 |
| 새 문서·파일 열기 | document_open, 신규 | kind, 등록 file ref, open mode | 맞는 실제 owner·창·doc ID, reader/파일 오류 |
| 문서/대상 읽기 | document_read, 신규 | doc, object/property 범위, fresh | 현재/미확정 값·단위·generation |
| 창·문서 활성화 | document_activate, 신규 | doc/host/view | 실제 활성 대상, 다른 문서 내용은 불변 |
| 트리/3D/표 대상 선택 | document_select, 신규 | object/instance/entity IDs, view | 같은 열린 화면의 선택·실제 대상 목록 |
| 저장/닫기/분기 | document_save / document_close / document_fork, 신규 | 위치, 기대 상태, 명시 close 선택 | committed revision 또는 save/dirty 오류 |
| CAD/입력 내보내기 | document_export, 신규 | 정확한 대상·형식·용도·허용 위치 | 실제 native/exporter와 같은 검사, 파일 ref 또는 차단 |
| Undo/Redo | document_undo / document_redo, 신규 | 정확 owner, 기대 generation | native/도메인 같은 undo, 바뀐 대상 |
| 파일 위치 복구 | document_repair_sources, 신규 | 이전 ref→등록 새 file ref | 내용 일치/새 revision 필요, 영향 branch |
| 스케치 생성/기하 편집 | cad_sketch_edit, 신규 | Body/평면, 기하·구속의 typed 변경 | 실제 Sketcher 객체, 진단 위치 |
| 치수/속성 입력 | cad_parameter_set, 신규 | 객체/속성·값·단위 | 같은 native 치수/Property와 재계산 상태 |
| 피처 생성/수정 | cad_feature_edit, 신규 | 지원 feature, profile/axis·값 | 실제 이력 노드, shape/recompute 결과 |
| 재계산·형상 검사 | cad_recompute / cad_validate, 신규 | 문서/범위 | 실제 실패 feature·형상 검사 |
| 연구 변수 등록 | cad_parameter_register, 신규 | 정확 native 경로·단위·타입 | domain 변수 ID, 영향/지원 검사 |
| 부품 배치 | cad_assembly_edit, 신규 | 부품 ref/Link, 배치·기준 고정 | 같은 조립의 실제 인스턴스 |
| 관절 생성/변경 | cad_joint_edit, 신규 | 두 참조·축/offset/한계·종류 | 관절·자유도/참조 오류 |
| 운동 생성/재생 설정 | cad_motion_evaluate, 신규 | 관절·식·시간·간격 | operation ID, frame/path ref, 실패 시간 |
| 추적점·경로 | cad_trace_define, 신규 | 인스턴스·로컬 위치/점·motion ref | 저장 trace, 좌표/시간 표 |
| 영역·연결 복구 | cae_region_edit / cae_reference_repair, 신규 | 대상 목록·개정·새 대응 | 실제 3D 영역과 끊긴 연결 진단 |
| 전체/국부 mesh 설정 | cae_mesh_configure, 신규 | geometry ref·요소·크기·region | native mesh 설정, 재생성 필요 |
| mesh 생성/품질 조회 | cae_mesh_generate / cae_mesh_quality, 신규 | 설정 ref, 지표·부분 조회 | operation/mesh ID, 요소 표·분포·실제 선택 |
| 재료/단면/조건 | cae_assignment_edit / cae_condition_edit, 신규 | Analysis·영역·law/조건·값·단위 | native 객체/화살표, 지원/단위/대상 오류 |
| 계산 전 검사 | calculation_prepare, 신규 | domain snapshot·지원 adapter | 준비 입력 ref·검사/차단 위치 |
| 실제 제출 | calculation_submit, 기존 | operation, arguments, request_id, resources | 실제 job ID. 준비 ref 사용은 기존 인자 계약 확장 필요 |
| 진행/상태 | job_status, 기존 | job_id | 같은 Runner job 상태·진단 |
| 선택 작업 취소 | job_cancel, 기존 | job_id | 취소 요청/실제 종료·보존 결과 |
| fit/DOE 전체 취소 | numerical_execution_cancel, 신규 | plan execution ID | 새 제출 중지·진행 종료 추적 |
| 실제 결과/응답 읽기 | result_read, 기존 | job_id, responses 또는 selection | 같은 결과의 선택 응답. 둘을 동시에 쓰지 않음 |
| reader 후보·결과 열기 | post_readers / post_open_result, 신규 | 등록 result/file ref·reader ID | 살아 있는 reader/source, missing arrays/단위 |
| field/time/범례·카메라 | post_view_set, 신규 | view/source·field/component/association·actual time | 같은 열린 view와 실제 적용 시간 |
| 절점/요소·원값 | post_select / post_values_read, 신규 | source rev·ID namespace/IDs·time | 3D/표 선택, 요청한 행·단위·위치 |
| Slice/Clip/Warp/Contour | post_filter_edit, 신규 | filter/input ref·typed properties | native pending 노드/오류 셀 |
| Apply/Reset | post_apply / post_reset, 신규 | 명시 node 집합·기대 상태 | 실제 적용 노드/출력 또는 충돌 |
| probe/선/시간곡선 | post_measurement_edit, 신규 | 원ID 또는 좌표·추적 규칙·시간/경로 | 저장 measurement·curve·mask |
| A/B·차이/변화율 | post_compare, 신규 | A/B refs·quantity·단위/기저/시간/공간·식 | 비교 노드·실제 파생 ref 또는 차단 사유 |
| 결과/표/그림 출력 | post_export, 신규 | output ref·포맷·범위·허용 위치 | 실제 파일 ref·크기·내용 확인값 |
| Data 열/단위/구간/mask | data_edit, 신규 | channel IDs·typed cell/metadata/selection 변경 | 같은 workbook/graph·오류 행 |
| Data 변환 | data_transform, 신규 | 입력 revision·지원 recipe/설정 | 새 출력/recipe ref·진단, 원자료 유지 |
| Material 계수/이력 | material_edit, 신규 | law/protocol/상태·값·단위 | 같은 계수표·이력곡선 |
| 직접 재료점 평가/보존 | material_evaluate / material_retain_result, 신규 wrapper | 유효 snapshot·보존 대상 | 기존 evaluation 호출, 입력/곡선/진단 ref |
| PDE 식·space·BC | pde_edit / pde_validate, 신규 | typed equation/model·mesh/대상 ref | 같은 node/Settings·문법/단위/지원 오류 |
| Numerical Plan 편집 | numerical_plan_edit, 신규 | 변수/응답/방법/예산 patch | 같은 독립/embedded Plan |
| fit/DOE/optimize/analyze | calculation_submit, 기존 경로 재사용 | 해당 operation·고정 Plan 인자 | 기존 수치 엔진·상위 job, 후보/evaluation ref |
| 후보 채택 | numerical_candidate_adopt, 신규 | candidate ref·owner별 기대 revision | 새 owner revision 또는 충돌/부분 준비 |
| 전문가 목록/자문 | experts_list / expert_ask, 기존 | expert_id, question, context, session_id | 실제 자문 job. 다자 UI 구현과 별개 |
| 편집 계산계획 제안 | calculations_plan, 기존 | request | 검증된 편집 초안. 실행 아님 |
| 자료 검색/원문 | knowledge_search / knowledge_source, 기존 | query/collections 또는 doc/revision/locator | 실제 근거와 원문 위치 |
| 논문 검색 | literature_search, 기존 | query/providers | 실제 검색 job |
| 토론·논점·reply·중지 | expert_discussion_edit / expert_discussion_control, 신규 | discussion/topic/reply·행동 | 같은 토론 창·실제 상태, 외부 provider 작업 구별 |
| Workbench 연결 | project_reference_edit, 신규 | owner refs·관계·기대 참조 | 실제 연결/영향, owner 원본 수정 안 함 |
| 큰 배열/파일 부분 조회 | artifact_read, 신규 | 등록 ref·field/row/time/region 범위 | metadata·제한된 값 또는 접근 가능한 파일 리소스 |

cad_sketch_edit 같은 명령은 임의 Python/eval 문자열이 아니다. 지원되는 기하/구속 종류와 값만 받아 native handler에 전달한다. 기존 임의 module/command/path 삽입 제한을 우회하지 않는다.

### 9.5 긴 작업·큰 결과·알림

- 짧은 편집은 applied와 새 generation, 긴 계산/mesh/filter는 accepted와 command/operation/job ID를 먼저 반환한다.
- 조회는 phase, 실제 진행량, log cursor, 상태, input snapshot, attempt, 진단을 돌려준다. 총량이 없으면 percent를 null/미정으로 둔다.
- GUI는 같은 ID를 구독/조회한다. MCP는 기존 job_status polling을 우선 사용한다. client가 지원하는 알림은 별도 capability로 붙이며 현재 구현으로 주장하지 않는다.
- native 문서 작업의 진행·취소 handle과 영구 계산 job을 구별한다. 모든 필터/직접 평가를 새 durable job으로 강제하지 않는다.
- 중단 불가능한 native 작업에 즉시 CANCELLED를 반환하지 않는다. 취소 요청/실제 종료/마지막 성공 출력 보존을 표시한다.
- 결과 응답은 input ID/hash, result ID, producer/version, field·단위·위치·실제 시간, validity, 원파일/파생 ref를 가진다.
- 큰 mesh/field를 대화 본문으로 전송하지 않는다. 배열 목록·크기·범위·선택값·행 페이지·시간/경로 구간을 요청하고 큰 결과는 등록된 파일/MCP resource로 읽는다.
- 파일 경로 문자열만 반환하고 AI가 읽은 것처럼 말하지 않는다. 접근 불가이면 부분 읽기나 허용된 리소스를 제공한다.
- 현재 HTTP의 JSON·upload 제한은 작은 명령/자료용이다. 대형 native 결과는 승인된 local root/파일 등록과 참조를 확장해 쓰고 JSON에 통째로 넣지 않는다.

사람과 AI의 결과 동일성은 입력 ID/hash·result ID·recipe revision·field/time/selection을 함께 대조한다. screenshot 모양이 같다는 이유로 동일 결과라고 판단하지 않는다.

### 9.6 Windows 설치·시작과 MCP 등록 예

**현재 소스로 확인한 실행 형태**

~~~powershell
caelab serve --store "C:\CAEProjects\Lab" --port 8766 --workbench-config "C:\CAEConfig\workbench.json"
~~~

~~~powershell
$env:CAELAB_SERVICE_URL = "http://127.0.0.1:8766"
python -m openscience.workbench_mcp
~~~

명령 구문·환경변수·module은 확인했다. 위 경로, Windows 번들/설치 성공, config 내용은 확인한 사실이 아니라 설치 예시다.

**stdio client 등록 예 — 제안 설치 경로**

~~~json
{
  "mcpServers": {
    "autonomous-cae-lab": {
      "command": "C:\\CAE-Lab\\runtime\\python.exe",
      "args": ["-m", "openscience.workbench_mcp"],
      "env": {
        "CAELAB_SERVICE_URL": "http://127.0.0.1:8766"
      }
    }
  }
}
~~~

client별 설정 위치는 그 client의 실제 규약을 따른다. 이 예에 비밀값은 넣지 않는다. 기존 client의 local token 처리·server의 Host/Origin/쓰기 검사를 재사용하고 새 native routes에도 적용한다.

**설치 UX**

1. Research/Core와 CAD·Post 패키지 설치/찾기 항목을 제공한다. CAD 미설치로 Research 실행을 막지 않는다.
2. 처음에는 작업 폴더와 설치된 backend/reader를 확인한다. 미지원 계산 때문에 문서 열기를 막지 않는다.
3. 도구 바로가기를 열면 필요한 service를 찾거나 시작하고 정확한 store/host를 표시한다. 여러 서비스가 있으면 연결된 문서 목록을 통해 고른다.
4. FreeCAD/ParaView 확장은 native 시작 때 host를 등록한다. AI가 없어도 GUI와 service 경로로 작업한다.
5. AI를 사용할 때만 stdio MCP를 client에 등록한다. OpenScience 전용 기능을 non-AI 사용의 의존성으로 넣지 않는다.
6. 브라우저의 원격 AI가 사용자 PC의 stdio/127.0.0.1에 자동 접근한다고 가정하지 않는다. 로컬 connector/허용된 client가 필요하며 네트워크 포트나 터널을 임의 공개하지 않는다.
7. Linux 서버는 별도 Runner 자원/adapter 경로다. 로컬 문서·native 창은 그대로 유지한다. 기존 SSH/queue 지원 여부를 확인하고 전송 입력·작업 위치·원격 실행 기록·돌아온 결과를 고정한다.

### 9.7 실제 연결 완료 시험

| 장면 | FreeCAD에서 확인 | ParaView에서 확인 |
|---|---|---|
| 사람→AI | 같은 열린 문서 치수 변경, MCP 최신 읽기 값·단위 일치 | field/time/필터 속성 변경, MCP 실제 source/값 일치 |
| AI→사람 | 유효한 조건/치수 변경, 같은 Tasks/3D 갱신 | Slice plane/field/time 변경, 같은 View/표 갱신 |
| invalid | 대상 셀/조건/피처 오류, 실행 거절 | 잘못된 배열/시간/비교 대응 오류, 파생 계산 거절 |
| 동시 편집 | 두 창·두 문서에서 정확한 대상, stale/BUSY 거절 | pending Apply 보호, 다른 Layout/source 미변경 |
| 실제 결과 | 해당 snapshot 실행 결과 ID를 반환 | 사람이 같은 결과를 열고 원값·A/B/차이를 확인 |
| Undo/재시작 | native undo와 generation, 새 owner 재열기 | pipeline/metadata undo, 저장 측정·비교 재열기 |
| 연결 끊김 | 성공 응답 금지, 재연결 후 최신 재조회 | 복제 pvpython 결과로 대체 금지 |

---

## 10. 재사용·신규 연결·미확인 구분

아래 공개 코드 평가는 a10f2023… 기준이다. 최신 로컬 변경과 대조한 뒤 실제 작업 파일을 확정한다.

| 기능 | 기존 프로그램에서 그대로 쓸 부분 | 우리 코드의 확인된 재사용 | 새로 연결·개발 | 아직 확인할 것 |
|---|---|---|---|---|
| native Pre 시작/파일 | FreeCAD 문서·작업대·선택·FCStd | apps/desktop_pre/cae_prep.py의 복사/hash·열기/saveAs·native 명령·선택 inspector | 일반 문서 owner·bridge·관리 저장 | Windows 창/저장·Link/Undo |
| CAD 설계 | Sketcher/PartDesign/Property/Tasks | 기존 CAD 변수 발견/fixture adapter의 해당 범위 | 일반 대상 등록·편집 효과·변경 진단 | fixture 외 두 번째 모델 |
| 조립·운동 | Assembly/Link/joint/Simulation | fixture_assembly.py의 지정 fixture 생성 | 임의 조립 편집 연결·trace/경로·참조 복구 | 통합 저장·재열기, 한계/실패 frame |
| mesh | Gmsh/국부 MeshRegion·native FEM 객체 | native_structural_mesh_worker.py, assembly_mesh.py의 제한된 생성/면 대응/품질 검사 | 품질표·실제 요소 선택·일반 영역·전후 비교 | 요소별 품질 범위, 다부품·혼합 차원 |
| 조건·입력 | native FEM Tasks·solver 객체·deck 작성 기능 | 기존 native/fixture 조건 catalog·단위/대상 검사 | 일반 영역/조건 편집·adapter 지원표·Runner 제출 | contact/preload/explicit/비선형 개별 지원 |
| Post 시작/reader | ParaView reader·pipeline/view | startup.py, build_workspace.py, prepare.py | 빈 분석·일반 외부 결과·reader 선택 | 형식/시계열/큰 결과별 실제 reader |
| Post 표시/측정 | ColorBy/selection/Slice/PlotOverLine/Spreadsheet | commands.py의 표시·단면·고정 peak probe | 임의 source/field/ID·저장 측정/시간곡선 | proxy/selection/undo main-thread 연결 |
| Post 비교 | native View/Calculator/resampling 도구 | prepare.py의 exact mesh 검사·B−A·% | 고정 A150N/B200N 제거·비교 editor·의미 검사 | 일반 필드·기저·time·mapping |
| Post 저장 | SaveState/LoadState/파일 chooser | save_project/verify_sources/verify_retained_readers | committed 저장·dirty/close·부분 복구 | 현재 PVSM+JSON 순차 쓰기의 교체 |
| Data/곡선 | Origin은 UX 참고만 | 자료 등록/원본 hash/표 reader | Data owner·편집 표·공통 곡선/recipe 편집 | 결측/비단조·큰 자료·교정 metadata |
| Material | MCalibration은 UX 참고만 | evaluation.prepare/evaluate/save_evaluation/read_result·FELUPE | 계수/protocol/draft/Undo·응답·Plan 연결 | 현재 모델 외 law/상태/접선·FE 변환 |
| PDE | COMSOL은 UX 참고만 | 기존 지원 PDE adapter·benchmark 경로 | PDE 문서·식/space/BC 편집·mesh 연결 | 실제 backend와 Windows/원격 가용성 |
| Numerical | HyperStudy는 UX 참고만 | fit_model/run_doe/optimize/analyze_candidates 등 기존 엔진 | 같은 Plan editor·후보/실패·원 결과·채택 | 방법별 실제 범위·재개/취소 |
| Runner | job monitor의 UX 참고 | JobManager·workbench_routes·client | desktop 목록·로그/상태·입력/결과 이동 | 자식 process 종료·remote 수명 |
| Expert | Co-STORM 논점/대화 UX | ExpertRuntime.plan/ask·knowledge·callbacks | 다자 UI·reply·pause/resume·Plan/result 연결 | 실제 provider 조합·중단/재개 |
| MCP | MCP stdio 규약 | workbench_mcp.py→client→server | native/연구 문서 typed tools·host 라우팅 | 실제 동일 열린 문서·장애/중복 |

### 10.1 기존 시안을 일반 제품으로 볼 수 없는 구체적 이유

- Pre fixture 생성·발견 경로에는 고정된 형상/파라미터 가정이 있다. 해당 adapter는 지원 fixture에 그대로 쓰고 일반 모델 editor의 성공으로 확대하지 않는다.
- assembly mesh 코드의 일부 부품/볼트 비활성·샘플 Jacobian 확인은 전체 조립 역학·볼트 preload의 검증이 아니다.
- native structural mesh worker의 단일 최종 solid·tetra10·유일 면 대응은 유용한 실제 연결이지만 일반 혼합 요소/조립 지원 완료가 아니다.
- 공개 Post는 특정 CalculiX step·하중 A/B와 U_mm·고정 peak 선택에 맞춰져 있다. 이 계산·검사 코드를 재사용하되 사용자 선택 모델로 일반화해야 한다.
- 현재 Post PVSM/JSON 순차 저장은 다중 파일 committed 저장과 동일하지 않다.
- 현재 계산 API의 존재는 편집 가능한 Data/Material/PDE owner·Undo 또는 열린 native 창 조작의 존재를 증명하지 않는다.

---

## 11. 구현 작업표와 순서

### 11.1 병행 구조

**첫 통합 묶음의 주 흐름은 Pre–Runner–Post다.** 같은 시점에 독립 Post와 독립 Research를 진행한다. 공통 문서 연결은 필요한 명령부터 붙이며 모든 domain을 위한 새 대형 framework 완성 뒤에 UI를 시작하지 않는다.

- 공통 담당: 기존 서비스·파일 등록·문서/host 식별·명령/저장·상태 계약.
- CAD/FE 담당: native 편집·조립·mesh/조건·복구·실제 제출/결과 연결.
- Post 담당: 독립 reader·필터/측정·일반 비교·저장·native bridge.
- Research 담당: 표/곡선 공통 UI, Data/Material/PDE/Plan, Runner/Expert 연결.
- 통합 담당: 각 변경을 같은 실제 업무에서 연결하고 범위/증거를 기록한다. 동일 공통 파일 수정은 한 owner가 통합한다.

아래 파일명 중 “신규 제안”은 아직 존재한다고 주장하지 않는다.

| ID | 기능/작업 대상 | 선행 | 사용자가 보는 결과 | 실제 완료 시험 |
|---|---|---|---|---|
| T01 | 공개/로컬 변경 대조, 기존 launcher/adapter 지원표 고정 | 없음 | 설치된 기능·미지원 이유가 맞는 메뉴 | 4fd9cea 변경 파일을 a10f…와 대조, 이름만 보고 기능 추정 안 함 |
| T02 | 기존 server/routes/client에 문서·host 등록/typed dispatch 추가. 신규 document_commands/host_bridge 후보 | T01 | 열린 창·문서가 정확히 연결 | 두 host·두 doc, stale/BUSY/재시작 세션 거절 |
| T03 | 공통 저장/참조 게시·path repair·migration | T01, T02 최소 계약 | Save/Close/Open, 실패 시 draft·이전본 유지 | 필수 파일 중간 실패·이동/변경·cold reopen |
| T04 | Windows launcher/서비스 수명·패키지 시작 | T01 | WSL 없이 도구 직접 실행/파일 열기 | 깨끗한 Windows 환경·한글/공백 경로·여러 창 |
| T05 | cae_prep.py에 native bridge/관리 저장 연결 | T02, T04 최소 시작 | GUI 치수와 MCP 값 일치 | 동일 실제 문서 변경 양방향, native Undo/Save |
| T06 | Sketcher/PartDesign·일반 변수 등록·효과 검사 | T05 | 자신의 부품 직접 편집·이력 재편집 | fixture 외 모델, invalid feature·재계산·저장 |
| T07 | Assembly/Link/joint/Simulation·trace UI 연결 | T05, 기존 native 명령 | 부품/관절/운동/경로 편집 | 지정 두 부품 외 모델, frame 실패·통합 저장 재편집 |
| T08 | 해석용 표현·영역·재료/단면·조건 편집 | T05, 기존 adapter | 실제 대상·화살표·조건 목록 | 하중/구속 단위/방향·누락/중복·미지원 차단 |
| T09 | Gmsh/국부 설정·품질표·요소 선택 | T08 | 나쁜 요소 선택→설정 수정→재생성 | 실제 mesh 변화·품질 계산·전후 보존 |
| T10 | 변경 영향/영역·관절·조건 재연결 | T06–T09 관련 부분 | 끊긴 참조 목록과 3D 복구 | 형상/면 개수 변경, 모호한 자동 연결 거절 |
| T11 | Analysis frozen 입력→기존 adapter/Runner | T08–T09, T02 | CAD에서 실제 계산·취소·원 결과 열기 | 현재 지원 단일 solid 경로 우선, 입력 변경/늦은 결과 |
| T12 | Post startup/build_workspace 일반화·native bridge | T02, T04 최소 시작 | CAD 없이 외부 결과 열기 | 실제 두 입력/시계열·reader 선택·원 solver 미설치 |
| T13 | Post filter/selection/measurement/curve | T12 | 절단·원ID·probe·시간/경로곡선 | native 선택↔표, pending/Apply/Undo·gap |
| T14 | Post comparison 일반화·같은 mesh 및 응답 비교 | T12–T13, 기존 prepare 비교 | A/B·차이·변화율·원값/식 | A=0/단위/기저/실제 time, 다른 mesh 차단 |
| T15 | Post 관리 저장/경로 복구 | T03, T12–T14 | 분석 저장/재열기·누락 branch 복구 | 새 ParaView owner·source 변경·선택 측정 복원 |
| T16 | Pre↔Runner↔Post 왕복 UI | T11–T15 핵심 | 실제 설계 변경과 두 결과 비교 | §8.1 전체, 같은 mesh 장 차이 + 변경 지그 응답 차이 |
| T17 | Data owner·표/곡선/recipe 컴포넌트 | T02–T03 | 독립 workbook·처리·관측 | 다른 열/단위 두 파일, 원값/mask·저장 |
| T18 | Material owner·계수/protocol/직접 평가 UI | T02–T03, 기존 evaluation | MCalibration형 실제 계수·이력·응답 | 직접/이전 비교·invalid draft·cold reopen |
| T19 | 동일 Numerical Plan·fit/DOE/후보/채택 | T17/18 또는 지원 외부 evaluator | 실제 다중 시험 fit·복수 변수 DOE | holdout·실패·순위 규칙·전체 취소·owner 채택 |
| T20 | Runner desktop·로그/진단/result 연결 | 기존 JobManager, T02 | 독립 job 표/monitor와 같은 job | 취소/실제 종료·INTERRUPTED·명시 attempt |
| T21 | PDE owner·식/space/BC·지원 평가 | T02–T03, 실제 PDE adapter | CAD 없는 PDE 직접 연구 | 식 수정→실제 해→기준/mesh 비교→재편집 |
| T22 | Expert 근거/Plan/result 연결·Co-STORM 전체 UI | 기존 ExpertRuntime, T19/20 핵심 | 논점/다자 발언/반론/일시정지 | 실제 provider 발언·reply·계산 후속·저장 |
| T23 | Study/Workbench 목록·연결도 | T02–T03·각 owner open | 선택적 연결 탐색/정확한 문서 열기 | drag/menu 같은 참조, stale·부분 실패 보존 |
| T24 | A/B/C용 law·contact·열/계면·수치 검증 | 해당 domain/adapter, T16/19/21 | 실제 경쟁 가설과 설계 판단 | §8.4 각 독립 기준·수치 오차·실제 자료 별도 |
| T25 | implicit/explicit·외부 batch·UQ/대리/MOO·원격/규모 | 해당 기존 엔진·T19/20/21 | 지원 방법별 실제 화면/결과 | 각 방법/solver 지원 입력·실패·결과·재개 |
| T26 | 전체 Windows 업무·성능·원형 대조·배포 | 각 기능 구현에 병행 | 전문 프로그램 밀도·키보드·큰 자료 | 실제 창/배율·긴 표·많은 곡선·큰 모델·취소 |

T05/T12/T17/T18/T20은 공통 계약의 최소 부분이 준비되는 대로 병행한다. T07 조립을 Material 뒤로 미루지 않는다. T22의 전체 토론 UI는 실제 계산 연결과 분리해 일찍 구현할 수 있고, 실결과 연결 시험은 T19/20과 합친다. T25라는 큰 항목은 실제 착수할 때 solver/방법별로 나누되 나머지 범위를 삭제하지 않는다.

### 11.2 묶음별 실제 인도물

| 묶음 | 반드시 보여줄 것 | 이것만으로 완료라고 부르지 않을 것 |
|---|---|---|
| G0. 연결 기반 | Windows 별도 환경에서 native 한 문서씩 양방향 편집/읽기·저장, Research 독립 시작 | Linux cloud의 기능 API 성공, 비슷한 mockup |
| G1. 첫 사용 연결 | Pre 편집→지원 mesh/조건→실제 job→Post 원값/비교→설계 변경, 독립 외부 Post 저장 | 탄성 재료점 한 곡선·고정 fixture 한 버튼 |
| G2. 전문 작업 깊이 | 조립/관절/경로·국부 mesh 품질/복구, Data/Material/Plan 실fit·DOE, CAD-free PDE, Expert 실제 근거 | 단계별 화면은 있으나 Save/Close/Open이 끊기는 상태 |
| G3. 전체 연구 수용 | A/B/C, 주요 implicit/explicit·외부 batch·UQ/대리/MOO·다자 토론·선택 그래프·규모/원격 | 세 사례나 52행 체크만 채우고 일반 도구를 생략 |

G0·G1은 작업 착수 순서이며 제품 범위 축소가 아니다. 이후 기능을 막연한 “향후”로 두지 않고 T07–T26의 실제 대상·선행·통과 장면으로 관리한다. 개발 기간이나 인력일은 현재 근거 없이 고정하지 않는다.

### 11.3 검증을 끝내는 기준과 진행 보고

native 기능 자체를 재입증하는 시범은 기존 기록을 활용한다. 추가 시험은 문서 bridge/Undo/저장/실제 작업을 막는 구체적 위험을 해결할 때만 한다. 한 기능의 설치/화면 자동화 실패에 전체 개발이 묶이면 원인·재사용 경계·대안을 기록하고 독립 lane을 계속 진행한다.

사용자가 중단한 로컬 FreeCAD 세션은 다시 사용하지 않는다. 필요한 Windows 검증은 별도 cloud/시험 환경에서 수행한다. Linux의 가상 화면 결과를 Windows 사람 조작성으로 바꾸어 기록하지 않는다.

진행 점검은 문서 개정 횟수나 질문 횟수가 아니라 다음 네 가지를 보고한다: 실제 바뀐 코드/연결, 사용자가 끝낸 작업, 실패와 남은 장애, 다음 통합 결과. 구현이 없으면 그 사실과 이유를 쓰며 “이번 요청은 기획뿐”이라고 사용자 의도를 바꾸지 않는다.

---

## 12. 기존 문서에서 실제로 바꿀 항목

| 위치/기존 문제 | 대체할 본문·그림·수용 기준 |
|---|---|
| 제품 설명의 Pre/Post 또는 세 진입점만으로 도구 독립성 설명 | §1–2의 workspace/host 구분·직접 파일 열기·여러 문서 수명 |
| PrepDocument가 자료/재료점/PDE까지 소유하는 잔재 | domain별 owner와 정확 참조. material assignment와 law 연구 분리 |
| UI 부록 W1의 보편적 오른쪽 Property/Tasks 또는 동일 3칸 틀 | UI01–03 native 작업별 배치와 직접 조작 |
| W2의 고정 A/B·오른쪽 native Properties | UI04 기본 단일 Render/왼쪽 Pipeline, UI05 필요 시 비교 Layout |
| 모든 UI에 같은 preview/apply/adopt를 요구 | native Task/Apply/즉시 표시·문서 채택의 서로 다른 의미 |
| Data–Material을 나머지 제품 착수 조건으로 둔 S1/S2/S3 순서 | T05/T12/T17/T18/T20 병행, G1 Pre–Runner–Post 실제 왕복 |
| Windows 배포·문서 수명을 후반 단계로만 둠 | T04/G0부터 native Windows·같은 owner·파일 경로 검증 |
| 기존 MCP 계산 기능을 열린 GUI 제어로 읽을 수 있는 설명 | §9 기존 tool과 신규 native bridge/typed tool 표 |
| native 저장/PVSM export를 Lab 저장으로 보는 표현 | 관리 Save 관문·필수 파일 완성→참조 게시·cold reopen |
| Optimization 후보를 항상 새 PrepDocument로 보냄 | 원 domain owner별 새 revision/분기·다중 owner 채택 |
| R17 재료점 연구를 Pre 기능으로 쓰는 대응 | Material 연구·공통 Plan·지원 FE adapter로 수정 |
| R19 공통 experiment를 모든 물리의 새 schema로 해석 | 공통 식별·입출력/참조만 공유하고 native/도메인 형식 유지 |
| 52개 요구·17UC를 범위 상한/완료 개수로 사용 | 누락 점검과 실제 독립/연결 업무 수용의 대응표 |
| 합성 HTML/native 제한 시안을 최종 화면처럼 사용 | 보존 근거로 별도 표시, 실제 원형/기획도/구현 화면 구별 |

이 변경은 이름 바꾸기나 면책 문구 추가가 아니다. owner, 실제 화면 배치, 저장 동작, MCP 경로, 구현 선행관계와 완료 장면을 교체한다.

### 12.1 확정할 설계와 실제 시험으로 정할 것

**지금 확정:** 전체 도구 역할·독립 진입, 같은 CAD 창의 깊은 편집, native Post 독립 분석, 문서 owner, 동일 GUI/MCP 기능, 위 화면 배치/조작/상태, 원형 대조, Pre/Post 병행 순서, 수치/AI 역할, 비교·보존·UNKNOWN 규칙.

**기술 시험으로 선택:** 각 native build의 Python/Qt/plugin 접점, native Task/Undo observer와 저장 staging, 연구 표/차트 구현 라이브러리와 Qt 패키징, reader별 실제 지원, mesh/접촉/solver adapter 범위, thread/GPU/원격 수명. 이 항목은 UI 기획을 미루는 이유가 아니라 해당 T작업의 구현 결정을 내릴 입력이다.

**실제 사용자 자료 때만 필요한 입력:** 제품/지그 파일, 재료/시험 이력, 장비·게이지 정의, 실제 불량·공차·제작 승인 기준. 자료가 없으면 합성/공개 입력의 기술 시험부터 진행한다. 이미 합의된 제품 목적·CAD 깊이·독립성·GUI 기술을 다시 질문하지 않는다.

### 12.2 구현 전에 남는 핵심 위험

1. native 수동 변경을 observer가 놓치면 generation만 있어도 GUI/MCP 동일성이 깨진다. 객체 값·Task pending·Undo·다중 창을 실제로 대조한다.
2. Save 단추를 native 파일 저장에만 연결하면 Lab 연결/결과를 잃는다. 관리 문서의 모든 저장 진입을 같은 관문으로 묶는다.
3. 설계 조립과 해석용 표현 사이의 면/접촉 의미가 사라질 수 있다. 단일 meshing object 제한을 단순 fuse로 감추지 않는다.
4. ParaView의 자동 conversion·근접 time·동적 selection은 그럴듯한 틀린 비교를 만들 수 있다. 실제 대상/연산 정의를 저장하고 불가 항목을 계산 위치에서 해결한다.
5. fixture/고정 A/B adapter를 UI만 일반화하면 다른 입력에서 무너진다. 두 번째 형상/자료/결과를 초기 수용에 포함한다.
6. Linux/cloud API 통과가 Windows 전체 업무 성공은 아니다. 별도 실제 Windows 프로세스·파일·화면 조작이 필요하다.
7. 기존 protocol/solver/Expert 기능을 이름만 보고 지원 완료로 쓰지 않는다. 설치·메뉴 노출·입력 변환·수치 검증·사용자 수용을 따로 기록한다.

### 12.3 17개 사용 사례의 범위 점검

| UC | 주 진입·필요한 도구 | 이 계획에서 확인할 핵심 |
|---|---|---|
| 01 공급사 시간의존 재료 | Data/Material/Plan/Post | 단위/시험 이력·다중 자료·속도/온도·holdout |
| 02 반복 소성 | Material/Plan/FE | 상태/제하·반복 이력·잔류 응답 |
| 03 적분·접선 | Material/PDE/검증 | 증분·내부상태·접선 기준 |
| 04 비선형 PDE 비교 | PDE/Runner/Post | 식/space·mesh/solver 오차 |
| 05 포장 낙하 | CAD/FE/explicit/Runner/Post | 조립·접촉/IC·시간/에너지·failure |
| 06 과열 불량 | PDE/CAD/FE/Post | 온도장·열/구조 연결·실제 기준 |
| 07 접착/박리 | Material/FE/Post | 계면 법칙·강도/에너지·관측 |
| 08 접촉 수렴 | CAD/FE/Runner/Post | 접촉 설정·증분/수렴·원 진단 |
| 09 지그 설계 | CAD/FE/Plan/Post | 편집·장착/제작성·측정오차·변경안 |
| 10 실험/기존 결과 상관 | Data/Post/Numerical | 원 solver 없이 열기·위치/시간 대응 |
| 11 공차/물성 산포 | Numerical/각 owner | 분포/상관·실패 표본·원 결과 |
| 12 다음 시험 선택 | Expert/Plan/Data | 경쟁 가설·미식별·실험 구별력 |
| 13 대리/다목적 | Numerical/Runner/Post | 학습검증·Pareto·실제 후보 채택 |
| 14 불량/VOC 자문 | Expert/Data/Post | 원문·실제 근거·반론·미확인 |
| 15 논문 재현 | Expert/각 domain/Runner | 구현/설정/단위·원 입력·오차 |
| 16 미세구조/연성/원격 | PDE/Material/FE/Runner | 지원 adapter·연결/변수·원격 기록 |
| 17 ASCII+LLM+실제DOE | Data/Expert/Plan/Runner | 편집 Plan·실제 영향도·후속 연구 |

52개 원 요구는 기존 번호를 유지해 owner/작업/수용에 연결한다. 본문에서 그 번호를 재정의하거나 새 52행만을 완료 기준으로 만들지 않는다.

---

## 13. 근거 목록과 구현자에게 필요한 원문

### 13.1 직접 조회한 제품 문서

- [제품 Page, 조회한 저장본16](https://chatgpt.com/space/page_d99abd5a046c8191b16263e448c8d8ee)
- [화면·조작 Page, 조회한 저장본21](https://chatgpt.com/space/page_e314876e22bc8191b562de881de7f3b6)

현재 링크는 나중에 새 저장본을 보여줄 수 있다. 여기서 읽은 시점은16/21이다.

### 13.2 공식 native/UI 자료

| 자료 | 확인 내용과 한계 |
|---|---|
| [FreeCAD FEM 공식 안내, 2025-09-16](https://blog.freecad.org/2025/09/16/getting-started-with-fem/) | 실제 Gmsh/Force 그림, FEM 작업 구조. 현재 제품 실행 증거 아님 |
| [FreeCAD MeshRegion 공식 archive](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/FEM_MeshRegion.md) | 국부 크기·대상 선택·부모 mesh Apply로 재생성 |
| [FreeCAD Sketcher 공식 archive](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Sketcher_Workbench.md) | 기하/구속 편집. archive와 pin의 메뉴 차이 주의 |
| [FreeCAD1.1.4 Assembly 명령 소스](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Assembly/CommandCreateAssembly.py) | 배포 pin의 명령 이름/단축키 |
| [FreeCAD1.1.4 joint 명령](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Assembly/CommandCreateJoint.py) | 관절 명령 |
| [FreeCAD1.1.4 Simulation 명령](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Assembly/CommandCreateSimulation.py) | Simulation/V. wiki 표기와 구별 |
| [ParaView6.2 Introduction](https://docs.paraview.org/en/v6.2.0/UsersGuide/introduction.html) | native dock/뷰·GUI. GUIOverview 그림 자체는5.12.0-RC3 |
| [ParaView6.2 Loading Data](https://docs.paraview.org/en/v6.2.0/UsersGuide/dataIngestion.html) | reader/시리즈/GUI와 Python reader 선택 차이 |
| [ParaView6.2 Filtering](https://docs.paraview.org/en/v6.2.0/UsersGuide/filteringData.html) | 실제 filter·pipeline·resampling |
| [ParaView6.2 Selecting](https://docs.paraview.org/en/v6.2.0/UsersGuide/selectingData.html) | 원 선택·표·조건 선택·저장 제한 |
| [ParaView6.2 Saving](https://docs.paraview.org/en/v6.2.0/UsersGuide/savingResults.html) | state/data/image 내보내기, 재열기 |
| [ParaView GUI tutorial](https://docs.paraview.org/en/v6.2.0/Tutorials/ClassroomTutorials/beginningGUI.html) | 분할·카메라 링크·native 뷰 |
| [ParaView 설정](https://docs.paraview.org/en/v6.2.0/ReferenceManual/customizingParaView.html) | Auto Apply/Auto Convert Properties |
| [ParaView Color Mapping](https://docs.paraview.org/en/v6.2.0/ReferenceManual/colorMapping.html) | 범례/색 범위 |
| [Origin GUI](https://docs.originlab.com/tutorials/origin-gui/) | workbook/graph/선택/metadata. 자료 내 최소 버전 표기와 최신판 여부 구별 |
| [MCalibration Quick Tutorial](https://www.ansys.com/content/dam/resource-center/datasheet/mcalibration-quick-tutorial.pdf) | p5/p12 실제 이미지, 화면6.0.0. 상용 의존성 도입 아님 |
| [COMSOL6.3 Desktop](https://doc.comsol.com/6.3/doc/com.comsol.help.comsol/comsol_ref_environment.18.02.html) | Figure2-1 Model Builder/Settings/Graphics |
| [COMSOL Weak Form](https://doc.comsol.com/6.3/doc/com.comsol.help.comsol/comsol_ref_equationbased.32.023.html) | equation UI 참고, 모든 기능 지원 약속 아님 |
| [HyperStudy2024 UI](https://2024.help.altair.com/2024/hwdesktop/hst/topics/chapter_heads/workspace_r.htm) | 실제 workspace 그림·Explorer/표·Messages |
| [Abaqus 공식 교육 요약, 2018](https://www.3ds.com/fileadmin/PRODUCTS-SERVICES/SIMULIA/RESOURCES/abaqus_unified_intro-summary.pdf) | job/monitor 구조. 현행 상세 화면 확보했다고 하지 않음 |
| [Co-STORM 논문v2 Figure15](https://arxiv.org/html/2408.15232v2) | 실제 논점/발언/참여 화면 |
| [Workbench2026R1 객체 조작](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/wb2_help/wb2h_start_projobj.html) | 선택/더블클릭/문맥 메뉴·연결 UX |
| [MCP2025-11-25 transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) | stdio/전송 역할. 기존 구현은stdio |
| [MCP tool 규약](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) | typed tool·구조화 반환의 근거 |

### 13.3 공개 코드 확인 링크

모든 링크는 확인 시점 공개 커밋에 고정했다.

- [Pre 진입/선택/native 명령](https://github.com/pikachu444/autonomous-cae-lab/blob/a10f2023a2084512839b5e0af8ab0adc0aeb9293/apps/desktop_pre/cae_prep.py)
- [Post build_workspace](https://github.com/pikachu444/autonomous-cae-lab/blob/a10f2023a2084512839b5e0af8ab0adc0aeb9293/apps/desktop_post/build_workspace.py)
- [Post commands](https://github.com/pikachu444/autonomous-cae-lab/blob/a10f2023a2084512839b5e0af8ab0adc0aeb9293/apps/desktop_post/commands.py)
- [Post prepare](https://github.com/pikachu444/autonomous-cae-lab/blob/a10f2023a2084512839b5e0af8ab0adc0aeb9293/apps/desktop_post/prepare.py)
- [현재 MCP tool](https://github.com/pikachu444/autonomous-cae-lab/blob/a10f2023a2084512839b5e0af8ab0adc0aeb9293/openscience/workbench_mcp.py)
- [현재 HTTP client](https://github.com/pikachu444/autonomous-cae-lab/blob/a10f2023a2084512839b5e0af8ab0adc0aeb9293/caelab/workbench_client.py)
- [현재 server](https://github.com/pikachu444/autonomous-cae-lab/blob/a10f2023a2084512839b5e0af8ab0adc0aeb9293/apps/lab/server.py)
- [현재 routes](https://github.com/pikachu444/autonomous-cae-lab/blob/a10f2023a2084512839b5e0af8ab0adc0aeb9293/apps/lab/workbench_routes.py)
- [현재 Workbench 서비스](https://github.com/pikachu444/autonomous-cae-lab/blob/a10f2023a2084512839b5e0af8ab0adc0aeb9293/caelab/workbench.py)
- [현재 JobManager](https://github.com/pikachu444/autonomous-cae-lab/blob/a10f2023a2084512839b5e0af8ab0adc0aeb9293/caelab/jobs.py)

### 13.4 Codex가 대조·제공할 정확한 추가 자료

기획 진행은 위 원문으로 완료할 수 있다. 구현 작업을 실제 파일에 배정하려면 **Codex가** 다음을 대조하면 된다.

1. 4fd9cea의 docs/PRODUCT_PLAN.md, docs/PREPOST_APP_SPEC.md, PROJECT_SCOPE.md, ADR/0060-independent-research-workspaces.md와 공개 a10f… 이후 diff.
2. 위 공개 Pre/Post/MCP/client/server/routes/JobManager에 로컬 변경이 있다면 변경 파일과 diff. 기존 노출 명령·launcher/config의 실제 등록 위치도 함께 제시.
3. 현재 고정한 runtime/adapter 지원표와 FreeCAD·ParaView 배포 명령, 실제 보존한 통합 저장 실패 로그의 경로. 새 시험을 돌리라는 요청이 아니라 기존 근거의 정확한 연결이다.

이는 사용자에게 전체 계획을 다시 고르라고 묻는 질문이 아니다. 사용자가 원하는 제품을 기준으로 확정한 작업을 실제 코드에 배정하기 위한 개발자 간 인계 항목이다.

최종 상태: 이 문서와 별첨은 전체 제품의 상세 설계 산출물이다. 기존 클라우드 FreeCAD 두 workflow의 FAIL/내부 PARTIAL, 조립/FEM 통합 저장 미검증, Windows 실제 조작성·동일 native GUI/MCP 미검증을 변경하지 않는다. 제품 소스·원본 Pages·저장소 문서는 이번 작성에서 수정하지 않았다.


