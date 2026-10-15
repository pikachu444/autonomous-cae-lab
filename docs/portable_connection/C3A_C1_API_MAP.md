# C3A C1 API 증분

## 기존 public API 유지

`inspect_copy(..., draft_policy, recovery_archives)`, `create_copy`, `read_archive`, `preview_resume`, `resume`, Workbench/Client/HTTP/CLI의 request shape는 바꾸지 않는다. 새 endpoint, owner, store, coordinator, solver, 의존 패키지는 없다. 기존 크기 제한과 사용자 명시 선택을 유지한다.

| 경계 | C1 변경 |
|---|---|
| portable_project.inspect_copy | collect_recovery 및 Q 의존 seed를 기존 revision queue 앞에 둠 |
| portable_recovery_dependencies.seed_dependencies | Q 전체 acknowledged typed refs 및 당시 saved base를 검증해 기존 queue에 합류 |
| AcknowledgedReader.archived_revision / revision_folder | 검증된 Q saved_sources의 원 위치를 읽기 전용으로 등록; live 충돌은 거절 |
| AcknowledgedReader.resolve | saved_revision을 가진 Material binding은 그 정확한 개정을 검사 |
| AcknowledgedReader.recovery_inputs | saved_only+Q의 명시 peer 과거 입력을 기존 input-only receipt reader로 검증; current whole working 자동 수집 아님 |
| verify_projection | 매 hop의 Q typed refs 검증; 발행과 buffer 재개에 적용 |
| projected_buffer | 처음부터 ack를 상속한 local_draft typed 경로만 mapping; 나머지 raw는 불변 |
| MaterialDocuments.command response | UPDATE/Undo/Redo의 기존 receipt에 acknowledged_document_sha256 추가 |
| mutation_marker / recover_mutation | 전체 post-document 증명; 원 receipt 유실 시 기존 durable marker로만 복구 |
| resume | 기존 command 재시도 뒤 full acknowledged hash와 현재 public document 대조 |

원 archive layer read는 편집 승인과 분리된다. 유효 Q의 mapping만 불완전하면 원문은 읽되, verify_project/명시 재개는 거절한다. missing/tampered Q 자체를 정상 읽기로 위장하지 않는다.

GUI 전달의 `BUFFER_READY`와 raw packet shape는 그대로이다. 추가 hash는 owner 응답의 machine field이며 사용자 메뉴에 출력할 항목이 아니다. Sol의 GUI 파일/회귀는 이번 변경 목록에 없다. 실패 응답은 현재 buffer 보존이며 자동 새 command 또는 late document redraw 지시가 아니다.
