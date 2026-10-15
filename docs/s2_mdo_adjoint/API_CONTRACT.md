# S2 API와 이산 미분 계약

## 공유 binding — 기존 정의의 하위 호환 확장

구형 `{id,stage,input_id,unit}` 그대로 읽고 실행한다. 새 행은 아래처럼 하나의 논리 값으로 여러 실제
입력을 묶는다. label/bounds는 선택적이고 targets는 1..32개다. 새 행/구형 행을 섞을 수 있지만 동일한
실제 stage/input을 두 번 할당할 수 없다. label은 사용자 이름, id는 안정적인 기술 식별자다.

```json
{"id":"SharedReference","label":"공유 기준온도","unit":"K","value":293.15,"bounds":[285,305],
 "targets":[{"stage":"Heat","input_id":"conductivity_reference_temperature"},
            {"stage":"Structure","input_id":"reference_temperature"}]}
```

각 원 adapter의 describe_inputs/bind_inputs로 실제 입력과 단위, 초기값과 양 끝 범위를 검사한다.
단위명의 유사성으로 변환하지 않는다. 새 fan-out은 연속 물리 입력만 지원한다. 구형 단일 target의
mixed/fixed/dependent 기능은 영향을 받지 않는다. descriptor는 한 행이고 target_descriptors에 각 원
입력의 경로를 따로 제공한다. 첫 target의 settings_path를 논리 변수 전체 경로인 것처럼 노출하지 않는다.

execute는 모든 입력을 deepcopy하고 실제 bound stage 모델로 시작 상태 해시를 만든다. 후보값이 없으면
새 공유 행은 저장된 value를, 구형 행은 원 단계 값을 쓴다. `input_bindings`에는 논리 값/단위/출처와 각
target의 original_value/applied_value/단위/d_target_d_logical=1이 남는다. 각 stage 입력은 기존 retained
stage result settings와 input_sha256으로 읽는다. candidate 간 UUID 결과 폴더와 초기 state는 독립이다.

## 지원 방법과 검증

`numerical.optimize`의 method 기본값은 `differential_evolution`이다. `slsqp_adjoint`를 명시하면
기존 DefinitionFactory 안에서 단일 정상 선형 열전도 지원 조건을 먼저 확인한다.

지원: thermal.scikit_fem.rectangle, beta=0, linearization_temperature=None, 내부 자유 DOF 존재,
정해진 P1 메시·clock, 단일 stage, 전달/반복/reuse 없음. 설계 입력 k, q, 경계 절대온도 T0,
전도율 기준온도(선형 beta=0에서는 미분 0). 응답은 정확한 `mean_temperature`, unit K,
component mean_temperature, location domain, reduction **native_integral**이다.

자유 변수는 연속형 linear/log만 가능하다. fixed 입력은 실제 초기 assignment 후 선형 여부를 다시
검사한다. free beta, 종속/이산/shape/mesh 및 nonsmooth reduction, nonlinear/coupled gradients는
이 방법에서 명시 거절한다. total adjoint가 없는 Picard를 frozen partial로 통과시키지 않는다.

```json
{"method":"slsqp_adjoint","objective":{"response":"mean_temperature","unit":"K",
 "direction":"minimize","scale":10,"reduction":"native_integral"},
 "constraints":[{"response":"mean_temperature","unit":"K","operator":"<=","limit":302,
 "scale":10,"reduction":"native_integral"}],
 "options":{"maxiter":30,"ftol":1e-9,"verify_gradient":true}}
```

나머지 request.inputs는 기존 backend=evaluation.definition, settings.definition_ref, variables,
execution을 사용한다. owner가 정확히 저장된 definition_ref를 compile한다. Check는 solver import/solve를
하지 않는다. backend 이름 guard 삭제나 새로운 우회 numerical.run endpoint는 없다.

## 원 primal와 실제 transpose

S1의 동일 scikit-fem P1/SciPy primal 조립으로 A,b,u 및 F/C DOF를 만들고 그대로 NPZ에 보존한다.
원 quadrature에서 ell_i=integral phi_i, w=ell/area이며 J=w^T u다. 새 adjoint worker는 원 input,
worker_result, system의 hash를 검증하고 **재조립·primal 재계산 없이** A_FF^T lambda=w_F를 푼다.

- k: -lambda^T (A/k)[F,:]u. 원 prescribed DOF를 포함한 u 전체가 쓰인다.
- q: lambda^T ell_F.
- T0: 직접항 sum(w_C)와 경계 residual항 -lambda^T A_FC 1의 합. 두 항을 별도로 저장한다.
- Tkref: beta=0 경로에서 0. 이것만으로 정상 gradient 검사를 대신하지 않는다.

K와 degC는 절대온도 입력에서 offset을 적용하지만 dT/dT0에서는 offset 미분이 0이다. 구조의
alpha*(T-Tref) 및 S1의 K/DeltaT 소유 계약은 변경하지 않는다. 상대 L2 primal/adjoint 잔차는 각각
1e-10 이하, mean contraction 일치는 1e-10 K 이하를 요구한다. source/physical bounds도 그대로다.

worker의 adjoint-system.npz/adjoint.json/result와 parent derivative_attempts를 원 stage와 함께
보존한다. 물리 gradient 단위, 직접항, residual항, mesh/입력/코드, 버전, solve/assembly/FD 호출수,
primal_reference가 포함된다. raw adjoint가 늦게 성공한 뒤 취소됐으면 raw 증거는 남기되 사용할 gradient는
없다. 손상되거나 없는 원 자료를 재계산·재보간해 보충하지 않는다.

## Chain rule와 실제 소비

각 논리 gradient는 연결한 target partial의 합(각 fan-out 미분1)이다. VariableDomains의 기존
linear/log 좌표의 bounds를 z in [0,1]로 정규화한다. dx/dz는 encoded 범위 폭이며 log면 추가로 x를
곱한다. 목표 최소/최대 direction, objective.scale과 constraint.operator/scale을 적용한 실제 jac가
SciPy SLSQP로 전달된다. `objective_gradient`와 `constraint_gradients`에는 물리 미분과 dx/dz,
scale/부호, 실제 소비 벡터, scalar components, 제약의 SciPy inequality 부호를 보존한다.

독립 검사는 fresh primal만 실행하며 base gradient 내부에 FD가 없다. h=1e-5 중앙차분과
h=[.04,.02,.01,.005]의 두 방향 Taylor 원 값·refs·R0/R1·차수를 보존한다. 고정 tolerance는
NUMERICAL_CONTRACT와 linear_adjoint_contract.py를 따른다. 검사 실패/중단은 gradient admission을
무효로 하고 best/rank를 만들지 않는다. 실제 raw 증거와 실패 원인은 남는다.

## 원 결과 선택 — 새로운 store/owner 없이

Python/HTTP의 기존 `numerical_evaluation_result(document_id,job_id,candidate_id,...)`를 사용한다.
`evaluation_index=0, selection={"metadata_only":true}`는 원 composite/gradient 요약을 읽는다.
`attempt_id`는 기존 stage 또는 새 derivative_attempts의 실제 ID를 선택한다. 같은 owner의 verified
retained root로 제한하며 다른 후보/원자료/손상된 경로를 대신 사용하지 않는다.

전달 조사도 같은 reader의 독점 selection으로 읽는다. 수치 보간은 실행하지 않는다.

```python
client.numerical_evaluation_result(plan_id, job_id, candidate_id, evaluation_index=0,
    selection={"transfer": {"id": "TtoU", "iteration": 5, "start": 0, "count": 128}})
```

id를 생략하면 후보의 전달 catalog이다. 실제 P1/동일메시 inspector의 원 마스크, 시간, 원행,
receiver actual input 비교 관문을 그대로 사용한다. transfer query와 stage/다른 selection을 섞으면 거절한다.

```powershell
caelab documents candidate N실제문서 J실제작업 C000000 --evaluation-index 0 --selection selection.json
caelab documents apply N실제문서 --operation numerical.run --session 실제세션 --generation 3 --arguments "{}"
```

console entrypoint는 caelab.cli:main이다. source packet에는 caelab.__main__이 없으므로
`python -m caelab`을 실행 명령으로 쓰지 않는다. 기존 MCP numerical_evaluation_result가 같은 Client
selection을 전달하는 계약은 변하지 않는다. 이번 packet 밖 MCP 서버 등록/stdio 실행은 NOT_RUN이다.
