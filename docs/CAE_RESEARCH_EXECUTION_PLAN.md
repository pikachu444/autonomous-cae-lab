# 실제 CAE 연구 실행 계획과 현재 작업

현재 계획의 단일 기준입니다. 기존 52개 요구사항·Phase 1–7·ADR은 계속 적용됩니다.
독립 Astra/high의 [감사 보고서](reviews/20261005-astra-high/READONLY-AUDIT.md)와
[상세 개선 계획](reviews/20261005-astra-high/IMPROVEMENT-PLAN.md)을 Root가 읽고 아래 순서를 채택했습니다.
상세 계획에는 단계별 개발·수치 검증·사용자 인계 기준, 의존성, R01–R52 매핑과 추정 자원이 있습니다.
집중 작업일 추정은 완료 약속이 아닙니다. actual run 비용을 측정해 조정합니다.

## 현재 판정

- 의미 있는 실제 연구 프로토타입. 일부 단일 지지부·PDE·재료·접촉 연구는 실행 기록이 있습니다.
- 현재 사용자 서비스 완료 아님. 실제 기본 연결·질문·부모 CAD 표시의 bounded gate는 통과했고, 전체 해석장 표시와 장시간 종료·재접속은 OPEN입니다.
- 전체 조립체 mechanics, broader Phase 3–7, 실물/배포 요구 OPEN. 강도·실물은 UNKNOWN/NOT_RELEASED.
- Goal은04:31:51Z 실제 ACTIVE였으나05:13:57Z 다시 BLOCKED로 관측됐습니다. 전환 원인 UNKNOWN, 사용자/시스템 재개 제어. 기존30분 후속 작업 ACTIVE와 실제 개발·서비스 가동은 별도입니다.
- clean source `c94da4e86be05146353e716b4fba8d71a96b7246`/새 run02에서 승인5.6Sol 연결, 실제 CAD 변수 조회 질문, 같은 resident IDLE/cleanup, foreground Ctrl+C/owned STOPPED를 확인했습니다. 질문310.124764초의 지연 원인은 NOT_ISOLATED입니다.
- 같은 UI source/새 view store에서 기존 human07의 올바른 부모 CAD·caption을 확인하고, store 전환20초 뒤 도착한 이전 성공 응답의 유입 차단을 확인했습니다. 기존72파일/40,924,681B는 그대로입니다. 이 검증 후 두 서비스는 의도적으로 종료했습니다.
- fine1.5 이전9PID 없음/terminal receipt 없음/old RUNNING 보존. 완료·종료 원인 UNKNOWN_NOT_QUALIFIED/UNKNOWN.
  같은 Gmsh import를 원인 변화 없이 재실행하지 않습니다.
- source-only kernel은 `bffbd807c56d9aa2cf817f4f6f5bfcbfb54bae77`에서 보존. 실제40 tests와 closed-coarse topology를 새 native field solve로 해석하지 않습니다.

## 순차 작업표

| 순서 | 작업과 사용자 결과 | 상태/담당 | 완료 기준 |
|---|---|---|---|
| S0 | 실제 실행·중단·목표 상태 복원 | READONLY_OBSERVED / Root | 지정PIDs/ports/원기록 구분, old outputs 보존. 종료 원인 UNKNOWN 유지 |
| S1 | 한 실행 동작에 승인 OpenScience+Lab 연결 | BOUNDED_LIVE_PASS / Root | 새 run02 실제 질문·도구 결과·resident idle·owned Stop 확인. active-job/native 취소·재시작은 S3 |
| S2a | 부모 CAD와 정확한 수치 검사 이름을 결과에 표시 | BOUNDED_FRESH_GUI_PASS / Root | 실제 부모·revision·manifest/caption과 늦은 성공 응답 차단 확인. late-error/detached branch는 source controlled-DOM 증거 |
| S2b | 실제 해석 mesh·하중·구속·U field·변형 표시 | BOUNDED_NATIVE_OUTPUT_PASS_PUBLIC_MODE_GUI_OPEN / Root | clean8c/기존4mm mesh1개/실제7715절점 U·원래DAT동일·Astra0P1/P2. 공개 selected-mode/Core·Research·같은 GUI는 다음 별도 gate; global sweep 없음 |
| S3 | 종료·강제 중단·재시작 상태와 admission 복구 | NEXT / Root shared execution owner | tiny crash/identity matrix, append-only reconciliation, real native cancel/reconnect, old evidence 보존 |
| U1 | 첫 간단한 사용자 CAE 연구 | WAITING_ON_S1_S2_S3 / Root | 아래 한 사용자 흐름을 실제로 끝내고 독립 검토·같은 GUI 결과·보고서로 확인 |
| S4a | coarse native affine full-field patch | OPEN / Domain·adapter | source kernel 재사용, U/strain/stress/energy/force/moment 전체 참조 비교. actual mechanics와 구분 |
| S4b | 원본7부품 실제 조립체 연구 | OPEN / Domain·adapter·Root | 부품별 재료/접촉/하중·관측점 선언, load path·평형/에너지·모델 목적별 검증, actual Research 연결. 전체 재메시 비교는 의무 아님 |
| S5 | Phase3의 남은 실제 탐색 연결 | OPEN | 기존 LHS/DE 재사용, 유효 response·budget/convergence·후보비교·재개; mixed variables 후속 |
| S6 | Phase4 PDE 연구 흐름 | OPEN | 지원 form별 actual field/reference/거부·mesh/time/MPI 검증, 변경·비교·AI 해석 |
| S7 | Phase5 재료·접촉의 FE coupling | OPEN | 재료점→구조 연결, history/energy/finite strain·native convergence와 물리 적합성 구분 |
| S8 | Phase6 실제 explicit 연구 | OPEN | 공식 설치 문제 진단, surface contact/preprocessing/history/animation·momentum/energy 비교 |
| S9 | Phase7 측정 inverse/UQ/다목적/HPC | OPEN | 기능별 작은 end-to-end 연구, 실제 측정·원격은 확보된 환경으로만 검증 |
| S10 | 보존·복원·회사 배포·실물 연결 | OPEN / 외부 gate 별도 | approved off-machine bytes restore, 실제 측정/장비/조직 승인; 외부 자료를 임의 생성하지 않음 |

## U1 실제 사용자 시나리오

질문: “롤러 지지대 폭을32mm에서38mm로 늘리면 처짐과 재료 사용량이 어떻게 바뀌나요?”
이미 정의한 단일 지지부 시나리오의 가상 재료·고정 바닥·24mm saddle 하중을 화면에서 확인합니다.
임의 물성 추정은 하지 않습니다. 각 CAD revision에서 목적에 맞게 선택한 한 mesh의100N 실제 CalculiX 결과,
전체 U와 signed Uz, 체적, XYZ 반력·입력/단위/구속/하중 분포를 비교합니다. geometry가 바뀐 revision에는
그 형상에 대응하는 mesh가 필요하지만, 전체 모델의 여러 mesh 재해석은 기본 사용자 완료 조건이 아닙니다.
기존 human07의4/3/2mm와5% screen은 해당 benchmark 기록에만 남깁니다. peak stress는 invalid diagnostic입니다.
현재 fixture adapter는2–8개의 mesh를 요구하므로 단일 mesh 연구 모드는 아직 OPEN입니다.
S2b 전체 U 출력 보존을 통합한 다음 명시적인 opt-in 단일 mesh 계약을 순차 구현·검증하며,
historical refinement descriptor/판정/수치 문턱을 바꾸거나 단일 mesh를 수렴 PASS로 만들지 않습니다.
후속150N 결과의 선형 비례를 raw 정밀도에 맞게 대조하고 조건 변경을 새 record로 보존합니다.
기존 SciPy DE(population5/max_generations1/seed13)로 유효 응답을 쓰는 연구용 탐색을 실행합니다.
budget 종료/`converged=false`/best observed를 최적해 확정과 구분합니다. DOE는 현재14-tool profile에 없습니다.
AI가 같은 record를 해석하고 사람이 모델·입력·결과·한계를 확인하며 같은 보고서를 저장·다시 엽니다.
rejected input에서는 solver 미실행, 취소 요청과 실제 종료, stale/restart 상태 및 old digest 보존도 확인합니다.

## 작업과 검증 원칙

사용자의2026-10-05 지시에 따라 전체 조립체·full model·explicit에 의무 mesh-convergence sweep을
적용하지 않습니다. 적절한 기존 mesh를 재사용하고 입력/재료/요소/접촉/구속/하중 전달과 필요한 결과를 봅니다.
정적은 반력·평형·변형 및 적합한 참조, 동적/explicit은 시간 증분·추가 질량·hourglass/에너지·접촉·
운동량/변형 이력과 확보된 실험/참조를 Domain이 목적별로 평가합니다. 각각은 구현·관측한 항목만 PASS입니다.
mesh sensitivity는 response나 관심 국부 현상/불확실성이 요구할 때 선택하고 범위·비용·판정 기준을 먼저 정합니다.
기존 canonical benchmark의 정확도/mesh/time 조건, 고정5%/1% screen 및 실패 결과를 없애거나 완화하지 않습니다.
[ADR0035](../ADR/0035-purpose-specific-model-verification.md)는 이 계획 우선순위와 아직 미구현인 단일 mesh 경계를 명시합니다.

Root가 설계·공통 인터페이스·최종 통합·Git을 소유합니다. launcher와 UI 후보 담당은 서로 다른 파일에만 씁니다.
내부 감수 Astra/high와 연구용 `openai-codex/gpt-5.6-sol`/기존 ChatGPT 인증을 구분하고 자동 대체하지 않습니다.
실패 후에는 expected/actual/input/runtime/raw packet으로 가설을 좁힌 뒤 변경된 조건에서 새 run을 만듭니다.
docs/UI 수정마다 전체 native matrix를 반복하지 않고 영향 있는 source·사용자 흐름 검증을 묶습니다.
815 exactCI37230315608의7SUCCESS/3FAIL(Core4289PASS/5SKIP)은 남아 있으며 새 source의CI PASS가 아닙니다.
문서·tests·solver exit0·AI 답변 하나로 전체 기능/goal을 닫지 않습니다. 실제 다음 acceptance의 evidence가 기준입니다.
현재 역할/계획표를 여기서 갱신하고 역사 prose는 여러 current 문서에 복제하지 않습니다.

## S3 최소 복구 경계에 대한 추가 독립 의견

Astra/high 후속 의견을 채택합니다. 먼저 HTTP job의 실행 전 journal, 재시작 후
RECOVERY_REQUIRED/UNKNOWN 표시, 과거 결과 조회와 해당 HTTP 저장소의 새 실행 차단을 구현합니다.
HTTP worker, 정확한 OpenScience session/MCP resident, owned native process 상태를 각각 확인합니다.
process 부재·메모리 IDLE·결과 파일 존재만으로 완료를 추정하지 않고 원기록을 보존한 reconciliation을 추가합니다.
정상 HTTP 부모가 MCP 자식의 작업을 기다리므로 공용 store lock을 양쪽에 단순 추가하면 순환 대기 위험이 있습니다.
이는 설계 위험이며 재현된 deadlock은 아닙니다. 전체 store의 교차 프로세스 single-writer 보장은 별도 계약과 gate입니다.
worker 시작 직전/직후, child 실행 중 재시작, 완료 직후 terminal 저장 전 crash, 다른 owner/PID 재사용을 tiny process로 검증하고
그 뒤 대표 native의 재접속·중복 차단·partial 보존을 확인합니다. 새로운 범용 scheduler부터 만들지 않습니다.

## 독립 감수 출처와 보존

감수 기준 Main815e207 / upstream3e48bf6. 최종 private receipt02SHA=e7dcdbfca100b70406c93c0ea3edf2f7f7ca0b1bc699a78fec3a6899cdbf9334.
공개 사본은 LF만 정리했으며 원본 사본/digest를 별도 보존합니다. source/실행 증거 전체87파일을 원격 복원했다고 주장하지 않습니다.
[docs/reviews/20261005-astra-high/LIVE-OBSERVATION-ADDENDUM.md](reviews/20261005-astra-high/LIVE-OBSERVATION-ADDENDUM.md)에
실제 Root 관찰과 현재 Goal 정정 출처가 있습니다. ACTIVE 관찰은04:31:51Z의 역사입니다. 최신05:13:57Z Root get_goal은 BLOCKED이며 원인은 UNKNOWN입니다.

## S1/S2a source-only integration checkpoint

`benchmarks/records/20261005-cae-usability-source-r01.json` binds the reviewed8working-file bytes,
actual selected parent/source dirty state, retained Root35mock/46controlled-DOM passes and4syntax checks.
Astra/high caught the verifier's hardcoded historical commit; Root's new correction binds full actual HEAD,
fixture/head/index and unchanged working source snapshots. Incremental independent review closed thatP2.
Eight protected native files and52ledger rows remain unchanged; no solver/provider/runtime was run by source checks.
Actual external approved path settings validate, but this is NOT readiness. Next is actual clean-source
new-store one-action Start/Question/Stop plus fresh same-record GUI. S2b fields and S3 recovery remain OPEN.
Previous exact bff CI37265205047 closed7success/3failure: explicit official download404, Aster Fz numerical
classification and vector PDE classification. Raw failed logs retained; deeper numeric causes UNKNOWN.
No previous CI or source-only gate is promoted to current full service/solver/engineering acceptance.
## S1 actual attempt01 and bounded host-path correction

Clean c21bc317/new cae-research-usability-20261005-01 actually started owned OpenScience4096 and Lab8766.
Research remained UNAVAILABLE: the default ProgramFiles PowerShell7 path is absent on this computer.
The host facade now forwards the existing PSHOME/pwsh.exe through the existing CLI argument. No installation/auth/model changed.
Root41mock controls and independent Astra/high source review PASS; exact idle Ctrl+C/foreground0/ownedSTOPPED is retained.
This is not a connected-question or active-job cancel PASS. Preserve run01 and require NEWrun02 with clean corrected source.
Record: `benchmarks/records/20261005-cae-research-host-bridge-source-r02.json`. S2b/S3/U1 remain OPEN.

## S1/S2a actual clean-source checkpoint

Clean c94/new `cae-research-usability-20261005-02` completes one actual ordinary Lab question,
one `caelab_parameters_discover`/eight CAD variables, readable answer and same resident/store IDLE cleanup.
Owned foreground Ctrl+C finishes0/STOPPED. Actual310.124764s question latency is retained; cause NOT_ISOLATED.
Separate fresh `cae-result-view-20261005-01` serves human07 read-only on the same UI source:
correct parent/revision/manifested preview/caption, same7UNKNOWN/NOT_RELEASED, actual late-success store-switch guard.
All72 historical files/40,924,681B are unchanged. Source producer162 and display sourcec94 are distinct.
Late-error/detached renderer branches are controlled-DOM source checks, not new real-network qualification.
S2b full-U/native field/view and S3 active-job/native cancel/durable restart/U1 remain OPEN. Services were stopped after tests.
Root private receipts: `host-bridge-correction-root-01/S1-LIVE-RECEIPT-03.json` SHA57ffae167fd9f02788feb5038d91eb6508e3424e17d8b7d8bca8825fa42ad6ef,
`result-context-live-root-01/RECEIPT.json` SHA40a046f7ba1d8d822740a314f5c5afae3c03d59e6cdb19ed246cb70a1a95f7eb.
Both are under `artifacts/development-cae-usability-audit-20261005-01/`; retained locally, not a remote raw restore claim.
Exact c94 CI37269269559 completed7SUCCESS/3FAIL: native/source/Core/registration/structural/DOE/optimization succeeded;
explicit download, Code_Aster and vector PDE jobs failed. Whole CI is not PASS; fresh actual failed logs are retained separately.

## S2b full-U source checkpoint

Bounded reviewed5files advance fixture adapter4→5: all-node FRD U request,
pre-native mesh/deck/saddle pins, strict native2.21 geometry/full-field reader,
additive `fea_field.json`/manifest association and TEST_ONLY compatibility controls.
Existing loaded DAT U/BASE RF/mechanics/native commands/statistics/thresholds remain.
Root Primary175PASS/3optionalSKIP14.81s; candidate actual legacy3PASS/15old files unchanged;
independent Astra/high source0P1/P2. No complete fresh native output or field GUI is implied.
Record: `benchmarks/records/20261005-fixture-full-field-source-r01.json`.
The following native checkpoint closes that output-only gate. The separate opt-in selected-mesh public contract and field GUI remain OPEN. No legacy U inference or remesh.

## S2b 실제 기존 메시 한 개의 전체 U 출력 checkpoint

clean `8c0233b9b08dec4d5fe2a39126e137c4afa20138`/새 `fixture-full-field-native-20261005-01`에서
기존 human07의4mm 메시·역학 입력을 재사용했습니다. 실제 CalculiX2.21 실행1회/2.701933초/exit0,
재메시0/모델 호출0.7715절점/23145실제 U 성분·4422TET10·1840CPS6·고정1057/하중123를 보존했습니다.
원래 DAT와 새 DAT는 바이트 동일, signed loaded UZ=-0.005642080mm, XYZ반력 상대 잔차4.389558e-9<=기존1%입니다.
역학 입력을 되돌리면 원본과 바이트 동일하고, 기존72파일/40,924,681B도 그대로입니다.
독립 Astra/high는 제품 parser 없이 원본을 별도로 읽어 bounded output replay PASS/0P1/P2를 확인했습니다.
record: `benchmarks/records/20261005-fixture-full-field-native-r01.json`.
이 실행은 OUTPUT_ONLY_REPLAY_NOT_CORE_EXPERIMENT입니다. 공개 단일 mesh/Core·Research 실행,
새 CAD-to-FEA·field GUI·S3·전체U1·52개 요구·강도 승인은 OPEN/UNKNOWN/NOT_RELEASED입니다.
version-only `ccx -v`의201을 드라이버가 실패로 처리한 첫 시도와 교정본을 모두 보존했습니다. native solve 실패가 아닙니다.
정확한8c CI37275234604는7SUCCESS/3FAIL이며 explicit 설치404/Code_Aster/vectorPDE raw 실패 로그를 새로 보존했습니다.
전체CI PASS가 아니고 후자 두 수치 실패의 깊은 원인은 아직 NOT_ISOLATED입니다.
다음은 승인된5파일 selected-mode source 단위→Root의 공통 Research admission→실제 공개 실행/같은 field GUI입니다.
