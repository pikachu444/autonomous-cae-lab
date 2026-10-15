# 공유 입력 MDO와 선형 adjoint

통합 후 별도로 수행한 첫 선형 경로의 실제 실행·원 실패·새 프로세스 재열기와 후속 표시 확인은 [Windows 확인 기록](WINDOWS_ACCEPTANCE_KO.md)에 있다. Pro의 Linux 수치 기록, Windows 선형 수치 실행, 계산 없는 reader·Qt 반례 확인은 서로 구별한다.

## 이번 인도에서 사용하는 흐름

기존 Evaluation에서 저장된 열·구조 입력을 선택하고 **변수 → 공유 입력**에서 같은 값으로
묶을 실제 입력을 트리에서 선택한다. 사용자 이름과 물리 단위, 초기값, 선택적 범위를 입력한다.
기술 식별자는 별도로 유지된다. 잘못된 문자열도 초안으로 남길 수 있지만 실행 점검을 통과해야
계산된다. 대화상자 취소는 원 초안을 바꾸지 않는다. 단계·대상·범위의 작성/점검/저장에는 solve가 없다.

Evaluation을 저장한 다음 기존 Numerical Plan을 연다. **변수/목적/제약 → 방법 → 예산 → 실행**을
사용한다. 온도 의존 열전도와 열구조 반복 후보는 **차분 진화**를 선택한다. 단일 정상 선형
열전도의 평균온도 적분 응답에는 **선형 adjoint SLSQP**를 선택할 수 있다. **미분 지원 확인**은
현재 저장 원본과 변수·응답·경계조건을 검사하지만 계산하지 않는다. 비선형/연성/이산/종속 변수나
미지원 reduction에는 이유를 표시하고 이 방법만 막는다. 차분 진화로 돌아가면 기존 기능은 유지된다.

후보를 선택하면 분야별 실제 입력·장·반복 잔차를 읽는다. **미분과 공유 입력**에는 물리 미분값/단위,
목적과 제약의 좌표·scale 적용, primal/adjoint 잔차, 실제 transpose 호출, 독립 Taylor 표/그래프를
표시한다. **전달값 보기**는 기존 전달 조사 창에서 해당 후보·반복의 원 공급/수신 좌표·온도·마스크·시간을
읽는다. 다른 후보 선택은 이미 열린 조사 창의 원 대상을 바꾸지 않는다. **선택 결과를 Post에서 열기**는
원 보존 필드 등록을 재사용한다. 저장 후 새 owner에서 읽기는 재계산/보간/미분을 실행하지 않는다.

Pro 원 작성 환경에서는 PySide6 설치가 되지 않아 Qt·Windows·ParaView native가 미실행이었다.
이후 Windows에서 첫 선형 adjoint/SLSQP와 새 프로세스 읽기를 확인했고, 별도의 controlled reader를
사용해 미분의 사용 가능/불가 표시를 실제 보통·좁은 Qt 창에서 확인했다. 후자의 확인은 새 FE 계산이나
전체 GUI 사용자 작업의 수용이 아니다. native ParaView와 MCP stdio는 이번 확인에 포함하지 않았다.

## 실행 가능한 공개 예제

S1과 같은 기존 Windows 전용 Python 환경을 사용한다. 설치가 아직 없으면 [Windows 시작 안내](../WINDOWS_QUICKSTART.md)의
명시 설치 명령을 아래와 같이 실행한다.
이 경로는 기존 [설치 스크립트](../../scripts/install-windows.ps1)의 `research-ui`·`spatial` 의존성을 준비한다.
설치에는 인터넷이 필요하며 이번 S2 확인에서 새 설치를 수행한 것은 아니다. 저장소에 없는
`dependencies` wheel 폴더나 runtime의 pip를 전제하지 않는다. 계산 worker는 설치를 수행하지 않는다.

```powershell
# 설치가 필요한 경우에만 사용자가 명시적으로 실행
.\Start-CAE-Lab.cmd -InstallOnly -ResearchUI
```

기존 설치가 준비돼 있으면 저장소 루트에서 다음과 같이 실행한다. 설치 시 RuntimeRoot를 바꿨다면
그 경로의 `venv\Scripts\python.exe`를 지정한다.

```powershell
$caePython = Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\windows-runtime\venv\Scripts\python.exe'
& $caePython -m examples.s2_mdo_adjoint --case adjoint --workspace "S2 결과\선형" --deadline-seconds 180 --cold-deadline-seconds 180
```

비선형 MDO도 같은 공개 예제에 있으며 아래 명령은 Pro의 Linux 실행과 연결된 사용법이다.
이번 Windows 수치 확인에는 이 120-dispatch 경로를 다시 실행하지 않았다.

```powershell
& $caePython -m examples.s2_mdo_adjoint --case mdo --workspace "S2 결과\열구조" --deadline-seconds 600 --cold-deadline-seconds 400
```

기존 workspace를 덮지 말고 실행마다 새 폴더를 지정한다. 공개 예제는 기존 HTTP 서비스,
owner commands, JobManager로 실제 입력을 저장하고 Check 계산 0회, Plan 실행, 결과·Post 등록,
저장과 별도 Python 프로세스의 cold 읽기를 수행한다. 예제의 finally에서 자기 서비스·Job·자식 프로세스를
정리한다. 성공/실패/취소 원 자료를 보존한다. `--deadline-seconds`는 명시적 테스트 벽시간 한계이고
물리 수렴 기준이 아니다. 읽기만 다시 확인할 때는 원 `s2-…json` 기록에 대해 다음 명령을 사용한다.

```powershell
& $caePython -m examples.s2_mdo_adjoint --reopen "S2 결과\선형\s2-adjoint-J실제기록.json"
```

adjoint 예제는 4×4 열전도, k와 q를 두 연속 변수로 사용한다. k의 log 변환, 목적 scale, 평균온도 제약을
실제 jac에 적용한다. 원 함수 호출에는 finite-difference jac를 사용하지 않는다. 명시적으로 선택된 독립
미분 검사의 perturbation만 별도 원점 출발 primal로 실행하며 실제 예산을 사용한다.

MDO 예제는 4×4 열 메시(25절점)와 5×3 구조 메시(24절점), 비영 열원, beta=0.003/K이다. 공유 기준온도는
합성 재료의 전도율 기준과 무응력 기준을 같게 두기로 한 **명시적인 설계 가정**이다. 원래 독립이어야 하는
물성을 자동으로 같게 만드는 일반 법칙이 아니다. 하나의 값이 두 입력에 실제로 전달되는 예제이며,
팬아웃 API는 임의의 여러 advertised 동단위 입력에 재사용할 수 있다.

## 예산과 실패 수정

새 공유 fan-out 정의 또는 adjoint 방법은 기존 `max_evaluations` 예산을 실제 분야/adjoint 제출마다
1회 차감한다. 한 후보가 6 Picard ×2분야이면 12회다. 독립 perturbation도 같은 예산을 공유한다.
실패한 제출도 이미 차감된 비용이며 잘못된 전달을 발견해 receiver를 제출하지 않으면 receiver 비용은 0이다.
기존 단일-target 정의는 기존 **완성 Evaluation 1회** 예산 의미를 유지한다. 결과 timing에 budget_unit과
primal/adjoint/verification 역할별 수를 명시하여 서로 혼동하지 않는다.

NOT_CONVERGED/불법 입력/필수 전달 실패/취소/예산 초과는 정상 목적·제약·gradient를 만들지 않는다.
독립 gradient 검사 실패/중단 때도 해당 후보를 best/rank에 올리지 않는다. 원 primal와 미분 raw attempt는
지우지 않고 남긴다. beta를 임의로 0으로 바꾸거나 수렴 한계를 늘려 통과시키지 않는다. 수정은 원 초안에서
명시적으로 한 뒤 새 작업으로 실행한다. 비선형 반복의 일부 수렴장을 다음 후보 seed로 물려주거나
partial-loop prefix로 재사용하는 작업은 계속 차단한다.

보존된 adjoint 자체가 성공했어도 후보나 부모 최적화가 실패·취소됐거나 독립 검사가 실패·미완료이면
미분 표시는 최적화에 사용할 수 없는 값으로 구분한다. 원 값·단위·원 실행 상태는 기술 상세에 그대로
남는다. 원 adjoint를 따로 열어도 부모의 사용 불가 판정을 지우지 않는다.

## 동일 API와 국소 검사

GUI, Python Client, HTTP는 같은 `evaluation.update/run`, `numerical.update/run`과 저장된 정의 참조를 쓴다.
CLI는 기존 `caelab documents apply`로 같은 owner 명령을 실행하고 새 `documents candidate` 읽기로
원 후보/분야/adjoint/전달을 선택한다. `API_CONTRACT.md`에 정확한 선택 예가 있다. 기존 MCP의 동일
Client 호출을 사용하는 도구는 새 payload를 그대로 전달하며 별도 실행체계를 만들지 않는다. MCP 런타임은
Pro packet에는 server source 전체가 없어 미실행이었고, 후속 Windows 확인에서도 MCP stdio는 실행하지 않았다.

```powershell
& $caePython -m pytest -q tests/test_s2_shared_admission.py tests/test_s2_gui_data.py
& $caePython -m pytest -q tests/test_s2_actual_fe.py
```

위 명령은 pytest가 준비된 개발 환경용이며 제품 사용을 위한 추가 설치 요구가 아니다.
actual FE 검사는 작은 실제 모델만 실행한다. `S2_EVIDENCE_ROOT`를 새 폴더로 지정하면 원 raw 검사 자료를
보존한다. GUI 테스트는 Qt가 없으면 명시 skip하며 Windows focus/selection을 증명하지 않는다.
분야 반복/미분의 넓은 실제 제품 qualification, nonlinear total adjoint, shape/mesh/transient/coupled
gradients와 나머지 B6/MDO 범위는 미완료다. 본 합성 수치 통과는 재료·장비·제품 release가 아니다.
