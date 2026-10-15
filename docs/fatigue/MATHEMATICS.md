# Strain-life · SWT · normal-strain critical plane — 계산 계약 v1

요청 PRO-FATIGUE-COMPLETION-20261015-01. 이 문서는 실제 `caelab/fatigue_{life,tensor,cycles,strain}.py`
구현의 계약이다. 단축 식 [1, 2]과 최대 normal-strain-range 면 기준 [2]을 사용한다.
변동진폭의 원 표본 loop association, half-cycle 처리, 반복 경계 검사는 이번에 작성한 명시적 확장이다.
단축 SWT 논문이 이 counting/association 전체를 정한다고 주장하지 않는다.

## 1. 입력과 지원 모델

`STRAIN_LIFE + NONE`: 지정한 한 정상 방향의 실제 total infinitesimal strain만 요구한다.
응력과 shear 채널은 필수가 아니다. `STRAIN_LIFE + SWT`는 같은 방향·위치·시각의 Cauchy
정상응력도 요구한다. `CP_SWT + SWT`는 stress와 total strain 각각 xx, yy, zz, xy, yz, xz 여섯
독립 성분을 실제로 요구한다. 3×3 배열의 암묵적 해석/자동 대칭화는 지원하지 않는다.
이번 경로는 명시된 6성분 입력 경로다. 비대칭 PK1, finite strain, plastic-only strain은 거절한다.

Data의 원 CSV는 원래의 시간 순서와 원행을 보존한다. 같은 exact retained result의 채널을 선택하고
기존 `_resolve`로 document/job/input revision/input hash/result hash를 읽기 전·후 검증한다.
시간축은 한 개의 실제 `time [s]`, 3개 이상의 유한 표본, 엄격 증가여야 한다. 모든 채널의 시각,
원행, sample identity, 고정 frame/basis, 위치, native exact selector(성분 외 부분), clock 의미가
동일해야 한다. quality/calculation/finite mask, 제외 행, gap, 다중 segment, 비유한 값은 차단한다.
자동 정렬·보간·최근접 위치·성분 0 채움·Poisson 추정·σ/E total strain 생성은 없다.

계산 내부 단위는 stress MPa, strain 1, time s, temperature K다. Pa는 10⁻⁶ 배, %는 10⁻² 배로 변환한다.
공학 전단 γij를 사용한다고 원 measure와 사용자 선택이 일치할 때만 εij=γij/2를 적용한다.
정상 성분은 /2하지 않는다. 이미 tensor strain인 값에 /2를 다시 적용하지 않는다.
원 단위와 각 채널의 변환 배율·원 response hash를 보존한다.

알려진 native model component basis의 `sensor/world alignment UNKNOWN`은 계산 기준계 UNKNOWN과
다르다. 같은 고정 model basis 안의 projection은 허용하면서 외부 정렬은 UNKNOWN으로 남긴다.
`normal_model`은 원 tensor가 선언한 고정 component 기준계 안의 법선 좌표다. 검색기저의 열은
그 기준계에 표시한 검색축이다. 원 descriptor의 basis를 또 곱하거나 임의 principal 회전을 하지 않는다.
외부 센서 좌표와 일치한다는 주장은 없다. 시간 의존/회전/미확인 basis는 차단한다.

## 2. 교정과 양의 root

CMB total-strain 식:

    εa = Δεn / 2 = (σf′ / E) (2 Nf)^b + εf′ (2 Nf)^c

SWT 식:

    P_SWT = σn,max εa
          = (σf′² / E) (2 Nf)^(2b) + σf′ εf′ (2 Nf)^(b+c)

Nf는 cycles, 2Nf는 reversals다. CMB RHS는 무차원, SWT RHS는 MPa다.
E, σf′, εf′는 양수, b,c는 음수인 단조 감소 branch만 이번에 지원한다. root는 명시한
`cycles_min..cycles_max` 안의 log(Nf) 이분법이다. 계수는 완전 양진 축방향 strain-life 교정이며
이미 mean-stress 보정한 계수/monotonic 계수를 cyclic으로 이름만 바꾸어 받지 않는다.
계수의 출처, 시험 조건, 실패 정의, 안정 cyclic 상태, 축방향 시험 기준, 온도, εa 범위와 SWT의
σmax 범위를 요구한다. 기본 재료 계수는 없다. 합성 예제 계수는 명시 예제 동작에서만 불러온다.

실제 root마다 초기/최종 cycles bracket, 반복 횟수, 절대/상대 RHS 잔차, 탄성·소성 항, 목표값,
계산 단위와 허용치를 보존한다. 기본 허용치는 log bracket의 상대폭 1e-10과 상대잔차 1e-10을
동시에 만족해야 한다. 기본 최대 반복은 128이다. 두 조건의 허용 범위는 각각 1e-14..1e-4,
반복 한도는 1..512로 제한한다. 임의 cutoff를 무한 수명으로 바꾸지 않는다.

교정 수명 구간에 root가 없거나, 수렴하지 않거나, 온도/εa/σmax 범위 밖이면 해당 cycle의
Nf와 damage는 UNKNOWN이다. εa≤0 또는 SWT σmax≤0도 UNKNOWN이다. 압축 전용 이력을
안전/무한 수명으로 승인하지 않으며 clamp나 숨은 NONE 전환을 하지 않는다. 설정 자체의 교정
누락·잘못된 단위·미완성 숫자는 기존 owner에서 invalid draft로 저장할 수 있지만 실행은 차단된다.

## 3. 같은 cycle의 동시 σmax

기존 vendored rainflow 3.2.0 [3]의 range, mean, count, reversal start/end tuple을 그대로 사용한다.
보조 association은 같은 reversal stack의 contraction을 따라 원 표본 edge를 운반한다. 각 출력이
기존 counter의 tuple과 정확히 같은지 검사한다. counter 또는 notice는 변경하지 않았다.

`sampled-contracted-branches-v1`의 full cycle은 A→B reversal edge와 B에서 A의 strain 수준으로
최초 복귀하는 branch까지다. 이미 계수한 중첩 loop의 내부 표본은 바깥 branch에서 제거한다.
공유 시작/closure 경계 표본은 양쪽에 남을 수 있다. cycle membership의 실제 동시 응력 표본 중
최대값이 σn,max다. reversal start:end slice 또는 두 endpoint 최대값으로 대신하지 않는다.

복귀가 원 표본과 정확히 일치하면 그 closure 표본을 포함한다. 두 표본 사이에서 복귀하면 마지막
안쪽 표본까지 포함하고, 바깥 표본은 제외하며 closure의 두 원행/시간 bracket을 보존한다.
closure 응력이나 표본 사이 peak를 보간하지 않는다. 따라서 이것은 **원 표본 평가법**이다.
연속시간의 실제 최대응력 또는 미관측 급격한 peak를 복원했다는 뜻이 아니다. plateau는 최초
복귀 표본에서 닫히며 그 뒤의 표본은 다음 branch에 속한다. 이 표본 정책과 재료 적용성은
실제 사용 전 독립 공학 검토 대상이다.

고정 반례: ε=[0,4,1,2,3,4,5,0]×0.001, σ=[10,20,30,400,900,50,60,10] MPa.
reversal pair (index1,index2)의 full cycle membership은 [1,2,3,4,5]다. closure=5,
이를 검출하는 뒤 reversal=6이며 σmax=900은 복귀 branch index4에만 있다. 바깥 0→6 half branch는
[0,1,5,6]을 사용한다. 안쪽 loop 내부 [2,3,4]를 다시 바깥 loop의 peak로 소비하지 않는다.
`synthetic-nested-return-peak.csv`와 해당 unit test에 같은 반례를 제공한다.

initial/residual half cycles에는 실제 관측한 half branch의 최대응력만 사용한다. 없는 나머지
반 loop를 만들지 않으며 count=.5를 유지한다. 이 유한 이력 정책은 다음의 반복 블록 적합성과
별개다. 비비례 이력도 고정 면에 전체 동시 tensor 경로를 projection하고 같은 규칙을 적용한다.
추가 비비례 hardening이나 반복 소성 constitutive 계산을 수행한 것은 아니다.

## 4. 실제 critical-plane 검색과 모델 구별

각 unit normal n에 대해 εn(t)=nᵀε(t)n, σn(t)=nᵀσ(t)n을 계산한다. 법선 n과 −n은 같은 면이다.
검색은 반구의 극각 분할 p와 방위각 분할 4p, 적도에는 반면의 2p 법선을 사용한다. 극점은 한 번만
넣는다. p=3은 31면, p=6은 133면이다. 좌표면의 삼각함수 오차 <1e-15는 정확한 0으로 정리한다.
원 tensor 성분을 0으로 채우는 처리가 아니다. 사용자 검색기저는 det=+1인 고정 직교행렬이어야 한다.

이 버전의 채택 기준은 **평가한 유한 이력 전체의 최대 정상변형률 범위 면**이다:

    argmax_n [ max_t εn(t) − min_t εn(t) ]

최종 격자의 모든 면에서 projection, rainflow, 동시 peak, root, damage를 실제 계산하고 보존한다.
최대 SWT 면과 최대 알려진 damage 면은 별도 진단값이다. 더 작은 strain-range 면을 damage가 크다는
이유로 채택하지 않는다. 최대 strain-range 동률은 상대 1e-10/절대 1e-14로 기록하고, 그 동률 집합
안에서만 가장 큰 알려진 damage 면을 표시한다. 동률 면 중 UNKNOWN이 있으면 전체 D를 완성하지 않는다.
이는 cycle마다 다른 critical plane을 선택하는 모델이나 FS/shear-damage 모델이 아니다.

선정 반례: diag strain 진폭 (0.01,0.006,0), 일정한 인장 diag stress (100,400,0) MPa.
최대 strain 면은 x이며 P=1 MPa, 최대 SWT/damage 면은 y이며 P=2.4 MPa다. 이 둘을 같은 선정법으로
표시하지 않는 검사가 있다. `synthetic-plane-selection-counterexample.csv`에 12성분을 명시했다.

p→2p 세분화의 최대 range 상대변화를 보존한다. 한 격자는 수렴 미확인이다. 허용치 이내 변화도
연속 면 전체의 전역 최적값 증명은 아니다. 최종 p≤48, 면×원표본≤1,000,000, 원표본≤100,000의
명시 자원 한도가 있다. 자동 downsample/시간 정렬은 하지 않는다. 여러 독립 구간으로 나누면
원 전체 이력과 같은 counting이라는 보장은 없으며, 분할 결과를 자동 합성하지 않는다.

독립 검사는 직접 nᵀTn 계산, 단축 limit, 순수전단, 동상/90° 위상차 axial-torsion, 회전한 tensor와
같이 회전한 검색기저의 법선·range·SWT·damage 대응, off-grid rank-one tensor의 격자 개선을 포함한다.
고정 격자만 두고 tensor를 회전했을 때의 격자 편향을 물리 비불변성과 혼동하지 않는다.

## 5. Miner, UNKNOWN, 반복 블록

cycle의 increment는 count/Nf다. 알려진 increment만 더한 `admitted_partial_damage`와 모든 필요한
cycle이 계산된 `miner_damage`를 구별한다. 알려지지 않은 cycle을 0으로 완성하지 않는다.
취소나 부분 면 실패는 완료된 면을 보존하되 전체 critical 집합과 전체 damage/life를 발표하지 않는다.
진행 중이던 미완료 면의 일부 cycle까지 복원한다고 주장하지 않는다.

반복 블록은 사용자가 명시한 같은 안정 이력 반복에 대해서만 검사한다. 모든 공급 stress/strain
성분의 양끝이 명시 절대 허용치(기본 0) 안에 있어야 한다. 현재 projected strain 블록은 동일한 전역
극값에서 닫혀야 한다. 임의 phase의 기록을 회전하거나 블록을 몰래 이어 cycle을 만들지 않는다.
반대 방향 residual half pair는 range/mean뿐 아니라 같은 σmax 대응도 만족해야 한다.
range/mean 비교는 상대 1e-12/strain 절대 1e-15, σmax 비교는 상대 1e-12/절대 0이다.
이 비교 허용치와 pair별 σmax, 원행 membership을 결과에 보존한다.

같은 range/mean half count 합이 1이어도 σmax=500과 900 MPa인 pair는 반복 수명 UNKNOWN이다.
선택 면의 normal 성분 경계가 같아도 다른 stress/strain 성분이 다르면 역시 차단한다.
위상차 periodic 자료도 임의 경계에서 자른 경우 자동으로 periodic 승인을 하지 않는다.
그 경우 관측 유한 이력의 부분/전체 damage는 읽을 수 있으며 반복 수명만 UNKNOWN일 수 있다.

전부 적합하고 D>0이 유한할 때만 1/D blocks와 block_duration/D seconds를 보고한다. 이는 명시한
반복 가정 아래의 **블록 등가 노출량/시간**이며 sequence 안의 정확한 최초 파손 시각을 추적한 값이
아니다. 실측 수명·안전계수·공학 release가 아니다. cyclic state 미확인 또는 비안정 이력은 별도로
보존하며 동일 안정 블록의 반복 수명을 승인하지 않는다.

## 6. 보존과 잔여

기존 `damage.rainflow` → `SimulationDocuments` → `evaluation.run` → artifact/reader 경로다.
원 bundle과 source reference, measure/unit/basis/clock 검증, 계수·모델·식·검색 버전, plane 이력,
cycle 원행/closure/peak/root, 반복 조건, 선택을 보존한다. 저장 선택은 기존 Simulation 초안의
bounded `selection`이며 원결과를 수정하지 않는다. 별도 owner/store/schema framework는 없다.

SWT는 normal/tensile damage 모델이다. 축방향 교정으로 shear-driven 재료, 실제 비비례 추가경화,
반복 소성 누적, cohesive fatigue 또는 FS를 검증하지 않는다. cyclic Ramberg–Osgood 파생 이력도
구현하지 않았다. 그 경로에는 별도 cyclic K′/n′, 전단 교정 및 state/적용성 근거가 필요하다.
Impact A/native 실행과 B/bulk-interface damage, 실재 재료 engineering qualification은 이번 밖이다.

## 일차 근거와 라이선스

[1] COMSOL 6.4 공식 Strain Life Models, CMB total-strain 식:
https://doc.comsol.com/6.4/doc/com.comsol.help.fatigue/fatigue_ug_sme.4.21.html

[2] COMSOL 6.4 공식 Strain Based Fatigue Models, SWT 및 최대 normal-strain-range 면:
https://doc.comsol.com/6.4/doc/com.comsol.help.fatigue/fatigue_ug_sme.4.23.html
원 단축 SWT 출처는 Smith, Watson, Topper, Journal of Materials 5(4), 767–778 (1970).
첨부 MATH_SOURCES의 논문 서지와 이번 공식 HTML 확인을 구별한다. 논문 PDF/상용 코드/그림은 재배포하지 않는다.

[3] 기존 `caelab/_vendor/rainflow.py`, v3.2.0 / commit 5fc6822fd1c626739c6f95d9b4595ee80330b4fc.
MIT LICENSE/NOTICE를 변경하지 않았다. 새 helper는 counter의 코드/라이선스를 대체하지 않는다.
https://github.com/iamlikeme/rainflow/tree/5fc6822fd1c626739c6f95d9b4595ee80330b4fc
