# Portable C2 — 원실행을 바꾸지 않는 작업 사본

요청 `PRO-PORTABLE-CONNECTION-20261015-C2`. C1의 saved base / acknowledged draft / Undo / typed 관계 편집 / 프로젝트 배치를 유지한 수정이다. 새 store, owner, coordinator, solver, provider, HTTP endpoint를 만들지 않는다. 실제 제품 저장은 기존 Data·Material·Numerical owner가 담당한다.

## 적용

기준은 요청 패킷 `SOURCE_MANIFEST.json`의 **86bc7db1cbe61060e7db98795a87c9f9aa37fc34 + C1 전용28 WIP**다. Windows RED 재현의 `2fea93f...` 또는 C1의 오래된 SOURCE_BASE가 적용 기준은 아니다.

1. 원자료와 원 C1을 보존한다. 정확한 패킷 `source/`를 별도 검사 폴더로 복사한다.
2. 그 폴더에서 `product.patch`를 적용한다. 전용 수정·새 파일만 포함한다.
3. `integration.patch`를 적용한다. **패킷에 아직 미적용인 원 C1 common5 제안과 C2 Numerical 최소 hunk를 합친 패치**다. `original-c1/integration.patch`를 다시 중복 적용하지 않는다. root가 원 common5를 이미 통합했다면 함께 제공한 `integration-c2-only.patch`만 추가한다. 세 patch의 기준은 인도 SOURCE_MANIFEST를 따른다. concurrent root 파일 전체를 교체하지 않는다.

```powershell
git apply --check product.patch
git apply product.patch
git apply --check integration.patch
git apply integration.patch
```

`source-dedicated.zip`은 전용 소스의 실제 파일이다. 공유 Workbench/HTTP/Client/desktop/native/Numerical 파일 전체를 넣지 않았다. 기존 Qt 창과 Codex의 두 표시 교정은 보존했다.

## 사용자 순서

기존 연결 창에서 실제 문서들을 선택하고 **작업 초안 포함**으로 파일 목록을 확인한 뒤 새 폴더 사본을 만든다. Data 원자료가 필요한 Plan은 해당 Data 문서, Material binding은 해당 Material을 함께 선택한다. 저장 개정과 acknowledged 초안은 별개이며, 원문서 저장·적용·재계산은 일어나지 않는다. raw widget의 아직 acknowledged되지 않은 `1e`/blank 버퍼는 이 사본의 대상이라고 표시하지 않는다. C01 capsule은 **NOT_INTEGRATED**다.

한글·공백 경로로 사본 폴더 전체를 옮긴 다음 기존 독립 도구로 연다. 원 보관소/등록 원자료 위치가 없어도 기존 owner가 편집·Undo·명시 저장을 수행한다. 새 문서 ID는 사본 편집/탐색 identity이고, 결과 안 원입력·원실행 identity는 그대로다. 이를 덮어써 맞추지 않는다.

원 CAPTURE가 저장 실패 뒤 REGISTERED에 머문 경우도 acknowledged 증거 파일을 포함한다. 사본에서 `document.save`를 명시하면 기존 Numerical savehook가 실제 retained evidence로 보존한다. 저장 개정의 해당 증거를 읽거나, 현재 session/generation으로 새 `numerical.evidence.capture`를 명시한다. **옛 command_id/session/approval의 자동 재실행은 없다.** 원 pending/completed journal과 publication witness는 이력으로 보존하며 사본 `commands/`의 실행 권한으로 설치하지 않는다.

후보 상세는 원 frozen 입력, 원값, 변수 범위, 단위, 원 trial/실패, 명시 선택한 attempt로 읽는다. 사본 현 Data/Material 값으로 새 곡선을 만들어 통과시키지 않는다. 이미 완료된 상세를 선택하고 기존 보존 명령을 사용한 다음 기존 Report owner의 capture/save, 비교, 명시 후보 채택으로 진행한다. 채택은 기존 target owner의 input/generation CAS와 수치팀의 모든 fit/holdout 증거 gate를 그대로 통과해야 한다. source나 target이 편집돼 낡은 선택이면 거절하며, 원문서에서 새 선택/명시 승인으로 다시 진행한다.

상세가 원래 보존되지 않은 성공 후보는 **상세 미보존** 상태다. 그 상태는 성공 판단도 실패 진단도 아니다. 메타데이터 보고만 가능하며, 실제 원실패가 있는 별도 후보만 failure diagnostic으로 보존·보고한다. 실패 증거는 채택을 승인하지 않는다. `holdout_acceptance=NOT_ASSESSED`, `engineering_release=NOT_RELEASED`는 계산 성공과 별개다.

현재 사본에서 저장한 보고서는 같은 프로젝트를 다시 열어 읽을 수 있다. **새 작업 사본 생성**의 선택 범위는 기존 Data/Material/Numerical 문서이며, 별도 Report 문서를 몰래 포함한다고 주장하지 않는다. 선택한 Material의 adoption 안에 있는 정확 candidate-evidence ref는 재복사 때 함께 대응한다. 일반 폴더 이동은 그 프로젝트 안에 이미 생성한 보고서 파일도 그대로 이동한다.

## 파일·권한 경계

로컬 작업 사본에는 사용자가 선택한 개인/회사 공학 자료도 정상 포함할 수 있다. 이 인도 ZIP만 공개 합성 자료다. 로컬 checkbox는 공개자료 선언이 아니라 포함 문서·보존 파일 목록 확인이다. 계정, 자격증명, 환경설정, QSettings, 인접 폴더를 자동 수집하지 않는다. 외부 전송 기능을 추가하지 않았다.

원 저장 개정과 acknowledged snapshot은 `portable/originals/`에 byte-exact로 남는다. 정상 편집본은 기존 `workbench/documents/`에 놓인다. `portable_execution/`은 기존 Numerical revision manifest에 등록되는 원 input/job bytes 및 typed 대응 증거다. 다른 store로 우회하는 경로가 없고, 결과 배열/CSV를 HTTP request body에 넣지 않는다.

일반 JSON command **128 KiB**, upload **16 MiB**, portable-create metadata **8 MiB** 한도는 그대로다. 큰 CSV는 허용된 local root에서 기존 등록 기능으로 선택하고, 서버가 이미 보존한 파일을 직접 복사한다. 파일/JSON 형식별 기존 local 읽기 한도도 유지한다. 전체 사본20 GiB/100000 files 한도 캠페인은 실시하지 않았다. proof 자산 증가도 최종 stage inventory 검사를 통과해야 목적지가 발행된다.

누락·해시 불일치·잘못된 raw ZIP 이름·일관되지 않은 receipt/reference는 발행 전에 원인/위치와 함께 거절한다. 원본이나 기존 사본을 덮지 않는다. 불완전 발행은 `.incomplete.json`으로 표시하며 정상 완료로 열지 않는다. 복구는 원래 동일 bytes를 지정하는 기존 명시 복구 방식이다.

**이미 생성된 구 C1 실패 사본**에는 이 C2가 요구하는 원 input/job 증거가 없을 수 있다. 추정 복구·hash 재작성으로 승격하지 않는다. 요청 패킷에 보존된 원 store에서 새 C2 사본을 만든다. 기존 실패 사본과 원 RED 기록은 유지한다.

## 공개 검사 재현

아래 첫 예제는 합성 fixture 생성 단계에서만 기존 공개 대수 evaluator를 실행한다. 이후 source rename/cold 단계에서는 기존 tripwire가 evaluator·Job·DAG dispatch를 차단한다. 물리 solver나 provider 실행이 아니다. 원본을 삭제하지 않고 다른 이름으로 보존한다.

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:C2_PUBLIC_PACKET = 'D:\공개 패킷\portable-c2'
python -m pytest -q tests/test_portable_execution_c2.py tests/test_portable_execution_supplied_c2.py --junitxml=portable-c2.xml
python -m examples.portable_connection_c2_public --output 'D:\공개 검사\새 C2 인도'
```

예제는 Numerical 팀의 정확한 fixture helper와 기존 pytest 개발 의존성을 재사용한다. 설치·다운로드하지 않는다. 사용자 일반 앱 실행에는 pytest나 fixture evaluator가 필요하지 않다. 새 명시 계산/새 mixed-origin attempt를 추가하는 실행 캠페인, Windows native/실제 Qt/OS mouse 동선은 이 read/save/consumer 검사에서 실행하지 않았다. 미실행을 성공으로 해석하지 않는다.
