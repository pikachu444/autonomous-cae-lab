# 혼합 변수로 계산하고 선택한 입력을 다시 쓰기

대상: 기존 Numerical Request Plan의 DOE·DE 최적화. 정수·명시 이산값·문자열 선택·고정값·단위 있는 종속값을 지원한다. 기존 연속 Plan은 kind/mode를 생략한 채 사용한다. 이번 묶음은 편집창 교체나 FN-20-01 전체 화면 완성본이 아니다.

## 실행해 보기

현재 제품의 Python 환경에서 저장소 루트를 작업 폴더로 사용한다. 출력 경로는 **아직 없는 새 폴더**를 지정한다. 기존 결과를 덮어쓰지 않는다.

```text
python examples/numerical_mixed_domains.py --output mixed-ode
python examples/numerical_mixed_domains.py --output mixed-search --optimize
python examples/numerical_mixed_domains.py --output mixed-owner --owner-cold
```

첫 실행은 count 1·2·3, 냉각 계수 0.1·0.2 /s, 네 적분 방법의 24개 조합을 실제 기존 ODE 어댑터로 계산한다. 두 번째는 기존 SciPy DE가 count·계수·두 적분 방법을 탐색한다. 세 번째는 실제 PDE 문서와 Request Plan, JobManager로 계산 → 후보 미리보기 → 명시 채택 → 저장 → 폴더 이동 → 새 Python 프로세스에서 재열기·수정·재저장 → 세 번째 프로세스에서 수정 저장값 확인을 수행한다.

ODE는 초기 온도 300 K, 주변 온도 290 K,
`sink_rate = count * base_rate`, `dT/dt = -sink_rate*(T-ambient)`이다.
독립 기준은 `290 + 10*exp(-sink_rate*t)`이다. 적분 방법은 **수치 설정**이지 물리 재료 종류가 아니다. 실행기가 solver 문자열과 원 숫자를 실제 `pde/input.json`에서 다시 읽는다. 잘못된 enum이나 정수 1.5는 모델로 전달되지 않는다.

기준 비교는 0~2 s의 21개 시각에서 수행한다. rtol=1e-8, atol=1e-9 K, max_step=0.005 s를 명시한다. 각 점의 오차를 `atol + rtol*abs(기준해)`와 비교한다. 이는 이 예제의 실측 기준 대조이며, 임의 ODE의 전역 오차 보증이나 공학 승인이 아니다. 독립 `solve_ivp` 대조는 검사에서만 호출한다. 제품은 기존 accepted-step 적분기를 유지해 취소와 부분 결과를 보존한다.

## Plan에 넣는 값

실행 가능한 선언 전체는 `examples/numerical_mixed_domains.py`의 `declarations()`에 있다. 명시 후보에는 **자유 변수만** 적는다.

```python
from examples.numerical_mixed_domains import declarations
variables = declarations(('RK45', 'DOP853'))
candidates = [{'candidate_id': 'Cchosen', 'values': {
    'count': 3, 'base_rate': 0.2, 'solver-method': 'DOP853'}}]
```

`sink_rate`와 고정 `ambient`를 후보에 다시 넣으면 거절된다. 종속식은 기존 안전한 단위 AST로 입력 준비 시 계산하며, 자유 탐색 축으로 추가하지 않는다. 원 선언과 순서, 선택지의 ID·표시명·실제 값, 자유값, 계산된 전체값, 실제 모델 입력과 응답은 함께 보존한다. Python float에서 `3*0.2`가 `0.6000000000000001`인 값도 그대로 남긴다. 채택 시 보기 좋은 값으로 반올림하지 않는다.

범주는 실제 광고된 유한 입력에서만 선택한다. 임의 settings_path, Python 식의 attribute/subscript, 파일 접근은 지원하지 않는다. 단위는 기존 SI 차원 체계를 사용하며 접두어·섭씨 오프셋을 자동 환산하지 않는다. 기존 연속값의 단위 라벨은 그대로 유지한다.

## 결과 사용

미리보기는 원 저장 모델에 보존된 전체 할당을 검증해 보여준다. 채택은 기존 owner의 명시 명령과 generation/원 입력 검사를 거친다. 원 모델을 바꾼 뒤 오래된 후보로 덮어쓰려 하면 차단된다. Evaluation 문서는 기존 경로로 독립 stage 사본을 만들며 원 stage를 바꾸지 않는다.

읽기·미리보기·채택·저장·재열기는 후보 생성, 종속식 평가, solver를 호출하지 않는다. 다만 선언의 문법·단위와 입력 membership, 저장 해시는 검사한다. 기존 결과를 다시 계산하려면 명시적으로 **새 job**을 실행해야 한다. 저장 결과 재열기는 DE 내부 상태 resume가 아니다.

LHS는 유한 축을 선언된 균일 구간으로 샘플링한다. 반복 행을 제거하지 않는다. 명시 DOE의 반복 행도 별도 평가한다. DE는 동일한 전체 실제 입력에 대한 기존 exact cache를 사용한다. `요청 행 수`, `유일 자유 입력 수`, `실제 model_calls`, `dispatch 수`, `cache hit`는 같은 숫자가 아니다. 유한 조합을 모두 방문했다고 물리적으로 모두 가능하거나 최적성이 승인된 것은 아니다.

혼합 변수의 통계·Pareto는 읽을 수 있지만 기존 연속 회귀·RBF·Sobol/UQ·least_squares/fit는 해당 방법만 사용 불가로 표시한다. 다른 방법으로 몰래 바꾸지 않는다. 저장된 과거 결과나 불완전한 초안은 계속 읽고 수정·저장할 수 있다.

## 검사 범위

Linux Python의 실제 SciPy 계산, owner/JobManager, 이동한 저장소의 새 프로세스 읽기·편집·재저장을 확인했다. Material/Simulation typed 채택 검사는 실제 owner와 제어된 evaluator를 사용한 연결 검사이며 FELUPE/FEniCSx 실계산 주장이 아니다. Windows·native Qt 화면·FreeCAD/Gmsh·FELUPE·전체 HTTP 캠페인은 완료로 표시하지 않는다. Sol GUI 연결, 전체 FN-20-01 수용, 반복 MDO·adjoint·mapping·B5.2/B5.4/B5.5/B5.6/B6 잔여는 별도다.
