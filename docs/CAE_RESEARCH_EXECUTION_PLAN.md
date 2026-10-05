# 실제 CAE 연구 실행 계획과 현재 작업

현재 계획의 단일 기준입니다. 기존 52개 요구사항·Phase 1–7·ADR은 계속 적용됩니다.
독립 Astra/high의 [감사 보고서](reviews/20261005-astra-high/READONLY-AUDIT.md)와
[상세 개선 계획](reviews/20261005-astra-high/IMPROVEMENT-PLAN.md)을 Root가 읽고 아래 순서를 채택했습니다.
상세 계획에는 단계별 개발·수치 검증·사용자 인계 기준, 의존성, R01–R52 매핑과 추정 자원이 있습니다.
집중 작업일 추정은 완료 약속이 아닙니다. actual run 비용을 측정해 조정합니다.

## 현재 판정

- 의미 있는 실제 연구 프로토타입. 일부 단일 지지부·PDE·재료·접촉 연구는 실행 기록이 있습니다.
- 현재 사용자 서비스 완료 아님. 기본 실행 연결, 결과 맥락, 장시간 종료·재접속이 핵심 gap입니다.
- 전체 조립체 mechanics, broader Phase 3–7, 실물/배포 요구 OPEN. 강도·실물은 UNKNOWN/NOT_RELEASED.
- Goal은04:31:51Z 실제 ACTIVE였으나05:13:57Z 다시 BLOCKED로 관측됐습니다. 전환 원인 UNKNOWN, 사용자/시스템 재개 제어. 기존30분 후속 작업 ACTIVE와 실제 개발·서비스 가동은 별도입니다.
- 2026-10-05T04:19:50–56Z 관찰에 관련 listeners 없음. 이후 새 가동 검증을 요구합니다.
- fine1.5 이전9PID 없음/terminal receipt 없음/old RUNNING 보존. 완료·종료 원인 UNKNOWN_NOT_QUALIFIED/UNKNOWN.
  같은 Gmsh import를 원인 변화 없이 재실행하지 않습니다.
- source-only kernel은 `bffbd807c56d9aa2cf817f4f6f5bfcbfb54bae77`에서 보존. 실제40 tests와 closed-coarse topology를 새 native field solve로 해석하지 않습니다.

## 순차 작업표

| 순서 | 작업과 사용자 결과 | 상태/담당 | 완료 기준 |
|---|---|---|---|
| S0 | 실제 실행·중단·목표 상태 복원 | READONLY_OBSERVED / Root | 지정PIDs/ports/원기록 구분, old outputs 보존. 종료 원인 UNKNOWN 유지 |
| S1 | 한 실행 동작에 승인 OpenScience+Lab 연결 | SOURCE_INTEGRATED_LIVE_OPEN / Root | 같은 clean source/새 store/owner, approved5.6Sol, 질문 가능 상태, 정상 종료·실패 cleanup 확인 |
| S2a | 부모 CAD와 정확한 수치 검사 이름을 결과에 표시 | SOURCE_INTEGRATED_GUI_OPEN / Root | 부모·revision·manifest 확인, stale UI 차단, mesh screen을 일반 수렴으로 과장하지 않음 |
| S2b | 실제 해석 mesh·하중·구속·U field·변형 표시 | OPEN / adapter·UI, Root | raw native fields와 동일 기록, probe/성분/단위·좌표계 검증. CAD 색칠을 FEA로 대신하지 않음 |
| S3 | 종료·강제 중단·재시작 상태와 admission 복구 | NEXT / Root shared execution owner | tiny crash/identity matrix, append-only reconciliation, real native cancel/reconnect, old evidence 보존 |
| U1 | 첫 간단한 사용자 CAE 연구 | WAITING_ON_S1_S2_S3 / Root | 아래 한 사용자 흐름을 실제로 끝내고 독립 검토·같은 GUI 결과·보고서로 확인 |
| S4a | coarse native affine full-field patch | OPEN / Domain·adapter | source kernel 재사용, U/strain/stress/energy/force/moment 전체 참조 비교. actual mechanics와 구분 |
| S4b | 원본7부품 실제 조립체 연구 | OPEN / Domain·adapter·Root | 부품별 재료/접촉/하중·관측점 선언, load path·평형/에너지·mesh 비교, actual Research 연결 |
| S5 | Phase3의 남은 실제 탐색 연결 | OPEN | 기존 LHS/DE 재사용, 유효 response·budget/convergence·후보비교·재개; mixed variables 후속 |
| S6 | Phase4 PDE 연구 흐름 | OPEN | 지원 form별 actual field/reference/거부·mesh/time/MPI 검증, 변경·비교·AI 해석 |
| S7 | Phase5 재료·접촉의 FE coupling | OPEN | 재료점→구조 연결, history/energy/finite strain·native convergence와 물리 적합성 구분 |
| S8 | Phase6 실제 explicit 연구 | OPEN | 공식 설치 문제 진단, surface contact/preprocessing/history/animation·momentum/energy 비교 |
| S9 | Phase7 측정 inverse/UQ/다목적/HPC | OPEN | 기능별 작은 end-to-end 연구, 실제 측정·원격은 확보된 환경으로만 검증 |
| S10 | 보존·복원·회사 배포·실물 연결 | OPEN / 외부 gate 별도 | approved off-machine bytes restore, 실제 측정/장비/조직 승인; 외부 자료를 임의 생성하지 않음 |

## U1 실제 사용자 시나리오

질문: “롤러 지지대 폭을32mm에서38mm로 늘리면 처짐과 재료 사용량이 어떻게 바뀌나요?”
이미 정의한 단일 지지부 시나리오의 가상 재료·고정 바닥·24mm saddle 하중을 화면에서 확인합니다.
임의 물성 추정은 하지 않습니다. 각 CAD revision에서100N/4·3·2mm 실제 CalculiX 결과의 signed Uz,
체적, XYZ 반력과 마지막 두 mesh의5% screen을 비교합니다. peak stress는 invalid diagnostic입니다.
후속150N 결과의 선형 비례를 raw 정밀도에 맞게 대조하고 조건 변경을 새 record로 보존합니다.
기존 SciPy DE(population5/max_generations1/seed13)로 유효 응답을 쓰는 연구용 탐색을 실행합니다.
budget 종료/`converged=false`/best observed를 최적해 확정과 구분합니다. DOE는 현재14-tool profile에 없습니다.
AI가 같은 record를 해석하고 사람이 모델·입력·결과·한계를 확인하며 같은 보고서를 저장·다시 엽니다.
rejected input에서는 solver 미실행, 취소 요청과 실제 종료, stale/restart 상태 및 old digest 보존도 확인합니다.

## 작업과 검증 원칙

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