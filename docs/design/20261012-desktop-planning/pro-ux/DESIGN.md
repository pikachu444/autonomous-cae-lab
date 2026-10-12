# Desktop UX design — engineering work first

## 1. 결정과 범위

주 작업은 **형상을 만들고 조건을 주어 해석을 검토한 뒤, 결과에서 설계를 판단하는 것**이다. CAD/FE → Simulation → Runner → Post → Numerical을 첫 번째 완결 경로로 작성했다. Expert/Study는 독립적인 질문·논의·판단 경로다. Data/Material/PDE는 병행 연구 도구다. 어느 하나의 완료를 다른 모든 도구의 선행조건으로 두지 않는다.

한 종류의 공통 폼이나 시작 wizard를 전 도구에 사용하지 않는다. 공통인 것은 File/Edit/Window와 숫자 편집·Undo·기본 저장 동작이며, 각 도구의 중심 대상은 아래처럼 다르다.

| 도구 | 중심 대상과 배치 | 선택의 이유 |
|---|---|---|
| CAD / FE | Model/Tasks dock, 모드별 치수·선·joint·mesh·condition, 큰 3D | 형상과 선택 면을 보면서 값을 바꾸는 기존 FreeCAD 작업 구조 |
| Simulation | 해석 tree, 선택 node의 settings, 대상 geometry | solver와 물리 설정을 Runner 자원 설정과 혼합하지 않음 |
| Runner | 작업 표, 선택 작업의 input/log/diagnostics/result/monitor 탭 | 많은 작업 중 하나의 진행·실패·취소를 명확히 판단 |
| Post | Pipeline/Properties, Apply/Reset, 큰 RenderView, 하단 curve/measurement | field·filter·시간·측정 대상이 동시에 보이는 ParaView 작업 구조 |
| Numerical | 연구 tree, 변수/응답/방법/입력 표, 후보/분석/curve | HyperStudy식 연구 정의·표·선택 후보 비교; 방법별 입력과 판단은 구별 |
| Expert | 논점 지도, 다자 발언, evidence, 하단 사용자 입력 | Co-STORM의 개입 가능한 논의를 실제 조작 대상으로 유지 |
| Study | 경쟁 가설과 evidence 관계 표, 명시 judgment/reason/next research | 논의 요약과 연구 결론을 자동으로 동일시하지 않음 |
| Data | 열명·단위·역할·수식, 조밀한 workbook, 연결 curve | Origin형 데이터 작업에서 선택 ID와 곡선을 함께 다룸 |
| Material | 시험/계수 왼쪽, 관측·예측 curve 오른쪽, output 하단 | MCalibration형 direct/calibrate/holdout 비교 |
| PDE | Model Builder, field/equation/boundary settings, 같은 domain/mesh graphics | field·식·경계의 물리 대상을 설정과 연결 |
| Evaluation | 기존 단계 표, field transfer와 coupling 탭 | 기존 Evaluation owner로 다물리 전달과 반복을 표현 |
| Workbench | 선택적 document/port 연결도 | 정확한 owner를 여는 보기이며 별도 scheduler나 optimizer가 아님 |

검토에서 제외한 대안은 browser/localhost 폼, web dashboard 카드, 강제 Back/Next, 상태·도움말 띠의 반복, 각 도구마다 새 owner/wrapper를 만드는 구조다. Windows native Qt와 기존 FreeCAD/ParaView 작업 방식을 채택한 것은 사용자의 확정 방향이다. 추가 계정·비용·asset 복사·LS-OPT 설치는 없다. 사용자가 제공할 reference image도 요구하지 않는다.

## 2. 화면과 구현의 경계

`qt_prototype.py`의 각 창은 실제 Qt widget이다. 표 셀·선택·splitter·dock·메뉴·dialog·키보드와 파일 선택을 조작할 수 있다. `qt_widgets.py`의 도형·mesh·contour·curve는 공개 합성 예시의 QPainter illustration이다. `prototype_state.py`는 이 단일 시제품의 저장 가능한 검토 상태이며 **새 제품 Core나 engine이 아니다**. 제품 실행 command를 import하거나 호출하지 않는다.

`screen_states.json`은 같은 창의 상태를 재현한다. `screens/*.svg`는 QtSvg가 그 창을 렌더한 편집 벡터다. 원형 그림을 불러와 GUI처럼 보이게 붙인 파일이 아니다. `Workflows.drawio`는 도구 간 작업 흐름 원본이며 GUI를 대체하지 않는다. D1 전체 기능 명세/74개 backlog는 별도 pin에 있는 원본으로 계속 읽는다.

사용자 창에는 자연스러운 작업명·선택·값/단위·저장·진행·오류·다음 action을 둔다. revision/hash/attempt 관계는 필요한 source/history/diagnostics나 실행 구현 계약에 있다. 사용자 파일명을 개발 접미사로 바꾸지 않는다. 저장 성공은 계산 성공이나 engineering release가 아니다.

## 3. CAD/FE — 생성부터 조건까지

### 생성·스케치·피처

Create…에서 Clamp/Plate/Block과 폭·높이·두께를 정한다. Sketch 모드에서 Draw line을 누르고 drag하면 선이 생기고 좌표 행으로 편집된다. Width/Height와 Constrain rectangle은 해당 constraint 필드만 바꾸며 기존 선·entity를 지우지 않는다. Features에서 Pad 치수와 through hole을 바꾸면 QPainter 형상이 변한다. native sketch constraint solve/feature kernel 계산은 시제품 밖이다.

잘못된 필수 치수나 미완성 숫자는 draft 저장이 가능하다. Check/해석 검토에서는 해당 위치로 돌아간다. 형상 변경은 mesh 검토 필요로 이어지며, 예전 mesh가 유효한 것처럼 export/run하지 않는다.

### Assembly·Motion·Mesh

Assembly에서 Base/Clamp/추가 인스턴스를 선택한다. 인스턴스 수를 바꾸면 표시 부품이 바뀐다. Revolute/Slider/Fixed joint의 선택 부품만 상대 운동한다. 우측/가운데 drag의 camera 이동과 joint 이동은 별개다. Motion의 preview를 Use pose하면 저장할 설계 자세가 되고 Restore pose하면 저장 설계 자세로 돌아간다. 선택되지 않은 부품 전체를 camera yaw로 움직이는 동작은 제거했다.

Mesh는 element size/type과 합성 mesh를 갖는다. 불량 요소 행 314/829를 선택하면 강조되며 작은 요소 크기의 작성된 예시로 재생성할 수 있다. 품질 수치는 authored fixture이고 실제 mesher 검사 증거가 아니다. geometry/pose 변경 후 이전 mesh의 stale 검사는 계속 적용한다.

### 면·조건·접촉과 Simulation 전달

Conditions에서 선택 face/edge, support/load 종류, 방향, signed 값과 단위를 지정한다. Add/Edit/Delete와 Apply/Cancel을 통해 표와 그림의 대상을 확인한다. 고정·변위·힘·압력·온도 입력을 구별한다. 접촉은 A/B 면 집합, law, friction, gap이다. 활성 접촉의 빈 집합·현재 형상에 없는 면·미해결 rebind는 Check/Run을 막는다. signed force나 의미 있는 zero를 무조건 양수 조건으로 막지 않는다.

CAD Save 후 Use in Simulation 또는 Simulation의 Update geometry…를 사용한다. 참조를 바꾸는 것과 함께 **동일 saved geometry의 치수, type, joint, 선택 부품, 구멍, 인스턴스, mesh 설정**이 viewer로 전달된다. 현재 CAD draft를 과거 결과의 형상으로 사용하지 않는다.

연결 상태: `cad-sketch` → `cad-features` → `cad-assembly`/`cad-motion` → `cad-mesh` → `cad-conditions`/`cad-contact` → `simulation-implicit`.

## 4. Simulation·Runner — 공학 설정과 작업 감시

Model에서 solver와 analysis family를 선택한다. Steps는 선택한 step의 duration/increments/time step/load와 nonlinear control을 보여 준다. Hold 2 s를 선택했으면 하단도 2 s이고, Hold를 3 s로 바꾸어도 Load 1 s는 유지된다. Implicit은 잔차·반복·line search, explicit은 CFL/mass scaling과 impact IC·energy 출력의 맥락을 사용한다. Failure는 strength/fracture energy/damage 파라미터와 출력 대상이다.

Boundary conditions/Initial conditions/Output은 각 node의 실제 대상이다. 지원되는 condition은 Add/Edit/Delete 후 Apply/Cancel한다. thermal/thermoelastic에서는 구조 impact/contact/failure 페이지를 감추고 독립 SI plate domain·온도/열팽창계수·관련 출력으로 이어진다. Open geometry/domain이 무조건 CAD를 여는 경로는 사용하지 않는다. Heat V-02/r4와 Expand V-03/r6 재열기는 해당 model family와 backend를 유지한다.

주 action은 **Run analysis…**다. 확인창은 선택 모델·solver·analysis·step·load·output을 보여 준다. 내부 freeze는 적용 가능한 필수 입력 검사를 수행하고 saved input을 만든다. 사용자가 Create review attempt를 누르면 PREPARED 작업을 만든다. 실제 process는 없다.

Runner는 domain solver 설정을 다시 정의하지 않는다. 작업 행을 고르면 input/log/diagnostic/result와 convergence/energy를 본다. Review 메뉴로 authored running/failed/result 상태를 불러온다. Cancel requested와 terminal Cancelled, disconnect와 reconnect를 구별한다. Retry는 새 attempt이며, 늦은 결과는 원 attempt에 속한다. 창을 닫는 동작이 job 취소가 되지 않는다. Existing remote target의 alias/processes/queue는 편집 제안이고 실제 접속·scheduler admission은 미확인이다.

## 5. Post — field·필터·측정·비교

Array/unit/association 변경은 한 Undo 명령이다. Contact pressure 선택을 한 번 Undo하면 이전 Displacement/mm/POINTS 전체가 복원된다. 표·legend·curve cursor는 동일한 exact synthetic frame을 사용한다. t=0의 force와 gauge는 0이며, 예시에 없는 t=.03은 unavailable이다. 빠진 frame을 보간하거나 다른 시간의 측정을 남기지 않는다.

| 필터 | 편집 대상 | Apply 후 보이는 대상 |
|---|---|---|
| Clip | plane axis/offset | 해당 plane으로 잘린 합성 형상 |
| Slice | plane axis/offset | 선택 단면 illustration |
| Warp by vector | Displacement vector/scale | 색상 배열과 독립적인 변위 기반 합성 warp |
| Plot over line | gauge 시작/끝, sample count | 선택 선 범위의 합성 curve |

Reset은 pending filter 값을 취소한다. 필터 선택만으로 모든 종류를 같은 mesh toggle로 처리하지 않는다.

Gauge는 두 점과 X/Y/Z/Magnitude를 선택한다. 예시의 Gauge left → Clamp centre는 full gauge의 절반이다. 측정표의 quantity/값/unit/locator를 Numerical response로 등록할 때 역할/limit/time/reduction이 함께 편집된다. 측정 위치를 단순한 파일명으로 대체하지 않는다.

Compare는 A/B 선택, 각 원 형상, 동일 field/time/association과 값·결측을 나란히 보여 준다. p19와 p04는 각각 thickness13.7/14.6을 쓴다. 현재 CAD를 99로 바꾸어도 이 결과 형상은 바뀌지 않는다. 검증되지 않은 공간 대응에서 물리적 차이 field를 계산한 것처럼 표시하지 않는다.

## 6. Numerical — 연구 정의와 방법별 판단

평가기 한 행은 고정된 작은 높이이며 나머지는 변수·응답·방법 입력·plot이 차지한다. Add variable…은 실제 owner/field/unit/start/lower/upper 바인딩을 만든다. CAD 치수·접촉 마찰/간극·mesh size, Material 계수, Simulation load/time, PDE 계수/mesh, thermal/thermoelastic 필드를 선택할 수 있다. Add response…은 quantity/role/limit/unit/location/time/reduction을 만든다. Expert나 Study에서 만든 빈 계획도 이 조작으로 완성할 수 있다.

표의 공통 숫자 편집은 QLineEdit 기반 delegate다. `0.001`, `1e-6`, `1.2e-5`, 음수와 `1e` 같은 미완성 입력을 처리한다. Qt 기본 소수 둘째 자리 float spinbox를 사용하지 않는다. 미완성 텍스트와 행 정의는 같은 Undo 기록으로 이동한다. 삭제 후 Undo가 μ의 입력을 thickness에 붙이는 오류도 막는다.

방법 변경은 사용자가 만든 연구 정의를 임의로 지우지 않는다. 입력 예시를 불러오는 행위는 명시적이다. 변수 변경 후 matrix는 owner/field/unit로 열을 맞추고 새 열은 빈 입력으로 둔다. Case/Use/Split을 변수 값으로 밀어 넣지 않는다. 빈·비유한·범위 밖 값은 수정 위치로 돌아간다.

| 방법 | 실제 편집 대상 | 결과 화면의 판단 |
|---|---|---|
| DOE | design points, replicates, budget, case×variable matrix와 Use | case response 표, main effects |
| Inverse | 실제 training source/quality IDs, Train/Holdout/Exclude, weight, residual scale, stress measure | 관측·예측·signed residual, train RMS, 별도 holdout, 계수 proposal |
| Optimization | algorithm/population/tolerance, 변수·목적·제약, case matrix | candidate history, feasible objective, constraint margin, failed response |
| Sobol | A/B/variable-crossed block, 동일 row IDs, base samples, independent inputs, bootstrap | first/total order, uncertainty interval, index convergence |
| UQ | variable distribution/단위/parameters/bounds, pair correlations, samples, quantiles, failure threshold | response CDF, quantile table, failure event probability |
| RBF surrogate | input/response case table, Train/Holdout, kernel/smoothing, support/extrapolation | 관측/예측 validation, residual, inside/outside-support query |
| MOO | objective direction, constraint role/limit, candidate comparison | 모든 후보와 feasible non-dominated 점을 구분 |
| MDO | existing Evaluation disciplines, thermal field transfer, coupling controls | exact Heat/Expand stage open, transfer, authored iteration residual |

DOE active cases×replicates와 declared count/budget, Sobol paired IDs와 crossed 값, UQ 분포/유효 correlation matrix, inverse positive train weight/residual scale과 실제 included IDs를 검사한다. 전부 Holdout인데 frozen training에 301개를 넣지 않는다. A82 제외 후 saved Data를 명시 refresh하면 300개, A78…A85의 여덟 ID를 제외하면 293개다. 오래된 A301 결과는 그대로다.

기본 MOO의 Mass/Gauge error는 둘 다 Minimize이다. p19(.42 kg,2.1%)는 p04(.49 kg,2.9%)를 지배한다. p19만 front marker이며 p27은 제약 위반, p31은 실패/metric 없음이다. 후보 선택만으로 CAD나 Material 값을 바꾸지 않는다. Apply/Save는 각 owner별 명시 작업이고 실패한 쪽만 retry한다. 부분 저장 시험 스위치는 Review 메뉴에 있다.

### D1 방법별 작업 연결

| 원 task | 소유 방법과 현재 화면 | 구현 구분 |
|---|---|---|
| FN-20-01 | DOE — numerical-doe / result-doe | 설계행렬·응답·효과 예시 |
| FN-20-02 | Sobol — numerical-sobol / result-sobol | A/B/crossed·S1/ST·불확실성·수렴; optional engine은 미실행 |
| FN-20-03 | DOE mixed-domain 확장 | 현재 숫자 표의 배치 참조. integer/discrete/categorical 조작과 engine 지원은 D1 구현 범위 |
| FN-21-01 | Optimization / Inverse — 각 numerical/result 상태 | 일반 목적·제약·후보와 관측·가중치·holdout을 각각 연결 |
| FN-21-02 | Optimization의 gradient/adjoint 확장 | 일반 최적화 화면 참조. 실제 capability 선택·gradient adapter는 미연결 |
| FN-22-01 / 02 | UQ — numerical-uq / result-uq | 분포/단위와 상관 정의·검사. 실제 sampler는 미실행 |
| FN-23-01 / 02 | RBF — numerical-surrogate / result-surrogate | 학습/검증/support와 저장된 합성 결과. 실제 trained artifact·confirmation은 미연결 |
| FN-24-01 | MOO — numerical-moo / candidate-partial-save | 비지배 feasible 후보와 owner별 명시 채택 |
| FN-24-02 | MDO — numerical-mdo / result-mdo / Evaluation transfer·coupling | 기존 분야·전달·정확 stage. 실제 MDO/설계 동기화 검증은 D1 구현 범위 |

각 task의 원래 18개 열과 순서는 유지한다. 추가 UX 열은 현재 Qt 조작과 향후 수치/adapter 수용 기준을 구별한다. 방법명이 같은 기능군에 있다는 이유로 다른 방법의 화면·결과를 대신 연결하지 않는다.

방법별 결과는 `fixtures/methods.json`에 작성된 데이터다. Runner에서 명시적으로 불러오면 별도 numerical result로 보관하며 `computed_from_input=false`다. 현재 연구에 대한 최적화/피팅/통계 계산을 수행했다고 주장하지 않는다. 한 종류의 MOO 결과를 DOE/Sobol/UQ 등의 결과로 재사용하지 않는다.

## 7. Expert·Study — 독립 질문에서 같은 결과의 후속 논의로

Expert는 논점 지도 선택 → speaker turn → reply/evidence → 하단 개입의 구조다. node label은 node 자체가 그리므로 PySide graphics child 수명에 의존하지 않는다. 논점 추가/선택/이동, 선택 발언에 reply, evidence의 정확 위치 열기, pause/resume과 editable Plan을 제공한다. 다자 발언 예시는 authored example이며 실제 provider 발언 수로 세지 않는다. 실제 provider가 없을 때 고정 답변을 만들어 표시하지 않는다.

Models…는 역할별 설정 작업이다.

| 선택 경로 | UI에 저장하는 제안 | 현재 증거와 상태 |
|---|---|---|
| Not configured | 역할·질문·local reply·plan만 편집 | provider unavailable |
| Existing subscription OAuth | openscience + `openai-codex/<existing-model>`, 기존 profile, 역할 model override | 기존 signed-in route에 대한 source seam. 특정 model 권한·남은 limit는 UNVERIFIED |
| Existing local endpoint | 명시 api_base_url, `credential_env=''`, 역할 model override | generic local adapter seam. 실제 server/model/tool call·maintained setup 검증 없음 |

API key 입력, 새 유료 API, 구독 변경 안내나 자동 fallback을 넣지 않는다. Pro 개발 relay를 제품 Expert 권한으로 간주하지 않는다. Apply configuration은 planning proposal 저장이며 실제 계정·provider 활성화가 아니다. 미연결/limit/unavailable 상태에서도 질문·turn·evidence·Plan의 로컬 편집과 저장은 계속된다.

Plan → Numerical → review attempt → authored method result에서 선택한 행은 Discuss selection으로 원 Discussion에 돌아온다. 결과 ID와 locator가 reply 근거로 남는다. Study에는 사용자가 target hypothesis와 Support/Refute/Neutral을 골라 붙인다. judgment와 reason은 명시 Apply하며 다음 연구를 새 editable Plan으로 연다. Study의 Discuss는 자기 질문을 가진 Discussion을 열며 무관한 Expert 질문을 덮어쓰지 않는다. Save/reopen으로 같은 결과 근거와 사용자 판단을 다시 연다.

## 8. Data·Material·PDE·Evaluation의 병행 범위

Data에서 열 이름·단위·역할·formula를 편집하고 sample ID로 표/curve/mask 선택을 묶는다. 지원 단위 변환은 확인 후 값과 단위를 함께 바꾼다. Formula는 편집 recipe이며 범용 expression engine 실행은 구현하지 않았다. Data Save → Use in Material은 저장된 관측을 명시적으로 전달한다. Calibration은 CAL-018/r2의 `Calibration.txt`, force-channel row18, 0–2000 N 범위를 연다. Stiffness report나 Material fit으로 잘못 보내지 않는다. 원문 누락 시 동일 hash locate와 변경 원문 분기를 구별한다.

Material은 direct evaluation, identification와 holdout을 구별한다. Neo-Hookean/J2/Drucker–Prager/Prony/User law의 계수 표, load-case history, initial state를 편집한다. law 변경으로 예전 prediction을 새 law의 계산값으로 표시하지 않는다. 식별 Plan은 선택 law의 해당 계수를 바인딩한다. r19 missing-test repair는 fit-base r17/current r18 adoption conflict와 별개이며 r19를 유지하는 동일 원문 복구·변경 branch·Cancel 경로다.

PDE는 Rectangle/field/function space/equation/mesh와 Left/Right/Top/Bottom의 개별 type/expression을 갖는다. Apply/Reset은 선택 경계만 바꾼다. General weak form은 test/trial/domain/integral, ODE는 state/RHS/initial/time step/time range/coefficient와 별도 authored curve를 갖는다. 이 확장은 편집 scope로 남고 actual solve는 미연결이다.

Evaluation은 기존 Heat V-02/r4 → Expand V-03/r6, Temperature[K]/POINTS/exact_same_mesh를 다룬다. 단계 순서·전달·coupling tolerance/limit를 편집하고 exact stage를 연다. static 연결 확인과 actual source field 준비는 다르다. 새 일반 scheduler/optimizer를 만들지 않는다.

## 9. 기존 owner와 실제 개발 경계

GUI/CLI/Python/MCP는 본구현에서 같은 owner command/문서 revision/result를 사용한다. 이 시제품의 `UI_REPLAY_ONLY` 저장 형식을 제품 저장 포맷으로 채택하는 작업은 없다.

| 기존 계층/소스 | 승인 뒤 연결 대상 |
|---|---|
| `caelab/workbench.py`, storage/schema/native_commands/native_transport | 공통 record/command/native 통신 재사용 |
| `apps/research/desktop.py`, 기존 Data/Material/PDE/Numerical/Evaluation/Study/Discussion documents | 새 owner 생성 없이 Qt view/selection/dispatch 확장 |
| `apps/desktop_pre/cae_prep.py`, `fem_edit.py`, `motion.py`, `parameters.py`, `mesh_binding.py`, `freeze_analysis.py` | native 형상·mesh·조건·저장 입력과 UI 상태 연결 |
| `apps/desktop_post/commands.py`, `source_repair.py`, 기존 readers | 실제 field/time/filter/measurement/mapping/managed save 연결 |
| 기존 `JobManager`, Numerical engines/optimization/multiobjective | 입력 검증·실행/취소·후보/실패 응답을 기존 실행 경로에 연결 |
| `discussion_document.py`의 update/ask/intervene/pause/resume/advance, managed experts.ask, `workbench_mcp` discussion edit/control/plan open | 역할 설정과 논의·Plan을 기존 command로 연결 |

전체 nonlinear implicit/explicit/contact/failure/constitutive/coupling/inverse/DOE/UQ/sensitivity/surrogate/MOO/MDO/remote/측정·교정 범위와 device/report/setup/cross-surface 기능은 기존 FN-01…35에 유지한다. 모든 backend를 이 시제품이 실행하거나 검증했다는 의미가 아니다. 장비 연결, native 소유권/스레드, adapter capability, 수치해/차원 검증은 해당 기능 구현 후 원래 reference/tolerance로 검사한다.

### 공통 파일 작업과 전용 Report/수집 작업의 근거

FN-01은 각 독립 도구의 실제 File → Open/Save as `QFileDialog`, Save review session과 새 프로세스 재열기에 연결한다. `ToolWindow.open_file/save/save_session`, `DesktopHub.open/open_session`과 `ReviewSession`의 review-file 저장/열기를 사용한다. 최근 문서·제품 portable-store branch·native host/다중 process 동일 owner 수용은 원 D1 구현 대상으로 구별한다.

FN-34는 원 `current_source_command`의 `document_command`, `local_input_register`, `command_status`, 기존 workbench client와 native bridges를 사용하는 **작업별 GUI/CLI/Python/MCP 동등성 계약**이다. Numerical/Post 화면은 연결할 조작의 예시다. 이 시제품에서 그 제품 command나 native transport를 실행했다고 표시하지 않는다. 상세 참조는 D1 `CLIENT-CONFLICT`, `PRE-DESIGN`, `RUN-CANCEL`, `POST-MEASURE` 및 WORKFLOW_CONTRACTS C01이다.

FN-32 보고서의 정확한 prior reference는 D1 SCREEN_SPEC의 **REPORT-REVIEW**와 **REOPEN-REPORT**다. 선택 근거·표/곡선·판단, section/output/preview/export, report와 source Study 재열기를 정의한다. 현재는 `report-sections`/`report-preview`의 전용 Qt 시안이 이 흐름을 맡는다. Post/Study는 입력 근거를 제공하며, 본제품 report engine·artifact integration은 별도 개발 작업으로 남는다.

FN-35 실측 수집의 정확한 prior reference는 **DEVICE-PLAN**, **DATA-CALIBRATION**, **RUN-ACTIVE**와 WORKFLOW_CONTRACTS **C09**다. device/driver, channel/unit/time sync, specimen/calibration, sample rate/duration, 허용 동작과 종료 acknowledgment를 다룬다. 현재 `acquisition-channels`/`acquisition-connection`의 전용 Qt 시안에서 수집 설정·기존 trace 검토와 연결/종료 미확인을 다룬다. 실제 driver·실물 제어는 UNAVAILABLE이다. Simulation cancel, acquisition cancel, physical emergency stop은 별개의 동작이다.

위 참조는 `95a2389ca534b807420a4e7dbe2397f5e60953c9`의 읽은 **텍스트 명세**이며, 본 branch에 D1의 해당 SVG가 있다고 가정하지 않는다. `screen_states.json`의 `prior_references`와 화면 색인에서 연결 범위를 확인할 수 있다.

## 10. 검토 후 개발 순서

`implementation_map.csv`의 기존 task ID와 dependencies가 기본이다. 공유 편집·정밀 수치·owner 연결과 각 도구 UI를 병렬로 진행하고, CAD→Simulation→Runner→Post 및 Expert→Numerical→결과→Study 두 경로를 통합한다. Data/Material/PDE를 전체 제품의 첫 번째 필수 마일스톤으로 강제하지 않는다. 기존 solver campaign을 UI 변경의 gate로 재실행하지 않는다.

현재 완료물은 검토 가능한 planning source와 실제 offscreen 확인이다. 사용자가 산출물을 검토하고 **개발 시작을 지시한 뒤** 본제품 변경을 시작한다. MoAI 연결과 해당 acceptance 매핑은 `MOAI_HANDOFF.md`, 구체적 실제 검사와 한계는 `REVIEW.md`에 있다.


## Report / Acquisition 전용 시안 — UX-COMPLETE-01

### Report: 절과 내용에서 출력까지

기존 Study 소유를 재사용하는 별도 검토 문서다. Study의 Report… 또는 Window → Report로 열며, 강제 Home이나 추가 실행 owner를 만들지 않는다. 왼쪽 Sections는 checkbox 포함 여부와 drag/Move up/down 순서를 갖는다. 중앙 Section content에는 선택 절의 본문 또는 근거 표·큰 curve가 나온다. 상단의 짧은 제목과 하단 caption을 편집한다. Source 데이터는 직접 덮어쓰지 않고 Open source로 해당 결과/locator 또는 저장한 Study 창을 연다.

Use Study는 명시적으로 선택한 **저장 Study**의 질문·판단·근거를 보고서에 가져온다. 편집 중인 Study는 먼저 그 창에서 저장해야 한다. 현재 draft를 과거 보고서의 원 근거 대신 열지 않는다. 표의 numerical locator는 method/table/row를 정확히 유지하며, 방법 전체 curve를 함께 넣으면 caption에서 선택 행의 표와 구별한다. Add section은 로컬 본문, 정확 결과 표, 보유 curve를 고른다. Include/Remove/Reorder/Edit 모두 기존 Undo/Redo와 일반 Save를 따른다.

Page preview는 기본 1440×900 desktop 가운데의 세로 용지와 Previous/Next를 쓴다. 오른쪽 Output dock은 해당 탭에서만 나타난다. Review PDF와 Markdown을 고르고 Export preview…의 파일 chooser에서 경로를 정한다. PDF는 preview와 **같은 ReportPage QPainter**를 사용한다. 표는 18행 단위 페이지로 나누며, 지나치게 긴 본문은 절 분할을 요구한다. Markdown curve는 원 좌표 표로 내보내므로 그림을 내보냈다고 주장하지 않는다. 원 입력·결과를 계산하는 보고서 엔진이나 승인 엔진은 없다.

근거가 없는 절은 그 절만 unavailable이다. 기본은 export 차단이고, 사용자가 unavailable placeholder를 선택하면 누락을 표시한 페이지를 출력한다. 임시 출력 완료 후 파일을 교체하여 일반 write error에서 이전 출력이 유지되게 한다. 저장한 보고서는 Study snapshot·결과 첨부·정확 locator·절 순서/내용을 갖고 단독 cold reopen할 수 있게 작성했다. Checks 절은 process completion, numerical validity, engineering checks, release를 구별하며 기존 F05 실패 수치/허용치를 유지한다.

### Acquisition: 채널과 기존 신호에서 수집 계획까지

기존 Data 소유의 검토 문서이며 장비 driver를 새로 구현하지 않는다. 왼쪽에는 instrument/driver 선택, 채널 표, sample rate/duration/time offset과 timebase/요청 모드가 있다. 오른쪽의 큰 curve와 표는 **이미 보유한 Data 파일**을 보여 준다. 계획한 1000 Hz·10 s를 기존 trace에 적용해 샘플을 만들지 않는다. 표와 curve의 선택 sample ID가 같으며 표시 단위와 명시한 시간 offset만 함께 바뀐다.

Add/Edit channel의 native dialog는 name, force/extension/temperature field, 호환 unit, Measurement/Monitor role, calibration link와 include를 편집한다. Cancel은 원 채널을 유지한다. CAL-018은 force 전용이며 원 Calibration.txt row18과 0–2000 N 범위를 연다. 교정 연결만으로 원 trace를 재교정한 것처럼 표시하지 않는다. Extension 등 미지정 calibration은 Check plan의 미완료 조건으로 보이며 live 연결 성공으로 바뀌지 않는다.

수집 수치는 기존 EngineeringTextDelegate로 지수 표기·음수 offset·의미 있는 zero·미완성 draft를 유지한다. rate와 duration은 양수여야 하며 time offset은 유한한 signed 값/0을 허용한다. invalid draft의 Save는 가능하고 Check plan이 해당 셀/채널로 이동한다. 값 점검 성공은 장비 실행 가능 판정이 아니다.

Review → Connection loss example은 오류 상황을 보는 작성된 시안이다. 같은 기존 trace와 함께 **Connection and end** 탭에서 live UNAVAILABLE, acquisition phase 미관측, requested stop NOT_SENT, device ACK NOT_RECEIVED, physical terminal UNKNOWN, allowed control NONE을 구별한다. 실제 명령을 보내는 Connect/Start/Stop은 비활성화된다. 메시지 확인을 physical ACK로 바꾸는 checkbox나 버튼은 없다. Return to setup / Open existing Data / Save를 통해 독립 파일 작업을 계속한다. Simulation cancel·acquisition cancel·physical emergency stop의 기존 C09 구별을 유지한다.

### 새 상태와 확인 범위

| 상태 | 주요 검토 대상 | D1 연결 |
|---|---|---|
| report-sections | 절 순서·선택·본문/표·정확 source | FN-32, REPORT-REVIEW |
| report-preview | 동일 Qt page·curve·output 조건 | FN-32, REOPEN-REPORT |
| acquisition-channels | 채널·단위·교정·수치·trace 선택 | FN-35, DEVICE-PLAN / DATA-CALIBRATION |
| acquisition-connection | 연결 오류·미확인 종료·기존 Data로 복귀 | FN-35, RUN-ACTIVE / C09 |

이 추가 소스의 원격 Linux Qt 실행은 환경 disconnect로 미확인이다. UX-RECOVERY-01에 따라 Codex가 기존 Windows Python3.13.5/PySide6 6.9.1에서 실행·렌더를 맡는다. 원격 재설치/유료 환경은 사용하지 않는다. 원래 52상태와 새 4상태는 같은 exporter/font policy를 사용한다. 기존 source에 대한 PASS를 새 화면으로 확대하지 않는다.
