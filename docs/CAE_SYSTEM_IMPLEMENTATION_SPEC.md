# Autonomous CAE Lab 구현 명세

명세 기준: main `4843c66`, 초기 범위는 PROJECT_SCOPE.md의 R01–R52와 Phase 1–7이다.
실행 순서는 CAE_RESEARCH_EXECUTION_PLAN.md 하나로 관리한다. 이 문서는 기존 코드를
교체하는 새 플랫폼 설계가 아니라, 재사용할 구현과 채워야 할 공통 기능의 명세다.
행마다 적은 보유 구현은 전체 요구사항 완료 판정이 아니다. 실제 실행 기록과
사용 범위가 일치할 때 해당 기능의 acceptance만 닫는다.

## 1. 사용자 산출물과 개발 기준

사용자는 한국어 연구 질문에서 시작해 모델을 만들거나 가져오고, 명시적 물성·
좌표계·하중·경계조건·접촉을 편집한다. 지원되는 솔버를 선택해 해석하고, 같은
모델 개정의 전체 필드·이력과 가설/관측을 비교한다. 조건 변경과 수치 탐색,
OpenScience 해석, 저장·재열람·재현·취소·재접속까지 한 연구 흐름으로 연결한다.

이전 작업 방식의 교정:

- 요구사항→기능→구현 인터페이스→실제 사용자 동작→완료 조건을 먼저 연결한다.
- 기존 계획의 존재를 충분한 명세나 개발 완료로 간주하지 않는다.
- 큰 기능 묶음을 구현·통합·실행·수정하고 묶음 마지막에 독립 검수한다.
- 예제 생성 코드, 단위테스트 개수, solver exit0, 작은 감수 반복은 제품 기능
  완성을 대신하지 않는다. 예제는 특정 기능/결함의 검증 근거로만 사용한다.
- 공통 구조를 먼저 연결하고 순차적으로 보완한다. 연결 장애와 외부 자료 부재가
  의존하지 않는 소프트웨어 개발 전체를 중단시키지 않는다.
- 전체 모델/explicit의 의무 mesh convergence sweep을 요구하지 않는다.
  목적에 적합한 메시와 반력·에너지·접촉·변형 이력 및 확보된 참조를 사용한다.

## 2. 공통 객체와 책임

| 객체/입력 | 공통 출력·동작 | 구현 소유자/재사용 포트 |
|---|---|---|
| Study: 질문·가설·목표·관측 출처 | 안정적인 study ID와 append-only 연구 기록 | Core `Lab.create_study/inspect_study`; OpenScience는 가설·계획·해석 |
| CAD model: 보존 원본·final 선택·변수 | native model ID, editable revision, discovery 후보와 등록 변수 | `CADAdapter`, FreeCAD/CadQuery/assembly adapters; registry가 연구 ID로 매핑 |
| Declared model: geometry/mesh/law/BC/load/IC/output | 명시적 model revision과 backend별 admission | `ModelAnalysisAdapter/ParameterizedModelAdapter/PDEAdapter`; Domain이 모델 의미 검사 |
| Analysis conditions: CAD revision·부품/면·재료·성분·출처 | revision-bound 조건 기록, 지원 여부, native settings 변환 | Core `analysis_conditions`; `ConditionCatalogAdapter/ConditionAnalysisAdapter` |
| Experiment: 동결 입력·backend·실행 요청 | 새 실험, proposal/result/ledger와 원본 artifact | Core `Lab.run_experiment/run_analysis/run_model_analysis/run_pde`; adapter가 native 실행 |
| Result: 값·단위·validity·부호/measure·시간/위치 | 전체 field/history, compact summary, 비교와 보고서 | Core envelope; family-owned response readers |
| Observation: 위치·성분·단위·축·조건·실측/가정 출처 | 조건·축 불일치 보존, 원 응답과 차이/잔차 | `response_comparison`, `observation_target`; Domain가 응답 의미 보존 |
| Campaign: variables·objective·constraints·seed·budget | 동결 후보/피드백/상태, 재개 가능한 DOE/search/report | 기존 LHS/DE 및 `campaign/model_doe/optimization/multiobjective` |
| Execution: 정확한 run/store/source/owner | 진행·취소요청·종료 확인·부분 결과·복구 상태 | 기존 LabService/jobs/execution_control; remote executor는 별도 adapter |
| Evidence/Validation | 근거와 판정 분리, invalid/UNKNOWN/NOT_RELEASED | Core storage/outcomes/schema; Domain가 공학 규칙 소유 |

유효하지 않은 입력은 export/downstream 실행을 차단한다. 새 실행은 새 ID/store나
append-only 개정으로 보존한다. native 경로·UFL·solver deck/cards·명령은 adapter가
소유한다. Core나 OpenScience에 특정 솔버 문법을 복사하지 않는다. GUI/CLI/MCP는
같은 Core 포트를 사용하고 같은 원본·개정·결과를 가리킨다.

## 3. 사용자 기능과 완료 조건

| 기능 | 현재 재사용 인터페이스 | 필요한 완성 동작과 acceptance |
|---|---|---|
| 로컬 시작/연구 연결 | `cae-research-local.ps1`, qualified binding, existing OAuth | 한 시작 절차에서 실제 서비스·허용 모델·MCP 연결을 표시하고 같은 연구 기록의 실제 AI 답변을 저장·재열람한다. 설치/인증/모델 임의 교체 없음 |
| 모델/변수 | native import/final/discover/register/refresh/regenerate | 사용자가 원본을 선택하고 후보/범위를 등록해 새 editable 모델을 생성한다. ineffective/invalid/다른 revision을 차단한다 |
| 조건 편집/solver 선택 | 조건 catalog, analysis/declaration ports | 부품/면/그룹·재료·좌표계·BC/하중/접촉 선언이 지원 adapter 입력과 같은 결과에 연결된다. 지원되지 않은 조합을 명확히 거부한다 |
| 해석 실행/장시간 제어 | LabService async jobs, MCP jobs, CancellationToken | 상태 조회는 새 실행을 만들지 않는다. 취소 acknowledgement와 실제 native cleanup을 구분한다. 같은 incarnation 재접속, terminal receipt, crash/UNKNOWN fence와 원 결과 보존을 실제 확인한다 |
| 결과/관측 비교 | field/history/comparison/report readers | 원 부호·measure·단위·위치·시간축의 전체 결과와 명시한 관측을 확인한다. 임의 interpolation/축 정렬/원인 확정 없음 |
| 수치 탐색 | LHS, DE, frozen plans, reports, epsilon campaign | 수치 엔진이 후보를 생성한다. 모든 후보·거부·목표·제약·잔차·상태/seed를 보존하며 같은 모델의 최선 후보/절충안을 다시 연다 |
| 연구 해석 | OpenScience typed profiles / NumericalReports | 승인된 `openai-codex/gpt-5.6-sol`/기존 OAuth로 실제 기록을 읽고 한국어로 가설 차이·한계·다음 실험을 해석한다. 기록 조회를 provider 실행으로 대신하지 않는다 |
| 사용자 화면 | Design/Simulation/Explore/Results/Research | 실제 모델·조건·실행·field/history/report를 조작한다. 내부 JSON/ID를 사용자가 수기 작성해야 하는 흐름을 줄이고 editable native GUI와 같은 artifact를 연다 |
| 원격/병렬/실험 연계 | 기존 source-only executor 후보와 공통 기록 | endpoint/runtime/source/nonce/job 소유권, submit/poll/cancel/collect를 연계한다. 실제 SSH/Slurm/PBS/장비 없는 경우 이 기능의 실제 실행은 UNKNOWN; 다른 로컬 개발을 멈추지 않는다 |

## 4. 기존 backend의 실제 지원 경계

| 계열 | 현재 구현·기록 재사용 | 범용 사용을 위해 남은 소프트웨어 |
|---|---|---|
| CAD | pinned upstream, CadQuery, FreeCAD Part/Sketcher/native upload/final, original assembly | 더 넓은 native topology와 변수/조건 catalog, 일반 모델 입출력/GUI 편의 |
| 선형 구조 | fixture CalculiX와 imported single-solid native mechanics; structural family adapters | 일반 조립/부품 모델의 declared BC/load/material 선택과 통합 admission; 일반 mesh API |
| 비선형 implicit | Code_Aster elasticity/geometric/J2/contact, bounded SVK/Maxwell 재료점 | 일반 물성 법칙/FE coupling, 원 조립체 load-transfer/contact, 더 넓은 사용자 모델 |
| PDE | scalar/nonlinear/rectangle/transient/vector/coupled/imported FEniCSx; selected input DOE | 더 넓은 weak-form/field/BC와 solver-independent 선언, MPI/다른 backend, 실제 넓은 연결. 기존 vector benchmark rejection은 그대로 보존 |
| Constitutive | MFront/MTest/MGIS stress/tangent, finite-strain/SVK/Maxwell, synthetic inverse | 일반 Gauss-point solver coupling, 측정 곡선/다축·시간 이력 식별과 broader law interfaces |
| Explicit | OpenRadioss freeflight/compliant/selected rigid translation, signed load/IC와 전체 이력 | 변형체·표면/회전 접촉·일반 material/failure cards·일반 preprocessing |
| Numerical | LHS/DE, scalar observation residual, regression/holdout surrogate, empirical/Pareto report, declared-distribution UQ, epsilon MOO | discrete/categorical search, field/history objectives, general curve/inverse, Sobol/MDO/PDE-constrained/선택 엔진 비교·채택 |
| Execution | local owned process control, HTTP journal, resident MCP, per-run qualified native binding | 정확한 incarnation 재접속/종료, native-provider control 일관성, executor/HPC actual acceptance |

`observation_target`의 현재 목적은 scalar 한 개다. field/history objectives는 아직
허용하지 않는다. 현재 UQ/감도는 유한 표본·선언 분포·regression/holdout 범위이며
Sobol, 실측 불량 확률, 인과 판정이 아니다. J2는 selected block/axial history,
explicit는 제한된 rigid topology다. AssemblyMechanics의 trusted operator path를
기본 Core/public research로 자동 승인하지 않는다. 보유 기능은 재사용하고,
이 한계를 지운 범용 완료 주장을 하지 않는다.

## 5. R01–R52 추적표

아래는 구현 위치와 남은 산출물이다. 운영 원칙 요구와 기능 요구를 섞어 단순
테스트 개수나 파일 개수로 완료율을 만들지 않는다. PROJECT_SCOPE의 원문과
실행 원장이 권위 있는 범위/근거이며 새 문서는 원문을 삭제하지 않는다.

| 요구 | 보유 구현/책임 | 남은 기능 또는 지속 확인 조건 |
|---|---|---|
| R01 범용 연구 플랫폼 | Core/Domain/adapters/numerical/UI/OpenScience | 아래 큰 기능 묶음의 범용 연결·사용 검증 |
| R02 Top-down 흐름 | `Lab`, typed MCP, research profiles | 질문→실행/결과→해석과 control의 일반 연결 |
| R03 연구와 수치 엔진 분리 | OpenScience + LHS/DE | 추가 탐색 역할을 기존 numerical ports에 연결 |
| R04 기존 fixture 재사용 | pinned `plugins/fixture_design/upstream`, fixture adapters | 원본 behavior/GUI/evidence 유지, 중복 복사 금지 |
| R05 Core/Domain/plugin 분리 | contracts, plugins, adapters | 신규 법칙/조건을 맞는 경계에 추가 |
| R06 Design Parameter Registry | registry/model_parameters/condition_parameters | 더 넓은 type/관계·native reference 지원 |
| R07 CAD 발견·등록·효과 검사 | FreeCAD/CadQuery candidates/final/register | 일반 CAD topology/GUI와 ineffective 판정 범위 |
| R08 단계별 실행 gate | engine/outcomes/adapter preflight | 추가 mesh/solver/복구 경로에도 동일 거부 보장 |
| R09 독립 validation | result schema/outcomes | 미검증 항목 UNKNOWN 및 release gate 지속 유지 |
| R10 evidence 분리 | storage/ledger/native fields/reports | 새로운 참조/관측·calibration 타입과 evidence 연결 |
| R11 재현 가능한 thread | frozen revisions/campaigns/producer/source pins | 공통 executor/native owner/reconnect의 terminal 근거 |
| R12 원본/가공 artifacts | manifests/report export/raw logs | 모든 신규 family 전체 결과와 같은 원본 재열람 |
| R13 GUI/headless 동일성 | native editable CAD/Lab UI/Core | 넓은 family UI/CLI/MCP parity와 사용 절차 |
| R14 implicit 솔버 평가·연계 | Code_Aster/CalculiX adapters/backend research | 일반 비선형/재료/contact 구성과 명시적 범위 |
| R15 explicit 솔버·preprocessing | OpenRadioss adapters/history/Domain | 일반 FE mesh/material/contact/rotation/failure 입력 |
| R16 PDE 계열 비교·user equations | FEniCSx ports/UFL workers/official research | broader weak form/physics coupling/MPI 및 필요 backend |
| R17 MFront/TFEL | material/hyperelastic/viscoelastic/inverse | constitutive FE interfaces와 measured-history 식별 |
| R18 optimizer 역할별 비교 | SciPy adapters/UQ/reports/epsilon | mixed types/Sobol/MDO 및 적합한 추가 engine admission |
| R19 common experiment | schemas/declared_model/analysis_conditions | 부족한 generalized geometry/mesh/execution 확장 |
| R20 common results/validity | result/outcomes/response readers | 넓은 fields/history objectives, 원 measure/축 유지 |
| R21 공통 Python/CLI/MCP | Lab/cli/mcp_server/HTTP | generic mesh, public operation parity, 일반 control |
| R22 확장 구조·재사용 분류 | contracts/adapters/plugins/ADR | 신규 기능도 source copy 없이 포트로 확장 |
| R23 기반 우선 | 기존 schemas/registry/storage/Core | source-only mock을 실제 기능/실행으로 구분 |
| R24 ADR 경계 | ADR0001와 cumulative ADR | material 변화마다 이유/대안/영향/근거 유지 |
| R25 Phase1 연구→CAD | 실제 연구/import/discovery/CAD 기록 | generic 연구 context/조건·실행·control 통합 |
| R26 Phase2 CAD→FEA | child-analysis/native mechanics/fields | 일반 모델·조립 조건/mesh/solver·metrics 통합 |
| R27 Phase3 DOE/최적화 | frozen LHS/DE/native candidates/replay | mixed types/다중 응답/GUI·AI의 일반 campaign 흐름 |
| R28 Phase4 PDE | selected PDE/full fields/observation | broader user form/BC/mesh/solver 사용 흐름 |
| R29 Phase5 implicit | bounded geometry/J2/contact/SVK/Maxwell | 일반 FE laws/contact/assembly coupling/참조 비교 |
| R30 Phase6 explicit | rigid/compliant/selected native histories | 일반 변형체/표면/rotation/material/failure 구성 |
| R31 Phase7 고급 연구 | synthetic inverse/UQ/surrogate/epsilon/coupled inputs | history inverse/Sobol/MDO/solver coupling/HPC/실측 interfaces |
| R32 실험·digital twin | observations/evidence/UNKNOWN gates | typed 측정/장비/calibration 포트; 실제 장비 승인 별도 |
| R33 공학 UI | Design/Simulation/Explore/Results/Research | capabilities와 실제 지원 범위 일치, 통합 작업 공간 |
| R34 자동 검증 | tests/benchmarks/native records/CI | 변경 기능별 실제 비교, 정확한 source CI 실패 수정 |
| R35 환경·license/security | dependencies/research/runtime guard | 배포별 license/data isolation 검토; 회사 승인 UNKNOWN |
| R36 repo/local 관계 | main/Git/pinned submodule/local stores | public repo에 회사 데이터·secret 배제, private 선택 별도 |
| R37 목적별 지원 에이전트 | bounded research/implementation/review | 큰 묶음의 독립 조사와 마지막 검수; 작은 승인 반복 금지 |
| R38 Root 전체 책임 | shared interface/design/integration/Git | 전체 범위 추적과 최종 실제 acceptance 책임 지속 |
| R39 공식 solver/PDE/재료 조사 | backend/MIDAS/official reference research | 부족한 범용 기능의 공식 source 조사와 채택 근거 |
| R40 역할별 optimizer 조사 | engine contracts/research | 문제 유형별 추가 engine 선택과 실제 검증 |
| R41 기존 source/CI audit | pinned upstream/retained audits/tests | 기존 behavior/변경 영향·debt 확인 후 통합 |
| R42 역할 분리·통합 | Root+bounded support | 동일 파일 쓰기 충돌 차단·증거 Root 판단 |
| R43 중요 구현 독립 검수 | retained final bundle reviews | 큰 변경 통합·실행·수정 후 한 묶음 검수 |
| R44 shared owner | AGENTS/Root ownership | schemas/Core/registry/provenance 동시 쓰기 금지 |
| R45 통합 판단 | ADR/contracts/evidence | source/native/UI/물리 판정 구분·충돌 해결 |
| R46 적합한 추론/역할 | Root 설계·bounded 지원 | 모델 이름보다 구현·실행·검증 근거 우선 |
| R47 중요한 지식 보존 | ADR/records/HANDOFF/CURRENT_STATE | 채택/기각·실패·다음 기능을 최소 기록으로 보존 |
| R48 실제 구축·실행·수정 | existing native/provider/GUI records | 새로운 기능 묶음도 구현과 실제 사용으로 닫기 |
| R49 state recovery | AGENTS/HANDOFF/현재 원장 | 미확인 대화/옛 실행을 새 성공 근거로 쓰지 않기 |
| R50 최초 수직 흐름 | 초기 CAD/evidence 및 후속 실제 연구 | 최초 예제를 다시 만들지 않고 일반 기능으로 확장 |
| R51 architecture change 관리 | cumulative ADR/contract/tests | 이유/대안/requirement·contract impact와 실제 evidence |
| R52 연결성과 사용성 우선 | common research loop/actual records | 전체 목표를 예제·문서·검사·카탈로그로 대체하지 않기 |

## 6. 공통 실행/연구 묶음의 이번 구현 계약

1. 원 controller/native incarnation을 readiness 시점의 retained handle로
   관찰한다. 기록의 PID는 새로운 process/Job 소유권을 만들지 않는다.
2. cancellation/stop attempt와 confirmed cleanup을 별도 상태로 둔다.
   부분 중단·refusal·관찰 실패는 UNKNOWN/CLEANUP_PENDING이다. STOPPED는
   요청한 원 launcher/native와 해당 native가 만든 MCP Job의 종료 근거가 필요하다.
3. 기존 resident/HTTP journal을 재사용한다. HTTP claim을 전체 Core/store lock으로
   확장해 부모와 MCP 자식이 서로 기다리게 만들지 않는다. 옛 R2 후보는 차이를
   검토해 통합하며 원본 후보/실험은 보존한다.
4. source/profile/default authentication pins는 strict하게 유지한다. 새 per-run
   qualified binding은 기존 승인 OAuth를 사용한다. 모델 대체·auth migration 없음.
5. 수치 연구 기록은 기존 실제 producer를 유지한다. 새 reader/AI 실행과 native
   producer source를 구분하고 SYNTHETIC/가정 분포/invalid 응답을 그대로 전달한다.
6. capabilities는 등록 API, 현재 profile admission, 실제 지원 범위와 일치해야
   한다. bounded field/history/UQ/MOO의 존재를 PLANNED로 잘못 표시하거나,
   method 존재를 native 실행 가능/범용 완료로 확대하지 않는다.
7. source parity/MCP consumer의 통합 오류를 교정하고 실제 시작→같은 기록 연구→
   재열람→owned 종료/재접속을 확인한다. source controls만으로 완료하지 않는다.

실제 성공·실패·미검증, 입력/원 artifact 보존, exact source/CI는 관련 원장에
기록한다. 이 명세 작성 자체로 어떤 Phase나 전체 52개 요구사항을 완료 처리하지 않는다.
