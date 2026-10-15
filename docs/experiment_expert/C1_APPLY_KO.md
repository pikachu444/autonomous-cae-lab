# FN05 C1 적용 안내 — root/Codex용

## 기준과 변경 범위

원 FN05 ZIP의 SHA256은 `a252a7a516312ee60f8fcca0f91704476e6a97e12c138226bb75131ffcf5cdd8`이다. 이 원 ZIP은 변경하지 않았다. 교정의 API 기준은 첨부 `CURRENT_PUBLIC_C2_CONSUMER_SOURCE.zip` 및 `SOURCE_MANIFEST_C1.json`의 공개 commit `910380d0b2027023f5f6c1260d729c6336e4a779`와 사용자가 추가 제공한 sample policy bridge이다. 최신 미게시 root 상태에 무충돌 적용됐다고 주장하지 않는다.

`product.patch`는 원 FN05 전용 네 모듈, 관련 시험 fixture/회귀, C1 문서의 **증분**이다. 신규 전체 engine/schema/store/backend/scheduler가 없다. `source/`는 검토할 완성 전용 파일과 관련 검사의 사본이다. 패치와 source 전체 복사를 중복 적용하지 않는다.

제품 변경 파일은 `caelab/experiment_uncertainty.py`, `experiment_final_diagnosis.py`, `experiment_analysis_service.py`, `experiment_analysis_reporting.py`이다. 공통 제품 `integration.patch`는 **필요 없으며 포함하지 않았다**. 원 전체 ZIP의 공통 패치를 다시 적용하라는 요청도 아니다.

## 적용 순서

1. root가 이미 통합한 원 FN05의 Core/Plan/Report 연결, Data C2 canonical consumer/운반, Numerical C2 evidence owner/savehook, sample policy preview/adopt와 공개 dispatch가 존재하는지 확인한다. `NumericalDocuments`에는 현재 `CandidateDetailMixin`이 이미 있다. 테스트에서 이를 다시 상속하지 않는다.
2. 패킷 폴더에서 `python verify_package.py`로 인도 파일 무결성을 검사한다. `python check_target.py <현재 작업 사본>`은 변경 대상 전용 파일의 원 내용만 읽어 대조한다. Windows CRLF는 내용 비교에서 정규화하지만 실제 소스를 수정하지 않는다. 다른 팀 변경이 겹치면 자동 전체 교체하지 말고 이 증분의 해당 hunk만 root가 병합한다.
3. root 작업 사본에서 `git apply --check <패킷>/product.patch`로 확인한 뒤 같은 패치를 한 번 적용한다. `git apply --check`가 실패하면 오래된 전체 파일을 덮지 않는다. `source/`와 diff를 대조해 전용 변경만 반영한다.
4. 현재 체크아웃에서 `python <패킷>/run_regressions.py --repo <현재 작업 사본> --output <새 검사 폴더>`를 실행한다. 이 명령은 명시된 FN05 회귀만 실행하고 package 설치, 네트워크, native/provider 호출을 하지 않는다. pytest/NumPy/SciPy/jsonschema 등 기존 시험 의존성이 필요하다. 테스트 evaluator는 고유한 `test.fn05.c1.synthetic` 등록이며 `material.felupe`를 대체하지 않는다.
5. Astra는 관련 principal block의 정확성, canonical/legacy 분리 및 source/weights 결합을 독립 검토한다. Windows Qt 인수는 Sol/root의 실제 환경에서 별도로 수행한다. 이 패킷은 그 검토나 실행을 대신 완료했다고 표시하지 않는다.

## 다른 작성자의 파일을 보존한다

Data C2의 `data_processing_consumer/lineage/selection`, `data_material_service`, Numerical의 `numerical.py`, candidate detail/evidence/fit_lineage/document, identification 공통, 현재775 교정, Expert 부분응답, Report/Study owner, 모든 GUI 파일은 제품 패치 대상이 아니다. 사용자가 제공한 policy bridge는 다시 작성하지 않았다. 실제 공개 API로 미리보기·채택한 command receipt를 회귀에서 읽어 확인한다.

## 시험 사본의 조립과 적용 검증의 의미

첨부 current-source는 전체 앱이 아닌 공개 allowlist다. 이번 Linux 시험 사본은 앞서 첨부한 35a91ed baseline과 원 FN05, 제공된 Data/Numerical 참고 모듈에 최신 current-main allowlist를 덮어 대조했다. current allowlist에는 원 FN05 연결 일부가 없어 **이미 제출한 원 FN05 연결만** 시험 사본에 재조합했다. 누락된 DataDocuments/MaterialDocuments는 같은 공개 910380d commit을 읽어 실제 Git blob와 일치시켰다. 이 두 파일은 새 구현도 이번 제품 교체본도 아니다. 정확한 입력·시험 소스 hash는 `verification/LOCAL_ASSEMBLY_MANIFEST.json`에 있다.

시험의 Workbench 초기 생성은 native Pre 생성자 의존 파일이 없는 묶음 특성 때문에 `Workbench.__new__`로 구성한다. 이후 현재 실제 Workbench 메서드, Data/Material/Numerical/Study/Report owner, JobManager, C2 consumer/CAS, SciPy fit/detail/J 경로를 실행한다. Data/Numerical compiler, policy 수학, evidence 승인 및 결과 저장을 시험 대역으로 바꾸지 않는다. 전체 Workbench GUI 기동이나 native 앱 실행과는 다르다.

깨끗한 적용 검사는 이 시험 사본에서 대상 전용 파일을 원 ZIP 내용으로 되돌린 새 사본에 `product.patch`를 적용하여 수행한다. 반환 source와 적용 결과의 파일 hash를 대조하고 그 새 사본에서 회귀를 실행한다. 사용자 root의 미게시 공통 통합본 전체가 검사됐다는 뜻은 아니다.
