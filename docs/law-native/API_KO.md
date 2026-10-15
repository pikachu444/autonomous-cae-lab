# API_KO — 정확한 법칙·피팅·저장 Material→native interface

요청 PRO-LAW-NATIVE-20261015-01. 아래 API는 첨부 3ba7c97 소스의 기존 owner/command 구조를 소비한다. source의 기존 shared 파일 전체를 최신 main에 덮어쓰지 않는다.

## 1. Backend와 값 계약

`material.law_native`는 PreparedEvaluation 재료점 backend다. `structure.felupe.law_native`는 고정 FELUPE 11.1.3 공간 FE backend다. 모델 ID는 `drucker_prager_linear`, `neo_hooke`, `single_branch_maxwell`이다. 모델명은 다른 구성식으로 치환하는 별명이 아니다.

`plugins.material_point.law_native`:

```python
law.default_settings(model)                  # 새로운 명시 입력 값만 생성; 계산 0
law.validate_settings(settings)              # 순수 검증, deep copy
law.describe_inputs(settings)                # 기존 fit binding용 계수·단위·범위·기본 free/fixed
law.bind_inputs(settings, coefficient_values)# 계수만 변경한 검증된 copy
law.declaration(settings)                    # pair/frame/unit/state/variant 명시
law.update(settings, accepted_state, F, time)# 순수 constitutive trial; 전달 state 불변
law.initial_response(settings)               # accepted 초기점; 초기 DP return을 몰래 수행하지 않음
```

필수 settings는 정확히 `model, parameters, stress_unit, time_unit, time, deformation_gradient, initial_state`이며 선택 필드는 `boundary_control, tangent_probe`다. 알 수 없는 필드는 거절한다. 스트레스 단위는 Pa/kPa/MPa/GPa 중 명시, 시간 단위는 s만 가능하다. F는 모든 시점의 3×3 배열이고 시간은 2..256개, 비음수·엄격 증가·최대 1e6 s다. 첫 시간과 F/strain은 accepted 초기 상태와 같아야 한다. 첫 점에서 누락된 내부 상태를 0으로 채우지 않는다. `default_settings`가 생성하는 0 초기값은 사용자에게 보이는 명시 seed이지 누락값 복구가 아니다.

DP 계수는 E,nu,alpha,beta,k0,H이고 직접 계수 convention만 받는다. 상태는 time,strain_kelvin,plastic_strain_kelvin,kappa다. 각도/응집력 자동 환산은 없다. SLS는 K0,G0,K1,G1,tau와 time,strain_kelvin,viscous_strain_kelvin,dissipated_energy,work를 모두 요구한다. Neo-Hooke는 mu,lmbda 및 초기 time,deformation_gradient이며 플라스틱/점성 내부변수를 받지 않는다.

Kelvin6 순서는 xx,yy,zz,xy,xz,yz이고 shear 값은 physical tensor shear의 sqrt(2)배다. 유한변형은 row-major physical9 xx,xy,xz,yx,yy,yz,zx,zy,zz다. 두 표현을 자동으로 같은 pair로 취급하지 않는다. 모든 법칙은 명시된 material_cartesian frame에서 평가한다. Neo는 PK1/F와 dP/dF, 작은 변형 DP/SLS는 infinitesimal Cauchy/Kelvin strain과 discrete dσK/dεK다.

`law_native_history.evaluate_history(settings)`는 기존 boundary-control solver를 재사용한다. `boundary_control = {stress_components: {yy:[...],zz:[...]}, solver:{atol,rtol,max_iterations,max_backtracks}}`처럼 각 시점의 물리 응력을 지정한다. 시점 수와 frame/pair를 고정한다. `tangent_probe = {increment:1, steps:[1e-6,1e-7,1e-8]}`는 한 noninitial 증분만 검사한다. 모든 perturbation은 동일 accepted state에서 시작한다. 중앙차분·일방차분·active-set 차이·미분불가를 각각 기록한다. 잘못된 접선은 FAIL이며 nominal trial도 다음 증분에 commit하지 않는다.

성공·실패 평가 결과는 기존 `save_evaluation`/reader를 사용한다. 실패 증분·원입력·partial stress/trial state/local residual·last accepted state를 구분한다. inspector는 실제 없는 값이나 에너지를 추정하지 않는다. DP의 누적 소산에너지, SLS 초기점의 dt 없는 접선 등은 unavailable이다.

## 2. 기존 Numerical/Data fit 연결

Workbench.describe_inputs와 기존 prepared evaluation/bind_inputs에 위 법칙별 선언을 연결했다. 원 Numerical Plan compiler, optimizer, frozen-fit-inclusion.v1 producer/validator, sample lineage, sample/test weight, holdout, 후보 상세/CAS/evidence 저장소를 교체하지 않는다. 초기 상태·측도·시간·법칙 ID는 자유 fit 계수가 아니다. alpha와 beta의 연동 조건 0≤beta≤alpha 및 실제 해석 admission을 모든 후보에 적용한다. 실패 후보의 trial state를 다음 후보에 사용하지 않는다.

공개 실행 예제 `examples/material-tests/law-native/point_fit_workflow.py`는 독립 p–q 기준으로 생성한 합성 인장/전단을 fit하고 압축/구속편차를 holdout으로 둔다. E,nu,alpha,beta,H를 고정하고 k0만 식별한다. 인장만으로 마찰·팽창·경화를 식별했다는 주장이 아니다. 명시 후보 증거 capture와 기존 domain_candidate_adopt CAS 이후에만 Material working input을 바꾸고 다시 저장한다. 자동 추가 계산/채택은 없다.

Neo fit는 실제 FELUPE가 필요하다. SLS/DP의 계수 binding은 제공하지만 이번 end-to-end 다시험 실행은 DP k0 사례다. 다른 조합의 실제 식별성/회귀/구속 검증을 이 기록으로 대신하지 않는다.

## 3. 원 Material과 새 고정 interface 사이의 mapping

`caelab.material_fe_transfer.source_snapshot(existing_material_owner, reference)`의 reference는 다음 세 키만 받는다.

```json
{"document_id":"실제 M...", "saved_revision":"실제 R...", "input_sha256":"실제 canonical draft SHA256"}
```

owner가 기존 immutable revision을 verify하고 원 draft, calibration/adoption/run provenance, retained 10개 kernel/source 텍스트와 SHA256, source revision/input identity를 읽는다. 원 문서·working·saved revision 3개 guard를 검토 시 고정하고 Apply 시 다시 검사한다. HTTP/import/archive가 private snapshot이나 arbitrary build 권한을 만들지 못한다.

새 `material.law_native` 저장은 기존 revision 내부에 `law-native-source.json` asset을 추가한다. 별도 store/owner가 아니다. 이는 고정 Python interface source identity이며 MFront build binary가 아니다. build 상태는 NOT_REQUIRED, arbitrary-source permission은 NOT_GRANTED다. 외부 numeric binary identity는 실제 worker의 runtime.json에 별도로 남는다.

명시적으로 허용한 legacy mapping은 (1) 원 `material.felupe`/neo_hooke의 동일 logJ 모델, (2) 원 `material.mfront.viscoelastic`의 원 validator를 통과한 단일 branch canonical 이력과 동일 5계수/상태 convention이다. 원 draft·온도 선언·이력은 snapshot에 남으며 새 fixed interface 사용이란 provenance를 붙인다. athermal fixed 모델이며 새로운 온도 의존 계수나 external state를 추정하지 않는다. SVK/J2/user-source를 새 이름의 다른 모델로 mapping하지 않는다.

`map_to_mpa`는 stress 계수·stress control tolerance/values·SLS work/dissipation 단위를 명시 변환한다. strain/kappa와 실제 시간은 변경하지 않는다. FE 길이는 mm, stress는 MPa, force는 N으로 고정한다. coefficient별 source 값/단위/factor/target 값과 출처를 preview에 남긴다.

## 4. Native typed 명령 — 새 endpoint 없음

기존 Workbench/Client.document_command를 사용한다. 매번 정확한 native document id, session_id, expected_generation 및 새 command_id가 필요하다. 선택은 다음 다섯 키다.

```python
selection = dict(analysis_id='현재 Analysis ID', material_id='현재 Material ID',
                 region_id='기존 FEM region ID', mesh_id='현재 Mesh ID',
                 solver_id='현재 native solver 문맥 ID')
```

| operation | public arguments (selection 공통) | 실제 효과 |
|---|---|---|
| pre.fem.law_read | selection | 보존 assignment·draft 읽기. runtime/source 경로 없이 읽음 |
| pre.fem.law_save | selection, raw | 기존 native metadata/transaction에 미완성 전달 초안만 저장 |
| pre.fem.law_preview | selection, source, options | 현재 target과 저장 revision을 고정한 순수 preview; owner/solver 수정 0 |
| pre.fem.law_apply | selection, review_command_id | 같은 native document/session에서 완료된 preview를 재검사하고 기존 transaction에 한 번 적용 |
| pre.fem.law_freeze | selection | 이미 적용된 정확한 assignment의 Simulation draft 생성; job 생성 0 |

options는 `solver,boundary,purpose` 세 키다. solver는 FE default의 정확한 backend/version/step/max_iterations/force_tolerance_N이다. boundary는 `{mode:'affine_boundary',origin_mm:[0,0,0]}` 또는 명시 조건에 맞는 `uniaxial_zero_lateral`이다. purpose는 `CONSTITUTIVE_SPECIMEN`만 허용한다. 누락된 strength/failure를 0이나 추정값으로 채워 engineering/failure 계산을 허용하지 않는다.

preview에는 saved coefficient/state/time/source/build identity와 실제 interface JSON, mapping, 필수 mesh/boundary/state/time 값의 출처, 차단 이유가 있다. `status=READY_FOR_EXPLICIT_APPLY`여도 미적용/미실행이다. `review_sha256`는 source/options/target 전체를 고정한다. target은 native document/session/generation, analysis membership와 physics, 현재 재료, region/geometry, native mesh 번호·연결·shape·global placement, solver 문맥/버전, execution backend/element/step을 포함한다.

Apply는 기존 native transaction 전/안에서 두 번 재검사한다. `CAELabLawNative` 읽기전용 property와 기존 metadata에 assignment를 저장하며 기존 `Material` dictionary/다른 region/section/orientation/loads/contacts/mesh를 쓰지 않는다. source가 transaction 중 변경되면 rollback을 요구한다. FreeCAD 실제 Undo/Redo 보장은 제공된 native smoke를 실행해야 검증된다; Python fixture 통과를 native 결과로 대신하지 않는다.

동일 command_id의 유실 응답은 기존 receipt 조회/회복으로만 처리한다. 다른 공개 arguments·target session/generation으로 같은 ID를 재사용하면 conflict다. 새 Material revision은 이미 적용된 native property나 과거 job을 자동 갱신하지 않는다. 명시 새 review/apply가 필요하다. Source/target/current kernel 변경은 SOURCE_CONFLICT, TARGET_CONFLICT, INTERFACE_SOURCE_CONFLICT, ASSIGNMENT_STALE 등의 명시 오류가 된다.

보존 읽기는 당시 source text/hash로 검사하고 현재 compiler/solver/native material source 경로를 필요로 하지 않는다. 새 계산은 현재 trusted kernel과 당시 retained kernel이 동일해야 한다. 보존한 arbitrary source를 자동 실행하지 않는다. archived 라이브 경로를 쓰는 새 Apply는 금지되고 현재 owner에서 reference를 새로 resolve해야 한다.

## 5. FE 적용 범위·결과

whole-solid 하나, 활성 material 하나, 원 reference geometry의 full-integration Hex8만 허용한다. native 하중/구속, contact/J2/shell/beam, dynamic, 비identity global placement, partial region, 다른 mesh source, 다른 기존 Material reference는 차단한다. 이는 기존 Pre의 기하/메시/경계조건 책임을 가져오지 않기 위한 전용 시편 admission이다. SMESH→VTK 고정 순서 `(0,3,2,1,4,7,6,5)`와 양의 Jacobian을 검사하며 모호한 노드 순서를 추측으로 수리하지 않는다.

`caelab.law_native_fe.default_settings(model)`는 공개 27절점·8 Hex8·2×2×2 Gauss점/요소 시편을 만든다. 검증 범위는 9..4096절점, 1..512요소, 최대 128시간점, 실제 내부 자유 DOF가 있는 메시다. 원 solver max_iterations1..80, absolute force tolerance≤1e-7 N(기본1e-8 N)이다. FELUPE native 상대 잔차 허용치1e-12는 별도 무차원 값으로 남긴다. 전역 solve의 success만 믿지 않고 free DOF force residual N과 전체 반력 평형을 검사한다.

고정 worker는 매 global Newton trial마다 모든 적분점의 동일 accepted 상태를 복원한다. 수렴 완료 시점만 commit한다. global/local 실패는 accepted prefix, 실패 증분, trial F/응력/상태, native relative residual trace, 실제 free DOF, 원 stdout/stderr 및 checkpoint를 보존한다. actual FE 후 모든 적분점의 응력과 F를 같은 측도·시간·경계의 point 결과와 비교한다. 평균 응력이나 point 결과를 FE field로 복사하지 않는다.

결과 channel `ip_stress`, `displacement`, `reaction`은 실제 공간 결과다. 기존 Simulation 곡선창용 `ip0_stress_xx` 등은 cell0/quadrature0의 실제 선택값이며 선택 identity를 함께 남긴다. `ip0_stored_energy`/`ip0_dissipated_energy`는 제공된 constitutive quadrature 출력만 기록한다. native solver 전역 에너지와 ParaView spatial exporter는 unavailable로 남긴다. Neo는 PK1, DP/SLS는 small-strain Cauchy다. raw physical9/Kelvin6 형식은 metadata를 따른다.

`law_freeze` 반환 `simulation_draft`로 기존 simulation owner를 열고 사용자가 별도로 `simulation.evaluate`한다. 이 호출이 기존 JobManager와 고정 worker/reader를 사용한다. 현재 assignment가 있는 native Analysis의 옛 CalculiX freeze/contact export는 guarded되므로 탄성 카드로 조용히 우회하지 않는다. 독립되는 다른 Analysis의 기존 J2/CalculiX 경로는 변경하지 않는다.

## 6. GUI 연결 및 인수 경계

기존 `apps.research.material_window`의 법칙 메뉴 및 저장 개정 재열기 분기에 `LawNativeMaterialWindow`를 연결했다. 기존 값 편집·큰 곡선·Plan·Undo/저장/결과 owner를 재사용한다. `LawNativeTransferDialog`는 기존 등록 Pre owner만 선택하고 초안/preview/apply/freeze/Simulation을 분리한다. 잘못된 raw `1e`는 `editor_raw_text`로 그대로 저장할 수 있으며 그 메모를 Material 계수로 적용하지 않는다. dirty close는 Save/Discard/Cancel, pending 명령은 결과 확인 전 닫지 않는다. 원 Qt 공통 위젯을 복제한 새 앱은 없다.

Sol은 현재 main의 GUI 구조/한글 label/large curve/normal·narrow·Enter/Esc/Undo·dirty close에 정합해야 한다. 이 소스의 Qt 표시는 NOT_RUN이다. 내부 hash/ID가 전송 상세 pane에 보이는 부분의 최종 UX와 0원 설치 배포는 root/Sol의 실제 확인 대상이다.
