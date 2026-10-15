# 적용 순서와 파일 소유 — Codex/root 인계

## 원본 기준

`BASELINE_MANIFEST.json`의 공개 baseline:
`35a91ed5d882d63e83118e79e55844083eb7f093`.
입력 ZIP SHA256: `fc9e741d21e794ce48c6ace743ee8d165c9ccb19ebbf7ddeffabd7f878d042d1`.
제공 manifest 442개 항목의 바이트 수/SHA256을 대조했다. 이 패킷은 현재 main
전체 checkout 또는 다른 팀의 작업 폴더가 아니다.

main26cf041의 Plan 원문 복구 위젯, NS2/N3, M4, Data/Numerical C2, Sol의
expert_partial_responses/Expert/Study/Report 창은 전체 교체하지 않는다.
보호 파일 목록/기준 hash와 인도 파일 목록은 최종 MANIFEST.json에 있다.

## 적용

1. 현재 root 통합 브랜치를 보존한 별도 작업 사본에서 적용한다. `product.patch`는
   신규 전용 파일만 추가한다. 동등한 `source/` overlay 복사와 **둘 다 적용하지 않는다**.
2. `integration.patch`는 기존 Core/Plan/report/Co-STORM 여섯 파일의 필요한 국부
   연결만 담는다. 첨부 baseline에 대한 `git apply --check`와 실제 적용을 검사했다.
   현재 main/미게시 C2에 무충돌이라는 주장은 아니다. 충돌은 해당 hunk만 root가 합친다.
3. `gui-integration.patch`는 Data 메뉴, Numerical의 저장 Plan 열기, Report 페이지
   dispatcher의 세 파일에만 적용한다. request_plan_window.py 또는 Plan 복구
   위젯을 바꾸지 않는다. 전체 UI 파일 대체는 금지한다.
4. `candidate-gui-C1.patch`는 제공 Numerical C1의 전용 상세 창에 대한 **선택적 2줄
   연결**이다. 그 실제 파일이 현재 통합본에 있을 때만 Sol/root가 hunk를 합친다.
   기존 C1 전체 integration.patch를 다시 적용하라는 뜻이 아니다.
5. 실제 Data C1 owner processing preview/apply/result/retain 및 기존 authenticated
   `/api/workbench/data-material` 읽기 route, Numerical C1 CandidateDetailMixin와
   evidence read/capture/resolve가 먼저 해당 팀의 코드로 연결되어야 한다.
   최신 C2 교정은 해당 팀의 최종 반환본을 root가 합친다. 이 패킷에는 그 교정을
   복제하거나 대신하는 Data/Numerical producer/CAS 파일이 없다.
6. 검사: `python -m pytest -q tests/experiment_expert`.
   첨부의 부분 baseline을 사용하는 검증 사본에서는
   `CAELAB_CONTRACT_ROOT=<추출한 references 경로>`를 환경변수로 지정한다.
   PowerShell은 `$env:CAELAB_CONTRACT_ROOT='...\references'` 형식이다.
   테스트의 C1 모듈 경로 추가는 명시된 공개 계약용이며 설치된 제품 코드보다
   우선하지 않는다. 제품 실행 시 이 테스트용 환경변수를 필요조건으로 만들지 않는다.

## 패치 내용

| 패치 | 기존 파일 | 연결 이유 |
|---|---|---|
| integration.patch | caelab/workbench.py | 새 두 **명시 operation**의 기존 Plan/JobManager dispatch·read-only preview·재검증·report 소비 gate |
| 동일 | caelab/assist/experts.py | 기존 Request Plan schema에 두 operation 등록. provider 설정 불변 |
| 동일 | caelab/desktop_links.py | 기존 정확 result→Plan 생성 receipt를 재사용; 원 결과/처리 개정 연결 검증 |
| 동일 | caelab/report_document.py | compact payload에 새 분석의 보존 상세 포함 |
| 동일 | caelab/research_workflows.py | 새 분석 report의 full 검증 배열을 사용, data_ref 주소만 동결하던 누락 방지 |
| 동일 | caelab/assist/costorm.py | 새 시험 분석이 formatter word limit에서 통째로 누락되지 않도록 bounded read summary |
| gui-integration.patch | apps/research/data_window.py | 현재 선택 원 시험의 메뉴 연결, 늦은 다른 선택 응답 차단 |
| 동일 | apps/research/numerical_window.py | 저장한 새 분석 Plan을 전용 창으로 열기 |
| 동일 | apps/research/report_pages.py | 기존 Report의 한글 표·곡선 renderer 연결 |
| candidate-gui-C1.patch | apps/research/numerical_candidate_detail_window.py | 정확 immutable evidence ref에서 전용 최종점 창 열기 |

## 다른 팀과의 경계

Data/Numerical C1은 **회수 reference**이지 C2 통합 완료본이 아니다. 제공 C1
Numerical integration.patch는 이전 overlay를 전제로 하므로 baseline35a91ed에
그대로 적용되지 않는다. 검증에서는 실제 제공 전용 모듈과 기존 owner를 명시적으로
조합했다. absent shared hooks의 시험용 조합은 `tests/experiment_expert/support.py`,
`test_processing_source.py`에 표시되어 있다. 이를 C2 CAS 수용으로 세지 않는다.

이번 패킷은 canonical 운반 adapter를 재작성하지 않는다. C2가 동결한 실제
`frozen-fit-inclusion.v1`를 현재 snapshot에 운반한 뒤 기존 consumer가 승인하는지
root에서 인수한다. 운반이 없으면 derived J는 차단되고 원자료·요약 읽기는 유지된다.

추가 실환경 인수: 두 Qt 크기의 메뉴/키보드/닫기/취소/미확정 재시도, 실제 Windows
지원 evaluator와 통합 HTTP 경로, C2 CAS/채택/상세 소비, 실제 provider가 허용된
운영 환경의 별도 검증. 이번 실행 결과로 대신하지 않는다.
