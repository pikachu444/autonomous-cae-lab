# Reference equations, conventions, independent limits

본 문서의 DP·SLS discrete 식과 독립 합성 시편 값은 이번 작성물이다. 참조를 같은 production update 재호출로 생성하지 않는다. 아래 새 DP/FE 한계는 기존 J2/SVK/Maxwell 고정 tolerance를 교체하지 않는다. 실행되지 않은 FE expected는 EXPECTED_NOT_EXECUTION이다.

## 1. DP-LINEAR-KAPPA-DEV/1

3차원 등방 작은 변형, ε=sym(F−I). σ는 인장 양, p=−tr(σ)/3는 압축 양이다. s=dev σ, q=sqrt(3/2 s:s)=sqrt(3J2). f=q−αp−(k0+Hκ)≤0, g=q−βp. κ=∫sqrt(2/3 dep:dep)의 dev 소성변형 등가 누적량이다. E,k0,H는 stress 단위, ν,α,β,κ는 무차원이다. K=E/[3(1−2ν)], G=E/[2(1+ν)].

허용: E,k0>0, −.99≤ν<.495, 0≤β≤α≤1, H≥0; |Kelvin ε|≤.05, 상태 유한·κ≥0이며 κ가 누적 dev plastic strain norm보다 작으면 거절한다. 각도/응집력 또는 Mohr–Coulomb 내·외접 환산은 구현하지 않는다. synthetic seed는 E=210000 MPa, ν=.3, α=.2, β=.05, k0=250 MPa, H=1000 MPa이다. 실측 재료값이 아니다.

### Cone return와 consistent discrete tangent

전 accepted ep0,κ0에서 σtr=C:(ε1−ep0), ftr=qtr−αptr−k0−Hκ0.
ftr≤local tolerance면 elastic이며 yield면 위는 elastic-side/nondifferentiable로 표시한다.
D=3G+αKβ+H, γ=ftr/D, q1=qtr−3Gγ>0인 cone에서는

```
n = (3/2) str/qtr
p1 = ptr + K β γ
s1 = (q1/qtr) str
Δep = γ (n + β I/3)
κ1 = κ0 + γ
σ1 = s1 - p1 I
C_alg = K I⊗I + 2G(q1/qtr) Pdev + (4G² γ/qtr) n⊗n
        - (2G n + Kβ I)⊗(2G n + Kα I)/D
```

이는 반환된 discrete update를 고정 accepted 상태에서 미분한 접선이다. 비연관 β≠α에서 major symmetry를 강제하지 않는다. continuum elastoplastic tangent와 혼용하지 않는다. Kelvin map은 에너지 내적을 보존하고 physical fourth-order tensor로 전개하여 기존 FELUPE single-field assembly에 전달한다.

### Apex

cone의 q1≤local tolerance이면 admissible apex를 검사한다. q=0에서 g의 dev 방향은 subgradient다. dev 소성 증분 norm은 γ와 같지 않을 수 있다.

```
Δκ = qtr/(3G)
κ1 = κ0 + Δκ
p1 = -(k0 + Hκ1)/α
γ  = (p1 - ptr)/(Kβ)
Δep_dev = str/(2G)
Δep_vol = βγ I/3
σ1 = -p1 I
```

αβ=0 또는 γ<Δκ 등 subgradient admissibility 불만족이면 partial trial과 원 accepted 상태를 보존하여 거절한다. qtr>0의 apex 내부 C_alg=(2H/(3α)) I⊗n이다. qtr=0,H>0에서는 고유한 방향미분이 없어 tangent=None, 미분불가다. H=0의 apex 내부는 zero tangent가 정확하다. cone/apex/yield 전환은 smooth 중앙차분 PASS로 숨기지 않는다.

α=β=0은 q−k0−Hκ J2 등방경화 radial return으로 환원된다. 독립 scalar return과 비교하며 원 J2 table/CalculiX 구현을 대체하지 않는다. 저장 에너지는 1/2(ε−ep):C:(ε−ep)+Hκ²/2를 표시하지만 누적 dissipated energy를 새 값으로 꾸미지 않는다.

독립 기준은 공개 `reference_cases.py`의 virgin monotonic proportional loading scalar p–q 해법이다. 긴 nonproportional path·apex를 이 해법으로 검증했다고 주장하지 않으며, apex는 별도 subgradient/재구성/one-sided 검사로 구분한다. 접선 허용치는 abs=2e−10 E, rel=2e−6, h=1e−6/1e−7/1e−8이다. yield tolerance는 2e−14 E+2e−11 max(k0,qtr,|αptr|)다.

## 2. 정확한 FELUPE compressible Neo-Hooke

기존 FELUPE 11.1.3 `NeoHookeCompressible(mu,lmbda)`를 실제 호출한다. 다른 체적 에너지의 ‘Neo-Hooke’ 카드로 전달하지 않는다. 참조 에너지의 상수도 원 출력대로 유지한다.

```
J = det F > 0
ψ = μ tr(FᵀF)/2 - μ ln J + λ(ln J)²/2
P = μF + (λ ln J - μ)F⁻ᵀ
A_iJkL = μ δik δJL + λ F⁻ᵀ_iJ F⁻ᵀ_kL
         + (μ - λ ln J) F⁻ᵀ_iL F⁻ᵀ_kJ
σ = P Fᵀ / J
ψ(I) = 3μ/2
```

PK1/F physical9와 A=dP/dF가 point/FE 양쪽의 기본 pair다. Cauchy는 선언한 변환으로 별도 제공한다. 회전에서 physical9 비대칭 성분을 Kelvin6으로 대체하지 않는다. μ>0, λ+2μ/3>0, principal stretches[.5,2]가 이번 pair 범위다. reference_cases.py는 analytic P/A/Cauchy/energy를 별도로 계산한다. 실제 FELUPE/회전/FE 검사는 환경 부재로 NOT_RUN이다.

원 finite-strain MFront SVK(PK1/DPK1_DF)는 다른 에너지·다른 모델이다. 원 canonical12 scalar-energy oracle 검사를 실행했지만 새 MFront/MGIS 실행 또는 SVK→Neo substitution이 아니다. 새 SVK Windows/FE pair는 작성 범위의 완료 항목에 넣지 않는다.

## 3. Bulk+shear 단일 branch Maxwell/SLS

평형 C0=K0 I⊗I+2G0 Pdev, branch C1=K1 I⊗I+2G1 Pdev, σ=C0ε+q, q=C1(ε−εv), dεv/dt=(ε−εv)/τ. K0,G0,K1,G1,τ 모두 양수이며 각 bulk/shear 계수를 생략하거나 하나의 E/ν로 뭉개지 않는다.

한 증분에서 strain은 물리 시간에 대해 선형 ramp다. accepted ε0,εv0에서 q0=C1(ε0−εv0), Δε=ε1−ε0, x=Δt/τ>0, a=exp(−x), b=(1−a)/x이면

```
q1 = a q0 + b C1 Δε
εv1 = ε1 - C1⁻¹ q1
σ1 = C0 ε1 + q1
C_alg = C0 + b C1
ψ1 = (ε1:C0:ε1 + q1:C1⁻¹:q1)/2
ΔD = ∫[0,Δt] q:C1⁻¹:q / τ dt
ΔW = (ε1+ε0):C0:Δε/2 + b q0:Δε
      + [(1-b)/x] (C1Δε):Δε
```

ΔD는 위 exact exponential path의 양의 quadratic form으로 평가한다. 작은 x에서 expm1/tanh 및 고정 급수를 사용하여 subtractive cancellation을 피한다. backward Euler나 시간 없는 elastic tangent로 바꾸지 않는다. 단일 branch Kelvin6 내부 상태, 누적 work/dissipation 초기값까지 명시 입력으로 보존한다. 초기 dt 없는 점의 tangent/residual은 unavailable이지 0값의 독립 검증 PASS가 아니다.

원 물리 tensor 성분 strain/viscous strain 범위 ±.01, moduli[1e−6,1e9] MPa, τ[1e−6,1e6] s를 유지한다. F=1.01의 float round-trip만 machine epsilon 수준으로 허용하며 물리 tolerance를 완화한 것이 아니다. 실제 time은 0..1e6 s, underflow x=0은 거절한다. 기존 canonical9/refined17, τ=1/.1/5의 원 reference/FIXED_LIMITS로 응력·상태·stored/dissipated energy를 비교했다. original MFront C++/MGIS 실행은 NOT_RUN이다. 새로운 비영 초기 viscous strain은 동일 방정식의 명시 상태 입력이며 새 branch/family가 아니다.

## 4. FE 수치·의미 경계

새 공간 solver를 만들지 않고 기존 FELUPE Hex8 full integration/global Newton/sparse solve를 사용한다. DP/SLS는 선언된 작은 변형 모델이고 P/F 유한변형 모델로 주장하지 않는다. FE residual에서 사용하는 small-strain stress와 dσ/dF의 sym map은 reference-gradient 약형에 일관되게 전달한다. Neo만 정확 PK1/dP_dF를 사용한다.

원소당 8적분점, 모든 실제 IP의 stress/F를 같은 point path에 비교한다. DP stress abs2e−7 MPa+rel2e−6, Neo abs1e−8+rel1e−6, SLS abs1e−10+rel1e−8, F abs2e−9; 반력 평형 relative2e−8이다. native relative Newton tolerance1e−12와 실제 final free-DOF force norm N은 구별한다. stress pair PASS, 실제 FE equilibrium PASS, 원 library의 수렴/단순 exit0는 별도 체크다. native global energy는 없으며 constitutive IP energy라고 표시한다.

## 5. 출처·버전 고정

아래 공식 원소스의 API/식 대조는 실행 증거가 아니다. 외부 코드를 이 인도본에 복사·번들하지 않았다. 사용자 첨부 packet의 공식 참고도 그대로 `request/`에 보존한다.

- FELUPE 11.1.3 Neo-Hooke 원소스: https://github.com/adtzlr/felupe/blob/v11.1.3/src/felupe/constitution/hyperelasticity/_neo_hooke_compressible.py
- 실제 Newton residual/callback 계약: https://github.com/adtzlr/felupe/blob/v11.1.3/src/felupe/tools/_newton.py
- Constitutive gradient/hessian와 state ABI: https://github.com/adtzlr/felupe/blob/v11.1.3/src/felupe/mechanics/_solidbody.py
- 기존 조립기(단일 field에서 비대칭 C를 임의 대칭화하지 않음): https://github.com/adtzlr/felupe/blob/v11.1.3/src/felupe/assembly/_integral.py
- Native mesh 원소 순서/API 참고(실제 설치판 확인은 NOT_RUN): https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/FEM_Mesh.md
- 기존 reference 경로: plugins/material_point/viscoelastic_reference.py, plugins/hyperelastic/reference.py, examples/material-tests/ns1/j2_example.tsv. 이들의 원식·기준은 변경하지 않았다.
