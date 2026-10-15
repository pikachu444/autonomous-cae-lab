# FN05 C1 — 부분 결합 공분산·canonical 소비·최종점 잔차 교정

요청: PRO-EXPERIMENT-EXPERT-20261015-02-C1. 원 FN05 기능의 교정이며 별도 전파 엔진, Data compiler, Numerical evaluator, 저장소, 스케줄러 또는 통계 플랫폼을 추가하지 않는다.

## 1. 부분 공분산의 의미와 차단 조건

원 결함은 개별 출력의 분산이 양수라는 사실을 결합 공분산의 유효성으로 잘못 사용한 것이다. 원 ZIP을 읽어 Linux/NumPy에서 직접 재현한 3×3 행렬은 대각 1, 비대각 −0.9이다. 고유값은 약 −0.8, 1.9, 1.9이고, v=(1,1,1)에 대해 vᵀCv≈−2.4이다. 네 번째 입력이 UNKNOWN이라는 이유로 이 알려진 모순을 통과시킬 수 없다.

`propagate_linear`는 기존 입력 구성과 개별 출력 계산을 유지하되 반환 전에 다음을 검사한다. 먼저 실제 계산할 출력의 0이 아닌 민감도에 등장하는 입력들의 합집합을 구한다. 이 관련 입력에서 완전히 알려진 모든 최대 principal block을 검사한다. 그다음 계산된 출력들의 공분산에도 같은 검사를 적용한다. 최대 block이 PSD이면 그 principal submatrix도 PSD이므로 모든 부분집합을 중복 검사할 필요는 없다. 서로 겹친 알려진 block도 검사하며, 단순 연결 성분별 검사로 대신하지 않는다.

알려진 관계를 그래프로 표현한 정확한 최대 clique 열거를 이 전용 함수 안에서만 사용한다. 외부 라이브러리나 covariance-completion 엔진은 없다. 방문 한도 65,536과 block 한도 4,096에 도달하면 UNKNOWN 사유로 해당 전파를 거절한다. 검사를 중간에 잘라 성공으로 반환하지 않는다. 기존 512개 입력/출력 한도는 유지한다.

PSD 판정은 기존처럼 표준불확실성으로 정규화한 무차원 행렬 A에 대해 `λmin(A) < −1e−12 × max(1, ||A||₂)`이면 거절한다. 이 기준을 완화하거나 단위 있는 고유값에 같은 절대 허용치를 적용하지 않는다. 0 분산의 0 아닌 공분산과 비대칭·비유한 보존 행렬도 거절한다. 대칭 확인 역시 표준불확실성 정규화 공간에서 수행한다. 대각 jitter, 고유값 절단, 임의 covariance 투영은 없다.

미제공 상관/공분산은 None으로 남는다. 미제공 관계를 0/독립으로 채우지 않는다. 명시적으로 0인 표준불확실성에 따르는 0 공분산은 원 구현의 수학적 처리 그대로이다. 출력별 필요한 공분산이 있으면 그 표준불확실성은 계산할 수 있다. 다만 출력 간 관계가 없으면 결합 공분산은 UNKNOWN이다. 제외된 출력과 그 출력에만 필요한 입력은 부분 결합 검사 대상이 아니다. 원 구현의 완전 제공 C에 대한 전체 PSD gate도 그대로 유지한다.

이 검사는 **모든 누락 관계에 대해 PSD 완성이 존재함을 증명하는 기능이 아니다**. 특히 알려진 block들이 유효해도 비 chordal 누락 관계의 완성 문제는 풀지 않는다. 결과에 `complete_joint_covariance=UNKNOWN`, `missing_covariance_completion=NOT_PERFORMED`를 남긴다. 보고서와 제한된 Expert 요약에서도 미제공 결합 관계를 명시한다. 개별 표준불확실성 계산 완료를 전체 결합 불확실성 확인으로 승격하지 않는다.

### 반환·실패 보존

기존 `propagate_linear(...)` 호출 인자는 바뀌지 않는다. 정상 반환에는 `joint_covariance_validation`이 추가된다. 입력/출력별 검사 block 수, 가장 큰 block 크기, 관련 입력/계산 출력/제외 출력 인덱스, 미제공 관계 수를 진단에 둔다. 원값, 처리 DAG, 제공 spec, 기존 mask는 변경하지 않는다.

알려진 관련 block이 비PSD이면 `InvalidCovariance(ValueError)`가 발생한다. 사용자 업무용 `propagate(problem, specification)`는 이를 `REJECTED` 결과로 보존한다. 포함 행은 UNKNOWN, 제외 행은 EXCLUDED이며, 잘못된 계산 prefix나 출력 공분산을 성공 결과로 반환하지 않는다. 원값·제공값·사유는 유지된다.

`validate_retained_covariance(result)`는 기존 보존 결과의 새 Study/Report/Expert 소비를 위한 읽기 전용 검사이다. 오래된 성공/부분 결과라도 알려진 결합 공분산이 비PSD이면 새 계산 근거로 받아들이지 않는다. 원 파일을 수정하지 않고 전파·모델 평가도 다시 실행하지 않는다. 원 owner의 일반 읽기는 여전히 가능하다. 거절 결과는 실패 사유 및 다음 연구 질문의 근거로 저장할 수 있다.

## 2. canonical과 legacy의 분리

`problem_from_evidence(resolved, *, submitted_arguments=None)`는 기존 immutable evidence 소비 gate가 확인한 결과를 받는다. canonical일 때는 같은 저장 revision에 속한 원 run의 실제 제출 arguments도 필요하다. 단순 호출자가 새로 작성한 Plan이나 다시 freeze한 packet으로 대신할 수 없다.

canonical의 원 위치는 `fit_input.inputs.frozen_inclusion`과 `fit_input.data_inclusion`이다. 각 experiment의 `frozen_fit_packet` header와 `frozen_fit_inclusion` trial을 유지한다. FN05는 `data_processing_consumer.admit_snapshot` 및 `retained_assessment`를 호출한다. 이들은 Data의 기존 `consume_frozen_fit_inclusion`으로 원 packet, 관측/원 source, settings, DAG, mask, sample_weights, 응답, 표본·좌표 ID를 확인한다. accepted 시험, 원 보존 시험, 기존 data_inclusion 판정이 같아야 한다.

`selected_problem`은 기존 `resolve_candidate_evidence`를 먼저 사용하고, 그 소비자가 쓰는 `_saved_owner`/`_source`로 동일 저장 원 run의 arguments를 읽는다. submitted arguments digest, inputs digest, immutable snapshot/reference 결합을 확인한다. live Plan, 현재 Data 개정, 최근 성공 attempt를 원 선택 대신 읽지 않는다. read/preview/save에서 새 packet 생산이나 모델 호출은 없다.

`fit_inclusion → fit_input.inclusion_packet`은 기존 Numerical-local legacy 경로로 별도 검증한다. canonical packet을 literal alias로 옮기거나 legacy wrapper로 가장하지 않는다. 파생 표본인데 실제 canonical packet이 없으면 차단한다. 원 Data C2 consumer/selection/lineage, Numerical transport/evidence CAS 파일은 이번 패치에 없다.

## 3. 가중 일반 잔차 Jacobian

FN05는 `sample_weights`를 무조건 거절하지 않는다. 기존 `numerical._experiment`의 검증을 먼저 호출하고, 차분 평가마다 기존 `_aligned`가 만드는 잔차를 그대로 사용한다.

포함 행 i의 원 Numerical 잔차는 `(prediction_i − observation_i) / scale × sqrt(experiment_weight / n_included) × sqrt(sample_weight_i)`이다. sample_weights가 없을 때만 마지막 항이 없다. FN05가 가중치를 다시 곱하거나 1로 바꾸지 않는다. 포함 표본의 0 weight는 현재 Numerical이 거절하는 입력이며, FN05도 평가 전에 거절한다. 제외 표본의 0 weight는 mask와 함께 그대로 보존한다.

J의 행은 원 experiment 순서와 포함 행 순서이다. 원/파생 표본 ID, coordinate_sample_id, 응답·단위, weight/scale/sample_weight, 관측·원 source·settings·mask digest와 canonical packet digest가 결합된다. 전체 source problem에는 원 packet/DAG/원값 및 evaluator binding이 보존된다. 해시 계산은 시험당 한 번으로 공유하되 값이나 행 순서는 바꾸지 않는다.

기존 h/h2 차분, 좌우 일관성, 경계의 단측 차분, log 좌표, 고정 계수, 예산·취소·실패 보존, SVD 상대 허용치 1e−6은 그대로이다. robust optimizer-modified J 또는 DE의 미보존 J를 재사용하지 않는다. 실제 선택 계수점에서 일반 잔차를 명시 평가한다. 원 fit holdout과 과거 실패/미보존 상세를 이후 결과로 소급 채우지 않는다. 추가 진단은 holdout을 평가하지 않는다.

원 C1 이전의 정확한 **비canonical·sample_weights 없는** 일반 J는 기존 행 형식과 전체 problem hash를 검증하여 읽을 수 있다. 새 메타데이터를 원 기록에 소급 삽입하지 않는다. weighted/canonical 기록을 legacy로 내리는 fallback은 없다. 모든 읽기는 evaluator를 호출하지 않는다.

## 4. 이번에 변경하지 않은 경계

제품 변경은 `experiment_uncertainty.py`, `experiment_final_diagnosis.py`, `experiment_analysis_service.py`, `experiment_analysis_reporting.py` 네 전용 모듈뿐이다. 새 공통 product integration hunk는 필요하지 않았다. 기존 root FN05 연결이 전제이다.

Data C2 compiler/consumer/운반, Numerical C2 CAS/savehook, 현재 식별 GUI/775 교정, Expert 부분응답, Report/Study owner, Sol GUI는 수정하지 않는다. 파일 기반 연구는 실장비·AI·CAD·WSL을 필요로 하지 않는다. C01 closure는 별도 C3 범위로 남으며 이번 tiny chain 성공은 그 완료 증명이 아니다. 전파 결과는 제공 입력 및 고정 축에 조건부인 1차 결과이고, 통계적 신뢰구간·전역 유일성·측정 불확실성 전체·공학 승인을 부여하지 않는다.
