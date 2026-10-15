# C3B-R1 Report 원문 보존 및 현재 탐색 계약

요청: PRO-PORTABLE-CONNECTION-20261015-C3B-01. 기준: 22da57c74a8239b1898c13d703fd3d7558f72118, upstream 3e48bf6138f495299f45b1af254bfb4aaff307b8, overlay 0.

이 인도는 Report 공학 자료의 이동 작업 사본을 실제 구현한 중간 인도다. CB01 전체 또는 C3B 전체 완료가 아니다. 기존 ReportDocuments, MaterialDocuments의 저장/Undo/Redo/세션/CAS, SnapshotReader, AcknowledgedReader, TypedProjection, portable staging/검증/마지막 manifest 발행, Client와 선택 연결창을 사용한다. 새로운 solver, store, owner, Q, ACL, controller, provider는 없다.

## 1. 입력과 current/history 경계

`inspect_copy`와 `create_copy`가 Report B를 기존 Data T/Material M/Numerical N과 함께 선택한다. saved_only는 명시 saved head를, acknowledged는 그 saved base와 실제 owner가 받은 현재 상태/Undo/Redo를 각각 보존한다. 미저장 Report는 current working 상태로만 시작하며 존재하지 않는 saved head를 만들지 않는다. 선택하지 않은 peer를 수집하지 않는다.

Report typed 경로는 기존 `connection_graph_refs.document_references(include_history=True)`가 선언한 draft 및 Undo/Redo의 `sections[].asset.reference`다. 제목·설명·raw/local_draft·임의 JSON의 ID/path처럼 보이는 문자열은 탐색/치환하지 않는다. 단순 본문·빈 보고서의 원 owner 문서도 섹션 자산과 독립적으로 보존한다.

현재 owner 식별자, input revision, saved revision과 위 typed navigation에만 기존 `_Fork`/TypedProjection으로 새 identity를 부여한다. 원 Report 문서의 세션/명령/실패/저장 상태는 raw archive에 남기고 실행 command journal이나 현재 승인으로 설치하지 않는다. 원 frozen reference와 원 실행·결과의 성공/실패/UNKNOWN/NOT_RELEASED는 변경하지 않는다.

## 2. 원 A JSON과 현재 navigation의 분리

A ID는 기존 `A + canonical_hash({reference,content})`이며 원 `assets/A<hash>.json`은 raw bytes 그대로 복사한다. 공백/개행이 다른 유효한 원 JSON도 재직렬화하지 않는다. `ReportDocuments._retain_inputs`의 기존 save 경로에도 좁은 raw retention hook을 연결한다.

사본의 section binding은 원 A id/sha를 유지한다. 선택한 현재 source로 이동하는 reference만 typed projection으로 변한다. 원 A JSON 안 reference를 새 ID로 바꾸지 않으며 기존 frozen/PNG 검증도 끄지 않는다. A마다 별도 `assets/A<hash>.navigation.json`에 원 report/scope/A/reference digest/원 owner archive와 기존 mapping hop을 보존한다. 문서의 `portable_report_assets`는 해당 파일의 raw SHA를 선언한다.

reader는 원 A canonical hash와 raw SHA, 원 Report가 실제 A를 선언했는지, 각 mapping의 scope/owner/typed input 및 최종 binding을 대조한다. 그 다음 기존 resolver로 현재 exact source를 읽어 원 frozen payload의 **명시 typed 투영**과 비교한다. 현재 source 조회가 실패해도 검증된 frozen payload는 별도로 읽힌다. 원 경로/store/native origin으로 fallback하지 않는다.

현재 navigation은 명시 선택한 `document`와 `result` source에 구현했다. document compact payload의 id/input_revision/draft만 기존 TypedProjection으로 비교한다. result 선택 내용은 변경하지 않고 기존 check_selection/compact_payload와 원 행·응답·성분·단위/시각 선택을 비교한다. 선택하지 않은 source, 보존 Post 그림, 그 밖의 비교·candidate 근거는 frozen-only다. 현재 비교/candidate 전용 navigation 및 knowledge local-scope 연결은 이 인도에 없다.

`ReportDocuments.content`의 기존 frozen `reference/content`는 원값이다. 추가 `navigation_reference`만 사본의 현재 탐색 대상이다. 소비자가 원 `reference`를 현재 opener에 넣어서는 안 된다. ReportWindow의 원자료 열기도 이 검증 응답을 사용하고 응답 전/마지막 실패 미리보기는 opener 권한으로 쓰지 않는다.

## 3. 원 owner 자체와 saved base의 재복사

원 문서, 원 revision manifest, A JSON 및 원 선언 파일은 기존 `portable_execution/report_archive/`에 raw hash 파일로 보존한다. 새 저장소가 아니라 기존 Report revision의 declared retained files다. archive descriptor의 path는 원 snapshot 내의 이름이며 현재 작업 경로가 아니다.

원 acknowledged snapshot과 원 saved base는 서로 다르다. descriptor는 원 acknowledged 문서의 saved_revision과 일치하는 **검토된** saved base를 `saved_base/<원 revision>/...`로 별도 선언한다. 원 manifest의 각 path/hash와 실제 원 문서 id/kind/saved_revision을 검증한다. 이를 새 current saved head로 승격하지 않는다.

문서의 `portable_report_owner`는 기존 `portable_execution/report_owner/`의 원문 이동 이력 파일을 가리킨다. 각 hop은 검토한 source owner archive와 동일 TypedProjection mapping만 가진다. 원 Report가 빈 문서이거나 이후 자산이 없어져도 원문 보존은 섹션 수에 의존하지 않는다. 매 재복사의 직전 source Report snapshot도 보존된다. 검증된 raw archive 전체를 현재 owner.save가 retain하므로 첫 사본 폴더를 없앤 다음 재복사 사본에서도 읽을 수 있다.

asset navigation과 owner history 모두 기존 MAX_HOPS=32를 유지한다. 동일 archive/map/A 파일은 저장 시 경로/해시를 대조하고 중복 I/O를 줄인다. 현재 선택 A 읽기는 필요한 원 문서/A와 증명 위주로 읽으며, copy/save는 전체 declared closure의 실제 raw bytes를 확인한다. 선언 밖 source store를 순회하지 않는다.

## 4. 권한·그림·실행

knowledge frozen source를 단순 파일로 공개하지 않는다. 이 인도에서 해당 source가 발견되면 `REPORT_KNOWLEDGE_SCOPE_REQUIRED`로 inspect를 차단하고 원 Report를 보존한다. exact revision의 원 수집/발행 권한과 새 local scope를 실제 KnowledgeStore 정책으로 연결하는 일은 CB02 잔여다. 새 ACL, source 최신판 치환, archived access metadata의 권한 승격은 없다.

보존 Post 그림은 기존 PNG decode/CRC/pixel/scene/origin 내부 계약을 검증한 frozen content다. 사본에서 읽을 때 외부 원 Post 경로를 다시 열거나 screenshot을 찍지 않는다. 원 PNG pin/origin과 bytes는 그대로 남고 `navigation_reference=null`이다. managed Post opener/relocation을 구현했다는 뜻이 아니다. 새로운 capture/replace는 기존 명시 Report capture/native 완료 명령을 사용해야 한다. 자동 capture는 없다.

이미 열린 사본에서 그림이 유실/변조되면 해당 content가 SNAPSHOT_UNAVAILABLE이며 새 save/copy를 거절한다. 현재 편집 문자열과 이전 정상 pointer는 유지한다. 동일한 원 파일 복구 후 재검증할 수 있다. 손상된 전체 portable project의 cold open은 기존 fail-closed verify를 유지한다. 그런 project를 부분/degraded open하는 새로운 경로는 이 중간 인도에 포함하지 않는다. 비이동 Report의 기존 degraded published-image reader와 unpublished-image 발행 거절은 유지하고 영향 회귀를 실행했다.

read/inspect/copy/reopen은 submit/solver/DAG/native/AI/search를 시작하지 않는다. 원 Data import 성공·실패는 retained record이며 새 JobManager 작업이 아니다. Report에는 원래 evaluate operation이 없다. 일반 Report 편집/저장은 CAD, AI, MCP, WSL을 요구하지 않는다.

## 5. GUI와 실패/재시도

Report 파일 메뉴의 `작업 사본 만들기…`(Ctrl+Shift+S)는 기존 ConnectionWindow에 현재 Report를 선택하여 연다. 미적용 section editor 내용이 있으면 실제 기존 편집칸으로 돌아가 명시 `설명 적용`을 요구한다. 로컬 제목/본문/구성만 달라진 경우 Save/Cancel 확인을 거쳐 기존 save_document만 실행하고, copy는 사용자가 다시 선택한다. copy 버튼이 Apply/Keep/commit을 숨겨 실행하지 않는다.

진행 중 command/응답유실 상태에서는 새 copy나 새 command ID를 만들지 않는다. 기존 pending retry 및 late-reply 보호를 유지한다. 연결창의 Q 조회에서 Report는 실제 Report owner identity를 확인한 뒤 Q 목록 대상에서만 제외한다. Report용 Q를 만들거나 다른 owner의 Q reader를 대신 호출하지 않는다.

전체 사본 발행은 기존 source pin/CAS 재확인, 독점 stage/destination, 마지막 portable-project.json 발행, 같은 command/destination 재확인을 그대로 사용한다. 기존 완료 destination과 원 store를 덮지 않는다. 원 데이터 손상/누락, owner 변경, 현재 잘못된 binding, 중간 발행 실패가 성공으로 바뀌지 않는다.

## 6. 한도와 변경 소유

128 KiB 일반 API, 16 MiB upload, 8 MiB create, 16 MiB JSON, 전체 20 GiB/100000 files, Report 자체 자산/문서 한도 및 32 hops를 늘리지 않았다. Report asset 허용 추가는 해당 owner의 정확한 A JSON/navigation 파일명에 한정한다. 기존 path/ZIP/backslash/NUL/casefold/symlink/reparse 검증을 재사용한다.

전용 변경은 portable_project*.py 및 C3B tests/example/docs다. 공유 변경은 ReportDocuments retention/content와 ReportWindow/ConnectionWindow의 최소 hunks 3파일뿐이다. Workbench/schema/registry/solver/native/다른 owner/FN05/Data C2 구현은 변경하지 않았다. 최소 공유 patch는 root가 현재 WIP와 대조해 통합한다.
