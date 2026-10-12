# Desktop screen specification — D1

요청 PRO-DESKTOP-DESIGN-20261012-01. 아래 state boards는1440×900의 편집 가능한 제품 기획 시안이다. `screens/screens.json`은 화면 ID, owner, 정확 좌표, text/shape layer, hotspot/action/target, 필드 형식·unit·기본·범위·종속성, function과 scenario를 가진다. SVG의 텍스트·선·면은 raster flatten이 아닌 편집 객체다. PNG는 빠른 시각 확인용이다. 모두 **SIMULATED UI**, synthetic fixture이며 Qt/native/solver/provider 실행 화면이 아니다.

## 1. 정보 구조와 도구별 배치

공통 title/menu/toolbar/status는 Windows 문서 수명을 제공한다. 작업영역은 도구의 핵심 판단에 따라 다르다. 일률적인 properties form이나 대시보드 KPI로 대체하지 않는다.

| 도구 | 기본 배치 / 1440×900 | 사용자가 주로 선택하는 객체 |
|---|---|---|
| Data | source/recipe tree214; 중앙1198 workbook 위·curve 아래; mapping 때 원본→canonical 표 | sample/channel ID, role/unit conversion, 구간/mask |
| Material | tests/coefficients446; curve963; 하단 residual/candidates; 같은 Plan 열과 source 상태 | protocol·계수·관측/예측/잔차·candidate availability |
| FreeCAD Pre | native tree/Tasks267; 3D772–864; 선택 작업에만 condition dock; quality/reference 표 하단 | feature/entity/face set/mesh element/pose |
| ParaView Post | native pipeline/properties269; 기본 single3D842; 필요시 A/B562씩; 측정/비교표 하단 | source/array/association/actualtime/originalID/probe |
| PDE | model tree224,selected-node370,field808; 하단 equation/error/result 표 | equation/field/space/domain/BC node |
| Evaluation | definition tree227,stages/transfers/iterations 같은 중앙영역; 하단 실제 stage 결과 | existing Evaluation stable stage/port/iteration |
| Numerical | Plan tree224, 설정/변수/후보 조밀표; 결과영역 method별 curve/hist/Pareto | typed variable/observation/candidate/method |
| Runner | job table 상단45%; selected attempt 로그/입력/진단 하단55% | job/attempt, actual observation/terminal/ref |
| Study | 질문·가설304,근거 행렬1106,명시 판단·다음 시험 | hypothesis/evidence relation/decision |
| Expert | topic270,thread754,evidence/Plan377; reply composer 하단 고정 | authored turn/topic/reply target/source |
| Workbench | 문서목록256,연결 view811,선택 link333 | exact revision link; double-click same owner |

`HOME-EMPTY`는 선택적인 파일/도구 chooser다. 각 독립 shortcut은 해당 owner/editor로 직접 시작한다. 동일 문서가 열려 있으면 기존 owner를 활성화한다. port/service URL/ID를 사용자에게 필수 입력시키지 않는다. 세 native runtime을 하나의 process로 억지 통합하지 않는다.

## 2. 시각 규칙과 실제 창 검토 조건

기준은 white table/plot, pale-gray docks, slate 제목·상태, blue selection/focus, teal valid, amber unresolved/pending, red error, purple Plan owner다. 상태는 색만이 아니라 아이콘/텍스트·이유로 식별한다. warning을 옅은 회색 도움말로 숨기지 않는다. 본문 font는 Windows Segoe UI/Malgun Gothic, 표13–14DIP, dock title12–13DIP bold, title14DIP, 입력·button30DIP, table row29DIP, outer gap8–12DIP다. 수치 셀은 tabular digits와 단위 머리글, 소수점 정렬을 구현 시 적용한다.

현재 SVG/PNG 예시는 영어 컨트롤을 사용한다. PNG 렌더는 제공된 DejaVu font를 사용했고 실제 Windows 한국어 label/font/DPI 검증은 하지 않았다. 한국어 text 확장·IME 조합·Minus/Greek glyph·단위 윗첨자와 native 번역을 Windows 검증 항목으로 남긴다. font를 작게 줄여 fit하지 않는다.

Dock 최소 폭은 Data source180,Pre/ Post260,Material coefficient380,PDE model200/settings300,Numerical tree200,Study hypothesis260,Expert topic220/side300DIP다. plot/3D 최소 usable 폭은480DIP, 최소 높이280DIP를 목표로 한다. 공간 부족 시 오른쪽 context dock을 tabify/닫기 가능한 overlay로 전환하고 하단 결과를 탭으로 접는다. 핵심 오류띠·현재 owner·실제 input/result/time은 유지한다. 중앙을 모두 scrollbar로 감싸 작은3D만 남기지 않는다. native dock behavior/restore geometry를 재사용한다.

1440×900와1920×1080 실제 창에서100/125/150%를 검토하고200%에서 keyboard 접근/잘림을 확인한다. 논리DIP와 물리screen pixels를 섞지 않는다. 작은 창은 dock 접기/restore와 최대화로 조작을 보장한다. 이 시안 파일의1440×900 출력 자체를 DPI 통과로 부르지 않는다.

## 3. 메뉴·toolbar·keyboard·selection

| 동작 | Research | native Pre / Post와의 연결 |
|---|---|---|
| Ctrl+O | kind-aware chooser / 등록 위치 / 최근 문서 | native Open 결과를 같은 등록·managed open으로 연결 |
| Ctrl+S | focus owner 저장; 메뉴에 owner 이름 표시 | managed Pre: pose restore→save gate; managed Post: 분석 저장. stock 다른 session 전역 설정을 변경하지 않음 |
| Ctrl+Shift+S | branch / portable copy with exact dependencies | native source export와 managed project copy를 명시 구별 |
| Ctrl+W / Alt+F4 | per-owner dirty/buffer와 job을 분리한 close dialog | native Task/pose restore/미저장 처리 연결; window close≠cancel |
| Ctrl+Z / Ctrl+Y | 포커스 owner의 명령명·대상 표시; generation 증가 | native Undo transaction/observer,Post pipeline Undo; camera Undo 별도 |
| F2 / Enter / Tab / Esc | cell edit/commit/next/cancel buffer; invalid raw draft 선택 가능 | native Task/field 규칙 유지; Esc가 job kill이 되지 않음 |
| F6 / Shift+F6 | dock 순환, focused title/outline 표시 | tree→Tasks→3D→diagnostics focus; keyboard 선택 대안 |
| Ctrl+F / Ctrl+G | 표/로그 찾기 / sample or object locator | source/ID namespace를 먼저 식별; active source만 추정하지 않음 |
| Ctrl / Shift selection | 불연속/연속 row·curve·face selection | exact IDs, selected count·unit·source/revision 상시 표시 |

단축키 충돌은 native context를 우선 점검한다. QAction에 표시된 동작명과 shortcut을 통합하고 테스트는 실제 설치 version/언어에서 한다. 키만 보내고 결과를 추정하지 않는다. 명령/실행 중에도 접근 가능한 Cancel/status가 있어야 한다.

표 row 선택↔원sample marker↔source/revision은 양방향이다. 곡선 brush는 time/row/axis 구간 모드를 명시하고 release 때 한 selection 변경, drag중 preview만 한다. Data quality exclude와 Plan train/holdout은 다른 context-menu 동작이다. 숨김은 계산 제외가 아니다. 선택 표시 축약 여부·실제 전체 sample count·원값 조회를 제공한다.

Pre selection은 object/face/edge/vertex filter와 activeAnalysis를 보인다. Face set의 Add/Remove는 keyboard/list로도 수행한다. rebind preview drag는 old/new 대응표를 갱신하며 Apply 전 원ref를 바꾸지 않는다. 모호한 가까운 면을 자동으로 붙이지 않는다. Post의 selection은 point/cell/original ID/probe를 구별한다. filter3D widget drag는 native pending properties로 반영되고 Apply 범위를 벗어난 다른 pending branch를 자동 적용하지 않는다.

필수 동작은 drag/double-click만으로 존재하지 않는다. 모든 graph link·face add·plot range는 menu/button/locator 대안을 가진다. 보드 hotspot은 single click 전이를 검토하는 도구이고 제품의 double-click/open·drag-preview→Apply semantics는 함수 명세와 위 규칙을 따른다.

## 4. 값·error·dirty·result availability 표현

입력 필드의 sample은 제품 default가 아니다. default 없는 필수 물리값은 placeholder/UNSPECIFIED로 시작하고 선택 law/adapter의 typed schema가 unit/range/dependency를 제공한다. 유한수/정수/enum/reference/식/채널 역할을 구별하고 단위를 이름 문자열 속에만 숨기지 않는다. affine absolute unit 변환과 delta unit scale은 다르게 처리한다.

오류는 해당 row/cell/face/node에 표시하며 하단 diagnostics 항목을 클릭하면 그 대상과 원문을 연다. valid input/running/retained/stale/engineering state를 동시에 볼 수 있다. unknown progress는 phase+spinner, percent=null로 둔다. `NOT_RETAINED`와 `NOT_EVALUATED`는 빈 plot이나0 curve로 위장하지 않는다. 해당 위치에 명시 `Evaluate selected details…` 또는 `Open raw artifact`를 제공한다.

Enter를 누르기 전 cell buffer는 compute input이 아니다. acknowledged draft invalid 문자열을 보존할 수 있으나 export/run gate는 막는다. raw buffer recovery capsule은 saved revision과 다른 행이다. 같은 창의 Material+Plan 두 owner 저장·Undo·source ref는 C01–C04 계약을 따른다. 저장 성공/실패는 owner별 receipt다. `SOURCE CHANGED`는 이전 result 삭제가 아니라 현재 draft와의 차이다.

## 5. 화면·동작 범위의 현재 한계

이 deliverable은 editable design과 별도 planning Qt source다. native app screenshot을 재사용해 제품 화면이라고 표시하지 않는다. CAD/FE 모델 그림은 합성 geometry, contour·curve·candidate는 합성 데이터다. native frame 내부의 우리 condition/reference/error/recovery 설계를 보여주며 실제 FreeCAD/ParaView 전체 menu를 다시 구현하는 계획이 아니다.

Qt gallery는 state board를 보는 clickable prototype, Material harness는 표/그래프/셀buffer/owner/save/recovery의 bounded simulation이다. 이 환경에는 PySide6가 없어 실제 window/dock/focus/keyboard/file dialog/Windows DPI는 **미확인**이다. Penpot native 편집/export도 미실행이며 Codex용 board/flow data를 제공했다. 최종 디자인 수용은 사용자가 시안과 실제 Qt 창을 따라가며 확인한 뒤 결정한다.
