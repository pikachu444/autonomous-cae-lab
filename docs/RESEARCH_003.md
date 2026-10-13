# 구성식·차원식·전달값 연구

## 현재 인도 범위

이 소스는 기존 Material/PDE/Evaluation 소유자와 JobManager를 확장한다.
새 문서/결과 저장소나 실행 대기열은 추가하지 않는다. 빌드 허용 기록만 문서 저장소 밖의 기존 사용자 설정 경로에 둔다. 작성 환경의 Python/Qt/native 실행은 **NOT_RUN**이다.
아래 실행 가능한 검사를 제출하며 Windows/WSL 실제 결과는 Codex 통합 기록으로 별도 남긴다.
읽기 전용 동료 검토는 기존 계약 조사이며 이 코드의 실행 통과를 의미하지 않는다.

| 작업 | 이번 코드 | 남은 범위 |
|---|---|---|
| FN-08-01 | 실제 증분·응력·정확한 접선 pair·초기/trial/committed 기록 읽기. FELUPE에서 명시적 독립 ±F 섭동을 새 Material 계산으로 실행. 저장 결과 재열기 | 생산자가 남기지 않은 잔차·substep·탄성 내부 상태는 없음. 미완료 native 적분의 일반 부분 상태 reader는 미지원 |
| FN-08-02 | 사용자 원문 등록/편집, native 원문 검토·버전별 로컬 빌드 허용, 명시 빌드 또는 빌드+평가. 실제 MGIS descriptor와 library/source/runtime 보존. generic 3차원 미소변형 Kelvin6 | 다른 pair/finite strain 사용자 법칙, FE interface export·FE solver 삽입, 과거 binary 직접 재사용은 미지원. generic library를 FE 지원으로 표시하지 않음 |
| FN-18-01 | 기존 영역/BC/결과 도구 재사용, 새 식의 오류 위치, 실제 장과 메시별 norm 표/그래프, 같은 Post/Numerical 진입 | 옛 adapter의 위치 없는 오류를 전부 새 parser로 교체하지 않음. 기존 adapter의 norm 표는 생산자별 추가 projection 필요 |
| FN-18-02 | 독립 차원 ODE(initial/time/state별단위)와 스칼라 선형 체적 약형식, 실제 SciPy/FEniCSx 실행 | 임의 mixed/vector/nonlinear/transient 약형식, 사용자 공간/비직사각형/경계적분 DSL, DAE/events 미지원 |
| FN-19-01 | 기존 계산 절차 창/owner/run/Plan 유지. 읽기용 새 창이 같은 frozen job을 사용 | Evaluation GUI 연결 한 곳은 해당 파일 소유자인 Codex가 아래 hook으로 통합 |
| FN-19-02 | 실제 공급 response와 수신 settings의 bound field를 exact mesh/node/time/unit로 대조. 구조 소유 Tref 별도 표시 | 다른 mesh projection, 단위 변환, 임의 mask 매핑은 미지원 |
| FN-19-03 | 같은 결과의 실패 단계·전달·반복 잔차를 읽고 기존 성공 prefix 재사용 경로 유지 | 반복 중간 checkpoint 재개는 미지원. 새 job을 resume로 부르지 않음 |

이 표는 D7 전체 수용 완료 선언이 아니다. 새 adapter의 실제 실행 및 GUI 수용은 제출 코드와 구분한다.

## 재료점 상태와 접선

1. Material에서 재료와 변형 이력을 편집하고 **입력 적용 → 계산 실행**한다.
2. 계산 하나를 선택해 **도구 → 구성식 증분…**을 연다. Native Material에서는 **구성식 → 구성식 증분…**이다.
3. 증분을 선택하고 접선 행/열 성분을 고른다. 표와 곡선은 같은 성분을 읽는다.
4. FELUPE의 **독립 섭동 계산…**에서 F 성분과 h 목록을 지정한다. 확인하면 선택한 frozen 입력의 새 Material 문서와 새 작업을 만든다. 원래 문서와 미적용 편집은 바꾸지 않는다.
5. 새 계산을 저장한 뒤 같은 문서를 다시 열면 접선과 ±섭동 원값을 읽을 수 있다. 읽기 자체는 계산하지 않는다.

FELUPE 선형 탄성은 dσ/dF, Neo-Hooke는 dP/dF이다. 비대각 F 성분 하나를 바꾸며 대칭 변형률을 몰래 가정하지 않는다.
MFront 탄성/Maxwell은 Kelvin6 dσK/dεK, SVK는 실제 native 순서의 PK1/F 9×9이다.
Native FD는 이미 보존된 독립 초기 상태/두 부호를 읽는다. 없는 committed/residual/substep은 trial이나 상태코드로 대신하지 않는다.

## 사용자 MFront 법칙

**새 구성식 → 사용자 MFront 법칙**에서 시작한다. **법칙 원문…**은 UTF-8 .mfront/.txt를 읽고 편집한다.
취소하면 초안이 변하지 않는다. 적용/저장은 소스 컴파일이나 라이브러리 로드를 하지 않는다.
물성/외부 변수의 실제 native 이름과 숫자 단위, 초기 내부 상태, 물리 텐서 변형률
xx yy zz xy xz yz 및 시간 s를 지정한다.

- **빌드만**: 새 owned 작업에서 컴파일하고 actual descriptor를 읽는다. 적분/응력 결과는 없다.
- **빌드하고 평가**: 해당 원문을 새 작업에서 다시 컴파일한 뒤 이력을 적분한다. 숨은 과거 binary 교체나 재사용은 없다.
- **빌드만 실행 / 빌드하고 평가**를 누르면 원문 검토 창이 열린다. **이 버전 빌드**로 확인한 원문만 로컬 운영자 권한 파일에 등록되고 기존 Material 작업을 시작한다. 취소는 초안과 권한을 바꾸지 않는다. 해시 복사나 JSON/CLI 편집은 사용자 절차가 아니다.
- Windows Qt는 같은 사용자의 Windows 권한 폴더 또는 WSL 배포판의 `wsl.localhost` 공유 폴더를 확인한다. 자동 확인이 안 되면 native 폴더 선택기로 현재 서비스의 권한 폴더를 선택할 수 있다. marker가 다른 폴더에는 쓰지 않는다. OS 권한이 없는 클라이언트는 빌드를 허용할 수 없으며 서비스 운영자가 같은 native 절차로 승인해야 한다.
- 서비스의 읽기 전용 `material-build-context`는 고정 운영자 폴더의 일치 정보만 준다. HTTP/model 요청으로 소스 허용·파일 경로·실행 파일을 지정하는 API는 없다. 소스 수정 후에는 새 버전을 다시 확인해야 한다. 기존 명시적 환경변수 allowlist는 운영자/검사용 호환 경로로만 남긴다.
- 기존 `CAELAB_MFRONT_IMAGE`, 정확한 image SHA 및 Singularity 설정을 재사용한다. Windows Qt는 이 실행 환경이 있는 WSL 서비스에 연결한다.
- 허용 목록은 native C++ 실행에 대한 운영자 권한이다. container 옵션을 임의 소스에 대한 보안 보장으로 해석하지 않는다.
- 각 작업은 input/source/helper/worker, 컴파일 명령과 로그, Makefile/library hash, 실제 MGIS descriptor와 runtime을 보존한다.
- 초기 응력/변형률은 0, 내부 상태는 명시 배열이다. scalar 물성/외부 변수를 actual descriptor와 대조한다.
  입력과 반환 단위는 사용자가 선언한 Pa/1/s이며 MGIS가 물리 차원을 추론했다는 주장은 하지 않는다.
- 현재 FE 내보내기는 지원하지 않는다. 일반 generic .so가 CalculiX/Code_Aster용 카드나 실제 FE 연동이라는 뜻은 아니다.

공개 작은 소스: `examples/research003/ResearchElastic.mfront`.
MFront DSL 문법은 [TFEL 공식 Elasticity 예제](https://github.com/thelfer/tfel/blob/85554f233306548d8c9c4d36af54b715c608b8c7/mfront/tests/behaviours/Elasticity.mfront)를 확인했고,
실행/상태/컴파일 helper는 프로젝트의 기존 native MFront 코드에서 재사용한다.
MGIS enum 및 descriptor API는 [공식 BehaviourDescription binding](https://github.com/thelfer/MFrontGenericInterfaceSupport/blob/master/bindings/python/src/BehaviourDescription.cxx)을 대조했다.
새 solver나 패키지 복제는 추가하지 않는다.

## 차원 ODE와 약형식

PDE **새 모델**에서 다음 중 하나를 선택한다.

### 상태 방정식

기본 예제는 K 단위의 온도 초기값과 s 단위 시간, 1/s 감쇠계수이다.
상태·계수 행을 추가/삭제할 수 있고 각 상태의 단위·초기값·미분식·독립 기준식·절대 허용치를 편집한다.
예: `-rate*(temperature-ambient)`. `temperature+rate`처럼 차원이 맞지 않는 식은 실행을 차단한다.
숫자의 미완성 입력과 오류 식도 저장한다. **입력 검사**는 순수 AST/차원 검사이며 solver를 실행하지 않는다.

명시 평가 후 실제 SciPy 출력 시각/상태/사용자 기준식/차이를 같은 결과 선택에서 읽는다.
출력은 실제 state series이며 가짜 공간 메시를 만들지 않는다.
SciPy RK45/DOP853/Radau/BDF, 개별 atol, 명시 rtol/max_step을 사용한다.
계산은 취소 신호를 RHS마다 확인하고 200000 RHS 호출 한도에서 중단한다.
정규화된 성공 상태나 없는 출력점을 0으로 채우지 않는다.

### 단위가 있는 선형 약형식

스칼라 P1 직사각형, 좌표 m, 선언한 장 단위를 사용한다.
계수 단위는 SI 곱셈/나눗셈/정수 지수로 입력하며 자동 mm→m 변환은 없다.
기본 열 예제의 a는 `k*inner(grad(u),grad(v))`, L은 `q*v`다.
두 식의 차원과 trial/test 선형성을 검사한 다음 명시 실행에서만 UFL/FEniCSx에 전달한다.
현재는 체적 적분과 명시 Dirichlet, 미지정 면의 자연 경계다.

메시 수준을 실제로 각각 계산하고 **연구 → 메시와 오차 비교…**에서 같은 기준식/정의의 norm을 읽는다.
2차원 L2 오차 단위는 장 단위×m이고 H1 준노름은 장 단위다. 이를 응력/온도 자체와 혼동하지 않는다.
기준식은 사용자가 선언한 비교식이며 공학 검증 승인이 아니다.
실제 P1 절점/삼각형/값은 기존 Post 등록과 정확한 study_index 선택을 재사용한다.

## 공급값과 수신값

새 창은 `apps.research.transfer_inspection_window.TransferInspectionWindow`다.
계산 절차의 선택한 document/job에서 호출하며 **현재 편집 중인 정의가 아닌 그 job의 frozen 정의**를 사용한다.
공급 response SHA와 정확한 attempt를 확인하고 수신 결과에 저장된 settings의 bound field를 읽는다.
현재 adapter로 다시 bind하거나 solver를 호출하지 않는다.

같은 절점·좌표·단위·시각·메시일 때만 값/차이를 나란히 표시한다.
수신 계산 실패와 전달값 일치는 동시에 가능하다. 실패 상태를 숨기지 않는다.
기존 SI 열→구조의 모든 P1 절점이 필수이며 원자료에 없는 native mask를 만들어내지 않는다.
Kelvin 절대온도와 구조 Tref를 별도로 읽고 ΔT를 다시 적용하지 않는다.

### Evaluation 소유자 통합 접점

`f77a6d8400bfa9b2031de79c7a32ffb037575879`의 실제 `evaluation_window.py`를 읽었다.
현재 선택은 `self.document['id']`, `self._selected_job`이고 `read_stage_result`는 그대로 둔다.
해당 파일은 Codex 소유이므로 이 branch에서 수정하지 않았다. **전달값 보기…** action의 연결 코드는 다음과 같다.

```python
from .transfer_inspection_window import open_transfer_inspection
window = open_transfer_inspection(
    self.client, self.document['id'], self._selected_job, parent=self)
self._transfer_windows.append(window)  # __init__에서 [] 생성
```

독립 실행도 가능하다. 선택한 기존 job을 읽기만 한다.

```powershell
python -m apps.research.transfer_inspection_window --service http://127.0.0.1:18767 --document-id <계산절차ID> --job-id <보존작업ID>
```

## 작은 공개 실행 경로

기존 서비스와 동일한 Store를 사용한다. 창은 같은 service/document에 연결한다.

```powershell
python -m examples.research003 --service http://127.0.0.1:18767 --case ode
python -m examples.research003 --service http://127.0.0.1:18767 --case ode --run
python -m apps.research.pde_window --service http://127.0.0.1:18767 --document-id <출력된 문서ID>
```

`--case weak --run`, `--case user-build --run`, `--case user-evaluate --run`은 각각 실제 설치된
FEniCSx/MFront를 가진 서비스와 사용자 법칙 source admission이 필요하다.
`--run` 없이는 문서 생성/저장만 한다. 새 source 자동 허용이나 설치를 하지 않는다.

## 변경 경로 검사

Author 실행: **NOT_RUN — 원격 환경 연결 안 됨**. 아래는 제출한 검사 명령이며 PASS 기록이 아니다.

```text
python -m pytest -q tests/test_dimensioned_research.py tests/test_research_constitutive_transfer.py tests/test_user_material.py tests/test_research003_ui.py
```

기본 검사는 실제 SciPy/FELUPE와 기존 real HTTP/owner를 사용한다. 열→구조 solver 경계만 명시적 기존 대역이다.
새 native 경로는 필요한 두 경우만 opt-in한다.

```bash
CAELAB_RUN_DIMENSIONED_WEAK_NATIVE=1 python -m pytest -q tests/test_dimensioned_research.py -k installed
CAELAB_RUN_USER_MFRONT_NATIVE=1 python -m pytest -q tests/test_user_material.py -k installed
```

두 번째 opt-in 검사는 공개 소스 하나만 test-local 허용한다. 제품에서 자동 허용하지 않는다.
기존 solver campaign은 재실행하지 않는다. Qt 검사 종료는 창 close→worker drain→HTTP 서비스 종료 순서를 따른다.

## 구현 선택과 변경 범위

- 기존 unit1 adapter를 완화하지 않고 새 backend 두 개로 실제 차원식을 분리했다.
- 일반 Python eval이나 UFL source 실행 대신 bounded AST를 수치/UFL primitive로 해석한다.
- 사용자 law는 별도 backend로 원래 고정 source/기준 검사를 보존한다.
- 기존 compiler/runtime/process cancellation helper를 재사용하며 정확한 소스 버전 권한은 서비스 사용자의 로컬 파일에만 둔다. native GUI가 OS 파일 접근과 원문 검토를 거쳐 쓰며 HTTP는 허용을 쓰지 못한다.
- 구성식/전달 inspector는 읽기 서비스다. Material/PDE 명시 실행과 저장은 기존 owner명령이다.
- Sol의 SimulationWindow, Codex의 EvaluationWindow/일반 한국어 문서/CURRENT_STATE/.moai는 수정하지 않았다.
- 계획한 범위 대비 추가 공통 파일은 backend 등록, simulation catalogue, Workbench/Client/read routes다.
  추가 권한 파일은 실행 코드 허용을 문서/모델 명령과 분리하기 위한 로컬 operator 설정이다.
  새 공통 schema/store/scheduler 대신 각 adapter의 닫힌 settings와 기존 result artifacts를 사용한다.

### 최신 상속 접점

Simulation 배치는 `876c825d56764b7ffb9f50102cca85b1f4f2b4b7`에서 실제 읽었다. 해당 파일은 변경하지 않았다.
NativeMaterial은 canonical backend/itemData, fields, result selector를 유지한다. 전용 작업명/온도/시험 종류를 한국어로 표시하며
사용자 법칙의 설명 영역은 base가 접은 뒤 명시적으로 표시하고, 실제 입력 이력만 그림으로 그린다.
