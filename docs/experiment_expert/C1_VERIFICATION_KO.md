# FN05 C1 검사 범위와 결과

## 실행 결과

**새 적용 사본의 선택 회귀: 76 passed / 0 failed / 0 errors / 0 skipped.** 원 테스트와 C1 신규 검사를 묶은 11개 모듈이며, 제품 전체 검사나 Windows 인수 건수가 아니다. 실제 라이브러리는 pytest 9.0.2, numpy 2.3.5, scipy 1.17.0, jsonschema 4.26.0이다.

최종 수치는 패킷의 `verification/final-regression/execution.json`, `junit.xml`, `pytest.log`를 기준으로 한다. 동일 원 전용 파일에 `product.patch`를 적용한 새 시험 사본에서 명시된 FN05 회귀를 실행한다. 개발 중 재시도 횟수나 기존 제품 전체 행 수를 완료율로 계산하지 않는다.

검사 대상은 원 analytic/단위/상관/UNKNOWN, 제공 output uncertainty 및 교정값 보존, shared 교정계수와 signed 원자료 기여, 새 부분 결합 PSD, 실제 canonical 소비, 비균일 sample_weights, final-point 일반 잔차/J, 고정/log/active bound, rank deficiency, robust/DE, 실패·예산·취소, 원 holdout/attempt 보존, 파일·Study·Report·새 프로세스 읽기이다.

원 source의 반례는 별도로 읽어 실제 Linux NumPy에서 실행했다. 기존 반환은 u=[1,1,1,None], 결합 최소 고유값 −0.8, vᵀCv≈−2.4였다. 수정 후 같은 입력은 ValueError/REJECTED 경로로 차단된다. 수치·사유 원 기록은 `verification/counterexample_before_after.json`에 있다. 첨부 `repro_partial_joint_psd.py`의 시험 코드를 별도 회귀 파일로 그대로 포함했다.

## 실제로 실행한 연결

Data 시험은 실제 CSV reader/import, Data owner의 processing.preview/apply/저장 및 현재 Data C2 compiler/consumer를 사용한다. 입력 파일은 공개 합성 전압/시험이며 회사자료·장비 측정 인증 자료가 아니다. original row, quality/calculation/Plan mask와 파생 기여를 보존한다.

canonical owner 시험은 실제 public `data.sample_policy.preview` → `data.sample_policy.adopt` dispatch와 명령 receipt를 사용한다. 채택한 policy의 source domain을 원 Plan command에서 다시 확인한다. processing 개정에서 fit/holdout 7개씩, 중간 비균일 가중치, 제외 행의 0 가중치를 실제 canonical packet으로 운반한다. packet/원 arguments/header/trial/source/settings/mask/weights/sample ID에 대한 변조를 기존 소비자가 거절하는지도 검사한다. 소비 단계의 새 `freeze_fit_inclusion` 호출은 금지한다.

실제 SciPy least_squares/DE 및 현재 Numerical 상세 평가·immutable evidence 승인 경로를 사용한다. 평가기 `test.fn05.c1.synthetic`는 명시 합성식 P=mu·t이며 기존 FELUPE backend를 덮지 않는다. 최종점의 5회 평가는 이 식을 기존 Numerical 평가 경로로 호출한다. J를 독립 해석식 `t × sqrt(sample_weight) × sqrt(experiment_weight/n)/scale`과 대조한다. 별도 다계수 analytic 회귀에서도 비균일 가중치, robust/DE 후 일반 J, 경계·고정·실패·차분 일관성을 확인한다. 이는 실제 엔지니어링 재료법칙 검증이 아니다.

저장 시험은 원 Data·Material·Numerical을 각각 저장한다. 원 fit 결과와 원 상세 미보존 상태가 나중 성공으로 채워지지 않는지 확인한다. 최종점 결과·Study·보고서를 저장한 뒤 휘발성 input/result/processing을 삭제하고 한글 경로를 이동한다. **별도 새 Python 프로세스**에서는 합성 evaluator를 등록하지 않고 submit을 금지한 상태로 같은 candidate evidence, 일반 J, 원 fit, 보고서, Study를 읽고 다시 저장한다. 결과 hash와 job 수가 유지된다. 이 결과는 pytest log의 `FN05_C1_COLD` JSON에도 남는다.

비PSD/정상 공분산 각각은 실제 원 Data → FN05 Plan → 결과 저장 → Study/Report 저장·다시 읽기의 작은 owner 경로로 검사한다. 거절을 정상 계산으로 바꾸지 않으며, 원 시험값과 제공 spec 및 제외 mask가 유지된다.

## 시험 fixture 정합 교정

현재 `NumericalDocuments`는 이미 CandidateDetailMixin을 상속하므로 원 Pro 시험의 이중 상속을 제거하고 실제 owner를 직접 사용한다. 현재 Data owner의 공개 processing 명령과 retain hook도 이미 있으므로 원 시험의 추가 수동 apply/이중 retain을 제거했다. 이는 제품 수학 교정과 별개의 시험 fixture 정합이다.

큰 canonical arguments를 수 millisecond마다 deepcopy하던 원 시험 polling 때문에 로컬 개발 재현에서 20초 fixture 대기를 초과했다. 같은 JobManager의 정확한 Future 완료를 기다리도록 시험 지원 코드를 변경했다. 제품 timeout, scheduler 또는 수치 허용치를 바꾸지 않았다. 개발 중 시험의 `base_residual`/`timing` 필드 가정도 실제 `residual_base`/`diagnostics` 계약에 맞췄다. 최종 결과는 수정 후 전체 선택 회귀에서 확인하며 이 이전 실패를 통과 횟수에 더하지 않는다.

## 미실행·범위 밖

Windows Qt, 전체 Workbench GUI 생성자, native solver/READ, FELUPE 수치 계산, 실제 provider/계정, 실제 장비 호출은 실행하지 않았다. 신규 외부 API나 provider 호출은 0회이며 설치·구독·추가 지출을 요구하지 않는다. 원 ODE native factory 검사를 이번 선택 회귀에 넣지 않았다. Qt 검사는 이번 제품 교정 범위에서 실행하지 않았다; skip을 pass로 세지 않는다.

시험 사본의 Workbench 생성 부분은 `C1_APPLY_KO.md`에 명시한 조합이다. 그 이후 owner·JobManager·Numerical/Data 수학·저장/승인 코드는 실제 제공/동일 commit 코드이다. 전체 current main 통합, 독립 Astra 검토, Sol GUI 완성, C01 C3 closure, 일반적인 이기종 파일 이동/장비 재시작을 완료 처리하지 않는다. PSD 및 국소 Jacobian 성공은 측정 불확실성 전체, 통계적 신뢰구간, 전역 유일성 또는 공학 승인이 아니다.
