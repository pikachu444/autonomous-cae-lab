# S2 수치 계약 — 실제 FE 검사 전에 고정

기준 5ee81c544093b6feb78fc874fd09be380d47f223. 첫 S2 solve 이전에 작성한다.
기존 residual 1e-10, uniform displacement 1e-10 m, uniform temperature 1e-8 K,
좌표 rtol1e-12/atol1e-14, S1 affine/constant P1 1e-10 K 및 saved Picard check는 변경하지 않는다.

첫 미분: constant k, steady scalar P1 conduction; all-boundary Dirichlet T0+gx*x+gy*y.
A u=b. J=(integral T dOmega)/area. w_i=(integral phi_i dOmega)/area.
자유 DOF F/구속 DOF C를 보관하고 A_FF^T lambda=w_F를 실제 SciPy SuperLU로 푼다.
k: direct=0, residual=-lambda^T (A/k)[F,:]u.
q: direct=0, residual=lambda^T integral(phi_F).
T0: direct=sum(w_C), residual=-lambda^T A_FC 1.
T0의 K/degC는 절대온도이며 미분은 온도차; offset 미분은 0이다.
beta=0에서 conductivity_reference_temperature 미분은 정확히 0이다.

지원은 thermal.scikit_fem.rectangle, beta=0, lag=None, 내부 DOF 존재, 단일 stage,
전달/반복 없음, mean_temperature의 native_integral reduction이다. Picard total,
구조/연성, 메시/shape, nonsmooth reduction, free beta 및 종속/이산 변수는 adjoint에서
거절한다. 기존 DE와 fixed/dependent/mixed 경로는 유지한다. 이 제외는 후속 요구 완료가 아니다.

독립 검사: 동일 원 stage 설정에서 매번 새 primal. 목적 f=direction*J/scale,
좌표 z는 기존 linear/log encoded bound를 [0,1]로 정규화한다.
중앙 h=1e-5; |g_adj-g_FD| <= 2e-7 + 3e-5*max(|g_adj|,|g_FD|).
독립 방향 p1=(0.8,0.6,...), p2=(-0.6,0.8,...), Taylor h=[0.04,0.02,0.01,0.005].
R0=|f(z+hp)-f(z)|, R1=|f(z+hp)-f(z)-h*g_z.p|.
마지막 두 구간 R0 차수 0.8..1.2, R1 차수 1.7..2.3.
R1 <= 1e-10*(1+|f|)인 경우만 roundoff floor로 별도 판정한다.
공개 비선형-in-k 예제는 양쪽 |g_z.p|>1e-6, 둘 이상 h의 R1이 floor 위여야 한다.
의도적인 sign/scale 오염은 같은 검사에서 실패해야 한다. 결과로 수치를 완화하지 않는다.
primal/adjoint 상대 L2 residual 각각 1e-10, mean contraction 일치 1e-10 K.

공유 입력은 identity fan-out이며 단위 변환 없음. 예제는 thermal k(T) 기준온도와
구조 strain-free 기준온도를 같다고 사용자가 선언한 합성 재료이며 보편 법칙이 아니다.
양쪽 실제 입력에 적용되고 beta>0/q>0/내부 DOF와 구조 Tref 효과를 갖는다.
S1 thermal 자기 lag/Picard와 일방향 열→구조만 사용하며 snapshot은 transient가 아니다.

예산: 기존 max_evaluations를 EvaluationDefinition에서는 stage/adjoint dispatch마다
1회 차감한다. 후보 수와 구별한다. 독립 perturbation도 같은 예산을 공유한다.
기존 SciPy SLSQP에 실제 jac callable을 전달한다. FD jac를 선택하지 않는다.
예약은 제출 전이며 실패 제출도 차감; 실제 worker solve 수와 제출 수는 별도 기록한다.

공개 MDO 사전 입력: k0=40 W/(mK), beta=.003 /K, q=100000 W/m³,
Tboundary=330 K, source mesh4×4/receiver5×3, 공유 Tref 범위285..305 K.
Picard maximum12, absolute1e-6 K/relative1e-8/scale300 K. 기존 식을 그대로 사용한다.
공개 선형 예제: k20/q10000/Tboundary300, k범위10..40(log), q5000..20000(linear).
목적 mean_temperature/10 최소화, mean_temperature<=302 K. 모든 검사는 고정 메시에서 수행한다.
