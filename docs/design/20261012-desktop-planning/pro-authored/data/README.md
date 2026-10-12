# 합성 fixture와 값의 동일성

이 폴더는 **화면 설계·상태 시제품용 합성 자료**다. 사용자 시험 자료, 기준 저장소의 과거 실행 산출물, 실제 solver/fit/provider 결과가 아니다. `build_visuals.py`가 같은 원자료로 SVG/PNG/layer JSON을 재생성한다. 실제 product adapter를 import하거나 계산하지 않는다.

## Material 두 CSV

| 파일 | 실제 열 순서 | 행 수·시간 | canonical 변환 |
|---|---|---|---|
| tensile_A.csv | time_s, force_N, extension_mm, temperature_C | 301행, 0–50s | s/N/mm 유지, °C+273.15→K |
| tensile_B.csv | extension_um, temperature_K, load_kN, time_ms | 241행, 0–40s | µm×.001→mm, K 유지, kN×1000→N, ms×.001→s |

원시편 geometry는 L0=50mm, A0=20mm²다. `e11=extension_mm/L0`, `F11=1+e11`, `P11=force_N/A0`이며 P11의 단위 N/mm²는 MPa다. 이는 nominal first-Piola 대 engineering strain의 조합이다. Cauchy stress는 필요한 J/현재 면적 정보 없이 만들지 않는다. 시간은 독립 채널이며 strain 정렬로 바꾸지 않는다.

raw CSV에는 quality flag를 넣지 않았다. `material_curves.json`은 화면의 **Data r4 처리 상태**로 A와 B 각각 source index82를 품질 제외한다. 따라서 A는 300/301 train, B는 240/241 holdout이다. 화면의 A0078–A0085는 8개 선택 중 A0082 하나 제외하여7개 usable이다. invalid-time board는 동일 원파일의 특정 시간 셀을 잘못 편집한 별도 draft 상태이며, 정상 raw CSV를 실제로 중복 시간으로 변경하지 않는다.

별도 Qt harness는 **Data r3, quality exclusion 없음**으로 시작하므로 초기 A301/B241이다. 사용자가 quality/Plan inclusion을 편집해 r4 상태로 갈 수 있다. 초기 harness가 gallery의 이미 처리된 r4와 같은 mask라고 주장하지 않는다. `prototype/CSV_INTEGRATION_CHECK.json`의 초기 role counts도 이 차이를 따른다.

표시용 `A-0082`는 source-local index의 짧은 표기다. 시제품의 실제 sample ID는 `A:<SHA256 앞12자>:82`이며 전체 hash와 source index를 함께 보존한다. CSV line 번호는 header를 포함하므로 index82는 line84다. 원파일 bytes가 바뀌면 이전 hash의 mask를 같은 행 위치에 자동 적용하지 않는다.

## 곡선의 생성 의미

곡선은 압축성 neo-Hooke 형태의 **해석적 authoring fixture**에서 만든다. μ=.862MPa, λ_L=12MPa다. λ1=1+e에서 transverse stretch squared t를 양수 구간의 이분법으로 찾는다.

`μ(t−1)+λ_L log(λ1·t)=0`

`J=λ1·t`, `P11=μ(λ1−1/λ1)+λ_L log(J)/λ1`.

이 작은 수식은 합성 그림의 일관성을 위한 것으로 실제 mixed-control product evaluator를 구현하거나 검증하지 않는다. 현재 product prescribed-F의 F22=F33=1을 자유 인장이라고 표시하지 않는다. 실제 traction-free 기능은 미지원/추가 개발로 남는다.

관측에는 deterministic noise를 더했다. quality 유효 표본에서 A의 raw RMSE는 `.05*sqrt(.00184) MPa`, B의 raw RMSE는 `.014MPa`가 되도록 정규화했다. A의 scale=.05MPa, weight1이면 `Σ[(prediction−observation)/(scale*sqrt(n))]²=.00184`다. B는 holdout이며 train objective에 들어가지 않는다. raw RMSE와 dimensionless scaled objective를 같은 값으로 표시하지 않는다.

## 후보 fixture

| 후보 | μ MPa | train objective | 상세·holdout | 의미 |
|---|---:|---:|---|---|
| c017 | .862 | .00184 | RETAINED, holdout RMSE .014MPa | 합성 보존 best 사례 |
| c014 | .901 | .07908 | NOT_RETAINED, NOT_EVALUATED | 같은 해석식으로 합산한 요약을5자리로 반올림; 곡선/holdout을 실제 후보 실행에서 보존했다고 주장하지 않음 |
| c009 | .401 | null | 실패 부분 기록; required response 미완결; holdout 없음 | penalty와 유효 objective를 구별. 부분 기록이 완전한 curve라는 뜻이 아님 |
| c021 | .878 | null | CANCELLED/PARTIAL; holdout 없음 | 취소 전 존재한 부분만 보존 |

λ_L는 모든 후보에서12MPa로 외부 고정되어 있으며 여기서 식별한 값이 아니다. 시제품의 `SIMULATED_RETAINED`, `PARTIAL_FIXTURE_ONLY`, `FAILED_INCOMPLETE_REQUIRED_RESPONSE` 등은 위 표를 더 구체적으로 표시하는 상태다. 선택만으로 새 evaluation이 생기지 않는다. 명시적인 detail operation은 별도 ID/예산의 **모의 sidecar**이며 원래 후보의 missing 상태를 소급 변경하지 않는다.

## Contact fixture

`contact_result_fixture.json`은 geometryr12/meshr6/contact-031 attempt02/result contact-result-031/r1을 고정한다. 실제 contact solver나 사용자 면집합 모델이 아니다.

선택 face184, t=.040s에서 pressure1.42MPa, signed gap−.006mm, penetration=max(0,−gap)=.006mm다. slip 배열은 없어 null/NOT_AVAILABLE로 표시한다. 면 normal이 같은 평면이라는 합성 조건에서 pressure [N/mm²]×area [mm²]를 합산한다.

| face | area mm² | pressure MPa | force N |
|---:|---:|---:|---:|
| 184 | 20 | 1.42 | 28.4 |
| 185 | 40 | .50 | 20.0 |
| 186 | 60 | .30 | 18.0 |
| 187 | 80 | .20 | 16.0 |
| 188 | 80 | .20 | 16.0 |
| 189 | 40 | .34 | 13.6 |
| 합 | 320 | 면적 가중 평균 .35 | **112.0** |

201개 시간점의 force curve는 `112*sin(pi*time/.08)^2 N`, 0–.05s이며 .040s 값112N과 표가 같다. field와 legend는 같은 색 변환을 쓴다. 그림의 3D는 편집 가능한 합성 기하 도형이며 native mesh나 engineering shape 수용 증거가 아니다. r13 rebind 상태는 별도 입력이며 r12 결과를 그대로 보존한다.

## Evaluation fixture

`evaluation_fixture.json`은 E-02r5/2 stages/2 transfers/seed293.15K, lag0 heat.temperature→solid.temperature와 lag1 heat.temperature→heat.linearization_temperature를 기록한다. convergence check는 heat.temperature/K, L_INFINITY, absolute1e-6K, relative0, scale1K, maximum12다.

12회 history의 첫 값은 previous output이 없어 `null/N/A`, 마지막은1.4e-5K로 임계값을 넘는다. 이는 NOT_CONVERGED 화면을 검토하기 위해 의도적으로 정체시킨 합성 이력이다. 정상적인 균일 Dirichlet 열 문제의 실제 numerical result라고 주장하지 않는다. 화면의 captured313.150014K 값도 이 UI fixture에 속한다.

별도의 **독립 물리 reference 계획**은 실제 uniform313.15K 열장을 구조로 전달하고 Tref293.15K, α1.2e-5/K, L1m에서 ΔL=.00024m를 확인하는 것이다. 여기서는 실행하지 않았다. 단방향 정상 기준, optional feedback 반복·state 수용, 의도적인 실패 UI fixture를 혼합하지 않는다.

## Gauge와 constitutive fixture

`post_gauge_fixture.json`의 external-A/r3, Gauge01/r2, original_node_id145는 displacement magnitude [mm]를 실제 표기 시간에 연결한다. .020/.030/.040s 값은 .114/.187/.224mm이며 .050s는 invalid gap이다. 연결선을 gap까지 연장하거나 0값으로 만들지 않는다.

`constitutive_fixture.json`은 μ=.85MPa/λ_L12MPa, F11=1/1.01/1.02/1.03, F22=F33=1의 **별도 prescribed-F** 수식 기준이다. 초기 P11=0, increment2의 P11≈.26663875MPa, dP11/dF11≈12.97261483MPa다. stress와 tangent는 같은 P/F pair다. central finite-difference 측정 오차는 실행하지 않아 NOT_RUN이며 임의 norm을 쓰지 않았다.

## 다른 Numerical 화면

DOE/Sobol/UQ/RBF/MOO/batch의 시안 표와 plot은 `build_visuals.py`의 `NUM_CONTENT`, `NUM_CONTEXT`, `precise_numerical_plot`에 편집 가능한 작은 수치 목록으로 들어 있다. MOO의 mass/deflection과 p19 선택, UQ96개 bin count+4failed, RBF disjoint holdout parity와 PREDICTED query, batch b01/failed/missing/ID-conflict를 각각 구별한다. 표본별 원 solver 출력 파일이 존재한다고 주장하지 않는다.

숫자는 실제 물리 threshold·기본 파라미터·과거 benchmark 수정이 아니다. 개발자는 이 합성 fixture와 제품 수치 검증의 reference 입력을 분리해 사용한다. 실제 정합성 검사와 한계는 QA_REPORT.md/VERIFICATION_PLAN.md를 따른다.
