# Autonomous CAE Lab 독립 연구 사용성 감사

감사자: 내부 독립 검토용 GPT-6 Astra / high. 작성일: 2026-10-05.
대상: Main `815e20768c972be736f1dee634b0d46d6323c90c`, fixture pin `3e48bf6138f495299f45b1af254bfb4aaff307b8`.
이 감사는 연구용 OpenScience 모델을 바꾸지 않는다. 승인된 `openai-codex/gpt-5.6-sol`과 기존 ChatGPT OAuth가 계속 기준이다.

## 1. 결론

**실제 CAE 연구에 쓸 수 있는 기반과 실행된 연구 사례는 있다. 그러나 비전문가가 현재 프로그램을 켜서 다양한 문제를 끝까지 연구할 수 있는 완성된 서비스라고 판단할 증거는 없다.** 적절한 표현은 “일부 문제에 대해 실제 연구가 검증된, 운영자 도움이 필요한 연구 프로토타입”이다. 전체 조립체 해석, 자유로운 문제 설정, 강도 판단, 장시간 작업 복구, 일반 후처리와 Phase 6–7 범위를 완료했다고 볼 수 없다.

Root의 작업이 무의미하거나 모두 임의의 솔버 테스트였다는 결론은 사실과 다르다. 원본 CAD 연결, 잘못된 하중 이산화 수정, 부호와 단위를 가진 실제 결과, 실패 보존, 수치 엔진 기반 탐색, 승인 모델의 실제 해석, 동일 기록을 여는 GUI는 사용자의 플랫폼 요구에 직접 기여한다. 특히 human05/human07은 단순 설치나 mock 테스트를 넘어선다.

반면 현재 실행 방식은 작은 소스·수치·문서·화면 gate마다 전체 상태를 반복 서술하고, 실패한 CI의 내부 진단을 충분히 확보하지 못한 채 다음 문서 커밋에서도 전체 검증을 실행하는 비용을 만든다. 사용자의 시작·수정·중단·재개·비교 경험보다 정확한 작은 acceptance 증명에 업무가 집중되는 경향이 실제 근거에서 보인다. **검증 기준은 유지하되, 작업의 단위를 사용자 연구 흐름으로 바꾸는 것이 우선이다.** 기존 구조와 도구를 새로 만들 필요는 없다.

## 2. 범위와 증거 수준

읽기 전용으로 요구사항 원장, 현재/역사 체크포인트, 아키텍처·ADR, OpenScience 계약, 실행 계획, 관련 acceptance 문서와 실제 소스·저장된 증거를 대조했다. 긴 역사 문서는 현재 상태·의사결정·원장·관련 사건을 중심으로 읽었다. 예전 채팅 전체나 모든 raw native field를 재감사한 것은 아니다. 이 한계를 전체 과거 검증 재현으로 표현하지 않는다.

- 직접 확인: Main Git 상태와 최근 커밋, submodule, worktree 목록/후보 상태, 실행·GUI·adapter 코드, human07 common result 및 독립 감사 영수증, 실제 보존 스크린샷 2장, coarse import 공개 기록, 815 exact CI 저장 영수증, field-kernel의 저장된 40-test 결과와 coarse topology 사전검사.
- 직접 재실행하지 않음: 솔버, AI provider, pytest, GUI 서버, 새 연구 질문, CI, 설치, 인증. fine live/불확실 출력 디렉터리는 읽지 않았다.
- “오늘 켜져 있다”는 과거 스크린샷으로 판정하지 않는다. 현재 프로세스·포트에 대한 Root의 별도 봉인 관찰이 오면 `LIVE-OBSERVATION-ADDENDUM.md`로 구분한다. 본문 작성 기준 현재 접속 가능성은 **이 감사가 직접 검증하지 않음**이다.
- Main의 저장된 현재 상단은 coarse qualification이다. 이후 fine 종료 여부/원인은 제공된 정보상 UNKNOWN이며 native-import의 오래된 RUNNING만으로 실제 실행 중이라고 판단할 수 없다. root 관찰을 직접 native 증거로 재분류하지 않는다.
- 코드량, 4,289 tests, 40 candidate tests, 독립 리뷰의 “0 P1/P2”, solver exit 0을 서비스·수치·물리 완료로 합산하지 않았다.

## 3. 오늘 연구할 수 있는 범위

| 연구 질문/흐름 | 실제 근거 | 가능한 주장 | 아직 할 수 없거나 새 확인이 필요한 것 |
|---|---|---|---|
| 단일 roller support의 폭·하중과 처짐/mesh 민감도 | human05/human07, producer fb7339b/1622313, 실제 CalculiX 4/3/2 mm | 원본 CAD 한 개의 새 child 해석, 가상 직교이방성·고정 바닥·24 mm saddle 하중이라는 조건에서 응답 비교 | 실제 롤러 접촉·볼트·조립체, 강도/피로/측정 물성, 임의 재료축 회전 |
| 실제 질문→CAD→해석→AI 해석→같은 Core 결과 확인 | human07 8 tools, 2 experiment IDs, GUI/cleanup 저장 증거 | 완전히 지정된 bounded 질문의 실행·해석 루프가 작동했음 | 현재 owner/runtime 가동, 간단한 자연어 질문의 모델링 능력, 임의 연구의 자율 계획 완수 |
| 폭 변화 DOE/제약 탐색 | P1.3/기존 SciPy LHS·DE 기록, ADR0003/0005 | 수치 엔진이 후보를 생성하고 유효/거부 결과와 replay를 추적 | 1세대 예산 종료는 최적 수렴이 아님. 정수/범주/다목적/UQ 전체 미완료 |
| 제한된 PDE·재료점·접촉 연구 | PDEFields c0/c3, SVK/Maxwell, ContactPatches 연결 기록 | 각 선언 범위의 수학·상태 이력·AI 해석/일부 field inspector | 일반 weak form, 시간+벡터+비선형+MPI 모든 조합, 구조 내 MFront coupling, 모든 접촉 형태 |
| 기존 구조 reference family 비교 | structural-family 실제 기록과 남은 Fz/roof 실패 | 통과한 정확한 case의 변위/응력/비례/비교만 활용 | 일부 Fz/roof·Code_Aster/CalculiX contact 불일치는 열려 있음 |
| 원본 fixture 조립체 | 원본 15-part CAD, 7-body coarse native import의 84 groups/완전 매핑 | 같은 개정 CAD를 살펴보고 원본 mesh가 native에 들어갔음을 확인 | 조립체 mechanics, 실제 접촉·재료·체결·하중 전달·field/strength, 공개 assembly Research 실행 |
| 낙하/충격 | flight 및 reduced compliant-stop 예제 | 제한된 질량·힘·가속도·에너지/반발 이력 사례 | 일반 표면·회전 접촉, 충격 재료/파손, 통합 애니메이션, 폭넓은 explicit preprocessing |
| 측정 기반 식별·실물 연구 | synthetic inverse와 evidence envelope | 합성 데이터의 제한된 numerical inverse | 실측 식별·검증 holdout, 장비 연결, 기업 배포·license/security 승인 |

human07에서 직접 확인한 값은 4/3/2 mm 순서의 `[-0.005642080, -0.005730928, -0.005827884] mm`이다. 마지막 쌍 변화율은 `0.01663656998`(1.663657%), 가장 큰 부호 포함 XYZ 평형 비는 `9.377174e-9`이다. 이 결과는 유효한 처짐 연구 근거이다. `peak_stress=0.5990679 MPa`는 원기록에서 **valid=false**이며 강도 목적함수로 쓸 수 없다. 15 PASS와 별도로 아래 7개 blocking UNKNOWN을 유지해야 한다: machine_interface, static_strength, physical_load_test, fatigue_durability, joint_and_contact, material_qualification, stress_convergence.

## 4. 우선순위별 독립 발견사항

심각도는 이 플랫폼을 사용자에게 인계할 때의 영향이다. 코드 보안 취약점 점수나 이미 qualified 된 작은 helper의 결함 판정을 의미하지 않는다. P0는 확인하지 않았다.

### F01 — P1: 기본 실행 경로와 실제 연구 연결이 분리되어 있다

`scripts/lab-local.ps1:1–8`은 Store/Port/WithoutHistory만 받고 `-m apps.lab --store ... --port ...`를 구성한다. `apps/lab/server.py:219–238`의 `--openscience-owner`는 여기에 연결되지 않는다. owner가 없으면 `research=None`, `apps/lab/service.py:95–98`은 NOT_CONFIGURED를 반환한다. 이는 정상적인 read-only Lab 사용에는 문제가 없지만, 사용자 관점의 “프로그램 시작→AI에게 연구 질문” 기본 경로는 아니다.

현재 가능한 우회는 운영자가 승인된 profile/source/store에 맞게 공식 runtime을 띄운 뒤 owner를 명시해 Lab을 시작하는 것이다. guard를 제거하거나 모델을 자동 선택하는 식으로 해결하면 안 된다. 단일 시작 동작이 기존 launcher를 조합하고, source/store/owner/실행 가능 기능을 확인해 사용자에게 정확히 보여줘야 한다. 과거 URL만 제공하는 것은 인계가 아니다.

### F02 — P1: 장시간 실행의 종료·재시작 상태는 제품 수준으로 내구성이 없다

`apps/lab/service.py:86–90`의 jobs/tokens/threads/active_job은 메모리이고, `:475–489`에서 daemon worker를 만든다. `execution_status():106–111`은 그 resident 메모리를 기준으로 IDLE을 계산한다. `ADR/0018-long-running-research-jobs.md`와 `apps/lab/CONTRACT.md:73–80`도 restart recovery/cross-process persistence 미지원이라고 명시한다.

`caelab/adapters/codeaster_elasticity.py:309–381`은 소유 프로세스·로그·RUNNING 및 정상/취소 terminal 기록을 남기므로 좋은 기반이다. 그러나 기록 주체 자체가 사라졌을 때 새 observer가 종료 사실·상태 불명을 정리하는 절차는 별개이다. 제공된 fine 사례의 “PIDs absent + stale RUNNING + terminal receipt 없음”은 바로 이 운영 gap을 드러내는 관찰이며, 사망 원인은 아직 UNKNOWN이다. 이를 특정 timeout/OOM/사용자 종료 탓이라고 단정할 수 없다.

해결 완료 기준은 단순 저장 queue 추가가 아니라: 재시작 후 이전 run 식별, 소유권과 실제 OS 관찰, terminal/UNKNOWN 구분, 이전 store 보존, 새 실행 충돌 방지, 사용자에게 취소 요청과 실제 종료를 구분해 표시하는 것이다. 기존 controller를 확장해야 하며 새로운 일반 스케줄러를 만드는 것이 첫 과제가 아니다.

### F03 — P1: 조립체의 실제 mechanics가 아직 없는데 import/patch가 긴 선행 gate가 되고 있다

`ADR0032:8–12,29–37,64–70` 및 `caelab/adapters/fixture_calculix.py:398,459–471`은 단일 지지부와 원본 조립체의 차이를 명확히 한다. `20261005-fixture-assembly-native-import-coarse-r01-qualified.json:1–15`는 실제 성공 범위를 **native import identity / mechanics NOT_RUN**으로 한정한다. 76,214 nodes와 61,344 cells/84 groups는 해석 응답이 아니다.

worktree의 `plugins/fixture_design/assembly_field_reference.py:1–6,37–53`은 모든 실제 외부 절점에 affine 변위를 주고, 모든 body에 E=2000 MPa, ν=.25를 쓰는 가상 patch다. 이 후보는 curved T10 full-field·strain/stress·energy 매핑의 검증에 타당하다. 하지만 specimen bending, base flexibility, roller contact, bolt preload 또는 실제 힘 전달을 검증하지 않는다. field helper 40-test PASS와 coarse topology PASS도 같은 한계를 가진다.

개선: coarse의 한 representative patch로 새 native field seam을 증명하고 재사용한다. fine import의 비용·종료 문제를 진단하되, 불변 데이터 복사/재감사 때문에 관련 없는 Domain input·UI 설계를 모두 멈추지 않는다. fine를 다시 돌리기 전에 변경할 가설과 성능 관찰을 적는다. 다음 주된 산출물은 실제 연구 조건을 표현하는 assembly mechanics와 그 결과를 보는 사용자 흐름이어야 한다.

### F04 — P2: 일반 사용자 연구를 입증한 범위가 좁다

human07 원문 `artifacts/development-human-workflow-20261004-01/human-07/question-01.txt`에는 모델 ID, 정확한 치수, 9개 직교이방성 상수, 재료축, mesh 3수준, fixed DOFs, 24 mm 하중 patch, 부호 있는 response 위치, unknown과 해석 한계까지 전문가가 지정한다. 이것은 실제 자연어 orchestration의 좋은 acceptance이지만, 비전문가가 “폭을 바꾸면 얼마나 덜 휘는가?”라고 했을 때 필요한 가정을 발견·표시·관리하는 UX 증거는 아니다.

ADR0034는 과거 6개 analysis request가 잘못된 settings로 거부된 실제 실패를 기록한다. 그 수정은 필수였고 유의미했다. 다음 gate는 더 복잡한 긴 검증 prompt가 아니라, 이미 정의된 안전한 예제의 가정을 화면에서 읽고 간단한 목표를 말해 연구를 마치는 과정이다. 미지의 물성을 임의로 만들지 말고, 가상값을 선택한 이유와 민감도 질문을 표시한다.

### F05 — P2: 결과 화면은 기본 CAE 해석에 필요한 맥락이 부족하다

직접 확인한 human07 `linked-result-02.jpg`에서 결과 제목 아래 “수치 수렴: 확인됨”이 보이지만 실제 근거는 마지막 두 mesh의 5% screen이다. `apps/lab/static/app.js:837`의 일반 `converged` boolean 표시가 이 의미를 넓힌다. 같은 화면의 model area는 “형상 미리보기 없음”이며 `:861`에 해당 fallback이 있다. `per-mesh-answer-01.jpg`에는 넓은 좌측 공백, 그대로 남은 `##`와 수식 escape 문자가 보인다.

숫자를 읽는 것만으로 사용자는 어떤 body·frame·surface에 하중과 구속이 놓였는지 판단하기 어렵다. 부모 CAD를 동일 revision으로 연결해 표시하고, mesh/BC/load/material axes를 겹쳐 보여주는 것이 우선이다. Ux/Uy/Uz와 magnitude, 변형 배율, 위치 probe, 반력 합, valid/invalid stress, 단위·좌표계 및 비교 mesh 선택을 단계적으로 제공한다. “마지막 두 메시 처짐 변화 기준 통과”처럼 실제 검사 이름을 보여줘야 한다.

### F06 — P2: 기능 지도와 현재 capability/readiness가 맞지 않는다

`apps/lab/service.py:128–164`는 정적 IMPLEMENTED/EXPERIMENTAL 및 Python method callable을 주로 사용한다. nonlinear_contact는 “다음 독립 reference 필요”, field_postprocessing은 “통합 viewer 미구현”으로 크게 묶지만 bounded contact/PDE inspector 및 실제 연결 증거가 이미 있다. 반대로 method가 있어도 현재 runtime 설치·profile admission·입력 지원 여부를 증명하지 않는다.

하나의 상태 대신 (a) 구현된 입력 범위, (b) 현재 host/runtime readiness, (c) 연구 profile admission, (d) exact qualified case/source, (e) 사용자 흐름 검증, (f) physical release 상태를 구분해야 한다. 모든 UNKNOWN을 감추거나 모두 미구현이라고 쓰는 양쪽 오류를 피한다.

### F07 — P2: 현 상태 문서의 복제가 실제 작업 방향을 흐린다

Main에서 PROJECT_SCOPE 2,062줄/166,673 B, HANDOFF 2,824줄/186,414 B, CURRENT_STATE 2,686줄/185,258 B, SYSTEM_EXECUTION_PLAN 1,174줄, SYSTEM_WORKLIST 1,729줄이다. Current/Latest/Active 제목은 HANDOFF 29개, CURRENT_STATE 27개다. 역사임을 설명하는 문구는 있으나 과거 next instruction이 같은 검색 결과에 계속 나온다. SYSTEM_WORKLIST 최상단은 human02 수정 단계인 반면 HANDOFF 최상단은 coarse import qualification이다. 실제 연구 profile 도움말에도 옛 runtime/Ollama 설명이 남아 있다.

이는 “문서가 많아서 나쁘다”가 아니라 다음 실행을 결정하는 상태가 여러 곳에 복제되어 상충하는 문제다. 역사 보존은 유지하되 현재 단일 상태표와 증거 링크를 만들고, ledger에는 requirement당 현재 source/evidence/next gate만 둔다. 상세 과거는 날짜별 기록으로 남긴다. 반복 prose·test count를 매 커밋 다수 파일에 복사하는 작업을 중단한다.

### F08 — P2: 검증을 재사용할 수 있는데 전체 CI와 실패 조회가 반복된다

`git show --stat 815e207`은 docs/acceptance record 7파일만 바뀐 커밋임을 보인다. `.github/workflows/caelab-ci.yml:3–14`는 Main push마다 전체 workflow를 실행하며 경로/영향 분기가 없다. exact 815 run `37230315608`도 10 jobs, 7 success/3 fail이고 Core 4,289 PASS/5 SKIP이다. 기록은 solver producer538과 containing815를 정확히 구분하지만, 전체 수치 재실행을 문서마다 해야 한다는 의미는 아니다.

815 저장 영수증의 실패 세부는 Fz native numerical checks, vector numerical classification, explicit install 단계이다. Fz의 내부 level/metric/reference/limit, vector의 actual category/status/rate, explicit의 실제 terminal curl 원인은 그 영수증에서 UNKNOWN이다. 이전 다른 run의 404나 설치 실패를 덮어씌우지 않은 것은 옳다. 다만 원인 판단에 필요한 실패 packet이 없는 채 같은 outer assertion을 반복 확인하는 흐름은 개선해야 한다.

변경영향 기반 fast CI와 예약/수동 native qualification을 분리하고, dependencies/runtime/schema/adapter/case hash가 그대로면 기존 numerical evidence를 참조한다. 실패는 original raw result, narrowed log, expected/actual, runtime identity를 한 번 수집해 진단한다. numerical threshold 완화나 failing job 숨김은 해법이 아니다.

### F09 — P2: 전체 scope의 남은 기능이 작은 case들의 연속에 가려진다

`PROJECT_SCOPE.md:1866–1917,2042–2062`는 Phase 1–7과 broader engine/PDE/implicit/explicit/physical/deployment 요구를 유지한다. 과거 좋은 bounded proof를 다시 만드느라 mixed variables, actual fixture mechanics, explicit preprocessing, measured inverse, UQ/surrogate/multiobjective, HPC와 실물 연결의 다음 개발 packet을 계속 뒤로 보내면 원래 요구의 완료에 접근하지 못한다.

“모든 수치 benchmark가 통과할 때까지 다른 모든 개발 중단”도, “실행되지 않은 feature를 계속 늘림”도 적절하지 않다. 단계 순서와 실제 의존성을 유지하면서 각 단계에서 정의·구현·연결을 완성하고 representative verification을 묶어야 한다. 더 넓은 연구 가능성과 software-ready/full-validation/physical-release를 각각 표시한다.

## 5. Root 작업의 가치와 방향 판정

유지할 것: pinned upstream 재사용, Core/Domain/adapter/수치 엔진 분리, immutable experiment/parent linkage, 실제 source/runtime pin, invalid metric·UNKNOWN, raw evidence, 잘못된 입력의 solver 차단, 독립 원자료 검토. saddle equal-node load 수정과 native identity 보존은 단순 형식주의가 아니라 계산 문제를 올바르게 전달하기 위한 필수 작업이다.

줄일 것: 동일 snapshot을 다수 현재 문서에 반복하는 일, 이미 닫힌 원자료의 목적 없는 전수 재해시, 문서 커밋마다 비싼 native matrix, 실패 원인을 좁히지 않은 새 run, GUI의 단순 라벨 수정에 전체 솔버 자격을 다시 요구하는 일. mandatory source/source-drift·소비 시 artifact hash 검사는 유지하되 solver rerun과 분리한다.

앞당길 것: 현재 지원 질문을 실제로 시작하는 동작, 작업 상태·취소·재접속, 원본 CAD+FEA 맥락, scenario 기반 간단한 입력, 기존 numerical engine 탐색의 사용자 연결, 조립체 실제 load path. 새로운 affine patch는 이 과정의 한 bounded prerequisite이며 사용자 deliverable 자체가 아니다.

## 6. Phase 및 52개 요구사항의 남은 gate

완료율을 숫자로 만들어 표시하지 않는다. 여기의 “남음”은 기존 기능이 전혀 없다는 뜻이 아니며, exact bounded evidence를 재사용한다.

| Phase | 확보된 핵심 | 다음 완료 gate |
|---|---|---|
| 0 | 공통 schema/Core/registry/evidence/CLI/MCP/HTTP | capability/readiness·작업 복구·retention 정책을 실제 운영 경로와 맞춤 |
| 1 | 실제 질문, imported/edited CAD, registry, invalid block | 단일 시작 경로·간단한 목표·동일 revision 사용자 화면·재접속 |
| 2 | 단일 support FEA, 구조 family 일부, 원본 assembly CAD/mesh/import | assembly 물성·구속·하중·contact/joints·native full fields와 공개 research/compare |
| 3 | LHS/DE·gated feedback·replay | 보존된 긴 탐색 증거 review, stopping/constraint semantics, 실제 사용자 DOE, broader variables |
| 4 | bounded scalar/nonlinear/transient/vector/coupled/imported + 일부 live flow | vector failure diagnosis, advertised domain/form/time limits, serial→MPI 순서의 실제 acceptance |
| 5 | affine/J2·SVK/Maxwell·contact patch | geometric failing cases, FE constitutive coupling·일반 contact와 assembly 연결 |
| 6 | flight/compliant stop | 실제 surface/rotating contact·재료/파손·preprocessing·history/animation/Research |
| 7 | material point/synthetic inverse | measured inverse·UQ/surrogate/multiobjective/MDO·MOOSE·HPC·실물 evidence loop |

| 요구 | 남은 핵심 또는 유지 의무 |
|---|---|
| R01 | 전체 physics/DOE/inverse/UQ/physical 플랫폼 범위 유지; bounded 사례를 전체 대체로 쓰지 않음 |
| R02 | OpenScience→Core→adapter→evidence 연결을 새 기능에도 실제로 실행 |
| R03 | 실제 numerical engine candidate·stopping을 AI 계획·해석과 연결 |
| R04 | upstream pin/실행 behavior 재사용; 과거 채팅 gap 공개 |
| R05 | 새 fixture/material/PDE/explicit 기능의 Domain 규칙 소유 유지 |
| R06 | registry broader type/dependency/refresh semantics와 UI 제공 |
| R07 | 사용자 CAD 가져오기·선택·효과 검증의 반복 가능한 경로 |
| R08 | invalid model/geometry/mesh/input에서 export·solver 차단 지속 |
| R09 | per-check verdict·blocking UNKNOWN과 release 분리 유지 |
| R10 | 전체 fields/history·measurement/calibration evidence 확장 |
| R11 | 장시간/재시작/원격을 포함한 디지털 thread와 상태 연결 |
| R12 | editable/raw artifact와 검증 가능한 off-machine retention/복원 |
| R13 | 같은 model/revision의 인간 GUI·headless/FEA scene 확인 |
| R14 | 실패한 Fz/contact 비교 진단 및 nonlinear formulation별 한계 |
| R15 | OpenRadioss 일반 preprocessing·surface/rotation/failure 범위 |
| R16 | PDE backend 비교 결과와 실제 bounded/unsupported capabilities 연결 |
| R17 | MFront 물성의 구조 솔버 coupling과 측정 기반 qualification |
| R18 | variable/engine/UQ/multiobjective/MDO/surrogate 별 실제 필요 gate |
| R19 | geometry/frames/contact/material/history/output 선언의 공통 의미 유지 |
| R20 | valid metric·units·field semantics·same-index response와 요약 |
| R21 | public CLI/Python/MCP/HTTP parity, 미지원 operation의 truthful refusal |
| R22 | Core/plugin/adapter 경계 및 기존 코드 재사용 지속 |
| R23 | 기반은 재구현하지 않고 실제 새 기능과 호환성 검증 |
| R24 | material architecture 변경의 ADR; 단순 milestone마다 중복 ADR 불필요 |
| R25 | 비전문가의 질문→모델→조건→실험→결과 한 흐름 |
| R26 | 정확한 assembly CAD→mechanical child→full fields·constraints |
| R27 | 탐색 목적/제약/유효 feedback·stopping/재개를 사용자에게 연결 |
| R28 | 선언 가능한 PDE 문제 범위·unsupported 입력·reference gate |
| R29 | geometric/material/contact nonlinear histories·reference 및 FE coupling |
| R30 | explicit 전체 접촉·재료·에너지·timestep·force/history evidence |
| R31 | 측정 inverse·UQ·surrogate·multiobjective·MOOSE·HPC 등 Phase7 |
| R32 | 실제 fabrication/calibration/machine/measurement/durability evidence |
| R33 | Design/Simulation/Explore/Results/Research 전환의 맥락과 가동성 |
| R34 | changed integration representative verification·실패 raw 진단 |
| R35 | exact dependency license 및 회사 데이터/security 배포 승인 |
| R36 | public repo와 회사 데이터/비공개 운영 경계 결정 |
| R37 | 유용한 bounded 독립 연구/구현/검토에만 병렬 agent 사용 |
| R38 | Root가 common interface·통합·전체 acceptance 책임 유지 |
| R39 | 공식 backend 근거를 scope에 연결; 조사만으로 runtime PASS 금지 |
| R40 | engine은 연구 문제 역할에 맞춰 선택, 설치 수 늘리지 않음 |
| R41 | source/native transaction/성능 부채의 구체적 재검토 |
| R42 | 구현자와 실제 numerical evidence reviewer 역할 구분 |
| R43 | 의미 있는 변경을 독립 검토; repeated count를 proof로 사용 금지 |
| R44 | 같은 interface/file 단일 소유자 유지 |
| R45 | Root가 연구 적합성·GUI·license·references 충돌까지 판단 |
| R46 | reasoning/model보다 실제 사용자/수치 acceptance가 최종 판단 |
| R47 | 발견·대안·근거는 단일 authoritative 기록으로 보존 |
| R48 | 실제 실행·실패 진단·수정·연결; 설치/검증 루프에 머물지 않음 |
| R49 | 현재 상태 복구를 짧은 current index로 단순화, 과거 history 보존 |
| R50 | 이미 실행된 first vertical slice 재사용; 동일 slice 재개발 금지 |
| R51 | architecture impact/ADR/tests/contract 변경근거 유지 |
| R52 | feature/test 수보다 연구 질문을 끝내는 연결 흐름으로 우선순위 결정 |

## 7. 최종 판정과 미확인 항목

본 감사 판정은 **의미 있는 연구 프로토타입 / 전체 사용자 서비스 미완료 / engineering NOT_RELEASED**이다. 플랫폼을 버리거나 solver/LLM을 바꿀 이유는 발견하지 않았다. 개발의 중심을 “다음 작은 benchmark를 닫기”에서 “다음 실제 연구 질문을 사용자가 시작하고 끝내기”로 옮길 이유는 충분하다.

현재 local listener/owner, fine 종료 원인, 815 실패 내부 raw, remote raw archive 복원, 비전문가 테스트, 기업 배포 승인은 아직 별도 증거가 필요하다. unknown을 실패 원인으로 채우지 않았다. 상세 순서는 같은 폴더의 `IMPROVEMENT-PLAN.md`, source/검사 pins는 `INSPECTION-MANIFEST.json`, 감사 범위·출력 digest는 `RECEIPT.json`을 참조한다. 본 감사는 tracked 파일을 고치거나 repairs를 실행하지 않았다.

## 8. 1차 봉인 뒤 현재 관리 상태 정정

Root는 후속 실제 `get_goal`에서 미등록 상태를 확인한 다음 사용자 연구 흐름과 전체52·Phase1–7을 포함한 새 goal을 등록했다고 전달했다. 생성 결과는 `status=active`, `tokensUsed=0`, `createdAt=1791174622`이다. 따라서 **현재 Root 목표는 ACTIVE**이며, 이전 BLOCKED/새 생성 거부는 과거 관찰이다. 미완료 목표를 완료로 속여 초기화했다는 근거는 없다. 기존30분 heartbeat ACTIVE와 별개이고, 새 목표가 생겼다는 사실은 서비스 가동·수치 acceptance·전체 연구 완료를 증명하지 않는다.

Root가 S1/S2/S3 사용자 연결·결과 맥락·운영 복구 우선순위와 내부 Astra reviewer/연구5.6Sol 분리를 채택할 예정이라고 밝혔다. 이는 계획 채택이지 구현 완료가 아니다. 최초 봉인 당시 candidate4files/source40-test snapshot은 그대로 역사 증거로 보존한다. Root가 이후 staged10files라고 전한 작업은 본 감사의 새로운 native qualification이 아니다.

1차 `RECEIPT.json`과 `INSPECTION-MANIFEST.json`은 덮어쓰지 않는다. 최종 append-only 정정과 최신 문서 digest는 `INSPECTION-SUPPLEMENT-02.json` 및 `RECEIPT-02.json`으로 잇는다. 감사 context 자체의 read-only goal 조회는 null이었으므로 Root의 goal 상태를 감사자가 직접 재확인했다고 주장하지 않는다.


최종 출처 보충: Root의 2026-10-05 04:31:51 UTC 실제 get_goal 봉인 기록 ../root-observation-01/GOAL-ACTIVE-OBSERVATION-01.json을 읽고 SHA-256 0d3d493c7c8199fe36da1075330385115495422a1f35934e2de4a554f39ef6ea 일치를 확인했다. 해당 관찰의 Root goal.status=active, createdAt1791174622이며 tokensUsed22291은 생성 후 관찰값이다. 이는 이전 생성 당시 tokensUsed0과 모순되지 않는다. 별도 auditor context의 null과 구분하며, goal ACTIVE가 서비스 readiness나 numerical PASS를 뜻하지 않는 판정은 유지한다.
