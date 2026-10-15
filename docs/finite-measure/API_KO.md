# 유한 관측 API 및 통합 경계

## 입력과 관측 변환

`caelab.finite_measure_input`은 Qt와 분리한 현재 Data 초안의 compiler다. `mapping(config)`은 실제 원 열을 `fm_load`, `fm_deformation`, `fm_area`, `fm_J`, `fm_Fxx` 등으로 가져오는 기존 mapping을 만든다. 힘을 stress로 이름만 바꾸지 않는다. 시간 단위는 기존 TIME 표에 따라 실제 수치 변환하며 원본 mapping에 변환 근거가 남는다. 힘·길이·면적 변환은 기존 `data_processing.convert_quantity`를 사용한다.

`definitions(config)` / `recipe(config, existing)`은 기존 recipe에 `Ofinite*` 유한변환 연산을 연결한다. 이 기능이 소유한 연산만 교체하며 다른 연산은 유지한다. 같은 출력 이름의 충돌을 거절한다. `local_preview(config, rows)`는 실제 계산·행별 오류를 보여 주는 비보존 미리보기이며 frozen 관측이나 canonical 원행 identity를 발행하지 않는다. 실제 Plan source는 기존 import → processing apply 경로만 사용한다.

설정 원문은 Data draft의 선택적 `finite_measure` 필드에 저장한다. 값은 미완성 문자열을 포함할 수 있다. `verify_processing_specification(draft, imported)`은 현재 치수/측도 설정과 현재 recipe·원 import mapping이 같은지 확인한다. 새 `1e` 초안 밑에서 옛 정상 식을 실행하는 것을 막는다. 과거 immutable processing을 읽을 때 현재 설정으로 재-freeze하지 않는다. GUI 설정이 없는 직접 작성 finite 연산은 그 연산의 정의를 검증한다.

`caelab.finite_measure`의 `make_definition`, `operation`, `evaluate_row`가 순수 수학 경계다. 변환 정의 schema는 `caelab.finite-observation/1`, 범위는 `uniaxial_coaxial`, frame은 `material_cartesian`이다. axis는 x/y/z 중 하나이며 방향 성분을 함께 검증한다. 출력은 `first_Piola`, `finite_Cauchy`, `engineering_strain`, `stretch`, `log_strain`이다.

현재 구현식:

```text
Pii = F_axial / A0
lambda_i = 1 + DeltaL_gauge / L0
e_i = lambda_i - 1
log_strain_i = ln(lambda_i)
sigma_ii = (lambda_i / J) * Pii
sigma_ii = F_axial / A_current
A_current = A0 * J / lambda_i   (중복 근거 일치 검사)
```

A0/L0는 필요한 연산에서만 양수 숫자·단위·evidence를 요구한다. 예를 들어 현재 면적과 힘만으로 sigma를 계산할 때 사용하지 않는 L0/J를 요구하지 않는다. 반면 J 방식의 진응력에 lambda 근거가 없으면 실행하지 않는다. 선택된 중복 면적/F/J/변형 근거는 일치해야 한다. crosshead를 gauge로 쓰거나 등체적 J=1을 쓰는 경우 `enabled=true` 및 이유가 있는 명시 가정이어야 하며 측정값으로 위장하지 않는다.

전체 F를 쓸 때 9개 값·단위·방향·같은 frame·양의 determinant·동축성을 검사한다. scalar 단축 변환은 비동축 F를 거절한다. 별도 `full_tensor_cauchy(P,F,stress_frame,gradient_frame)`은 충분한 전체 P/F와 같은 정규직교 frame에서만 tensor 식을 지원한다. 이 helper가 있다고 일반 full-F 시험 입력/피팅 GUI 전체를 지원한다고 선언하지 않는다.

## 원행 DAG와 선택

`finite_measure_lineage.apply`는 기존 raw channel들의 정확한 source/grid/time/sample 대응을 확인한다. 같은 시간이라는 이유로 원행을 합치거나 재정렬하지 않는다. loading/unloading 및 반복 변형값은 acquisition 순서로 유지한다. controller용 시간은 기존대로 엄격 증가해야 하며 중복/역행 시간은 오류다. 별도 비동기 보조 이력의 보간/자동 join은 하지 않는다.

새 노드에는 물리 metadata, parent sample refs, 비선형 정의, 수치 audit 및 원 오류를 보존한다. `verify_node`는 정의를 다시 계산해 출력·원값·마스크·시간·identity를 검사한다. JSON 객체 key 순서에 의존하지 않도록 역할 순서를 고정했다. `dependency_trace`는 원 raw cell 의존성만 반환한다. 비선형 관계를 affine 계수로 거짓 표현하지 않으며 새 공분산 전파를 지원하지 않는다.

`NONLINEAR_EXACT`는 기존 selection compiler가 exact raw 의존성을 검증할 때만 허용한다. 원 sample train/holdout 중복 금지, mask, sample/test weight, sample policy, frozen inclusion 검사는 유지한다. raw-row processing source에도 canonical inclusion을 생산하고 보존한다. 과거 저장 노드의 metadata를 임의 보충하거나 과거 결과의 canonical 근거를 재작성하지 않는다. 필요한 근거가 없는 옛 결과는 새 명시 처리 revision에서 다시 생성해야 한다.

## protocol과 후보 예측

`finite_measure_protocol.recipe(channel,axis,lateral=...)`는 version 2, kind `finite_measured`를 만든다. `measured_protocol`은 보존된 stretch/engineering/log strain 채널의 정확한 시간·방향·단위·완전한 유효성을 확인하고 기존 `material_control.uniaxial_settings`로 변환한다. x/y/z 축은 기존 설정의 물리축을 순열로 대응시킨다. lateral free는 기존 stress-controlled lateral solve이며 fixed 또는 prescribed와 같지 않다. 지원 대상은 기존 Neo 경로다. 기존 소변형 법칙을 이 경로로 확대하지 않는다.

Plan 시험의 `extensions.finite_measure`는 다음 명시 선택이다.

```json
{
  "schema": "caelab.finite-comparison/1",
  "payload": {
    "operation": "PK1_to_finite_Cauchy",
    "scope": "uniaxial_coaxial",
    "axis": "x",
    "frame": "material_cartesian",
    "kinematics": "actual_accepted_candidate_state"
  }
}
```

`finite_measure_prediction.derive`는 원 evaluation을 변경하지 않고 파생 response를 반환한다. 실제 수락 증분의 전체 F/P·시간·원 stress 단위/frame·성분·수락 길이·commit 여부·수렴 근거를 확인한다. 이미 있는 J/Cauchy 진단이 있으면 독립 tensor 계산과 교차 확인한다. response의 `extensions.finite_measure`에는 원 evaluation SHA, 원 native response SHA, 각 accepted increment SHA, 실제 F/J/P를 보존한다. 이 SHA들은 각 입력 대상의 hash이지 서로 다른 범위의 원 job 파일 SHA를 대체하지 않는다. 기존 evidence의 원 job/input/result hash는 유지한다.

`numerical._aligned`에서는 원 성공 상태 확인 뒤 명시 변환을 수행하고 기존 동일 measure/frame/component/unit/지원 시간 관문으로 보낸다. 허용되지 않은 변환은 `EvaluationFailed`이며 optimizer를 성공값으로 속이지 않는다. `_fit_curve`에는 파생 prediction metadata를 원 결과와 분리해 남긴다. candidate table은 기존 prescribed F 열을 유지하고 실제 accepted F/J/P를 별도 열로 제공한다. 정확한 수락 시간에 일치하지 않는 보간 display 행은 실제 F를 만들어내지 않고 `NO_EXACT_ACCEPTED_STATE_AT_DISPLAY_TIME`이다.

`allow_failed_prefix=True`는 보존 실패의 표/곡선 확인에만 사용한다. 원 실패 상태·failed increment·prefix가 파생 metadata와 화면에 남는다. 채점 경로에서는 이 옵션을 사용하지 않는다. 물리 단위 prediction−observation 잔차와 scale/weight가 적용된 objective는 별개다.

## 공유 통합 지점

공유 변경은 `integration.patch`와 `FILE_OWNERSHIP.tsv`의 root-owned 항목이다. Data draft/processing/lineage/selection, Numerical 관측 admission·curve metadata·canonical inclusion, 후보 표 metadata, 기존 Data/Material/Plan Qt 메뉴 및 trial 확장 전달에 한정한다. `material_control.py`, constitutive adapter/native law, optimizer 구현, 저장소·scheduler는 수정하지 않는다.

GUI helper는 기존 owner/session/generation/source/draft token을 확인한 뒤 현재 초안에만 반영한다. 취소는 result_config를 반환하지 않는다. 늦은 현재-target 변경은 적용을 막고 원 target의 재시도 초안을 분리 보존한다. 저장 및 유실응답 receipt/CAS는 기존 host를 사용한다. 새 전체 실패 주입/Windows 실창 검사는 NOT_RUN이며 코드 검토를 실행 증거로 대체하지 않는다.
