# 설계 결정과 남은 범위

## 공유 입력과 실제 MDO

범용 재료 card/geometry framework를 먼저 만들지 않고 기존 advertised numerical input에 대한
명시 identity fan-out을 택했다. 하나의 논리값을 여러 target에 적용하며 모호한 단위 변환이나
서로 다른 값을 가진 두 독립 변수를 수동 복사하는 방식이 아니다. 입력별 물리 검증과 target 충돌은
기존 adapter 검증의 합으로 제한한다. 모든 분야에서 같은 기준온도를 사용해야 한다는 주장은 하지 않는다.

공개 예제에서 k(T)=k0*(1+beta*(T_previous-Tkref))의 Tkref와 구조 무응력 Tref를 동일한 합성 설계
가정으로 명시했다. beta=0.003/K, q=100000 W/m^3, 내부 DOF가 있어 열 쪽 응답도 실제 바뀐다.
구조 입력은 다른 P1 메시의 실제 보간 온도로 계산한다. 이는 **열 자기 Picard loop + one-way 열→구조**다.
구조가 열에 피드백하는 양방향 연성, 시간 적분, conservative projection이 아니다.

saved convergence check의 원 식 L-infinity(new-old) <= absolute + relative*max(max(abs(new)),scale)을
그대로 쓴다. 정상 기본 max12와 abs1e-6/rel1e-8/scale300 K를 변경하지 않았다. 실패 반례만 별도
정의로 max1을 명시하고 원 실패를 보존했다. 후보들은 같은 saved 초기 입력에서 시작하며 a,b,a와b,a
실제 실행으로 원 상태 재현을 확인했다. 선택 DE 후보도 같은 원 saved definition으로 별도 direct
Evaluation 12stage를 실행해 응답/초기 state 해시가 완전히 일치했다.

## 선형과 비선형 경계

첫 선형 adjoint를 원 thermal P1 assembly에 붙였다. 원 primal CSR을 재사용하므로 동일한 FE 행렬,
경계와 실제 quadrature response에 대한 이산 미분이다. 새로운 FE 구현이나 optimizer가 아니다.
분리된 작은 worker는 원 captured-source supervisor를 사용한다. 부모에 별도 비동기 solver/store를
만들지 않고 같은 Job/취소/retention 경계로 실행한다.

정상선형범위 밖 nonlinear total adjoint, coupled transfer derivative, geometry/mesh, transient,
vector response/reduction의 확장, 종속 변수 자동미분은 열려 있다. 이 범위들은 DE를 막지 않고,
첫 scalar adjoint 성공으로 B6나 전체 MDO/adjoint 완료를 표시하지 않는다. field 보간은 기존 scalar
P1 interpolation이며 보존적이라고 부르지 않는다.

## 수치 검증 및 예산 호환성

검사 한계는 첫 실제 FE 전에 contract code에 두었다. 첫 captured worker에도 동일한 기준 상수가
포함된다. 초기 threshold 문서 hash 로그와 현재 문서 hash는 별도로 보존한다. 문서의 재작성/설명 차이를
동일 바이트라고 주장하지 않는다. primal/adjoint 잔차, 중앙차분, Taylor h/order/floor 값은 낮추거나
결과를 보고 완화하지 않았다. 첫 캡처와 최종 코드의 실제 상수 대조 기록을 evidence에 제공한다.

기존 Evaluation의 완성 후보 1회 예산은 구형 단일 binding 경로에서 유지했다. 새 fan-out/명시 adjoint는
기존 _Budget을 공유하며 실제 native stage와 adjoint dispatch마다 1회 charge한다. 비용 종류와 후보 수를
별도로 보존한다. 독립 perturbation 또한 같은 budget을 사용한다. 같은 solver callback 점만 계산 내
cache로 재사용하며, 다른 후보 결과/수렴장을 물려주거나 새 hidden budget을 만들지 않는다.

취소가 접수되면 mapping 뒤 receiver 제출, primal 뒤 adjoint 제출, optimizer 뒤 다음 trial을 각각
체크한다. late result는 증거로만 보존하고 usable responses/gradients를 없앤다. 기존 owned supervisor가
정확한 process group/Windows Job을 정리한다. UI 창을 이름으로 찾아 종료하는 코드는 추가하지 않았다.
실제 테스트에서 after-primal/during-adjoint/after-adjoint 및 HTTP 실제 PID 관측 후 취소를 확인했다.
외부 도구가 강제로 끊은 초기 실행의 finally 확인 실패는 별도 원 기록으로 남겼다.

## 사용자 화면 선택

기존 Engineering Qt 표/트리/분할창을 사용하고 구조적 연결은 input tree, 방법/목적/제약은 기존 Plan
worksheet, 결과는 기존 후보 detail와 전달 조사 창으로 배치했다. 새 웹 화면/프레임워크를 만들지 않았다.
원 id와 hash는 기술 상세/숨긴 열에, 의미 있는 이름과 단위는 사용자 영역에 둔다. 모든 dialog 편집은
로컬 draft이고 취소·미완성 셀·원 selection 수명을 보존한다. GUI 독립 검토/실제 한글 렌더와 좁은 창의
focus/selection/Undo·저장 왕복은 Sol/Windows 측 실제 확인이 남아 있다. 이 작성자가 Sol/Astra 역할을
실제로 수행했다고 표시하지 않는다.

## 무료 Windows OSS 근거

공식 scikit-fem12.0.2 배포는 Python>=3.10, OS Independent BSD 패키지이며 NumPy/SciPy를 사용한다.
첨부 wheel의 실제 bytes/CRC/SHA와 manifest를 검사하고 --no-index --no-deps로 설치했다. SciPy1.17의
minimize(method=SLSQP)는 callable jac, bounds, constraints와 결과 multipliers를 제공한다. 원
spsolve에 transpose CSC matrix를 전달하고 use_umfpack=False/COLAMD로 실행한다. API 문서에 있는
finite-difference 옵션을 adjoint라고 바꾸지 않는다.

공식 근거(2026-10-15 확인, 런타임은 아래 고정 버전이며 rolling 문서와 구분):
- https://pypi.org/project/scikit-fem/12.0.2/
- https://scikit-fem.readthedocs.io/en/latest/api.html (Basis, BilinearForm, LinearForm, condense API 대조)
- https://docs.scipy.org/doc/scipy-1.17.0/reference/optimize.minimize-slsqp.html
- https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.sparse.linalg.spsolve.html

실제 환경은 Linux/Python3.13.5/NumPy2.3.5/SciPy1.17.0/scikit-fem12.0.2다. 본 S2 Windows,
Qt 런타임, ParaView 실제 표시, MCP stdio 실행, 독립 Astra 검토는 NOT_RUN이다. 사용자가 전달한
기존 S1 Windows 성공을 S2 실행 증거로 재활용하지 않는다. 공학적 적합성/실제재료/강도/장비 기준은
UNKNOWN이며 release 판정은 없다.

## 실제 관측된 읽기 비용

MDO 120개 stage의 exact cold 읽기는 원 90초 프로세스 한계를 넘었다. 원 TIMEOUT을 보존했다.
같은 원 결과를 새 프로세스에서 explicit 400초 한계로 **읽기만** 재시도했고 약188.53초에 성공했다.
물리 기준/계산을 바꾸지 않았다. reader가 각 선택에서 원 전체 artifact를 반복 검증하는 비용은 남아 있다.
이 성능 제한을 숨기거나 bounded metadata 조회를 검증되지 않은 VERIFIED로 바꾸지 않았다.
