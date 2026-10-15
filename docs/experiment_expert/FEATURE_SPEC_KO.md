# 제공 불확실성·최종점 진단·중단 토론 — 구현 명세

요청: PRO-EXPERIMENT-EXPERT-20261015-02. 기준은 첨부 공개 commit
`35a91ed5d882d63e83118e79e55844083eb7f093`이다. 새 프로젝트 형식, 저장소,
스케줄러, 수치 evaluator, 유료 provider, 장비 프레임워크를 만들지 않았다.
공통 연결은 root 검토용 작은 패치이며 현재 main의 전체 파일 교체본이 아니다.

## 1. 사용자가 끝내는 작업

파일 시험의 원값·교정 증빙을 Data에서 읽고, 제공 입력/계수 불확실성에 대해
**명시 전파**하거나 보존한 피팅 후보에 대해 **명시 최종점 진단**을 한다.
원값·곡선·제외 표본·실패·국소 판단을 읽고 다음 시험 질문을 Study로 저장한다.
Report는 선택한 실행의 입력/결과와 상세 배열을 동결해 새 owner에서도 읽는다.
CAD·AI·장비·WSL은 이 작업의 필수가 아니다.

### 구현 및 연결 상태

| 기능 | 이번 코드의 실제 지원 | 제한 / 별도 인수 |
|---|---|---|
| 원 시험 전파 | 기존 affine 교정의 원값·계수 미분, 명시 단위 변환, 입력·계수 공분산, 표본 간 출력 공분산 | 1차 값 전파. 축 미분·비선형 확률 전파·신뢰구간 아님 |
| Data 처리 전파 | 실제 C1 owner가 게시한 처리 개정, 정확 채널 hash, `trace_sample`의 signed 기여, 원 import 계수의 공통 영향 | 기존 선형 값 기여가 확정되는 경로. 새로운 DAG/보간/공분산 producer 아님 |
| 최종점 진단 | 정확 candidate/detail ref → 기존 evaluator의 일반 residual 차분 → 기존 SVD | robust optimizer J를 사용하지 않음. 원 fit 수렴/전역 유일성/실험 승인으로 승격하지 않음 |
| 명시 실행/재시도 | 기존 Numerical Request Plan·CAS command·JobManager·예산·취소·보존 결과 | C1 소유 API 연결 필요. C2 evidence CAS 완료를 주장하지 않음 |
| Study/Report | 기존 owner를 통한 질문/판단/보존 결과, 새 배열 포함 report projection | 통계·공학 승인 자동 생성 없음 |
| Expert 중단 | 기존 saved journal·명시 retry·현재 예산·권한/자료 검증 재사용 | 실제 계정/provider 호출 없음. Qt partial-reader는 Sol 소유 |
| 결과 환류 | 큰 새 시험 분석 결과를 명시적으로 불완전한 bounded summary로 전달하고 원 ref 유지 | 전체 상세 비교/채택/성공 보고 권한을 요약에 부여하지 않음 |
| 장비 | 기존 파일 수집/설정 재사용을 유지 | 실제 장비/driver/권한/physical stop 미제공, 장비 인도 아님 |

## 2. 불확실성의 수학과 보존 경계

기존 교정은 `y = a*(x*fx - x0*f0) + b`이다. fx/f0는 기존
`experiment_calibration.factor`의 명시 단위 변환이다. 교정값 y는 보존된
`transformed_value`를 읽으며 **다시 계산해 덮어쓰지 않는다**.
입력 좌표 `[x, a, x0, b]`의 민감도는 `[a*fx, x*fx-x0*f0, -a*f0, 1]`이다.
제공한 공분산 C에 대해서만 `C_out = G C G^T`를 계산한다.

`standard`는 제공 표준불확실성, `expanded`는 제공 U/k이다. k가 없으면 해당
표준불확실성은 미확인이다. 표준불확실성과 제공 공분산 대각이 모순이면 거절한다.
대칭·차원·유한성·분산·Cauchy bound·계산에 사용한 완전한 공분산 블록의 PSD를
검사한다. 혼합 단위의 큰 숫자가 잘못된 상관을 가리지 않도록 PSD는 무차원화한다.
완전하지 않은 공분산은 NaN 내부 표지/JSON null로 미확인을 유지한다.
모든 입력의 공동 분포 또는 누락 성분의 PSD completion을 추정하는 엔진은 아니다.

미제공 상관은 0이 아니다. 독립성은 `independent_declared`와 근거를 함께
명시해야 한다. **명시된 0 분산**에 대한 0 공분산만 수학적으로 사용한다.
원 fit 잔차·RMSE·optimizer curvature는 측정 불확실성의 공급원이 아니다.
부분 전파에서는 계산 가능한 행과 미확인 행을 분리한다. 원 범위/포화/품질/표시
선택/Plan mask는 원본에 그대로 남으며, 포함 집합의 교집합만 계산한다.

원 채널의 제공 output uncertainty는 별도 항목이다. 새 전파 결과를 여기에
덮거나 두 값을 자동 합산하지 않는다. 출력 값이 같다고 같은 센서/교정으로
합치지 않는다. 같은 원 import application의 계수는 그 표본들에서 공유하고,
다른 source/channel의 동일한 숫자 레시피는 별도 불확실 입력으로 남긴다.

Data C1의 `trace_sample`을 실제 호출한다. `.terms`만 signed 원값 기여이다.
`validity_inputs`는 품질/gap 판정용이며 값 covariance에 섞지 않는다.
원 affine import 계수의 미분에 필요한 원 x를 해당 import node에서 읽는 것은
값 기여가 0인 경우에도 필요하다. 이미 있는 DAG를 걸을 뿐 새 처리 DAG를 만들지 않는다.
보간/SG 계수는 **동결 축 아래 값 기여**이며 축 좌표 불확실성 미분이 아니다.

`axis_uncertainty=UNKNOWN`에서도 값 조건부 전파는 가능하지만 전체 측정
불확실성은 UNKNOWN이다. `fixed_coordinates_declared`도 선언 조건부 1차 결과일
뿐이다. 실제 축 불확실성 요청, actuator travel→specimen strain, 공간 투영,
mesh mapping은 지원한다고 꾸미지 않고 해당 전파/변환만 차단한다. 제공 위치·방향·
기준계·시각의 원 metadata와 UNKNOWN/UNSPECIFIED 표시는 유지한다.

구현 한도: 입력 변수 512개, 출력 표본 512개, raw affine 경로는 원값+계수 3개를
포함하므로 원행 509개 이하. 이는 명시 dense covariance 기능의 한도다. 전체 원자료
읽기/저장 한도로 주장하지 않는다. 큰 데이터를 임의 다운샘플해 통과시키지 않는다.

## 3. 최종점의 일반 residual Jacobian

소비 시작점은 실제 `resolve_candidate_evidence`의 immutable snapshot이다.
`read`는 요약/실패를 읽을 수 있다. 실제 새 평가 및 성공 보고에는 기존
`success_report` gate를 다시 사용한다. 실패 목적 ref는 실패 진단으로 남긴다.
`candidate_detail_readiness`만 보고 저장/성공을 승인하지 않는다.

정확한 계수값/선언 변환/단위/범위, 시험 settings, 원 행·derived sample ID,
coordinate sample ID, 원 mask, response metadata, weight/scale, evaluator
등록·설정·버전, 원 holdout 및 선택 attempt가 source problem에 결합된다.
소비자별로 달라지는 permission 출력은 불변 입력 hash에 넣지 않는다. 실제
snapshot의 readiness를 보존하고 현재 소비 gate는 별도로 재검사한다.

기존 residual은 `sqrt(weight/retained_count)*(prediction-observation)/scale`이다.
`numerical._aligned`, `_experiment`, `_Evaluators`, `_Budget`를 재사용한다.
선형 또는 자연로그 계수 좌표에서 각 자유 계수를 바꾸며 모든 fit 시험을 평가한다.
기본 범위 상대 간격은 1e-4, 명시 지원 범위는 1e-8…1e-2다.

- 내부점: 기준점 + 계수별 ±h, ±h/2. 모델 호출 수 `(1+4*n)*fit시험수`.
- 경계/경계 근처: 기준점 + 가능 방향 h, 2h, h/2의 2차 한쪽 차분.
- 실제 float 표현 좌표로 차분 가중치를 만들며 점이 구별되지 않으면 차단한다.
- h와 h/2 비교 외에 같은 평가점의 좌우 2차 미분을 대조한다. `abs(x-x*)` 같은
  대칭 뾰족점이 0 미분으로 오인되는 경우를 막는다. 추가 모델 호출은 없다.
- 한쪽 경계 진단은 그 가능 방향의 국소 진단이다. 경계 밖/양쪽 미분 가능성은
  UNKNOWN이며 이 검사를 수학적 미분 가능성의 증명으로 부르지 않는다.

기존 수치 gate를 완화하지 않았다. 기존 SVD 상대 rank 허용치는 **1e-6**이다.
추가 gate: 보존 기준 잔차 재현 rtol=1e-10/atol=1e-12, 차분 일관성
rtol=1e-3/atol=1e-10. 불일치하면 행렬·평가를 보존하고 식별 판단은 UNKNOWN이다.
고정 계수는 원 Plan에 실제 `free=False`로 보존된 항목만 별도 표시한다. 시험별
고정 settings는 전체 그대로 보존한다. 없는 고정 계수 정의를 생성하지 않는다.
active bound, 국소 미식별, 평가 실패, 수렴 여부, 전체 측정 불확실성을 구분한다.

robust LSQ의 `result.jac`는 재사용하지 않는다. DE에서 J가 없다는 사실을 그대로
유지하고 별도 명시 작업에서 일반 J를 생산한다. **원 optimizer를 다시 돌리지 않는다.**
정확한 보존 일반 J는 `reuse_result`를 명시한 경우 검증 후 0 평가로 재사용한다.
일반 읽기/저장/재열기는 이 재사용 작업조차 제출하지 않는다.

예산 미달은 0 호출의 REJECTED다. 실패를 penalty residual로 바꾸지 않는다.
각 실제 차분점/시험 raw·곡선·실패 사유를 새 attempt 결과에 남긴다. 취소 후
남은 점은 NOT_EVALUATED이며 원 fit/실패 attempt/holdout을 바꾸지 않는다.
이번 진단에서 holdout 모델 호출은 항상 0이다. 원 holdout 실패가 새 성공
국소 진단 뒤에도 그대로 남는 회귀를 포함한다.

지원 한도는 자유 계수 64개, 실제 residual 행 32768개, 기존 직렬 evaluator이다.
이산 event 미분, 미제공 evaluator binding, 다른 backend 버전, 현재 residual
엔진이 소비하지 않는 sample_weights, 상태를 차분점 사이에 재사용하는
EvaluationDefinition은 차단한다. 지원 불가를 숫자/성공으로 위장하지 않는다.

## 4. Data C2 / Numerical C2의 단일 소유

Data canonical packet이 실제로 동결 snapshot에 있으면 제공된
`consume_frozen_fit_inclusion`으로 검증한다. derived sample이 있는데 canonical
packet 운반이 없으면 새 J는 차단한다. integer source_rows로 바꾸거나 legacy
packet의 이름/hash를 복사해 canonical이라고 표시하지 않는다.
원행/inline 경로는 명시 legacy/inline residual 경로라는 상태를 남긴다.

Data C2의 freeze/consume 운반 adapter와 Numerical C2의 PRESERVING/CAS 복구는
이번 코드에 없으며 해당 파일을 수정하지 않았다. 이번 전용 소비 adapter는 실제
Data owner의 처리 결과와 실제 C1 evidence reader를 호출한다. 이 둘이 아직
합의/통합됐다는 뜻이 아니다. 파생 피팅의 끝까지 인수는 C2 통합 후 root의 업무다.

## 5. FN30 — journal에서 재개, 계산 결과 반환

새 토론 backend나 journal store는 없다. 원 `document_result`/DiscussionDocuments,
`expert.retry`, `assist.costorm.Completion`과 실제 vendored runner를 재사용한다.
추가 `expert_journal_inspection`은 선택한 원 job의 raw journal을 페이지 단위로 읽는
순수 projection이다. Sol의 partial-reader/Expert 창은 교체하지 않는다.

중간 text와 committed 발언/report를 구분한다. STOPPED 예산 소진과
CANCEL_REQUESTED/CANCEL_CONFIRMED도 구분한다. 같은 원 job을 저장·새 owner에서
읽어도 inference는 없다. 명시 retry만 현재 한도에서 새 호출을 허용하고 유효
journal은 재생한다. 형식 불량 completion, 권한 취소, source 개정 변경을 검사한다.
미전송 새 의견은 retry에 자동 섞지 않고 명시 intervene 이후 전달한다.

추가 확인한 연결 결함: 새 시험 분석의 full JSON은 1,000단어보다 커질 수 있다.
기존 Co-STORM formatter는 그런 단일 snippet을 **통째로 생략**했다. 실제
SelectedRetriever/runner 회귀에서 재현했으며, 새 두 결과 종류에 대해서만
원 ref를 유지한 bounded summary를 우선 삽입한다. 요약은 처음 8개 표본/계수와
생략 수, 상태/단위/원값/UNKNOWN/미승인을 명시한다. full raw/J/DAG는 원 결과에
있다. 이 요약에 comparison/adoption/success_report 권한을 새로 부여하지 않는다.
기존 권한·전송 범위·payload gate는 낮추지 않았다. 다른 결과 종류는 변경하지 않았다.

실제 계정·OAuth·provider는 호출하지 않았다. 테스트의 생성문장/검색만 명시 시험
대역이며 owner·취소·허가·저장·journal·vendored runner는 실제 소스가 실행됐다.
토론 내용의 사실 정확도나 실제 provider 연결 인수로 이 결과를 사용하면 안 된다.
