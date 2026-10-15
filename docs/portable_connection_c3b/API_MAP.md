# C3B-R1 실제 API 및 GUI 연결

## 기존 공개 command 유지

| 경로 | 입력/동작 | 이번 실제 연결 |
|---|---|---|
| Workbench/Client.portable_inspect | selections, draft_policy, recovery_archives | Report B 포함. 선택한 Report의 saved/current/Undo/Redo asset 및 원 owner archive closure 검증 |
| Workbench/Client.portable_create | inspection, destination, approved, command_id, session_id | 기존 CAS/pin/stage/last manifest/재확인. Report current projection과 원 raw 자료 분리 |
| portable_verify / verify_project | exact folder | 원 inventory 및 현재 Report retained proof/owner history 검증. 실행 없음 |
| open_project | exact folder | 기존 Workbench/Report owner open. 반환한 Workbench는 호출자가 finally shutdown |
| document_open/read/command | 기존 B ID/session/generation | report.update, document.undo/redo/save 그대로. 새 operation 없음 |
| report_content | document_id, bindings | 원 frozen content와 별도 current navigation 결과. A hash/PNG 검증 유지 |
| report_capture | document_id, exact reference | 기존 명시 새 capture만. 원 A를 변경하는 copy hook이 아님 |
| portable_recovery_catalog | exact document_ids | 실제 Report는 Q 없는 문서로 확인. 다른 Data/Material/Numerical Q 계약 그대로 |

HTTP 경로도 기존 `/api/workbench/portable-project/...`, `/api/workbench/report-content` 등 dispatcher를 그대로 쓴다. routes/Client/schema를 새로 만들거나 요청 한도를 늘리지 않는다. 정확한 실제 route 이름은 이 기준의 `apps/lab/workbench_routes.py`와 Client 함수 원문이 권위다.

## report_content의 추가 읽기 필드

`reference`와 `content`는 frozen 원값이다. 사본의 원문을 현재 input ID로 다시 쓰지 않는다.

| 필드 | 의미 |
|---|---|
| source_status | AVAILABLE은 현재 명시 typed source 내용까지 대조 성공. UNAVAILABLE은 원 frozen 보존본과 구별되는 탐색 부재/오류 |
| snapshot_status=AVAILABLE | A/원 raw archive/증명/필요한 PNG 검증 성공 |
| navigation_reference | 현재 사본에 검증된 document/result exact reference. 포함하지 않은 source/native는 null |
| navigation_status | VERIFIED_TYPED_SOURCE, FROZEN_ONLY 또는 현재 원자료 검증 실패의 SOURCE_UNAVAILABLE. 마지막 경우 navigation_reference는 null이며 보존본은 계속 읽고 원자료 열기는 재확인으로 돌아감. 원 실패를 새 계산 성공으로 표시하는 상태가 아님 |
| origin_authority=HISTORY_ONLY | 원 실행/원 경로/원 세션은 provenance이며 현재 권한이 아님 |

검증 불가/자산 유실이면 기존 Report content의 `source_status=SNAPSHOT_UNAVAILABLE` 오류 응답을 유지한다. 그 응답에는 존재하지 않는 content/PNG를 넣지 않는다. 원문 조회 실패와 현재 source unavailable를 혼동하지 않는다.

## 전용 helper

`portable_project_report.py`: bindings/asset_name, project_reference/can_navigate, collect_working, inspect_document, write_revision, replay/replay_owner, declared_refs/owner_refs, retain/retain_owner_history/install_working, content/verify_current. 모두 기존 Report 저장 경로 또는 portable exact revision 안에서만 작동한다. 공개 일반 controller/owner API를 추가한 것이 아니다.

원 owner archive schema, section navigation schema, owner history schema는 OWNER_CONTRACT.md에 설명한다. 내부 파일/hash는 GUI 기술 상세/검증용이며 주 작업 화면의 편집 형식이 아니다.

## GUI 데이터·오류·late reply

ReportWindow.prepare_portable_copy → busy/pending 차단 → 기존 local editor 명시 Apply 또는 Save/Cancel → 기존 ConnectionWindow(client, document_id=현재 B). 이후 기존 선택/검토/copy command를 사용한다. ConnectionWindow는 Report 포함 안내만 보강했다.

ReportWindow.open_source는 report_content의 navigation_reference를 소비한다. copied marker가 있는데 새 조회가 없거나 retained_preview_only이면 원 경로를 열지 않고 기존 read_assets로 돌아간다. null이면 frozen 자료만 보여준다. 기존 retry가 보낸 draft와 현재 draft를 비교하는 late-reply 보호는 변경하지 않았으며 Python 경계 회귀를 실행했다.

## 구현하지 않은 API

Study/Expert/knowledge local-scope, PDE/Simulation/Evaluation 원 execution adapter, managed native selection/relocation/current opener, Report comparison/candidate 전용 current navigation에는 새 임시 API/성공 stub를 만들지 않았다. 미지원 owner는 기존 검사에서 거절된다. knowledge Report는 명시 scope 오류로 중단한다. 세부 상태는 ACCEPTANCE_STATUS.md를 따른다.
