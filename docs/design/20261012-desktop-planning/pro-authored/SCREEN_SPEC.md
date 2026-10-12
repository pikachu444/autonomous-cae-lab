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


## 전체 state board inventory

| ID | 도구·owner | 작업·상태 | 다음 조작 | 기능 |
|---|---|---|---|---|
| CLIENT-CONFLICT | Material / Material owner / source refresh | Another client changed this document · STALE_DOCUMENT / BUSY_EDIT | Apply reviewed source r18 + selected starts | FN-02, FN-34 |
| CLOSE-DIRTY | Material / Material + Plan + running job | Close workspace / unsaved work · DIRTY / JOB RUNNING | Save selected documents and close | FN-02 |
| COMMAND-MESH | Pre / FreeCAD host / Bracket / command mesh-006 | Native mesh generation / command monitor · COMMAND_CANCEL_REQUESTED | Refresh same command / no resubmission | FN-13 |
| DATA-CALIBRATION | Data / Data T-A / T-B | Gauge and calibration evidence · DIRTY | Apply mapping | FN-05, FN-35 |
| DATA-EDIT | Data / Data T-A / T-B | Tensile observations · r4 * · DIRTY | Link exact observation r4 | FN-01, FN-03, FN-04 |
| DATA-INVALID | Data / Data T-A / T-B | Time channel needs repair · INVALID_DRAFT | Link exact observation r4 | FN-04 |
| DATA-MAP | Data / Data T-A / T-B | Import two test files · MAPPING | Apply mapping | FN-03 |
| DEVICE-PLAN | Device / Host / record / evidence owner | Physical acquisition / hardware plan · REVIEW | Import existing measurement file | FN-35 |
| EVAL-NONCONVERGED | Evaluation / Existing Evaluation E-02 (same editor) | Coupled run · convergence not met · NONCONVERGED | Save definition and convergence evidence | FN-19 |
| EVAL-STAGES | Evaluation / Existing Evaluation E-02 (same editor) | Heat → structure · stages · STAGES | Edit same transfer owner | FN-19, FN-24 |
| EVAL-TRANSFER | Evaluation / Existing Evaluation E-02 (same editor) | Heat → structure · field transfer · TRANSFER | Evaluate once | FN-19 |
| EXPERT-DISCUSS | Expert / Discussion D-02 / explicit Study link | Material and fixture hypotheses · DISCUSSION_RETAINED | Edit Plan before explicit run | FN-30 |
| EXPERT-DRAFT | Expert / Discussion D-02 / explicit Study link | Question / provider unavailable · PROVIDER_UNAVAILABLE | Edit Plan before explicit run | FN-30 |
| HOME-EMPTY | Research / Document chooser | Open a document / independent tools · EMPTY | Open selected document / same owner | FN-01, FN-33 |
| MAT-ADOPT-CONFLICT | Material / Material + candidate proposal | Adopt c017 / target changed · BASE / CANDIDATE / CURRENT | Propose c017 on current r18… | FN-07, FN-21, FN-24 |
| MAT-ADOPT-DRAFT | Material / Material target / same existing owner | Material adoption / dirty target draft on r18 · DIRTY_ADOPTION | Save acknowledged Material draft | FN-07 |
| MAT-ADOPT-SAVED | Material / Material target / same existing owner | Material adoption / saved r19 · SAVED_ADOPTION | Cold reopen saved r19 | FN-07 |
| MAT-BRANCH-DRAFT | Material / Material M-branch-01 / independent new ID | Candidate c017 / new Material branch · NEW_BRANCH_DRAFT | Save new branch to independent location | FN-07 |
| MAT-BRANCH-SAVED | Material / Material M-branch-01 / independent new ID | Candidate c017 / new Material branch · SAVED_BRANCH | Reopen saved branch r1 without evaluation | FN-07 |
| MAT-CONSTITUTIVE | Material / Material + Numerical Plan (embedded) | Constitutive integration study · CONSTITUTIVE | Open separate inverse-fit evidence | FN-08 |
| MAT-DIRTY | Material / Material + Numerical Plan (embedded) | Rubber *  +  Fit A * · DIRTY | Review source / save conflict | FN-02, FN-04, FN-06, FN-07 |
| MAT-EMPTY | Material / New Material owner / no Plan | Untitled material / unsaved · EMPTY | Import two synthetic CSVs | FN-06 |
| MAT-FE-TRANSFER | Material / Material + Numerical Plan (embedded) | Assign retained law to FE · FE-TRANSFER | Open native material Tasks | FN-09 |
| MAT-FIT-PARTIAL | Material / Material + Numerical Plan (embedded) | Fit A · retained results · FIT-PARTIAL | Adopt candidate c017… | FN-07 |
| MAT-FIT-RUNNING | Material / Material + Numerical Plan (embedded) | Fit A · candidate evaluations · FIT-RUNNING | Simulate partial completion | FN-07 |
| MAT-PROTOCOL | Material / Material + Numerical Plan (embedded) | A-01 · protocol and measures · PROTOCOL | Keep protocol draft / review curves | FN-03, FN-06, FN-07 |
| MAT-READY | Material / Material + Numerical Plan (embedded) | PROPOSED future-supported mixed-control state · READY | Run fit… | FN-07 |
| NUM-ADOPT-CONFLICT | Numerical / N-MOO/r4 proposal → CAD and Material owners | p19 / owner-specific adoption conflict · ADOPTION_CONFLICT | Cancel / keep current owners | FN-24 |
| NUM-BATCH | Numerical / N-Batch/r2 | External batch / import exact candidate responses · BATCH | External batch | FN-26 |
| NUM-CASE-BATCH | Numerical / N-Batch/r2 | b01 / exact retained case · SELECTED_CASE | Keep selection / return to method | FN-26 |
| NUM-CASE-DOE | Numerical / N-DOE/r3 | c001 / exact retained case · SELECTED_CASE | Keep selection / return to method | FN-20 |
| NUM-CASE-MOO | Numerical / N-MOO/r4 | p19 / exact retained case · SELECTED_CASE | Keep selection / return to method | FN-24 |
| NUM-CASE-SENSITIVITY | Numerical / N-Sobol/r2 | thickness / exact retained case · SELECTED_CASE | Keep selection / return to method | FN-20 |
| NUM-CASE-SURROGATE | Numerical / N-RBF/r4 | q03 / exact retained case · SELECTED_CASE | Keep selection / return to method | FN-23 |
| NUM-CASE-UQ | Numerical / N-UQ/r2 | s041 / exact retained case · SELECTED_CASE | Keep selection / return to method | FN-22 |
| NUM-DOE | Numerical / N-DOE/r3 | DOE / experiment design · DOE | DOE | FN-10, FN-20 |
| NUM-MOO | Numerical / N-MOO/r4 | Multiobjective / explicit Pareto selection · MOO | Multiobjective | FN-24 |
| NUM-NEXT-TEST | Numerical / New Numerical Plan N-next / derived from Study S-02r3 | Fixture-only compliance / new proposal · INVALID_DRAFT / PROPOSAL | Save next-test draft / reopen | FN-29 |
| NUM-OPTIMIZE | Numerical / N-05/r8 | Fit A / inverse or optimization · OPTIMIZATION | Optimization / inverse | FN-05, FN-21, FN-23, FN-30 |
| NUM-SENSITIVITY | Numerical / N-Sobol/r2 | Sensitivity / definition of influence · SENSITIVITY | Sensitivity | FN-20 |
| NUM-SURROGATE | Numerical / N-RBF/r4 | Surrogate / holdout validation · SURROGATE | Surrogate | FN-23 |
| NUM-UQ | Numerical / N-UQ/r2 | Uncertainty / success-conditioned distribution · UQ | UQ | FN-22 |
| PDE-EQUATION | PDE / PDE Q-04 / same existing owner | PDE Q-04 / bounded nonlinear diffusion · EDIT | Show synthetic result state | FN-18 |
| PDE-INVALID | PDE / PDE Q-04 / same existing owner | PDE Q-04 / invalid RHS draft · INVALID | Correct symbol / boundary | FN-18 |
| PDE-RESULT | PDE / PDE Q-04 / same existing owner | PDE Q-04 / retained reference comparison · RESULT | Show synthetic result state | FN-18 |
| POST-COMPARE | Post / ParaView native Post document | Comparison A / B · exact recipe · COMPARE | Preview / validate mapping | FN-05, FN-28 |
| POST-CONTACT | Post / ParaView native Post document | Contact result · Pair A → B · CONTACT | Save measurement | FN-14, FN-16, FN-17 |
| POST-MAP-PREVIEW | Post / ParaView native Post document | B → A mapping / valid region · MAP-PREVIEW | Apply valid recipe | FN-28 |
| POST-MEASURE | Post / ParaView native Post document | Saved gauge · source / time / ID · MEASURE | Save measurement | FN-15, FN-27, FN-34 |
| POST-OPEN | Post / ParaView native Post document | External time series · no CAD required · OPEN | Reader Properties → Apply | FN-27 |
| POST-REPAIR | Post / ParaView native Post document | Locate moved or changed dependencies · REPAIR | Repair identical files | FN-27, FN-28 |
| PRE-CONTACT | Pre / FreeCAD native document / Analysis 1 | Contact pair · Pad / Base · CONTACT | Geometry split scenario | FN-14 |
| PRE-CONTACT-CANCELLED | Pre / FreeCAD r13 / contact owner | Contact on geometry r13 / rebind cancelled · UNRESOLVED_DRAFT | Keep state / save and reopen | FN-14 |
| PRE-CONTACT-READY | Pre / FreeCAD native document / Analysis 1 | PROPOSED admitted contact / frozen input · CONTACT-READY | Freeze valid contact input (simulated) | FN-14 |
| PRE-CONTACT-REBIND | Pre / FreeCAD native document / Analysis 1 | Contact · changed geometry r13 · CONTACT-REBIND | Apply selected rebind | FN-14 |
| PRE-CONTACT-REBOUND | Pre / FreeCAD r13 / contact owner | Contact on geometry r13 / rebind applied to draft · REBOUND_DRAFT | Keep state / save and reopen | FN-14 |
| PRE-CONTACT-UNSUPPORTED | Pre / FreeCAD native document / Analysis 1 | Contact · adapter admission · CONTACT-UNSUPPORTED | Return to face sets | FN-14 |
| PRE-DESIGN | Pre / FreeCAD native document / Analysis 1 | Bracket · editable native model · DESIGN | Recompute / effect check | FN-10, FN-34 |
| PRE-FEM | Pre / FreeCAD native document / Analysis 1 | Bracket · Analysis 1 · FEM | Contact pair… | FN-09, FN-11, FN-12, FN-13 |
| PRE-MESH-QUALITY | Pre / FreeCAD native document / Analysis 1 | Mesh r6 · quality selection · MESH-QUALITY | Regenerate / new command | FN-13 |
| PRE-MOTION | Pre / FreeCAD native document / Analysis 1 | Assembly · pose preview · MOTION | Restore design pose | FN-11 |
| PRE-RESTORE-FAILED | Pre / FreeCAD native document / Analysis 1 | Assembly · restore needs verification · RESTORE-FAILED | Restore design pose | FN-11 |
| RECOVERY-REOPEN | Material / Saved owner revisions + separate recovery capsule | Reopen saved work / recovery drafts · COLD_REOPEN | Open saved Material + Plan | FN-01, FN-02, FN-07, FN-32 |
| REOPEN-CONSTITUTIVE | Material / Saved prescribed-F reference / saved study | Reopen prescribed-F reference / saved study · COLD_REOPEN | Continue editing the same owner | FN-08 |
| REOPEN-CONTACT | Pre / Saved Bracket.caepre / geometry r12 | Reopen Bracket.caepre / geometry r12 · COLD_REOPEN | Continue editing the same owner | FN-14 |
| REOPEN-CONTACT-CANCELLED | Pre / Saved geometry r13 / invalid contact refs | Reopen geometry r13 / invalid contact refs · COLD_REOPEN | Continue editing the same owner | FN-14 |
| REOPEN-CONTACT-R13 | Pre / Saved geometry r13 / rebound contact r8 | Reopen geometry r13 / rebound contact r8 · COLD_REOPEN | Continue editing the same owner | FN-14 |
| REOPEN-DATA | Data / Saved Data A+B / r4 | Reopen Data A+B / r4 · COLD_REOPEN | Continue editing the same owner | FN-03 |
| REOPEN-EVALUATION | Evaluation / Saved E-02 / r5 | Reopen E-02 / r5 · COLD_REOPEN | Continue editing the same owner | FN-19 |
| REOPEN-EXPERT | Expert / Saved Discussion D-02 / r4 | Reopen Discussion D-02 / r4 · COLD_REOPEN | Continue editing the same owner | FN-30 |
| REOPEN-FE-ASSIGNMENT | Pre / Saved FE assignment draft / Bracket r12 | Reopen FE assignment draft / Bracket r12 · COLD_REOPEN | Continue editing the same owner | FN-09 |
| REOPEN-MAT-ADOPTED | Material / Saved Material r19 / adopted c017 | Reopen Material r19 / adopted c017 · COLD_REOPEN | Continue editing the same owner | FN-07 |
| REOPEN-MAT-BRANCH | Material / Saved M-branch-01 / r1 | Reopen M-branch-01 / r1 · COLD_REOPEN | Continue editing the same owner | FN-07 |
| REOPEN-NEXT-TEST | Numerical / Saved N-next / saved next-test draft | Reopen N-next / saved next-test draft · COLD_REOPEN | Continue editing the same owner | FN-29 |
| REOPEN-NUM-BATCH | Numerical / Saved N-Batch/r2 | Reopen N-Batch/r2 · COLD_REOPEN | Continue editing the same owner | FN-26 |
| REOPEN-NUM-DOE | Numerical / Saved N-DOE/r3 | Reopen N-DOE/r3 · COLD_REOPEN | Continue editing the same owner | FN-20 |
| REOPEN-NUM-MOO | Numerical / Saved N-MOO/r4 | Reopen N-MOO/r4 · COLD_REOPEN | Continue editing the same owner | FN-24 |
| REOPEN-NUM-SENSITIVITY | Numerical / Saved N-Sobol/r2 | Reopen N-Sobol/r2 · COLD_REOPEN | Continue editing the same owner | FN-20 |
| REOPEN-NUM-SURROGATE | Numerical / Saved N-RBF/r4 | Reopen N-RBF/r4 · COLD_REOPEN | Continue editing the same owner | FN-23 |
| REOPEN-NUM-UQ | Numerical / Saved N-UQ/r2 | Reopen N-UQ/r2 · COLD_REOPEN | Continue editing the same owner | FN-22 |
| REOPEN-NUMERICAL | Numerical / Saved N-05 / r8 | Reopen N-05 / r8 · COLD_REOPEN | Continue editing the same owner | FN-21 |
| REOPEN-PDE | PDE / Saved Q-04 / r3 | Reopen Q-04 / r3 · COLD_REOPEN | Continue editing the same owner | FN-18 |
| REOPEN-POST | Post / Saved Post analysis / r6 | Reopen Post analysis / r6 · COLD_REOPEN | Continue editing the same owner | FN-27, FN-28 |
| REOPEN-REPORT | Study / Saved Research report / exported draft | Reopen Research report / exported draft · COLD_REOPEN | Continue editing the same owner | FN-32 |
| REOPEN-SIMULATION | Simulation / Saved V-03 draft / exact model refs | Reopen V-03 draft / exact model refs · COLD_REOPEN | Continue editing the same owner | FN-15, FN-16, FN-17 |
| REOPEN-STUDY | Study / Saved S-02 / r3 | Reopen S-02 / r3 · COLD_REOPEN | Continue editing the same owner | FN-29 |
| REOPEN-WORKBENCH | Workbench / Saved Connection view / saved refs | Reopen Connection view / saved refs · COLD_REOPEN | Continue editing the same owner | FN-31 |
| REPORT-REVIEW | Report / Host / record / evidence owner | Evidence report / release status · REVIEW | Keep draft and return to Study | FN-08, FN-16, FN-32 |
| RUN-ACTIVE | Runner / Existing JobManager / attempt records | Attempt monitor · ACTIVE | Inspect transferred / partial artifacts | FN-14, FN-15, FN-16, FN-21, FN-25, FN-35 |
| RUN-CANCEL | Runner / Existing JobManager / attempt records | Cancellation / actual termination · CANCEL | Close window separately… | FN-19, FN-25, FN-34 |
| RUN-CANCEL-CONTACT | Runner / JobManager / contact-031 attempt02 | Contact attempt / cancellation · CANCEL_REQUESTED | Simulate completed contact result | FN-14 |
| RUN-CANCEL-EVALUATION | Runner / JobManager / eval-019 attempt02 | Evaluation attempt / cancellation · CANCEL_REQUESTED | Simulate NOT_CONVERGED result | FN-19 |
| RUN-CONTACT | Runner / JobManager / contact-031 attempt02 | Contact attempt / frozen input · RUNNING | Simulate completed contact result | FN-14 |
| RUN-EVALUATION | Runner / JobManager / eval-019 attempt02 | Evaluation attempt / frozen input · RUNNING | Simulate NOT_CONVERGED result | FN-19 |
| RUN-NUM-BATCH | Runner / N-Batch/r2 | batch-021 / attempt03 · SIMULATED_EXECUTION | Return to retained method results | FN-26 |
| RUN-NUM-DOE | Runner / N-DOE/r3 | doe-025 / attempt03 · SIMULATED_EXECUTION | Return to retained method results | FN-20 |
| RUN-NUM-MOO | Runner / N-MOO/r4 | moo-029 / attempt03 · SIMULATED_EXECUTION | Return to retained method results | FN-24 |
| RUN-NUM-SENSITIVITY | Runner / N-Sobol/r2 | sobol-026 / attempt03 · SIMULATED_EXECUTION | Return to retained method results | FN-20 |
| RUN-NUM-SURROGATE | Runner / N-RBF/r4 | confirm-028 / attempt03 · SIMULATED_EXECUTION | Return to retained method results | FN-23 |
| RUN-NUM-UQ | Runner / N-UQ/r2 | uq-027 / attempt03 · SIMULATED_EXECUTION | Return to retained method results | FN-22 |
| RUN-REMOTE-CONFIG | Runner / Runner / N-Batch/r2 / exchange ex-2026-10-12-04 | Remote batch-021 / attempt03 · LOCATION_CONFIG | Inspect reconnect / result staging scenario | FN-26 |
| RUN-REMOTE-LOST | Runner / Runner / N-Batch/r2 / exchange ex-2026-10-12-04 | Remote batch-021 / attempt03 · CONNECTION_LOST | Keep original attempt / reopen | FN-25, FN-26 |
| SAVE-PARTIAL | Material / Material + Numerical Plan | Some documents were saved · PARTIAL_SAVE | Retry Plan only | FN-02 |
| SETUP-CAPABILITY | Environment / Host / record / evidence owner | Registered capability / actual environment · REVIEW | Open saved work without running a probe | FN-33 |
| SIM-EXPLICIT | Simulation / Simulation V-03 + native or external input | Explicit impact / drop · EDIT / SUPPORT CHECK | Open contact / surface definition | FN-16 |
| SIM-FAILURE | Simulation / Simulation V-03 + native or external input | Failure / cohesive interface · EDIT / SUPPORT CHECK | Open contact / surface definition | FN-17 |
| SIM-IMPLICIT | Simulation / Simulation V-03 + native or external input | Nonlinear implicit · EDIT / SUPPORT CHECK | Open contact / surface definition | FN-09, FN-12, FN-15 |
| SIM-THERMAL | Simulation / V-02/r4 | V-02/r4 / saved SI stage · SAVED_STAGE | Open exact stage transfer | FN-19 |
| SIM-THERMOELASTIC | Simulation / V-03/r6 | V-03/r6 / saved SI stage · SAVED_STAGE | Open exact stage transfer | FN-19 |
| STUDY-DECISION | Study / Existing Study S-02 | Why does measured stiffness differ? · DECISION_DRAFT | Save explicit research decision | FN-05, FN-17, FN-22, FN-29, FN-30, FN-31, FN-35 |
| STUDY-EMPTY | Study / Existing Study S-02 | New research question · EMPTY | Create hypothesis and inspect evidence | FN-29 |
| STUDY-HISTORY | Study / Study S-02 / immutable saved r2 | Study S-02 / previous decision r2 · READ_ONLY_HISTORY | Return to current Study without changing it | FN-29 |
| WB-LINKS | Workbench / Existing document links / Study view | Optional connection view · STALE_REFERENCE | Disconnect link… | FN-31 |

## CLIENT-CONFLICT — Another client changed this document

편집 원본: `screens/CLIENT-CONFLICT.svg` · 미리보기: `screens/CLIENT-CONFLICT.png` · owner: **Material owner / source refresh**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-02: 내 기준 generation 41, 서버 42, 같은 coefficient의 이전/내 값/다른 client 값. → 내 변경 복사·원본 다시 읽기·새 분기 중 선택한다. 겹치는 셀은 자동 병합하지 않는다. non-overlap도 fresh preview 후 명시 적용한다.
- FN-34: 현재 owner/session/generation·pending native Task 또는 cell editing. → 변경 전 fresh owner inspect로 실제 대상을 읽고 typed domain command를 보낸다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Read current / keep buffer | navigate / Read current / keep buffer | MAT-DIRTY |
| Review new proposal | navigate / Review new proposal | MAT-ADOPT-CONFLICT |
| New branch from local draft | navigate / New branch from local draft | MAT-DIRTY |
| Apply reviewed source r18 + selected starts | navigate / Apply reviewed source r18 + selected starts | MAT-DIRTY |
| Cancel refresh / keep source r17 and starts | navigate / Cancel refresh / keep source r17 and starts | MAT-DIRTY |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | New law/protocol or import observation |
| edit | Material value and embedded Plan bound have different Undo owners |
| dirty | Per-owner save/source refresh/Plan starting values explicit |
| running | Frozen input; current draft can diverge; old/late result linked correctly |
| fail | Failed candidate/input diagnostics or save receipt; no made-up curve |
| cancel | Stop submission separately from job terminal and window close |
| complete | Retained details/holdout → explicit owner adoption → save |
| reopen | Open saved rN or separate recovery capsule; never evaluate on selection |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-02, FN-34와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## CLOSE-DIRTY — Close workspace / unsaved work

편집 원본: `screens/CLOSE-DIRTY.svg` · 미리보기: `screens/CLOSE-DIRTY.png` · owner: **Material + Plan + running job**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-02: 셀 버퍼·owner draft·saved revision 3열, 열린 job의 계속 실행/취소 항목. → 선택 문서 저장 후 닫기, 초안 복구본 유지 후 닫기, 계속 편집을 고른다. ‘닫기’와 job 취소는 별개다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Save selected documents and close | navigate / Save selected documents and close | RECOVERY-REOPEN |
| Keep recovery drafts and close | navigate / Keep recovery drafts and close | RECOVERY-REOPEN |
| Discard selected changes and close | navigate / Discard selected changes and close | HOME-EMPTY |
| Return to workspace | navigate / Return to workspace | MAT-DIRTY |
| Inspect separate job cancellation… | navigate / Inspect separate job cancellation… | RUN-CANCEL |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | New law/protocol or import observation |
| edit | Material value and embedded Plan bound have different Undo owners |
| dirty | Per-owner save/source refresh/Plan starting values explicit |
| running | Frozen input; current draft can diverge; old/late result linked correctly |
| fail | Failed candidate/input diagnostics or save receipt; no made-up curve |
| cancel | Stop submission separately from job terminal and window close |
| complete | Retained details/holdout → explicit owner adoption → save |
| reopen | Open saved rN or separate recovery capsule; never evaluate on selection |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-02와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## COMMAND-MESH — Native mesh generation / command monitor

편집 원본: `screens/COMMAND-MESH.svg` · 미리보기: `screens/COMMAND-MESH.png` · owner: **FreeCAD host / Bracket / command mesh-006**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-13: command_id mesh-006·geometryr12/startg41·취소요청·NOT_APPLIED와 보존meshr6. → 같은 command_status/cancel을 사용한다. 취소접수와 실제terminal/applygeneration을 구별하고 job_id로 조회하지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open mesh settings | navigate / Open mesh settings | PRE-MESH-QUALITY |
| Refresh command status | navigate / Refresh command status | COMMAND-MESH |
| Return to native document | navigate / Return to native document | PRE-FEM |
| Refresh same command / no resubmission | navigate / Refresh same command / no resubmission | COMMAND-MESH |
| Inspect preserved mesh r6 | navigate / Inspect preserved mesh r6 | PRE-MESH-QUALITY |
| Return to conditions / retained native document | navigate / Return to conditions / retained native document | PRE-FEM |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Native New/Open model; no forced fixture |
| edit | Native Task/selection/Undo; BUSY_EDIT protects pending work |
| dirty | Managed save first restores design pose, preserves invalid draft |
| running | Native command ID differs from calculation job ID; generation guarded apply |
| fail | Failed feature/mesh/face reference/restore location opens directly |
| cancel | Cancel Task/preview/rebind separately from command/job; old mesh/results retained |
| complete | Preflight → frozen input → Runner → exact Post result |
| reopen | Editable FCStd/native dependencies and design pose; no solver rerun |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-13와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## DATA-CALIBRATION — Gauge and calibration evidence

편집 원본: `screens/DATA-CALIBRATION.svg` · 미리보기: `screens/DATA-CALIBRATION.png` · owner: **Data T-A / T-B**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-05: 시편·로트·장착·장비·교정 revision, voltage/count raw 채널과 변환식. → 보정계수·유효기간·단위·영점·uncertainty source를 연결하고 전후 값을 비교한다.
- FN-35: experiment plan·specimen/device/calibration refs와 기록할 채널. → 장비 입력/출력 계약과 수집 단위·time synchronization을 정의한다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Instrument / calibration ref | reference / 해당 없음 | Extensometer / CAL-018 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Observation position | reference / 해당 없음 | Gauge centre / axis X | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| L0 / fixture condition | text / 해당 없음 | 50 mm / aligned tabs | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Force uncertainty (reported) | number / N | UNKNOWN | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Original calibration document | reference / 해당 없음 | CAL-018 · registered document r2 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open files… | navigate / Open files… | DATA-MAP |
| Map channels | navigate / Map channels | DATA-MAP |
| Apply mapping | navigate / Apply mapping | DATA-EDIT |
| Send observation | navigate / Send observation | MAT-PROTOCOL |
| Save Data | navigate / Save Data | REOPEN-DATA |
| Calibration details | navigate / Calibration details | DATA-CALIBRATION |
| Show invalid sample | navigate / Show invalid sample | DATA-INVALID |
| Open registered original | navigate / Open registered original | REPORT-REVIEW |
| Compare in Post | navigate / Compare in Post | POST-COMPARE |
| Add Study evidence | navigate / Add Study evidence | STUDY-DECISION |
| Review Plan selection | navigate / Review Plan selection | NUM-OPTIMIZE |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open file(s) or create sheet |
| edit | Enter/Tab commit cell to Data; Esc cancels buffer |
| dirty | Save Data; exact observation refs stay on saved revision |
| running | Import/transform command tracks real phase; current dataset retained |
| fail | Open marked row/column/recipe; keep invalid draft |
| cancel | Cancel mapping/transform before publish; old channels intact |
| complete | Inspect canonical samples → link observation → save |
| reopen | Restore raw hashes/channel IDs/recipes/masks; no calculation |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-05, FN-35와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## DATA-EDIT — Tensile observations · r4 *

편집 원본: `screens/DATA-EDIT.svg` · 미리보기: `screens/DATA-EDIT.png` · owner: **Data T-A / T-B**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-01: 문서명, 현재 입력과 saved revision, dirty 표식, 마지막 결과. → 지원 입력을 편집한다. missing backend가 있어도 문서 읽기·draft 저장은 계속된다.
- FN-03: P11–e11 곡선과 원 row ID, 단위와 reference configuration, 관측 시간축. → 표 행·곡선 구간을 함께 선택해 원자료 값을 검토하고 Data 저장/관측 게시를 실행한다.
- FN-04: 왼쪽 raw/recipe tree, 중앙 표, 아래 곡선, 선택 40–110행과 time 4–11 s. → 곡선을 드래그하거나 Shift+행 선택, 숫자 구간 입력으로 같은 원 sample을 선택한다. 선택은 아직 mask가 아니다.
- FN-04: Filter/zero-shift/resample node의 입력·설정·출력 channel과 전후 곡선. → 실행 전 미리보기→Apply로 recipe 새 revision을 만든다. 원자료와 이전 처리 결과는 남는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open files… | navigate / Open files… | DATA-MAP |
| Map channels | navigate / Map channels | DATA-MAP |
| Apply mapping | navigate / Apply mapping | DATA-EDIT |
| Send observation | navigate / Send observation | MAT-PROTOCOL |
| Save Data | navigate / Save Data | REOPEN-DATA |
| Calibration details | navigate / Calibration details | DATA-CALIBRATION |
| Show invalid sample | navigate / Show invalid sample | DATA-INVALID |
| Edit flagged time cell · F2 | edit / Original raw preserved; invalid owner draft visible | DATA-INVALID |
| Exclude / restore quality | navigate / Exclude / restore quality | DATA-EDIT |
| Correct time in recipe | navigate / Correct time in recipe | DATA-EDIT |
| Link exact observation r4 | navigate / Link exact observation r4 | MAT-PROTOCOL |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open file(s) or create sheet |
| edit | Enter/Tab commit cell to Data; Esc cancels buffer |
| dirty | Save Data; exact observation refs stay on saved revision |
| running | Import/transform command tracks real phase; current dataset retained |
| fail | Open marked row/column/recipe; keep invalid draft |
| cancel | Cancel mapping/transform before publish; old channels intact |
| complete | Inspect canonical samples → link observation → save |
| reopen | Restore raw hashes/channel IDs/recipes/masks; no calculation |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-01, FN-03, FN-04와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## DATA-INVALID — Time channel needs repair

편집 원본: `screens/DATA-INVALID.svg` · 미리보기: `screens/DATA-INVALID.png` · owner: **Data T-A / T-B**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-04: sample 82의 sensor dropout, mask 사유와 불연속 구간. → M 또는 우클릭 ‘품질 제외’로 source-quality mask를 저장한다. 행 삭제나 곡선 숨김으로 대신하지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open files… | navigate / Open files… | DATA-MAP |
| Map channels | navigate / Map channels | DATA-MAP |
| Apply mapping | navigate / Apply mapping | DATA-EDIT |
| Send observation | navigate / Send observation | MAT-PROTOCOL |
| Save Data | navigate / Save Data | REOPEN-DATA |
| Calibration details | navigate / Calibration details | DATA-CALIBRATION |
| Show invalid sample | navigate / Show invalid sample | DATA-INVALID |
| Edit flagged time cell · F2 | edit / Original raw preserved; invalid owner draft visible | DATA-INVALID |
| Exclude / restore quality | navigate / Exclude / restore quality | DATA-EDIT |
| Correct time in recipe | navigate / Correct time in recipe | DATA-EDIT |
| Link exact observation r4 | navigate / Link exact observation r4 | MAT-PROTOCOL |
| Invalid time axis | open_diagnostic / Correct the marked cell or save an invalid draft. | DATA-EDIT |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open file(s) or create sheet |
| edit | Enter/Tab commit cell to Data; Esc cancels buffer |
| dirty | Save Data; exact observation refs stay on saved revision |
| running | Import/transform command tracks real phase; current dataset retained |
| fail | Open marked row/column/recipe; keep invalid draft |
| cancel | Cancel mapping/transform before publish; old channels intact |
| complete | Inspect canonical samples → link observation → save |
| reopen | Restore raw hashes/channel IDs/recipes/masks; no calculation |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-04와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## DATA-MAP — Import two test files

편집 원본: `screens/DATA-MAP.svg` · 미리보기: `screens/DATA-MAP.png` · owner: **Data T-A / T-B**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-03: A/B 원본 미리보기와 독립적인 열 선택, raw 단위→canonical 단위·scale·offset·변환 후 3행. → 이름 기반 채널을 지정한다. B extension ×0.001 mm, load ×1000 N, time ×0.001 s; 온도는 절대량 K 기준으로 변환한다.
- FN-03: ‘단위 지정’과 ‘수치 변환’, source channel ID. 열명만 MPa로 바꾸는 오류 셀. → force/A0로 nominal stress P11, extension/L0로 engineering strain e11 파생 채널을 만든다. L0·A0가 없으면 해당 연산만 차단한다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Gauge length L0 | number / mm | 50 | 미지정; sample을 기본값으로 쓰지 않음 / >0 | 선택 owner / 대상 |
| Original section A0 | number / mm² | 20 | 미지정; sample을 기본값으로 쓰지 않음 / >0 | 선택 owner / 대상 |
| Displacement meaning | enum / 해당 없음 | Extensometer gauge extension | UNSPECIFIED / 선택 capability·문서 규칙 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open files… | navigate / Open files… | DATA-MAP |
| Map channels | navigate / Map channels | DATA-MAP |
| Apply mapping | navigate / Apply mapping | DATA-EDIT |
| Send observation | navigate / Send observation | MAT-PROTOCOL |
| Save Data | navigate / Save Data | REOPEN-DATA |
| Calibration details | navigate / Calibration details | DATA-CALIBRATION |
| Show invalid sample | navigate / Show invalid sample | DATA-INVALID |
| Review protocol / measures | navigate / Review protocol / measures | MAT-PROTOCOL |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open file(s) or create sheet |
| edit | Enter/Tab commit cell to Data; Esc cancels buffer |
| dirty | Save Data; exact observation refs stay on saved revision |
| running | Import/transform command tracks real phase; current dataset retained |
| fail | Open marked row/column/recipe; keep invalid draft |
| cancel | Cancel mapping/transform before publish; old channels intact |
| complete | Inspect canonical samples → link observation → save |
| reopen | Restore raw hashes/channel IDs/recipes/masks; no calculation |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-03와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## DEVICE-PLAN — Physical acquisition / hardware plan

편집 원본: `screens/DEVICE-PLAN.svg` · 미리보기: `screens/DEVICE-PLAN.png` · owner: **Host / record / evidence owner**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-35: 장비 connection 상태·capability·control limits/interlocks·허용 실험. → read-only 확인/수집 준비를 수행한다. 실제 actuator 동작은 현재 권한/환경이 확인된 명시 실행으로만 요청한다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Device / driver | reference / 해당 없음 | UNBOUND / free path not yet confirmed | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Specimen / fixture / calibration | reference / 해당 없음 | Data A-01 / fixture rev / calibration doc | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Sample rate | number / Hz | 1000 | 미지정; sample을 기본값으로 쓰지 않음 / device-supported | 선택 owner / 대상 |
| Acquisition duration | number / s | 10 | 미지정; sample을 기본값으로 쓰지 않음 / >0 | 선택 owner / 대상 |
| Permitted actuation | enum / 해당 없음 | NONE — file import only in this scenario | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open… | navigate / Open… | HOME-EMPTY |
| Recent documents | navigate / Recent documents | RECOVERY-REOPEN |
| Capabilities | navigate / Capabilities | SETUP-CAPABILITY |
| Study | navigate / Study | STUDY-EMPTY |
| Help / evidence | navigate / Help / evidence | REPORT-REVIEW |
| Import existing measurement file | navigate / Import existing measurement file | DATA-CALIBRATION |
| Edit acquisition / evidence plan | navigate / Edit acquisition / evidence plan | DEVICE-PLAN |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open or create the relevant owner record |
| edit | Use typed fields / contextual actions |
| dirty | Preserve owner draft / exact refs |
| running | No automatic activity in this board; observe external job separately |
| fail | Open diagnostic, save draft and retain evidence |
| cancel | Cancel preview / keep previous owner content |
| complete | Save exact record / explicit next tool |
| reopen | Restore saved refs / no hidden execution |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-35와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## EVAL-NONCONVERGED — Coupled run · convergence not met

편집 원본: `screens/EVAL-NONCONVERGED.svg` · 미리보기: `screens/EVAL-NONCONVERGED.png` · owner: **Existing Evaluation E-02 (same editor)**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-19: stage attempt·iteration residual·absolute/relative scale·최대 반복·NOT_CONVERGED. → 실패 단계 원입력 또는 동일 prefix 재사용 범위를 연다. iteration은 현 코드의 부분 loop 재사용 불가 제한을 유지한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open definition | navigate / Open definition | EVAL-STAGES |
| Save definition | navigate / Save definition | REOPEN-EVALUATION |
| Stages | navigate / Stages | EVAL-STAGES |
| Transfers | navigate / Transfers | EVAL-TRANSFER |
| Iterations | navigate / Iterations | EVAL-NONCONVERGED |
| Evaluate once | navigate / Evaluate once | RUN-EVALUATION |
| Open Fit A example | navigate / Open Fit A example | NUM-OPTIMIZE |
| Inspect failed / last stage | navigate / Inspect failed / last stage | RUN-EVALUATION |
| Edit iteration policy (new input) | navigate / Edit iteration policy (new input) | EVAL-STAGES |
| Retry identical definition / new attempt | navigate / Retry identical definition / new attempt | RUN-EVALUATION |
| Cancel / keep retained result | navigate / Cancel / keep retained result | REOPEN-EVALUATION |
| Save definition and convergence evidence | navigate / Save definition and convergence evidence | REOPEN-EVALUATION |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Create existing Evaluation kind=evaluation, add saved stages |
| edit | Same stage/transfer/iteration editor and owner in standalone/embedded use |
| dirty | Save definition; linked Plan keeps exact old ref until explicit update |
| running | Static connection distinct from actual field; child attempts and residual |
| fail | Failed stage / transfer / NOT_CONVERGED retain input and partial fields |
| cancel | Stop subsequent stages; actual current child terminal separate |
| complete | Inspect stage refs/field mapping/satisfied residual before valid result |
| reopen | Restore same definition/checkpoint; identical full hash/values required for current prefix reuse |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-19와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## EVAL-STAGES — Heat → structure · stages

편집 원본: `screens/EVAL-STAGES.svg` · 미리보기: `screens/EVAL-STAGES.png` · owner: **Existing Evaluation E-02 (same editor)**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-19: saved Material/PDE/Simulation 단계·순서·exact revision과 공개 inputs/outputs. → 단계를 추가하고 같은 표에서 삭제·순서를 바꾼다. 삭제로 끊기는 transfer를 표시하고 invalid draft로 저장 가능하다.
- FN-24: 복수 분야 입력/응답 연결과 공통 변수 bindings. → MDO 평가 절차가 필요하면 같은 Evaluation 정의를 편집한다. graph 자체가 optimizer가 되지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open definition | navigate / Open definition | EVAL-STAGES |
| Save definition | navigate / Save definition | REOPEN-EVALUATION |
| Stages | navigate / Stages | EVAL-STAGES |
| Transfers | navigate / Transfers | EVAL-TRANSFER |
| Iterations | navigate / Iterations | EVAL-NONCONVERGED |
| Evaluate once | navigate / Evaluate once | RUN-EVALUATION |
| Open Fit A example | navigate / Open Fit A example | NUM-OPTIMIZE |
| Open selected domain | navigate / Open selected domain | SIM-THERMOELASTIC |
| Add / remove stage | navigate / Add / remove stage | EVAL-STAGES |
| Edit same transfer owner | navigate / Edit same transfer owner | EVAL-TRANSFER |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Create existing Evaluation kind=evaluation, add saved stages |
| edit | Same stage/transfer/iteration editor and owner in standalone/embedded use |
| dirty | Save definition; linked Plan keeps exact old ref until explicit update |
| running | Static connection distinct from actual field; child attempts and residual |
| fail | Failed stage / transfer / NOT_CONVERGED retain input and partial fields |
| cancel | Stop subsequent stages; actual current child terminal separate |
| complete | Inspect stage refs/field mapping/satisfied residual before valid result |
| reopen | Restore same definition/checkpoint; identical full hash/values required for current prefix reuse |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-19, FN-24와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## EVAL-TRANSFER — Heat → structure · field transfer

편집 원본: `screens/EVAL-TRANSFER.svg` · 미리보기: `screens/EVAL-TRANSFER.png` · owner: **Existing Evaluation E-02 (same editor)**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-19: 출발/도착 port·quantity/measure/unit/association/mesh/time·필수 영역. → 현재 exact_same_mesh이면 실제 metadata equality를 확인한다. K/°C 변환·mapping은 새 검증 경로가 있어야 선택한다.
- FN-19: 정적 연결 검사와 공급 field 수신 값 검사를 구별한 상태. → 한 번 평가를 실행한다. 생산된 field·mask를 검사한 뒤 수신 단계를 제출한다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Mapping method | enum / 해당 없음 | exact_same_mesh | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Transfer convention | enum / 해당 없음 | absolute temperature | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Missing policy | enum / 해당 없음 | block required input | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open definition | navigate / Open definition | EVAL-STAGES |
| Save definition | navigate / Save definition | REOPEN-EVALUATION |
| Stages | navigate / Stages | EVAL-STAGES |
| Transfers | navigate / Transfers | EVAL-TRANSFER |
| Iterations | navigate / Iterations | EVAL-NONCONVERGED |
| Evaluate once | navigate / Evaluate once | RUN-EVALUATION |
| Open Fit A example | navigate / Open Fit A example | NUM-OPTIMIZE |
| Inspect actual transfer | navigate / Inspect actual transfer | EVAL-NONCONVERGED |
| Return to stages | navigate / Return to stages | EVAL-STAGES |
| Open separate Fit A Plan | navigate / Open separate Fit A Plan | NUM-OPTIMIZE |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Create existing Evaluation kind=evaluation, add saved stages |
| edit | Same stage/transfer/iteration editor and owner in standalone/embedded use |
| dirty | Save definition; linked Plan keeps exact old ref until explicit update |
| running | Static connection distinct from actual field; child attempts and residual |
| fail | Failed stage / transfer / NOT_CONVERGED retain input and partial fields |
| cancel | Stop subsequent stages; actual current child terminal separate |
| complete | Inspect stage refs/field mapping/satisfied residual before valid result |
| reopen | Restore same definition/checkpoint; identical full hash/values required for current prefix reuse |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-19와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## EXPERT-DISCUSS — Material and fixture hypotheses

편집 원본: `screens/EXPERT-DISCUSS.svg` · 미리보기: `screens/EXPERT-DISCUSS.png` · owner: **Discussion D-02 / explicit Study link**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-30: 실제 author/model/provider·turn·source citation·가정/관측/계산 구분. → 논점 또는 발언 선택으로 관련 근거를 열고 특정 turn에 반론을 입력한다.
- FN-30: pause/resume·부분 발언·다음 round 범위·budget. → 일시정지는 후속 발언을 막고 기존 solver job은 별도 Runner에서 취소한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open discussion | navigate / Open discussion | EXPERT-DRAFT |
| Save discussion | navigate / Save discussion | REOPEN-EXPERT |
| Pause / resume | navigate / Pause / resume | EXPERT-DISCUSS |
| Next-test Plan | navigate / Next-test Plan | NUM-NEXT-TEST |
| Study decision | navigate / Study decision | STUDY-DECISION |
| Inspect eligible provider | navigate / Inspect eligible provider | SETUP-CAPABILITY |
| Select reply 1 | select_reply / Select exact turn / topic; do not infer provider output | EXPERT-DISCUSS |
| Select reply 2 | select_reply / Select exact turn / topic; do not infer provider output | EXPERT-DISCUSS |
| Select reply 3 | select_reply / Select exact turn / topic; do not infer provider output | EXPERT-DISCUSS |
| Open exact retained result | navigate / Open exact retained result | MAT-FIT-PARTIAL |
| Open original evidence | navigate / Open original evidence | DATA-CALIBRATION |
| Edit Plan before explicit run | navigate / Edit Plan before explicit run | NUM-NEXT-TEST |
| Adopt judgment in Study | navigate / Adopt judgment in Study | STUDY-DECISION |
| Save reply draft | navigate / Save reply draft | REOPEN-EXPERT |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Draft question/source/roles without provider |
| edit | Topic/turn/reply owner; actual author retained |
| dirty | Save reply/discussion draft |
| running | Actual provider status separate from solver/Plan jobs |
| fail | Provider unavailable/limit preserves draft and retained turns |
| cancel | Pause next turns; solver cancel is separate |
| complete | Editable Plan / explicit Study judgment, no automatic adoption |
| reopen | Retained turns, sources and Plan refs without asking provider again |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-30와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## EXPERT-DRAFT — Question / provider unavailable

편집 원본: `screens/EXPERT-DRAFT.svg` · 미리보기: `screens/EXPERT-DRAFT.png` · owner: **Discussion D-02 / explicit Study link**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-30: 논점·질문 초안·자료 범위·역할, provider 미연결과 retained history. → 자료/결과 refs를 붙이고 draft를 작성한다. actual role response 요청만 inference를 사용한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open discussion | navigate / Open discussion | EXPERT-DRAFT |
| Save discussion | navigate / Save discussion | REOPEN-EXPERT |
| Pause / resume | navigate / Pause / resume | EXPERT-DISCUSS |
| Next-test Plan | navigate / Next-test Plan | NUM-NEXT-TEST |
| Study decision | navigate / Study decision | STUDY-DECISION |
| Inspect eligible provider | navigate / Inspect eligible provider | SETUP-CAPABILITY |
| Select reply 1 | select_reply / Select exact turn / topic; do not infer provider output | EXPERT-DISCUSS |
| Select reply 2 | select_reply / Select exact turn / topic; do not infer provider output | EXPERT-DISCUSS |
| Select reply 3 | select_reply / Select exact turn / topic; do not infer provider output | EXPERT-DISCUSS |
| Open exact retained result | navigate / Open exact retained result | MAT-FIT-PARTIAL |
| Open original evidence | navigate / Open original evidence | DATA-CALIBRATION |
| Edit Plan before explicit run | navigate / Edit Plan before explicit run | NUM-NEXT-TEST |
| Adopt judgment in Study | navigate / Adopt judgment in Study | STUDY-DECISION |
| Save reply draft | navigate / Save reply draft | REOPEN-EXPERT |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Draft question/source/roles without provider |
| edit | Topic/turn/reply owner; actual author retained |
| dirty | Save reply/discussion draft |
| running | Actual provider status separate from solver/Plan jobs |
| fail | Provider unavailable/limit preserves draft and retained turns |
| cancel | Pause next turns; solver cancel is separate |
| complete | Editable Plan / explicit Study judgment, no automatic adoption |
| reopen | Retained turns, sources and Plan refs without asking provider again |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-30와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## HOME-EMPTY — Open a document / independent tools

편집 원본: `screens/HOME-EMPTY.svg` · 미리보기: `screens/HOME-EMPTY.png` · owner: **Document chooser**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-01: 도구 이름, 최근 문서 이름·종류·위치·마지막 저장 시각. 내부 ID 입력칸은 없다. → Ctrl+O로 파일을 선택하거나 새 Data/Material/PDE/Plan/Study를 만든다. 필요한 owner로 바로 진입한다.
- FN-01: 기존 store와 같은 문서가 이미 열린 창, 별도 사본 여부. → 같은 store/document는 기존 창 활성화가 기본이다. 새 view는 같은 owner에 붙인다. 다른 store의 같은 ID는 별개 namespace로 표시한다.
- FN-33: Data/Material/PDE/Study 등의 독립 진입과 native optional installation. → CAD 미설치에서도 Research와 과거 결과를 연다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Current registered location | reference / 해당 없음 | Research store / user-selected folder | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open… | navigate / Open… | HOME-EMPTY |
| Recent documents | navigate / Recent documents | RECOVERY-REOPEN |
| Capabilities | navigate / Capabilities | SETUP-CAPABILITY |
| Study | navigate / Study | STUDY-EMPTY |
| Help / evidence | navigate / Help / evidence | REPORT-REVIEW |
| Data / test files | navigate / Data / test files | DATA-MAP |
| Material | navigate / Material | MAT-EMPTY |
| PDE | navigate / PDE | PDE-EQUATION |
| Numerical | navigate / Numerical | NUM-DOE |
| Runner | navigate / Runner | RUN-ACTIVE |
| Study | navigate / Study | STUDY-EMPTY |
| FreeCAD Pre | navigate / FreeCAD Pre | PRE-DESIGN |
| ParaView Post | navigate / ParaView Post | POST-OPEN |
| Evaluation | navigate / Evaluation | EVAL-STAGES |
| Expert | navigate / Expert | EXPERT-DRAFT |
| Open selected document / same owner | navigate / Open selected document / same owner | MAT-DIRTY |
| Locate portable copy… | navigate / Locate portable copy… | RECOVERY-REOPEN |
| Optional connection view | navigate / Optional connection view | WB-LINKS |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open or create the relevant owner record |
| edit | Use typed fields / contextual actions |
| dirty | Preserve owner draft / exact refs |
| running | No automatic activity in this board; observe external job separately |
| fail | Open diagnostic, save draft and retain evidence |
| cancel | Cancel preview / keep previous owner content |
| complete | Save exact record / explicit next tool |
| reopen | Restore saved refs / no hidden execution |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-01, FN-33와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## MAT-ADOPT-CONFLICT — Adopt c017 / target changed

편집 원본: `screens/MAT-ADOPT-CONFLICT.svg` · 미리보기: `screens/MAT-ADOPT-CONFLICT.png` · owner: **Material + candidate proposal**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-07: 채택 후보 μ=0.862, fit 당시 Material r17, 현재 r18의 μ=0.90와 protocol 변경. → 기준/현재/후보 비교 후 새 분기를 만들거나 재검토한다. stale candidate를 현재 모델에 바로 덮어쓰지 않는다.
- FN-21: 후보값 vs 현재 각 owner의 exact revision·changed fields. → owner별 채택 preview→유효성 검사→새 revision 또는 분기를 만든다.
- FN-24: 선택 후보의 owner별 변경 목록·revision conflict. → 명시 채택 또는 새 분기로 저장한다. 점 선택·정렬만으로 값을 적용하지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Propose c017 on current r18… | navigate / Propose c017 on current r18… | MAT-ADOPT-DRAFT |
| Create Material branch | navigate / Create Material branch | MAT-BRANCH-DRAFT |
| Cancel / keep current | navigate / Cancel / keep current | MAT-FIT-PARTIAL |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | New law/protocol or import observation |
| edit | Material value and embedded Plan bound have different Undo owners |
| dirty | Per-owner save/source refresh/Plan starting values explicit |
| running | Frozen input; current draft can diverge; old/late result linked correctly |
| fail | Failed candidate/input diagnostics or save receipt; no made-up curve |
| cancel | Stop submission separately from job terminal and window close |
| complete | Retained details/holdout → explicit owner adoption → save |
| reopen | Open saved rN or separate recovery capsule; never evaluate on selection |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-07, FN-21, FN-24와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## MAT-ADOPT-DRAFT — Material adoption / dirty target draft on r18

편집 원본: `screens/MAT-ADOPT-DRAFT.svg` · 미리보기: `screens/MAT-ADOPT-DRAFT.png` · owner: **Material target / same existing owner**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-07: 이전/현재 입력·draft·saved revision·정확한 결과와 해당 복구 상태. 같은 기능의 결과를 다른 예시로 대체하지 않는다. → 명시 Apply/Save/Cancel/재열기로 전이하며 frozen 결과는 원 입력에 남긴다. unsupported/invalid required 입력의 Run은 계속 차단한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Retained candidate | navigate / Retained candidate | MAT-FIT-PARTIAL |
| Save Material | navigate / Save Material | MAT-ADOPT-SAVED |
| Review original conflict | navigate / Review original conflict | MAT-ADOPT-CONFLICT |
| Save acknowledged Material draft | navigate / Save acknowledged Material draft | MAT-ADOPT-SAVED |
| Inspect retained c017 / source r17 | navigate / Inspect retained c017 / source r17 | MAT-FIT-PARTIAL |
| Review target conflict / cancel proposal | navigate / Review target conflict / cancel proposal | MAT-ADOPT-CONFLICT |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | New law/protocol or import observation |
| edit | Material value and embedded Plan bound have different Undo owners |
| dirty | Per-owner save/source refresh/Plan starting values explicit |
| running | Frozen input; current draft can diverge; old/late result linked correctly |
| fail | Failed candidate/input diagnostics or save receipt; no made-up curve |
| cancel | Stop submission separately from job terminal and window close |
| complete | Retained details/holdout → explicit owner adoption → save |
| reopen | Open saved rN or separate recovery capsule; never evaluate on selection |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-07와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## MAT-ADOPT-SAVED — Material adoption / saved r19

편집 원본: `screens/MAT-ADOPT-SAVED.svg` · 미리보기: `screens/MAT-ADOPT-SAVED.png` · owner: **Material target / same existing owner**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-07: 이전/현재 입력·draft·saved revision·정확한 결과와 해당 복구 상태. 같은 기능의 결과를 다른 예시로 대체하지 않는다. → 명시 Apply/Save/Cancel/재열기로 전이하며 frozen 결과는 원 입력에 남긴다. unsupported/invalid required 입력의 Run은 계속 차단한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Retained candidate | navigate / Retained candidate | MAT-FIT-PARTIAL |
| Cold reopen saved r19 | navigate / Cold reopen saved r19 | REOPEN-MAT-ADOPTED |
| Review original conflict | navigate / Review original conflict | MAT-ADOPT-CONFLICT |
| Cold reopen saved r19 | navigate / Cold reopen saved r19 | REOPEN-MAT-ADOPTED |
| Inspect retained c017 / source r17 | navigate / Inspect retained c017 / source r17 | MAT-FIT-PARTIAL |
| Review target conflict / cancel proposal | navigate / Review target conflict / cancel proposal | MAT-ADOPT-CONFLICT |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | New law/protocol or import observation |
| edit | Material value and embedded Plan bound have different Undo owners |
| dirty | Per-owner save/source refresh/Plan starting values explicit |
| running | Frozen input; current draft can diverge; old/late result linked correctly |
| fail | Failed candidate/input diagnostics or save receipt; no made-up curve |
| cancel | Stop submission separately from job terminal and window close |
| complete | Retained details/holdout → explicit owner adoption → save |
| reopen | Open saved rN or separate recovery capsule; never evaluate on selection |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-07와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## MAT-BRANCH-DRAFT — Candidate c017 / new Material branch

편집 원본: `screens/MAT-BRANCH-DRAFT.svg` · 미리보기: `screens/MAT-BRANCH-DRAFT.png` · owner: **Material M-branch-01 / independent new ID**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-07: candidate c017/source17·현재 target18·새 문서ID M-branch-01. → 분기를 명시 생성한다. 원 Material·Plan은 바꾸지 않고 새 owner draft에 채택값을 반영한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Save branch | navigate / Save branch | MAT-BRANCH-SAVED |
| Original target conflict | navigate / Original target conflict | MAT-ADOPT-CONFLICT |
| Retained candidate | navigate / Retained candidate | MAT-FIT-PARTIAL |
| Save new branch to independent location | navigate / Save new branch to independent location | MAT-BRANCH-SAVED |
| Return to original target conflict / preserve branch draft | navigate / Return to original target conflict / preserve branch draft | MAT-ADOPT-CONFLICT |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | New law/protocol or import observation |
| edit | Material value and embedded Plan bound have different Undo owners |
| dirty | Per-owner save/source refresh/Plan starting values explicit |
| running | Frozen input; current draft can diverge; old/late result linked correctly |
| fail | Failed candidate/input diagnostics or save receipt; no made-up curve |
| cancel | Stop submission separately from job terminal and window close |
| complete | Retained details/holdout → explicit owner adoption → save |
| reopen | Open saved rN or separate recovery capsule; never evaluate on selection |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-07와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## MAT-BRANCH-SAVED — Candidate c017 / new Material branch

편집 원본: `screens/MAT-BRANCH-SAVED.svg` · 미리보기: `screens/MAT-BRANCH-SAVED.png` · owner: **Material M-branch-01 / independent new ID**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-07: M-branch-01 r1·derived_from r18/c017·원 target18불변. → 분기 저장 위치를 확인하고 새프로세스에서 동일 분기를 연다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Cold reopen branch | navigate / Cold reopen branch | REOPEN-MAT-BRANCH |
| Original target conflict | navigate / Original target conflict | MAT-ADOPT-CONFLICT |
| Retained candidate | navigate / Retained candidate | MAT-FIT-PARTIAL |
| Reopen saved branch r1 without evaluation | navigate / Reopen saved branch r1 without evaluation | REOPEN-MAT-BRANCH |
| Return to original target conflict / preserve branch draft | navigate / Return to original target conflict / preserve branch draft | MAT-ADOPT-CONFLICT |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | New law/protocol or import observation |
| edit | Material value and embedded Plan bound have different Undo owners |
| dirty | Per-owner save/source refresh/Plan starting values explicit |
| running | Frozen input; current draft can diverge; old/late result linked correctly |
| fail | Failed candidate/input diagnostics or save receipt; no made-up curve |
| cancel | Stop submission separately from job terminal and window close |
| complete | Retained details/holdout → explicit owner adoption → save |
| reopen | Open saved rN or separate recovery capsule; never evaluate on selection |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-07와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## MAT-CONSTITUTIVE — Constitutive integration study

편집 원본: `screens/MAT-CONSTITUTIVE.svg` · 미리보기: `screens/MAT-CONSTITUTIVE.png` · owner: **Material + Numerical Plan (embedded)**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-08: law source/build/interface, stress/strain measure, state 변수, integration history. → 인장·압축·전단·제하·반복 등 protocol을 선택하고 초기 state와 증분 순서를 정의한다.
- FN-08: 선택 증분의 trial/committed state, local residual·substep·return mapping 진단. → 실패 증분을 확대하고 step size만 바꾼 새 evaluation을 만든다. 이전 state를 수동 덮어쓰지 않는다.
- FN-08: 반환 tangent와 기준 directional derivative, perturbation scale별 오차 곡선. → 정확한 stress/strain pair·tensor index·frame을 고른 뒤 FD/complex-step 가능한 경우만 독립 검사를 실행한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open… | navigate / Open… | HOME-EMPTY |
| Save Material | navigate / Save Material | SAVE-PARTIAL |
| Save both… | navigate / Save both… | SAVE-PARTIAL |
| Direct evaluation | navigate / Direct evaluation | MAT-CONSTITUTIVE |
| Fit blocked… | navigate / Fit blocked… | MAT-PROTOCOL |
| Results | navigate / Results | MAT-FIT-PARTIAL |
| Edit test A protocol | open_protocol / Same Material owner protocol editor | MAT-PROTOCOL |
| Observation / Data r4 | navigate / Observation / Data r4 | DATA-EDIT |
| Protocol / measures | navigate / Protocol / measures | MAT-PROTOCOL |
| Edit current mu · F2 | edit / Material buffer, Enter updates Material only | MAT-DIRTY |
| Edit Plan bounds · F2 | edit / Plan owner bounds only | MAT-DIRTY |
| Refresh Plan source… | navigate / Refresh Plan source… | MAT-DIRTY |
| Open same Plan | navigate / Open same Plan | NUM-OPTIMIZE |
| Inspect MFront interface / build | navigate / Inspect MFront interface / build | MAT-FE-TRANSFER |
| Retain with input + diagnostics | navigate / Retain with input + diagnostics | REOPEN-CONSTITUTIVE |
| Open separate inverse-fit evidence | navigate / Open separate inverse-fit evidence | MAT-FIT-PARTIAL |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | New law/protocol or import observation |
| edit | Material value and embedded Plan bound have different Undo owners |
| dirty | Per-owner save/source refresh/Plan starting values explicit |
| running | Frozen input; current draft can diverge; old/late result linked correctly |
| fail | Failed candidate/input diagnostics or save receipt; no made-up curve |
| cancel | Stop submission separately from job terminal and window close |
| complete | Retained details/holdout → explicit owner adoption → save |
| reopen | Open saved rN or separate recovery capsule; never evaluate on selection |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-08와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## MAT-DIRTY — Rubber *  +  Fit A *

편집 원본: `screens/MAT-DIRTY.svg` · 미리보기: `screens/MAT-DIRTY.png` · owner: **Material + Numerical Plan (embedded)**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-02: 상단 Material * / Plan * 두 표시, 선택 셀의 owner, 입력중 ‘1e’와 owner에 반영된 0.85 MPa. → Enter는 셀 버퍼를 해당 owner draft에 제출하고 Esc는 버퍼만 취소한다. 숫자 오류는 문자열 draft와 셀 진단으로 저장 가능하게 보존한다.
- FN-04: 관측 source mask와 Plan 연구 선택/holdout이 다른 열. → 연결된 관측을 Plan에 고정하고 fit 구간/weight만 Plan에서 바꾼다.
- FN-06: 직접 평가의 frozen input과 응력/에너지·state 곡선; 현재 draft와 다를 수 있다. → 원값과 tangent/state를 연다. ‘결과 보존’ 후 저장하면 새 프로세스에서 재계산 없이 읽는다.
- FN-07: 시험 A/B 관측 refs·roles, Material current μ=0.85 MPa와 Plan lower=0.40/upper=1.40 MPa. → 같은 창에서 source Data dock, protocol, Plan 범위·mask·weight를 편집한다. Material 값과 Plan 범위는 별도 owner로 표시한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open… | navigate / Open… | HOME-EMPTY |
| Save Material | navigate / Save Material | SAVE-PARTIAL |
| Save both… | navigate / Save both… | SAVE-PARTIAL |
| Direct evaluation | navigate / Direct evaluation | MAT-CONSTITUTIVE |
| Fit blocked… | navigate / Fit blocked… | MAT-PROTOCOL |
| Results | navigate / Results | MAT-FIT-PARTIAL |
| Edit test A protocol | open_protocol / Same Material owner protocol editor | MAT-PROTOCOL |
| Observation / Data r4 | navigate / Observation / Data r4 | DATA-EDIT |
| Protocol / measures | navigate / Protocol / measures | MAT-PROTOCOL |
| Edit current mu · F2 | edit / Material buffer, Enter updates Material only | MAT-DIRTY |
| Edit Plan bounds · F2 | edit / Plan owner bounds only | MAT-DIRTY |
| Refresh Plan source… | navigate / Refresh Plan source… | MAT-DIRTY |
| Open same Plan | navigate / Open same Plan | NUM-OPTIMIZE |
| Review source / save conflict | navigate / Review source / save conflict | CLIENT-CONFLICT |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | New law/protocol or import observation |
| edit | Material value and embedded Plan bound have different Undo owners |
| dirty | Per-owner save/source refresh/Plan starting values explicit |
| running | Frozen input; current draft can diverge; old/late result linked correctly |
| fail | Failed candidate/input diagnostics or save receipt; no made-up curve |
| cancel | Stop submission separately from job terminal and window close |
| complete | Retained details/holdout → explicit owner adoption → save |
| reopen | Open saved rN or separate recovery capsule; never evaluate on selection |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-02, FN-04, FN-06, FN-07와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## MAT-EMPTY — Untitled material / unsaved

편집 원본: `screens/MAT-EMPTY.svg` · 미리보기: `screens/MAT-EMPTY.png` · owner: **New Material owner / no Plan**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-06: 법칙 목록의 지원 operation·필요 runtime·응력척도·현재 상태. → 모델을 고르고 계수를 표에서 편집한다. 임의 law를 기존 backend 이름에 끼워 넣지 않는다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Constitutive law | enum / 해당 없음 | Select a supported law… | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Material name | text / 해당 없음 | Untitled material | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open material | navigate / Open material | MAT-DIRTY |
| Import observations | navigate / Import observations | DATA-MAP |
| Create protocol | navigate / Create protocol | MAT-PROTOCOL |
| Choose law / create test protocol | navigate / Choose law / create test protocol | MAT-PROTOCOL |
| Import two synthetic CSVs | navigate / Import two synthetic CSVs | DATA-MAP |
| Create a prescribed-F protocol | navigate / Create a prescribed-F protocol | MAT-PROTOCOL |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | New law/protocol or import observation |
| edit | Material value and embedded Plan bound have different Undo owners |
| dirty | Per-owner save/source refresh/Plan starting values explicit |
| running | Frozen input; current draft can diverge; old/late result linked correctly |
| fail | Failed candidate/input diagnostics or save receipt; no made-up curve |
| cancel | Stop submission separately from job terminal and window close |
| complete | Retained details/holdout → explicit owner adoption → save |
| reopen | Open saved rN or separate recovery capsule; never evaluate on selection |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-06와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## MAT-FE-TRANSFER — Assign retained law to FE

편집 원본: `screens/MAT-FE-TRANSFER.svg` · 미리보기: `screens/MAT-FE-TRANSFER.png` · owner: **Material + Numerical Plan (embedded)**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-09: source law·measure·state·단위와 target solver/version·law·element family 지원표. → ‘해석에 할당’에서 지원되는 변환을 고른다. adapter가 없으면 draft mapping만 저장한다.
- FN-09: 계수 mapping 표와 단위 변환, 누락/추가 필수값·온도/rate 범위. → 공급되지 않은 값은 직접 근거와 함께 입력한다. 임의 default strength/failure 값은 채우지 않는다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Analysis / exact revision | reference / 해당 없음 | Bracket / r12 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Region / dimension | reference / 해당 없음 | Base solid / 3D | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open… | navigate / Open… | HOME-EMPTY |
| Save Material | navigate / Save Material | SAVE-PARTIAL |
| Save both… | navigate / Save both… | SAVE-PARTIAL |
| Direct evaluation | navigate / Direct evaluation | MAT-CONSTITUTIVE |
| Fit blocked… | navigate / Fit blocked… | MAT-PROTOCOL |
| Results | navigate / Results | MAT-FIT-PARTIAL |
| Edit test A protocol | open_protocol / Same Material owner protocol editor | MAT-PROTOCOL |
| Observation / Data r4 | navigate / Observation / Data r4 | DATA-EDIT |
| Protocol / measures | navigate / Protocol / measures | MAT-PROTOCOL |
| Edit current mu · F2 | edit / Material buffer, Enter updates Material only | MAT-DIRTY |
| Edit Plan bounds · F2 | edit / Plan owner bounds only | MAT-DIRTY |
| Refresh Plan source… | navigate / Refresh Plan source… | MAT-DIRTY |
| Open same Plan | navigate / Open same Plan | NUM-OPTIMIZE |
| Save assignment draft | navigate / Save assignment draft | REOPEN-FE-ASSIGNMENT |
| Open native material Tasks | navigate / Open native material Tasks | PRE-FEM |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | New law/protocol or import observation |
| edit | Material value and embedded Plan bound have different Undo owners |
| dirty | Per-owner save/source refresh/Plan starting values explicit |
| running | Frozen input; current draft can diverge; old/late result linked correctly |
| fail | Failed candidate/input diagnostics or save receipt; no made-up curve |
| cancel | Stop submission separately from job terminal and window close |
| complete | Retained details/holdout → explicit owner adoption → save |
| reopen | Open saved rN or separate recovery capsule; never evaluate on selection |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-09와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## MAT-FIT-PARTIAL — Fit A · retained results

편집 원본: `screens/MAT-FIT-PARTIAL.svg` · 미리보기: `screens/MAT-FIT-PARTIAL.png` · owner: **Material + Numerical Plan (embedded)**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-07: 후보별 train objective·실패·상세보존 여부. best/확인 평가의 holdout만 실제 값, 다른 후보는 NOT_EVALUATED/NOT_RETAINED. → 행 선택으로 이미 보존된 원값/잔차만 연다. 없는 후보 곡선은 ‘선택 후보 상세·holdout 평가’를 명시 실행해 새 evaluation/ref/예산으로 얻는다. 행 선택은 계산하지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open… | navigate / Open… | HOME-EMPTY |
| Save Material | navigate / Save Material | SAVE-PARTIAL |
| Save both… | navigate / Save both… | SAVE-PARTIAL |
| Direct evaluation | navigate / Direct evaluation | MAT-CONSTITUTIVE |
| Run fit… | navigate / Run fit… | MAT-FIT-RUNNING |
| Results | navigate / Results | MAT-FIT-PARTIAL |
| Edit test A protocol | open_protocol / Same Material owner protocol editor | MAT-PROTOCOL |
| Observation / Data r4 | navigate / Observation / Data r4 | DATA-EDIT |
| Protocol / measures | navigate / Protocol / measures | MAT-PROTOCOL |
| Edit current mu · F2 | edit / Material buffer, Enter updates Material only | MAT-DIRTY |
| Edit Plan bounds · F2 | edit / Plan owner bounds only | MAT-DIRTY |
| Refresh Plan source… | navigate / Refresh Plan source… | MAT-DIRTY |
| Open same Plan | navigate / Open same Plan | NUM-OPTIMIZE |
| Evaluate selected details… | navigate / Evaluate selected details… | MAT-FIT-RUNNING |
| Adopt candidate c017… | navigate / Adopt candidate c017… | MAT-ADOPT-CONFLICT |
| Open exact result in Study | navigate / Open exact result in Study | STUDY-DECISION |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | New law/protocol or import observation |
| edit | Material value and embedded Plan bound have different Undo owners |
| dirty | Per-owner save/source refresh/Plan starting values explicit |
| running | Frozen input; current draft can diverge; old/late result linked correctly |
| fail | Failed candidate/input diagnostics or save receipt; no made-up curve |
| cancel | Stop submission separately from job terminal and window close |
| complete | Retained details/holdout → explicit owner adoption → save |
| reopen | Open saved rN or separate recovery capsule; never evaluate on selection |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-07와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## MAT-FIT-RUNNING — Fit A · candidate evaluations

편집 원본: `screens/MAT-FIT-RUNNING.svg` · 미리보기: `screens/MAT-FIT-RUNNING.png` · owner: **Material + Numerical Plan (embedded)**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-07: method·seed·budget, frozen μ 범위/관측 revision, 현재 평가 수와 실제 실행 phase. → Fit을 실행한다. 편집을 계속하면 결과는 출발 snapshot에 붙는다. 전체 취소는 다음 후보 제출부터 중단한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open… | navigate / Open… | HOME-EMPTY |
| Save Material | navigate / Save Material | SAVE-PARTIAL |
| Save both… | navigate / Save both… | SAVE-PARTIAL |
| Direct evaluation | navigate / Direct evaluation | MAT-CONSTITUTIVE |
| Monitor fit | navigate / Monitor fit | RUN-ACTIVE |
| Results | navigate / Results | MAT-FIT-PARTIAL |
| Edit test A protocol | open_protocol / Same Material owner protocol editor | MAT-PROTOCOL |
| Observation / Data r4 | navigate / Observation / Data r4 | DATA-EDIT |
| Protocol / measures | navigate / Protocol / measures | MAT-PROTOCOL |
| Edit current mu · F2 | edit / Material buffer, Enter updates Material only | MAT-DIRTY |
| Edit Plan bounds · F2 | edit / Plan owner bounds only | MAT-DIRTY |
| Refresh Plan source… | navigate / Refresh Plan source… | MAT-DIRTY |
| Open same Plan | navigate / Open same Plan | NUM-OPTIMIZE |
| Open attempt monitor | navigate / Open attempt monitor | RUN-ACTIVE |
| Cancel whole fit… | navigate / Cancel whole fit… | RUN-CANCEL |
| Simulate partial completion | navigate / Simulate partial completion | MAT-FIT-PARTIAL |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | New law/protocol or import observation |
| edit | Material value and embedded Plan bound have different Undo owners |
| dirty | Per-owner save/source refresh/Plan starting values explicit |
| running | Frozen input; current draft can diverge; old/late result linked correctly |
| fail | Failed candidate/input diagnostics or save receipt; no made-up curve |
| cancel | Stop submission separately from job terminal and window close |
| complete | Retained details/holdout → explicit owner adoption → save |
| reopen | Open saved rN or separate recovery capsule; never evaluate on selection |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-07와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## MAT-PROTOCOL — A-01 · protocol and measures

편집 원본: `screens/MAT-PROTOCOL.svg` · 미리보기: `screens/MAT-PROTOCOL.png` · owner: **Material + Numerical Plan (embedded)**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-03: Material 시험 목록의 A=train/B=holdout 제안, 정확 Data saved/import refs, P11와 axial stretch. → 관측으로 연결을 누르면 Material 안에 Data 편집 dock와 동일 Plan 관측표가 열린다. 별도 wizard 왕복은 없다.
- FN-06: 축방향 제어 이력, 횡방향 자유/고정/전체 F 지정, 모델의 반환 stress measure. → time·strain/stretch/stress control과 온도·초기 상태를 설정한다. 자유 횡방향은 mixed-control 구현이 준비된 adapter만 실행한다.
- FN-06: F11/F22/F33 및 determinant, 제어/응답 구별과 시간 단조성. → 현재 지원 ‘전체 F 지정’으로 직접 평가하거나 새 횡조건을 draft로 저장한다. 필수 불일치는 셀에서 수정한다.
- FN-07: P11/engineering strain/axial stretch·횡조건 검사가 맞는지, 학습과 holdout 표본 수. → 관측과 예측이 같은 measure/location/frame/time인지 검사한다. Cauchy↔Piola는 검증된 recipe가 없으면 실행을 막는다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Control mode | enum / 해당 없음 | Uniaxial traction-free | Prescribed F / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Longitudinal control | expression / 해당 없음 | F11 = 1 + e(t) | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Lateral targets | number / MPa | P22 = P33 = 0 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | traction-free |
| Observation measure | enum / 해당 없음 | first_Piola / P11 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Time axis / frame | reference / 해당 없음 | time [s] / material_cartesian | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Cauchy conversion | enum / 해당 없음 | Disabled: needs J / area | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open… | navigate / Open… | HOME-EMPTY |
| Save Material | navigate / Save Material | SAVE-PARTIAL |
| Save both… | navigate / Save both… | SAVE-PARTIAL |
| Direct evaluation | navigate / Direct evaluation | MAT-CONSTITUTIVE |
| Fit blocked… | navigate / Fit blocked… | MAT-PROTOCOL |
| Results | navigate / Results | MAT-FIT-PARTIAL |
| Edit test A protocol | open_protocol / Same Material owner protocol editor | MAT-PROTOCOL |
| Observation / Data r4 | navigate / Observation / Data r4 | DATA-EDIT |
| Protocol / measures | navigate / Protocol / measures | MAT-PROTOCOL |
| Edit current mu · F2 | edit / Material buffer, Enter updates Material only | MAT-DIRTY |
| Edit Plan bounds · F2 | edit / Plan owner bounds only | MAT-DIRTY |
| Refresh Plan source… | navigate / Refresh Plan source… | MAT-DIRTY |
| Open same Plan | navigate / Open same Plan | NUM-OPTIMIZE |
| Keep protocol draft / review curves | navigate / Keep protocol draft / review curves | MAT-DIRTY |
| Use supported prescribed-F | navigate / Use supported prescribed-F | MAT-CONSTITUTIVE |
| Preview proposed ready state | navigate / Preview proposed ready state | MAT-READY |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | New law/protocol or import observation |
| edit | Material value and embedded Plan bound have different Undo owners |
| dirty | Per-owner save/source refresh/Plan starting values explicit |
| running | Frozen input; current draft can diverge; old/late result linked correctly |
| fail | Failed candidate/input diagnostics or save receipt; no made-up curve |
| cancel | Stop submission separately from job terminal and window close |
| complete | Retained details/holdout → explicit owner adoption → save |
| reopen | Open saved rN or separate recovery capsule; never evaluate on selection |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-03, FN-06, FN-07와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## MAT-READY — PROPOSED future-supported mixed-control state

편집 원본: `screens/MAT-READY.svg` · 미리보기: `screens/MAT-READY.png` · owner: **Material + Numerical Plan (embedded)**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-07: 현재 미지원 입력은 blocked. 별도 미래 지원 상태는 PROPOSED / SIMULATED로 표시. → 미지원 Run으로 성공 상태를 만들지 않는다. 별도 미래 branch를 명시 선택해 지원이 구현된 뒤의 조작만 검토한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open… | navigate / Open… | HOME-EMPTY |
| Save Material | navigate / Save Material | SAVE-PARTIAL |
| Save both… | navigate / Save both… | SAVE-PARTIAL |
| Direct evaluation | navigate / Direct evaluation | MAT-CONSTITUTIVE |
| Run fit… | navigate / Run fit… | MAT-FIT-RUNNING |
| Results | navigate / Results | MAT-FIT-PARTIAL |
| Edit test A protocol | open_protocol / Same Material owner protocol editor | MAT-PROTOCOL |
| Observation / Data r4 | navigate / Observation / Data r4 | DATA-EDIT |
| Protocol / measures | navigate / Protocol / measures | MAT-PROTOCOL |
| Edit current mu · F2 | edit / Material buffer, Enter updates Material only | MAT-DIRTY |
| Edit Plan bounds · F2 | edit / Plan owner bounds only | MAT-DIRTY |
| Refresh Plan source… | navigate / Refresh Plan source… | MAT-DIRTY |
| Open same Plan | navigate / Open same Plan | NUM-OPTIMIZE |
| Review source / save conflict | navigate / Review source / save conflict | CLIENT-CONFLICT |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | New law/protocol or import observation |
| edit | Material value and embedded Plan bound have different Undo owners |
| dirty | Per-owner save/source refresh/Plan starting values explicit |
| running | Frozen input; current draft can diverge; old/late result linked correctly |
| fail | Failed candidate/input diagnostics or save receipt; no made-up curve |
| cancel | Stop submission separately from job terminal and window close |
| complete | Retained details/holdout → explicit owner adoption → save |
| reopen | Open saved rN or separate recovery capsule; never evaluate on selection |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-07와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## NUM-ADOPT-CONFLICT — p19 / owner-specific adoption conflict

편집 원본: `screens/NUM-ADOPT-CONFLICT.svg` · 미리보기: `screens/NUM-ADOPT-CONFLICT.png` · owner: **N-MOO/r4 proposal → CAD and Material owners**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-24: Pareto p19 / CADr12→r13 및 Materialr17→r18 충돌, thickness13.7mm / mu1.12MPa. → 각 owner 변경을 검토해 명시 draft Apply→각 Save→group receipt 게시. 취소는 current owners와 p19 결과를 유지하며 Material fit c017로 바뀌지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Cancel adoption | navigate / Cancel adoption | NUM-MOO |
| Inspect p19 | navigate / Inspect p19 | NUM-CASE-MOO |
| Keep proposal / save | navigate / Keep proposal / save | REOPEN-NUM-MOO |
| Cancel / keep current owners | navigate / Cancel / keep current owners | NUM-MOO |
| Inspect exact p19 input | navigate / Inspect exact p19 input | NUM-CASE-MOO |
| Save proposal for explicit review | navigate / Save proposal for explicit review | REOPEN-NUM-MOO |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Create Plan from supported evaluator or external exchange |
| edit | Typed variables/observations/method; source owner bounds retained |
| dirty | Plan source and starts explicitly refreshed/saved |
| running | Fixed mask/method/seed/budget/source; failures and penalties separate |
| fail | Select failed candidate, exact input/log; missing NOT_EVALUATED |
| cancel | Stop next submissions, retain late result, no hidden resume |
| complete | Method-specific evidence → explicit confirmation/adoption |
| reopen | History browse without exact engine resume unless checkpoint supported |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-24와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## NUM-BATCH — External batch / import exact candidate responses

편집 원본: `screens/NUM-BATCH.svg` · 미리보기: `screens/NUM-BATCH.png` · owner: **N-Batch/r2**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-26: case/exchange/candidate IDs·values/units·input files·hash·expected outputs. → export_batch로 실행 묶음을 만든다. 이것은 solver 실행이 아니다.
- FN-26: 돌아온 결과의 exchange/case/candidate identity·status·missing/duplicate rows. → import_batch로 검증하고 missing은 NOT_EVALUATED로 남긴다. 원래 Plan/후보에서 결과를 연다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open Fit A | navigate / Open Fit A | NUM-OPTIMIZE |
| Save Plan | navigate / Save Plan | REOPEN-NUM-BATCH |
| Evaluation editor | navigate / Evaluation editor | EVAL-STAGES |
| Run / analyze | navigate / Run / analyze | RUN-NUM-BATCH |
| Results | navigate / Results | NUM-CASE-BATCH |
| Inspect selected | navigate / Inspect selected | NUM-CASE-BATCH |
| DOE | navigate / DOE | NUM-DOE |
| Optimization / inverse | navigate / Optimization / inverse | NUM-OPTIMIZE |
| Sensitivity | navigate / Sensitivity | NUM-SENSITIVITY |
| UQ | navigate / UQ | NUM-UQ |
| Surrogate | navigate / Surrogate | NUM-SURROGATE |
| Multiobjective | navigate / Multiobjective | NUM-MOO |
| External batch | navigate / External batch | NUM-BATCH |
| Inspect selected result | navigate / Inspect selected result | NUM-CASE-BATCH |
| Confirm with evaluator… | navigate / Confirm with evaluator… | RUN-NUM-BATCH |
| Save Plan / reopen without rerun | navigate / Save Plan / reopen without rerun | REOPEN-NUM-BATCH |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Create Plan from supported evaluator or external exchange |
| edit | Typed variables/observations/method; source owner bounds retained |
| dirty | Plan source and starts explicitly refreshed/saved |
| running | Fixed mask/method/seed/budget/source; failures and penalties separate |
| fail | Select failed candidate, exact input/log; missing NOT_EVALUATED |
| cancel | Stop next submissions, retain late result, no hidden resume |
| complete | Method-specific evidence → explicit confirmation/adoption |
| reopen | History browse without exact engine resume unless checkpoint supported |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-26와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## NUM-CASE-BATCH — b01 / exact retained case

편집 원본: `screens/NUM-CASE-BATCH.svg` · 미리보기: `screens/NUM-CASE-BATCH.png` · owner: **N-Batch/r2**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-26: 선택 candidate/analysis의 원 입력·결과·단위·validity·NOT_RETAINED 상태. → 같은 method Plan과 case를 유지해 조회한다. 행 선택은 새 evaluation을 만들지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Return to method | navigate / Return to method | NUM-BATCH |
| Open same case run | navigate / Open same case run | RUN-NUM-BATCH |
| Save / reopen | navigate / Save / reopen | REOPEN-NUM-BATCH |
| Keep selection / return to method | navigate / Keep selection / return to method | NUM-BATCH |
| Explicit confirmation (new evaluation) | navigate / Explicit confirmation (new evaluation) | RUN-NUM-BATCH |
| Save exact case references | navigate / Save exact case references | REOPEN-NUM-BATCH |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Create Plan from supported evaluator or external exchange |
| edit | Typed variables/observations/method; source owner bounds retained |
| dirty | Plan source and starts explicitly refreshed/saved |
| running | Fixed mask/method/seed/budget/source; failures and penalties separate |
| fail | Select failed candidate, exact input/log; missing NOT_EVALUATED |
| cancel | Stop next submissions, retain late result, no hidden resume |
| complete | Method-specific evidence → explicit confirmation/adoption |
| reopen | History browse without exact engine resume unless checkpoint supported |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-26와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## NUM-CASE-DOE — c001 / exact retained case

편집 원본: `screens/NUM-CASE-DOE.svg` · 미리보기: `screens/NUM-CASE-DOE.png` · owner: **N-DOE/r3**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-20: 선택 candidate/analysis의 원 입력·결과·단위·validity·NOT_RETAINED 상태. → 같은 method Plan과 case를 유지해 조회한다. 행 선택은 새 evaluation을 만들지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Return to method | navigate / Return to method | NUM-DOE |
| Open same case run | navigate / Open same case run | RUN-NUM-DOE |
| Save / reopen | navigate / Save / reopen | REOPEN-NUM-DOE |
| Keep selection / return to method | navigate / Keep selection / return to method | NUM-DOE |
| Explicit confirmation (new evaluation) | navigate / Explicit confirmation (new evaluation) | RUN-NUM-DOE |
| Save exact case references | navigate / Save exact case references | REOPEN-NUM-DOE |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Create Plan from supported evaluator or external exchange |
| edit | Typed variables/observations/method; source owner bounds retained |
| dirty | Plan source and starts explicitly refreshed/saved |
| running | Fixed mask/method/seed/budget/source; failures and penalties separate |
| fail | Select failed candidate, exact input/log; missing NOT_EVALUATED |
| cancel | Stop next submissions, retain late result, no hidden resume |
| complete | Method-specific evidence → explicit confirmation/adoption |
| reopen | History browse without exact engine resume unless checkpoint supported |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-20와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## NUM-CASE-MOO — p19 / exact retained case

편집 원본: `screens/NUM-CASE-MOO.svg` · 미리보기: `screens/NUM-CASE-MOO.png` · owner: **N-MOO/r4**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-24: 선택 candidate/analysis의 원 입력·결과·단위·validity·NOT_RETAINED 상태. → 같은 method Plan과 case를 유지해 조회한다. 행 선택은 새 evaluation을 만들지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Return to method | navigate / Return to method | NUM-MOO |
| Open same case run | navigate / Open same case run | RUN-NUM-MOO |
| Save / reopen | navigate / Save / reopen | REOPEN-NUM-MOO |
| Keep selection / return to method | navigate / Keep selection / return to method | NUM-MOO |
| Explicit confirmation (new evaluation) | navigate / Explicit confirmation (new evaluation) | RUN-NUM-MOO |
| Save exact case references | navigate / Save exact case references | REOPEN-NUM-MOO |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Create Plan from supported evaluator or external exchange |
| edit | Typed variables/observations/method; source owner bounds retained |
| dirty | Plan source and starts explicitly refreshed/saved |
| running | Fixed mask/method/seed/budget/source; failures and penalties separate |
| fail | Select failed candidate, exact input/log; missing NOT_EVALUATED |
| cancel | Stop next submissions, retain late result, no hidden resume |
| complete | Method-specific evidence → explicit confirmation/adoption |
| reopen | History browse without exact engine resume unless checkpoint supported |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-24와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## NUM-CASE-SENSITIVITY — thickness / exact retained case

편집 원본: `screens/NUM-CASE-SENSITIVITY.svg` · 미리보기: `screens/NUM-CASE-SENSITIVITY.png` · owner: **N-Sobol/r2**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-20: 선택 candidate/analysis의 원 입력·결과·단위·validity·NOT_RETAINED 상태. → 같은 method Plan과 case를 유지해 조회한다. 행 선택은 새 evaluation을 만들지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Return to method | navigate / Return to method | NUM-SENSITIVITY |
| Open same case run | navigate / Open same case run | RUN-NUM-SENSITIVITY |
| Save / reopen | navigate / Save / reopen | REOPEN-NUM-SENSITIVITY |
| Keep selection / return to method | navigate / Keep selection / return to method | NUM-SENSITIVITY |
| Explicit confirmation (new evaluation) | navigate / Explicit confirmation (new evaluation) | RUN-NUM-SENSITIVITY |
| Save exact case references | navigate / Save exact case references | REOPEN-NUM-SENSITIVITY |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Create Plan from supported evaluator or external exchange |
| edit | Typed variables/observations/method; source owner bounds retained |
| dirty | Plan source and starts explicitly refreshed/saved |
| running | Fixed mask/method/seed/budget/source; failures and penalties separate |
| fail | Select failed candidate, exact input/log; missing NOT_EVALUATED |
| cancel | Stop next submissions, retain late result, no hidden resume |
| complete | Method-specific evidence → explicit confirmation/adoption |
| reopen | History browse without exact engine resume unless checkpoint supported |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-20와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## NUM-CASE-SURROGATE — q03 / exact retained case

편집 원본: `screens/NUM-CASE-SURROGATE.svg` · 미리보기: `screens/NUM-CASE-SURROGATE.png` · owner: **N-RBF/r4**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-23: 선택 candidate/analysis의 원 입력·결과·단위·validity·NOT_RETAINED 상태. → 같은 method Plan과 case를 유지해 조회한다. 행 선택은 새 evaluation을 만들지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Return to method | navigate / Return to method | NUM-SURROGATE |
| Open same case run | navigate / Open same case run | RUN-NUM-SURROGATE |
| Save / reopen | navigate / Save / reopen | REOPEN-NUM-SURROGATE |
| Keep selection / return to method | navigate / Keep selection / return to method | NUM-SURROGATE |
| Explicit confirmation (new evaluation) | navigate / Explicit confirmation (new evaluation) | RUN-NUM-SURROGATE |
| Save exact case references | navigate / Save exact case references | REOPEN-NUM-SURROGATE |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Create Plan from supported evaluator or external exchange |
| edit | Typed variables/observations/method; source owner bounds retained |
| dirty | Plan source and starts explicitly refreshed/saved |
| running | Fixed mask/method/seed/budget/source; failures and penalties separate |
| fail | Select failed candidate, exact input/log; missing NOT_EVALUATED |
| cancel | Stop next submissions, retain late result, no hidden resume |
| complete | Method-specific evidence → explicit confirmation/adoption |
| reopen | History browse without exact engine resume unless checkpoint supported |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-23와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## NUM-CASE-UQ — s041 / exact retained case

편집 원본: `screens/NUM-CASE-UQ.svg` · 미리보기: `screens/NUM-CASE-UQ.png` · owner: **N-UQ/r2**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-22: 선택 candidate/analysis의 원 입력·결과·단위·validity·NOT_RETAINED 상태. → 같은 method Plan과 case를 유지해 조회한다. 행 선택은 새 evaluation을 만들지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Return to method | navigate / Return to method | NUM-UQ |
| Open same case run | navigate / Open same case run | RUN-NUM-UQ |
| Save / reopen | navigate / Save / reopen | REOPEN-NUM-UQ |
| Keep selection / return to method | navigate / Keep selection / return to method | NUM-UQ |
| Explicit confirmation (new evaluation) | navigate / Explicit confirmation (new evaluation) | RUN-NUM-UQ |
| Save exact case references | navigate / Save exact case references | REOPEN-NUM-UQ |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Create Plan from supported evaluator or external exchange |
| edit | Typed variables/observations/method; source owner bounds retained |
| dirty | Plan source and starts explicitly refreshed/saved |
| running | Fixed mask/method/seed/budget/source; failures and penalties separate |
| fail | Select failed candidate, exact input/log; missing NOT_EVALUATED |
| cancel | Stop next submissions, retain late result, no hidden resume |
| complete | Method-specific evidence → explicit confirmation/adoption |
| reopen | History browse without exact engine resume unless checkpoint supported |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-22와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## NUM-DOE — DOE / experiment design

편집 원본: `screens/NUM-DOE.svg` · 미리보기: `screens/NUM-DOE.png` · owner: **N-DOE/r3**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-10: 등록 변수의 model bounds/종속성, 이번 Plan의 free·search bounds. → Plan 범위를 따로 정한다. 실제 효과 검사는 명시한 perturbation과 관측 범위를 기록한다.
- FN-20: 변수 ID·unit/type·model bounds와 Plan 탐색범위, response definition. → free/fixed·linear/log와 LHS count/seed/budget를 설정하고 실제 후보를 생성한다.
- FN-20: candidate table·선택 점 scatter·실패 후보·원 evaluation refs. → 행/점 선택을 연결하고 후보를 실행한다. 실패/invalid 응답은 누락과 사유를 보존한다.
- FN-20: 선택 후보의 원 input/response·plot와 저장 상태. → 중간/실패 후보를 보존하고 ‘원 모델 열기/후보 채택’은 명시 동작으로 수행한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open Fit A | navigate / Open Fit A | NUM-OPTIMIZE |
| Save Plan | navigate / Save Plan | REOPEN-NUM-DOE |
| Evaluation editor | navigate / Evaluation editor | EVAL-STAGES |
| Run / analyze | navigate / Run / analyze | RUN-NUM-DOE |
| Results | navigate / Results | NUM-CASE-DOE |
| Inspect selected | navigate / Inspect selected | NUM-CASE-DOE |
| DOE | navigate / DOE | NUM-DOE |
| Optimization / inverse | navigate / Optimization / inverse | NUM-OPTIMIZE |
| Sensitivity | navigate / Sensitivity | NUM-SENSITIVITY |
| UQ | navigate / UQ | NUM-UQ |
| Surrogate | navigate / Surrogate | NUM-SURROGATE |
| Multiobjective | navigate / Multiobjective | NUM-MOO |
| External batch | navigate / External batch | NUM-BATCH |
| Inspect selected result | navigate / Inspect selected result | NUM-CASE-DOE |
| Confirm with evaluator… | navigate / Confirm with evaluator… | RUN-NUM-DOE |
| Save Plan / reopen without rerun | navigate / Save Plan / reopen without rerun | REOPEN-NUM-DOE |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Create Plan from supported evaluator or external exchange |
| edit | Typed variables/observations/method; source owner bounds retained |
| dirty | Plan source and starts explicitly refreshed/saved |
| running | Fixed mask/method/seed/budget/source; failures and penalties separate |
| fail | Select failed candidate, exact input/log; missing NOT_EVALUATED |
| cancel | Stop next submissions, retain late result, no hidden resume |
| complete | Method-specific evidence → explicit confirmation/adoption |
| reopen | History browse without exact engine resume unless checkpoint supported |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-10, FN-20와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## NUM-MOO — Multiobjective / explicit Pareto selection

편집 원본: `screens/NUM-MOO.svg` · 미리보기: `screens/NUM-MOO.png` · owner: **N-MOO/r4**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-24: 목표별 minimize/maximize·단위·limit와 axes, infeasible 후보. → 기존 epsilon-constraint method의 primary objective와 threshold grid·총 budget를 설정한다.
- FN-24: Pareto scatter↔candidate table↔선택 설계의 실제 objectives/constraints. → 같은 점의 원 결과를 열고 범위·지배/비지배·solver validity를 검토한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open Fit A | navigate / Open Fit A | NUM-OPTIMIZE |
| Save Plan | navigate / Save Plan | REOPEN-NUM-MOO |
| Evaluation editor | navigate / Evaluation editor | EVAL-STAGES |
| Run / analyze | navigate / Run / analyze | RUN-NUM-MOO |
| Results | navigate / Results | NUM-CASE-MOO |
| Adopt selected… | navigate / Adopt selected… | NUM-ADOPT-CONFLICT |
| DOE | navigate / DOE | NUM-DOE |
| Optimization / inverse | navigate / Optimization / inverse | NUM-OPTIMIZE |
| Sensitivity | navigate / Sensitivity | NUM-SENSITIVITY |
| UQ | navigate / UQ | NUM-UQ |
| Surrogate | navigate / Surrogate | NUM-SURROGATE |
| Multiobjective | navigate / Multiobjective | NUM-MOO |
| External batch | navigate / External batch | NUM-BATCH |
| Inspect selected result | navigate / Inspect selected result | NUM-CASE-MOO |
| Confirm with evaluator… | navigate / Confirm with evaluator… | RUN-NUM-MOO |
| Save Plan / reopen without rerun | navigate / Save Plan / reopen without rerun | REOPEN-NUM-MOO |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Create Plan from supported evaluator or external exchange |
| edit | Typed variables/observations/method; source owner bounds retained |
| dirty | Plan source and starts explicitly refreshed/saved |
| running | Fixed mask/method/seed/budget/source; failures and penalties separate |
| fail | Select failed candidate, exact input/log; missing NOT_EVALUATED |
| cancel | Stop next submissions, retain late result, no hidden resume |
| complete | Method-specific evidence → explicit confirmation/adoption |
| reopen | History browse without exact engine resume unless checkpoint supported |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-24와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## NUM-NEXT-TEST — Fixture-only compliance / new proposal

편집 원본: `screens/NUM-NEXT-TEST.svg` · 미리보기: `screens/NUM-NEXT-TEST.png` · owner: **New Numerical Plan N-next / derived from Study S-02r3**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-29: 이전/현재 입력·draft·saved revision·정확한 결과와 해당 복구 상태. 같은 기능의 결과를 다른 예시로 대체하지 않는다. → 명시 Apply/Save/Cancel/재열기로 전이하며 frozen 결과는 원 입력에 남긴다. unsupported/invalid required 입력의 Run은 계속 차단한다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Question | text / 해당 없음 | Does fixture compliance explain residual? | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Experiment | enum / 해당 없음 | Fixture only / rigid specimen substitute | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Variable | quantity / 해당 없음 | applied force [N] / known load steps | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Response | quantity / 해당 없음 | relative gauge displacement [mm] | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Method | enum / 해당 없음 | explicit load levels / file batch | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open source Study | navigate / Open source Study | STUDY-DECISION |
| Save proposal | navigate / Save proposal | REOPEN-NEXT-TEST |
| Native fixture input | navigate / Native fixture input | PRE-DESIGN |
| Run blocked | navigate / Run blocked | NUM-NEXT-TEST |
| Save next-test draft / reopen | navigate / Save next-test draft / reopen | REOPEN-NEXT-TEST |
| Open measurement metadata | navigate / Open measurement metadata | DATA-CALIBRATION |
| Return to explicit Study decision | navigate / Return to explicit Study decision | STUDY-DECISION |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Create Plan from supported evaluator or external exchange |
| edit | Typed variables/observations/method; source owner bounds retained |
| dirty | Plan source and starts explicitly refreshed/saved |
| running | Fixed mask/method/seed/budget/source; failures and penalties separate |
| fail | Select failed candidate, exact input/log; missing NOT_EVALUATED |
| cancel | Stop next submissions, retain late result, no hidden resume |
| complete | Method-specific evidence → explicit confirmation/adoption |
| reopen | History browse without exact engine resume unless checkpoint supported |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-29와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## NUM-OPTIMIZE — Fit A / inverse or optimization

편집 원본: `screens/NUM-OPTIMIZE.svg` · 미리보기: `screens/NUM-OPTIMIZE.png` · owner: **N-05/r8**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-05: 식별 가능한 계수와 고정할 지그 강성/마찰, 새 시편의 train/holdout 구분. → 수치 inverse Plan을 만들어 실제 준비된 관측으로 평가한다. 재료와 지그 변수의 상관을 확인한다.
- FN-21: 목적/제약 표의 quantity·unit·location/time/reduction·방향·limit. → 최소 변위/최대 강성/측정 오차 등 목적을 지정한다. 응력 peak와 average를 같은 이름으로 섞지 않는다.
- FN-21: method·bounds·budget/seed·중지 조건·parallel execution 설정. → 지원 DE/least-squares 등 실제 method를 선택하고 기준 평가를 확인한다.
- FN-23: 대리 예측을 사용한 추천 후보와 실해석 미확인. → ‘실제 평가로 확인’은 새 evaluation으로 제출하고 두 결과를 보존한다.
- FN-30: 제안된 editable Plan의 평가기/변수/응답/범위/예산과 source turn. → 같은 Plan owner에서 수정 후 명시 실행한다. 허용한 Plan budget 안의 매 후보에 재승인을 요구하지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open Fit A | navigate / Open Fit A | NUM-OPTIMIZE |
| Save Plan | navigate / Save Plan | REOPEN-NUMERICAL |
| Evaluation editor | navigate / Evaluation editor | EVAL-STAGES |
| Run / analyze | navigate / Run / analyze | RUN-ACTIVE |
| Results | navigate / Results | MAT-FIT-PARTIAL |
| Adopt selected… | navigate / Adopt selected… | MAT-ADOPT-CONFLICT |
| DOE | navigate / DOE | NUM-DOE |
| Optimization / inverse | navigate / Optimization / inverse | NUM-OPTIMIZE |
| Sensitivity | navigate / Sensitivity | NUM-SENSITIVITY |
| UQ | navigate / UQ | NUM-UQ |
| Surrogate | navigate / Surrogate | NUM-SURROGATE |
| Multiobjective | navigate / Multiobjective | NUM-MOO |
| External batch | navigate / External batch | NUM-BATCH |
| Inspect selected result | navigate / Inspect selected result | MAT-FIT-PARTIAL |
| Confirm with evaluator… | navigate / Confirm with evaluator… | RUN-ACTIVE |
| Save Plan / reopen without rerun | navigate / Save Plan / reopen without rerun | REOPEN-NUMERICAL |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Create Plan from supported evaluator or external exchange |
| edit | Typed variables/observations/method; source owner bounds retained |
| dirty | Plan source and starts explicitly refreshed/saved |
| running | Fixed mask/method/seed/budget/source; failures and penalties separate |
| fail | Select failed candidate, exact input/log; missing NOT_EVALUATED |
| cancel | Stop next submissions, retain late result, no hidden resume |
| complete | Method-specific evidence → explicit confirmation/adoption |
| reopen | History browse without exact engine resume unless checkpoint supported |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-05, FN-21, FN-23, FN-30와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## NUM-SENSITIVITY — Sensitivity / definition of influence

편집 원본: `screens/NUM-SENSITIVITY.svg` · 미리보기: `screens/NUM-SENSITIVITY.png` · owner: **N-Sobol/r2**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-20: 회귀 영향도의 sample/제외·rank·condition·분석 범위 또는 Sobol의 S1/ST/CI. → LHS 회귀와 matched Sobol plan을 별도 분석으로 고른다. Sobol 샘플 순서/입력 identity를 검사한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open Fit A | navigate / Open Fit A | NUM-OPTIMIZE |
| Save Plan | navigate / Save Plan | REOPEN-NUM-SENSITIVITY |
| Evaluation editor | navigate / Evaluation editor | EVAL-STAGES |
| Run / analyze | navigate / Run / analyze | RUN-NUM-SENSITIVITY |
| Results | navigate / Results | NUM-CASE-SENSITIVITY |
| Inspect selected | navigate / Inspect selected | NUM-CASE-SENSITIVITY |
| DOE | navigate / DOE | NUM-DOE |
| Optimization / inverse | navigate / Optimization / inverse | NUM-OPTIMIZE |
| Sensitivity | navigate / Sensitivity | NUM-SENSITIVITY |
| UQ | navigate / UQ | NUM-UQ |
| Surrogate | navigate / Surrogate | NUM-SURROGATE |
| Multiobjective | navigate / Multiobjective | NUM-MOO |
| External batch | navigate / External batch | NUM-BATCH |
| Inspect selected result | navigate / Inspect selected result | NUM-CASE-SENSITIVITY |
| Confirm with evaluator… | navigate / Confirm with evaluator… | RUN-NUM-SENSITIVITY |
| Save Plan / reopen without rerun | navigate / Save Plan / reopen without rerun | REOPEN-NUM-SENSITIVITY |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Create Plan from supported evaluator or external exchange |
| edit | Typed variables/observations/method; source owner bounds retained |
| dirty | Plan source and starts explicitly refreshed/saved |
| running | Fixed mask/method/seed/budget/source; failures and penalties separate |
| fail | Select failed candidate, exact input/log; missing NOT_EVALUATED |
| cancel | Stop next submissions, retain late result, no hidden resume |
| complete | Method-specific evidence → explicit confirmation/adoption |
| reopen | History browse without exact engine resume unless checkpoint supported |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-20와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## NUM-SURROGATE — Surrogate / holdout validation

편집 원본: `screens/NUM-SURROGATE.svg` · 미리보기: `screens/NUM-SURROGATE.png` · owner: **N-RBF/r4**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-23: train/holdout run refs·rows·input ranges·model settings. → 지원 SciPy RBF 옵션을 고르고 holdout을 학습에 쓰지 않는다는 범위를 확인한다.
- FN-23: predicted-vs-observed·residual·MAE/RMSE/max error와 out-of-range 표식. → 오차 점→원 candidate/result로 이동해 누락/실패 또는 boundary issue를 검토한다.
- FN-23: 새 parameter point·support check와 PREDICTED 결과. → 예측을 요청한다. 외삽은 explicit out_of_range이며 solver result badge를 쓰지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open Fit A | navigate / Open Fit A | NUM-OPTIMIZE |
| Save Plan | navigate / Save Plan | REOPEN-NUM-SURROGATE |
| Evaluation editor | navigate / Evaluation editor | EVAL-STAGES |
| Run / analyze | navigate / Run / analyze | RUN-NUM-SURROGATE |
| Results | navigate / Results | NUM-CASE-SURROGATE |
| Inspect selected | navigate / Inspect selected | NUM-CASE-SURROGATE |
| DOE | navigate / DOE | NUM-DOE |
| Optimization / inverse | navigate / Optimization / inverse | NUM-OPTIMIZE |
| Sensitivity | navigate / Sensitivity | NUM-SENSITIVITY |
| UQ | navigate / UQ | NUM-UQ |
| Surrogate | navigate / Surrogate | NUM-SURROGATE |
| Multiobjective | navigate / Multiobjective | NUM-MOO |
| External batch | navigate / External batch | NUM-BATCH |
| Inspect selected result | navigate / Inspect selected result | NUM-CASE-SURROGATE |
| Confirm with evaluator… | navigate / Confirm with evaluator… | RUN-NUM-SURROGATE |
| Save Plan / reopen without rerun | navigate / Save Plan / reopen without rerun | REOPEN-NUM-SURROGATE |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Create Plan from supported evaluator or external exchange |
| edit | Typed variables/observations/method; source owner bounds retained |
| dirty | Plan source and starts explicitly refreshed/saved |
| running | Fixed mask/method/seed/budget/source; failures and penalties separate |
| fail | Select failed candidate, exact input/log; missing NOT_EVALUATED |
| cancel | Stop next submissions, retain late result, no hidden resume |
| complete | Method-specific evidence → explicit confirmation/adoption |
| reopen | History browse without exact engine resume unless checkpoint supported |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-23와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## NUM-UQ — Uncertainty / success-conditioned distribution

편집 원본: `screens/NUM-UQ.svg` · 미리보기: `screens/NUM-UQ.png` · owner: **N-UQ/r2**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-22: 분포 표: 종류·단위·mean/std/bounds·source·독립/상관 선언. → 현재 지원 uniform/normal/truncnorm/lognormal과 independence를 선택한다. 실측/문헌/가정/합성을 구분한다.
- FN-22: 샘플 budget와 domain bounds 밖 예상/검사, response threshold. → 명시 샘플 생성·실행한다. normal tail을 몰래 잘라 truncate하지 않는다.
- FN-22: valid/failed counts, conditional histogram/CDF·quantiles·exceedance fraction. → bar/bin 선택으로 해당 실제 sample의 입력/실패/결과를 연다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open Fit A | navigate / Open Fit A | NUM-OPTIMIZE |
| Save Plan | navigate / Save Plan | REOPEN-NUM-UQ |
| Evaluation editor | navigate / Evaluation editor | EVAL-STAGES |
| Run / analyze | navigate / Run / analyze | RUN-NUM-UQ |
| Results | navigate / Results | NUM-CASE-UQ |
| Inspect selected | navigate / Inspect selected | NUM-CASE-UQ |
| DOE | navigate / DOE | NUM-DOE |
| Optimization / inverse | navigate / Optimization / inverse | NUM-OPTIMIZE |
| Sensitivity | navigate / Sensitivity | NUM-SENSITIVITY |
| UQ | navigate / UQ | NUM-UQ |
| Surrogate | navigate / Surrogate | NUM-SURROGATE |
| Multiobjective | navigate / Multiobjective | NUM-MOO |
| External batch | navigate / External batch | NUM-BATCH |
| Inspect selected result | navigate / Inspect selected result | NUM-CASE-UQ |
| Confirm with evaluator… | navigate / Confirm with evaluator… | RUN-NUM-UQ |
| Save Plan / reopen without rerun | navigate / Save Plan / reopen without rerun | REOPEN-NUM-UQ |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Create Plan from supported evaluator or external exchange |
| edit | Typed variables/observations/method; source owner bounds retained |
| dirty | Plan source and starts explicitly refreshed/saved |
| running | Fixed mask/method/seed/budget/source; failures and penalties separate |
| fail | Select failed candidate, exact input/log; missing NOT_EVALUATED |
| cancel | Stop next submissions, retain late result, no hidden resume |
| complete | Method-specific evidence → explicit confirmation/adoption |
| reopen | History browse without exact engine resume unless checkpoint supported |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-22와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## PDE-EQUATION — PDE Q-04 / bounded nonlinear diffusion

편집 원본: `screens/PDE-EQUATION.svg` · 미리보기: `screens/PDE-EQUATION.png` · owner: **PDE Q-04 / same existing owner**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-18: Model Builder의 domain/field/space/equation/BC/IC/mesh/solver·큰 field view. → node 선택에 따라 equation editor·field table·region selector가 바뀐다. 전체 raw settings를 한 폼에 나열하지 않는다.
- FN-18: boundary tags·dimension·개수·unit/mesh revision, field polynomial order. → 경계·초기조건과 function space를 선택하고 유효 input을 고정한다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Diffusion coefficient alpha | number / 1 | 1.0 | 1 / 0 ≤ alpha ≤ 2 | 선택 owner / 대상 |
| Equation (template, read only) | capability_template / 해당 없음 | -div((1+alpha*u²) grad(u))=rhs | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Boundary scope / value | constant_expression / 1 | entire boundary / 0.0 | 0 / whole-boundary constant only | 선택 owner / 대상 |
| Mesh / degree | increasing_doubling_integer_list / 해당 없음 | 8,16,32 cells per axis / P1 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Reference u | bounded_expression / 1 | sin(pi*x[0])*sin(pi*x[1]) | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Newton atol / rtol | fixed_capability_value / 해당 없음 | 1e-10 / 1e-10 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Max Newton iter. | fixed_capability_value / 해당 없음 | 25 | 25 / 선택 capability·문서 규칙 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open model | navigate / Open model | PDE-EQUATION |
| Save PDE | navigate / Save PDE | REOPEN-PDE |
| Check expression | navigate / Check expression | PDE-INVALID |
| Evaluate blocked | navigate / Evaluate blocked | SETUP-CAPABILITY |
| Retained result | navigate / Retained result | PDE-RESULT |
| Evaluation definition | navigate / Evaluation definition | EVAL-STAGES |
| Validate without solving | navigate / Validate without solving | PDE-INVALID |
| Show synthetic result state | navigate / Show synthetic result state | PDE-RESULT |
| Review equation error state | navigate / Review equation error state | PDE-INVALID |
| Save bounded PDE draft | navigate / Save bounded PDE draft | REOPEN-PDE |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | New domain/equation without CAD |
| edit | Node-selected settings and spatial BC selection |
| dirty | Invalid equation draft saveable |
| running | Frozen model / adapter actual output / same Runner |
| fail | Expression, region or solver diagnostic opens corresponding node |
| cancel | Current evaluation cancel; keep source and last results |
| complete | Inspect reference/mesh errors then save |
| reopen | Restore equation/mesh/BC/retained results without runtime |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-18와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## PDE-INVALID — PDE Q-04 / invalid RHS draft

편집 원본: `screens/PDE-INVALID.svg` · 미리보기: `screens/PDE-INVALID.png` · owner: **PDE Q-04 / same existing owner**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-18: 선택 약형식의 미선언 변수·차원·backend syntax 오류 위치. → 식 검사에서 오류 token으로 이동해 수정한다. 식 검사와 solver 실행은 별도다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Diffusion coefficient alpha | number / 1 | 1.0 | 1 / 0 ≤ alpha ≤ 2 | 선택 owner / 대상 |
| Equation (template, read only) | capability_template / 해당 없음 | -div((1+alpha*u²) grad(u))=rhs | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Boundary scope / value | constant_expression / 1 | entire boundary / 0.0 | 0 / whole-boundary constant only | 선택 owner / 대상 |
| Mesh / degree | increasing_doubling_integer_list / 해당 없음 | 8,16,32 cells per axis / P1 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Reference u | bounded_expression / 1 | sin(pi*x[0])*sin(pi*x[1]) | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Newton atol / rtol | fixed_capability_value / 해당 없음 | 1e-10 / 1e-10 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Max Newton iter. | fixed_capability_value / 해당 없음 | 25 | 25 / 선택 capability·문서 규칙 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open model | navigate / Open model | PDE-EQUATION |
| Save PDE | navigate / Save PDE | REOPEN-PDE |
| Check expression | navigate / Check expression | PDE-INVALID |
| Evaluate blocked | navigate / Evaluate blocked | PDE-INVALID |
| Retained result | navigate / Retained result | PDE-RESULT |
| Evaluation definition | navigate / Evaluation definition | EVAL-STAGES |
| Validate without solving | navigate / Validate without solving | PDE-INVALID |
| Show synthetic result state | navigate / Show synthetic result state | PDE-RESULT |
| Correct symbol / boundary | navigate / Correct symbol / boundary | PDE-EQUATION |
| Save invalid PDE draft | navigate / Save invalid PDE draft | REOPEN-PDE |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | New domain/equation without CAD |
| edit | Node-selected settings and spatial BC selection |
| dirty | Invalid equation draft saveable |
| running | Frozen model / adapter actual output / same Runner |
| fail | Expression, region or solver diagnostic opens corresponding node |
| cancel | Current evaluation cancel; keep source and last results |
| complete | Inspect reference/mesh errors then save |
| reopen | Restore equation/mesh/BC/retained results without runtime |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-18와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## PDE-RESULT — PDE Q-04 / retained reference comparison

편집 원본: `screens/PDE-RESULT.svg` · 미리보기: `screens/PDE-RESULT.png` · owner: **PDE Q-04 / same existing owner**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-18: 해 field와 L2/H1 또는 정의한 response error·mesh levels·residual. → 해석해/다른 mesh/solver의 동일 정의와 비교하고 Post로 exact result를 연다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Diffusion coefficient alpha | number / 1 | 1.0 | 1 / 0 ≤ alpha ≤ 2 | 선택 owner / 대상 |
| Equation (template, read only) | capability_template / 해당 없음 | -div((1+alpha*u²) grad(u))=rhs | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Boundary scope / value | constant_expression / 1 | entire boundary / 0.0 | 0 / whole-boundary constant only | 선택 owner / 대상 |
| Mesh / degree | increasing_doubling_integer_list / 해당 없음 | 8,16,32 cells per axis / P1 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Reference u | bounded_expression / 1 | sin(pi*x[0])*sin(pi*x[1]) | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Newton atol / rtol | fixed_capability_value / 해당 없음 | 1e-10 / 1e-10 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Max Newton iter. | fixed_capability_value / 해당 없음 | 25 | 25 / 선택 capability·문서 규칙 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open model | navigate / Open model | PDE-EQUATION |
| Save PDE | navigate / Save PDE | REOPEN-PDE |
| Check expression | navigate / Check expression | PDE-INVALID |
| Evaluate blocked | navigate / Evaluate blocked | SETUP-CAPABILITY |
| Retained result | navigate / Retained result | PDE-RESULT |
| Evaluation definition | navigate / Evaluation definition | EVAL-STAGES |
| Validate without solving | navigate / Validate without solving | PDE-INVALID |
| Show synthetic result state | navigate / Show synthetic result state | PDE-RESULT |
| Open exact source equation | navigate / Open exact source equation | PDE-EQUATION |
| Save retained reference comparison | navigate / Save retained reference comparison | REOPEN-PDE |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | New domain/equation without CAD |
| edit | Node-selected settings and spatial BC selection |
| dirty | Invalid equation draft saveable |
| running | Frozen model / adapter actual output / same Runner |
| fail | Expression, region or solver diagnostic opens corresponding node |
| cancel | Current evaluation cancel; keep source and last results |
| complete | Inspect reference/mesh errors then save |
| reopen | Restore equation/mesh/BC/retained results without runtime |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-18와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## POST-COMPARE — Comparison A / B · exact recipe

편집 원본: `screens/POST-COMPARE.svg` · 미리보기: `screens/POST-COMPARE.png` · owner: **ParaView native Post document**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-05: 측정 게이지의 두 위치·방향·게이지 길이, 예측 응답과 time alignment. → 동일 관측량을 선택한다. actuator displacement와 specimen strain을 같은 응답으로 묶지 않는다.
- FN-28: A/B quantity/unit/measure/association/frame/mesh/time·비교 식 B−A. → 비교할 scalar/component와 동일 응답 정의를 고른다. 불일치는 해당 셀에 표시한다.
- FN-28: 원 A, A 위치의 B 보간값, B source cell·time, delta/percent 두 validity columns. → Apply로 mapping/recipe를 게시한다. A=0이면 delta는 가능할 수 있지만 percent는 undefined다.
- FN-28: 서로 다른 coordinate/time/unit 입력의 필요한 변환 chain. → 지원 converter만 explicit node로 적용한다. 미지원 tensor/시간보간/다른 element는 차이 계산만 차단하고 side-by-side/동일 게이지 비교는 유지한다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Color field | enum / 해당 없음 | s [mm] | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Actual time | sample / s | .040 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Display deformation | number / 해당 없음 | 1.0 × | 미지정; sample을 기본값으로 쓰지 않음 / >0 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open data… | navigate / Open data… | POST-OPEN |
| Save analysis | navigate / Save analysis | REOPEN-POST |
| Measure | navigate / Measure | POST-MEASURE |
| Compare… | navigate / Compare… | POST-COMPARE |
| Apply | navigate / Apply | POST-MEASURE |
| Reset | navigate / Reset | POST-OPEN |
| Repair sources | navigate / Repair sources | POST-REPAIR |
| Open exact input | navigate / Open exact input | POST-OPEN |
| Inspect zero-denominator sample | select / Delta remains valid, percentage undefined | POST-COMPARE |
| Preview / validate mapping | navigate / Preview / validate mapping | POST-MAP-PREVIEW |
| Apply valid recipe | navigate / Apply valid recipe | POST-COMPARE |
| Reset preview | navigate / Reset preview | POST-MEASURE |
| Save exact mask / recipe | navigate / Save exact mask / recipe | REOPEN-POST |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open supported registered file set / managed PVSM |
| edit | Pending native properties / Apply / Reset; direct view changes separate |
| dirty | Ctrl+S managed analysis, native Save Data remains export |
| running | Native Apply scope/command ID; current source kept |
| fail | Broken reader/branch or invalid correspondence; valid branches remain |
| cancel | Reset preview/pending or command cancel with actual support; no invented rollback |
| complete | Save measurements/recipe/mask/native state/results |
| reopen | Exact values/recipe; missing files repaired by same bytes or new branch |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-05, FN-28와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## POST-CONTACT — Contact result · Pair A → B

편집 원본: `screens/POST-CONTACT.svg` · 미리보기: `screens/POST-CONTACT.png` · owner: **ParaView native Post document**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-14: actual t=0.040 s·contact pressure/normal force/gap/penetration/slip·status, 양 surface 관계. → pressure cell 선택→같은 contact point/face의 time curve·원값을 읽는다. force sum과 pressure integral의 의미/위치를 확인한다.
- FN-16: contact sequence·force/acceleration/time·deformation·failure field. → 정확 frame과 event/peak 정의로 응답을 비교한다. acceleration filter는 별도 recipe로 표시한다.
- FN-17: opening/slip/damage·plastic strain·energy·failure location/time. → 계면과 벌크 반응을 따로 선택하고 결과 변화와 mesh regularization을 검토한다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Color field | enum / 해당 없음 | Pressure | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Actual time | sample / s | .040 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Display deformation | number / 해당 없음 | 1.0 × | 미지정; sample을 기본값으로 쓰지 않음 / >0 | 선택 owner / 대상 |
| Original ID / namespace | reference / 해당 없음 | surface face 184 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Quantity / association | enum / 해당 없음 | contact pressure / surface | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Value / actual time | retained_value / 해당 없음 | 1.42 MPa @ .040 s | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open data… | navigate / Open data… | POST-OPEN |
| Save analysis | navigate / Save analysis | REOPEN-POST |
| Measure | navigate / Measure | POST-MEASURE |
| Compare… | navigate / Compare… | POST-COMPARE |
| Apply | navigate / Apply | POST-MEASURE |
| Reset | navigate / Reset | POST-OPEN |
| Repair sources | navigate / Repair sources | POST-REPAIR |
| Open exact input | navigate / Open exact input | PRE-CONTACT |
| Save measurement | navigate / Save measurement | POST-MEASURE |
| Plot selected over time | navigate / Plot selected over time | POST-MEASURE |
| Compare exact source B | navigate / Compare exact source B | POST-COMPARE |
| Repair contact after split | open_exact_input / Open new geometry revision and unresolved face set | PRE-CONTACT-REBIND |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open supported registered file set / managed PVSM |
| edit | Pending native properties / Apply / Reset; direct view changes separate |
| dirty | Ctrl+S managed analysis, native Save Data remains export |
| running | Native Apply scope/command ID; current source kept |
| fail | Broken reader/branch or invalid correspondence; valid branches remain |
| cancel | Reset preview/pending or command cancel with actual support; no invented rollback |
| complete | Save measurements/recipe/mask/native state/results |
| reopen | Exact values/recipe; missing files repaired by same bytes or new branch |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-14, FN-16, FN-17와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## POST-MAP-PREVIEW — B → A mapping / valid region

편집 원본: `screens/POST-MAP-PREVIEW.svg` · 미리보기: `screens/POST-MAP-PREVIEW.png` · owner: **ParaView native Post document**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-28: B→A target points, source linear tetra cells, valid/outside/NaN counts. → 현재 지원 same_mesh 또는 linear_tetra_b_to_a를 명시하고 실제 preview를 검사한다. closest point는 대체 방법이 아니다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Color field | enum / 해당 없음 | s [mm] | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Actual time | sample / s | .040 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Display deformation | number / 해당 없음 | 1.0 × | 미지정; sample을 기본값으로 쓰지 않음 / >0 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open data… | navigate / Open data… | POST-OPEN |
| Save analysis | navigate / Save analysis | REOPEN-POST |
| Measure | navigate / Measure | POST-MEASURE |
| Compare… | navigate / Compare… | POST-COMPARE |
| Apply | navigate / Apply | POST-MEASURE |
| Reset | navigate / Reset | POST-OPEN |
| Repair sources | navigate / Repair sources | POST-REPAIR |
| Open exact input | navigate / Open exact input | POST-OPEN |
| Inspect zero-denominator sample | select / Delta remains valid, percentage undefined | POST-COMPARE |
| Preview / validate mapping | navigate / Preview / validate mapping | POST-MAP-PREVIEW |
| Apply valid recipe | navigate / Apply valid recipe | POST-COMPARE |
| Reset preview | navigate / Reset preview | POST-MEASURE |
| Save exact mask / recipe | navigate / Save exact mask / recipe | REOPEN-POST |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open supported registered file set / managed PVSM |
| edit | Pending native properties / Apply / Reset; direct view changes separate |
| dirty | Ctrl+S managed analysis, native Save Data remains export |
| running | Native Apply scope/command ID; current source kept |
| fail | Broken reader/branch or invalid correspondence; valid branches remain |
| cancel | Reset preview/pending or command cancel with actual support; no invented rollback |
| complete | Save measurements/recipe/mask/native state/results |
| reopen | Exact values/recipe; missing files repaired by same bytes or new branch |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-28와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## POST-MEASURE — Saved gauge · source / time / ID

편집 원본: `screens/POST-MEASURE.svg` · 미리보기: `screens/POST-MEASURE.png` · owner: **ParaView native Post document**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-15: 하중–변위·반력·소성/접촉/에너지와 mesh/step-dependent response. → 원 sample·선택 요소와 응답 curve를 비교하고 retained result를 저장한다.
- FN-27: 큰 Render view·native Slice/Clip/Warp/Contour의 pending 설정. → 3D widget과 numeric property로 편집→Apply/Reset한다. display/color/camera 변경은 native 즉시표시 의미를 따른다.
- FN-27: point/cell·ID namespace·coordinate/probe·actual time·units. → 3D/Find Data 선택을 원값 표와 연결하고 ‘측정 저장’을 누른다. solver ID가 없으면 VTK index라고 표시한다.
- FN-27: PlotOverLine/SelectionOverTime의 sample·gap·원ID/보간 표식. → 시간/경로 곡선을 저장하고 원 field·선택점으로 돌아간다.
- FN-34: 정확 input/result/recipe/field/time/selection의 partial values. → 큰 배열은 metadata·선택 범위·파일 artifact로 읽고 사람과 AI의 ID/원값을 대조한다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Color field | enum / 해당 없음 | Displacement magnitude | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Actual time | sample / s | .040 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Display deformation | number / 해당 없음 | 1.0 × | 미지정; sample을 기본값으로 쓰지 않음 / >0 | 선택 owner / 대상 |
| Original ID / namespace | reference / 해당 없음 | node145 / original_node_id | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Quantity / association | enum / 해당 없음 | displacement magnitude / point | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Value / actual time | retained_value / 해당 없음 | .224 mm @ .040 s | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open data… | navigate / Open data… | POST-OPEN |
| Save analysis | navigate / Save analysis | REOPEN-POST |
| Measure | navigate / Measure | POST-MEASURE |
| Compare… | navigate / Compare… | POST-COMPARE |
| Apply | navigate / Apply | POST-MEASURE |
| Reset | navigate / Reset | POST-OPEN |
| Repair sources | navigate / Repair sources | POST-REPAIR |
| Open exact input | navigate / Open exact input | POST-OPEN |
| Save measurement | navigate / Save measurement | POST-MEASURE |
| Plot selected over time | navigate / Plot selected over time | POST-MEASURE |
| Compare exact source B | navigate / Compare exact source B | POST-COMPARE |
| Keep measurement + Save analysis | navigate / Keep measurement + Save analysis | REOPEN-POST |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open supported registered file set / managed PVSM |
| edit | Pending native properties / Apply / Reset; direct view changes separate |
| dirty | Ctrl+S managed analysis, native Save Data remains export |
| running | Native Apply scope/command ID; current source kept |
| fail | Broken reader/branch or invalid correspondence; valid branches remain |
| cancel | Reset preview/pending or command cancel with actual support; no invented rollback |
| complete | Save measurements/recipe/mask/native state/results |
| reopen | Exact values/recipe; missing files repaired by same bytes or new branch |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-15, FN-27, FN-34와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## POST-OPEN — External time series · no CAD required

편집 원본: `screens/POST-OPEN.svg` · 미리보기: `screens/POST-OPEN.png` · owner: **ParaView native Post document**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-27: reader 선택·의존파일 완전성, Pipeline/Properties·Apply, field/association/time 정보. → 파일을 선택·등록하고 reader 옵션을 Apply한다. PVSM은 분석 상태 열기로 처리한다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Color field | enum / 해당 없음 | Displacement magnitude | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Actual time | sample / s | .040 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Display deformation | number / 해당 없음 | 1.0 × | 미지정; sample을 기본값으로 쓰지 않음 / >0 | 선택 owner / 대상 |
| Original ID / namespace | reference / 해당 없음 | node145 / original_node_id | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Quantity / association | enum / 해당 없음 | displacement magnitude / point | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Value / actual time | retained_value / 해당 없음 | .224 mm @ .040 s | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open data… | navigate / Open data… | POST-OPEN |
| Save analysis | navigate / Save analysis | REOPEN-POST |
| Measure | navigate / Measure | POST-MEASURE |
| Compare… | navigate / Compare… | POST-COMPARE |
| Apply | navigate / Apply | POST-MEASURE |
| Reset | navigate / Reset | POST-OPEN |
| Repair sources | navigate / Repair sources | POST-REPAIR |
| Open exact input | navigate / Open exact input | POST-OPEN |
| Save measurement | navigate / Save measurement | POST-MEASURE |
| Plot selected over time | navigate / Plot selected over time | POST-MEASURE |
| Compare exact source B | navigate / Compare exact source B | POST-COMPARE |
| Reader Properties → Apply | navigate / Reader Properties → Apply | POST-MEASURE |
| Inspect missing units | navigate / Inspect missing units | POST-COMPARE |
| Load managed analysis | navigate / Load managed analysis | REOPEN-POST |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open supported registered file set / managed PVSM |
| edit | Pending native properties / Apply / Reset; direct view changes separate |
| dirty | Ctrl+S managed analysis, native Save Data remains export |
| running | Native Apply scope/command ID; current source kept |
| fail | Broken reader/branch or invalid correspondence; valid branches remain |
| cancel | Reset preview/pending or command cancel with actual support; no invented rollback |
| complete | Save measurements/recipe/mask/native state/results |
| reopen | Exact values/recipe; missing files repaired by same bytes or new branch |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-27와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## POST-REPAIR — Locate moved or changed dependencies

편집 원본: `screens/POST-REPAIR.svg` · 미리보기: `screens/POST-REPAIR.png` · owner: **ParaView native Post document**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-27: 분석 저장과 Save Data/State/Image/Animation export의 대상 구분. → 관리 Ctrl+S로 analysis/save refs를 보존하고 새 ParaView session에서 연다.
- FN-28: A/B refs·recipe/version·mask·보존 결과·source 변경 상태. → save/reopen 후 같은 값과 mask를 확인한다. changed bytes는 새 source branch로 연다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Color field | enum / 해당 없음 | Displacement magnitude | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Actual time | sample / s | .040 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Display deformation | number / 해당 없음 | 1.0 × | 미지정; sample을 기본값으로 쓰지 않음 / >0 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open data… | navigate / Open data… | POST-OPEN |
| Save analysis | navigate / Save analysis | REOPEN-POST |
| Measure | navigate / Measure | POST-MEASURE |
| Compare… | navigate / Compare… | POST-COMPARE |
| Apply | navigate / Apply | POST-MEASURE |
| Reset | navigate / Reset | POST-OPEN |
| Repair sources | navigate / Repair sources | POST-REPAIR |
| Open exact input | navigate / Open exact input | POST-OPEN |
| Find / register replacement | navigate / Find / register replacement | POST-REPAIR |
| Repair identical files | navigate / Repair identical files | POST-MEASURE |
| Create branch for changed B | navigate / Create branch for changed B | POST-COMPARE |
| Cancel repair | navigate / Cancel repair | POST-OPEN |
| Save partial recovery | navigate / Save partial recovery | REOPEN-POST |
| Inspect original retained values | navigate / Inspect original retained values | POST-COMPARE |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open supported registered file set / managed PVSM |
| edit | Pending native properties / Apply / Reset; direct view changes separate |
| dirty | Ctrl+S managed analysis, native Save Data remains export |
| running | Native Apply scope/command ID; current source kept |
| fail | Broken reader/branch or invalid correspondence; valid branches remain |
| cancel | Reset preview/pending or command cancel with actual support; no invented rollback |
| complete | Save measurements/recipe/mask/native state/results |
| reopen | Exact values/recipe; missing files repaired by same bytes or new branch |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-27, FN-28와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## PRE-CONTACT — Contact pair · Pad / Base

편집 원본: `screens/PRE-CONTACT.svg` · 미리보기: `screens/PRE-CONTACT.png` · owner: **FreeCAD native document / Analysis 1**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-14: A pad-bottom 4 faces(320 mm²), B base-top 2 faces(336 mm²), normal arrows·closest gap. → face filter/Ctrl 또는 목록 Add/Remove로 두 set을 지정한다. 목록 행 선택↔3D 강조, A/B 교체는 별도 명령이다.
- FN-14: normal law·friction law·μ=0.15·initial clearance=0.20 mm, orientation와 detection 영역. → law를 고르면 필수 접선/normal/penalty 옵션만 펼친다. gap 값은 typed 단위와 실제 형상 진단을 나란히 표시한다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Set A / geometry revision | reference / 해당 없음 | Pad underside / r12 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Set B / geometry revision | reference / 해당 없음 | Base top / r12 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Law | enum / 해당 없음 | Coulomb | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Friction μ | number / 1 | .15 | 미지정; sample을 기본값으로 쓰지 않음 / finite >=0 | 선택 owner / 대상 |
| Initial gap | number / mm | .20 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Normal policy | enum / 해당 없음 | A → B | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open native… | navigate / Open native… | PRE-DESIGN |
| Save project | navigate / Save project | REOPEN-CONTACT |
| Design | navigate / Design | PRE-DESIGN |
| Assembly | navigate / Assembly | PRE-MOTION |
| FEM | navigate / FEM | PRE-FEM |
| Preflight | navigate / Preflight | PRE-CONTACT-UNSUPPORTED |
| Run blocked | navigate / Run blocked | PRE-CONTACT-UNSUPPORTED |
| Results | navigate / Results | POST-CONTACT |
| Properties / selected object | navigate / Properties / selected object | PRE-FEM |
| Change impact / references | navigate / Change impact / references | PRE-CONTACT-REBIND |
| Register research variable | navigate / Register research variable | NUM-DOE |
| Flip / preview | navigate / Flip / preview | PRE-CONTACT-REBIND |
| Check capability | navigate / Check capability | PRE-CONTACT-UNSUPPORTED |
| Add selected faces | navigate / Add selected faces | PRE-CONTACT |
| Remove from set | navigate / Remove from set | PRE-CONTACT |
| Preview supported path | navigate / Preview supported path | PRE-CONTACT-READY |
| Geometry split scenario | navigate / Geometry split scenario | PRE-CONTACT-REBIND |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Native New/Open model; no forced fixture |
| edit | Native Task/selection/Undo; BUSY_EDIT protects pending work |
| dirty | Managed save first restores design pose, preserves invalid draft |
| running | Native command ID differs from calculation job ID; generation guarded apply |
| fail | Failed feature/mesh/face reference/restore location opens directly |
| cancel | Cancel Task/preview/rebind separately from command/job; old mesh/results retained |
| complete | Preflight → frozen input → Runner → exact Post result |
| reopen | Editable FCStd/native dependencies and design pose; no solver rerun |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-14와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## PRE-CONTACT-CANCELLED — Contact on geometry r13 / rebind cancelled

편집 원본: `screens/PRE-CONTACT-CANCELLED.svg` · 미리보기: `screens/PRE-CONTACT-CANCELLED.png` · owner: **FreeCAD r13 / contact owner**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-14: 이전/현재 입력·draft·saved revision·정확한 결과와 해당 복구 상태. 같은 기능의 결과를 다른 예시로 대체하지 않는다. → 명시 Apply/Save/Cancel/재열기로 전이하며 frozen 결과는 원 입력에 남긴다. unsupported/invalid required 입력의 Run은 계속 차단한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Save invalid draft | navigate / Save invalid draft | REOPEN-CONTACT-CANCELLED |
| Review rebind again | navigate / Review rebind again | PRE-CONTACT-REBIND |
| Open old r12 result | navigate / Open old r12 result | POST-CONTACT |
| Run blocked (diagnosis) | navigate / Run blocked (diagnosis) | PRE-CONTACT-CANCELLED |
| Review only unresolved references | navigate / Review only unresolved references | PRE-CONTACT-REBIND |
| Inspect old contact result / input | navigate / Inspect old contact result / input | POST-CONTACT |
| Keep state / save and reopen | navigate / Keep state / save and reopen | REOPEN-CONTACT-CANCELLED |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Native New/Open model; no forced fixture |
| edit | Native Task/selection/Undo; BUSY_EDIT protects pending work |
| dirty | Managed save first restores design pose, preserves invalid draft |
| running | Native command ID differs from calculation job ID; generation guarded apply |
| fail | Failed feature/mesh/face reference/restore location opens directly |
| cancel | Cancel Task/preview/rebind separately from command/job; old mesh/results retained |
| complete | Preflight → frozen input → Runner → exact Post result |
| reopen | Editable FCStd/native dependencies and design pose; no solver rerun |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-14와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## PRE-CONTACT-READY — PROPOSED admitted contact / frozen input

편집 원본: `screens/PRE-CONTACT-READY.svg` · 미리보기: `screens/PRE-CONTACT-READY.png` · owner: **FreeCAD native document / Analysis 1**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-14: 현재 미지원 입력은 blocked. 별도 미래 지원 상태는 PROPOSED / SIMULATED로 표시. → 미지원 Run으로 성공 상태를 만들지 않는다. 별도 미래 branch를 명시 선택해 지원이 구현된 뒤의 조작만 검토한다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Set A / geometry revision | reference / 해당 없음 | Pad underside / r12 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Set B / geometry revision | reference / 해당 없음 | Base top / r12 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Law | enum / 해당 없음 | Coulomb | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Friction μ | number / 1 | .15 | 미지정; sample을 기본값으로 쓰지 않음 / finite >=0 | 선택 owner / 대상 |
| Initial gap | number / mm | .20 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Normal policy | enum / 해당 없음 | A → B | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open native… | navigate / Open native… | PRE-DESIGN |
| Save project | navigate / Save project | REOPEN-CONTACT |
| Design | navigate / Design | PRE-DESIGN |
| Assembly | navigate / Assembly | PRE-MOTION |
| FEM | navigate / FEM | PRE-FEM |
| Preflight | navigate / Preflight | PRE-CONTACT-UNSUPPORTED |
| Run… | navigate / Run… | RUN-CONTACT |
| Results | navigate / Results | POST-CONTACT |
| Properties / selected object | navigate / Properties / selected object | PRE-FEM |
| Change impact / references | navigate / Change impact / references | PRE-CONTACT-REBIND |
| Register research variable | navigate / Register research variable | NUM-DOE |
| Flip / preview | navigate / Flip / preview | PRE-CONTACT-REBIND |
| Check capability | navigate / Check capability | PRE-CONTACT-UNSUPPORTED |
| Freeze valid contact input (simulated) | navigate / Freeze valid contact input (simulated) | RUN-CONTACT |
| Return to current blocked capability | navigate / Return to current blocked capability | PRE-CONTACT-UNSUPPORTED |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Native New/Open model; no forced fixture |
| edit | Native Task/selection/Undo; BUSY_EDIT protects pending work |
| dirty | Managed save first restores design pose, preserves invalid draft |
| running | Native command ID differs from calculation job ID; generation guarded apply |
| fail | Failed feature/mesh/face reference/restore location opens directly |
| cancel | Cancel Task/preview/rebind separately from command/job; old mesh/results retained |
| complete | Preflight → frozen input → Runner → exact Post result |
| reopen | Editable FCStd/native dependencies and design pose; no solver rerun |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-14와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## PRE-CONTACT-REBIND — Contact · changed geometry r13

편집 원본: `screens/PRE-CONTACT-REBIND.svg` · 미리보기: `screens/PRE-CONTACT-REBIND.png` · owner: **FreeCAD native document / Analysis 1**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-14: geometry split 후 old A4→new A7 candidate, 면적·centroid·normal 비교, 1 face normal flip. → old set translucent overlay에서 후보를 검토하고 new faces를 직접 골라 preview한다. Rebind Apply는 새 contact revision; Cancel은 원 참조를 unresolved로 보존한다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Set A / geometry revision | reference / 해당 없음 | Pad underside / r12 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Set B / geometry revision | reference / 해당 없음 | Base top / r12 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Law | enum / 해당 없음 | Coulomb | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Friction μ | number / 1 | .15 | 미지정; sample을 기본값으로 쓰지 않음 / finite >=0 | 선택 owner / 대상 |
| Initial gap | number / mm | .20 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Normal policy | enum / 해당 없음 | A → B | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open native… | navigate / Open native… | PRE-DESIGN |
| Design | navigate / Design | PRE-DESIGN |
| Assembly | navigate / Assembly | PRE-MOTION |
| FEM | navigate / FEM | PRE-FEM |
| Preflight | navigate / Preflight | PRE-CONTACT-UNSUPPORTED |
| Run blocked | navigate / Run blocked | PRE-CONTACT-UNSUPPORTED |
| Results | navigate / Results | POST-CONTACT |
| Properties / selected object | navigate / Properties / selected object | PRE-FEM |
| Change impact / references | navigate / Change impact / references | PRE-CONTACT-REBIND |
| Register research variable | navigate / Register research variable | NUM-DOE |
| Flip / preview | navigate / Flip / preview | PRE-CONTACT-REBIND |
| Check capability | navigate / Check capability | PRE-CONTACT-UNSUPPORTED |
| Apply selected rebind | navigate / Apply selected rebind | PRE-CONTACT-REBOUND |
| Cancel rebind | navigate / Cancel rebind | PRE-CONTACT-CANCELLED |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Native New/Open model; no forced fixture |
| edit | Native Task/selection/Undo; BUSY_EDIT protects pending work |
| dirty | Managed save first restores design pose, preserves invalid draft |
| running | Native command ID differs from calculation job ID; generation guarded apply |
| fail | Failed feature/mesh/face reference/restore location opens directly |
| cancel | Cancel Task/preview/rebind separately from command/job; old mesh/results retained |
| complete | Preflight → frozen input → Runner → exact Post result |
| reopen | Editable FCStd/native dependencies and design pose; no solver rerun |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-14와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## PRE-CONTACT-REBOUND — Contact on geometry r13 / rebind applied to draft

편집 원본: `screens/PRE-CONTACT-REBOUND.svg` · 미리보기: `screens/PRE-CONTACT-REBOUND.png` · owner: **FreeCAD r13 / contact owner**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-14: 이전/현재 입력·draft·saved revision·정확한 결과와 해당 복구 상태. 같은 기능의 결과를 다른 예시로 대체하지 않는다. → 명시 Apply/Save/Cancel/재열기로 전이하며 frozen 결과는 원 입력에 남긴다. unsupported/invalid required 입력의 Run은 계속 차단한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Save project | navigate / Save project | REOPEN-CONTACT-R13 |
| Review rebind again | navigate / Review rebind again | PRE-CONTACT-REBIND |
| Open old r12 result | navigate / Open old r12 result | POST-CONTACT |
| Run blocked (diagnosis) | navigate / Run blocked (diagnosis) | PRE-CONTACT-REBOUND |
| Review only unresolved references | navigate / Review only unresolved references | PRE-CONTACT-REBIND |
| Inspect old contact result / input | navigate / Inspect old contact result / input | POST-CONTACT |
| Keep state / save and reopen | navigate / Keep state / save and reopen | REOPEN-CONTACT-R13 |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Native New/Open model; no forced fixture |
| edit | Native Task/selection/Undo; BUSY_EDIT protects pending work |
| dirty | Managed save first restores design pose, preserves invalid draft |
| running | Native command ID differs from calculation job ID; generation guarded apply |
| fail | Failed feature/mesh/face reference/restore location opens directly |
| cancel | Cancel Task/preview/rebind separately from command/job; old mesh/results retained |
| complete | Preflight → frozen input → Runner → exact Post result |
| reopen | Editable FCStd/native dependencies and design pose; no solver rerun |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-14와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## PRE-CONTACT-UNSUPPORTED — Contact · adapter admission

편집 원본: `screens/PRE-CONTACT-UNSUPPORTED.svg` · 미리보기: `screens/PRE-CONTACT-UNSUPPORTED.png` · owner: **FreeCAD native document / Analysis 1**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-14: 선택 solver/version·surface formulation·element pairing의 지원, 미지원 cohesive 또는 large-sliding 항목. → preflight 오류 행에서 조건을 고치거나 지원 adapter를 선택한다. law를 자동 다른 법칙으로 바꾸지 않는다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Set A / geometry revision | reference / 해당 없음 | Pad underside / r12 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Set B / geometry revision | reference / 해당 없음 | Base top / r12 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Law | enum / 해당 없음 | Coulomb | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Friction μ | number / 1 | .15 | 미지정; sample을 기본값으로 쓰지 않음 / finite >=0 | 선택 owner / 대상 |
| Initial gap | number / mm | .20 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Normal policy | enum / 해당 없음 | A → B | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open native… | navigate / Open native… | PRE-DESIGN |
| Save project | navigate / Save project | REOPEN-CONTACT |
| Design | navigate / Design | PRE-DESIGN |
| Assembly | navigate / Assembly | PRE-MOTION |
| FEM | navigate / FEM | PRE-FEM |
| Preflight | navigate / Preflight | PRE-CONTACT-UNSUPPORTED |
| Run blocked | navigate / Run blocked | PRE-CONTACT-UNSUPPORTED |
| Results | navigate / Results | POST-CONTACT |
| Properties / selected object | navigate / Properties / selected object | PRE-FEM |
| Change impact / references | navigate / Change impact / references | PRE-CONTACT-REBIND |
| Register research variable | navigate / Register research variable | NUM-DOE |
| Flip / preview | navigate / Flip / preview | PRE-CONTACT-REBIND |
| Check capability | navigate / Check capability | PRE-CONTACT-UNSUPPORTED |
| Save invalid contact draft | navigate / Save invalid contact draft | REOPEN-CONTACT |
| Inspect solver settings | navigate / Inspect solver settings | SIM-IMPLICIT |
| Return to face sets | navigate / Return to face sets | PRE-CONTACT |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Native New/Open model; no forced fixture |
| edit | Native Task/selection/Undo; BUSY_EDIT protects pending work |
| dirty | Managed save first restores design pose, preserves invalid draft |
| running | Native command ID differs from calculation job ID; generation guarded apply |
| fail | Failed feature/mesh/face reference/restore location opens directly |
| cancel | Cancel Task/preview/rebind separately from command/job; old mesh/results retained |
| complete | Preflight → frozen input → Runner → exact Post result |
| reopen | Editable FCStd/native dependencies and design pose; no solver rerun |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-14와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## PRE-DESIGN — Bracket · editable native model

편집 원본: `screens/PRE-DESIGN.svg` · 미리보기: `screens/PRE-DESIGN.png` · owner: **FreeCAD native document / Analysis 1**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-10: 활성 Body/Part·Sketch·Feature 이력과 큰 3D, 선택한 named constraint. → native Sketcher/PartDesign Tasks에서 치수 또는 피처를 편집·재계산한다. 모델 트리 선택과 3D 강조가 일치한다.
- FN-10: 변경 전후 형상, invalid feature 또는 이전 정상 형상 표시. → Lab 검사에서 실패 feature로 이동하거나 native Undo로 복구한다. invalid draft 저장은 허용한다.
- FN-10: ‘연구 변수 등록’의 실제 object/path·unit·type·dependency, 현재값. → 선택 속성만 등록한다. display name과 stable research ID, native target을 분리한다.
- FN-34: 같은 native 치수/selection과 command receipt. → 실제 owner handler가 변경한 값이 GUI에 반영되는지 확인한다. 복제 headless 파일 변경을 열린 GUI 변경으로 말하지 않는다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Active Body | reference / 해당 없음 | Base | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Pad length | number / mm | 12.0 | 미지정; sample을 기본값으로 쓰지 않음 / >0 | 선택 owner / 대상 |
| Sketch constraint | native_constraint / 해당 없음 | Width = 80 mm | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Research variable | identifier / 해당 없음 | plate_thickness | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open native… | navigate / Open native… | PRE-DESIGN |
| Save project | navigate / Save project | REOPEN-CONTACT |
| Design | navigate / Design | PRE-DESIGN |
| Assembly | navigate / Assembly | PRE-MOTION |
| FEM | navigate / FEM | PRE-FEM |
| Preflight | navigate / Preflight | PRE-CONTACT-UNSUPPORTED |
| Run blocked | navigate / Run blocked | PRE-CONTACT-UNSUPPORTED |
| Results | navigate / Results | POST-CONTACT |
| Properties / selected object | navigate / Properties / selected object | PRE-FEM |
| Change impact / references | navigate / Change impact / references | PRE-CONTACT-REBIND |
| Register research variable | navigate / Register research variable | NUM-DOE |
| Recompute / effect check | navigate / Recompute / effect check | PRE-DESIGN |
| Open assembly | navigate / Open assembly | PRE-MOTION |
| Continue in FEM | navigate / Continue in FEM | PRE-FEM |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Native New/Open model; no forced fixture |
| edit | Native Task/selection/Undo; BUSY_EDIT protects pending work |
| dirty | Managed save first restores design pose, preserves invalid draft |
| running | Native command ID differs from calculation job ID; generation guarded apply |
| fail | Failed feature/mesh/face reference/restore location opens directly |
| cancel | Cancel Task/preview/rebind separately from command/job; old mesh/results retained |
| complete | Preflight → frozen input → Runner → exact Post result |
| reopen | Editable FCStd/native dependencies and design pose; no solver rerun |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-10, FN-34와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## PRE-FEM — Bracket · Analysis 1

편집 원본: `screens/PRE-FEM.svg` · 미리보기: `screens/PRE-FEM.png` · owner: **FreeCAD native document / Analysis 1**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-09: 할당 solid/shell/beam region·orientation·두께와 Material ref. → native 선택으로 적용 대상을 고르고 중복/미할당을 검사한다.
- FN-11: 설계 자세 복원 확인과 exact CAD revision. → FEM으로 전환한다. 적용한 P1에는 과거 preview의 P0 restore를 다시 보내지 않는다.
- FN-12: 설계 CAD와 analysis representation, 포함/제외·공유/접촉/tie 경계. → 다부품을 무조건 fuse하지 않고 body별 해석 참여와 차원 solid/shell/beam을 정한다.
- FN-12: body/face/edge/point selection filter, set 이름·개수·면적·revision. → Ctrl/Shift 또는 Add/Remove 목록으로 region을 만든다. 화살표와 대상 목록을 함께 확인한다.
- FN-12: 재료/section·orientation·load/BC와 active Analysis. → native Tasks에서 힘/압력/변위/온도/초기조건을 편집한다. total force와 pressure를 다른 quantity로 입력한다.
- FN-13: 새 mesh 적용 후 region/condition 재연결 상태. → 검사된 mesh를 해당 Analysis에 적용하고 기존 mesh·quality 기록을 남긴다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Representation | enum / 해당 없음 | Separated contact bodies | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Load / selected set | quantity_vector / 해당 없음 | Force 1000 N / Top | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Support | reference / 해당 없음 | Base underside / fixed | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Solver policy | enum / 해당 없음 | Static / implicit | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open native… | navigate / Open native… | PRE-DESIGN |
| Save project | navigate / Save project | REOPEN-CONTACT |
| Design | navigate / Design | PRE-DESIGN |
| Assembly | navigate / Assembly | PRE-MOTION |
| FEM | navigate / FEM | PRE-FEM |
| Preflight | navigate / Preflight | PRE-CONTACT-UNSUPPORTED |
| Run blocked | navigate / Run blocked | PRE-CONTACT-UNSUPPORTED |
| Results | navigate / Results | POST-CONTACT |
| Properties / selected object | navigate / Properties / selected object | PRE-FEM |
| Change impact / references | navigate / Change impact / references | PRE-CONTACT-REBIND |
| Register research variable | navigate / Register research variable | NUM-DOE |
| Contact pair… | navigate / Contact pair… | PRE-CONTACT |
| Local mesh / quality | navigate / Local mesh / quality | PRE-MESH-QUALITY |
| Nonlinear / step controls | navigate / Nonlinear / step controls | SIM-IMPLICIT |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Native New/Open model; no forced fixture |
| edit | Native Task/selection/Undo; BUSY_EDIT protects pending work |
| dirty | Managed save first restores design pose, preserves invalid draft |
| running | Native command ID differs from calculation job ID; generation guarded apply |
| fail | Failed feature/mesh/face reference/restore location opens directly |
| cancel | Cancel Task/preview/rebind separately from command/job; old mesh/results retained |
| complete | Preflight → frozen input → Runner → exact Post result |
| reopen | Editable FCStd/native dependencies and design pose; no solver rerun |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-09, FN-11, FN-12, FN-13와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## PRE-MESH-QUALITY — Mesh r6 · quality selection

편집 원본: `screens/PRE-MESH-QUALITY.svg` · 미리보기: `screens/PRE-MESH-QUALITY.png` · owner: **FreeCAD native document / Analysis 1**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-13: native Gmsh Tasks의 전체/국부 크기와 target region, 현재 mesh geometry revision. → global size와 selected-face local size를 정하고 생성한다. total 미지정이면 spinner/phase만 표시한다.
- FN-13: 새 mesh의 요소 수·유형, quality 지표 분포·실제 sampled/full 범위. → 불량 구간 또는 요소 행을 선택하면 3D에서 해당 element를 강조·격리·확대한다.
- FN-13: 국부 mesh 설정 및 주변 geometry, before/after 품질 비교. → refinement를 수정하고 부모 mesh에서 regenerate한다. 설정 변경만으로 current mesh라 표시하지 않는다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Element family | enum / 해당 없음 | Tet10 / supported path | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Global size | number / mm | 4.0 | 미지정; sample을 기본값으로 쓰지 않음 / >0 | 선택 owner / 대상 |
| Selected region size | number / mm | 1.0 | 미지정; sample을 기본값으로 쓰지 않음 / >0 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open native… | navigate / Open native… | PRE-DESIGN |
| Save project | navigate / Save project | REOPEN-CONTACT |
| Design | navigate / Design | PRE-DESIGN |
| Assembly | navigate / Assembly | PRE-MOTION |
| FEM | navigate / FEM | PRE-FEM |
| Preflight | navigate / Preflight | PRE-CONTACT-UNSUPPORTED |
| Run blocked | navigate / Run blocked | PRE-CONTACT-UNSUPPORTED |
| Results | navigate / Results | POST-CONTACT |
| Properties / selected object | navigate / Properties / selected object | PRE-FEM |
| Change impact / references | navigate / Change impact / references | PRE-CONTACT-REBIND |
| Register research variable | navigate / Register research variable | NUM-DOE |
| Regenerate / new command | navigate / Regenerate / new command | COMMAND-MESH |
| Zoom / isolate selection | navigate / Zoom / isolate selection | PRE-MESH-QUALITY |
| Edit selected refinement | navigate / Edit selected refinement | PRE-MESH-QUALITY |
| Previous mesh comparison | navigate / Previous mesh comparison | POST-COMPARE |
| Return to conditions | navigate / Return to conditions | PRE-FEM |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Native New/Open model; no forced fixture |
| edit | Native Task/selection/Undo; BUSY_EDIT protects pending work |
| dirty | Managed save first restores design pose, preserves invalid draft |
| running | Native command ID differs from calculation job ID; generation guarded apply |
| fail | Failed feature/mesh/face reference/restore location opens directly |
| cancel | Cancel Task/preview/rebind separately from command/job; old mesh/results retained |
| complete | Preflight → frozen input → Runner → exact Post result |
| reopen | Editable FCStd/native dependencies and design pose; no solver rerun |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-13와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## PRE-MOTION — Assembly · pose preview

편집 원본: `screens/PRE-MOTION.svg` · 미리보기: `screens/PRE-MOTION.png` · owner: **FreeCAD native document / Analysis 1**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-11: 부품 정의와 배치 Link, joint axis/limits, 설계 P0와 preview frame. → native Assembly로 부품·고정·관절을 만들고 시간/drive expression을 설정한다.
- FN-11: native 계산 phase·frame 개수와 supports_cancel, trace point의 로컬/세계 좌표. → 운동 계산 뒤 slider/재생으로 frame을 본다. trace point 선택→경로·time 표를 연결한다.
- FN-11: 일시정지·설계 자세 복원·현재 자세 적용이라는 세 동작. → 일시정지는 frame 유지, Stop/Cancel은 P0 복원. ‘현재 자세 적용’만 지원 native 정의의 새 설계 transaction이다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Design pose | reference / 해당 없음 | P0 / generation 41 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Preview | reference / 해당 없음 | P1 / frame 12 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Time interval | number / s | 0.00 … 1.00 | 미지정; sample을 기본값으로 쓰지 않음 / end > start | 선택 owner / 대상 |
| Output Δt | number / s | .02 | 미지정; sample을 기본값으로 쓰지 않음 / >0 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open native… | navigate / Open native… | PRE-DESIGN |
| Save project | navigate / Save project | REOPEN-CONTACT |
| Design | navigate / Design | PRE-DESIGN |
| Assembly | navigate / Assembly | PRE-MOTION |
| FEM | navigate / FEM | PRE-FEM |
| Preflight | navigate / Preflight | PRE-CONTACT-UNSUPPORTED |
| Run blocked | navigate / Run blocked | PRE-CONTACT-UNSUPPORTED |
| Results | navigate / Results | POST-CONTACT |
| Properties / selected object | navigate / Properties / selected object | PRE-FEM |
| Change impact / references | navigate / Change impact / references | PRE-CONTACT-REBIND |
| Register research variable | navigate / Register research variable | NUM-DOE |
| Pause preview | navigate / Pause preview | PRE-MOTION |
| Restore design pose | navigate / Restore design pose | PRE-DESIGN |
| Apply current pose… | navigate / Apply current pose… | PRE-FEM |
| Simulate restore failure | navigate / Simulate restore failure | PRE-RESTORE-FAILED |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Native New/Open model; no forced fixture |
| edit | Native Task/selection/Undo; BUSY_EDIT protects pending work |
| dirty | Managed save first restores design pose, preserves invalid draft |
| running | Native command ID differs from calculation job ID; generation guarded apply |
| fail | Failed feature/mesh/face reference/restore location opens directly |
| cancel | Cancel Task/preview/rebind separately from command/job; old mesh/results retained |
| complete | Preflight → frozen input → Runner → exact Post result |
| reopen | Editable FCStd/native dependencies and design pose; no solver rerun |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-11와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## PRE-RESTORE-FAILED — Assembly · restore needs verification

편집 원본: `screens/PRE-RESTORE-FAILED.svg` · 미리보기: `screens/PRE-RESTORE-FAILED.png` · owner: **FreeCAD native document / Analysis 1**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-11: 부품별 P0/실제 placement 차이와 출발/current generation. → 복원 미확인이면 저장/FEM 전환/export를 차단한다. 지금 상태 읽기→사용자 편집 대조→지원 복원 또는 새 분기를 선택한다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Design pose | reference / 해당 없음 | P0 / generation 41 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Preview | reference / 해당 없음 | P1 / frame 12 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Time interval | number / s | 0.00 … 1.00 | 미지정; sample을 기본값으로 쓰지 않음 / end > start | 선택 owner / 대상 |
| Output Δt | number / s | .02 | 미지정; sample을 기본값으로 쓰지 않음 / >0 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open native… | navigate / Open native… | PRE-DESIGN |
| Design | navigate / Design | PRE-DESIGN |
| Assembly | navigate / Assembly | PRE-MOTION |
| Preflight | navigate / Preflight | PRE-CONTACT-UNSUPPORTED |
| Results | navigate / Results | POST-CONTACT |
| Properties / selected object | navigate / Properties / selected object | PRE-FEM |
| Change impact / references | navigate / Change impact / references | PRE-CONTACT-REBIND |
| Register research variable | navigate / Register research variable | NUM-DOE |
| Pause preview | navigate / Pause preview | PRE-MOTION |
| Restore design pose | navigate / Restore design pose | PRE-DESIGN |
| Simulate restore failure | navigate / Simulate restore failure | PRE-RESTORE-FAILED |
| Reconnect / compare actual pose | navigate / Reconnect / compare actual pose | PRE-MOTION |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Native New/Open model; no forced fixture |
| edit | Native Task/selection/Undo; BUSY_EDIT protects pending work |
| dirty | Managed save first restores design pose, preserves invalid draft |
| running | Native command ID differs from calculation job ID; generation guarded apply |
| fail | Failed feature/mesh/face reference/restore location opens directly |
| cancel | Cancel Task/preview/rebind separately from command/job; old mesh/results retained |
| complete | Preflight → frozen input → Runner → exact Post result |
| reopen | Editable FCStd/native dependencies and design pose; no solver rerun |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-11와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## RECOVERY-REOPEN — Reopen saved work / recovery drafts

편집 원본: `screens/RECOVERY-REOPEN.svg` · 미리보기: `screens/RECOVERY-REOPEN.png` · owner: **Saved owner revisions + separate recovery capsule**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-01: 마지막 저장본과 복구 가능한 working draft의 차이, 원인과 기록 시각. → 저장본 열기 또는 복구 초안 이어가기를 선택한다. 열기만으로 계산·LLM을 실행하지 않는다.
- FN-02: saved Material r18, Plan r8 및 복구 draft, 마지막 저장 관계. → 새 owner에서 저장본/복구본을 구분해 연다. 미완료 save group은 재개 또는 해제하며 기존 refs는 그대로다.
- FN-07: 채택 Material 새 revision, Plan·Data refs, 원 run/실패 후보·holdout 곡선. → Save related 후 새 프로세스에서 연다. 후보 선택이나 재열기로 숨은 fit을 수행하지 않는다.
- FN-32: 보고서 artifact과 source model/results를 다시 열 수 있는 링크. → 새 session에서 근거를 열어 같은 원값/recipe를 조회한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open saved Material + Plan | navigate / Open saved Material + Plan | MAT-DIRTY |
| Recover raw unsaved draft | navigate / Recover raw unsaved draft | CLIENT-CONFLICT |
| Inspect moved dependencies | navigate / Inspect moved dependencies | POST-REPAIR |
| Open retained c017 | navigate / Open retained c017 | MAT-FIT-PARTIAL |
| Open saved Study | navigate / Open saved Study | STUDY-DECISION |
| Return to document chooser | navigate / Return to document chooser | HOME-EMPTY |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | New law/protocol or import observation |
| edit | Material value and embedded Plan bound have different Undo owners |
| dirty | Per-owner save/source refresh/Plan starting values explicit |
| running | Frozen input; current draft can diverge; old/late result linked correctly |
| fail | Failed candidate/input diagnostics or save receipt; no made-up curve |
| cancel | Stop submission separately from job terminal and window close |
| complete | Retained details/holdout → explicit owner adoption → save |
| reopen | Open saved rN or separate recovery capsule; never evaluate on selection |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-01, FN-02, FN-07, FN-32와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## REOPEN-CONSTITUTIVE — Reopen prescribed-F reference / saved study

편집 원본: `screens/REOPEN-CONSTITUTIVE.svg` · 미리보기: `screens/REOPEN-CONSTITUTIVE.png` · owner: **Saved prescribed-F reference / saved study**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-08: prescribed F 연구 정의·합성 reference·FD미실행 상태. → 같은 Material 연구로 열어 증분/접선을 이어서 검토한다. retained라는 이유로 evaluator실행을 꾸미지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open saved editor | navigate / Open saved editor | MAT-CONSTITUTIVE |
| Inspect reference fixture | navigate / Inspect reference fixture | MAT-CONSTITUTIVE |
| Repair / inspect dependencies | navigate / Repair / inspect dependencies | MAT-PROTOCOL |
| Document chooser | navigate / Document chooser | HOME-EMPTY |
| Continue editing the same owner | navigate / Continue editing the same owner | MAT-CONSTITUTIVE |
| Inspect reference fixture | navigate / Inspect reference fixture | MAT-CONSTITUTIVE |
| Inspect control protocol | navigate / Inspect control protocol | MAT-PROTOCOL |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | New law/protocol or import observation |
| edit | Material value and embedded Plan bound have different Undo owners |
| dirty | Per-owner save/source refresh/Plan starting values explicit |
| running | Frozen input; current draft can diverge; old/late result linked correctly |
| fail | Failed candidate/input diagnostics or save receipt; no made-up curve |
| cancel | Stop submission separately from job terminal and window close |
| complete | Retained details/holdout → explicit owner adoption → save |
| reopen | Open saved rN or separate recovery capsule; never evaluate on selection |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-08와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## REOPEN-CONTACT — Reopen Bracket.caepre / geometry r12

편집 원본: `screens/REOPEN-CONTACT.svg` · 미리보기: `screens/REOPEN-CONTACT.png` · owner: **Saved Bracket.caepre / geometry r12**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-14: 이 도구의 정확한 saved owner·입력·결과·누락 branch, 새 session. → 같은 도구 편집/보존 결과/영향받은 참조 복구 중 선택한다. 자동 실행하지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open saved editor | navigate / Open saved editor | PRE-CONTACT |
| Open retained result | navigate / Open retained result | POST-CONTACT |
| Repair / inspect dependencies | navigate / Repair / inspect dependencies | PRE-CONTACT-REBIND |
| Document chooser | navigate / Document chooser | HOME-EMPTY |
| Continue editing the same owner | navigate / Continue editing the same owner | PRE-CONTACT |
| Open retained result | navigate / Open retained result | POST-CONTACT |
| Repair only affected references | navigate / Repair only affected references | PRE-CONTACT-REBIND |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Native New/Open model; no forced fixture |
| edit | Native Task/selection/Undo; BUSY_EDIT protects pending work |
| dirty | Managed save first restores design pose, preserves invalid draft |
| running | Native command ID differs from calculation job ID; generation guarded apply |
| fail | Failed feature/mesh/face reference/restore location opens directly |
| cancel | Cancel Task/preview/rebind separately from command/job; old mesh/results retained |
| complete | Preflight → frozen input → Runner → exact Post result |
| reopen | Editable FCStd/native dependencies and design pose; no solver rerun |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-14와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## REOPEN-CONTACT-CANCELLED — Reopen geometry r13 / invalid contact refs

편집 원본: `screens/REOPEN-CONTACT-CANCELLED.svg` · 미리보기: `screens/REOPEN-CONTACT-CANCELLED.png` · owner: **Saved geometry r13 / invalid contact refs**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-14: 이전/현재 입력·draft·saved revision·정확한 결과와 해당 복구 상태. 같은 기능의 결과를 다른 예시로 대체하지 않는다. → 명시 Apply/Save/Cancel/재열기로 전이하며 frozen 결과는 원 입력에 남긴다. unsupported/invalid required 입력의 Run은 계속 차단한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open saved editor | navigate / Open saved editor | PRE-CONTACT-CANCELLED |
| Open retained result | navigate / Open retained result | POST-CONTACT |
| Repair / inspect dependencies | navigate / Repair / inspect dependencies | PRE-CONTACT-REBIND |
| Document chooser | navigate / Document chooser | HOME-EMPTY |
| Continue editing the same owner | navigate / Continue editing the same owner | PRE-CONTACT-CANCELLED |
| Open retained result | navigate / Open retained result | POST-CONTACT |
| Repair only affected references | navigate / Repair only affected references | PRE-CONTACT-REBIND |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Native New/Open model; no forced fixture |
| edit | Native Task/selection/Undo; BUSY_EDIT protects pending work |
| dirty | Managed save first restores design pose, preserves invalid draft |
| running | Native command ID differs from calculation job ID; generation guarded apply |
| fail | Failed feature/mesh/face reference/restore location opens directly |
| cancel | Cancel Task/preview/rebind separately from command/job; old mesh/results retained |
| complete | Preflight → frozen input → Runner → exact Post result |
| reopen | Editable FCStd/native dependencies and design pose; no solver rerun |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-14와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## REOPEN-CONTACT-R13 — Reopen geometry r13 / rebound contact r8

편집 원본: `screens/REOPEN-CONTACT-R13.svg` · 미리보기: `screens/REOPEN-CONTACT-R13.png` · owner: **Saved geometry r13 / rebound contact r8**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-14: 이전/현재 입력·draft·saved revision·정확한 결과와 해당 복구 상태. 같은 기능의 결과를 다른 예시로 대체하지 않는다. → 명시 Apply/Save/Cancel/재열기로 전이하며 frozen 결과는 원 입력에 남긴다. unsupported/invalid required 입력의 Run은 계속 차단한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open saved editor | navigate / Open saved editor | PRE-CONTACT-REBOUND |
| Open retained result | navigate / Open retained result | POST-CONTACT |
| Repair / inspect dependencies | navigate / Repair / inspect dependencies | PRE-CONTACT-REBIND |
| Document chooser | navigate / Document chooser | HOME-EMPTY |
| Continue editing the same owner | navigate / Continue editing the same owner | PRE-CONTACT-REBOUND |
| Open retained result | navigate / Open retained result | POST-CONTACT |
| Repair only affected references | navigate / Repair only affected references | PRE-CONTACT-REBIND |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Native New/Open model; no forced fixture |
| edit | Native Task/selection/Undo; BUSY_EDIT protects pending work |
| dirty | Managed save first restores design pose, preserves invalid draft |
| running | Native command ID differs from calculation job ID; generation guarded apply |
| fail | Failed feature/mesh/face reference/restore location opens directly |
| cancel | Cancel Task/preview/rebind separately from command/job; old mesh/results retained |
| complete | Preflight → frozen input → Runner → exact Post result |
| reopen | Editable FCStd/native dependencies and design pose; no solver rerun |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-14와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## REOPEN-DATA — Reopen Data A+B / r4

편집 원본: `screens/REOPEN-DATA.svg` · 미리보기: `screens/REOPEN-DATA.png` · owner: **Saved Data A+B / r4**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-03: 원본301/241행·Data r4의 변환과 quality mask·저장 관측. → 같은 Data owner를 열어 표/매핑/교정 자료를 이어서 편집한다. Plan train/holdout는 덮어쓰지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open saved editor | navigate / Open saved editor | DATA-EDIT |
| Inspect stored mapping | navigate / Inspect stored mapping | DATA-MAP |
| Repair / inspect dependencies | navigate / Repair / inspect dependencies | DATA-CALIBRATION |
| Document chooser | navigate / Document chooser | HOME-EMPTY |
| Continue editing the same owner | navigate / Continue editing the same owner | DATA-EDIT |
| Inspect stored mapping | navigate / Inspect stored mapping | DATA-MAP |
| Inspect calibration | navigate / Inspect calibration | DATA-CALIBRATION |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open file(s) or create sheet |
| edit | Enter/Tab commit cell to Data; Esc cancels buffer |
| dirty | Save Data; exact observation refs stay on saved revision |
| running | Import/transform command tracks real phase; current dataset retained |
| fail | Open marked row/column/recipe; keep invalid draft |
| cancel | Cancel mapping/transform before publish; old channels intact |
| complete | Inspect canonical samples → link observation → save |
| reopen | Restore raw hashes/channel IDs/recipes/masks; no calculation |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-03와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## REOPEN-EVALUATION — Reopen E-02 / r5

편집 원본: `screens/REOPEN-EVALUATION.svg` · 미리보기: `screens/REOPEN-EVALUATION.png` · owner: **Saved E-02 / r5**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-19: 정의·exact refs·잔차·미수렴·부분 결과·재사용 가능 prefix. → save→새 owner reopen 후 같은 editor에서 수정하거나 명시 새 attempt를 시작한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open saved editor | navigate / Open saved editor | EVAL-STAGES |
| Open retained result | navigate / Open retained result | EVAL-NONCONVERGED |
| Repair / inspect dependencies | navigate / Repair / inspect dependencies | EVAL-TRANSFER |
| Document chooser | navigate / Document chooser | HOME-EMPTY |
| Continue editing the same owner | navigate / Continue editing the same owner | EVAL-STAGES |
| Open retained result | navigate / Open retained result | EVAL-NONCONVERGED |
| Repair only affected references | navigate / Repair only affected references | EVAL-TRANSFER |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Create existing Evaluation kind=evaluation, add saved stages |
| edit | Same stage/transfer/iteration editor and owner in standalone/embedded use |
| dirty | Save definition; linked Plan keeps exact old ref until explicit update |
| running | Static connection distinct from actual field; child attempts and residual |
| fail | Failed stage / transfer / NOT_CONVERGED retain input and partial fields |
| cancel | Stop subsequent stages; actual current child terminal separate |
| complete | Inspect stage refs/field mapping/satisfied residual before valid result |
| reopen | Restore same definition/checkpoint; identical full hash/values required for current prefix reuse |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-19와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## REOPEN-EXPERT — Reopen Discussion D-02 / r4

편집 원본: `screens/REOPEN-EXPERT.svg` · 미리보기: `screens/REOPEN-EXPERT.png` · owner: **Saved Discussion D-02 / r4**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-30: 이 도구의 정확한 saved owner·입력·결과·누락 branch, 새 session. → 같은 도구 편집/보존 결과/영향받은 참조 복구 중 선택한다. 자동 실행하지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open saved editor | navigate / Open saved editor | EXPERT-DRAFT |
| Open retained result | navigate / Open retained result | EXPERT-DISCUSS |
| Repair / inspect dependencies | navigate / Repair / inspect dependencies | STUDY-DECISION |
| Document chooser | navigate / Document chooser | HOME-EMPTY |
| Continue editing the same owner | navigate / Continue editing the same owner | EXPERT-DRAFT |
| Open retained result | navigate / Open retained result | EXPERT-DISCUSS |
| Open linked Study | navigate / Open linked Study | STUDY-DECISION |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Draft question/source/roles without provider |
| edit | Topic/turn/reply owner; actual author retained |
| dirty | Save reply/discussion draft |
| running | Actual provider status separate from solver/Plan jobs |
| fail | Provider unavailable/limit preserves draft and retained turns |
| cancel | Pause next turns; solver cancel is separate |
| complete | Editable Plan / explicit Study judgment, no automatic adoption |
| reopen | Retained turns, sources and Plan refs without asking provider again |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-30와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## REOPEN-FE-ASSIGNMENT — Reopen FE assignment draft / Bracket r12

편집 원본: `screens/REOPEN-FE-ASSIGNMENT.svg` · 미리보기: `screens/REOPEN-FE-ASSIGNMENT.png` · owner: **Saved FE assignment draft / Bracket r12**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-09: 정확 lawr19→Bracketr12/Base assignmentdraft와 미검증card. → native target Analysis를 다시 열어 호환성진단을 수정한다. draft저장은 exportadmission을 바꾸지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open saved editor | navigate / Open saved editor | MAT-FE-TRANSFER |
| Open target Analysis | navigate / Open target Analysis | PRE-FEM |
| Repair / inspect dependencies | navigate / Repair / inspect dependencies | MAT-FE-TRANSFER |
| Document chooser | navigate / Document chooser | HOME-EMPTY |
| Continue editing the same owner | navigate / Continue editing the same owner | MAT-FE-TRANSFER |
| Open target Analysis | navigate / Open target Analysis | PRE-FEM |
| Review card compatibility | navigate / Review card compatibility | MAT-FE-TRANSFER |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Native New/Open model; no forced fixture |
| edit | Native Task/selection/Undo; BUSY_EDIT protects pending work |
| dirty | Managed save first restores design pose, preserves invalid draft |
| running | Native command ID differs from calculation job ID; generation guarded apply |
| fail | Failed feature/mesh/face reference/restore location opens directly |
| cancel | Cancel Task/preview/rebind separately from command/job; old mesh/results retained |
| complete | Preflight → frozen input → Runner → exact Post result |
| reopen | Editable FCStd/native dependencies and design pose; no solver rerun |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-09와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## REOPEN-MAT-ADOPTED — Reopen Material r19 / adopted c017

편집 원본: `screens/REOPEN-MAT-ADOPTED.svg` · 미리보기: `screens/REOPEN-MAT-ADOPTED.png` · owner: **Saved Material r19 / adopted c017**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-07: 이전/현재 입력·draft·saved revision·정확한 결과와 해당 복구 상태. 같은 기능의 결과를 다른 예시로 대체하지 않는다. → 명시 Apply/Save/Cancel/재열기로 전이하며 frozen 결과는 원 입력에 남긴다. unsupported/invalid required 입력의 Run은 계속 차단한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open saved editor | navigate / Open saved editor | MAT-ADOPT-SAVED |
| Open retained result | navigate / Open retained result | MAT-FIT-PARTIAL |
| Repair / inspect dependencies | navigate / Repair / inspect dependencies | MAT-ADOPT-CONFLICT |
| Document chooser | navigate / Document chooser | HOME-EMPTY |
| Continue editing the same owner | navigate / Continue editing the same owner | MAT-ADOPT-SAVED |
| Open retained result | navigate / Open retained result | MAT-FIT-PARTIAL |
| Repair only affected references | navigate / Repair only affected references | MAT-ADOPT-CONFLICT |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | New law/protocol or import observation |
| edit | Material value and embedded Plan bound have different Undo owners |
| dirty | Per-owner save/source refresh/Plan starting values explicit |
| running | Frozen input; current draft can diverge; old/late result linked correctly |
| fail | Failed candidate/input diagnostics or save receipt; no made-up curve |
| cancel | Stop submission separately from job terminal and window close |
| complete | Retained details/holdout → explicit owner adoption → save |
| reopen | Open saved rN or separate recovery capsule; never evaluate on selection |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-07와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## REOPEN-MAT-BRANCH — Reopen M-branch-01 / r1

편집 원본: `screens/REOPEN-MAT-BRANCH.svg` · 미리보기: `screens/REOPEN-MAT-BRANCH.png` · owner: **Saved M-branch-01 / r1**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-07: 저장된 M-branch-01r1과 원 Material18·Plan8참조. → branch를 편집하되 원 Plan을 자동redirect하지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open saved editor | navigate / Open saved editor | MAT-BRANCH-SAVED |
| Open retained result | navigate / Open retained result | MAT-FIT-PARTIAL |
| Repair / inspect dependencies | navigate / Repair / inspect dependencies | MAT-ADOPT-CONFLICT |
| Document chooser | navigate / Document chooser | HOME-EMPTY |
| Continue editing the same owner | navigate / Continue editing the same owner | MAT-BRANCH-SAVED |
| Open retained result | navigate / Open retained result | MAT-FIT-PARTIAL |
| Repair only affected references | navigate / Repair only affected references | MAT-ADOPT-CONFLICT |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | New law/protocol or import observation |
| edit | Material value and embedded Plan bound have different Undo owners |
| dirty | Per-owner save/source refresh/Plan starting values explicit |
| running | Frozen input; current draft can diverge; old/late result linked correctly |
| fail | Failed candidate/input diagnostics or save receipt; no made-up curve |
| cancel | Stop submission separately from job terminal and window close |
| complete | Retained details/holdout → explicit owner adoption → save |
| reopen | Open saved rN or separate recovery capsule; never evaluate on selection |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-07와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## REOPEN-NEXT-TEST — Reopen N-next / saved next-test draft

편집 원본: `screens/REOPEN-NEXT-TEST.svg` · 미리보기: `screens/REOPEN-NEXT-TEST.png` · owner: **Saved N-next / saved next-test draft**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-29: 이전/현재 입력·draft·saved revision·정확한 결과와 해당 복구 상태. 같은 기능의 결과를 다른 예시로 대체하지 않는다. → 명시 Apply/Save/Cancel/재열기로 전이하며 frozen 결과는 원 입력에 남긴다. unsupported/invalid required 입력의 Run은 계속 차단한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open saved editor | navigate / Open saved editor | NUM-NEXT-TEST |
| Open source Study | navigate / Open source Study | STUDY-DECISION |
| Repair / inspect dependencies | navigate / Repair / inspect dependencies | DATA-CALIBRATION |
| Document chooser | navigate / Document chooser | HOME-EMPTY |
| Continue editing the same owner | navigate / Continue editing the same owner | NUM-NEXT-TEST |
| Open source Study | navigate / Open source Study | STUDY-DECISION |
| Inspect calibration | navigate / Inspect calibration | DATA-CALIBRATION |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Create Plan from supported evaluator or external exchange |
| edit | Typed variables/observations/method; source owner bounds retained |
| dirty | Plan source and starts explicitly refreshed/saved |
| running | Fixed mask/method/seed/budget/source; failures and penalties separate |
| fail | Select failed candidate, exact input/log; missing NOT_EVALUATED |
| cancel | Stop next submissions, retain late result, no hidden resume |
| complete | Method-specific evidence → explicit confirmation/adoption |
| reopen | History browse without exact engine resume unless checkpoint supported |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-29와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## REOPEN-NUM-BATCH — Reopen N-Batch/r2

편집 원본: `screens/REOPEN-NUM-BATCH.svg` · 미리보기: `screens/REOPEN-NUM-BATCH.png` · owner: **Saved N-Batch/r2**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-26: 같은 Plan/method/원자료/실행 기록과 saved refs. → 같은 method 결과를 열고 재실행 없이 읽는다. engine resume 지원이 없으면 새 실행으로 제안한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open saved editor | navigate / Open saved editor | NUM-BATCH |
| Open retained result | navigate / Open retained result | NUM-CASE-BATCH |
| Repair / inspect dependencies | navigate / Repair / inspect dependencies | NUM-BATCH |
| Document chooser | navigate / Document chooser | HOME-EMPTY |
| Continue editing the same owner | navigate / Continue editing the same owner | NUM-BATCH |
| Open retained result | navigate / Open retained result | NUM-CASE-BATCH |
| Repair only affected references | navigate / Repair only affected references | NUM-BATCH |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Create Plan from supported evaluator or external exchange |
| edit | Typed variables/observations/method; source owner bounds retained |
| dirty | Plan source and starts explicitly refreshed/saved |
| running | Fixed mask/method/seed/budget/source; failures and penalties separate |
| fail | Select failed candidate, exact input/log; missing NOT_EVALUATED |
| cancel | Stop next submissions, retain late result, no hidden resume |
| complete | Method-specific evidence → explicit confirmation/adoption |
| reopen | History browse without exact engine resume unless checkpoint supported |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-26와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## REOPEN-NUM-DOE — Reopen N-DOE/r3

편집 원본: `screens/REOPEN-NUM-DOE.svg` · 미리보기: `screens/REOPEN-NUM-DOE.png` · owner: **Saved N-DOE/r3**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-20: 같은 Plan/method/원자료/실행 기록과 saved refs. → 같은 method 결과를 열고 재실행 없이 읽는다. engine resume 지원이 없으면 새 실행으로 제안한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open saved editor | navigate / Open saved editor | NUM-DOE |
| Open retained result | navigate / Open retained result | NUM-CASE-DOE |
| Repair / inspect dependencies | navigate / Repair / inspect dependencies | NUM-DOE |
| Document chooser | navigate / Document chooser | HOME-EMPTY |
| Continue editing the same owner | navigate / Continue editing the same owner | NUM-DOE |
| Open retained result | navigate / Open retained result | NUM-CASE-DOE |
| Repair only affected references | navigate / Repair only affected references | NUM-DOE |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Create Plan from supported evaluator or external exchange |
| edit | Typed variables/observations/method; source owner bounds retained |
| dirty | Plan source and starts explicitly refreshed/saved |
| running | Fixed mask/method/seed/budget/source; failures and penalties separate |
| fail | Select failed candidate, exact input/log; missing NOT_EVALUATED |
| cancel | Stop next submissions, retain late result, no hidden resume |
| complete | Method-specific evidence → explicit confirmation/adoption |
| reopen | History browse without exact engine resume unless checkpoint supported |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-20와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## REOPEN-NUM-MOO — Reopen N-MOO/r4

편집 원본: `screens/REOPEN-NUM-MOO.svg` · 미리보기: `screens/REOPEN-NUM-MOO.png` · owner: **Saved N-MOO/r4**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-24: 같은 Plan/method/원자료/실행 기록과 saved refs. → 같은 method 결과를 열고 재실행 없이 읽는다. engine resume 지원이 없으면 새 실행으로 제안한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open saved editor | navigate / Open saved editor | NUM-MOO |
| Open retained result | navigate / Open retained result | NUM-CASE-MOO |
| Repair / inspect dependencies | navigate / Repair / inspect dependencies | NUM-MOO |
| Document chooser | navigate / Document chooser | HOME-EMPTY |
| Continue editing the same owner | navigate / Continue editing the same owner | NUM-MOO |
| Open retained result | navigate / Open retained result | NUM-CASE-MOO |
| Repair only affected references | navigate / Repair only affected references | NUM-MOO |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Create Plan from supported evaluator or external exchange |
| edit | Typed variables/observations/method; source owner bounds retained |
| dirty | Plan source and starts explicitly refreshed/saved |
| running | Fixed mask/method/seed/budget/source; failures and penalties separate |
| fail | Select failed candidate, exact input/log; missing NOT_EVALUATED |
| cancel | Stop next submissions, retain late result, no hidden resume |
| complete | Method-specific evidence → explicit confirmation/adoption |
| reopen | History browse without exact engine resume unless checkpoint supported |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-24와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## REOPEN-NUM-SENSITIVITY — Reopen N-Sobol/r2

편집 원본: `screens/REOPEN-NUM-SENSITIVITY.svg` · 미리보기: `screens/REOPEN-NUM-SENSITIVITY.png` · owner: **Saved N-Sobol/r2**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-20: 같은 Plan/method/원자료/실행 기록과 saved refs. → 같은 method 결과를 열고 재실행 없이 읽는다. engine resume 지원이 없으면 새 실행으로 제안한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open saved editor | navigate / Open saved editor | NUM-SENSITIVITY |
| Open retained result | navigate / Open retained result | NUM-CASE-SENSITIVITY |
| Repair / inspect dependencies | navigate / Repair / inspect dependencies | NUM-SENSITIVITY |
| Document chooser | navigate / Document chooser | HOME-EMPTY |
| Continue editing the same owner | navigate / Continue editing the same owner | NUM-SENSITIVITY |
| Open retained result | navigate / Open retained result | NUM-CASE-SENSITIVITY |
| Repair only affected references | navigate / Repair only affected references | NUM-SENSITIVITY |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Create Plan from supported evaluator or external exchange |
| edit | Typed variables/observations/method; source owner bounds retained |
| dirty | Plan source and starts explicitly refreshed/saved |
| running | Fixed mask/method/seed/budget/source; failures and penalties separate |
| fail | Select failed candidate, exact input/log; missing NOT_EVALUATED |
| cancel | Stop next submissions, retain late result, no hidden resume |
| complete | Method-specific evidence → explicit confirmation/adoption |
| reopen | History browse without exact engine resume unless checkpoint supported |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-20와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## REOPEN-NUM-SURROGATE — Reopen N-RBF/r4

편집 원본: `screens/REOPEN-NUM-SURROGATE.svg` · 미리보기: `screens/REOPEN-NUM-SURROGATE.png` · owner: **Saved N-RBF/r4**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-23: 같은 Plan/method/원자료/실행 기록과 saved refs. → 같은 method 결과를 열고 재실행 없이 읽는다. engine resume 지원이 없으면 새 실행으로 제안한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open saved editor | navigate / Open saved editor | NUM-SURROGATE |
| Open retained result | navigate / Open retained result | NUM-CASE-SURROGATE |
| Repair / inspect dependencies | navigate / Repair / inspect dependencies | NUM-SURROGATE |
| Document chooser | navigate / Document chooser | HOME-EMPTY |
| Continue editing the same owner | navigate / Continue editing the same owner | NUM-SURROGATE |
| Open retained result | navigate / Open retained result | NUM-CASE-SURROGATE |
| Repair only affected references | navigate / Repair only affected references | NUM-SURROGATE |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Create Plan from supported evaluator or external exchange |
| edit | Typed variables/observations/method; source owner bounds retained |
| dirty | Plan source and starts explicitly refreshed/saved |
| running | Fixed mask/method/seed/budget/source; failures and penalties separate |
| fail | Select failed candidate, exact input/log; missing NOT_EVALUATED |
| cancel | Stop next submissions, retain late result, no hidden resume |
| complete | Method-specific evidence → explicit confirmation/adoption |
| reopen | History browse without exact engine resume unless checkpoint supported |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-23와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## REOPEN-NUM-UQ — Reopen N-UQ/r2

편집 원본: `screens/REOPEN-NUM-UQ.svg` · 미리보기: `screens/REOPEN-NUM-UQ.png` · owner: **Saved N-UQ/r2**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-22: 같은 Plan/method/원자료/실행 기록과 saved refs. → 같은 method 결과를 열고 재실행 없이 읽는다. engine resume 지원이 없으면 새 실행으로 제안한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open saved editor | navigate / Open saved editor | NUM-UQ |
| Open retained result | navigate / Open retained result | NUM-CASE-UQ |
| Repair / inspect dependencies | navigate / Repair / inspect dependencies | NUM-UQ |
| Document chooser | navigate / Document chooser | HOME-EMPTY |
| Continue editing the same owner | navigate / Continue editing the same owner | NUM-UQ |
| Open retained result | navigate / Open retained result | NUM-CASE-UQ |
| Repair only affected references | navigate / Repair only affected references | NUM-UQ |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Create Plan from supported evaluator or external exchange |
| edit | Typed variables/observations/method; source owner bounds retained |
| dirty | Plan source and starts explicitly refreshed/saved |
| running | Fixed mask/method/seed/budget/source; failures and penalties separate |
| fail | Select failed candidate, exact input/log; missing NOT_EVALUATED |
| cancel | Stop next submissions, retain late result, no hidden resume |
| complete | Method-specific evidence → explicit confirmation/adoption |
| reopen | History browse without exact engine resume unless checkpoint supported |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-22와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## REOPEN-NUMERICAL — Reopen N-05 / r8

편집 원본: `screens/REOPEN-NUMERICAL.svg` · 미리보기: `screens/REOPEN-NUMERICAL.png` · owner: **Saved N-05 / r8**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-21: Plan N-05r8/sourceMaterial17·후보/실패·미보존 상세. → 계산 없이 같은 Plan·retainedfit을 열고 명시새평가와 이력열람을 구별한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open saved editor | navigate / Open saved editor | NUM-OPTIMIZE |
| Open retained result | navigate / Open retained result | MAT-FIT-PARTIAL |
| Repair / inspect dependencies | navigate / Repair / inspect dependencies | CLIENT-CONFLICT |
| Document chooser | navigate / Document chooser | HOME-EMPTY |
| Continue editing the same owner | navigate / Continue editing the same owner | NUM-OPTIMIZE |
| Open retained result | navigate / Open retained result | MAT-FIT-PARTIAL |
| Repair only affected references | navigate / Repair only affected references | CLIENT-CONFLICT |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Create Plan from supported evaluator or external exchange |
| edit | Typed variables/observations/method; source owner bounds retained |
| dirty | Plan source and starts explicitly refreshed/saved |
| running | Fixed mask/method/seed/budget/source; failures and penalties separate |
| fail | Select failed candidate, exact input/log; missing NOT_EVALUATED |
| cancel | Stop next submissions, retain late result, no hidden resume |
| complete | Method-specific evidence → explicit confirmation/adoption |
| reopen | History browse without exact engine resume unless checkpoint supported |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-21와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## REOPEN-PDE — Reopen Q-04 / r3

편집 원본: `screens/REOPEN-PDE.svg` · 미리보기: `screens/REOPEN-PDE.png` · owner: **Saved Q-04 / r3**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-18: 이 도구의 정확한 saved owner·입력·결과·누락 branch, 새 session. → 같은 도구 편집/보존 결과/영향받은 참조 복구 중 선택한다. 자동 실행하지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open saved editor | navigate / Open saved editor | PDE-EQUATION |
| Open retained result | navigate / Open retained result | PDE-RESULT |
| Repair / inspect dependencies | navigate / Repair / inspect dependencies | PDE-INVALID |
| Document chooser | navigate / Document chooser | HOME-EMPTY |
| Continue editing the same owner | navigate / Continue editing the same owner | PDE-EQUATION |
| Open retained result | navigate / Open retained result | PDE-RESULT |
| Repair only affected references | navigate / Repair only affected references | PDE-INVALID |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | New domain/equation without CAD |
| edit | Node-selected settings and spatial BC selection |
| dirty | Invalid equation draft saveable |
| running | Frozen model / adapter actual output / same Runner |
| fail | Expression, region or solver diagnostic opens corresponding node |
| cancel | Current evaluation cancel; keep source and last results |
| complete | Inspect reference/mesh errors then save |
| reopen | Restore equation/mesh/BC/retained results without runtime |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-18와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## REOPEN-POST — Reopen Post analysis / r6

편집 원본: `screens/REOPEN-POST.svg` · 미리보기: `screens/REOPEN-POST.png` · owner: **Saved Post analysis / r6**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-27: 이 도구의 정확한 saved owner·입력·결과·누락 branch, 새 session. → 같은 도구 편집/보존 결과/영향받은 참조 복구 중 선택한다. 자동 실행하지 않는다.
- FN-28: 이 도구의 정확한 saved owner·입력·결과·누락 branch, 새 session. → 같은 도구 편집/보존 결과/영향받은 참조 복구 중 선택한다. 자동 실행하지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open saved editor | navigate / Open saved editor | POST-MEASURE |
| Open retained result | navigate / Open retained result | POST-COMPARE |
| Repair / inspect dependencies | navigate / Repair / inspect dependencies | POST-REPAIR |
| Document chooser | navigate / Document chooser | HOME-EMPTY |
| Continue editing the same owner | navigate / Continue editing the same owner | POST-MEASURE |
| Open retained result | navigate / Open retained result | POST-COMPARE |
| Repair only affected references | navigate / Repair only affected references | POST-REPAIR |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open supported registered file set / managed PVSM |
| edit | Pending native properties / Apply / Reset; direct view changes separate |
| dirty | Ctrl+S managed analysis, native Save Data remains export |
| running | Native Apply scope/command ID; current source kept |
| fail | Broken reader/branch or invalid correspondence; valid branches remain |
| cancel | Reset preview/pending or command cancel with actual support; no invented rollback |
| complete | Save measurements/recipe/mask/native state/results |
| reopen | Exact values/recipe; missing files repaired by same bytes or new branch |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-27, FN-28와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## REOPEN-REPORT — Reopen Research report / exported draft

편집 원본: `screens/REOPEN-REPORT.svg` · 미리보기: `screens/REOPEN-REPORT.png` · owner: **Saved Research report / exported draft**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-32: S-02r3/evidence/contact-result-031/r1/F05원값을 가진 reportdraft. → 저장한 report와 sourceStudy를 다시 열고 UNKNOWN/NOT_RELEASED를 보존한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open saved editor | navigate / Open saved editor | REPORT-REVIEW |
| Inspect exported report | navigate / Inspect exported report | REPORT-REVIEW |
| Repair / inspect dependencies | navigate / Repair / inspect dependencies | STUDY-DECISION |
| Document chooser | navigate / Document chooser | HOME-EMPTY |
| Continue editing the same owner | navigate / Continue editing the same owner | REPORT-REVIEW |
| Inspect exported report | navigate / Inspect exported report | REPORT-REVIEW |
| Open source Study | navigate / Open source Study | STUDY-DECISION |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Question/hypothesis first; no Plan/Expert prerequisite |
| edit | Explicit evidence relation / decision / next research |
| dirty | Study owns adopted judgments; Discussion stays separate |
| running | Study edit does not execute jobs; links may observe running result |
| fail | Reference/locator invalid: repair or save draft without evidence claim |
| cancel | Cancel evidence attachment or judgment leaves prior decision |
| complete | Explicit judgment + unresolved questions + precise references |
| reopen | Same question/hypotheses/decisions without automatic inference |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-32와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## REOPEN-SIMULATION — Reopen V-03 draft / exact model refs

편집 원본: `screens/REOPEN-SIMULATION.svg` · 미리보기: `screens/REOPEN-SIMULATION.png` · owner: **Saved V-03 draft / exact model refs**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-15: 이 도구의 정확한 saved owner·입력·결과·누락 branch, 새 session. → 같은 도구 편집/보존 결과/영향받은 참조 복구 중 선택한다. 자동 실행하지 않는다.
- FN-16: 이 도구의 정확한 saved owner·입력·결과·누락 branch, 새 session. → 같은 도구 편집/보존 결과/영향받은 참조 복구 중 선택한다. 자동 실행하지 않는다.
- FN-17: 이 도구의 정확한 saved owner·입력·결과·누락 branch, 새 session. → 같은 도구 편집/보존 결과/영향받은 참조 복구 중 선택한다. 자동 실행하지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open saved editor | navigate / Open saved editor | SIM-IMPLICIT |
| Open retained result | navigate / Open retained result | SIM-EXPLICIT |
| Repair / inspect dependencies | navigate / Repair / inspect dependencies | SETUP-CAPABILITY |
| Document chooser | navigate / Document chooser | HOME-EMPTY |
| Continue editing the same owner | navigate / Continue editing the same owner | SIM-IMPLICIT |
| Open retained result | navigate / Open retained result | SIM-EXPLICIT |
| Repair only affected references | navigate / Repair only affected references | SETUP-CAPABILITY |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open or create the relevant owner record |
| edit | Use typed fields / contextual actions |
| dirty | Preserve owner draft / exact refs |
| running | No automatic activity in this board; observe external job separately |
| fail | Open diagnostic, save draft and retain evidence |
| cancel | Cancel preview / keep previous owner content |
| complete | Save exact record / explicit next tool |
| reopen | Restore saved refs / no hidden execution |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-15, FN-16, FN-17와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## REOPEN-STUDY — Reopen S-02 / r3

편집 원본: `screens/REOPEN-STUDY.svg` · 미리보기: `screens/REOPEN-STUDY.png` · owner: **Saved S-02 / r3**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-29: 이 도구의 정확한 saved owner·입력·결과·누락 branch, 새 session. → 같은 도구 편집/보존 결과/영향받은 참조 복구 중 선택한다. 자동 실행하지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open saved editor | navigate / Open saved editor | STUDY-DECISION |
| Open retained result | navigate / Open retained result | REPORT-REVIEW |
| Repair / inspect dependencies | navigate / Repair / inspect dependencies | DATA-CALIBRATION |
| Document chooser | navigate / Document chooser | HOME-EMPTY |
| Continue editing the same owner | navigate / Continue editing the same owner | STUDY-DECISION |
| Open retained result | navigate / Open retained result | REPORT-REVIEW |
| Repair only affected references | navigate / Repair only affected references | DATA-CALIBRATION |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Question/hypothesis first; no Plan/Expert prerequisite |
| edit | Explicit evidence relation / decision / next research |
| dirty | Study owns adopted judgments; Discussion stays separate |
| running | Study edit does not execute jobs; links may observe running result |
| fail | Reference/locator invalid: repair or save draft without evidence claim |
| cancel | Cancel evidence attachment or judgment leaves prior decision |
| complete | Explicit judgment + unresolved questions + precise references |
| reopen | Same question/hypotheses/decisions without automatic inference |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-29와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## REOPEN-WORKBENCH — Reopen Connection view / saved refs

편집 원본: `screens/REOPEN-WORKBENCH.svg` · 미리보기: `screens/REOPEN-WORKBENCH.png` · owner: **Saved Connection view / saved refs**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-31: saved exact ownerrefs와 graphlayout. → 같은 connectionview를 열고 실제Study/Evaluationowner로 이동한다. 저장이 source문서를 수정하지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open saved editor | navigate / Open saved editor | WB-LINKS |
| Open linked Study | navigate / Open linked Study | STUDY-DECISION |
| Repair / inspect dependencies | navigate / Repair / inspect dependencies | WB-LINKS |
| Document chooser | navigate / Document chooser | HOME-EMPTY |
| Continue editing the same owner | navigate / Continue editing the same owner | WB-LINKS |
| Open linked Study | navigate / Open linked Study | STUDY-DECISION |
| Review saved links | navigate / Review saved links | WB-LINKS |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open or create the relevant owner record |
| edit | Use typed fields / contextual actions |
| dirty | Preserve owner draft / exact refs |
| running | No automatic activity in this board; observe external job separately |
| fail | Open diagnostic, save draft and retain evidence |
| cancel | Cancel preview / keep previous owner content |
| complete | Save exact record / explicit next tool |
| reopen | Restore saved refs / no hidden execution |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-31와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## REPORT-REVIEW — Evidence report / release status

편집 원본: `screens/REPORT-REVIEW.svg` · 미리보기: `screens/REPORT-REVIEW.png` · owner: **Host / record / evidence owner**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-08: 양호/불량 tangent 비교와 원 law·빌드·settings·reference. → 검토 결과를 보존하고 FE material 할당에는 별도의 solver interface 지원 검사를 요청한다.
- FN-16: 원 input·energy balance·mesh/time-step sensitivity·물리 시험 비교 여부. → 결과와 한계를 저장하고 physical validation 미제공이면 UNKNOWN을 남긴다.
- FN-32: 선택 입력/결과/evidence·source revisions·표/곡선/그림·judgment. → 보고서에 포함할 근거와 범위를 선택하고 data provenance를 확인한다.
- FN-32: program/solver 종료·numerical validity·engineering check별 상태. → UNKNOWN/NOT_RELEASED와 실패값을 유지한다. 검증 기준이 없는 항목에 PASS를 자동 부여하지 않는다.
- FN-32: 보고서 미리보기와 데이터/그림 export 범위. → Markdown/지원 PDF·CSV/PNG 등 무료 출력으로 내보내고 native·raw refs를 함께 보관한다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Report title | text / 해당 없음 | Stiffness study / review draft | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Output location | reference / 해당 없음 | user selected / registered folder | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open… | navigate / Open… | HOME-EMPTY |
| Recent documents | navigate / Recent documents | RECOVERY-REOPEN |
| Capabilities | navigate / Capabilities | SETUP-CAPABILITY |
| Study | navigate / Study | STUDY-EMPTY |
| Help / evidence | navigate / Help / evidence | REPORT-REVIEW |
| Open selected exact evidence | navigate / Open selected exact evidence | MAT-FIT-PARTIAL |
| Inspect prior decision | navigate / Inspect prior decision | STUDY-DECISION |
| Export report draft | navigate / Export report draft | REOPEN-REPORT |
| Keep draft and return to Study | navigate / Keep draft and return to Study | STUDY-DECISION |
| Inspect dependency availability | navigate / Inspect dependency availability | POST-REPAIR |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open or create the relevant owner record |
| edit | Use typed fields / contextual actions |
| dirty | Preserve owner draft / exact refs |
| running | No automatic activity in this board; observe external job separately |
| fail | Open diagnostic, save draft and retain evidence |
| cancel | Cancel preview / keep previous owner content |
| complete | Save exact record / explicit next tool |
| reopen | Restore saved refs / no hidden execution |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-08, FN-16, FN-32와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## RUN-ACTIVE — Attempt monitor

편집 원본: `screens/RUN-ACTIVE.svg` · 미리보기: `screens/RUN-ACTIVE.png` · owner: **Existing JobManager / attempt records**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-14: frozen contact sets와 step, iteration/cutback·contact search 로그. → 실행·취소·실패를 Runner에서 추적한다. 실패는 source contact/normal/step 설정으로 돌아가 새 run을 만든다.
- FN-15: physical time/load factor·iteration·residual/cutbacks, wall time 별도. → 현재 수렴 곡선과 진단을 읽는다. 수치 정책 수정은 새 입력/run이며 같은 attempt retry가 아니다.
- FN-16: physical time·minimum timestep·added mass·kinetic/internal/contact/hourglass energy. → actual solver logs를 추적하고 중단/불안정 원인을 확인한다.
- FN-21: 세대·평가수·best feasible·실패·실제 child attempts. → 진행을 관찰하고 필요 시 전체 취소한다. 모든 후보가 infeasible이면 그 사유를 유지한다.
- FN-25: job/input/backend/host/state/attempt/elapsed/result 목록과 selected attempt 탭. → job 행을 선택해 frozen input·logs·convergence·result/원 문서로 이동한다.
- FN-25: failed attempt 입력 hash와 수정 필요 위치. → 인프라 retry는 같은 입력 새 attempt; 수치/물리 설정 변경은 새 run/input이다.
- FN-35: 실험 attempt·실제 장비 state·수집 phase·stop/ack 여부. → 수집·중지·장비 종료 확인을 기록한다. solver job cancel을 hardware emergency stop으로 대신하지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Refresh status | navigate / Refresh status | RUN-ACTIVE |
| Submit prepared | navigate / Submit prepared | RUN-ACTIVE |
| Cancel selected… | navigate / Cancel selected… | RUN-CANCEL |
| Open input | navigate / Open input | MAT-DIRTY |
| Open result | navigate / Open result | MAT-FIT-PARTIAL |
| Locations | navigate / Locations | RUN-REMOTE-CONFIG |
| Native command monitor / exact target | navigate / Native command monitor / exact target | PRE-MESH-QUALITY |
| Open original log file | navigate / Open original log file | REPORT-REVIEW |
| Failed input / diagnostics | navigate / Failed input / diagnostics | SIM-IMPLICIT |
| Retry same input / new attempt | navigate / Retry same input / new attempt | RUN-ACTIVE |
| Reconnect and read same remote ID | navigate / Reconnect and read same remote ID | RUN-ACTIVE |
| Inspect transferred / partial artifacts | navigate / Inspect transferred / partial artifacts | NUM-BATCH |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open prepared run or retained history; no CAD required |
| edit | Host/resources only, physics owned by domain |
| dirty | Location/resource draft saves separately from frozen run |
| running | Attempt identity, observed time, actual phase / log |
| fail | New retry attempt or changed input; preserve failed records |
| cancel | Requested versus observed terminal; whole run / child distinction |
| complete | Exact result + frozen input navigation |
| reopen | Reconcile retained attempts, mark interrupted/termination unknown honestly |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-14, FN-15, FN-16, FN-21, FN-25, FN-35와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## RUN-CANCEL — Cancellation / actual termination

편집 원본: `screens/RUN-CANCEL.svg` · 미리보기: `screens/RUN-CANCEL.png` · owner: **Existing JobManager / attempt records**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-19: 전체 evaluation 취소 범위·진행 child/command·cleanup. → 후속 stage/iteration을 멈추고 actual terminal을 확인한다. 늦은 결과는 보존하며 실행을 재개하지 않는다.
- FN-25: 선택 job 취소 vs 전체 Plan/Evaluation 취소, actual children/cleanup·지원 여부. → 범위에 맞게 취소한다. CANCEL_REQUESTED는 terminal과 다르고 창을 닫아도 job은 취소하지 않는다.
- FN-34: command_id vs job_id·queued/running/applied/result unconfirmed. → 응답 유실 시 동일 ID status 조회; 같은 ID 다른 payload는 거절한다. 옛 session mutation은 거절한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Refresh status | navigate / Refresh status | RUN-ACTIVE |
| Submit prepared | navigate / Submit prepared | RUN-ACTIVE |
| Cancel selected… | navigate / Cancel selected… | RUN-CANCEL |
| Open input | navigate / Open input | MAT-DIRTY |
| Open result | navigate / Open result | MAT-FIT-PARTIAL |
| Locations | navigate / Locations | RUN-REMOTE-CONFIG |
| Native command monitor / exact target | navigate / Native command monitor / exact target | PRE-MESH-QUALITY |
| Wait / refresh actual state | navigate / Wait / refresh actual state | RUN-ACTIVE |
| Open partial results | navigate / Open partial results | MAT-FIT-PARTIAL |
| Close window separately… | navigate / Close window separately… | CLOSE-DIRTY |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open prepared run or retained history; no CAD required |
| edit | Host/resources only, physics owned by domain |
| dirty | Location/resource draft saves separately from frozen run |
| running | Attempt identity, observed time, actual phase / log |
| fail | New retry attempt or changed input; preserve failed records |
| cancel | Requested versus observed terminal; whole run / child distinction |
| complete | Exact result + frozen input navigation |
| reopen | Reconcile retained attempts, mark interrupted/termination unknown honestly |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-19, FN-25, FN-34와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## RUN-CANCEL-CONTACT — Contact attempt / cancellation

편집 원본: `screens/RUN-CANCEL-CONTACT.svg` · 미리보기: `screens/RUN-CANCEL-CONTACT.png` · owner: **JobManager / contact-031 attempt02**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-14: 선택 기능의 job/attempt/frozen input/result, cancel scope와 실제 종료 관측. → 정확한 source editor/result를 연다. 취소 요청은 새 제출을 멈추며 terminal이 확인될 때까지 현재 실행을 보존한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open exact input | navigate / Open exact input | PRE-CONTACT-READY |
| Refresh same attempt | navigate / Refresh same attempt | RUN-CONTACT |
| Cancel selected… | navigate / Cancel selected… | RUN-CANCEL-CONTACT |
| Save / reopen record | navigate / Save / reopen record | REOPEN-CONTACT |
| Simulate completed contact result | navigate / Simulate completed contact result | POST-CONTACT |
| Open retained inputs / same owner | navigate / Open retained inputs / same owner | PRE-CONTACT-READY |
| Read actual terminal status | navigate / Read actual terminal status | RUN-CONTACT |
| Preserve record / reopen exact context | navigate / Preserve record / reopen exact context | REOPEN-CONTACT |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open prepared run or retained history; no CAD required |
| edit | Host/resources only, physics owned by domain |
| dirty | Location/resource draft saves separately from frozen run |
| running | Attempt identity, observed time, actual phase / log |
| fail | New retry attempt or changed input; preserve failed records |
| cancel | Requested versus observed terminal; whole run / child distinction |
| complete | Exact result + frozen input navigation |
| reopen | Reconcile retained attempts, mark interrupted/termination unknown honestly |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-14와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## RUN-CANCEL-EVALUATION — Evaluation attempt / cancellation

편집 원본: `screens/RUN-CANCEL-EVALUATION.svg` · 미리보기: `screens/RUN-CANCEL-EVALUATION.png` · owner: **JobManager / eval-019 attempt02**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-19: 선택 기능의 job/attempt/frozen input/result, cancel scope와 실제 종료 관측. → 정확한 source editor/result를 연다. 취소 요청은 새 제출을 멈추며 terminal이 확인될 때까지 현재 실행을 보존한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open exact input | navigate / Open exact input | EVAL-STAGES |
| Refresh same attempt | navigate / Refresh same attempt | RUN-EVALUATION |
| Cancel selected… | navigate / Cancel selected… | RUN-CANCEL-EVALUATION |
| Save / reopen record | navigate / Save / reopen record | REOPEN-EVALUATION |
| Simulate NOT_CONVERGED result | navigate / Simulate NOT_CONVERGED result | EVAL-NONCONVERGED |
| Open retained inputs / same owner | navigate / Open retained inputs / same owner | EVAL-STAGES |
| Read actual terminal status | navigate / Read actual terminal status | RUN-EVALUATION |
| Preserve record / reopen exact context | navigate / Preserve record / reopen exact context | REOPEN-EVALUATION |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open prepared run or retained history; no CAD required |
| edit | Host/resources only, physics owned by domain |
| dirty | Location/resource draft saves separately from frozen run |
| running | Attempt identity, observed time, actual phase / log |
| fail | New retry attempt or changed input; preserve failed records |
| cancel | Requested versus observed terminal; whole run / child distinction |
| complete | Exact result + frozen input navigation |
| reopen | Reconcile retained attempts, mark interrupted/termination unknown honestly |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-19와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## RUN-CONTACT — Contact attempt / frozen input

편집 원본: `screens/RUN-CONTACT.svg` · 미리보기: `screens/RUN-CONTACT.png` · owner: **JobManager / contact-031 attempt02**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-14: 선택 기능의 job/attempt/frozen input/result, cancel scope와 실제 종료 관측. → 정확한 source editor/result를 연다. 취소 요청은 새 제출을 멈추며 terminal이 확인될 때까지 현재 실행을 보존한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open exact input | navigate / Open exact input | PRE-CONTACT-READY |
| Refresh same attempt | navigate / Refresh same attempt | RUN-CONTACT |
| Cancel selected… | navigate / Cancel selected… | RUN-CANCEL-CONTACT |
| Save / reopen record | navigate / Save / reopen record | REOPEN-CONTACT |
| Simulate completed contact result | navigate / Simulate completed contact result | POST-CONTACT |
| Open retained inputs / same owner | navigate / Open retained inputs / same owner | PRE-CONTACT-READY |
| Request cancellation of this attempt | navigate / Request cancellation of this attempt | RUN-CANCEL-CONTACT |
| Preserve record / reopen exact context | navigate / Preserve record / reopen exact context | REOPEN-CONTACT |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open prepared run or retained history; no CAD required |
| edit | Host/resources only, physics owned by domain |
| dirty | Location/resource draft saves separately from frozen run |
| running | Attempt identity, observed time, actual phase / log |
| fail | New retry attempt or changed input; preserve failed records |
| cancel | Requested versus observed terminal; whole run / child distinction |
| complete | Exact result + frozen input navigation |
| reopen | Reconcile retained attempts, mark interrupted/termination unknown honestly |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-14와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## RUN-EVALUATION — Evaluation attempt / frozen input

편집 원본: `screens/RUN-EVALUATION.svg` · 미리보기: `screens/RUN-EVALUATION.png` · owner: **JobManager / eval-019 attempt02**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-19: 선택 기능의 job/attempt/frozen input/result, cancel scope와 실제 종료 관측. → 정확한 source editor/result를 연다. 취소 요청은 새 제출을 멈추며 terminal이 확인될 때까지 현재 실행을 보존한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open exact input | navigate / Open exact input | EVAL-STAGES |
| Refresh same attempt | navigate / Refresh same attempt | RUN-EVALUATION |
| Cancel selected… | navigate / Cancel selected… | RUN-CANCEL-EVALUATION |
| Save / reopen record | navigate / Save / reopen record | REOPEN-EVALUATION |
| Simulate NOT_CONVERGED result | navigate / Simulate NOT_CONVERGED result | EVAL-NONCONVERGED |
| Open retained inputs / same owner | navigate / Open retained inputs / same owner | EVAL-STAGES |
| Request cancellation of this attempt | navigate / Request cancellation of this attempt | RUN-CANCEL-EVALUATION |
| Preserve record / reopen exact context | navigate / Preserve record / reopen exact context | REOPEN-EVALUATION |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open prepared run or retained history; no CAD required |
| edit | Host/resources only, physics owned by domain |
| dirty | Location/resource draft saves separately from frozen run |
| running | Attempt identity, observed time, actual phase / log |
| fail | New retry attempt or changed input; preserve failed records |
| cancel | Requested versus observed terminal; whole run / child distinction |
| complete | Exact result + frozen input navigation |
| reopen | Reconcile retained attempts, mark interrupted/termination unknown honestly |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-19와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## RUN-NUM-BATCH — batch-021 / attempt03

편집 원본: `screens/RUN-NUM-BATCH.svg` · 미리보기: `screens/RUN-NUM-BATCH.png` · owner: **N-Batch/r2**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-26: 해당 named Plan/job/attempt와 새 confirmation 범위. → 명시 새 evaluation/attempt만 만들고 이전 예측/실패/요약을 덮어쓰지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open method | navigate / Open method | NUM-BATCH |
| Open selected case | navigate / Open selected case | NUM-CASE-BATCH |
| Locations | navigate / Locations | RUN-REMOTE-CONFIG |
| Preserve / reopen | navigate / Preserve / reopen | REOPEN-NUM-BATCH |
| Return to retained method results | navigate / Return to retained method results | NUM-BATCH |
| Inspect exact case / available artifacts | navigate / Inspect exact case / available artifacts | NUM-CASE-BATCH |
| Inspect same execution / no new ID | navigate / Inspect same execution / no new ID | RUN-NUM-BATCH |
| Keep record and close / reopen | navigate / Keep record and close / reopen | REOPEN-NUM-BATCH |
| Inspect external batch alternative | navigate / Inspect external batch alternative | NUM-BATCH |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open prepared run or retained history; no CAD required |
| edit | Host/resources only, physics owned by domain |
| dirty | Location/resource draft saves separately from frozen run |
| running | Attempt identity, observed time, actual phase / log |
| fail | New retry attempt or changed input; preserve failed records |
| cancel | Requested versus observed terminal; whole run / child distinction |
| complete | Exact result + frozen input navigation |
| reopen | Reconcile retained attempts, mark interrupted/termination unknown honestly |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-26와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## RUN-NUM-DOE — doe-025 / attempt03

편집 원본: `screens/RUN-NUM-DOE.svg` · 미리보기: `screens/RUN-NUM-DOE.png` · owner: **N-DOE/r3**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-20: 해당 named Plan/job/attempt와 새 confirmation 범위. → 명시 새 evaluation/attempt만 만들고 이전 예측/실패/요약을 덮어쓰지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open method | navigate / Open method | NUM-DOE |
| Open selected case | navigate / Open selected case | NUM-CASE-DOE |
| Locations | navigate / Locations | RUN-REMOTE-CONFIG |
| Preserve / reopen | navigate / Preserve / reopen | REOPEN-NUM-DOE |
| Return to retained method results | navigate / Return to retained method results | NUM-DOE |
| Inspect exact case / available artifacts | navigate / Inspect exact case / available artifacts | NUM-CASE-DOE |
| Inspect same execution / no new ID | navigate / Inspect same execution / no new ID | RUN-NUM-DOE |
| Keep record and close / reopen | navigate / Keep record and close / reopen | REOPEN-NUM-DOE |
| Inspect external batch alternative | navigate / Inspect external batch alternative | NUM-BATCH |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open prepared run or retained history; no CAD required |
| edit | Host/resources only, physics owned by domain |
| dirty | Location/resource draft saves separately from frozen run |
| running | Attempt identity, observed time, actual phase / log |
| fail | New retry attempt or changed input; preserve failed records |
| cancel | Requested versus observed terminal; whole run / child distinction |
| complete | Exact result + frozen input navigation |
| reopen | Reconcile retained attempts, mark interrupted/termination unknown honestly |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-20와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## RUN-NUM-MOO — moo-029 / attempt03

편집 원본: `screens/RUN-NUM-MOO.svg` · 미리보기: `screens/RUN-NUM-MOO.png` · owner: **N-MOO/r4**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-24: 해당 named Plan/job/attempt와 새 confirmation 범위. → 명시 새 evaluation/attempt만 만들고 이전 예측/실패/요약을 덮어쓰지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open method | navigate / Open method | NUM-MOO |
| Open selected case | navigate / Open selected case | NUM-CASE-MOO |
| Locations | navigate / Locations | RUN-REMOTE-CONFIG |
| Preserve / reopen | navigate / Preserve / reopen | REOPEN-NUM-MOO |
| Return to retained method results | navigate / Return to retained method results | NUM-MOO |
| Inspect exact case / available artifacts | navigate / Inspect exact case / available artifacts | NUM-CASE-MOO |
| Inspect same execution / no new ID | navigate / Inspect same execution / no new ID | RUN-NUM-MOO |
| Keep record and close / reopen | navigate / Keep record and close / reopen | REOPEN-NUM-MOO |
| Inspect external batch alternative | navigate / Inspect external batch alternative | NUM-BATCH |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open prepared run or retained history; no CAD required |
| edit | Host/resources only, physics owned by domain |
| dirty | Location/resource draft saves separately from frozen run |
| running | Attempt identity, observed time, actual phase / log |
| fail | New retry attempt or changed input; preserve failed records |
| cancel | Requested versus observed terminal; whole run / child distinction |
| complete | Exact result + frozen input navigation |
| reopen | Reconcile retained attempts, mark interrupted/termination unknown honestly |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-24와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## RUN-NUM-SENSITIVITY — sobol-026 / attempt03

편집 원본: `screens/RUN-NUM-SENSITIVITY.svg` · 미리보기: `screens/RUN-NUM-SENSITIVITY.png` · owner: **N-Sobol/r2**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-20: 해당 named Plan/job/attempt와 새 confirmation 범위. → 명시 새 evaluation/attempt만 만들고 이전 예측/실패/요약을 덮어쓰지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open method | navigate / Open method | NUM-SENSITIVITY |
| Open selected case | navigate / Open selected case | NUM-CASE-SENSITIVITY |
| Locations | navigate / Locations | RUN-REMOTE-CONFIG |
| Preserve / reopen | navigate / Preserve / reopen | REOPEN-NUM-SENSITIVITY |
| Return to retained method results | navigate / Return to retained method results | NUM-SENSITIVITY |
| Inspect exact case / available artifacts | navigate / Inspect exact case / available artifacts | NUM-CASE-SENSITIVITY |
| Inspect same execution / no new ID | navigate / Inspect same execution / no new ID | RUN-NUM-SENSITIVITY |
| Keep record and close / reopen | navigate / Keep record and close / reopen | REOPEN-NUM-SENSITIVITY |
| Inspect external batch alternative | navigate / Inspect external batch alternative | NUM-BATCH |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open prepared run or retained history; no CAD required |
| edit | Host/resources only, physics owned by domain |
| dirty | Location/resource draft saves separately from frozen run |
| running | Attempt identity, observed time, actual phase / log |
| fail | New retry attempt or changed input; preserve failed records |
| cancel | Requested versus observed terminal; whole run / child distinction |
| complete | Exact result + frozen input navigation |
| reopen | Reconcile retained attempts, mark interrupted/termination unknown honestly |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-20와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## RUN-NUM-SURROGATE — confirm-028 / attempt03

편집 원본: `screens/RUN-NUM-SURROGATE.svg` · 미리보기: `screens/RUN-NUM-SURROGATE.png` · owner: **N-RBF/r4**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-23: 해당 named Plan/job/attempt와 새 confirmation 범위. → 명시 새 evaluation/attempt만 만들고 이전 예측/실패/요약을 덮어쓰지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open method | navigate / Open method | NUM-SURROGATE |
| Open selected case | navigate / Open selected case | NUM-CASE-SURROGATE |
| Locations | navigate / Locations | RUN-REMOTE-CONFIG |
| Preserve / reopen | navigate / Preserve / reopen | REOPEN-NUM-SURROGATE |
| Return to retained method results | navigate / Return to retained method results | NUM-SURROGATE |
| Inspect exact case / available artifacts | navigate / Inspect exact case / available artifacts | NUM-CASE-SURROGATE |
| Inspect same execution / no new ID | navigate / Inspect same execution / no new ID | RUN-NUM-SURROGATE |
| Keep record and close / reopen | navigate / Keep record and close / reopen | REOPEN-NUM-SURROGATE |
| Inspect external batch alternative | navigate / Inspect external batch alternative | NUM-BATCH |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open prepared run or retained history; no CAD required |
| edit | Host/resources only, physics owned by domain |
| dirty | Location/resource draft saves separately from frozen run |
| running | Attempt identity, observed time, actual phase / log |
| fail | New retry attempt or changed input; preserve failed records |
| cancel | Requested versus observed terminal; whole run / child distinction |
| complete | Exact result + frozen input navigation |
| reopen | Reconcile retained attempts, mark interrupted/termination unknown honestly |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-23와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## RUN-NUM-UQ — uq-027 / attempt03

편집 원본: `screens/RUN-NUM-UQ.svg` · 미리보기: `screens/RUN-NUM-UQ.png` · owner: **N-UQ/r2**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-22: 해당 named Plan/job/attempt와 새 confirmation 범위. → 명시 새 evaluation/attempt만 만들고 이전 예측/실패/요약을 덮어쓰지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open method | navigate / Open method | NUM-UQ |
| Open selected case | navigate / Open selected case | NUM-CASE-UQ |
| Locations | navigate / Locations | RUN-REMOTE-CONFIG |
| Preserve / reopen | navigate / Preserve / reopen | REOPEN-NUM-UQ |
| Return to retained method results | navigate / Return to retained method results | NUM-UQ |
| Inspect exact case / available artifacts | navigate / Inspect exact case / available artifacts | NUM-CASE-UQ |
| Inspect same execution / no new ID | navigate / Inspect same execution / no new ID | RUN-NUM-UQ |
| Keep record and close / reopen | navigate / Keep record and close / reopen | REOPEN-NUM-UQ |
| Inspect external batch alternative | navigate / Inspect external batch alternative | NUM-BATCH |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open prepared run or retained history; no CAD required |
| edit | Host/resources only, physics owned by domain |
| dirty | Location/resource draft saves separately from frozen run |
| running | Attempt identity, observed time, actual phase / log |
| fail | New retry attempt or changed input; preserve failed records |
| cancel | Requested versus observed terminal; whole run / child distinction |
| complete | Exact result + frozen input navigation |
| reopen | Reconcile retained attempts, mark interrupted/termination unknown honestly |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-22와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## RUN-REMOTE-CONFIG — Remote batch-021 / attempt03

편집 원본: `screens/RUN-REMOTE-CONFIG.svg` · 미리보기: `screens/RUN-REMOTE-CONFIG.png` · owner: **Runner / N-Batch/r2 / exchange ex-2026-10-12-04**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-26: local/외부파일/SSH/Slurm/PBS 경로·등록 환경·명시 probe·resource limits. → 사용할 실행 위치와 queue/resource를 고른다. 실제 지원·권한이 없으면 draft를 저장한다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Host alias | text / 해당 없음 | existing-lab-node | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Transport | enum / 해당 없음 | SSH / Slurm or PBS extension | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Credential reference | reference / 해당 없음 | OS-managed alias only | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Queue / allocation | text / 해당 없음 | research / existing allocation | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Allowed work root | reference / 해당 없음 | registered root / unique attempt | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| CPUs | integer / 해당 없음 | 8 | 미지정; sample을 기본값으로 쓰지 않음 / ≥1 | 선택 owner / 대상 |
| Memory | number / GiB | 16 | 미지정; sample을 기본값으로 쓰지 않음 / >0 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open batch input | navigate / Open batch input | NUM-BATCH |
| Locations | navigate / Locations | RUN-REMOTE-CONFIG |
| Read same remote ID | navigate / Read same remote ID | RUN-REMOTE-LOST |
| Keep record / reopen | navigate / Keep record / reopen | REOPEN-NUM-BATCH |
| Probe selected location (explicit) | navigate / Probe selected location (explicit) | SETUP-CAPABILITY |
| Use file batch exchange instead | navigate / Use file batch exchange instead | NUM-BATCH |
| Inspect reconnect / result staging scenario | navigate / Inspect reconnect / result staging scenario | RUN-REMOTE-LOST |
| Save resource draft / preserve attempt | navigate / Save resource draft / preserve attempt | REOPEN-NUM-BATCH |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open prepared run or retained history; no CAD required |
| edit | Host/resources only, physics owned by domain |
| dirty | Location/resource draft saves separately from frozen run |
| running | Attempt identity, observed time, actual phase / log |
| fail | New retry attempt or changed input; preserve failed records |
| cancel | Requested versus observed terminal; whole run / child distinction |
| complete | Exact result + frozen input navigation |
| reopen | Reconcile retained attempts, mark interrupted/termination unknown honestly |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-26와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## RUN-REMOTE-LOST — Remote batch-021 / attempt03

편집 원본: `screens/RUN-REMOTE-LOST.svg` · 미리보기: `screens/RUN-REMOTE-LOST.png` · owner: **Runner / N-Batch/r2 / exchange ex-2026-10-12-04**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-25: 마지막 관측 시각·service restart/INTERRUPTED·process 종료 확인 유무. → 상태 재조회·연결 복구·원파일 로그 확인을 한다. 동일 작업 폴더에 자동 중복 실행하지 않는다.
- FN-26: transfer checksum·scheduler job ID·last seen·원격 workdir/exit 확인. → 연결이 끊기면 재조회/로그·결과 회수를 재개한다. 같은 job을 다시 submit하지 않는다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Host alias | text / 해당 없음 | existing-lab-node | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Transport | enum / 해당 없음 | SSH / Slurm or PBS extension | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Credential reference | reference / 해당 없음 | OS-managed alias only | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Queue / allocation | text / 해당 없음 | research / existing allocation | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Allowed work root | reference / 해당 없음 | registered root / unique attempt | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| CPUs | integer / 해당 없음 | 8 | 미지정; sample을 기본값으로 쓰지 않음 / ≥1 | 선택 owner / 대상 |
| Memory | number / GiB | 16 | 미지정; sample을 기본값으로 쓰지 않음 / >0 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open batch input | navigate / Open batch input | NUM-BATCH |
| Locations | navigate / Locations | RUN-REMOTE-CONFIG |
| Read same remote ID | navigate / Read same remote ID | RUN-REMOTE-LOST |
| Keep record / reopen | navigate / Keep record / reopen | REOPEN-NUM-BATCH |
| Probe selected location (explicit) | navigate / Probe selected location (explicit) | SETUP-CAPABILITY |
| Use file batch exchange instead | navigate / Use file batch exchange instead | NUM-BATCH |
| Reconnect / read scheduler84271 | navigate / Reconnect / read scheduler84271 | RUN-REMOTE-LOST |
| Inspect transferred / partial artifacts | navigate / Inspect transferred / partial artifacts | NUM-BATCH |
| Keep original attempt / reopen | navigate / Keep original attempt / reopen | REOPEN-NUM-BATCH |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open prepared run or retained history; no CAD required |
| edit | Host/resources only, physics owned by domain |
| dirty | Location/resource draft saves separately from frozen run |
| running | Attempt identity, observed time, actual phase / log |
| fail | New retry attempt or changed input; preserve failed records |
| cancel | Requested versus observed terminal; whole run / child distinction |
| complete | Exact result + frozen input navigation |
| reopen | Reconcile retained attempts, mark interrupted/termination unknown honestly |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-25, FN-26와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## SAVE-PARTIAL — Some documents were saved

편집 원본: `screens/SAVE-PARTIAL.svg` · 미리보기: `screens/SAVE-PARTIAL.png` · owner: **Material + Numerical Plan**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-02: Material r18 저장 성공, Plan r8→draft 저장 실패, 아직 갱신하지 않은 연결. → 실패 파일·경로를 수정하고 Plan만 다시 저장한다. 성공한 Material r18을 되돌리거나 전체 성공 알림을 내지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Retry Plan only | navigate / Retry Plan only | RECOVERY-REOPEN |
| Save Plan branch elsewhere… | navigate / Save Plan branch elsewhere… | RECOVERY-REOPEN |
| Keep working / both owners | navigate / Keep working / both owners | MAT-DIRTY |
| Review source r17 → r18 | navigate / Review source r17 → r18 | CLIENT-CONFLICT |
| Close with recovery choices… | navigate / Close with recovery choices… | CLOSE-DIRTY |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | New law/protocol or import observation |
| edit | Material value and embedded Plan bound have different Undo owners |
| dirty | Per-owner save/source refresh/Plan starting values explicit |
| running | Frozen input; current draft can diverge; old/late result linked correctly |
| fail | Failed candidate/input diagnostics or save receipt; no made-up curve |
| cancel | Stop submission separately from job terminal and window close |
| complete | Retained details/holdout → explicit owner adoption → save |
| reopen | Open saved rN or separate recovery capsule; never evaluate on selection |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-02와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## SETUP-CAPABILITY — Registered capability / actual environment

편집 원본: `screens/SETUP-CAPABILITY.svg` · 미리보기: `screens/SETUP-CAPABILITY.png` · owner: **Host / record / evidence owner**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-33: 등록 capability·adapter 범위·runtime NOT_PROBED·실제 check receipt가 별도 열. → 사용할 backend만 ‘환경 확인’을 실행한다. 목록 조회 자체는 probe/설치하지 않는다.
- FN-33: 정확 path/build/version·필수 libraries·supported operation과 probe date. → 기존 executable을 선택하고 허용된 version/library check를 수행한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open… | navigate / Open… | HOME-EMPTY |
| Recent documents | navigate / Recent documents | RECOVERY-REOPEN |
| Capabilities | navigate / Capabilities | SETUP-CAPABILITY |
| Study | navigate / Study | STUDY-EMPTY |
| Help / evidence | navigate / Help / evidence | REPORT-REVIEW |
| Probe selected component | navigate / Probe selected component | SETUP-CAPABILITY |
| Open remote location settings | navigate / Open remote location settings | RUN-REMOTE-CONFIG |
| Keep working with saved data | navigate / Keep working with saved data | HOME-EMPTY |
| Open cost / license evidence record | navigate / Open cost / license evidence record | REPORT-REVIEW |
| Open saved work without running a probe | navigate / Open saved work without running a probe | RECOVERY-REOPEN |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open or create the relevant owner record |
| edit | Use typed fields / contextual actions |
| dirty | Preserve owner draft / exact refs |
| running | No automatic activity in this board; observe external job separately |
| fail | Open diagnostic, save draft and retain evidence |
| cancel | Cancel preview / keep previous owner content |
| complete | Save exact record / explicit next tool |
| reopen | Restore saved refs / no hidden execution |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-33와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## SIM-EXPLICIT — Explicit impact / drop

편집 원본: `screens/SIM-EXPLICIT.svg` · 미리보기: `screens/SIM-EXPLICIT.png` · owner: **Simulation V-03 + native or external input**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-16: body/rigid/material/contact·floor normal, COM·orientation·drop height/velocity. → height+gravity로 계산한 이상화 speed 또는 측정된 pre-impact v/ω 중 입력 모드를 명시한다. 두 모드를 몰래 중복 적용하지 않는다.
- FN-16: end time·time step/CFL·mass scaling·contact/failure output request. → 단위계와 control을 정하고 미지원 card/connector/composite를 preflight한다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Backend | enum / 해당 없음 | OpenRadioss (exact build pending) | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Initial velocity | vector / 해당 없음 | vY = −2.0 m/s | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Duration / output interval | time / 해당 없음 | .050 s / .001 s | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Mass scaling | enum / 해당 없음 | OFF / disclose added mass | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open input | navigate / Open input | SIM-IMPLICIT |
| Save draft | navigate / Save draft | REOPEN-SIMULATION |
| Implicit | navigate / Implicit | SIM-IMPLICIT |
| Explicit | navigate / Explicit | SIM-EXPLICIT |
| Failure / interface | navigate / Failure / interface | SIM-FAILURE |
| Preflight | navigate / Preflight | SETUP-CAPABILITY |
| Submit blocked | navigate / Submit blocked | SETUP-CAPABILITY |
| Inspect capabilities / runtime | navigate / Inspect capabilities / runtime | SETUP-CAPABILITY |
| Open contact / surface definition | navigate / Open contact / surface definition | PRE-CONTACT |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open or create the relevant owner record |
| edit | Use typed fields / contextual actions |
| dirty | Preserve owner draft / exact refs |
| running | No automatic activity in this board; observe external job separately |
| fail | Open diagnostic, save draft and retain evidence |
| cancel | Cancel preview / keep previous owner content |
| complete | Save exact record / explicit next tool |
| reopen | Restore saved refs / no hidden execution |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-16와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## SIM-FAILURE — Failure / cohesive interface

편집 원본: `screens/SIM-FAILURE.svg` · 미리보기: `screens/SIM-FAILURE.png` · owner: **Simulation V-03 + native or external input**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-17: bulk/interface law tree·traction–separation curve, opening/sliding directions. → 강성/강도/파괴에너지·mixed-mode·damage onset/evolution을 해당 domain에서 입력한다.
- FN-17: 압축 전달·재닫힘 contact·마찰·벌크 plasticity의 중복/누락 진단. → damage 후 압축 접촉 경로와 tied/cohesive/contact 경계를 검토한다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Interface law | enum / 해당 없음 | traction-separation / cohesive | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Mode I energy | number / 해당 없음 | 0.50 N/mm (fixture) | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Compression reclosure | enum / 해당 없음 | required capability | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Fatigue / durability | status / 해당 없음 | NOT_QUALIFIED | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open input | navigate / Open input | SIM-IMPLICIT |
| Save draft | navigate / Save draft | REOPEN-SIMULATION |
| Implicit | navigate / Implicit | SIM-IMPLICIT |
| Explicit | navigate / Explicit | SIM-EXPLICIT |
| Failure / interface | navigate / Failure / interface | SIM-FAILURE |
| Preflight | navigate / Preflight | SETUP-CAPABILITY |
| Submit blocked | navigate / Submit blocked | SETUP-CAPABILITY |
| Inspect capabilities / runtime | navigate / Inspect capabilities / runtime | SETUP-CAPABILITY |
| Open contact / surface definition | navigate / Open contact / surface definition | PRE-CONTACT |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open or create the relevant owner record |
| edit | Use typed fields / contextual actions |
| dirty | Preserve owner draft / exact refs |
| running | No automatic activity in this board; observe external job separately |
| fail | Open diagnostic, save draft and retain evidence |
| cancel | Cancel preview / keep previous owner content |
| complete | Save exact record / explicit next tool |
| reopen | Restore saved refs / no hidden execution |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-17와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## SIM-IMPLICIT — Nonlinear implicit

편집 원본: `screens/SIM-IMPLICIT.svg` · 미리보기: `screens/SIM-IMPLICIT.png` · owner: **Simulation V-03 + native or external input**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-09: 지원 카드 미리보기와 provenance, 필요한 material-point 또는 single-element 검증. → 입력 생성 후 해당 adapter gate를 통과한 snapshot만 실행한다. export된 파일과 원 Material을 저장한다.
- FN-12: 선택 solver의 입력 지원표, 할당 누락·중복·unsupported 조건. → preflight에서 문제 행으로 이동해 수정하고 유효 snapshot을 Runner로 보낸다.
- FN-15: model/mesh/material refs, nonlinear geometry·law·contact, step loading. → NLGEOM·load steps·initial state·time control을 source domain에서 편집한다.
- FN-15: increment min/initial/max, nonlinear tolerance·line search/solver·output frequency. → 물리적 의미와 단위가 있는 설정을 고르고 preflight한다. Runner 자원 설정과 섞지 않는다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Solver family | enum / 해당 없음 | Code_Aster candidate / CCX bounded | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Geometric nonlinearity | enum / 해당 없음 | finite / supported policy | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Initial / minimum increment | step_fraction / 해당 없음 | .01 / 1e-6 | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Convergence | enum / 해당 없음 | force + displacement norms | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open input | navigate / Open input | SIM-IMPLICIT |
| Save draft | navigate / Save draft | REOPEN-SIMULATION |
| Implicit | navigate / Implicit | SIM-IMPLICIT |
| Explicit | navigate / Explicit | SIM-EXPLICIT |
| Failure / interface | navigate / Failure / interface | SIM-FAILURE |
| Preflight | navigate / Preflight | SETUP-CAPABILITY |
| Submit blocked | navigate / Submit blocked | SETUP-CAPABILITY |
| Inspect capabilities / runtime | navigate / Inspect capabilities / runtime | SETUP-CAPABILITY |
| Open contact / surface definition | navigate / Open contact / surface definition | PRE-CONTACT |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open or create the relevant owner record |
| edit | Use typed fields / contextual actions |
| dirty | Preserve owner draft / exact refs |
| running | No automatic activity in this board; observe external job separately |
| fail | Open diagnostic, save draft and retain evidence |
| cancel | Cancel preview / keep previous owner content |
| complete | Save exact record / explicit next tool |
| reopen | Restore saved refs / no hidden execution |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-09, FN-12, FN-15와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## SIM-THERMAL — V-02/r4 / saved SI stage

편집 원본: `screens/SIM-THERMAL.svg` · 미리보기: `screens/SIM-THERMAL.png` · owner: **V-02/r4**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-19: 기존 bounded SI stage V-02r4/V-03r6, metre/P1/K, Tref와 actual transfer. → 같은 Simulation owner의 정확한 stage를 연다. 일반 nonlinear 예시나 dimensionless PDE를 thermal input으로 바꿔 표시하지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Same Evaluation | navigate / Same Evaluation | EVAL-STAGES |
| Transfer values | navigate / Transfer values | EVAL-TRANSFER |
| Run readiness | navigate / Run readiness | SETUP-CAPABILITY |
| Save / reopen | navigate / Save / reopen | REOPEN-SIMULATION |
| Open exact stage transfer | navigate / Open exact stage transfer | EVAL-TRANSFER |
| Back to same definition owner | navigate / Back to same definition owner | EVAL-STAGES |
| Inspect captured field fixture | navigate / Inspect captured field fixture | EVAL-TRANSFER |
| View retained NOT_CONVERGED UI example | navigate / View retained NOT_CONVERGED UI example | EVAL-NONCONVERGED |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open or create the relevant owner record |
| edit | Use typed fields / contextual actions |
| dirty | Preserve owner draft / exact refs |
| running | No automatic activity in this board; observe external job separately |
| fail | Open diagnostic, save draft and retain evidence |
| cancel | Cancel preview / keep previous owner content |
| complete | Save exact record / explicit next tool |
| reopen | Restore saved refs / no hidden execution |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-19와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## SIM-THERMOELASTIC — V-03/r6 / saved SI stage

편집 원본: `screens/SIM-THERMOELASTIC.svg` · 미리보기: `screens/SIM-THERMOELASTIC.png` · owner: **V-03/r6**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-19: 기존 bounded SI stage V-02r4/V-03r6, metre/P1/K, Tref와 actual transfer. → 같은 Simulation owner의 정확한 stage를 연다. 일반 nonlinear 예시나 dimensionless PDE를 thermal input으로 바꿔 표시하지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Same Evaluation | navigate / Same Evaluation | EVAL-STAGES |
| Transfer values | navigate / Transfer values | EVAL-TRANSFER |
| Run readiness | navigate / Run readiness | SETUP-CAPABILITY |
| Save / reopen | navigate / Save / reopen | REOPEN-SIMULATION |
| Open exact stage transfer | navigate / Open exact stage transfer | EVAL-TRANSFER |
| Back to same definition owner | navigate / Back to same definition owner | EVAL-STAGES |
| Inspect captured field fixture | navigate / Inspect captured field fixture | EVAL-TRANSFER |
| View retained NOT_CONVERGED UI example | navigate / View retained NOT_CONVERGED UI example | EVAL-NONCONVERGED |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open or create the relevant owner record |
| edit | Use typed fields / contextual actions |
| dirty | Preserve owner draft / exact refs |
| running | No automatic activity in this board; observe external job separately |
| fail | Open diagnostic, save draft and retain evidence |
| cancel | Cancel preview / keep previous owner content |
| complete | Save exact record / explicit next tool |
| reopen | Restore saved refs / no hidden execution |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-19와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## STUDY-DECISION — Why does measured stiffness differ?

편집 원본: `screens/STUDY-DECISION.svg` · 미리보기: `screens/STUDY-DECISION.png` · owner: **Existing Study S-02**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-05: 이전 모델·예측·새 관측, 지지/반박 근거와 미식별 항목. → 새 개정 채택 또는 보류, 구별력이 있는 후속 시험을 Study에 기록하고 저장한다.
- FN-17: 관측 박리/잔류변형·가설 지지/반박, fatigue 자료 유무. → 한 cycle 결과를 fatigue life로 쓰지 않고 별도 누적손상/시험 근거 요구를 남긴다.
- FN-22: 성공 표본에 조건부인 통계와 실패율, 기준 초과·불확실한 항목. → 가정·통계 한계를 포함해 근거를 Study에 연결하고 저장한다.
- FN-29: 가설별 supporting/contradicting/inconclusive evidence·source locator/revision. → 문서·result·Data 관측·문헌 또는 Expert turn을 연결하고 원근거를 연다.
- FN-29: 서로 충돌하는 evidence와 이전 판단, 입력 변경 영향. → 판단은 사용자 명시 편집으로 채택/보류/기각한다. 새 발언이나 fit rank가 자동으로 결정하지 않는다.
- FN-29: 다음 관측/experiment·관련 domain/Plan·책임·status. → ‘후속 연구 만들기’로 실제 편집 가능한 domain/Plan/Discussion을 열고 Study는 exact ref만 보관한다.
- FN-30: 실제 retained result를 읽은 후속 발언과 사용자가 채택할 판단. → Discussion 발언을 Study의 근거로 연결하되 Study 판단은 별도로 편집한다.
- FN-31: 채택된 연구 판단과 계산 계획의 별도 owner. → 원 editor에서 수정하고 돌아오면 같은 관계를 갱신한다.
- FN-35: 새 Data/교정 결과와 예측·모델 후보·다음 시험. → FN-05/21의 보정과 Study 판단을 이어 저장한다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Decision | text / 해당 없음 | Keep H1 and H2; alignment remains UNKNOWN | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Rationale / source selection | text / 해당 없음 | B holdout improves; fixture measurement still needed | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| New Study | navigate / New Study | STUDY-EMPTY |
| Save Study | navigate / Save Study | REOPEN-STUDY |
| Attach evidence | navigate / Attach evidence | STUDY-DECISION |
| Open selected source | navigate / Open selected source | MAT-FIT-PARTIAL |
| Discuss (optional) | navigate / Discuss (optional) | EXPERT-DRAFT |
| Report | navigate / Report | REPORT-REVIEW |
| Add competing hypothesis | navigate / Add competing hypothesis | STUDY-DECISION |
| Open Data / calibration | navigate / Open Data / calibration | DATA-CALIBRATION |
| Open holdout retained result | open_exact_reference / Retained result and its actual source revision | MAT-FIT-PARTIAL |
| Attach registered source | navigate / Attach registered source | STUDY-DECISION |
| Inspect selected evidence | navigate / Inspect selected evidence | MAT-FIT-PARTIAL |
| Save explicit research decision | navigate / Save explicit research decision | REOPEN-STUDY |
| Open previous decision revision | navigate / Open previous decision revision | STUDY-HISTORY |
| Create editable Plan proposal | navigate / Create editable Plan proposal | NUM-NEXT-TEST |
| Discuss evidence (optional) | navigate / Discuss evidence (optional) | EXPERT-DISCUSS |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Question/hypothesis first; no Plan/Expert prerequisite |
| edit | Explicit evidence relation / decision / next research |
| dirty | Study owns adopted judgments; Discussion stays separate |
| running | Study edit does not execute jobs; links may observe running result |
| fail | Reference/locator invalid: repair or save draft without evidence claim |
| cancel | Cancel evidence attachment or judgment leaves prior decision |
| complete | Explicit judgment + unresolved questions + precise references |
| reopen | Same question/hypotheses/decisions without automatic inference |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-05, FN-17, FN-22, FN-29, FN-30, FN-31, FN-35와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## STUDY-EMPTY — New research question

편집 원본: `screens/STUDY-EMPTY.svg` · 미리보기: `screens/STUDY-EMPTY.png` · owner: **Existing Study S-02**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-29: 연구 질문과 competing hypotheses 빈 목록, 자료 연결 위치. → 질문·가설·구별할 관측을 적는다. automatic discussion을 시작하지 않는다.

### 구체 입력

| 필드 | 형식 / unit | 시안값 | 기본값 / 허용범위 | 종속 조건 |
|---|---|---|---|---|
| Research question | text / 해당 없음 | Why does stiffness differ between experiment and model? | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| First hypothesis | text / 해당 없음 | The chosen constitutive law misses the observed response. | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |
| Evidence to inspect | reference / 해당 없음 | Optional saved Data / result / Expert turn | 미지정; sample을 기본값으로 쓰지 않음 / 선택 capability·문서 규칙 | 선택 owner / 대상 |

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| New Study | navigate / New Study | STUDY-EMPTY |
| Save Study | navigate / Save Study | REOPEN-STUDY |
| Attach evidence | navigate / Attach evidence | STUDY-DECISION |
| Open selected source | navigate / Open selected source | STUDY-DECISION |
| Discuss (optional) | navigate / Discuss (optional) | EXPERT-DRAFT |
| Report | navigate / Report | REPORT-REVIEW |
| Add competing hypothesis | navigate / Add competing hypothesis | STUDY-DECISION |
| Open Data / calibration | navigate / Open Data / calibration | DATA-CALIBRATION |
| Create hypothesis and inspect evidence | navigate / Create hypothesis and inspect evidence | STUDY-DECISION |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Question/hypothesis first; no Plan/Expert prerequisite |
| edit | Explicit evidence relation / decision / next research |
| dirty | Study owns adopted judgments; Discussion stays separate |
| running | Study edit does not execute jobs; links may observe running result |
| fail | Reference/locator invalid: repair or save draft without evidence claim |
| cancel | Cancel evidence attachment or judgment leaves prior decision |
| complete | Explicit judgment + unresolved questions + precise references |
| reopen | Same question/hypotheses/decisions without automatic inference |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-29와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## STUDY-HISTORY — Study S-02 / previous decision r2

편집 원본: `screens/STUDY-HISTORY.svg` · 미리보기: `screens/STUDY-HISTORY.png` · owner: **Study S-02 / immutable saved r2**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-29: 읽기전용 StudyS-02r2의 질문/판단/원 근거와 currentr3비교. → 과거판단을 읽고 현재r3로 돌아간다. 다른owner복구창을 열거나 현재판단을 자동rollback하지 않는다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Return to current r3 | navigate / Return to current r3 | STUDY-DECISION |
| Open saved current Study | navigate / Open saved current Study | REOPEN-STUDY |
| Inspect referenced fit | navigate / Inspect referenced fit | MAT-FIT-PARTIAL |
| Return to current Study without changing it | navigate / Return to current Study without changing it | STUDY-DECISION |
| Inspect the retained source attached to this decision | navigate / Inspect the retained source attached to this decision | MAT-FIT-PARTIAL |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Question/hypothesis first; no Plan/Expert prerequisite |
| edit | Explicit evidence relation / decision / next research |
| dirty | Study owns adopted judgments; Discussion stays separate |
| running | Study edit does not execute jobs; links may observe running result |
| fail | Reference/locator invalid: repair or save draft without evidence claim |
| cancel | Cancel evidence attachment or judgment leaves prior decision |
| complete | Explicit judgment + unresolved questions + precise references |
| reopen | Same question/hypotheses/decisions without automatic inference |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-29와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.


## WB-LINKS — Optional connection view

편집 원본: `screens/WB-LINKS.svg` · 미리보기: `screens/WB-LINKS.png` · owner: **Existing document links / Study view**. 화면 기준1440×900. 모든 표/값/곡선/3D는 합성 fixture.

### 화면에서 끝낼 작업

- FN-31: 문서·관계 목록과 optional graph, node kind·saved revision·stale/broken badges. → 한 번 클릭은 상세, 더블클릭은 정확한 owner/editor 또는 result를 연다.
- FN-31: 가능한 port/관계 종류와 전달할 exact revision. → drag 또는 ‘연결 추가’ 메뉴로 관계를 선택한다. Esc는 새 연결만 취소한다.
- FN-31: 새 revision 있음 vs 원 참조 깨짐, 영향받는 Plan/Study/result. → reference를 새 revision으로 바꾸기 전에 영향/필수 변환을 확인한다.

### 클릭·키보드·화면 전환

| 표시 조작 | 동작 / owner effect | 다음 state |
|---|---|---|
| Open owner | navigate / Open owner | STUDY-DECISION |
| List / graph | navigate / List / graph | WB-LINKS |
| Connect by menu | navigate / Connect by menu | WB-LINKS |
| Inspect revision | navigate / Inspect revision | CLIENT-CONFLICT |
| Save references | navigate / Save references | REOPEN-WORKBENCH |
| Open Material owner | navigate / Open Material owner | MAT-DIRTY |
| Open Evaluation owner | navigate / Open Evaluation owner | EVAL-STAGES |
| Open Data A / B · r4 | open_same_owner / Exact reference / editor; no copy | DATA-EDIT |
| Open Material · r17 | open_same_owner / Exact reference / editor; no copy | MAT-DIRTY |
| Open Plan · r8 | open_same_owner / Exact reference / editor; no copy | NUM-OPTIMIZE |
| Open Evaluation · r5 | open_same_owner / Exact reference / editor; no copy | EVAL-STAGES |
| Open Result c017 | open_same_owner / Exact reference / editor; no copy | MAT-FIT-PARTIAL |
| Open Study · r3 | open_same_owner / Exact reference / editor; no copy | STUDY-DECISION |
| Review source diff… | navigate / Review source diff… | CLIENT-CONFLICT |
| Keep exact r17 reference | navigate / Keep exact r17 reference | WB-LINKS |
| Disconnect link… | navigate / Disconnect link… | WB-LINKS |

### 상태별 다음 행동·저장/Undo

| 상태 | 조작·결과 |
|---|---|
| empty | Open or create the relevant owner record |
| edit | Use typed fields / contextual actions |
| dirty | Preserve owner draft / exact refs |
| running | No automatic activity in this board; observe external job separately |
| fail | Open diagnostic, save draft and retain evidence |
| cancel | Cancel preview / keep previous owner content |
| complete | Save exact record / explicit next tool |
| reopen | Restore saved refs / no hidden execution |

오류·취소·복구의 정확한 입력/output/현재 source·새 코드 연결은 FN-31와 FUNCTION_SPEC 상세 계약 C01–C09를 따른다. 이 board의 hotspot은 설계 전이이며 service/native 실행이 아니다.
