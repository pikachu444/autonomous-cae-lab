# Data·Material C3 — 미저장 Data의 원본까지 보관하는 Keep Recovery

요청: `PRO-DATA-MATERIAL-DELIVERY-20261015-01-C3`.

현재 main 통합에서는 원 C2의 `acknowledged_state`와 저장 후 working 보존 연결을
추가하고, 기존 canonical 소비·Plan Redo·Numerical C2 저장 관문을 유지했다.
Windows의 관련 8검사에서 미저장 원본·실제 등록 파일, 현재/Undo/Redo/run의 12개 입력,
부분 복사 실패와 손상 거절, 원 store 삭제 후 한글 경로의 별도 프로세스 읽기를 확인했다.
소유 Job은 종료했다. 이는 아래 Pro의 Linux 검사와 별도 결과이며 GUI의 Keep/닫기 연결이나
이동용 프로젝트 전체 통합 완료를 뜻하지 않는다. 현재 배정과 다음 작업은
[CURRENT_STATE](../../CURRENT_STATE.md)를 따른다.

이 전달은 C2의 불변 acknowledged base/receipt 보관에 **Data 원본 의존 파일**을 추가하는 교정이다.
새 owner, store, compiler, schema, source registry, Qt widget, 실행 관리자는 만들지 않았다.
Keep·읽기에서 save/import/apply/run/자동 원본 등록·자동 rebase를 하지 않는다.

## 적용 기준과 변경 범위

첨부 current-main 기준은 `3b52657a008f87c8ca12b04c8585b9c06c8564cc`다.
원 C2 ZIP은 `pro-data-material-delivery-20261015-01-C2.zip`, SHA-256은
`0f090293020d9798420f8f96735d9eeb66632f44b68cac4d45517c58d5753e01`이며 변경하지 않았다.
입력 C3 ZIP·파일별 출처는 `references/`와 `BASE_HASHES.json`에서 확인한다.

C3의 기존 전용 파일 변경은 다음 세 개뿐이다.

| 파일 | C3 변경 |
|---|---|
| `caelab/related_save_recovery_assets.py` | 원 Data 입력 의존 수집·원 등록 receipt/bytes와 import 결과 관계 검증 연결 |
| `caelab/related_save_recovery.py` | 원본 보존 상태 표시, 원본 미보관/없는 경우 닫기 차단, bounded source preview |
| `caelab/data_material_service.py` | 기존 dispatcher에 `recovery.source_preview` 한 항목 추가 |

신규 `caelab/data_recovery_inputs.py`가 기존 Data owner의 `_retained_source`, `resolve_input`,
`_check_source`, `resolve_job_source`와 기존 recovery manifest/preserve/verify를 재사용한다.
`DataDocuments._retain_inputs`와 동일한 현재/Undo/Redo/run 범위를 읽되 **저장 함수를 호출하지 않는다**.
추가로 원 run의 frozen source/receipt hash와 실제 `input.json` 원문 바이트를 확인한다.

**C3 추가 공통·schema·GUI 변경은 0개이므로 root 공통 patch는 없다.**
C2의 `MaterialDocuments.acknowledged_state()`와 save 후 working 인정 hook은 기존 선행 의존이다.
root가 C2를 현재 main에 통합하는 작업 위에 C3를 적용해야 한다. 오래된 cumulative C2 패치를
최신 main 전체에 무조건 재적용하라는 뜻이 아니다.

`PlanOwnerAdapter.redo`, `related_save.py`, `related_save_edits.py`, MaterialPlanPanel/RelatedSaveDialog,
RawEditorFocusGuard, Numerical candidate evidence/detail/CLI/fit_lineage/CAS, 모든 common·GUI·다른 팀 파일은
C3 패치에 없다. C2 canonical 모듈도 변경하지 않았다. 과거 overlay 전체로 최신 main을 덮지 않는다.

## 패치 적용 — 둘 중 하나

권장 경로는 `correction-C3.patch` 하나다. 이 패치에는 위 세 파일의 좁은 hunk와 신규 소스·시험·예제·문서가
있다. root가 `git apply --check correction-C3.patch`로 확인하고 적용한다. 세 기존 파일의 C2 기준 해시는
`BASE_HASHES.json`에 있다. 이미 다른 변경을 가진 파일은 hunk를 병합하며 파일 전체를 교체하지 않는다.

대안은 `overlay/`의 **신규 파일만** 추가하고 `recovery-hooks-C3.patch`를 적용하는 것이다.
이때 `correction-C3.patch`를 또 적용하면 안 된다. overlay에는 기존 common/GUI 및 기존 전용 모듈의
whole-file replacement가 없다. `references/`, `evidence/`, `validation/`는 적용 폴더가 아니다.

두 경로를 원 C2 파일 복사본에 실제 적용하여 최종 파일 바이트가 검사 소스와 같은지 확인했다.
`tools/verify_c3_delivery.py`는 배포 manifest를 읽기 전용으로 검사한다.

## 보존 계약

Keep는 원 acknowledged 문서의 현재 draft, `_undo`, `_redo`, 각 import run draft/arguments에서
Data `data_id`, mapping calibration source, acquisition channel calibration source를 추적한다.
각 source record의 `uses[].path`는 **원 acknowledged 문서 내부 위치**다. run의 frozen source/receipt
참조도 별도로 대조한다. raw editor와 `raw.local_draft`는 이 의존 목록에 섞지 않는다.

선택된 원본의 실제 source bytes와 **실제 `input.json` 원문 bytes**를 기존 `.assets` 아래에 복사한다.
등록 receipt의 name/file/created_utc/origin 등을 재생성하지 않는다. 원 id, 단위·측도·원행,
교정 recipe, 처리 결과·DAG는 바꾸지 않는다. unrelated input이나 미적용 GUI 선택은 복사하지 않는다.

기존 owner에 정확한 retained source binding이 있으면 그것을 먼저 사용한다. 바인딩·revision manifest가
깨졌다면 live 파일로 우회하지 않는다. 원 live 파일이 사라져도 저장된 동일 source/receipt로 복구할 수 있고,
live의 동일 ID가 다른 bytes로 바뀌어도 그것을 원 retained source로 채택하지 않는다.

불완전한 빈/잘못된 source identity는 원문 그대로 `UNDECLARED`/`INVALID_IDENTITY`로 보관한다.
형식상 유효하지만 한번도 실행되지 않았고 등록 위치도 없는 ID는 `UNRESOLVED_UNSUBMITTED`로 기록할 수 있다.
이 경우 raw capsule 자체는 저장해도 **source bytes가 없으므로 해당 창의 close는 false**다.
사용한 import·교정 source가 없는 경우, 알려진 hash가 맞지 않는 경우, 남아 있는 등록의 일부가 사라진 경우는
수집 실패다. 실패를 원본 보존 성공으로 표시하지 않는다. invalid draft의 보관은 평가 승인과 다르다.

prepare는 전체 원본/receipt/artifact evidence hash를 검토 응답에 묶고 execute는 같은 owner lock 아래에서
재확인한다. 부분 복사·권한·readback 실패는 해당 owner의 close를 막는다. GUI는 live raw buffer를 유지해야
한다. 다른 owner의 성공 capsule/save는 취소하지 않는다. 기존 close gate와 editor token 비교도 유지한다.

## 읽기와 resume는 다르다

기존 `recovery.inspect`/`recovery.portable_payload`에 원본 evidence가 포함된다. capsule+동명 `.assets`
폴더만 임의의 한글·공백 경로로 옮겨서 `data_recovery_inputs.inspect_capsule/resolve_source/preview_source/
read_table_source`로 읽을 수 있다. 원 store나 owner 생성, 원본 재등록이 필요 없다.

읽기는 original identity를 바꾸지 않으며 resume/discard 권한을 이식하지 않는다. 같은 store에서의
session/generation/input/content 검사와 명시 session-change 확인은 기존 C2대로다.
C2 과거 Data capsule에 원본이 없으면 base는 읽되 `LEGACY_INPUT_CLOSURE_NOT_RETAINED`로 구별한다.
현재 working이나 다른 입력을 그 원본이라고 제시하지 않는다. 새 Keep close gate도 열지 않는다.

파일 해시뿐 아니라 base identity, dependency closure, 원 receipt, frozen import claim, saved binding,
실제 input.json/source bytes 및 import 결과의 source 관계를 대조한다. Portable 외부 신뢰 기준은 성공한
Keep 응답의 `capsule_sha256`을 별도로 보관해 `expected_capsule_sha256`으로 전달할 수 있다.
이 로컬 해시 체계가 파일·해시·외부 기대값을 전부 교체하는 공격자에 대한 전자서명이라는 주장은 하지 않는다.

## 실제 실행한 좁은 동선

공개 생성 CSV 4개와 작은 교정 파일들로 실제 Workbench·Data/Material/Numerical owner·JobManager를 사용했다.
A를 import한 후 B/C/D로 편집하고 Undo하여 **현재 C / Undo A,B / Redo D / 실행 A**를 만들었다.
각 source마다 mapping 및 acquisition 교정 원본이 있어 인정된 등록은 12개다. 추가로 등록한 미적용 GUI 선택과
무관한 입력 2개는 보관하지 않는다. acquisition은 보존만 했으며 기기 수집을 실행했다고 하지 않는다.

아직 Data를 document.save하지 않은 상태에서 기존 처리 엔진으로 L0=50 mm, A0=20 mm²의 e/P11과 절대온도를
만들고 Material의 prescribed-F 측정 축·Plan의 명시 sample policy 채택/관측 입력까지 확인했다.
**Material solver, fit optimizer, candidate/detail evaluator는 새로 실행하지 않았다.**
실행한 Job은 기존 files.table import 하나이며 Keep 자체는 Job을 제출하지 않는다.

Keep 이후 live inputs/result bytes를 교체·삭제하고 원 store 전체를 제거했다. capsule와 assets만 이동해
별도 Python 프로세스에서 12개 원본·receipt, 현재/Undo/Redo/run 다섯 경로의 원 매핑, import·processing 결과,
원행 [1,2,3,4], 공칭 응력 [0,1,2,3] MPa, e=[0,.01,.02,.03], 절대온도 293.15 K 및 Material/Plan 관측 대응을 읽었다.
새 프로세스에서는 owner 생성·쓰기·Job submit을 막았고 이동 폴더의 전후 모든 파일 해시도 같았다.

변조/누락, coherent source+receipt 바꿔치기와 frozen run 불일치, prepare 후 변경, saved fallback 변조,
캡슐 재봉인 후 closure·claim·path 변조, 부분 복사/readback 실패, 미적용 buffer 분리 및 resume/store gate를 검사했다.
이는 저장/원자료 재읽기 계약 검사이며 물성·해석 수치 benchmark나 공학 release 판정이 아니다.

## 검사 실행과 한계

`python -m pytest tests/data_material_c3 -q`가 C3 전용 검사다.
기존 C1/C2 raw recovery·관련 save 검사를 함께 실행한 명령과 결과는 `validation-summary.json` 및 JUnit에 있다.
의도적으로 실제 Material evaluate 한 검사는 선택하지 않았다. native/solver/GUI 캠페인을 시작하지 않았다.

첨부는 최신 파일 부분집합이므로 검사 의존성은 이전 첨부의 실제 소스와 C2의 기존 공통 hook을 조합했다.
이번 C3 변경을 전체 current-main 회귀 검사로 표시하지 않는다. current-main에 아직 없는 C2 canonical 함수 때문에
넓은 consumer 시험의 수집을 한번 중단한 기록도 남겼다. 이를 통과로 세지 않는다. 별도 검사 복사본에서
**변경하지 않은 C2 Data compiler 두 파일**을 사용하여 C3 37개 동선도 재확인했다. Numerical 파일은 수정하지 않았다.

실행 환경은 Linux Python 3.13.5이다. Windows Python 3.12/Qt/WSL/native/FELUPE와 전체 engineering qualification은
이번 C3에서 실행하지 않았다. 사용자가 보고한 기존 Windows C2 통과 수를 합산하지 않는다.
root의 C2 통합 및 Sol의 실제 Windows Keep/실패/닫기/재열기 인수 동선은 남아 있으며 전체 인도 완료가 아니다.
