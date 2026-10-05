# 실제 CAE 연구 사용을 위한 순차 개선 계획

2026-10-05 · 독립 Astra/high 감사 제안 · 기준 Main815e207 / fixture3e48bf6.
이 문서는 실행한 작업의 보고가 아니라 Root가 통합할 **제안 계획**이다. 각 단계의 개발, 실제 검증, 사용자 인계, 물리 승인 기준을 구분한다. 기존 52개 요구와 Phase 1–7을 삭제하거나 solver/연구 모델을 바꾸지 않는다.

## 1. 완료 기준부터 바꾼다

한 단계의 개발 완료는 소스가 있고 중요한 거부/호환성 조건을 확인한 상태다. 수치 검증 완료는 실제 native 입력과 결과가 사전에 정한 reference·보존·오차·평형·mesh/time 기준을 만족한 상태다. 연구 기능 완료는 사용자가 질문하고 조건을 확인하며 실행·수정·비교·해석·원본 조회·종료까지 같은 기록으로 마친 상태다. 물리/강도 RELEASED는 실측 물성·실제 접합과 하중·기계 인터페이스·허용치·제작·실험·내구 등의 blocking 요구를 실제 evidence로 닫은 상태다.

**일상적인 가상 CAE 연구는 NOT_RELEASED 상태에서도 수행할 수 있다.** 가정·수치 유효성·입력 범위가 명확하고, 해당 질문에 필요한 응답이 유효하면 된다. 강도 판정이나 안전한 실제 사용 승인으로 확장할 때에는 부족한 물리 근거를 요구한다. 모든 연구를 실물 승인 때까지 막거나, solver exit로 실물 승인을 부여하는 양쪽 접근을 피한다.

최종 전체 software 완료 기준은 R01–R52의 각 구현/연결 요구에 대응하는 사용자 흐름과 증거가 있고, 외부 장비·회사 승인·실측 데이터가 필요한 항목은 그 정확한 외부 gate로 남는 것이다. 외부 gate가 남았다고 전체52를 완료로 바꾸지는 않는다. 반대로 고정된 작은 예제 하나가 통과했다는 이유로 해당 phase의 나머지 기능을 지우지 않는다.

## 2. 실행 순서와 예상 자원

아래 기간은 **경험적 계획 추정, 1명의 통합 담당자와 필요한 bounded 검토를 가정한 집중 작업일**이다. 검증된 소요시간이나 완료 약속이 아니다. 현재 자료만으로 신뢰할 수 있는 전체 달력 ETA는 산정할 수 없다. 특히 assembly/explicit의 RAM·성능과 실물/회사 승인에는 외부 변수가 크다. 처음 대표 run의 CPU/RAM/I/O/파일량을 측정한 뒤 갱신한다.

| 순서 | 사용자에게 생기는 결과 | 의존성/주 담당 | 개발 추정 | 별도 실제 검증 |
|---|---|---|---|---|
| S0 | 현재 가동/중단/미확인 상태를 정확히 알 수 있음 | 기존 receipt와 controller; Root/운영 | 0.5–1일 | 읽기 전용 상태 대조 1회, 새 solve 없음 |
| S1 | 한 시작 동작으로 지원 질문을 실행할 수 있음 | S0; launcher/Lab | 1–3일 | 현재 source의 질문→같은 result→종료 1회 |
| S2 | mesh·하중·구속·형상과 비교를 이해할 수 있음 | S1; Results/UI/adapter reader | 2–5일 | 저장 결과 UI 검증 후 바뀐 경로만 fresh run |
| S3 | 중단·프로그램 재시작 후 작업과 결과를 찾을 수 있음 | S0, S1; 실행 소유자/Core 경계 Root | 2–5일 | tiny process crash matrix + 대표 native cancel/reconnect |
| S4 | 원본 조립체가 명시한 mechanics로 계산되고 보임 | phase5 contact 기반·S3; Domain/adapter | 5–15일 이상 | import/patch/실제 mechanics를 목적별 묶음 검증 |
| S5 | 기존 수치 엔진으로 설계 비교·탐색을 끝냄 | S1–S3; Phase3 | 3–8일 | 기존 증거 reuse, representative new campaign 1묶음 |
| S6 | 선언된 PDE를 수정하고 field/history를 비교 | Phase4 기존 구현; S2–S3 | 5–15일 | 변경된 form/domain/벡터/MPI 의존만 검증 |
| S7 | 비선형 재료/접촉을 실제 구조 모델에서 연구 | Phase5·S4; Domain/implicit/MFront | 10–25일 이상 | 재료점→FE coupling→대표 구조 history |
| S8 | 표면 접촉을 가진 실제 낙하/충격 연구 | Phase6; explicit adapter/preprocessor | 10–25일 이상 | Starter/Engine·history·refinement·GUI/Research |
| S9 | 측정 역추정/UQ/다목적/원격 연구 | Phase7; 데이터/수치 엔진/원격 adapter | 15–40일 이상 | 기능별 작은 end-to-end 캠페인, 외부 장비 별도 |
| S10 | 계속 쓸 수 있는 인계·보존·배포 방식 | 모든 단계; Root/사용자 조직 | 2–5일+외부대기 | export/restore·현재 host start/use/stop·배포 검토 |

현재 이미 있는 Phase3–5 소스·native evidence는 재개발하지 않는다. S0–S3은 모든 단계에 공통인 사용성/운영 보완이며, S4는 현재 P2.4와 이미 개발한 Phase5 접촉의 의존성을 닫는 일이다. 그 뒤 S5–S9는 기존 단계 순서의 미완료 범위만 처리한다. 같은 공통 파일은 Root 단일 소유, 독립 검토는 읽기 전용, 특정 adapter/UI 구현은 파일 소유자를 정한 bounded 작업으로 한정한다.

## 3. S0 — 현재 상태를 정리하고 다음 실행을 명확하게 만든다

**개발/정리**

1. Root가 봉인한 `root-observation-01`을 authoritative observation으로 링크한다. fine는 완료/실행 중으로 추정하지 않고 `UNKNOWN_NOT_QUALIFIED`로 기록한다. 원래 RUNNING 파일과 partial outputs는 그대로 둔다. 원인을 알아내는 진단 기록은 새 sidecar에 남긴다.
2. 현재 단일 queue에 활성 단위, owner, source, run, 실행 여부, 실제 마지막 변화 시각, 다음 행동, stop/cancel 조건을 둔다. HANDOFF 상단은 이 상태를 짧게 요약하고 나머지 문서에는 링크만 둔다. 52 ledger 설명과 history는 보존한다.
3. 상태를 `software implementation / native numerical qualification / connected user flow / current readiness / physical release`로 나눈다. imported·source-only·hypothetical patch를 solver mechanics와 혼합하지 않는다.
4. fine 새 run 전에 현재 partial의 원인 후보를 좁힐 수 있는 **기존 종료·호스트/WSL/자원 관찰**만 수집한다. 종료 원인이 확인되지 않으면 UNKNOWN으로 남기고, 새 run의 supervision을 고친 뒤 새 ID로 실행한다. OOM/timeout이라고 선결론을 쓰지 않는다.

**가장 작은 완료 근거**: 현재 source/8지정ports/9기록PIDs·old fine 상태가 서로 구분된 한 기록, 기존 store 불변, 다음 run의 owner/output/state 위치와 대기·중단 기준. 이 단계에 solver나 모델 호출은 필요 없다.

**요구 매핑**: R08–R13, R21, R38, R43–R49, R52. Root가 기록한다. 기존 목표의 BLOCKED 상태, 새 goal 생성 거부, ACTIVE heartbeat는 별도 관리 상태이며 여기서 기능 완료로 바꾸지 않는다.

## 4. S1–S2 — 첫 실제 연구 시나리오를 제품 흐름으로 완성한다

### 사용자가 보는 흐름

“롤러 지지대 폭을 32 mm에서 38 mm로 늘리면 처짐과 재료 사용량이 어떻게 바뀌나요?”라고 시작한다. 화면은 이미 정의된 `단일 지지부 선형 연구` 시나리오와 가정을 먼저 보여준다. 사용자는 목표·폭 범위·하중을 보고 수정한다. 연구 assistant가 모델을 만들고 적절한 기존 operation을 호출한다. 결과에서는 실제 형상, 고정 바닥, saddle 하중, 재료축, mesh 크기, 처짐 표·곡선과 비교가 한 연구 안에서 보인다. 이후 “하중을 150 N으로 바꾸면?”과 “이 가정 안에서 더 적은 재료를 쓰는 후보를 찾아 주세요”로 이어간다.

재료나 BC가 사용자 목적에 맞지 않으면 모델이 그 불일치를 드러내고 필요한 조건만 확인한다. 전문가용 긴 검증 prompt를 사용자가 작성하게 하지 않는다. 이미 승인된 가상 시나리오를 선택한 경우 그 사실을 명시해 기본값을 사용한다. 실측인 척하거나 임의 물성을 자동 추정하지 않는다.

### 최초 시나리오의 구체적 모델링 선언

| 항목 | 입력/해석 의미 |
|---|---|
| 모델 | pinned upstream `roller_support`, 각 폭의 편집 가능한 CadQuery source와 STEP를 별도 CAD revision으로 보존 |
| 변수 | support_width_mm 32/38 mm 비교. 나머지는 초기 깊이40/높이26/roller diameter8.3/pitch X20,Y24/hole4.5/edge2 mm. 실제 discovery·registry로 확인 |
| 하중 | 지지부당 -Z 총100 N, 후속150 N. 중앙24 mm saddle patch에 existing area-weighted nodal load. 전체 조립체 하중 분담을 주장하지 않음 |
| 구속 | 바닥 X/Y/Z 고정. 실제 bolt·machine mounting을 대체한 이상화 |
| 재료 | **가상 미측정 직교이방성** E1/E2/E3=1800/1800/900 MPa, ν12/ν13/ν23=.3, G12/G13/G23=650/320/320 MPa. CAD X/Y/Z와 재료축 일치. Z는 가상의 적층 방향 |
| 메시 | 같은 CAD revision에 4/3/2 mm T10, 실제 element count·quality·loaded sets·force sum·raw deck를 보존 |
| 주 응답 | 각 mesh에서 loaded saddle의 signed min global Uz(mm), 최대 displacement와 구분. volume(mm³), signed XYZ reactions(N), mesh sensitivity |
| 기존 수치 gate | 마지막 두 mesh 처짐 상대 변화≤5%, signed XYZ 반력 balance≤1%. 기존 정의/분모 유지. stress는 invalid diagnostic |
| 가설/비교 | 폭 변경의 처짐·체적 영향은 결과로 평가한다. 100→150 N은 linear 모델의 1.5 비례를 raw 출력 정밀도에 맞춰 확인한다. 임의의 통과 기대값을 끼워 넣지 않음 |
| 유지할 UNKNOWN | material/strength/contact/fastening/machine/physical/fatigue 및 stress convergence. 결과는 NOT_RELEASED |

human07 값은 역사 reference로 비교 가능하지만 새 source/run의 숫자를 강제로 같게 맞출 기준은 아니다. 정확한 runtime/source/input이 같은 경우 예상 변동의 해석 기준으로 쓰며, 변경이 있으면 그 물리·수치 영향을 기록한다. 인간이 보는 입력과 native deck 설정을 실제로 대조한다.

### 탐색의 첫 연결은 이미 허용된 optimizer를 사용한다

현재 FixtureRefinement의 14 tools에는 DOE가 없고 optimization plan/run/inspect가 있다. 첫 AI 시나리오는 existing SciPy DE, population5/max_generation1, seed13, 폭의 등록 범위 안에서 volume 최소화와 유효 displacement constraint를 선언한다. 기존 acceptance의 0.0065 mm 제한을 사용할 경우 **연구용 가상 screen**임을 표시한다. invalid stress를 objective/constraint로 쓰지 않는다. budget 종료/`converged=false`/best observed feasible을 정확히 설명한다. 한 세대만으로 “최적 폭”을 확정하지 않는다.

5점 LHS DOE는 이미 있는 Explore/Core 경로로 인간이 실행할 수 있다. AI에서 직접 DOE를 원하면 Phase3의 별도 descriptor admission/actual gate로 연결한다. 기존 descriptor를 몰래 넓히지 않는다. 첫 시나리오에서 DOE와 DE를 모두 풀 native로 반복할 필요는 없다.

### 개발 작업

1. 기존 `openscience-server-local.ps1`와 Lab을 조합한 명시적 시작·상태·종료 경로를 제공한다. approved5.6Sol, ChatGPT, Research/FixtureRefinement, 기존 auth/project, **새 store**를 사용한다. owner/source/store를 일치시키고 지원되지 않는 기능을 실행 전에 표시한다. 인증/profile를 초기화하지 않는다.
2. 간단한 시나리오 카드에 가정·변수·입력 단위·예상 계산 단계와 수정 가능한 범위를 넣는다. 실제 제출될 설정을 Core declaration과 연결한다. 모호한 자유문장도 scenario context를 통해 기존 strict input contract로 유도한다.
3. 부모 CAD view를 analysis result에서 같은 revision으로 참조한다. scene에 mesh/boundary/load/material axes를 함께 표시하고, 분석 mesh와 CAD tessellation을 구분한다. 없는 FEA field를 CAD 색칠로 대신하지 않는다.
4. 실제 지원된 native output에서 Uz/Ux/Uy/magnitude/반력·단위·probe·deformation scale을 연결한다. stress는 invalid reason을 계속 보인다. 다른 field family를 한 번에 새로 만들지 말고 기존 PDE/contact readers를 공통 UI 요소에 재사용한다.
5. 수렴 boolean의 표시를 case-specific checks로 바꾼다. mesh sensitivity와 asymptotic convergence, solver iteration convergence는 별도다. 답변 heading/수식·표를 읽을 수 있게 하고 wide empty column을 제거한다. raw answer는 함께 보존한다.
6. 간단한 예외 흐름: 잘못된 폭/간격 → 이유와 수정 가능한 입력 표시 → 새 revision 생성. UI가 거부 조건을 자동 완화하지 않는다.

### 검증 묶음과 인계 gate

- 저장된 human07 result를 이용해 화면/링크/단위/invalid/UNKNOWN을 먼저 검증한다. 이 단계는 새 solver가 필요 없다.
- 바뀐 시작·context/제출 경로가 준비되면 깨끗한 source/새 store에서 **한 묶음**을 실행한다: 질문→폭32/38→같은 부모의 mesh 비교→150 N 후속→한 bounded 탐색→동일 result scene/report→정상 종료. 질문을 사람이 뒤에서 고쳐 도구를 대신 실행하지 않고 실제 실패가 나면 그대로 기록한다.
- 일상 사용 gate는 사용자에게 명령어나 raw JSON을 요구하지 않고 위 작업을 끝내는 것이다. observer가 개입한 단계·막힌 표현·대기 시간을 기록한다. 시스템이 내부적으로 만든 IDs는 사용자가 수기로 입력하지 않아도 된다.
- 별도 rejected-input 1건은 solver가 실행되지 않았음을 확인한다. 변경 전 결과 digest 보존, report ZIP 내용·parent refs 일치, owned stop/실제 terminal을 확인한다.
- runtime 구성시간을 제외한 historical human07 질문은 약418초였다. 이는 1 CAD/3mesh/8tools의 참고치일 뿐이며 확대 scenario의 약속 시간이 아니다. 새 scenario는 20–90분짜리 관찰 창을 **초기 계획 추정**으로 두고, 측정 후 수정한다. wall budget을 scientific threshold와 섞지 않는다.

**요구 매핑**: R02/03/06–13/19–21/25–27/33/34/48/50–52. Root: launcher/shared interfaces; UI owner: 화면; adapter owner: 실제 native fields; 독립 reviewer: input→raw→display 의미.

## 5. S3 — 장시간 작업을 책임 있게 관리한다

### 필요한 개발

기존 process helper/owned controller에 작은 durable lifecycle record와 재접속 판정을 추가한다. 새로운 general queue나 cloud orchestration을 시작하지 않는다. root owner·run UUID·host/WSL boot identity·process PID+시작 identity·source/input hash·output root·stage·마지막 진전 시각·cancel request/observed·terminal을 구분해 저장한다. PID 숫자만으로 소유권을 추정하거나 kill하지 않는다.

재시작 후 startup scan은 자기 store의 unresolved run만 다룬다. 소유 프로세스가 살아 있으면 관찰만 다시 연결하고 duplicate execution을 막는다. 없고 terminal receipt도 없으면 “작업 프로세스를 찾지 못함, 완료 여부 미확인”으로 기록한다. 이전 RUNNING 원기록은 덮어쓰지 않고 새 reconciliation event를 추가한다. UI의 IDLE은 “이 resident에 thread가 없다”와 “전체 store의 미해결 native가 없다”를 구분해야 한다.

각 run은 stage 시간, CPU/RSS, output 크기, 마지막 log advance, solver 제공 iteration 정보를 한정된 간격으로 남긴다. heartbeat가 계속 살아 있다는 사실은 numerical progress가 아니다. code_aster native cpu limit와 optional wall budget은 사용자/운영 정책으로 명시하고 물리 설정·결과판정에서 분리한다. 자동으로 같은 실패를 재시작하지 않는다.

### 작은 검증부터 실제 검증까지

1. tiny owned child로 정상완료, startup failure, 사용자 cancel, controller abrupt exit, cleanup failure, PID 재사용/다른 owner, 두 관찰자의 재접속, incomplete output의 상태 전이를 확인한다. 이 단계는 solver 반복이 필요 없다.
2. 실제 native representative 1건에서 active cancellation과 partial 보존·owner terminal을 확인한다. historical human05는 native가 끝난 뒤 cooperative cancel이므로 즉시 solver interrupt 증거로 재사용할 수 없다.
3. 새 store로 재접속 후 old result inspection과 새 작업 admission이 모두 정확한지 확인한다. known live child에만 existing owned termination을 사용한다.

**롤백/중단**: 확실하지 않은 자원은 CLEANUP_PENDING/UNKNOWN, 해당 store writer admission 차단, old evidence 보존. 무관한 process 종료·강제 overwrite 금지. 개발 변경 rollback은 소스 commit으로 하고 run record는 남긴다.

**요구 매핑**: R08/11/12/21/27/38/43/48/49/52. 완료 근거는 재접속 화면+state events+실제 OS observation이며 test count가 아니다.

## 6. S4 — 조립체를 import에서 실제 mechanics 연구로 연결한다

### A. 비용이 작은 native field seam qualification

- 이미 qualified coarse3 mesh/CAD를 재사용한다. 현재 4개 후보 파일은 source-only이며 Root가 검토된 의미 있는 단위로 통합한다. Main dirty/live source가 없는지를 통합 전에 확인한다.
- affine benchmark는 E2000 MPa/ν.25, full exterior affine Dirichlet/interior free로 고정된 numerical patch임을 이름과 결과에 표시한다. 실제 load path와 분리한다.
- native import 이후 U 전체 성분, raw stress tensor/strain/energy, 실제 integration-point 좌표·weights, reactions를 읽고 독립 affine 식과 비교한다. shear tensor vs engineering convention, node/cell/ELGA ordering과 body mapping이 중요하다. 모든 외부 절점을 지정해 내부 해가 불필요해지지 않았는지 실제 free interior DOFs를 확인한다.
- 기준은 frozen candidate의 displacement/stress/energy/force/moment limits다. 단순한 constant field에 refinement error rate를 강요하거나 roundoff rate를 합격 조작하지 않는다. coarse 1회가 새 seam을 증명하면 다음 actual mechanics로 진행한다. fine1.5의 identity/performance gate는 필요한 비교 해상도 자격으로 따로 닫는다.
- ASTER native text/MED 등 새 transport로 성능을 바꾸는 경우, syntax research만으로 개선을 주장하지 않는다. same original node/ordered cell/group bijection과 실제 elapsed/RAM을 측정한다. 작은 import-only probe→원래 coarse→필요할 때 fine 순서다. 다시 Gmsh parse/완전 복사를 반복하는 횟수와 비용을 기록하고 불필요한 중복을 제거하되 input hash/semantic identity는 유지한다.

### B. 실제 조립체 연구용 모델을 먼저 선언한다

전체 15 components 중 현재 active7/inactive8 bolts라는 partition을 명확히 한다. 최초 mechanical scope에서 제외한 bolt는 의도와 남는 UNKNOWN을 보인다. 사용자 질문은 예를 들어 “선언한 하중에서 specimen 처짐과 support/base compliance가 어떻게 나뉘고, 지지부 폭에 얼마나 민감한가?”이다.

필수 선언은 다음과 같다.

1. 각 component의 material law/units/source/axes. printed part 가상 orthotropic, metal roller/nose/specimen 가상 isotropic 등 역할이 다르면 값도 별도 선언한다. 임의 uniform E를 실제 재료처럼 사용하지 않는다.
2. 실제 global frame과 geometry catalog의 named support/load/contact selections. fixed base/bolted support 중 무엇을 이상화하는지 선택하고 모델 revision에 넣는다.
3. top nose에 force 또는 displacement control 중 하나를 목적에 맞게 명시한다. preload/접촉 초기화/load stepping, large displacement 여부, friction law와 initial gaps를 선언한다. force와 displacement를 같은 DOF에 부당하게 중복하지 않는다.
4. body pair별 frictionless contact, bonded tie, open interface를 명시한다. friction/preload를 모르면 unknown으로 남기고 가상 비교 연구로만 사용한다. 초기 CAD distance가 contact pressure/gap qualification이 아님을 유지한다.
5. 측정 response 위치: specimen 중앙 displacement, nose displacement/force, support/base displacement, full U, stress tensor의 적절한 위치/validity, contact pressure/resultant, penetration/slip 등 solver가 실제 제공하는 양. derived gap이면 native와 구분한다.
6. force/moment equilibrium, external work/strain/contact energy, reaction path, load-step convergence, mesh/contact sensitivity의 기준을 output 전에 정의한다. singular edge의 point peak stress를 material strength로 판정하지 않는다.

### C. 가장 작은 유의미한 실제 acceptance

먼저 기구적으로 안정한 한 declared model에서 static load path가 모든 intended body로 전달되는지, named contact normal과 resultant 방향이 맞는지 확인한다. 가능한 축약 limit case(선형 specimen/이상 지지의 beam 식 등)는 해당 가정으로만 비교하고 3D assembled 해를 임의의 beam 표에 강제로 맞추지 않는다. 이미 retained official SSNP121A contact qualification은 adapter contact primitive의 근거로 재사용하며 실제 assembly adequacy를 대신하지 않는다.

그 뒤 두 mesh/한 changed load 또는 displacement로 지정 response와 contact/resultant의 민감도를 검토한다. 새 fine가 매우 비싸면 measured coarse 비용과 목표 response를 보고 필요 refinement를 계획하되, 기존 실패 기준을 바꾸거나 mesh 수를 줄인 결과를 동일 gate PASS라고 표시하지 않는다. 실패는 numerical/physical/modeling/transport/environment 중 아직 확인된 범위까지만 분류한다.

마지막으로 existing `run_analysis` child/같은 CAD revision에 adapter를 연결하고, 필요한 public capability/guard를 새 scope로 명시하여 실제 OpenScience whole question→새 parent/child→field view→조건 변경→비교→중단/보존을 수행한다. 내부 import function에 성공했다고 public Research가 생긴 것으로 취급하지 않는다.

**산출물**: model declaration/ADR impact, parent CAD+recipe, original/transport/native mesh mappings, comm/deck/log/MED/field tables, references/error tables, evidence/result/decision, GUI scene·comparison·report, resource/lifecycle receipt.

**요구 매핑**: R04/05/08–14/19–21/26/29/33/34/43/45/51/52. physical material/fastener/machine/strength/durability는 이 numerical research gate 이후에도 UNKNOWN이다.

## 7. S5 — Phase3 탐색을 실제 연구 기능으로 닫는다

**개발**: 보존된 `269d8bf` five-generation fixture proof의 정확한 source·input·state·result를 먼저 read-only로 검토하고 필요한 integration만 한다. 이미 있는 LHS/DE를 새로 작성하지 않는다. registered input이 실제 CAD/declared model의 어떤 값에 연결되는지, objective/constraint의 단위·validity, stopped/budget/infeasible/error 구분을 화면에 제공한다. DOE를 AI에 연결할 때는 새 bounded admission으로 실제 flow를 검증한다.

**수치 검증**: 알려진 constrained analytical objective에 대한 engine proof는 보존된 것을 재사용한다. 실제 fixture는 “best observed”와 numerical convergence를 구분하고, 독립 repeat seed가 필요한 질문인지 사전에 정한다. 같은 input/source를 가진 completed evaluations는 replay로 재사용한다. invalid CAD에는 solver child 없음, invalid field에는 usable feedback 없음, active constraint의 source/units 유지, stop/restart 후 candidate order·old artifacts 보존이 최소 gate다.

**확장 순서**: mixed integer/categorical variables와 관계 constraint→필요한 sensitivity/UQ→multiobjective/surrogate는 Phase7에서 역할에 맞는 engine을 선택한다. 단순 scalar 문제에 DAKOTA/OpenMDAO/pymoo를 모두 설치하지 않는다. 구현된 SciPy 결과의 한계를 해결할 때만 adapter 추가를 정당화한다.

**사용자 완료**: objective/constraint를 고르고 예산을 설정해 실행, feasible/invalid 후보를 같은 CAD·FEA record에서 비교, stop reason과 다음 실험을 해석. 최적화의 최종 숫자만 보여주지 않는다. R03/06/11/18–21/27/33/34/40/43/48/52.

## 8. S6 — Phase4 PDE 기능을 일관된 연구 흐름으로 만든다

**개발**: 기존 scalar/nonlinear/rectangle/transient/vector/coupled/imported 범위를 표로 정리하고 실제 profile별 admission·UI inputs·output을 맞춘다. 현재 지원되지 않는 form, BC type, nonlinear-time-vector 조합, mesh format/size/MPI는 실행 전 명확히 거부한다. equation/reference/source/boundary를 사용자가 바꿀 때 무엇이 새 model revision이 되는지 보여준다.

**실패 진단**: 815 vector의 outer classification assertion만으로 solver failure를 단정하지 않는다. exact case raw result·expected classification·실제 rate/reference error·input/runtime을 한 번 모아 source/classification/numerical 원인을 구분한다. wrong-reference negative case가 rejection으로 저장되는지 긍정 case와 분리한다. 같은 fixture를 blind rerun하지 않는다.

**검증 묶음**: 바뀐 form/domain마다 manufactured polynomial/closed response로 source/BC/field error를 독립 비교한다. 공간 refine와 시간 refine는 한 축씩, interface flux의 의미와 physical flux를 구분한다. 실제 residual/KSP/Newton·full field를 유지한다. serial qualified 뒤 필요한 실제 MPI 분할에서 동일 문제/양 보존을 검증한다.

**사용자 완료**: 간단한 선언식과 named boundary를 입력→한 조건 변경→mesh/time field slider와 component probe→reference/오차 plot→AI의 올바른 해석→report. 기존 c0/c3 사례를 시연 출발점으로 재사용한다. 범용 symbolic language를 새로 만드는 일부터 시작하지 않는다. R16/19–21/28/33/34/39/43/48/52.

## 9. S7 — Phase5 비선형·구성방정식과 실제 구조를 연결한다

**개발**: 보존된 geometric beam 실패·partial을 정확히 진단하고 load control/step/history/result reader의 문제와 native convergence를 구분한다. SVK/Maxwell의 material-point stress/tangent/energy state를 기존 구조 adapter가 사용하는 실질적 solver coupling으로 확장한다. 임의 초탄성/점탄성 모델을 모두 구현할 필요 없이 이미 선택된 모델에서 interface·finite strain convention·state update를 닫는다.

**대표 검증**: material point는 independent derivatives/finite difference와 energy/state history, FE 연결은 homogeneous one-element/patch→구속 조건이 달라진 작은 구조→현상별 구조 reference 순서다. 이것은 MFront compile/MTest PASS와 FE response PASS의 차이를 닫기 위한 최소 연결이다. contact는 retained SSNP121A를 재사용하고 실제 slip/friction/large-deformation 필요한 family만 추가한다. 이미 실패한 CalculiX pilot은 원래 limits로 남긴다.

**사용자 완료**: 재료 law·load history·contact를 지정하고 full stress/strain/energy/history와 iteration/invalidity를 볼 수 있으며, 조건 변화가 새 record로 남고 AI가 solver convergence와 물리 적합성을 구분한다. 실제 measurement와 allowables가 없으면 강도는 UNKNOWN. R14/17/19/20/26/29/33/34/39/43/48/52.

## 10. S8 — Phase6를 reduced stop에서 실제 explicit 연구로 넓힌다

**개발**: 현재 설치의 exact artifact URL/digest/사용 가능 여부를 확인해 installer 실패를 해결한다. mirror/update가 필요하면 공식 출처·license·새 version을 명시하고 기존 run provenance와 분리한다. exit0을 얻기 위해 download pin 검사를 제거하지 않는다.

모델 선언에는 deformable/rigid bodies, 질량·관성·initial velocity/gravity, 일반 surface contact·friction·rotation, materials/failure, contact/output controls와 시간 단위를 포함한다. PrePoMax inp conversion 등 실제 경로를 선택해 mapping된 카드·unsupported 내용·loss를 검사한다. conversion 전체를 지원한다고 광고하지 않는다.

**대표 검증**: 기존 flight와 compliant-stop 에너지/반발 근거는 재사용한다. 다음은 실제 surface contact를 가진 단순 body impact, 그 다음 deformable impact/wave 또는 완전한 공식 reference다. force/acceleration의 동기화, momentum/impulse, energy components·hourglass·mass scaling, contact penetration, timestep/mesh 민감도와 finite material/failure response를 정한 output에서 검토한다. ideal wall의 역사 rejection을 미화하지 않는다.

**사용자 완료**: drop/impact 조건→실제 preprocessing/deck→Starter/Engine→time-history/animation→조건변경 비교→OpenScience 해석. 한 animation screenshot이나 energy 총합만으로 Phase6 완료라 하지 않는다. R15/19–21/30/33/34/39/43/48/52.

## 11. S9–S10 — Phase7과 지속 가능한 연구 환경

### 측정 역추정과 재료 coupling

측정 CSV/단위/시간/하중경로/시편 정보·calibration·불확실성·원본 hash를 가져온다. synthetic truth case로 parameter recovery와 invalid data refusal를 먼저 확인하고, 측정 fit/calibration set과 독립 validation set을 분리한다. 비식별 변수·상관·parameter bound·residual structure와 extrapolation 한계를 표시한다. optimizer가 만든 모든 candidate와 model state를 보존한다. 측정이 없으면 synthetic demonstration까지만 닫고 measured identification은 실제 외부 gate로 남긴다.

### sensitivity/UQ/surrogate/multiobjective/MDO

먼저 독립 analytical scalar model에서 민감도/분포 propagation/constraint treatment를 확인하고 기존 adapter의 소규모 연구로 연결한다. 표본수와 sampling stopping을 질문에 맞게 정하고 Monte Carlo 몇 번을 포괄 UQ라고 부르지 않는다. surrogate는 held-out prediction error·domain validity·추가실험 전략, 다목적은 Pareto tradeoff와 infeasible 처리, MDO는 disciplines coupling/residual과 consistency를 각각 검증한다. DAKOTA/OpenMDAO/pymoo/TAO/MOOSE는 이 문제 역할과 유지비로 선택한다.

### MOOSE/multiphysics·HPC

실제 필요한 작은 coupled heat/mechanics 또는 PDE 문제로 conservation/reference를 정의한 뒤 MOOSE 선택을 정당화한다. 원격 adapter는 immutable staged input, solver/version pin, scheduler job ID, queued/running/terminal, lost connection과 reconnect, cancel, output collection/hash·partial evidence를 보존한다. SSH/Slurm/PBS 세 종류를 먼저 모두 구현하지 말고 사용 가능한 실제 환경 한 곳을 닫은 뒤 같은 계약으로 확장한다. 없는 cluster에서는 source-only로 정직하게 남긴다.

### 실물과 배포

실물 경로는 장비 자동 제어부터 시작하지 않는다. 먼저 approved external measurements/calibration records를 imported evidence로 연결하여 CAE→측정→비교→새 가설까지 실행한다. 장비가 있고 허가가 확보된 경우에만 안전한 제어/중단과 sensor/time/unit calibration을 추가한다. fixture strength/release에 필요한 실제 material, fastening, machine interface, fabrication, load test, fatigue/durability를 항목별로 닫는다.

현재 public repo에는 secrets/회사 CAD/측정 자료를 넣지 않는다. 개발 소스, private data store, approved archive를 분리하고 exact license/linking/redistribution·telemetry/endpoints/session trace·접근 정책을 검토한다. 중요한 결과는 hash만 remote에 남기지 말고 approved off-machine archive의 실제 bytes와 restore를 검증한다. 신규 host/재부팅에서 start→known scenario→report→stop을 수행하고 사용 설명은 현재 경로만 남긴다.

**요구 매핑**: R01/10–12/17/18/31/32/35/36/39/40/43/45/47–49/51/52. 실제 장비·측정·cluster·조직 승인이 없는 부분은 완료 시점을 임의 산정하지 않는다.

## 12. 검증을 줄이는 것이 아니라 필요한 곳에 묶는 방법

1. **소스 개발 중**: 바뀐 함수/계약의 의미 있는 positive/negative controls, source drift·invalid propagation·범위 충돌만 실행한다. 모든 UI 문구 수정에 수천 Core tests와 native matrix를 반복하지 않는다.
2. **통합 단위당**: shared interfaces가 바뀌면 relevant compatibility suite를 한 번 실행한다. representative native input mapping·field parsing·balance/reference를 묶어 독립 검토한다. 소스 review와 같은 implementation 공식을 복제한 test만으로 native를 대체하지 않는다.
3. **사용자 기능 단위당**: 모델 실제 질문과 같은 GUI 결과, 조건변경·거부·cancel/reconnect, 보고서/retention을 한 acceptance packet으로 닫는다. 관측용 API health는 실행 증거가 아니다.
4. **CI 분리**: docs-only는 문서/manifest/link consistency; changed source는 영향 받는 fast suite; native는 backend/runtime/schema/formulation/IO에 영향이 있을 때 또는 계획된 regression batch. docs containing commit은 원 solver producer·dependency hash에 링크한다. failing cases를 skip으로 숨기지 않고 별도 known-failure issue/실패 packet을 보존한다.
5. **실패 시 bounded 진단**: 첫 실패 후 native rerun 대신 expected/actual/case/source/runtime/raw state를 확보한다. 최대 1개의 focused probe로 가설을 확인하고, 실제 변경이 생긴 뒤 새 ID로 한 번 재시도한다. 같은 원인·같은 입력으로 두 번째 실패면 broad retry를 멈추고 원인분석 packet을 만든다. 이 횟수는 제안된 운영 규칙이며 자동 scientific PASS 기준이 아니다.
6. **보존**: result를 소비할 때 필요한 hash 검증은 유지한다. 전체 store를 매 tiny checkpoint마다 반복 복사/해시하지 않고 immutable run manifest와 stage-specific before/after를 이용한다. 전체 store 변경을 감시하는 주장과 이미 닫힌 experiment subtree의 불변성 주장을 혼동하지 않는다.

완전한 외부 reference가 있으면 재사용한다. `docs/CONTACT_ACCEPTANCE.md:96–106`의 Code_Aster SSNP121A 원본 comm/MED/정의와 analytical pressure/displacement는 실제 retained 사례다. `docs/MIDAS_BENCHMARK_REVIEW.md:15–29`의139 구조+18 CFD 조사와 NAFEMS catalog는 source inventory이다. 전체 원도면·edition·재료·하중·BC·measured response·tolerance가 없는 case는 실행하지 말고 필요한 근거를 먼저 확보하거나 완전한 accessible reference를 선택한다. NAFEMS R0026/R0081 같은 catalog 항목을 “NAFEMS 검증 완료”라고 부르지 않는다. 하나의 다른 response나 다른 formulation을 원 benchmark 결과에 대입하지 않는다.

## 13. 실행기·명령·서비스 경계 — 구현 담당자용

아래는 읽은 현재 소스에 있는 경로다. 본 감사에서는 실행하지 않았다. 값이 확정되지 않은 owner/auth/project path를 추측해 복사 실행하지 않는다. Root가 기존 승인 configuration을 확인하여 각 new run에 정확한 paths를 채운다.

| 목적 | 현재 경로/제어 | 필요한 주의 |
|---|---|---|
| 공식 runtime start/status/stop | `scripts/openscience-server-local.ps1 -Mode Start/Status/Stop` | Research, FixtureRefinement, ChatGPT, approved model, existing auth/project, new run/store/source explicit. 기본 Ollama/Acceptance 값에 의존 금지 |
| 공식 attached question/receipt | `scripts/openscience-local.ps1`, trusted `scripts/lab-openscience.ps1` | 기존 owner/source/descriptor guards·same-session/idle 확인 재사용 |
| Lab current bridge | `python -m apps.lab --store <새 WSL store> --port <선택 port> --openscience-owner <동일 runtime owner의 WSL path>` | `scripts/local.ps1 -PythonArgs`로 기존 WSL runtime/environment/Git bridge 사용 가능. auth contents를 전달하지 않음 |
| 현재 쉬운 Lab 실행기 | `scripts/lab-local.ps1 -Store ... -Port ...` | 현 source는 owner 인자를 전달하지 않음. S1에서 옵션/통합 시작 보완 필요 |
| 상태/조회 | `GET /api/overview`, `/api/research`, `/api/jobs/<id>`, `/api/experiments/<id>` | listener와 owner 확인 후 사용. snapshot은 source/numerical PASS 대체 아님 |
| 사용자 작업 | UI→`POST /api/jobs` operation+arguments | existing token/origin/single-writer checks 유지. audit에서는 POST하지 않음 |
| 취소 | UI→`POST /api/jobs/<id>/cancel` | request/observed/native cleanup/terminal 분리; 즉시 종료라고 약속하지 않음 |
| 결과 내보내기 | `GET /api/report/<id>.html/.json/.zip` | exact parent/artifact hash 유지, approved archive restore 별도 |
| 직접 Core 탐색 | CLI `doe plan/run/inspect`, `optimize plan/run/inspect`, existing model-analysis/PDE | 사용자 UI와 같은 Core·store·새 IDs. AI profile 범위와 direct Core availability 구분 |

표시된 URL은 예시 경로이며 **현재 켜진 서비스 주소가 아니다**. Root의 2026-10-05T04:19:50–56Z observation에는 지정된4098/4099/8766/8775/8778/8779/8780/8781 Windows listener가 없었다. 가동 전 owned source/store 확인부터 해야 한다.

## 14. Goal·heartbeat와 장시간 supervision의 완료 규칙

Root 전달 사실: 기존 미완료 goal이 BLOCKED이고 새 create_goal 호출은 그 때문에 거부되었다. 이를 지우기 위해 미완료 목표를 COMPLETE라고 속이면 안 된다. 현재 tool의 user-controlled resume/clear 경계를 그대로 보고한다. 기존30분 heartbeat는 새 사용자 연구 목적/완료조건으로 업데이트되어 ACTIVE가 확인되었다. **ACTIVE heartbeat는 새 goal 활성화나 서비스 실행을 의미하지 않는다.** 본 감사는 goal/automation 도구를 변경하지 않았다.

heartbeat의 역할은 (a) 새 terminal/evidence/meaningful state change 알림, (b) 실행 가능한 다음 단계에 대한 안전한 재개, (c) 사용자 입력이 실제 필요한 외부 gate만 알리는 것이다. 아직 진행 중이거나 변화 없는 상태에서는 반복 “여전히 실행 중” 알림을 내지 않는다. 새 raw stage/log/CPU progress가 없으면 오래된 RUNNING을 진전이라고 표시하지 않는다. desktop/WSL이 꺼졌을 때 자동화가 실제 작업을 했다고 말하지 않는다.

실행 전 각 단계에 **done predicate**를 남긴다. 예: `question received + exact approved profile + native child/result + valid response/reference checks + same-record GUI + changed condition + terminal/cancel lifecycle + old artifacts preserved + report accessible`. 적용되지 않는 부분은 그 이유를 적는다. 문서 커밋, test40 PASS, solver exit0, poll 성공, 질문에 답변이 생긴 것 하나로 goal을 닫지 않는다.

장기 전체 목표는 Phase1–7/52의 남은 항목이 실제 닫힐 때까지 유지한다. 물리/조직 외부 gate는 실제 사용자 입력/외부 변화 없이는 완료할 수 없다. blocked는 구체적 외부 gate에만 사용하고, 어려운 수치 문제·짧은 남은 시간·검증 대기만으로 전체 개발을 방치하는 상태로 쓰지 않는다. 기능적으로 독립적인 다음 작업이 허용되어 있다면 정확한 검증 대기 상태를 남기고 진행한다.

## 15. Root가 다음에 실제로 할 첫 묶음

1. 현재 fine의 stale state·absent processes와 원인 UNKNOWN을 새 봉인 관찰로 현재 queue에 반영한다.
2. reviewed four-file field kernel을 source-only 의미로 보존·통합할 준비를 하고, fine actual acceptance와 혼동하지 않는다. 사용자가 보게 될 assembly mechanics 선언을 함께 정한다.
3. S1 default launcher+readiness/capability와 S2 retained human07 result scene·convergence label·답변 layout를 bounded 구현한다. 운영·field 공유 경계 변경만 relevant checks/독립 리뷰한다.
4. S3의 durable terminal/reconnect를 최소 범위로 구현하고 tiny process gate를 닫는다. 그 전의 비싼 fine blind replay는 하지 않는다.
5. 같은 clean source에 승인5.6Sol/FixtureRefinement/새 store를 하나 열어 첫 사용자 시나리오를 실제로 마친다. user intervention, metrics, scene/links, elapsed/resource, old evidence, exact stop을 한 packet으로 기록한다.
6. 그 결과를 사용자에게 보여준 뒤 S4 actual assembly patch→mechanics→Research와 기존 Phase3–7 미완료 기능을 위 순서대로 계속한다. 성공하지 못한 부분은 구체적인 다음 수정으로 연결하며 전체 scope를 축소하지 않는다.

이 순서는 “전부 검증한 뒤 사용할 수 있게 만들기”를 반복하지 않고, 사용자가 쓸 수 있는 연구 기능을 만들면서 그 기능에 필요한 정확한 수치·운영 검증을 함께 닫기 위한 것이다.

## 16. 후속 현재정정 — Root goal ACTIVE

1차 봉인 뒤 Root가 새 실제 get_goal에서 미등록 상태를 확인하고 목표 생성에 성공했다고 전달했다. 현재 Root 목표는 **ACTIVE**(createdAt1791174622, 생성 당시 tokensUsed0)이다. 목표에는 실제 사용자 CAE 연구 흐름과 전체52·Phase1–7이 포함된다. S0 및 14절의 “기존 BLOCKED/새 생성 거부”는 보존할 과거 사실이며 현재 상태를 가리키지 않는다. 새 goal과 이미 ACTIVE인30분 heartbeat는 서로 다른 상태다. 이제 미등록/거부 해결을 다음 개발 gate로 되풀이할 필요가 없다.

개발 순서는 Root가 채택 예정인 S1 시작·연결/S2 결과 맥락/S3 실행 복구를 먼저 concrete user flow로 닫는 것이다. 내부 독립 Astra 검토와 연구용 approved5.6Sol은 계속 분리한다. 목표 등록 성공이나 plan 채택을 구현/실제 연구/전체52 완료로 바꾸지 않는다. 앞서 기록한 서비스 ports 없음·fine 종료원인 UNKNOWN·Main815/current candidate source-only 판정은 별도 새 실행 증거가 나오기 전까지 유지한다.

이 정정은 Root가 보고한 실제 tool 결과에 근거한다. 감사자의 별도 read-only goal 조회는 null이어서 Root goal의 직접 재확인으로 표현하지 않는다. 생성 결과 원기록을 Root가 추가 봉인하면 최종 supplement에서 exact path/hash로 연결한다. 1차 receipt/manifest는 보존하고 2차 receipt가 이 문서의 최신 digest를 제공한다.


최종 출처 보충: Root의 2026-10-05 04:31:51 UTC 실제 get_goal 봉인 기록 ../root-observation-01/GOAL-ACTIVE-OBSERVATION-01.json을 읽고 SHA-256 0d3d493c7c8199fe36da1075330385115495422a1f35934e2de4a554f39ef6ea 일치를 확인했다. 해당 관찰의 Root goal.status=active, createdAt1791174622이며 tokensUsed22291은 생성 후 관찰값이다. 이는 이전 생성 당시 tokensUsed0과 모순되지 않는다. 별도 auditor context의 null과 구분하며, goal ACTIVE가 서비스 readiness나 numerical PASS를 뜻하지 않는 판정은 유지한다.
