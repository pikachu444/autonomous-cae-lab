# 주요 설계 판단·대안·교정 기록 — D1

요청 **PRO-DESKTOP-DESIGN-20261012-01** · 기준 코드 `9a6e3083037630b45694b812b135dc1cd63cf95a` · 작성일 2026-10-12.

이 문서는 Pro가 작성한 연결된 전체 제품 설계 초안의 선택 이유와 남은 확인을 기록한다. 기능 본문은 FUNCTION_SPEC, 상태·조작은 SCREEN_SPEC/screens.json, 실제 검증은 QA_REPORT와 reviews가 소유한다. 설계 초안 제출은 제품 구현 승인, Windows 사용성 수용, 수치 검증 또는 공학적 release가 아니다.

## 1. 근거와 권한의 경계

실제로 전달받은 것은 사용자 메시지에 있는 일곱 문서 본문이다. 원본 ZIP, 사용자 attachment 폴더, 원본/작업본 SHA256 manifest, 이전 22쪽 PDF, 기존 Qt spike 원본, 다른 대화/Space/Windows 디스크는 제공받지 않았다. 이들을 열거나 비교했다고 주장하지 않는다. 추가로 읽은 pinned 공개 파일과 읽지 못한 범위는 SOURCE_EVIDENCE.md/json에 구별했다. 최신 요구와 현재 소스의 차이는 과거 v2의 “신규 owner” 분류를 그대로 복사하지 않고 판단했다.

이번 결과는 이 폴더 아래의 기획·편집 원본·별도 시제품으로 한정한다. production code, solver threshold, AGENTS, 사용자 설정, CURRENT_STATE/HANDOFF와 원격 저장소를 수정하지 않았다. Codex가 나중에 실제 수신·검토·실행 결과를 기존 문서에 통합한다. 본구현은 사용자가 설계 검토 뒤 개발 시작을 지시해야 한다.

이 세션은 실제 Pro 상세 작성 응답이다. 하위 에이전트의 답변을 Pro 작성 대신으로 표기하지 않았다. 독립 검토는 명시적으로 배정한 Astra/xhigh, 제한된 runtime·prototype 확인은 Sol/high, source 정리는 Luna/high가 맡았으며 Pro가 해당 결과를 대조해 문서와 시안을 교정했다. 사용자 PC의 Pro UI 모드·relay 설정·MoAI 설치를 원격으로 확인했다고 확대하지 않는다.

## 2. 제품과 구현 방향의 결정

| 결정 | 선택과 이유 | 검토한 대안·영향 | 구현·확인의 소유 |
|---|---|---|---|
| D01 독립 desktop 도구 | Data/Material/PDE/Numerical/Runner/Expert/Study는 직접 실행한다. Workbench는 참조 탐색을 원할 때만 연다. | 강제 Workbench/AI/CAD 입구는 독립 작업을 막으므로 채택하지 않았다. 도구 수와 process 수는 같은 개념이 아니다. | 기존 Research desktop dispatcher와 각 owner 재사용; FN-01/31/33 |
| D02 세 native 실행 환경 | Research는 기존 PySide6 6.9.1 Widgets+Matplotlib, Pre는 FreeCAD native, Post는 ParaView native다. | 웹 GUI, localhost 페이지, QtWebEngine wrapping, HTML 폼, 유료 UI kit는 제품 주 GUI로 채택하지 않았다. 내부 기존 loopback 서비스는 GUI 형태와 별개다. | 환경별 Python/Qt 분리, 기존 bridge를 확장; FN-10–19/27/34 |
| D03 기존 owner 유지 | Data/Material/PDE/Simulation/Evaluation/Study/Discussion/Plan owner와 native bridge·JobManager가 이미 있는 코드를 재사용한다. | 새 universal owner, scheduler, optimizer, duplicated Plan editor를 만들지 않는다. 기존 소스가 있다는 사실을 전체 사용자 수용으로 확대하지도 않는다. | SOURCE_EVIDENCE 및 backlog current_status/gap 구별 |
| D04 입력·판단·실행 소유 분리 | Core는 공통 record/schema/mapping/gate/artifact/evidence/provenance, Domain은 물리·수치 의미, Adapter는 syntax/path를 소유한다. | 모든 물리를 새 common solver schema에 압축하지 않는다. native 기능의 실제 모델/이력을 유지한다. | FN-09/12/19/34, 기존 ADR0001 및 0060–0062의 유효 범위 |
| D05 파일 형식 | 현재 store/document.json/revision 구조, 관리 .caepre, FCStd/PVSM/원 결과 형식을 유지한다. 이동용 사본은 기존 manifest+필요 의존 파일을 보존하는 새-ID 분기다. | v2의 새 .caelab 권고는 이번 기본안에서 채택하지 않았다. 현재 형식 migration의 위험 없이 직접 열기/최근 파일/분기를 먼저 개선한다. | FN-01/02/27; 새 확장자 도입은 별도 이유·migration 검토 없이는 진행하지 않는다. |
| D06 desktop 정보 구조 | 표·곡선·모델을 중심에 두고 작업별 dock 구성을 달리한다. Material은 시험/계수와 큰 곡선·후보표, PDE는 model tree/settings/field, Post는 native pipeline/view다. | 요구 절 번호별 동일 폼이나 모든 속성을 나열하는 공통 wizard를 채택하지 않았다. 상세 옵션은 선택 맥락에 둔다. | SCREEN_SPEC 공통 규칙·개별 board; Windows 실제 폭/DPI 수용은 남음 |
| D07 실행 정체성 | GUI/CLI/Python/optional MCP는 동일 owner·saved input/result/command를 다룬다. native command_id와 calculation job_id의 수명·조회·취소를 구별한다. | 화면에 표시된 active 문서를 추정해 쓰거나, 다른 복사본 실행을 현재 native 창 편집 성공으로 보고하지 않는다. | 기존 routes/client/native handler 확장; FN-25/34 |
| D08 invalid와 UNKNOWN | invalid draft는 저장한다. invalid required input/CAD는 해당 export/run만 막는다. 공학 기준 미제공은 UNKNOWN/NOT_RELEASED로 남는다. | 프로그램 실행 성공, 수치 정확도, 사용성, engineering release를 단일 PASS로 합치지 않는다. | FN-02/12/32; F05 `3.32295e-6 > 1e-6` 원값·한계 그대로 |

## 3. 작업을 끝내기 위한 상세 선택

### D09 Material과 Plan을 같은 작업면에서 편집

Material 현재 계수와 Plan 시작값·bounds·고정/자유·train/holdout은 서로 다른 열과 owner 표시를 가진다. 같은 PlanVariablesTable/owner를 embedded와 독립 Numerical 창이 사용한다. Material current를 바꿔도 Plan source나 starts는 자동 갱신하지 않는다. Enter는 해당 owner draft에 반영하고 Esc는 셀 버퍼만 취소한다. Undo는 focus owner의 최근 명령이며 다른 owner의 history를 소비하지 않는다.

저장은 cell buffer, acknowledged owner draft, immutable saved revision, frozen run input을 구별한다. 복수 owner 저장은 각각의 receipt를 보이고 Material 성공/Plan 실패를 전체 성공으로 표시하지 않는다. 현재 구현이 제공하지 않는 cross-process atomic commit을 시제품의 JSON replace로 보증하지 않는다.

### D10 두 CSV의 물리량 의미를 먼저 맞춤

A는 s/N/mm/°C, B는 ms/kN/µm/K를 다른 열 순서로 갖는다. mapping은 채널 역할·수치 단위 변환·quantity 계산을 나눈다. L0=50mm/A0=20mm²인 합성 시편에서 e=ΔL/L0, λ1=1+e, P11=F/A0를 만든다. extension을 strain으로 이름만 바꾸거나 Cauchy stress를 J=1로 추정하지 않는다. 위치·영점·게이지·방향과 실제 시험 metadata가 부족하면 판단에 필요한 진단으로 남긴다.

현재 FELUPE neo_hooke는 `mu,lmbda`와 prescribed F 계약이다. F22=F33=1은 구속된 횡변형이며 자유 인장의 P22=P33=0이 아니다. 미래 mixed-control 계산은 별도 capability·실패/재시도/state 보존 과제다. 현재 미지원 Run은 차단되고, 미래 지원 시안은 MAT-READY를 사용자가 명시 선택해야 시작한다.

### D11 mask·잔차·보존 범위

원자료 quality, 연산 validity, Plan inclusion/train/holdout, Post visibility는 서로 다른 소유와 목적을 가진다. frozen fit sample은 quality ∩ operation-valid ∩ Plan-included로 compile한다. 현재 Data quality_rows만으로 Numerical objective에서 자동 제외된다고 주장하지 않았다. compiler 연결을 FN-04-03/FN-07에 남겼다.

현재 잔차 의미를 재사용한다: 각 곡선 rᵢ=√(w/n)·(prediction−observation)/scale, train objective=Σrᵢ². n은 고정된 유효 표본 수다. holdout은 objective에 들어가지 않는다. 숨김, 실패 후보, NaN, 빈 구간을 좋은 점수로 만들기 위해 임의 제거하지 않는다.

모든 후보의 상세 곡선/holdout이 이미 보존되었다고 가정하지 않는다. c017은 보존 상세, c014는 summary/NOT_RETAINED/NOT_EVALUATED, c009는 실패 부분, c021은 취소 부분을 보여준다. 상세 부재는 명시 새 evaluation·별도 budget·sidecar로만 보완한다. 선택·정렬·재열기는 계산하지 않는다.

### D12 채택은 draft Apply와 Save를 분리

Material candidate c017의 source r17, 현재 target r18/μ=.900과 current protocol 변경을 3-way 비교한다. fresh CAS 뒤 Apply는 μ=.862의 dirty target draft와 UNSAVED receipt를 만들며 saved r18은 그대로다. 명시 Save가 성공해야 r19와 receipt를 게시한다. Save 전/후 cold reopen은 각각 .900/.862를 읽는다. 그 사이 또 다른 client가 바꾸면 저장을 거절하고 draft를 유지한다.

N-MOO의 p19는 CAD thickness와 Material 값을 바꾸는 별도 proposal이다. 이를 Material-fit c017로 바꿔 표시하지 않는다. 여러 owner는 준비/적용/저장 receipt를 구별하고, 필요한 저장이 모두 성공하기 전 group reference를 성공으로 게시하지 않는다. 실패 원본과 이전 결과는 보존한다.

### D13 일반 사용자 contact

사용자 면집합 Add/Remove와 3D 선택을 연결한다. law/friction/gap/normal/단위/solver outputs를 함께 검사하고, 현재 bounded benchmark·단일 solid exporter가 일반 사용자 접촉을 지원한다고 하지 않는다. 미지원 입력의 Run은 차단한다. 미래 지원 branch에서는 contact-031/attempt02와 frozen r12/r6/r7이 끝까지 이어진다.

Post는 pressure, normal resultant, signed gap, penetration, slip availability, actual time을 같은 source에서 보여준다. 부호 규약과 association·필요한 출력 배열이 검사 대상이다. 합성 contact fixture는 face184 pressure1.42MPa, gap−.006mm, penetration.006mm, .040s normal112N이다. 면적 가중 압력 합과 시간곡선을 맞췄으며 slip 부재는 0이 아니다.

형상이 r13으로 바뀌어 face split/normal flip이 생기면 Cancel도 r13 CAD 편집을 되돌리지 않는다. old r12 contact refs가 unresolved로 남고 실행은 차단된다. Apply는 명시한 대응만 r13 contact draft로 바꾸며 old mesh r6은 계속 stale다. Cancel/Apply 각각의 저장·재열기 화면에서 이 상태를 유지한다. 예전 r12 결과를 새 r13 결과로 relabel하지 않는다.

### D14 pose와 native 저장

운동 preview P1은 view 상태다. 설계 P0와 generation을 보존하고 Save/close/FEM/export 전에 실제 native pose 복원을 확인한다. 복원 미확인은 해당 작업을 차단한다. ‘현재 자세 적용’만 설계 변경이며 지원되는 native constraints와 transaction이 필요하다. 늦은 restore가 이후 설계를 덮어쓰지 않도록 session/generation을 확인한다. 운동학 경로를 응력·충격·접촉력 계산으로 표현하지 않는다.

### D15 Post 비교와 이동 파일

비교는 quantity/measure/unit, association, coordinate basis, 실제 time, mesh/mapping을 검사한다. 현재 scalar POINTS/linear tetra B→A 경로를 재사용하고 일반 vector/tensor/time/단위 변환은 명시 확장으로 남긴다. `B_at_A−A`와 percentage의 masks를 분리해 A=0이면 delta는 유효하고 percentage만 undefined가 된다. 영역 밖, gap, 결측은 0이나 최근접값으로 대체하지 않는다.

같은 bytes의 이동은 위치 수리이며 원 입력 identity를 유지한다. 내용이 바뀐 PVD 한 frame은 새 source revision/branch다. 정상 A와 보존된 B 근거는 부분 열기로 계속 본다. Post Ctrl+S는 managed 분석 저장이고 native Save Data는 export다.

### D16 Evaluation의 현재 지원과 미래 확장

이미 있는 Evaluation owner/editor, 1–32 saved stages와 exact_same_mesh, lagged feedback, 기존 JobManager를 재사용한다. bounded SI thermal/thermoelastic Simulation stages도 이미 있다. 열→구조를 새 owner/새 framework 개발로 분류하지 않았다. current prefix reuse는 앞 stage만 아니라 전체 definition hash와 candidate values 동일성을 먼저 요구한다.

SI stage와 dimensionless PDE를 구별한다. 열 입력은 metre/global/P1 triangle·Kelvin absolute field, 구조는 명시 Tref와 free expansion 조건이다. 실제 수용은 열 solver가 계산한 field를 전달해 ΔL=α(T−Tref)L과 비교한다. 이번 NOT_CONVERGED 화면은 lag0 `heat.temperature→solid.temperature`, seeded lag1 `heat.temperature→heat.linearization_temperature`, L∞ ΔT/abs1e-6K/rel0/scale1K/max12가 선언된 **의도적으로 정체된 UI fixture**다. 첫 반복은 previous 값이 없어 residual N/A다. 이 합성 실패 이력을 균일 정상 열전도 solver가 실제 산출한 결과라고 주장하지 않는다.

### D17 일반 PDE·수치·물리 범위 유지

현재 nonlinear PDE reference는 `-div((1+alpha*u²)*grad(u))=rhs`, unit_square/P1, 전체 경계 상수 Dirichlet, alpha0..2, bounded RHS와 고정 Newton atol=rtol1e-10/max25다. 이 범위를 시안에 정확히 표시했다. 일반 weak form/ODE/다른 BC·space·transient·multiphysics는 삭제하지 않고 별도 adapter·editor 확장으로 분해했다.

nonlinear implicit, explicit impact/drop, bulk failure/cohesive/reclosure, constitutive/tangent, DOE/inverse/optimization, Sobol sensitivity/UQ/RBF surrogate/MOO/MDO, remote batch/SSH/Slurm/PBS, physical measurement calibration·향후 장비 연결을 각각 사용자 결과와 검증 과제로 남겼다. 등록 목록·소스 존재·무료 이름을 실제 설치/지원/수치 정확도와 구별한다. 수치 엔진은 후보를 만들고 solver는 물리를 계산한다.

### D18 Study/Expert/다음 연구

Study는 독립 질문·경쟁 가설·지지/반박 근거·명시 판단·다음 연구를 소유한다. Discussion의 새 발언이나 Plan 결과가 판단을 자동 채택하지 않는다. 현재 Study가 지원하는 saved document/result/Expert turn refs를 재사용하며 일반 문헌은 등록 원문+locator 또는 명시 ref extension으로 연결한다.

fixture-only compliance를 다음 연구로 선택하면 새 N-next draft를 보여준다. 기존 Material Fit A를 새 제안인 것처럼 열지 않는다. N-next는 load levels/relative gauge response와 필요한 calibration/안전한 실제 환경을 가진 저장 가능한 invalid draft다. 장비 제어는 수행하지 않는다.

Expert는 provider 미연결/limit에서도 논점·질문·사용자 reply draft·보존 발언을 읽고 저장한다. 개발용 Pro relay 사용권을 제품 inference/API 권한으로 간주하지 않는다. 유료 fallback이나 임의 provider 전환은 없다.

## 4. 무료 도구·라이선스 선택

공식 출처와 exact-version 한계는 `reviews/TOOLS_LICENSE_AUDIT.md`가 상세 기록한다. 법적 배포 승인이나 사용자의 설치 상태를 대신하는 표가 아니다.

| 범위 | 선택 | 비용·license 사실 및 조건 | 이번 실제 사용 |
|---|---|---|---|
| 제품 Research UI | PySide6 6.9.1 Core/Gui/Widgets/UiTools | exact PyPI release에 LGPLv3/GPL2/GPL3 경로. 선택 모듈의 LGPL 안내를 확인했다. 배포 시 exact wheel·third-party notices·교체/재링크 조건 점검 필요. | Qt source/.ui 작성. 이 환경에는 PySide6 없어 실행 미확인. |
| plot | 기존 Matplotlib | 3.10.8 공식 PSF 기반 license 확인. 유료 plotting/UI 라이브러리 없음. | 시제품 소스는 기존 Matplotlib 사용. 표·그림 authoring은 기존 Pillow/stdlib 이용. |
| workflow 편집 | draw.io Desktop용 .drawio | 현재 Desktop 저장소는 GPLv3. 구형 일반 draw.io Apache 안내를 Desktop license로 단정하지 않았다. | mxGraph XML 원본·nodes/edges JSON 작성·parse. 실제 Desktop 앱 열기는 미확인. |
| design 협업 | Penpot Professional | 공식 가격 $0/user/month 확인. 무료 용량/기록 한계가 있으며 계정별 권한·실제 export는 확인되지 않았다. source MPL2.0. | editable SVG/layer JSON/hotspot data를 local 인계. native .penpot를 만들었다고 주장하지 않는다. |
| 도구 대안 | editable SVG/JSON+.drawio+Qt .ui | 새 계정·서버·hosting·유료 서비스 없이 편집 가능한 원본을 제작. | Penpot 연결이 없어도 전체 설계 작성은 진행했다. Codex actual Penpot import/edit/export 단계는 남음. |
| optional backend | Code_Aster/CalculiX/OpenRadioss/FEniCSx/MFront 및 수치 후보 | 프로젝트별 공식 license·혼합 dependency·exact build/Windows 가용성을 분리. SALOME mixed components, MFront exception, OpenRadioss license 원문 미확인 범위도 그대로 기록. | 설치·solver 실행 없음. 유료 CAE/LS-OPT/상용 API/결제 trial 도입 없음. |

공식 확인 링크: <https://pypi.org/project/PySide6/6.9.1/> · <https://doc.qt.io/archives/qt-6.9/qtuitools-index.html> · <https://matplotlib.org/3.10.8/project/license.html> · <https://github.com/jgraph/drawio-desktop/blob/dev/LICENSE> · <https://penpot.app/pricing> · <https://help.penpot.app/user-guide/export-import/penpot-file-format/>.

## 5. 제공받은 Astra baseline의 반영

| baseline 지적 | D1 반영 | 남은 실제 수용 |
|---|---|---|
| 옛 next implementation/cloud-only가 최신 범위를 거스름 | D1은 planning/prototype만. CODEX_HANDOFF의 운영 반영안 제공. 기존 문서는 직접 덮어쓰지 않음. | 사용자 개발 시작 지시 이후 본구현 |
| 이미 있는 owner/bridge 신규 분류 | SOURCE_EVIDENCE와 backlog를 reuse/extension으로 교정 | 변경 handler의 실제 regression |
| implicit/explicit/failure/UQ/surrogate/MOO/remote 포괄행 | FN-08/14–24/26/35에 다른 workflow·input·source·criteria | 선택 adapter 무료 경로·실제 실행 |
| 곡선/3D/graph가 설명문 | concrete editable SVG와 동일 PNG/layer/hotspot data | Windows native/Qt 실제 조작성 |
| Material 두 CSV와 Plan 흐름 단절 | C02–C04, SC-01, shared Material/Plan harness·adoption/reopen variants | 실제 mixed-control/retention/mask compiler 구현 |
| Contact 사용자 면부터 rebind까지 미완결 | SC-02, r13 cancel/applied/reopen, exact contact run/result/field fixture | 일반 면집합 exporter와 contact physics 검증 |
| Study 누락/Evaluation owner 혼동 | 독립 Study, same Evaluation editor, N-next proposal | 실제 Study ref extensions·runtime |
| multi-owner dirty/save 미정 | buffer/draft/saved/run, focused Undo/CAS/receipt/partial/close를 분리 | 실제 cross-client/process crash·native 저장 |
| .caelab 형식과 기존 저장 충돌 | 기존 store/.caepre/PVSM 유지·portable branch 선택 | Windows file association·cold reopen |
| Expert inference와 relay 혼동 | providerless drafts·retained turns·no paid fallback | 실제 구독 포함 실행경로 확인 |
| dock/keyboard/DPI 구체 부족 | minima/focus/reflow/shortcut·native rule, .ui/harness 제공 | 100/125/150/200% 실제 Windows 확인 |
| 검증 시점·재사용 부족 | V-01–35, task별 timing/evidence, P/U/R/N/I 분리 | 관련 기능 구현 때 해당 검사만 수행 |

## 6. 이번 Astra actual-artifact 검토의 교정

최종 독립 판정·파일 hash·검토 범위는 `reviews/ASTRA_DRAFT_REVIEW.md`를 따른다. 아래는 Pro의 반영 기록이며 Astra나 사용자 수용을 대신하지 않는다.

| Finding | 교정한 결정·실제 산출물 |
|---|---|
| ASTRA-P1-01 | c017/c014/c009/c021의 retained/partial/missing/holdout, explicit detail evaluation/ID/budget; 원 실행 소급 대체 금지 |
| ASTRA-P1-02 | quality/operation/Plan mask compiler gap 명시, stable sample ID와 fixed objective definition; 시제품 owner별 mask 교집합 검사 |
| ASTRA-P1-03 | E/yield toy를 현재 neo_hooke mu/lmbda로 교체. 두 CSV mapping·selected raw samples·protocol·holdout·target conflict·save/reopen을 같은 harness에 연결 |
| ASTRA-P2-04 | invalid raw buffer/acknowledged invalid draft/recovery capsule을 보존. close와 job cancel 분리 |
| ASTRA-P2-05 | current Evaluation reuse는 whole definition SHA+candidate values 일치가 필요하다고 교정 |
| ASTRA-P2-06 | 기존 bounded SI thermal→structural stages 재사용; 신규 owner 작업 제거 |
| ASTRA-P1-07 | current Run blocked와 explicit future-supported branch 분리. Contact/Evaluation/각 Numerical/remote attempt 및 save/reopen exact context 추가 |
| ASTRA-P1-08 | exact lag0/lag1 ports+seed/check, metres/P1/K field, initial N/A 포함12회 잔차, deliberate UI nonconvergence와 물리 reference 분리 |
| ASTRA-P1-09 | A0078–A0085 table/curve range와 A0082 quality exclusion 연결 |
| ASTRA-P2-10 | Apply는 dirty draft, Save만 r19/receipt; focused-owner Undo; current Material draft와 frozen Plan source 불일치 Run 차단. pure tests 실제 실행 |
| ASTRA-P2-11 | contact pressure×area/resultant/curve/gap, field/legend 동일 색 함수, node145 gauge/time, constitutive initialP=0, UQ/MOO/RBF/DOE 실제 해당 fixture 축과 값으로 교정 |
| ASTRA-P2-12 | task-level implementation_prerequisites DAG와 runtime_prerequisites 분리. FN12↔13/14↔15/16 등의 거짓 전체 선행 제거 |
| ASTRA-P2-13 | README와 .drawio 실제 경로 일치; 최종 package 링크/manifest 검증 |
| 후속 r13/채택/다음 연구 context | rebind Cancel/Apply 후에도 r13 유지, adoption savedr18→dirty→savedr19 variants, 새로운 fixture-only N-next draft와 Study 연계 |

### 마지막 state/identity 교정의 구체화

Data/WB/구성 연구/FE assignment/report 저장은 각각 자기 문맥의 reopen으로 연결한다. Study의 이전 판단은 S-02r2 read-only inspector로 열고 currentr3를 유지한다. Material branch는 M-branch-01이라는 새 owner ID와 draft→savedr1을 표시하며 원 Materialr18/Planr8을 변경하지 않는다. N-next는 NOT_RUN이므로 retained result 대신 sourceStudy를 연다. native mesh는 command_id monitor로 이동한다. rebind review의 Save는 Apply/Cancel 전 비활성화되며, accepted B outward normal은 원 face 방향 복원을 보여준다. disabled action 제거 뒤 hotspot ID/tab order는 최종 재번호하여 중복하지 않는다.

## 7. 지금 남는 판단과 환경 확인

이미 정한 desktop 형태, 도구 독립성, 비용0, PySide6 재사용, 본구현 승인 순서는 다시 질문하지 않는다. 기획을 막지 않는 실제 미결은 다음과 같다.

1. **사용자 실제 연구 자료가 생겼을 때**: 시편·law variant·측정 위치·교정·공차·failure/release 기준을 해당 작업에서 정한다. 현재 합성 값은 기본값이나 공학 허용치가 아니다.
2. **실제 배포 구성 결정 시**: 내부 사용/외부 재배포, exact native/Qt 패키지 묶음·license notices·linking 방식을 확인한다. 비용을 발생시키는 선택지는 제외한다.
3. **원격·장비 기능을 실제 실행할 때**: 이미 보유한 무료 host/queue allocation·드라이버·실제 장비 범위와 authorization을 확인한다. 지금 file loop와 나머지 독립 기능은 진행 가능하다.
4. **Codex 실제 환경 연결**: 사용자 Windows의 MoAI/relay/Qt/Designer/native/Penpot 상태를 다시 확인하고 기존 설정을 merge한다. 여기서 설치 또는 접근 성공을 추정하지 않는다.

현재 한계는 제품 범위 삭제가 아니다. 상세 업무·편집 시안·오류복구·구현 과제는 제공했으며, 실행하지 않은 Qt/native/solver/provider와 actual Penpot export는 명확히 미확인으로 남긴다. 사용자는 이 D1과 시제품을 검토한 뒤 필요한 교정을 지시하고, 별도로 제품 개발 시작 여부를 결정할 수 있다.
