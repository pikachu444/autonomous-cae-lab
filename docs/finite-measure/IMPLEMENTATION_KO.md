# 유한변형 시험 관측 구현 인도

요청 `PRO-FINITE-MEASURE-20261015-01`. 기준은 공개 Git `d5d5eafcc0220adaf9f6130ce6b7df51e2a5413e`, upstream pin `3e48bf6138f495299f45b1af254bfb4aaff307b8`의 775개 source 파일이다. 첨부 ZIP은 5,275,101 bytes, SHA256 `c6c839b429f515bfb6f729713ed118edf746fd5ac68ac9a67b479c9cc042173b`이며 원본 크기·SHA256·CRC를 확인했다. 작업트리 overlay는 없다. 이후 main 및 B13/S2/Contact/C3B/Data·Runner WIP를 가져오거나 덮어쓰지 않았다.

## 확정한 연결

관측은 기존 Data recipe에 `finite_observation` 단계를 추가해 계산한다. 같은 sample DAG에 원본 채널·단위·원행·시간과 재실행 가능한 비선형 식을 보존한다. `NONLINEAR_EXACT`는 식과 원 입력 의존성을 검증할 수 있다는 뜻이며 affine coefficient, Jacobian, 공분산 전파 계수를 뜻하지 않는다. 원 채널과 파생 관측은 분리한다. 원행 품질·연산 유효성·계산 mask·표시 숨김을 각각 유지한다.

예측은 원 Material 결과와 원 PK1 응답을 변경하지 않고 `finite_Cauchy` 응답을 파생한다. 후보별 실제 `constitutive_increments`의 F/P·시간·수락/commit·원 residual/tolerance를 검증하고 `sigma=P@F.T/det(F)`를 계산한다. 관측 J와 prescribed F는 이 변환의 입력으로 받지 않는다. 기존 `_aligned`의 동일 측도/frame/component/unit/time support 검사는 그대로이다. 실패한 결과의 prefix는 읽기 전용 진단으로만 변환할 수 있고 피팅 성공값으로 채점하지 않는다.

유한 측정 driver는 기존 `material_control.uniaxial_settings` 및 mixed controller로 컴파일한다. 자유 횡수축, 고정, 지정 신장비를 명시 선택한다. 기존 analytic/native tangent, 수렴 tolerance, accepted state와 optimizer는 수정하지 않았다. 새로운 owner/store/controller/optimizer/framework는 만들지 않았다.

기존 Data 저장·processing revision·canonical inclusion·Plan policy·candidate detail/evidence·CAS 채택을 소비한다. 공유 파일 전체본은 인도에 포함하지 않고 `integration.patch`로만 제공한다. 전용 신규 파일과 허용된 두 전용 기존 파일은 `product.patch` 및 `source/`에 있다.

## 실제 확인된 범위

최종 실행은 `evidence/case-r07/`이다. 실제 Workbench/Data owner에서 두 CSV를 가져오고 유한변환 결과를 명시 보존했다. 실제 Material 초안과 같은 Numerical Plan에 독립 train/holdout·원행 mask/weight·canonical frozen 관측을 구성하고 저장했다. 이후 기존 Workbench의 실제 `inputs`, `jobs`, `results` 경로를 격리하고 별도 Python 프로세스의 새 owner에서 같은 자료·관측·초안·frozen input을 읽었다. 이 읽기가 생성한 job은 0이다. 현재 Data 초안에 `1e`를 저장하고 무효행과 원 이유를 확인한 뒤 50 mm로 수정·저장했다. 과거 처리 결과 파일 SHA와 물리 내용은 바뀌지 않았다.

최종 관련 검사: **35 passed, 1 skipped, 1 deselected**. 변경 Python 28개 AST 검사 PASS. 이 중 예측 수학·accepted-state 테스트는 명시한 계약 fixture 검사이며 실제 FELUPE 해석으로 계산한 결과가 아니다.

이 컨테이너에는 FELUPE와 PySide6가 없다. 실제 adapter 준비는 `CapabilityUnavailable: FELUPE runtime unavailable; no alternate law is substituted`를 반환했다. 설치·다운로드·업그레이드·유료 호출은 0이다. **실제 Neo 예측 → fit → 보존 후보 비교/상세 → 명시 CAS 채택은 NOT_RUN**이다. 그 경로의 제품 연결 코드와 실제 owner API를 호출하는 runnable은 작성했지만 이 환경에서 후반부를 실행 검증하지 못했다. 임의 함수나 fake backend로 대체하지 않았다. Qt offscreen도 미실행이며 Windows 실창은 NOT_RUN이다.

따라서 이번 인도를 전체 FM01–09 완료라고 표시하지 않는다. 전체 B4, 다른 법칙/FE pair, 실측 재료 식별성·강도·engineering release도 완료로 변경하지 않는다.

## 기록의 정정

중간 인도 이후 실제 경로 격리 검사와 전달 문서를 보완했다. r05에서는 격리 대상 경로를 Workbench root보다 한 단계 위로 잡아 실제 폴더를 옮기지 않았다. r05의 Data/Plan/cold 성공 자체는 남지만 입력 경로 독립성의 증거로 사용하지 않는다. r06/r07은 실제 `store/workbench/{inputs,jobs,results}`를 격리하고 확인했다. r07의 격리 파일 수는 각각 4/2/22개이며 `quarantine.json`에 기록되어 있다.

중간 ZIP의 README가 가리킨 상세 구현 문서가 중간 ZIP에 빠졌던 것도 최종 인도에서 교정했다. 중간 ZIP을 조용히 교체하지 않았으며 최종 ZIP의 patch/source가 최신 인도다. 앞선 실패 로그는 `ACCEPTANCE_KO.md`에 원인·교정과 함께 남겼다.

API와 경계는 `API_KO.md`, 사용자 작업 및 재실행은 `USAGE_KO.md`, 실제 검사 및 남은 수용은 `ACCEPTANCE_KO.md`를 따른다.
