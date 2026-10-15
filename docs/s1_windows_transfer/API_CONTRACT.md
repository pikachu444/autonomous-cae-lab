# S1 확정 경계: backend, field, clock, binding, retained result

이 문서는 인도 소스의 실제 API이다. 실행 검증 상태는 ACCEPTANCE_RESULTS.md와 분리한다.
새 엔진/스케줄러/optimizer/store/owner가 아니라 기존 계약에 대한 작은 capability 확장이다.

## 물리 입력과 계산

`caelab.scikit_fem_models.default_settings/validate_settings/describe_inputs/bind_inputs`는
기존 dimensioned AST/thermoelastic reference를 재사용한다. 기존 `get_backend`와
`evaluation.prepare/run/execute_model/read_result`가 adapter를 선택한다. 새 worker는
scikit-fem으로만 P1 조립하고 SciPy SuperLU로만 solve한다. 입력과 worker dependency closure를
실제 바이트로 동결해 저장하고 기존 `_run_process`로 소유 자식 프로세스를 감독한다.
plugins namespace와 thermoelastic 초기화 파일도 원 사본으로 한정하며 실제 import 경로/hash를
`import_identity.json`으로 보존한다. 설치된 다른 제품 경로가 대신 선택되면 계산 전에 실패한다.
`CAELAB_SCIKIT_FEM_WALL_TIMEOUT_SECONDS`는 사용자가 명시하는 양의 wall limit이다.
기존 runtime thread/memory 제한을 보존하고 프로세스 종료/cleanup 상태를 구별한다.

열 약형식은 `∫k_lag∇T·∇v dA=∫qv dA`다. 경계 절대 온도는
`T0_K+gx*x+gy*y`, k_lag는 기존 `k0[1+β(T_previous−Tkref)]`다.
이 단계는 한 번의 lagged solve이며 기존 Evaluation의 Picard/lag 반복이 수렴을 관리한다.
독립 steady solve를 새로운 nonlinear/transient integrator로 부르지 않는다.

구조는 μ=E/[2(1+ν)], λ_ps=Eν/[(1+ν)(1−ν)],
`σ=2μ(ε−αΔT I)+λ_ps tr(ε−αΔT I)I`다. 열 하중은
`∫2(μ+λ_ps)αΔT div(v)dA`, 구조는 기존 3개 강체모드 anchor를 사용한다.
절대 포트에서는 구조가 T−Tref를 한 번 계산한다. difference 포트에서는 전달 시 이미
차감된 ΔT 및 receiver_material Tref provenance를 검사하고 구조가 다시 차감하지 않는다.

실제 함수 공간은 `MeshTri/ElementTriP1/Basis`다. 변위는 vector P1, 응력은 실제 strain과
열변형률로 계산한 element cell-average DG0다. 명시 잔차는
`||A_II*u_I-b_condensed||₂ / ||b_condensed||₂`; 분모 0이면 절대 norm을 기록한다.
Dirichlet만 있는 메시에서는 linear_solve_calls=0을 정확히 기록한다. 공개 예제는 이 경우를
피하고 실제 내부 자유도를 갖는다. Matrix rank warning/nonfinite는 성공으로 넘기지 않는다.

일반 차원식은 기존 안전한 AST만 lowering한다. 조립할 식을 바꾸면 해당 식의 quadrature
값이 바뀐다. 독립 기준식의 L2/H1 norm은 같은 degree-8 quadrature에서 계산한다.
`scikit_fem_forms.gradient`는 공간 기준식의 chain rule이며 설계 adjoint가 아니다.

## P1 field와 엄격한 admission

`p1_temperature_transfer.validate_capture`는 기존 sealed field의 원 필수 메타데이터에
`basis=P1`, `valid_mask=[bool,...]`, `snapshot_kind=steady|physical_snapshot`을 추가로 요구한다.
원 node_ids/coordinates/cell_node_ids/mesh_declaration/mesh_sha256/capture_sha256을 보존한다.
원 grid/topology validator에 넣는 내부 복사본에서만 arbitrary sparse node labels를 index로
정규화한다. 실제 연결을 재생성하거나 Delaunay로 hole을 메우지 않는다.

지원 필드: scalar, node, POINTS, metre/global Cartesian, absolute_temperature,
thermodynamic_temperature, K 또는 명시 absolute degC/°C. dimensionless, wrong measure/frame/
basis/association은 자동 변환하지 않는다. 절대 °C의 변환은 +273.15이고 Δ°C/ΔK에는 offset이
없다. difference field에는 receiver_material의 Tref 값/K/material_sha256이 필요하다.
원 절대온도 0..5000K, grid 상대 1e-12/절대 1e-14 등 reference 기준은 유지한다.

`map_temperature(fields, receiver_settings, options, source_refs=...)`는 실제 삼각형의
barycentric weights로 각 snapshot을 독립 공간 보간한 뒤 시간 가중치를 적용한다.
경계의 1e-14 수준 가중치 roundoff 정리는 명시하며, 남은 음의 weights/미포함 점은 실패한다.
P1 보간은 conservative가 아니다. source mask는 모든 원 절점에서 필요하고 receiver의 모든
절점이 필수다. optional region/nearest/extrapolation/zero fill은 이 capability에 없다.

## 기존 Evaluation transfer row의 추가 정책

기존 `exact_same_mesh` row의 7개 키와 기존 admission은 바꾸지 않는다. 새 정책만
`options` 키를 더한다. 아래는 serializable **입력 예**이며 계산 결과가 아니다.

```json
{
  "id":"TtoU", "from_stage":"Start", "output":"temperature",
  "to_stage":"Structure", "input":"temperature", "mapping":"p1_temperature", "lag":0,
  "options": {
    "time": {
      "mode":"linear",
      "receiver":{"value":1.0,"unit":"s","origin":"public_s1_physical_snapshots"},
      "sources":[{"stage":"Start","output":"temperature"},{"stage":"End","output":"temperature"}],
      "same_steady_state":null
    },
    "required":"all_receiver_nodes", "target_quantity":"absolute_temperature", "target_unit":"K"
  }
}
```

exact는 하나의 물리적 동일 시각, linear는 선언된 2~32개 snapshot에서 receiver를 감싸는
두 끝점을 사용한다. 전 snapshot의 유효성과 엄격한 오름차순을 먼저 확인한다. s/ms/min/h는
원 decimal 표기를 보존해 물리 시각을 비교한다. duplicate, unsorted, origin mismatch,
missing endpoint, missing required snapshot, extrapolation은 실패한다. 자동 sorting은 없다.
`steady_relabel`은 하나의 steady field와 `{declared:true, statement:...}` 선언을 요구한다.
이 경우 clock relabel을 시간 보간과 별도로 기록한다.

컴파일은 port 선언만 검사한다. `evaluation_temperature_mapping.bind_transfer`는 기존
`evaluation_definition.execute` 내부, **receiver dispatched/run_stage 이전**에 호출한다.
각 원 snapshot의 stage/attempt/result/source_response hash와 frozen source ref를 기록한다.
실패 및 성공 모두 기존 attempt의 `transfers/iNNNN-ID.json`을 기록하고 receipt hash를
Evaluation 진행 기록에 남긴다. 다른 store나 queue를 만들지 않는다. mapping 뒤에 취소를
다시 확인하여 validated receipt가 있어도 수신 제출을 막을 수 있다.

## 읽기, 편집, 실행: 같은 owner

기존 `Client.document_open/read/command`의 generation/session/command-ID 규약을 유지한다.
typed GUI 명령은 `pde.update/pde.evaluate`, `simulation.update/simulation.evaluate`,
`evaluation.update/evaluation.run`, `document.save/undo/redo`다. Simulation의 job operation
`simulation.run`과 typed document command `simulation.evaluate`를 혼동하지 않는다.

기존 read API를 재사용한다.

| Python | HTTP / 내용 |
|---|---|
| `Client.evaluation_inspect(document_id)` | `GET /api/workbench/evaluations/{id}/inspect`; draft/ports/clock diagnostics, solve 0 |
| `Client.evaluation_progress(document_id,job_id)` | 기존 evaluation progress; actual attempts/transfers/convergence |
| `Client.evaluation_stage_result(document_id,job_id,attempt_id,selection=...)` | 기존 exact stage result; original input/response/Post refs |
| `Client.evaluation_transfer(document_id,job_id,transfer_id,iteration,start=0,count=256)` | 기존 `POST /api/workbench/evaluation-transfer`; 별도 source_snapshots와 receiver_rows |

새 read 응답은 `source_snapshots[].rows`에 원 ID/좌표/값/mask/clock/단위/refs,
`receiver_rows`에 실제 receiver 좌표/mapped/received/차이/각 snapshot의 barycentric stencil,
`clock`에 source times/receiver instant/weights를 제공한다. 실패에서는 값을 생성하지 않고
None/정확한 오류와 producer refs를 돌려준다. bounded pagination은 전체 source/receiver 중
최대 row 수를 total로 사용하며 빈 page가 된 snapshot은 다른 snapshot 값으로 대체하지 않는다.

reader는 retained payload/receipt/원 input hash를 확인한다. missing/corrupt 결과를 다시
map/solve/repair하지 않는다. compatibility `rows`는 receiver_rows이며 원 공급 행으로
해석하면 안 된다. 원 source는 반드시 source_snapshots에서 읽는다.

CLI는 기존 Client를 호출하는 얇은 경로만 추가했다.

```powershell
caelab documents inspect <document-id> --url http://127.0.0.1:8766
caelab documents stages <document-id> <job-id> --url http://127.0.0.1:8766
caelab documents stage <document-id> <job-id> <attempt-id> --url http://127.0.0.1:8766
caelab documents transfer <document-id> <job-id> --transfer-id TtoU --iteration 0 --start 0 --count 256 --url http://127.0.0.1:8766
```

MCP는 기존 `openscience/workbench_mcp.py` 서버에 `register_transfer_tool(mcp,client)`를
추가하여 `evaluation_transfer_read` 한 개만 등록한다. 전달의 실제 HTTP 함수는 시험했고,
SDK transport는 NOT_RUN이다. 파일이 첨부 closure 밖이므로 별도 MCP 패치 및 확인된
원 Git blob을 제공한다. 전체 파일 적용 검증 상태는 ROOT_INTEGRATION.md를 따른다.

## 저장과 S2 연결 경계

기존 Evaluation/Simulation/PDE owners, ModelSource/descriptor, PreparedEvaluation,
DefinitionFactory, JobManager, read_result, physical_fields.write_field를 사용한다.
Post field set은 온도 K, 변위 m, stress Pa, POINTS/CELLS, frame/measure/basis/physical time을
그대로 보존한다. Post native launcher를 새로 만들지 않는다.

S2는 이 frozen model/field/clock/binding/retained result 경계에서 이어진다. 공유 변수는
기존 DefinitionFactory binding으로 여러 실제 입력에 적용하고 기존 lag/Picard 및 optimizer를
재사용해야 한다. NOT_CONVERGED/실패/취소는 유효 목적값이 아니다. 첫 실제 adjoint와
독립 perturbation/Taylor 검증은 **이번에 구현/실행하지 않았다**. 더 넓은 geometry,
conservative/vector mapping, transient/checkpoint 확대도 원 범위에 계속 남는다.
