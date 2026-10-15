# 실제 검사 및 남은 범위

## 2026-10-15 Windows 통합 확인

아래 Linux 기록은 원 작성 환경의 결과로 보존한다. 이후 Codex가 현행 소스에 최소
공통 패치를 통합하고 Sol이 기존 Windows Python 3.12.14·FELUPE 11.1.3 환경에서
공개 Neo-Hooke 사례를 실행했다. 새 패키지·유료 호출·다른 솔버 설치는 없다.

실제 Data 변환→같은 측도 예측→독립 train/holdout 피팅→보존 후보 상세·비교→
명시 계수 채택·저장→별도 프로세스 재열기가 끝났다. μ는 1.2500000000013436 MPa,
피팅 RMSE는 약 8.93e-13 MPa, 독립 검증 RMSE는 약 8.58e-12 MPa다. 실행 전 고정한
상대 계수 오차 2e-5와 응력 RMSE 2e-5 MPa를 바꾸지 않았다. 재열기는 기존 입력·작업·
결과 경로를 격리한 뒤 수행했고 새 계산은 없었다. 미완성 `1e` 저장·무효 판정·정정 뒤에도
과거 결과는 유지됐다.

첫 사례는 채택 뒤 바뀐 현재 Material을 과거 Plan과 다시 컴파일하려다 정상 관문에
막혔다. 예제가 초기 재료의 기존 저장 개정·내용을 명시하도록 교정했으며, 원 실패를
보존하고 새 출력에서 재실행했다. 물리 엔진과 허용 기준은 바꾸지 않았다.

실제 Qt에서 설정·변환 원행·응력 비교 창의 한글·좁은 창·키보드·취소·미완성 숫자와
미리보기/반영 분리를 확인했다. 실제 저장 곡선을 읽은 Numerical 창에서 피팅/검증
전환·측정 신장비와 언로딩 순서를 확인했다. 이 GUI 확인은 통제된 읽기 응답을 사용했으며
새 HTTP 계산이나 GUI에서의 전체 저장·재열기 시험을 의미하지 않는다. 계산·저장 검사는
위 실제 서비스 경로와 구별한다. 모든 소유 프로세스와 Job은 종료했다.

Astra의 독립 검토에서 발견한 실제 시험 설정 전달과 파생 곡선의 원 시험 연결을
교정했고, 원 실패 문구·공통 상태 표시·숫자 가독성도 보완했다. 전용 코드는 Pro 작성,
국소 연결·예제·화면 교정은 Codex/Sol 작성이다. 새 비동축·다른 법칙/요소 조합과
실측 물성의 타당성, 광범위 취소·저장 실패 시나리오 전체 수용은 이 확인 범위가 아니다.

원 실행·첫 실패·최종 GUI 기록은 로컬
`_workspace/delivery-data-material/finite-measure-windows-01/`과
`_workspace/delivery-data-material/finite-measure-windows/gui/`에 보존했다.
일반 사용 방법과 실제 화면은 [사용법](USAGE_KO.md)을 따른다.

## 최종 검사 결과

Linux Python 3.13.5의 기존 환경을 사용했다. FELUPE/PySide6는 미설치이며 추가 설치·다운로드·업그레이드·유료 호출은 하지 않았다. 환경 세부사항은 ZIP의 `evidence/ENVIRONMENT.json`이다.

| 검사 | 실제 결과 | 기록 |
|---|---|---|
| 신규 관련 단위/계약 + 직접 영향 legacy | 35 passed, 1 skipped, 1 deselected; exit 0 | final-tests-r02.log |
| 변경 Python AST | 28개 PASS | syntax.json |
| 실제 Data import→finite processing→Plan policy/frozen→저장→별도 process cold | PASS; 전체 runnable exit 2 | case-r07.log, case-r07/result.json |
| 실제 현재 입력·job·result 원경로 격리 | PASS, 원폴더 파일 수4/2/22 | case-r07/quarantine.json |
| cold에서 새 job 생성 | 0 | case-r07/cold.json |
| 원 결과/hash 및 raw `1e` 저장·무효 검토·수정 | PASS | case-r07/checkpoint.json, cold.json |
| 실제 Neo 수치 예측/fit/후보 상세·비교/CAS 채택 | NOT_RUN | case-r07/native-not-run.json |
| Qt offscreen 및 실제 Windows 창 | NOT_RUN | PySide6 importorskip, Windows 미실행 |
| 두 patch 원 baseline 적용 및 변경 파일 SHA | PASS 여부는 실제 패키징 기록 참조 | PATCH_VERIFICATION.json |

실행한 최종 명령:

```text
python -m pytest -q tests/finite_measure tests/test_material_test_workflow.py -k 'not csv_two_coefficients'
python scripts/finite_measure/run_case.py --output /mnt/data/finite_work/evidence/case-r07
```

1 skipped는 PySide6 없는 전용 GUI 모듈이다. 1 deselected는 실제 FELUPE를 요구하는 기존 `csv_two_coefficients` 경로다. 예측 테스트의 P/F/accepted record는 수학 및 계약 반례를 위한 명시 fixture이지 실제 backend 결과라고 주장하지 않는다. 독립 Neo fixture 식은 입력 파일을 생성하기 위한 oracle이며 제품 controller 또는 backend를 대체하지 않는다.

## FM별 판정

| 조건 | 확인된 부분 | 남은 부분 |
|---|---|---|
| FM01 | 단위/열 순서가 다른 동일 시험 CSV 실제 읽기, 수치 동등, 원행·원값 추적 | Windows 입력 UI |
| FM02 | P/진응력/e/lambda/log 손계산, 면적/J 일치, DAG·처리 저장 | 실측 자료 적용 수용 |
| FM03 | 필요한 필드만 검증, 잘못된 단위·frame·방향·domain·중복 충돌·crosshead 명시 가정, raw invalid 저장 | 실창 오류 수정 |
| FM04 | exact raw DAG·aux sample/time mismatch·재hash 변조·무효행/이유·mask/weight·train/holdout 독립성 | Windows 표/곡선 조작 |
| FM05 | candidate actual F/J 변환 코드, 원 P/결과 불변과 실패/수렴 관문 계약 검사 | **실제 Neo 평가에 대한 연결 실행 NOT_RUN** |
| FM06 | 기존 coefficient Plan 구성·sample policy·독립 frozen fit/holdout 실제 owner 실행, native 후반부 runnable 작성 | **실제 fit·보존 후보 비교·CAS 채택 NOT_RUN** |
| FM07 | `1e` 보존·무효행·현재 정의 일치 관문, backend 실제 준비 오류, prefix 채점 차단 계약 | Qt Cancel/late callback/저장 실패 주입·실행 취소 native 실증 NOT_RUN |
| FM08 | 실제 Data/Material 초안/Plan frozen source cold, 원경로 격리, job0, 원 hash, 현재 owner 재편집/save | 실제 fit 결과·후보·채택을 포함하는 cold 분기 NOT_RUN |
| FM09 | 전용 Qt 코드와 기존 독립 메뉴 연결 작성 | Windows 실창 전부 NOT_RUN |

전체 사용자 흐름 완료를 PASS로 판정하지 않는다. 실제 native 후반부는 미실행 코드 경로이므로 추가 결함이 남을 가능성도 있다. 지원 법칙/FE pair, B4 전체, 실측 적합성 또는 engineering release를 완료로 표시하지 않는다.

## 실제 실패와 교정 이력

`unit-r01`은 반복 lambda에서 다른 힘을 주고 동일 stress를 기대한 잘못된 테스트 기대값으로 실패했다. 하중이 다르면 응력이 달라지는 기대값으로 교정했다. 원 로그를 남겼다.

`case-r01`은 저장 JSON key 정렬 후 nonlinear footprint가 달라지는 실제 구현 결함이었다. parent dict 순회 대신 정의된 역할 순서로 sample identity를 만들도록 수정했다. sorted JSON roundtrip 회귀를 추가했다.

`case-r02`는 미설치 오류가 baseline에서 CapabilityUnavailable로 감싸지는 것을 runnable이 처리하지 못한 실패였다. 실제 타입과 원 메시지를 기록하는 NOT_RUN 분기를 교정했다. backend 성공으로 바꾸지 않았다.

`case-r03`은 기존 preview가 무효행을 남기는 READY/성공 projection임에도 전체 execution FAILED를 기대한 runnable 검사 실패였다. 유효 response 부재, operation_valid=false와 원 이유 보존을 검사하도록 교정했다. Plan 실행 관문은 완화하지 않았다.

`case-r04`는 후속 저장 시 현재 retained_revision locator가 바뀌는 정상 projection을 물리 결과 변조로 비교한 검사 실패였다. 첫 cold에서는 전체 projection hash를 비교하고, 후속 저장 뒤에는 locator를 제외한 불변 내용과 실제 저장 result.json SHA를 구분해 검사했다. 원 내용 hash를 임의 재작성하지 않았다.

`case-r05`는 Data/Plan/cold에 성공했으나 격리 경로를 잘못 지정하여 실제 input/job/result 폴더를 옮기지 않았다. 따라서 경로 독립성 검증은 성립하지 않는다. r06/r07에서 실제 Workbench root 아래 경로 존재·격리·파일 수·원경로 부재를 assert하고 별도 프로세스로 재실행했다. 최종 근거는 r07이다.

중간 ZIP의 상세 구현 문서 누락도 최종 인도에서 교정했다. 원 중간 ZIP과 그 존재검사 JSON은 변경하지 않는다. 새 최종 파일을 최종 기준으로 사용한다.

## 고정 공개 사례

실행 전에 FIXED_CASE를 output에 기록했다. mu 진값1.25 MPa, lmbda5 MPa, A0 20 mm2, L0 50 mm, mu초기.8/범위.5–2, 자유변수 mu 하나, budget40, seed17이다. 시간0–5 s, train lambda=[1,1.1,1.2,1.14,1.24,1.18], holdout=[1,1.07,1.17,1.11,1.22,1.16]이다. 기존 controller tolerance는 바꾸지 않았다. native 후반부 판정은 mu상대오차2e-5, curve RMSE2e-5 MPa로 고정했다. 이는 앞으로 실행할 판정 기준이지 실제 fit 성능 결과가 아니다.

결과, 환경, 고정 입력, 실패 로그, 변경별 before/after와 실제 패치 적용 검사가 서로 다른 증거임을 유지한다. 후속 Windows 실행은 기존 절대 runtime, 새 output, native_check timeout≤150s 및 exact own process/Job 정리만 사용한다. 전체 suite/FE/native/provider 캠페인을 요구하거나 수행하지 않았다.
