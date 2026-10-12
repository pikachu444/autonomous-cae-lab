# Verification plan — D1

요청 PRO-DESKTOP-DESIGN-20261012-01. 검증은 관련 기능을 만들 때 그 변경의 위험을 확인한다. 과거 solver 전체 campaign이나 F05를 화면 기획의 선행 gate로 되살리지 않는다. 이 문서는 **앞으로 수행할 검증 계획**이며 아래의 명시한 artifact/순수 prototype 검사 외 제품 실행을 주장하지 않는다.

## 검증 수준 / 시점 / 완료의 의미

| 수준 | 수행 시점 / 필요한 환경 | 확인하는 것 | 완료 증거 / 해석의 한계 |
|---|---|---|---|
| P — planning | 지금, 전달 문서·pinned source·실제 artifacts | 사용자 start/end·owner·state/action·source/gap·전체 scope·무료 경로·핵심 오류복구 | 기능/화면/flow/scenario 일치, 독립 검토 finding disposition. 사용자 승인이나 구현 PASS 아님 |
| U — UI interaction | 별도 Qt prototype와 실제 native 새 창, Windows | focus/IME/dock/resize/table-plot/keyboard/dialog·dirty/save/conflict/cancel/reopen | 환경·source hash·작업script·실제 상태/캡처. offscreen/XML/gallery만으로 native/DPI PASS 금지 |
| R — implementation regression | 사용자 개발 시작 후 해당 handler/schema/adapter 변경 때 | 기존 contract 보존·invalid draft·CAS/ref/ID·save failure·source/mask/recipe compiler | 영향 받은 test node와 actual input/output/assertion. test파일 존재와 실행 결과 구별 |
| N — numerical reference | 해당 물리/수치/변환 경로가 실제 준비됐을 때 | 독립 해석해/제조해/신뢰 기준·mesh/increment/tangent·energy/reaction·mapping validity | exact build/input/method/units/tolerance chosen before run/raw output/difference. exit0는 부족 |
| I — final integration | 연결된 해당 사용자 workflow 구현 후, 실제 Windows/native/runtime | 자신의 파일→edit→actual run/result→error/recovery→save→새 owner reopen, GUI/CLI/Python 동일성 | SC 경로+두번째 비fixture input+실제 결과/refs. 사용자 검토·공학 release 별도 |

P/U/R/N/I는 모든 기능이 직렬로 전체 수준을 통과해야 다음 도구를 시작하는 순서가 아니다. 예를 들어 독립 Post와 Data 편집은 contact solver 설치를 기다리지 않는다. same-mesh 비교는 다른mesh generalized mapping을 기다리지 않는다. provider 없이 Expert/Study draft를 쓴다.

## 이번에 실제로 수행한 범위

- 실제 전달된 일곱 본문과 pinned source 조회. exact 출처·snapshot normalization은 SOURCE_EVIDENCE.md/json.
- Pro 작성 generator로 FUNCTION_SPEC/CSV, editable SVG+PNG+screens JSON, scenarios, .drawio XML 생성. JSON/XML parsing, ID/target/action 연결은 generation reports.
- planning Material state model의 한정된 순수 tests. 정확 실행 횟수·결과는 prototype/VERIFICATION.md 및 QA_REPORT.md의 마지막 기록.
- PNG 시각 검토와 Astra actual artifact review. 확인한 board/교정은 QA_REPORT.md/reviews에 기록.
- **미실행:** PySide6 Qt 창, Designer, 실제 Penpot/draw.io app open/export, Windows DPI, FreeCAD, ParaView, solver/FEniCSx, fit/DOE campaign, provider, SSH/queue, 장비, production regression.

## evidence record 형식

각 실제 시험은 requirement/function/backlog ID, source pin+수정diff, artifact hash, fixture 또는 실제 사용자 input hash, environment/host/runtime/build, trigger/action, expected→actual, raw log/result/ref, units/measure/frame/time/mask, tolerance와 사전 선택 이유, cancellation/terminal observation, save/reopen new process ID, defects/limitations를 남긴다. 평가값 하나에 PASS를 붙여 실행·수치·사용성·공학 상태를 합치지 않는다.

기존 test paths는 pinned tree에서 존재를 확인한 **재사용 후보**다. SOURCE_EVIDENCE에서 read를 밝힌 파일 외에는 본문 전체를 이번에 읽거나 실행했다고 주장하지 않는다. Codex는 해당 작업을 시작할 때 실제 test semantics를 읽고 영향 있는 node만 재사용/확장한다. 옛 JS/web UI tests는 Qt/native 조작성 증거가 아니며 handler contract만 유효한 부분을 재사용한다. 새로운 동작을 구현하기 전 테스트 개수만 늘리지 않는다.

## 반드시 분리해서 검증할 실패 경로

1. Material+Plan 두 dirty, invalid raw buffer Enter/close/recovery, Material save success/Plan failure, source refresh Cancel/Apply와 Plan starts.
2. fit candidate click no evaluation, unretained detail/new explicit eval ID, holdout not in objective, finite quality-marked row truly excluded by compiler.
3. current r18 vs r17 candidate target conflict, current change after preview, prepare/apply/branch/cancel and exact refs.
4. Contact required face split/normal flip/unsupported law; Cancel preserves unresolved draft and prior results; new geometry cannot inherit old PASS.
5. P0/P1 motion lifecycle, unsupported pose apply, stale restore after current design change, actual native save/reopen.
6. Post A/B different units/frame/time/mesh; capability rejection; outside/gap/nonfinite masks; A=0 leaves delta valid and percent undefined.
7. same-content relocation vs changed-content one PVD frame, missing dependency and partial branch reopen; no auto computation.
8. Definition hash/source/candidate equality for current Evaluation reuse, bounded SI actual field transfer, history state restore and NOT_CONVERGED.
9. job/command cancellation requested vs terminal/unsupported/completion race, response lost/replay/session restart; window close independent.
10. provider limit/unavailable, remote disconnect/uncertain termination and physical acquisition unbound all preserve draft/retained work.

## 기능별 목적·선행·기준·재사용


### V-01 / FN-01 — 독립 도구에서 자료를 열고 같은 문서를 다시 찾기

**목적:** 도구 바로가기 또는 파일에서 시작해 자기 문서를 정확한 편집기로 열고 종료 뒤 이어서 작업한다.

**선행:** 기존 store/type별 open/save dispatcher와 별도 owner process.

**완료 판단 / 독립 비교:** 한국어/공백 경로·더블클릭·same owner 활성화·portable branch identity·old format read-only. 최종 사용자 완료는 새 Windows 프로세스에서 자기 Data와 Material, CAD 없는 PDE, 독립 Study를 열고 편집한다. 같은 문서의 이중 writable owner를 만들지 않는다. 재열기 시 결과 ID와 원 입력이 유지된다.

**시점:** PV-01 planning → UI-01 Windows 파일·창 → RG-01 same owner → IT-01 cold reopen. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `apps/research/desktop.py::launch_tool,open_saved_reference; scripts/start_cae_research.ps1; caelab/material_document.py::open; client.document_open`.

**재사용 test 후보:** `tests/test_material_documents.py;tests/test_retained_native_and_post_save.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-01, SC-04; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-01-01 | UI + REGRESSION | 동일 store/doc는 기존 owner 활성화; 다른 store는 구별; 결과 열기 무실행 | 두 프로세스 화면·문서 ID·원본 hash·launch receipt |
| FN-01-02 | REGRESSION + INTEGRATION | 이동용 사본이 원 store 없이 열리고 원본·이전 결과가 불변 | manifest diff, 이동/한글경로/새 프로세스 open receipt |

### V-02 / FN-02 — 셀 편집·동시 dirty·충돌·부분 저장을 잃지 않고 처리

**목적:** 어느 문서를 바꾸고 저장했는지 알고, 다른 client의 변경과 저장 실패에서도 자신의 입력을 복구한다.

**선행:** Material/Plan owner generation·save receipts·raw recovery capsule.

**완료 판단 / 독립 비교:** 두 client CAS, invalid buffer, partial save 중 이전 committed ref와 draft 보존; close와 job은 독립. 최종 사용자 완료는 숫자를 입력하는 중 외부 변경·부분 save·close를 발생시켜도 입력 소실과 결과 바꿔치기가 없다. 새 프로세스에서 saved/draft/refs를 구분하고 계속 편집한다.

**시점:** PV-02 → UI-02 input focus·paste·Undo → RG-02 stale/CAS/partial-save → IT-02 two-process recovery. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `caelab/material_document.py::command,_save; apps/research/material_window.py::_commit_cell_editor,_leave,refresh_document; numerical_document.py; native owners`.

**재사용 test 후보:** `tests/test_material_documents.py;tests/test_data_numerical_documents.py;tests/test_research_adoption_receipt_ui.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-01, SC-04, SC-11; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-02-01 | UI + REGRESSION | Enter/Esc/Undo/멀티owner paste가 대상 owner만 변경 | 행·셀 owner·generation 전후·실제 키 입력 기록 |
| FN-02-02 | REGRESSION + INTEGRATION | Material만 성공해도 Plan 실패와 old reference 보존; 재열기 무계산 | 중간 파일 실패 주입·saved hash·cold reopen |
| FN-02-03 | REGRESSION + UI | 동일 필드 stale 덮어쓰기 금지; 재승인 없는 새 ID 자동 재시도 금지 | 두 client stale/옛session/BUSY_EDIT receipt |

### V-03 / FN-03 — 열 순서와 단위가 다른 시험 파일을 같은 관측량으로 연결

**목적:** 숫자의 의미와 변환을 확인한 두 Data 관측을 Material에서 그대로 사용한다.

**선행:** 채널 metadata와 quantity conversion schema.

**완료 판단 / 독립 비교:** B 원단위→canonical exact hand calculation, P11=F/A0 및 λ/J 변환 조건, 시간축 보존. 최종 사용자 완료는 A/B의 같은 물리량이 같은 단위로 보이고 임의 셀의 원값→변환값을 손계산으로 추적한다. 열 재배치 후 채널 참조가 유지된다. 미확인 stress/strain measure로 fit을 실행하지 못한다.

**시점:** PV-03 → UI-03 two-file mapping → RG-03 raw/scale/offset identity → NR-01 unit/quantity conversion; IT-03 retained reopen. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `caelab/data_document.py::DataDocuments,diagnostics,source_preview; caelab/adapters/file_table.py; apps/research/data_window.py; data.update/data.import`.

**재사용 test 후보:** `tests/test_data_numerical_documents.py;tests/test_data_research_handoffs.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-01; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-03-01 | UI + NUMERICAL_REFERENCE | B 1250 µm→1.25 mm, 0.01 kN→10 N, 1000 ms→1 s를 원행과 대조 | 원 CSV hash·선택 row·계산식·변환값 |
| FN-03-02 | REGRESSION + NUMERICAL_REFERENCE | 현재면적/J 없이 true stress 요청은 차단; invalid draft 저장 | quantity conversion unit fixtures·positive stretch/unknown area 거절·saved refs |

### V-04 / FN-04 — 표–곡선으로 구간·mask·처리 이력을 편집

**목적:** 원자료를 보존하면서 사용할 구간과 처리 방법을 선택하고 재사용 가능한 관측을 만든다.

**선행:** mask inclusion compiler·stable row/channel identity.

**완료 판단 / 독립 비교:** 유한 quality-marked sample이 실제 objective에서 제외됨; quality/operation/Plan 교집합·view hide 불변. 최종 사용자 완료는 masked gap이 선으로 연결되지 않고 raw/processed/Plan 포함 샘플 수가 일치한다. plot에서 선택한 한 점이 정확 원행으로 이동한다. 저장 후 mask·recipe·선택을 재열고 수정한다.

**시점:** PV-04, UI-04 selection/keyboard/large table, RG-04 masks/recipe, NR-02 filter/interpolation reference, IT-03. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `caelab/adapters/file_table.py::validate_row_selection; caelab/data_document.py; apps/research/data_window.py; apps/research/curve_comparison_window.py`.

**재사용 test 후보:** `tests/test_data_numerical_documents.py;tests/test_research_comparison_context.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-01, SC-04, SC-11; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-04-01 | UI + REGRESSION | hide가 통계 제외를 바꾸지 않고 mask Undo는 원 row를 보존 | 마우스/키보드 선택 trace·row/point identity |
| FN-04-02 | REGRESSION + NUMERICAL_REFERENCE + PERFORMANCE | 비단조·gap·NaN 원자료 보존; 허용된 연산만 실행; 큰 파일 전체 UI reload 방지 | 원본/recipe hash·filter 독립 기준·메모리/지연 측정 |
| FN-04-03 | REGRESSION + NUMERICAL_REFERENCE | 품질 제외 finite sample·Plan 제외 sample은 raw/화면에 남되 objective에 포함되지 않음; hide와 holdout 독립 | 독립 residual 합 검산·mask/source/import hash·cold reopen |

### V-05 / FN-05 — 측정·교정·시험 조건을 예측과 맞추고 연구를 갱신

**목적:** 실제 측정이 예측의 어떤 양을 검증하는지 정의하고 새 자료로 모델 또는 판단을 갱신한다.

**선행:** 실제 등록 원문/측정 또는 synthetic fixture+metadata.

**완료 판단 / 독립 비교:** 교정/게이지 위치/방향/불확실성 UNKNOWN, train/holdout 독립성과 원본 불변. 최종 사용자 완료는 같은 raw sample에 적용한 교정·좌표/시간·게이지 정의와 모델 입력을 조회한다. 새 교정 또는 새 시험이 이전 결과를 덮어쓰지 않고 후속 연구에 연결된다.

**시점:** PV-05, RG-05 calibration lineage, NR-03 independent unit/calibration check, IT-04 measurement→revision→decision. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `caelab/data_document.py::test_metadata; caelab/data_comparison.py; caelab/research_context.py; caelab/study_document.py`.

**재사용 test 후보:** `tests/test_data_research_handoffs.py;tests/test_study_documents.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-03, SC-09, SC-11, SC-12; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-05-01 | REGRESSION + NUMERICAL_REFERENCE + INTEGRATION | raw→보정값→동일 관측량→판단의 정확 refs를 재열기 | 공개/합성 교정 reference·누락 metadata·source lineage |
| FN-05-02 | UI + NUMERICAL_REFERENCE | 미식별 계수는 fixed/unidentified로 보이고 다른 시험을 기록 | 합성 식별/비식별 두 사례·실제자료 판정 UNKNOWN |

### V-06 / FN-06 — 재료 법칙과 시험 이력을 직접 평가

**목적:** 관측 없이도 재료점의 응답·상태·기본 법칙을 조사하고 유효 입력의 결과를 보존한다.

**선행:** 선택 evaluator와 정확 stress/F/control convention.

**완료 판단 / 독립 비교:** prescribed-F와 traction-free의 다른 해; detF>0, P22/P33 해, cancellation/late result provenance. 최종 사용자 완료는 직접 평가와 fit이 별도 행동이며, 자유 인장과 횡구속 시험이 다른 결과를 낸다. 선택한 result의 응력척도/입력/상태를 재열기에서 유지한다.

**시점:** PV-06, UI-06 protocol edit, RG-06 result identity, NR-04 prescribed vs traction-free, IT-03. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `caelab/material_document.py; caelab/adapters/felupe_material.py::FelupeMaterialAdapter; apps/research/material_window.py; apps/research/native_material_window.py`.

**재사용 test 후보:** `tests/test_material_documents.py;tests/test_native_material_research.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-01, SC-04, SC-11; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-06-01 | UI + REGRESSION | 현재 실제 F·time·stress measure를 저장 결과에서 확인 | 직접 평가/late result/invalid draft 기존 회귀 + 시각 기록 |
| FN-06-02 | NUMERICAL_REFERENCE + REGRESSION | 동일 axial stretch에서 자유 횡응력≈0; 고정 F22/33와 구별; 실패 state 보존 | 독립 단축 탄성/초탄성 기준과 step convergence·반복 state reset |

### V-07 / FN-07 — 관측·잔차·holdout을 확인해 계수를 동정하고 채택

**목적:** 두 CSV에서 출발해 fit 후보의 장단점과 실패를 검토하고 충돌 없이 Material 새 개정으로 채택한다.

**선행:** 동일 embedded Plan/Material owner·fixed observation compiler·selected result retention.

**완료 판단 / 독립 비교:** r=sqrt(w/n)Δ/s 독립 합산; holdout 배제; missing details 무계산; 별도eval; target conflict/branch. 최종 사용자 완료는 서로 다른 두 CSV 매핑→mask→역할 설정→fit→부분/실패 후보→충돌→새 분기 채택→save→cold reopen을 중간 창 왕복 없이 마친다. 확인되지 않은 계수를 식별 성공으로 쓰지 않는다.

**시점:** PV-07, UI-07 full Material script, RG-07 frozen role/late result/adoption, NR-05 identifiable synthetic fit, IT-03. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `caelab/numerical.py::fit_model,compare_curves,_aligned; caelab/numerical_document.py::diagnostics,adopted_draft; apps/research/numerical_window.py; client.numerical_adopt`.

**재사용 test 후보:** `tests/test_workbench_numerical.py;tests/test_numerical_result_identity.py;tests/test_evaluation_candidates.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-01, SC-04, SC-11; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-07-01 | UI + REGRESSION | Material+Plan 동시 dirty·trial roles·정확 source ref를 한 화면에서 편집 | 두 CSV 클릭 경로·owner command trace·미확정셀 처리 |
| FN-07-02 | NUMERICAL_REFERENCE + UI | 없는 곡선/holdout은 없음 표시; 행 선택 무계산; 명시 평가만 새 ref, source masks 실제 objective 적용 | raw residual/weight/scale sum 검산·failed candidate retained log |
| FN-07-03 | REGRESSION + INTEGRATION | r17 fit 결과를 r18에 silent overwrite하지 않고 새 revision과 provenance를 보존 | 동시 변경·adoption stale·부분save·cold reopen 증거 |

### V-08 / FN-08 — 구성 적분·상태·접선을 연구하고 사용자 법칙을 등록

**목적:** 증분 크기·내부 상태·consistent/continuum tangent 차이를 독립 기준으로 검토한다.

**선행:** law/build/interface와 state restore 또는 명시 unsupported.

**완료 판단 / 독립 비교:** 독립 material point stress/tangent pair, δF central difference·증분 축소·history checkpoint; yield/failure 의미 분리. 최종 사용자 완료는 같은 discrete update의 초기 상태를 복원하며 perturbation 시험을 수행하고, 잘못된 tangent가 실패로 남는다. cyclic history에서 반복 횟수가 다른 초기화를 섞지 않는다.

**시점:** PV-08, UI-08 state inspection, NR-06 tangent/local integration independent tests, RG-08 input-state isolation. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `caelab/material_document.py::NATIVE_LAWS; caelab/adapters/felupe_material.py; apps/research/native_material_window.py; registered MFront adapters (exact interface별 추가 대조)`.

**재사용 test 후보:** `tests/test_native_material_research.py;tests/test_native_law_inputs.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-12; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-08-01 | UI + REGRESSION | 선택 증분→state/residual/tangent 원값·입력 ref를 조회 | 실패 증분·state IDs·raw artifacts |
| FN-08-02 | NUMERICAL_REFERENCE + INTEGRATION | 지원 pair/finite strain/interface별 증거가 없으면 해당 실행·export 차단 | 개별 law의 공식 기준·FD step sweep·cross-solver reference |

### V-09 / FN-09 — 검증된 재료 모델을 해석용 할당과 solver 카드로 전달

**목적:** 채택 계수의 물리 의미·단위·interface를 유지하며 특정 해석의 재료로 사용한다.

**선행:** 정확 law→지원 solver card/units/state converter.

**완료 판단 / 독립 비교:** 동일 constitutive response material-point/FE 단위·척도·state cross-check; unsupported card 차단. 최종 사용자 완료는 source coefficient와 solver deck의 실제 값/단위·할당 영역을 추적하고 single-element 기준이 적용된다. 변환 미지원이면 저장 가능한 초안과 명시 export 차단을 제공한다.

**시점:** PV-09, UI-09 assignment, RG-09 revision mapping, NR-07 solver-law/interface validation. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `apps/desktop_pre/fem_edit.py; apps/desktop_pre/freeze_analysis.py; caelab/simulation_document.py; material_document.py`.

**재사용 test 후보:** `tests/test_native_law_inputs.py;tests/test_native_condition_inputs.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-02, SC-10; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-09-01 | UI + REGRESSION | 미지원 조합·누락 failure 계수를 숨기지 않고 export 차단 | assignment 선택·draft 저장·카드 diff |
| FN-09-02 | NUMERICAL_REFERENCE | 성공 exit와 stress/strain/energy 동등성 구분 | 정확 solver/version/law와 허용오차·source/target curves |

### V-10 / FN-10 — 자기 CAD의 치수·피처를 편집하고 연구 변수로 등록

**목적:** 기존 native 이력을 유지하며 유효한 설계 변경과 탐색 가능한 변수 대상을 만든다.

**선행:** 새 native 문서·fixture 외 모델·등록 변수 handler.

**완료 판단 / 독립 비교:** 실제 feature/shape 변화와 ineffective observation scope, invalid feature 저장/export gate. 최종 사용자 완료는 fixture 이외 모델 두 개에서 치수 변경→재계산→변수 등록→재열기 재편집을 완료한다. invalid CAD는 해당 export/run을 막는다.

**시점:** UI-10 native CAD; RG-10 target identity; NR-08 geometry effect; IT-05 .caepre reopen. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `apps/desktop_pre/bridge.py; apps/desktop_pre/parameters.py; apps/desktop_pre/parameter_panel.py; plugins/fixture_design/upstream@3e48bf6`.

**재사용 test 후보:** `tests/test_native_contract.py;tests/test_native_face_catalog_actual.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-02, SC-05, SC-07; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-10-01 | UI + REGRESSION | constraint 재정렬 뒤 같은 semantic target 또는 명시 수리; 원 CAD 보존 | 서로 다른 FCStd/STEP에서 target·generation·형상 diff |
| FN-10-02 | UI + INTEGRATION | 무반응 관측이 전역 free 변수 금지로 확대되지 않음 | invalid draft save·export block·다른 Plan 값 유지 |

### V-11 / FN-11 — 조립·관절·운동 경로를 검토하고 설계 자세를 보호

**목적:** 조립 운동을 확인한 뒤 preview pose가 설계/FEM/저장에 섞이지 않도록 한다.

**선행:** 새 FreeCAD owner/session·Assembly/motion bridge.

**완료 판단 / 독립 비교:** P0→P1 pause/cancel/save/FEM/reopen; 실제 Placement readback; explicit Apply/Undo·stale restore 차단. 최종 사용자 완료는 P0→P1 preview→pause/stop/save→새 FreeCAD P0가 확인된다. 명시 pose 적용 시에만 새 generation의 P1을 저장하고 Undo도 증가 generation으로 기록한다.

**시점:** PV-11, UI-11 native motion/focus, RG-11 stale restore, IT-05 pose save/FEM isolation. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `apps/desktop_pre/motion.py::Motion; apps/desktop_pre/motion_panel.py; apps/desktop_pre/projects.py; apps/desktop_pre/bridge.py`.

**재사용 test 후보:** `tests/test_native_commands.py;tests/test_native_busy_completion.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-02, SC-05; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-11-01 | UI + REGRESSION | old restore가 새로운 P1 adoption을 되돌리지 못함 | P0/P1 placement·generation·save sequence |
| FN-11-02 | UI + INTEGRATION | cancel request/unsupported/terminal/restore를 실제 native 상태로 표시 | 긴 운동 계산·재생·owner 종료/재연결 기록 |

### V-12 / FN-12 — 해석용 표현·영역·재료·하중·조건을 모델에 배치

**목적:** 설계 형상에서 실제 해석 대상을 골라 의미와 단위가 맞는 입력을 구성한다.

**선행:** 해석 표현/region/assignment exact geometry·supported domain.

**완료 판단 / 독립 비교:** solid/shell/beam 지원별 단위/총힘/면압/중복/미할당·외부 Simulation/CAD-free source. 최종 사용자 완료는 실제 할당 대상과 입력 deck의 node/element/face set이 맞으며 누락 조건이 조용히 제거되지 않는다. 불유효 모델 저장 후 재열어 고칠 수 있다.

**시점:** UI-12 selection/Tasks, RG-12 mapping/export rejection, NR-09 load/unit checks, IT-06 prepare→run. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `apps/desktop_pre/fem_edit.py; apps/desktop_pre/fem_panel.py; apps/desktop_pre/mesh_binding.py; caelab/simulation_document.py`.

**재사용 test 후보:** `tests/test_native_condition_inputs.py;tests/test_native_structural_domain.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-02, SC-10; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-12-01 | UI + REGRESSION | 잘못된 body/face·중복/누락을 3D와 table에서 함께 수정 | 지원 입력 snapshot과 native target 대조 |
| FN-12-02 | NUMERICAL_REFERENCE + INTEGRATION | 지원되지 않는 card는 draft 저장·실행 차단; raw include 보존 | 각 조건/element/interface 수용과 정확 source/version |

### V-13 / FN-13 — 메시를 생성·개선하고 품질 결함의 실제 요소로 이동

**목적:** 국부 크기를 바꿔 실제 메시 품질과 재현 가능한 입력을 개선한다.

**선행:** native mesher·설정/quality metric·element ID inspector.

**완료 판단 / 독립 비교:** 나쁜 요소 selection↔3D/분포, 실제 국부mesh 변경, old mesh retained, stale applying 거절. 최종 사용자 완료는 선택 불량 요소가 실제 mesh ID와 일치하고 local refinement 후 quality/개수가 변한다. 실패·취소·stale 결과에서도 이전 실행 가능 mesh가 남는다.

**시점:** UI-13, RG-13 mesh result apply, NR-10 quality metric independent definition, IT-06. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `apps/desktop_pre/mesh_binding.py; apps/desktop_pre/fem_edit.py; plugins/fixture_design/upstream (mesh worker 범위)`.

**재사용 test 후보:** `tests/test_native_structural_deck.py;tests/test_native_face_catalog_actual.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-02; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-13-01 | UI + NUMERICAL_REFERENCE | 불량 element를 선택·격리·수정·재생성·비교 | 실제 element ID·품질 계산 범위·전후 mesh hash |
| FN-13-02 | REGRESSION + INTEGRATION | stale mesh는 보존되고 적용하지 않음; 취소와 종료 구분 | command/input/current generation과 old mesh 보존 |

### V-14 / FN-14 — 사용자 면 집합의 접촉을 정의·해석·복구

**목적:** 자기 모델의 접촉조건부터 압력·힘·gap·slip 결과와 형상 변경 후 재연결까지 끝낸다.

**선행:** 일반 사용자 face set exporter·지원 contact law/solver/parser.

**완료 판단 / 독립 비교:** frictionless/μ>0, gap/normal sign, load balance, mesh/refinement·연결복구; bounded benchmark 별도. 최종 사용자 완료는 자기 face sets→law/μ/gap/normal→unsupported 수정→run→pressure/force/gap/penetration/slip/time→save→split/normal flip→rebind cancel/적용→재열기를 완료한다. benchmark 하나의 PASS는 이 수용을 대체하지 않는다.

**시점:** PV-14, UI-14 selection/rebind; RG-14 exact-set/cancel; NR-11 contact force/gap/friction reference; IT-07 complete contact journey. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `apps/desktop_pre/fem_edit.py; apps/desktop_pre/mesh_binding.py; apps/desktop_pre/freeze_analysis.py; apps/desktop_post/measurements.py; existing contact benchmark adapters`.

**재사용 test 후보:** `tests/test_native_face_catalog.py;tests/test_native_condition_inputs.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-02; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-14-01 | UI + REGRESSION | 두 set/normal arrows/실제 gap과 입력 policy 확인; 미지원 저장 가능·run block | face IDs/geometry rev·unsupported 상태·normal 선택 |
| FN-14-02 | NUMERICAL_REFERENCE + INTEGRATION | 실제 pressure/force/gap/slip의 단위·위치·부호·time를 독립 검증 | 정확 law/formulation/solver version과 2개 사용자 모델·반력/force 기준 |
| FN-14-03 | UI + REGRESSION + INTEGRATION | Cancel은 old refs unresolved 유지; Apply는 새 geometry/contact rev와 재preflight | split 전후 target lists·면적·법선·Cancel/Undo/save/reopen |

### V-15 / FN-15 — 비선형 implicit 해석의 하중 단계·수렴·응답을 다룸

**목적:** 재료/기하 비선형·접촉을 포함한 static 또는 지원 implicit dynamics를 준비하고 실패 원인을 추적한다.

**선행:** 선택 nonlinear implicit adapter와 기준해·결과 reader.

**완료 판단 / 독립 비교:** large displacement/material nonlinearity별 반력·energy·increment/mesh convergence; solver success≠engineering pass. 최종 사용자 완료는 선형 limit·기하비선형·소성·접촉 사례를 각각 설정·실행·실패수정·저장하고 비교한다. ‘프로세스 정상 종료’와 수렴·유효·release를 따로 읽는다.

**시점:** PV-15, UI-15 step/convergence; RG-15 snapshot/retry; NR-12 linear/nonlinear/implicit dynamic references; IT-06. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `caelab/simulation_document.py; apps/research/simulation_window.py; apps/desktop_pre/freeze_analysis.py; existing registered structural adapters`.

**재사용 test 후보:** `tests/test_native_structural_domain.py;tests/test_native_law_inputs.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-03, SC-10; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-15-01 | UI + REGRESSION | 물리 time/iteration/walltime 분리; 실패 increment→원설정 수정 | 입력/export 로그·새 run vs retry |
| FN-15-02 | NUMERICAL_REFERENCE + INTEGRATION | 각 physics 기준을 충족한 조합만 run enabled; 다른 도구의 선행 gate 없음 | 해석해/공식 reference·mesh/increment convergence·반력/에너지 |

### V-16 / FN-16 — explicit 충격·낙하의 초기조건·접촉·에너지를 연구

**목적:** 조립 모델의 낙하 조건과 출력 요청을 준비해 실제 충격 결과와 실패를 비교한다.

**선행:** 무료로 검토된 OpenRadioss build/export/cards/reader.

**완료 판단 / 독립 비교:** impact IC/rigid/contact/energy/timestep/failure; analytic free-flight/energy와 독립기준, added mass 공개. 최종 사용자 완료는 자기 모델의 단위·IC·contact를 확인하고 실제 solver 결과의 에너지·forces·acceleration·time/failure를 저장/재열기한다. 한 benchmark로 제품 낙하 전체 수용을 선언하지 않는다.

**시점:** PV-16, UI-16 IC; RG-16 card/units; NR-13 impact energy/time/force references; IT-08 explicit workflow. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `caelab/simulation_document.py; apps/research/simulation_window.py; registered explicit adapters (범위별 추가 확인); existing Runner/Post`.

**재사용 test 후보:** `tests/test_research_catalog.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-02, SC-10, SC-12; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-16-01 | UI + REGRESSION | 미지원 card 누락 없이 차단; 측정 v/ω와 height-derived mode 분리 | 단위/회전/frame·IC 검산·export include manifest |
| FN-16-02 | NUMERICAL_REFERENCE + INTEGRATION | 정확 physical time·added mass·energy balance·failure 및 원값을 남김 | 기준 충돌/낙하·time/mesh sensitivity·원값 보존 |

### V-17 / FN-17 — 파괴·계면·피로 가정을 분리해 손상 연구

**목적:** bulk 소성, cohesive 손상, 재접촉과 반복 효과를 구별해 관측과 비교한다.

**선행:** 선택 bulk/interface law+state·regularization 정의.

**완료 판단 / 독립 비교:** traction-separation work=G, closure/compression transfer, history unloading; one cycle≠fatigue qualification. 최종 사용자 완료는 동일 모델에서 bulk/interface 결과와 압축 재접촉을 구분하고 에너지·단위·mesh sensitivity를 검토한다. 시험 없는 fatigue/release는 UNKNOWN이다.

**시점:** UI-17, NR-14 material/interface/fracture energy tests, RG-17 history identity, IT-07/08. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `caelab/material_document.py; caelab/simulation_document.py; apps/desktop_pre/fem_edit.py; apps/desktop_post/measurements.py`.

**재사용 test 후보:** `tests/test_native_law_inputs.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-02, SC-09, SC-10, SC-12; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-17-01 | UI + REGRESSION + NUMERICAL_REFERENCE | bulk와 interface damage·reclosure 결과를 따로 추적 | traction-separation/energy·mode mix·mesh study |
| FN-17-02 | NUMERICAL_REFERENCE + PHYSICAL_EVIDENCE | 단일 cycle을 수명으로 표시하지 않고 요구/미확인 보존 | law/시험 범위·cycle metadata·판정 UNKNOWN 근거 |

### V-18 / FN-18 — CAD 없이 방정식·약형식·ODE/PDE를 편집하고 해를 비교

**목적:** 모델 식·영역·공간·조건을 바꿔 지원 backend의 해와 독립 기준을 조사한다.

**선행:** 등록된 PDE adapter 또는 general weak-form extension.

**완료 판단 / 독립 비교:** 해석해/제조해 오차·mesh/order convergence·BC selection·dimension validation; CAD 없고 runtime 없어도 draft/reopen. 최종 사용자 완료는 식 수정→오류수정→domain/BC→실제 해→동일 norm 비교→save/reopen을 완료한다. 식 검사 성공을 numerical validation으로 표시하지 않는다.

**시점:** PV-18, UI-18 equations; RG-18 parser/refs; NR-15 manufactured solution/mesh rates; IT-09 CAD-free PDE. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `caelab/pde_document.py::DOMAINS,validate_draft,support_details; apps/research/pde_window.py; existing pde results/adapters; plugins/pde_nonlinear/reference.py::validate_settings,manufactured_rhs,manufactured_settings,model_declaration,assess`.

**재사용 test 후보:** `tests/test_research_pde_ui.py;tests/test_pde_post_metadata.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-06; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-18-01 | UI + REGRESSION | 현재 bounded AST/unit1를 정확히 보여주고 declared input을 바꿈 | equation node·boundary ids·retained result |
| FN-18-02 | NUMERICAL_REFERENCE + INTEGRATION | 미지원 방정식 draft 저장·실행 차단; 지원 equation 독립 기준 충족 | manufactured solutions·boundary/nullspace·space/order·time refinement |

### V-19 / FN-19 — 같은 Evaluation 정의로 단계·장 전달·연성 반복을 수행

**목적:** Plan 없이 재사용 평가 정의를 편집하고 실제 단계 결과·전달·미수렴/복구를 추적한다.

**선행:** 기존 Evaluation owner·bounded SI stages+FEniCSx runtime.

**완료 판단 / 독립 비교:** 실제 thermal output→Kelvin receiving field→ΔL=α(T−Tref)L; NOT_CONVERGED·full hash reuse·state restore. 최종 사용자 완료는 같은 Evaluation을 독립/embedded/MCP로 편집한다. 실제 열 결과→구조 수신 값을 조회해 ΔL 기준을 검증한다. NOT_CONVERGED·cancel·failed-stage reuse·cold reopen을 별도로 확인한다.

**시점:** PV-19, UI-19 same editor; RG-19 reference/partial restart; NR-16 field transfer/thermal expansion/iteration; IT-10. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `caelab/evaluation_definition.py::EvaluationDocuments,validate_draft,compile_definition,execute; apps/research/evaluation_window.py; evaluation.coupled`.

**재사용 test 후보:** `tests/test_thermoelastic_stages.py;tests/test_evaluation_mapping_lifetime.py;tests/test_evaluation_candidates.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-04, SC-06, SC-11; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-19-01 | UI + REGRESSION | Plan 없이 같은 kind=evaluation 문서를 저장/평가·Plan은 exact ref | 독립/embedded/CLI 동일 document·generation |
| FN-19-02 | NUMERICAL_REFERENCE + INTEGRATION | 실제 공급/수신 field와 ΔL=α(T−Tref)L 기준; ΔT offset 중복 금지 | computed thermal field·양쪽 port metadata·mask·free expansion reference |
| FN-19-03 | REGRESSION + NUMERICAL_REFERENCE + INTEGRATION | NOT_CONVERGED는 유효 목적값 아님; 반복 partial checkpoint 미지원 유지 | max iteration/cancel/late output·prefix identity·reopen |

### V-20 / FN-20 — DOE 후보를 만들고 영향도와 Sobol 분석을 구분

**목적:** 실제 후보의 입력/결과/실패를 보고 변수의 영향과 분석 한계를 판단한다.

**선행:** existing DOE/SALib optional engine·matched design/output set.

**완료 판단 / 독립 비교:** seed/bounds/rank·Sobol analytic function benchmark, missing/nonfinite no estimator shortcut; regression≠global sensitivity. 최종 사용자 완료는 복수 변수 DOE를 실제로 실행하고 행/점/원 evaluation이 동일하다. rank 결함·실패·Sobol 설계 불일치가 분석 성공으로 넘어가지 않는다.

**시점:** UI-20, RG-20 candidate identity/matched design, NR-17 analytic sensitivity, IT-11. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `caelab/numerical.py::run_doe,analyze_candidates,sample_sensitivity,analyze_sensitivity; apps/research/numerical_window.py; request_plan_window.py`.

**재사용 test 후보:** `tests/test_research_numerical_operations.py;tests/test_workbench_numerical.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-07; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-20-01 | UI + REGRESSION | 행 선택→원입력/응답, rank deficient 표시와 failed 후보 보존 | candidate table·engine request·rank/condition |
| FN-20-02 | NUMERICAL_REFERENCE + REGRESSION | ordinary LHS/누락 결과/순서 변경은 Sobol 차단 | analytic additive model·matched sample IDs·fail path |
| FN-20-03 | NUMERICAL_REFERENCE + INTEGRATION | 종속/비연속 변수를 continuous rounding으로 속이지 않음 | mixed-variable 기준 문제·원 domain admissibility |

### V-21 / FN-21 — 목표·제약과 관측으로 일반 최적화·역해석 수행

**목적:** 단일 값 조정부터 여러 domain의 역해석까지 명시한 목적·제약으로 계산하고 근거와 함께 채택한다.

**선행:** existing optimizer·fixed objective/constraints·supported evaluator.

**완료 판단 / 독립 비교:** known bounded constrained minimizer + inverse identifiability/holdout; penalty vs valid objective; multi-owner adoption. 최종 사용자 완료는 실제 여러 변수·제약 search와 inverse를 실행하고 유효 후보를 분리한다. 바뀐 target의 stale adoption·실패·취소·재열기까지 처리한다.

**시점:** UI-21, RG-21 budget/penalty/adoption, NR-18 known optimum/inverse identifiability, IT-11. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `caelab/numerical.py::optimize,fit_model; caelab/numerical_document.py; apps/research/request_plan_window.py; domain_candidate_adopt`.

**재사용 test 후보:** `tests/test_workbench_numerical.py;tests/test_numerical_adoption_polling.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-01, SC-11; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-21-01 | UI + NUMERICAL_REFERENCE | 가짜 응답·penalty 혼입 없이 best feasible/failed/infeasible 구분 | known optimum·constraint check·candidate history |
| FN-21-02 | NUMERICAL_REFERENCE + INTEGRATION | gradient 지원이 없으면 해당 method만 unavailable; 일반 search 유지 | adjoint vs FD·state/reset·budget/cancel·method capability |

### V-22 / FN-22 — 산포·상관 가정을 정의하고 UQ 결과를 읽기

**목적:** 불확실성 입력과 실패 표본의 영향을 알고 분포·초과확률을 해석한다.

**선행:** supported distributions·independent sampling implementation.

**완료 판단 / 독립 비교:** analytic mean/variance on linear response; failed fraction·conditional stats·correlation extension validation separate. 최종 사용자 완료는 각 분위수/초과확률에 valid count·failure conditioning과 정확 분포를 확인한다. 상관 요구가 삭제되지 않고 지원 미완료로 남는다.

**시점:** UI-22, NR-19 moments/tail/conditioning/correlation, RG-22 sample identity, IT-11. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `caelab/numerical.py::run_uq; caelab/optimizers/probabilistic_analysis.py (tree 확인); numerical_document.py`.

**재사용 test 후보:** `tests/test_research_numerical_operations.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-07, SC-09, SC-12; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-22-01 | UI + NUMERICAL_REFERENCE | 실패 표본 포함 전체 수·조건부 통계·tail bounds를 표시 | 독립 분포 기준·seed/matrix·failed fraction |
| FN-22-02 | NUMERICAL_REFERENCE | PSD/unit/순서 검사; correlation 미지원이면 explicit block | 상관 정상분포 독립식·샘플 moments·변수 매핑 |

### V-23 / FN-23 — 대리모델을 학습·검증하고 실제 solver 확인과 구별

**목적:** 보존된 해석으로 빠른 예측을 만들되 적용 범위와 holdout 오차를 확인한다.

**선행:** existing RBF surrogate·disjoint exact source/holdout points.

**완료 판단 / 독립 비교:** known held-out function error; no train/holdout leakage; out-of-range PREDICTED and explicit actual confirmation. 최종 사용자 완료는 holdout 오차와 extrapolation을 확인하고 새 실평가로 검증한다. 학습용 점 중복 또는 PREDICTED를 engineering PASS로 승격하지 않는다.

**시점:** UI-23, RG-23 split/identity, NR-20 known functions/interpolation/holdout, IT-11. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `caelab/numerical.py::fit_surrogate,Surrogate; apps/research/request_plan_window.py`.

**재사용 test 후보:** `tests/test_research_numerical_operations.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-07, SC-11; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-23-01 | UI + NUMERICAL_REFERENCE | 학습점 중복 거절·out_of_range와 PREDICTED 명시 | known nonlinear function·independent holdout·원 결과 |
| FN-23-02 | REGRESSION + INTEGRATION | 재열기 숨은 학습/solve 없음; 확인 결과는 새 evaluation | trained artifact/설정/결과 hash·새 프로세스 verify |

### V-24 / FN-24 — 다목적·분야별 trade-off에서 실제 후보를 비교

**목적:** Pareto 후보의 의미와 feasibility를 보고 여러 owner에 반영할 설계를 고른다.

**선행:** existing epsilon-DE/constraints·fixed real evaluation budget.

**완료 판단 / 독립 비교:** independent Pareto dominance / constraints / objective direction·infeasible retained; MDO coupling sensitivity when added. 최종 사용자 완료는 실제 후보와 Pareto 점을 상호 선택하고 infeasible 사유·원 결과를 확인한다. 분야별 의미를 유지한 채 후보를 새 revision으로 채택한다.

**시점:** UI-24, NR-21 known Pareto set/MDO reference, RG-24 all-child budget/cancel, IT-11. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `caelab/numerical.py::epsilon_optimize,analyze_candidates; caelab/evaluation_definition.py; request_plan_window.py`.

**재사용 test 후보:** `tests/test_research_numerical_operations.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-01, SC-06, SC-07, SC-11; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-24-01 | UI + NUMERICAL_REFERENCE | total budget·directions·infeasible 보존과 정확한 점/결과 | known Pareto set·thresholds·all-child counts |
| FN-24-02 | NUMERICAL_REFERENCE + INTEGRATION | 새 scheduler 없이 domain/Plan 경계 유지·설계 동기화 검증 | multidisciplinary reference·coupling residual·adoption receipt |

### V-25 / FN-25 — 로컬 작업의 진행·로그·취소·재시도를 관리

**목적:** 선택한 job/attempt의 실제 상태와 원 입력을 알고 실패나 중단 뒤 안전하게 이어간다.

**선행:** JobManager·child process ownership·native command monitor.

**완료 판단 / 독립 비교:** cancel queued/running/unsupported/completion race·INTERRUPTED/termination unknown·new attempt/workdir. 최종 사용자 완료는 queued/running/cleanup/terminal·미확인 종료를 정확히 구별하고 입력/로그/결과를 재열기한다. 창 닫기가 solver kill이나 재제출로 이어지지 않는다.

**시점:** UI-25, RG-25 cancellation race/restart/ID, IT-12 actual processes. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `apps/research/runner_window.py; caelab/jobs.py; caelab/research_execution.py; workbench_client.py`.

**재사용 test 후보:** `tests/test_research_runner_ui.py;tests/test_native_poll_completion.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-04, SC-08; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-25-01 | UI + REGRESSION | 같은 job/result/input을 열고 status 관측만으로 submit 없음 | selected attempt·log cursor·원입력/result identity |
| FN-25-02 | REGRESSION + INTEGRATION | 늦은 결과 보존; 종료 미확인 자동 retry/kill 금지 | 실제 cancel/cleanup receipt·response loss·service restart |

### V-26 / FN-26 — 외부 batch·SSH/HPC 실행을 로컬 연구에 연결

**목적:** 외부 계산을 정확한 후보/입력과 대응하고 원격 연결 실패에서도 결과를 회수한다.

**선행:** existing file batch exchange; real SSH/queue only if implemented/available.

**완료 판단 / 독립 비교:** candidate/exchange/units/hash mismatch rejection; remote disconnect+same ID reconciliation+partial transfer, no paid server. 최종 사용자 완료는 다른 PC 결과를 정확 exchange/candidate로 가져오고 missing/duplicate/stale/failed를 구별한다. 원격 연결이 끊겨도 중복 제출 없이 결과를 회수한다.

**시점:** UI-26, RG-26 exchange manifest/partial transfer, IT-13 actual authorized SSH/queue (환경 미제공 시 NOT_RUN). / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `caelab/numerical.py::export_batch,import_batch; existing jobs/client; SSH/Slurm/PBS implementation NOT_VERIFIED`.

**재사용 test 후보:** `tests/test_workbench_numerical.py;tests/test_research_numerical_operations.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-08; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-26-01 | UI + REGRESSION | stale exchange/duplicate/값변경 거절; missing은 NOT_EVALUATED | export→외부모의/실계산→import manifest·누락/실패 |
| FN-26-02 | INTEGRATION | reconnect에 중복 submit 없음; 실제 job termination과 file checksum 확인 | 사용자 제공 기존 host/권한·queue job/transfer/cleanup receipt |

### V-27 / FN-27 — 외부 결과를 독립 Post에서 열고 필터·측정으로 분석

**목적:** 원 solver 없이 지원 결과를 열어 field/time/선택·곡선을 다루고 분석 프로젝트를 보존한다.

**선행:** installed native ParaView/readers·registered source sets·workspace handlers.

**완료 판단 / 독립 비교:** source/pipeline/Apply/reset/original selection/probe/time curve/gap/native Undo·managed save/cold reopen. 최종 사용자 완료는 독립 외부 파일→필터·원값·시간/경로 측정→분석저장→새 session reopen과 누락 branch recovery를 수행한다.

**시점:** PV-27, UI-27 actual ParaView, RG-27 source/view/measurement identities, NR-22 interpolation/reduction, IT-14. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `apps/desktop_post/bridge.py::Owner.operations,dispatch; workspace.py; analysis.py; measurements.py; external.py; source_repair.py`.

**재사용 test 후보:** `tests/test_desktop_post_bridge.py;tests/test_desktop_post_external.py;tests/test_post_workspace_ownership.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-03; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-27-01 | UI + REGRESSION | 정확 source/time/association↔3D/표/곡선 선택 일치 | ParaView 실제 원값·selection ID·pending Apply/Reset |
| FN-27-02 | UI + INTEGRATION | 관리 Ctrl+S/close save가 동일 관문; native stock 설정은 별도 | 저장 원본/의존/pipeline/measurement·새 session reopen |

### V-28 / FN-28 — 다른 메시·좌표·시각·단위 결과를 검증된 대응으로 비교

**목적:** A/B 원값과 변환/보간값·차이·valid mask를 구별하고 틀린 차분을 막는다.

**선행:** current scalar POINTS/tet path; extension converters individually ready.

**완료 판단 / 독립 비교:** affine field independent formula at noncoincident A points, outside invalid; delta valid/%undefined at A0; cross-frame/time unit blockers. 최종 사용자 완료는 지원 다른 tet mesh에서 affine 기준 s=1+x+2y+3z, B=s+0.25 mm가 A 위치에서 delta=0.25 mm가 된다. outside·A0·nonfinite는 올바른 mask; time/unit/frame mismatch는 explicit repair 또는 차단이다.

**시점:** PV-28, UI-28 mapping preview; RG-28 stale/masks/order; NR-23 affine/units/time/basis; IT-14 reopen. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `apps/desktop_post/analysis.py::_validate_recipe,_mesh,OUTPUT_ARRAYS; apps/desktop_post/workspace.py; apps/desktop_post/source_repair.py`.

**재사용 test 후보:** `tests/test_post_analysis.py;tests/test_post_declared_metadata.py;tests/test_post_r3_repairs.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-03; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-28-01 | UI + NUMERICAL_REFERENCE | 동일 tet 또는 B→A scalar만 지원; percent mask와 delta mask 구분 | 독립 affine 내부/외부 점·source cell·Undo/save/reopen |
| FN-28-02 | NUMERICAL_REFERENCE + REGRESSION | 필수 F/J·coordinate/time mapping 없으면 해당 field diff 차단 | 단위 offset/벡터 회전/tensor stress/time gap·transform order reference |
| FN-28-03 | REGRESSION + INTEGRATION | 원 A 정상 유지·새 B branch로만 변경; retained old result 보존 | PVD 한 frame 변경·누락→수리·새 session mask/recipe 복원 |

### V-29 / FN-29 — Study에서 경쟁 가설·근거·판단·후속 연구를 관리

**목적:** 독립 연구 질문에서 증거를 비교하고 자신의 판단과 다음 연구를 보존한다.

**선행:** existing Study owner/ref resolver·registered evidence locator.

**완료 판단 / 독립 비교:** question/hypothesis/relation/decision edit·same exact evidence reopen·new turn/result does not adopt judgment. 최종 사용자 완료는 질문→경쟁 가설→지지/반박→명시 판단→후속 연구→save/reopen을 수행한다. discussion/결과 도착이 기존 판단을 자동 변경하지 않는다.

**시점:** PV-29, UI-29 standalone Study, RG-29 refs/no-execution/explicit decision, IT-15. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `apps/research/study_window.py; caelab/study_document.py; caelab/research_context.py; study.update`.

**재사용 test 후보:** `tests/test_study_documents.py;tests/test_research_study_ui.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-09, SC-12; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-29-01 | UI + REGRESSION | Study 단독 생성/저장; Expert 없이 판단·후속 문서 열기 | same owner·exact evidence refs·no hidden execution |
| FN-29-02 | REGRESSION + INTEGRATION | 새 evidence 자동 decision 변경 금지; invalid ref는 repair 가능 | source revision/hash drift·saved Study reopen |
| FN-29-03 | implementation regression + UI interaction | URL만 붙여도 근거 확인됨으로 표시하지 않고 원문 위치가 열리며 누락/변경 branch를 식별 | Study reference validation, 원문 등록 receipt 및 cold reopen |

### V-30 / FN-30 — Expert의 실제 토론·반론을 편집 Plan과 결과에 연결

**목적:** 자료와 실제 계산에 근거한 논의를 진행하고 사용자 반론·후속 연구를 보존한다.

**선행:** Discussion owner and optional eligible actual provider.

**완료 판단 / 독립 비교:** providerless draft/cold reopen; actual author/reply/topic/Plan/result identity; pause vs solver cancel; limit preserves drafts. 최종 사용자 완료는 provider가 있을 때 실제 답변→반론→계획 편집→actual result→후속 토론을 완료한다. 연결 없음·limit에서도 저장/재열기가 되며 유료 API로 우회하지 않는다.

**시점:** PV-30, UI-30 discussion; RG-30 ownership/no-fallback, IT-16 actual authorized provider (이번 NOT_RUN). / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `apps/research/expert_window.py; caelab/discussion_document.py; caelab/assist; client.discussion_plan; existing Expert commands`.

**재사용 test 후보:** `tests/test_discussion_documents.py;tests/test_discussion_plan_integration.py;tests/test_research_reply_ownership.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-09, SC-11, SC-12; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-30-01 | UI + REGRESSION | reply 대상/실제 source·provider author·Plan draft가 보존 | turn identities·pause/partial/save/reopen |
| FN-30-02 | INTEGRATION | no-provider/limit은 drafts 유지; 유료 fallback·자동 provider 전환 금지 | actual provider/정확 사용권·read evidence·result roundtrip; 미확인 시 NOT_RUN |

### V-31 / FN-31 — 선택 Workbench에서 문서 연결과 변경 영향을 탐색

**목적:** 자료/모델/Plan/result/Study의 정확한 관계를 찾아 원 owner로 이동한다.

**선행:** existing links / owner open handlers.

**완료 판단 / 독립 비교:** drag/menu same ref and Cancel, new revision≠broken reference, no graph-only source editing/scheduler. 최종 사용자 완료는 모든 graph 동작을 목록/키보드로도 수행하고 정확 owner를 연다. 링크 변경이 다른 문서 원값을 몰래 편집하지 않는다.

**시점:** UI-31, RG-31 refs/stale/drag cancel, IT-15. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `caelab/research_context.py; caelab/desktop_links.py; apps/research/desktop.py; existing service reference operations`.

**재사용 test 후보:** `tests/test_connected_evaluation_study.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-09, SC-11, SC-12; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-31-01 | UI + REGRESSION | drag/menu 동등; broken과 new revision 별도; 원본 편집 없음 | relation before/after·Escape·keyboard·correct window |

### V-32 / FN-32 — 결과·근거·검증 상태를 보고서와 인계로 보존

**목적:** 어떤 입력과 기준에서 무엇을 확인했는지 설명 가능한 보고서를 만든다.

**선행:** retained artifacts/units/validity/decision refs.

**완료 판단 / 독립 비교:** report includes raw/failure/missing refs and provenance; F05 immutable; export does not set release PASS. 최종 사용자 완료는 보고서의 모든 수치가 source input/result/recipe로 연결되고 원 실패와 UNKNOWN이 유지된다. F05 원값 3.32295e-6 >1e-6을 변경하거나 전체 설계 gate로 사용하지 않는다.

**시점:** UI-32, RG-32 source/report integrity, IT-17 report→original evidence. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `caelab/research_context.py; existing artifact/evidence/provenance records; report implementation specifics NOT_VERIFIED`.

**재사용 test 후보:** `tests/test_retained_native_and_post_save.py;tests/test_study_documents.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-04, SC-12; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-32-01 | UI + REGRESSION + INTEGRATION | 수치/plot/판단 source를 재열고 실패/UNKNOWN/NOT_RELEASED 유지 | 보고서와 source 값·원 file hash·broken link 처리 |

### V-33 / FN-33 — 무료 실행 환경·도구 설치 상태와 실제 지원을 확인

**목적:** 어떤 문서를 지금 편집하고 어떤 계산을 실행할 수 있는지 비용 없이 확인한다.

**선행:** actual Windows launcher/runtime selection and explicit probe handler.

**완료 판단 / 독립 비교:** REGISTERED/NOT_PROBED/receipt separation, Unicode paths, separate native runtimes, exact package licenses. 최종 사용자 완료는 미설치 도구를 준비됨으로 표시하지 않는다. 실제 사용권·라이선스가 확인된 무료 경로로 실행하며 Windows 100/125/150/200%에서 readable/focus/file paths를 확인한다.

**시점:** PV-33 license review, UI-33 clean Windows/DPI, IT-18 install/open/readiness. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `scripts/start_cae_research.ps1; apps/research/desktop.py; workbench_client.py::backend_readiness; openscience/workbench_mcp.py`.

**재사용 test 후보:** `tests/test_research_catalog.py;tests/test_native_contract.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-01, SC-10; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-33-01 | UI + INTEGRATION | 도구 선택 없이 파일로 바로 맞는 owner; browser 주화면 없음 | 실제 Windows shortcuts/한글경로/multiple stores |
| FN-33-02 | UI + INTEGRATION | version probe만으로 solver benchmark/GUI 수용 PASS 표시 금지 | 정확 installed versions/notices·probe receipts·NOT_PROBED 상태 |

### V-34 / FN-34 — GUI·CLI·Python·선택 MCP에서 같은 문서와 명령 사용

**목적:** 자연어/스크립트로 수행한 작업을 실제 열린 문서에서 확인하고 동일 결과를 분석한다.

**선행:** same owner commands through advertised wrappers.

**완료 판단 / 독립 비교:** same ID/ref/value/mask/result; stale/session/BUSY/duplicate/hash conflict and cache freshness; native GUI actual readback. 최종 사용자 완료는 같은 문서에 GUI→CLI/MCP 읽기와 typed edit→GUI 확인을 수행하고 stale/BUSY/두 host·응답유실을 올바르게 처리한다.

**시점:** RG-34 command identity/idempotence, UI-34 actual same-window roundtrip, IT-19 optional client. / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `openscience/workbench_mcp.py::document_command,local_input_register,command_status; caelab/workbench_client.py; apps/desktop_pre/bridge.py; apps/desktop_post/bridge.py`.

**재사용 test 후보:** `tests/test_native_contract.py;tests/test_lab_research_service.py;tests/test_connected_research_http_ui.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-02, SC-03, SC-04, SC-05; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-34-01 | REGRESSION + INTEGRATION | 같은 결과 refs·actual values/selection; fake success나 active doc 추정 없음 | 두 native hosts·same session/generation·GUI/CLI/Python/MCP receipts |

### V-35 / FN-35 — 실제 실험장비 연동과 교정 반복을 지원 범위로 유지

**목적:** 장비가 준비된 환경에서 계획→실험→측정→보정의 반복을 정확히 기록한다.

**선행:** real authorized hardware/driver/free path/operation limits; absent here.

**완료 판단 / 독립 비교:** file loop independent; acquisition cancel≠physical emergency stop; sample/time/calibration identity; no actuation here. 최종 사용자 완료는 권한 있는 실제 장비가 준비되면 plan→data→calibration→model revision→next test와 중지/복구를 수행한다. 그 전 상태는 NOT_VERIFIED/NOT_RUN이며 fake device result를 만들지 않는다.

**시점:** PV-35 interface planning, RG-35 replayed recorded IO, PH-01 actual authorized device integration (이번 NOT_RUN). / 계획 검토는 지금; 실제 구현·수치·Windows 수용은 준비된 해당 경로에서 수행.

**재사용 source/command:** `existing Data/Study/Plan/evidence; actual device driver NOT_VERIFIED`.

**재사용 test 후보:** `tests/test_data_research_handoffs.py`. 새 실행 PASS 없음.

**연결된 클릭 경로:** SC-09, SC-12; 시안 클릭과 실제 계산 수용은 별도.

| 관련 backlog | 시점 | 구체 완료 조건 | 필요한 실행 근거 |
|---|---|---|---|
| FN-35-01 | PHYSICAL_INTEGRATION | 실측 data/장비 종료 acknowledgment·실험 input과 보정 lineage 확인 | 실제 장비/교정/권한·raw streams·stop/recovery receipts |

## 독립 수치 reference의 구체 기준

| 경로 | 독립 기준 / 입력 | 미리 정할 tolerance / 보존 | 금지되는 대체 |
|---|---|---|---|
| 단위/quantity mapping | A/B 수기 지정 샘플, mm/µm/N/kN/s/ms/K/°C, P11=F/A0 | 정수 scale에 의한 상대 floating roundoff와 offset0점·입력범위 | label만 바꾸거나 J=1 추정 |
| Fit residual | 고정 mask/n/weight/scale의 작은 배열을 직접 합산 | n,curve contribution,raw RMSE,scaled objective,holdout exclusion | objective 좋아지도록 실패 sample drop |
| Material point | 선택 law의 정확 measure/pair; prescribed F와 traction-free 각각 독립 기대값 | 실제 tangents·stress norm·증분과 finite-difference step 미리 기록 | constrained F22=F33=1을 uniaxial free라고 부르기 |
| Contact | 단순 두 body equilibrium/friction limit/initial gap orientation, mesh/increment refinement | solver convention과 force integration·gap/penetration 정의별 기준 | benchmark fixture 하나를 arbitrary faces/full contact 완료로 확대 |
| SI thermal→structure | 실제 열계산 uniform Kelvin field 전달, ΔL=α(T−Tref)L | same mesh/metre/K, α/L/Tref·실제 element/BC/build·수치허용오차 사전 기록 | 구조에 온도상수 직접입력만 하고 transfer PASS |
| Post B→A | 서로 다른 선형tet, noncoincident A points, s=1mm+x+2y+3z, B=s+.25mm | inside Δ=.25, outside invalid; independently evaluate A coords; mask/pipeline reopen | resampler output을 기준값으로 다시 사용 |
| UQ/Sobol/RBF/MOO | 알려진 linear moment/function-index, disjoint held-out function, 직접 dominance 판정 | 표본/seed/design hash·불확실성/예산·실패율·domain bound | regression을 Sobol로, prediction을 solver observation으로 취급 |

이 표의 mathematical fixture는 일반 engineering approval을 대신하지 않는다. 실제 수치 tolerance는 정확 adapter/reference의 입력·order·unit·norm과 함께 실행 **전에** 정한다. 이번 UI fixture의 .014MPa, residual1.4e-5, 품질.18 등의 숫자는 threshold 변경이나 실행 결과가 아니다.

## 최종 연결 수용과 중단 기준

SC-01/02/03을 실제 source/solver/result로 구현한 뒤, 해당 tools의 새 process reopen까지 닫는다. 한 경로 실패가 독립 다른 도구 구현을 막지 않는다. 문서만 완성됐거나 screenshot처럼 보인다고 사용자 업무 수용을 완료 처리하지 않는다. 핵심 command/owner/ref/값 손실·silent overwrite·wrong units/mask·미지원 실행 성공 표시는 P1로 수정한 뒤 재검토한다.

변경하지 않은 mesh/solver/physics fixture의 재실행은 구체 영향이 있을 때만 한다. F05 `3.32295e-6 > 1e-6`, 실패한 AMD 시도, UNKNOWN/NOT_RELEASED 원상태를 보존한다. 실제 장비·재료·공차·내구·승인 기준이 없는 경우 engineering release는 UNKNOWN/NOT_RELEASED다.
