# 숫자 입력 등록 호환 교정 — C1

요청: PRO-NUMERICAL-MIXED-DOMAINS-20261015-01-C1.
원 혼합 변수 ZIP을 대체하는 전체 배포본이 아니라 그 작성본에 대한 증분이다.

## 달라지는 사용 흐름

모델이 적분 방법 같은 범주 입력도 제공하더라도, 기존 숫자 입력 찾기와 등록을 계속 사용할 수 있다. 실제 소스의 공개 이름은 `Lab.discover_model_parameters`와 `Lab.register_model_parameter`이다. 등록한 숫자 계수는 기존 `plan_model_doe/run_doe` 또는 `plan_model_optimization/run_optimization`으로 사용한다.

숫자 후보 목록에는 숫자 입력만 나온다. 원본 설명에는 **범주를 포함한 전체 입력, 현재 값, 선택지 순서, 단위와 설정 위치**가 그대로 남는다. 모델·입력 식별값도 이 전체 설명에서 만든다. 숫자 후보 목록과 전체 설명을 같은 순번으로 대응시키지 않는다.

`solver-method`를 숫자 registry에 직접 등록하면 적용이나 probe 전에 거절하고 **typed Request Plan** 사용을 안내한다. Plan의 `kind='categorical'`과 모델이 광고한 문자열 선택지를 사용한다. `0/1/2` 같은 코드를 넣거나 임의 설정 경로를 지정하지 않는다. 적분 방법은 물리 계수가 아니라 수치 계산 설정이다.

모델의 적분 방법 또는 선택지 의미가 바뀌면 과거 숫자 등록의 source도 달라진다. 이전 등록을 새 모델로 몰래 재해석하지 않는다. 명시적으로 변경된 모델을 확인하고 새 등록/새 캠페인을 만든다. 저장된 과거 결과는 그대로 읽는다.

## 실행 예제

기존 혼합 변수 구현과 C1을 적용한 저장소의 일반 Python 환경에서 실행한다. 추가 API, 구독, WSL 또는 GUI가 필요하지 않다.

```text
python examples/numerical_mixed_legacy_c1.py --output C:\CAE\checks\mixed-c1-new
```

출력 폴더는 새 경로여야 한다. 기존 결과를 덮지 않는다. Linux에서도 같은 명령의 출력 경로만 바꾸어 실행할 수 있다.

예제는 원 `DimensionedODEAdapter`에 **예제 한정 Lab 메타데이터/결과 포장**을 붙여 명시적으로 한 Lab 인스턴스에 주입한다. 원 adapter는 evaluation 역할이며 이 배포에서 기본 model backend로 등록하지 않았다. 설정 setter, 차원식, 적분기, sampler, registry와 저장 처리는 기존 구현이다. 따라서 예제 성공은 원래 없던 기본 Lab ODE backend의 자동 설치나 GUI 연결 성공을 뜻하지 않는다.

냉각 계수만 바꾼 네 LHS 후보를 실제 ODE로 계산한다. 각 원 입력·계수·적분 방법·시각별 온도와 해석해를 대조한다. `receipt.json`에 실제 호출 수, 원 descriptor, 등록 effect, 결과 식별값을 남기며 `lab/`에 원 입력·계획·실험 결과를 보존한다. 허용 오차는 기존 mixed 예제의 `atol + rtol * abs(reference)`를 그대로 쓴다.

```text
python -m pytest -q tests/test_numerical_mixed_legacy_c1.py
```

전용 검사는 실제 Lab DOE/DE, enum 위치 변경, 잘못된 enum/setter/선언, 오래된 source 거절과 별도 Python 프로세스의 이동된 저장소 읽기를 포함한다. cold 읽기에서는 solver·bind·probe·표본 생성·종속식 계산을 막고 저장소 파일이 그대로인지 확인한다. typed 후보 채택·수정·재저장은 원 mixed owner 검사로 별도 회귀한다.

## 확인 범위

이 C1에서 실제 실행한 환경은 Linux Python 3.13.5 / NumPy 2.3.5 / SciPy 1.17.0이다. Windows, Qt GUI, FELUPE, 전체 HTTP/제품 수용, 최신 working tree 통합, Astra의 C1 독립 검토는 실행하지 않았다. 자세한 검사별 명령·결과·기존 실패는 ZIP의 `validation/status.json`에 있다.

기존 `test_domain_candidate.py`의 C2 선택 후보 근거 누락 4건은 교정 전후 동일하게 실패한다. 이를 숨기거나 기존 관문·기대값을 바꾸지 않았다. 기존 Numerical C2, Data/Portable 처리, GUI와 다른 팀의 코드는 C1 수정 대상이 아니다.

### 현재 Windows 통합 확인

2026-10-15 Codex가 원 혼합 변수 구현과 C1을 현재 main에 통합했다. 기존 처리 표본의
피팅 입력, 후보 증거·저장, 이동 사본과 시험 분석의 공통 연결을 보존했으며 Astra가
충돌 구간의 최종 변경을 원 Pro 작성물과 대조했다. Windows 설치 런타임에서 변수 선언·
기존 숫자 등록·실제 ODE·직렬/배치/프로세스 DE·평가 예산의 관련 79개 검사가 통과했다.
실행은 94.60초였고 해당 Windows Job과 자식 프로세스는 모두 종료했다.
타입별 GUI의 연결과 전체 owner 이동·채택 수용은 이 검사에 포함하지 않았다.
