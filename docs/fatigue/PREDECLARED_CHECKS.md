# 실행 전 고정한 비교 기준 — 2026-10-15

요청 PRO-FATIGUE-COMPLETION-20261015-01. 아래 값/허용치는 첫 새 테스트 실행 전에 작성했다.
관측 결과에 맞춰 범위나 허용치를 넓히지 않는다. 구현 오류 수정과 실패 기록은 별도 보존한다.

* 합성 cyclic 계수: E=200000 MPa, sigma_f'=1000 MPa, epsilon_f'=0.5 [1], b=-0.1, c=-0.5.
  교정 Nf 범위 1..1e9 cycles, total strain amplitude 1e-6..1 [1], SWT sigma_max 1e-6..20000 MPa,
  온도 293..294 K, 평가 293.15 K. 출처/실패 정의/상태는 SYNTHETIC, 실재 재료가 아니다.
* 독립 forward 식에서 Nf=10,1000,1000000 cycles를 생성. 역산 Nf 상대오차 <=2e-9;
  solver 기본 log bracket 상대폭 <=1e-10 및 RHS 상대잔차 <=1e-10을 동시에 요구.
  Pa/MPa 및 strain 1/% 변환 후 비교 상대오차 <=2e-12.
* 중첩 이력 epsilon=[0,4,1,2,3,4,5,0] (단위 배율은 테스트별 명시),
  sigma=[10,20,30,400,900,50,60,10]. reversal pair (1,2)로 생긴 full cycle은
  return rows 3,4,5를 포함하고 sigma_max=900 at source index4. closure index5,
  closing trigger index6. outer half branch는 내부 rows2,3,4를 재소비하지 않는다.
* 순수전단: epsilon_xy=a*sin(t), normal n=(1,1,0)/sqrt(2)에서 epsilon_n=a*sin(t).
  engineering gamma=2*epsilon_xy 입력과 tensor 입력은 상대오차 <=2e-12.
* 면 선정 반례: diagonal strain amplitudes xx=.01, yy=.006, zz=0; constant tensile
  stresses xx=100, yy=400, zz=0. 최대 strain 면 x, x의 P_SWT=1 MPa,
  y의 P_SWT=2.4 MPa. 두 선정 기준을 같은 모델로 표시하지 않는다.
* 동시 tensor와 검색 basis를 같은 직교 회전 R로 변환한 대응 결과의 range/SWT/damage
  상대오차 <=2e-9, 면 법선 abs(dot(n_rotated,R*n)) >=1-1e-12.
  비례 및 90도 위상차 비비례 합성 이력은 직접 n^T T n 수치와 <=2e-12 비교.
* angular convergence는 tensor epsilon=a(t)*u*u^T, u가 격자에서 벗어난 방향인 경우
  p=3,6,12 중 세분된 격자 최대 range가 감소하지 않고 exact 2*a와 오차가 감소함을 검사.
  이는 유한 격자 검사이며 전역 수렴의 증명은 아니다.
* 반복성 반례: scalar strain의 동일 range/mean half pair라도 그 sigma_max가 다르면
  finite history damage는 남고 repeat life는 UNKNOWN. strain/stress 다른 tensor 성분의
  시작/끝 불일치도 repeat life 차단. 시간/위치/성분 누락은 자동 수리하지 않는다.
* FC06은 실제 기존 Data import와 Simulation damage.rainflow job을 사용한다.
  원 CSV와 원 작업 input/job 경로를 없앤 복사본을 별도 Python process에서 읽고 동일 result
  hash/plane/cycle/원행 선택을 확인한다. cold job 생성0; solver/provider 호출0.
* Windows Qt 실행은 이 환경에서 NOT_RUN. PySide6 미설치 시 Qt 테스트 skip을 PASS로 세지 않는다.

## 추가 경계 검사의 실행 전 조건

기존 허용치/교정 범위를 바꾸지 않고 다음 검사를 추가한다. 단축 NONE에서는 shear 선언 미확인이
정상 성분 계산을 막지 않는다. 잘못된 quantity, 한국어 미확인 기준계·위치, 중복 sample ID는 거절한다.
N=1000에서 생성한 진폭 a의 `[a,-a,a,-2a,a]` 이력과 εa 상한 1.25a에서는 알려진 작은 cycle의
D=0.001만 부분값으로 남고 전체 D/반복 수명은 미정이어야 한다. 기존 2e-9 상대 허용치를 사용한다.
실제 기존 JobManager에서 두 면 완료 직후 취소를 요청하고 완료 면 두 개/원 결과를 보존한다.
기존 owner의 최종 저장 pointer 쓰기 실패를 주입하면 이전 pointer·결과와 현재 미저장 초안은 보존되며,
명시 재저장 후 읽기가 가능해야 한다. 이 결함 주입은 외부 solver/runtime을 사용하지 않는다.

추가 부분 실패 주입: 세 번째 면의 cycle-association에서 ValueError를 주입하면 완료한 두 면을
보존하되 실행 상태 FAILED, 전체 critical/damage 미정으로 반환한다. 성공으로 교정하지 않는다.

Residual σmax 대응은 단위 크기에 무관한 상대 1e-12로만 허용하고 절대 바닥값을 두지 않는다.
E=200 MPa, σf′=1 MPa로 응력 척도만 축소한 합성 계수에서 εa=.01,
동시 residual peak 0.1 및 0.1000000005 MPa는 다른 peak로 거절해야 한다.
이는 교정/비교 허용치 확대가 아니라 반복 대응의 절대 tolerance 제거 검사다.
