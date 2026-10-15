> C1 기록은 아래에 보존합니다. 현재 C2 추가 내용은 [C2_OWNER_CONTRACT.md](C2_OWNER_CONTRACT.md)을 참조하세요.

# C1 공통 owner·연결 계약

이 문서는 `PRO-PORTABLE-CONNECTION-20261015-C1`의 **실제 코드 경계**다. 최초 문서는 `history/PRE_C1_OWNER_CONTRACT.md`에 보존했다. C1 입력은 tested fbcfb37 + Pro 전용 코드 + 검사폴더의 최초 common4 + Windows 문구/fixture 교정이다. main 공통 문맥은 첨부 `current-common-context`이며 커밋 표기는 `1e3025f565c2246c2746c8cedd300f95e21e0408`이다. `SOURCE_BASE`의 90d/dynamic 라벨을 실제 적용 기준으로 사용하지 않는다.

## 소유·적용

전용 파일은 portable_project*, connection_graph*, connection_window*와 전용 tests/examples/docs다. domain owner, schema, storage, registry, 다른 팀 GUI, `current-wip`는 수정하지 않는다. `integration.patch`만 workbench/client/routes/desktop/native_commands를 변경한다. 첨부 공통 문맥에 최초 overlay와 C1 증분을 순서대로 실제 적용해 만들었고 CRLF를 보존했다. 전체 공유 파일을 덮어쓰지 않는다.

`native_commands`의 6개 M4 operation 등록 문자열은 그대로다. attachment에 누락된 `assembly_pose_candidate.py`를 capability 조회 때 eager import하지 않도록 정확한 여섯 이름의 상수만 남긴 좁은 import 경계 교정이 있다. pinned 공개 원본의 `OPERATIONS`와 current-main import hunk를 조회해 대조했다. M4 implementation을 만들거나 native activation을 검증한 변경이 아니다. 공개 조회 출처와 blob 값은 인도 `SOURCE_MANIFEST.json`에 기록한다.

## 세 개의 입력 층

1. **SAVED**: 실제 owner가 저장한 base/이전 개정. 기존 pointer/revision 검증과 원본 파일을 보존한다.
2. **ACKNOWLEDGED_WORKING**: owner가 명령으로 받아들인 현재 draft, generation/input_revision, Undo/Redo, 결과 이력을 가진 별도 스냅샷. 사본의 실제 `working.json`으로 복원한다. 사용자 저장을 호출하지 않는다.
3. **ACKNOWLEDGED_INPUT**: 다른 문서의 이력이 가리키는 이전 acknowledged Material 입력. 기존 owner의 완료 command response 또는 이전 portable의 검증된 보존 컨테이너에 exact doc/input revision/generation/draft 증거가 있을 때만 채택한다. draft 내용이 같다는 이유로 입력 ID를 추측하지 않는다. 이는 옛 전체 작업 문서라는 주장이 아니라 정확한 이전 입력의 증거다.

`portable_snapshot.container_revision`이 해당 컨테이너 revision과 같고 layer가 ACKNOWLEDGED_*일 때만 저장본 선택에서 제외한다. 실제 owner가 나중에 새 R로 저장하면 정상 SAVED 개정이다. 표시 필드만 남았다고 영원히 초안으로 오판하지 않는다. 저장 개정과 초안 보존 컨테이너를 같은 saved reference로 노출하지 않는다.

열린 owner의 raw 메모리 상태와 디스크 `working.json`은 저장 직후 다를 수 있다. 현재 실제 acknowledged 상태는 snapshot bytes로, 디스크 복구 파일은 `owner-working.json` 원본 bytes로 **별도** 보존한다. 원 완료 receipt는 `owner-receipt.json` 증거로만 보존한다. 사본의 commands 디렉터리에 재실행 가능한 receipt로 복원하지 않는다. 새 jobs/provider/입력 registry를 재구성하지 않는다.

## 복사 계약

`inspect_copy(wb, selections, draft_policy='acknowledged')`가 기본이다. `saved_only`만 명시적으로 초안 제외를 허용한다. 기본 흐름에서는 선택한 저장 base가 현재 head와 같아야 한다. saved head가 없는 실제 acknowledged-only 문서도 포함할 수 있다. typed 의존의 saved ref와 current/history draft ref를 각각 검증한다.

Data의 현재 입력, Undo/Redo, 실제 run 입력, calibration에 명시된 data_id만 사용한다. 기존 owner의 retained source/result helper와 register된 local root를 사용한다. 이력 입력이 누락되거나 다른 문서가 선택되지 않으면 위치/회복 방법을 반환하고 발행하지 않는다. unretained completed CSV run은 실제 JobManager 기록의 document/operation/arguments와 원입력을 대조하고 소유 결과/실패 파일만 보존한다. 진행 중/미확정 run은 차단한다.

원 저장 개정·원 acknowledged snapshot·정확 receipt·원자료·원 성공/실패 결과는 `portable/originals`에 byte-identical하게 보존한다. 새 owner용 projected 개정의 알려진 typed refs와 검사 metadata만 새 문서/개정/입력 ID에 맞춘다. Units/UNKNOWN/invalid/알 수 없는 필드의 의미나 값은 임의 정규화하지 않는다. result body bytes는 원본이다. projected input hash가 다를 수 있으며 원input snapshot과 `portable_origin`으로 원실행을 구별한다.

```text
portable-project.json
portable/originals/<old doc>/<old R or acknowledged or acknowledged-input-I...>/
portable/originals/connection-view.json             # view가 존재하면 원 bytes 보존
workbench/documents/<new doc>/document.json         # 실제 저장 head가 있는 경우
workbench/documents/<new doc>/working.json          # acknowledged 포함 시
workbench/documents/<new doc>/revisions/<new R>/... # SAVED와 구별된 retained containers 포함
workbench/views/connection.json                    # 선택적, 이동 가능한 versioned view
```

owner fingerprint는 saved base와 dirty draft를 구분한다. 검사 token은 full raw acknowledged 상태(Undo/Redo 포함), generation/input, saved pointer, 명시 파일 및 view 상태를 고정한다. create 직전 다시 검사하며 기존 owner locks를 재사용한다. 다른 owner lock을 이미 잡은 뒤 무기한 대기하지 않고 OWNER_BUSY로 실패해 기존 Numerical→Material 잠금 순서와 역전 교착을 피한다. 실패 시 선택/원본은 남고 폴더 overwrite는 없다. 기존 staging, 배타적 목적지 발행, manifest-last, incomplete marker 및 동일 요청 receipt를 재사용한다.

현재 API 밖인 `files.table` 전역 data_id, owner 없는 legacy job, frozen CAD/FE 입력은 명시 차단한다. 아직 보존되지 않은 comparison은 `DRAFT_COMPARISON_NOT_RETAINED`로 차단하고 원 owner의 보존 또는 명시 saved_only를 안내한다. 이전 acknowledged Material 입력 증거가 사라졌다면 맞는 값처럼 꾸미지 않는다. 이 제한을 조용한 초안 제외로 바꾸지 않는다.

## 실제 typed 읽기와 편집 범위

기존 read adapter는 owner prefix와 실제 문서 ID, working/pointer/revision을 읽는다. tool fixture key, JSON 문자열 속 ID, VTK proxy ID를 문서 관계로 승격하지 않는다. Native 관계는 이미 보고된 descriptor와 명시 Pre job link만 읽으며 token/nonce를 내보내거나 expire/activate하지 않는다. Study/Report/Expert evidence·보존 method/adoption/history·comparison refs는 기존 typed reader로 읽고 원 owner에 위임한다.

| 대상 owner / port | 허용 원본 | 값·계산에 대한 제한 |
| --- | --- | --- |
| Numerical non-request `material` | exact Material saved 입력 또는 current acknowledged 입력 | 기존 material_reference 계약; 계수/시험/단위 변경 없음 |
| Numerical 기존 `experiment/<id>` | 실제 보존 Data result의 명시 response | 기존 unit/frame/component/protocol 검사; 행 생성·변환 없음 |
| Numerical request `source` | Data/Material/PDE/Simulation/Evaluation/Study 저장 개정 | exact saved reference, request 값 복사 없음 |
| Numerical request `model_source` | Material/PDE/Simulation/Evaluation 저장 개정 | 모델 설정 자동 동기화 없음 |
| Numerical request `result/<role>` | 기존 RESULT_ROLES 및 명시 optional role에 맞는 retained result | exact doc/job/input/result hash; 후보표/모델/manifest 의미 검사; inline 충돌은 거절 |
| Evaluation 기존 `stage/<id>` | Material/PDE/Simulation 저장 개정 | 단계 생성·transfer/mesh/field/unit mapping 없음 |

기존 current editable 포트만 수정한다. 알 수 없는 종류, 중복 row ID, 과거 frozen ref, native 관계, Report capture 등은 구체적으로 거절한다. 해제로 입력이 미완성해져도 기존 owner의 editable invalid draft와 진단을 유지하며 저장 base/원결과를 삭제하지 않는다. 실패 결과는 읽기/사본에 보존하지만 없는 성공 response나 후보표를 새로 만들지 않는다.

store의 현재 로컬 경로를 hash한 runtime scope와 실제 서비스 session을 selection envelope에 넣는다. scope는 saved ref의 도메인 식별자가 아니다. 다른 store나 재시작 뒤 같은 ID를 가진 token은 거절한다. 작업 사본 이동 뒤에는 새 scope로 선택을 다시 읽으며 이전 scope에 의존하지 않는다.

source token에는 kind, basis(saved/acknowledged/result), 실제 doc ID, 개정/입력/결과의 exact identity와 현재 observed generation/head/fingerprint가 있다. target token에도 현재 observed identity가 있다. preview는 읽기 전용 proposal+impact를 반환하고 apply는 proposal hash, scope, source/target CAS와 실제 source contents를 다시 검증한다. 원 owner의 update_operation에 `draft`의 지정 ref만 바꾼 사본을 전달한다. owner history/generation/idempotence receipt를 재사용한다. graph만의 관계 저장소는 없다.

preview의 영향은 exact typed downstream 문서, saved/current/proposed ref, 결과의 noncurrent 여부, 원 owner diagnostics다. 도메인 실행/물리 판정이 아니다. locked snapshot 뒤 추가된 다른 문서는 다음 조회에서 보이며 무제한 전역 장악이나 scheduler를 추가하지 않는다. 조회/apply 시 점유된 owner는 OWNER_BUSY로 명시 재시도하게 한다.

## 공통 명령·전송

Workbench/Client 동일 함수:

```python
graph = client.connection_graph(document_ids=None, include_history=False)
catalog = client.connection_catalog(target_id)
impact = client.connection_impact(target_id, port)
proposal = client.connection_preview(catalog['target'], port, 'add', source_token)
receipt = client.connection_apply(proposal, confirmed=True, command_id='Cunique')
view = client.connection_view_read()
receipt = client.connection_view_save(state, scope=view['scope'],
    expected_revision=view['revision'], expected_sha256=view['state_sha256'], command_id='Cview')
inspection = client.portable_inspect(selected_ids, draft_policy='acknowledged')
copy = client.portable_create(inspection, new_path, approved=True,
    command_id='Ccopy', session_id=inspection['service_session_id'])
```

POST `/api/workbench/connection/{catalog,impact,preview,apply,view-read,view-save}` 및 기존 `/api/workbench/connection-graph`, `/api/workbench/portable-project/{inspect,create,verify,repair}`를 기존 loopback/token/Origin 처리로 연결한다. 알려지지 않은 필드는 거절한다. 일반 command 128 KiB, upload 16 MiB, create metadata 8 MiB를 유지한다. owner document draft용 기존 별도8 MiB+envelope 경로도 확대하지 않았다. 큰 파일은 명시 register된 server-local path에서 직접 복사하며 JSON/base64 전송하지 않는다. preview/apply가 너무 큰 draft/metadata를 초래하면 현재 한도 안에서 명시 거절되며 전체 전송 한도를 올리지 않는다.

`connection_graph_commands`는 같은 Client에 위임하는 전용 CLI이며 새 controller/service를 생성하지 않는다. 전역 registry/CLI/MCP tool registration과 Windows shortcut는 root 통합 영역이다. capsule/related-save/remote 명령을 이 namespace에 만들어 넣지 않는다.

반환 graph의 각 node.actions에는 **select/cancel/open_owner/open_saved_reference/impact/add/repair/unlink**의 enabled, handler/command, exact 대상/포트/참조 및 거절 이유가 있다. Qt 메뉴·키보드·context menu·graph·list는 이 계약을 공유한다. 원문서는 desktop_links, 정확 저장 참조는 기존 ReferenceWindow를 쓴다. read-only graph 응답의 `read_only=true`는 조회가 쓰기를 하지 않는다는 뜻이지 별도 apply API가 없다는 뜻이 아니다.

## view state

`caelab.connection-view/1`, `workbench/views/connection.json`. 허용 키는 검증된 bindings/positions/selected/checked_documents/filter/graph_documents/panel뿐이다. 외부 경로, raw binary, global QSettings, 실행 명령, proxy 자료를 받지 않는다. 최대96 KiB UTF-8,1024 anchors,선택 문서256,필터200자,finite 좌표/제한 확대율·panel enum이다.

view의 opaque V key와 domain exact ref는 분리한다. anchor는 문서, consumer의 typed path, run/source의 owner identity다. 관계 ref 값이 바뀌어도 같은 typed slot의 배치/선택은 유지한다. 프로젝트 복사 때 old→new document ID만 검증 대응하고 view scope는 저장하지 않는다. copy inspection은 source view도 pin하며 원 view bytes를 archive하고 사본 view는 이후 합법적으로 수정 가능한 파일로 둔다. view CAS와 마지막 command receipt는 view 파일 안에 있고 기존 owner lock만 재사용한다. 문서 dirty/hash나 결과 bytes는 변경하지 않는다.

## DataMaterial extension 경계 — 미확정 API를 구현하지 않음

`portable_project_drafts.CAPSULE_CONTRACT`는 format/status/owner/automatic_collection/raw_widget_buffers_included로 **NOT_INTEGRATED**를 알린다. callable fake capsule API가 아니다. 현재 사본은 이를 extension 상태 metadata로 표시할 뿐 다른 팀의 메모리나 파일을 탐색하지 않는다.

향후 DataMaterial이 확정할 작은 경계는 사용자 선택으로 받은 owner-managed capsule에 대해 같은 source store/session/document/generation, capsule version, 명시 파일 목록/byte hash, owner 검증/복원 책임을 구분하는 것이다. 그 계약이 도착하면 전용 adapter에서 검증 후 포함하며 raw-buffer receipt를 acknowledged document 저장으로 간주하지 않는다. FN02 related-save의 문서별 성공/실패 receipt와 original reference 유지도 해당 coordinator 소유다. 이번 portable 코드는 coordinator를 호출하거나 implicit save/apply하지 않는다. API 이름/registry 등록/위젯 필드를 임의로 정하지 않았다.

## 실행·검증 경계

실제 cold 파일 검사는 Data·Material·Numerical saved/ack/history/raw/result/units/ref/layout와 owner edit/Undo/save를 검사했다. shared HTTP/CLI는 실제 로컬 서버에서 검사했다. Windows baseline 증거는 참고 입력으로 보존했고 C1 통과에 합산하지 않았다. Qt widget/QTest, OS mouse/native activation, 전체 설치, 물리/공학 승인은 별개이며 `VERIFICATION_KO.md`의 NOT_RUN을 따른다. 새 provider/유료 의존성/계정/비공개 자료의 외부 전송은 없다. 기존 출처·라이선스를 바꾸거나 재라이선스하지 않는다.
