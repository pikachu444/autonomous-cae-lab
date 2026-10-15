# C3A Data C2 — 원 보정 자료의 현재 owner retention

요청: PRO-PORTABLE-CONNECTION-20261015-C3A-DATA-C2. 정확한 C3A02+C1 작성 기준의 좁은 교정이다. C1의 Material R2/Q.assets-only와 whole post-state 보호는 유지한다. 다른 owner/native의 C3B 완료가 아니다.

## 세 층과 자료 위치

`saved_only + 명시 Data Q`의 저장 R1에는 없는 보정 입력이 Q의 검증된 `acknowledged.data_inputs`와 선언 assets에는 있을 수 있다. 사본 생성/열기/source-preview는 현재 owner retention이나 등록소를 수정하지 않는다. 실제 편집 재개의 승인 후, **현재 Data owner의 기존 UPDATE**가 Q acknowledged draft와 이에 필요한 자료 위치를 함께 확정한다.

`portable_recovery_data_inputs`는 `projected_buffer`/`archive_row`의 기존 typed navigation 검증과 `data_recovery_inputs.verify_inputs/resolve_source`를 재사용한다. 파일 경로는 이 검증된 기록만 사용한다. `raw`, `local_draft`, paste에 새 ID나 경로가 있어도 자료 수집/등록의 근거로 쓰지 않는다. 불완전한 acknowledged 입력은 원 상태로 남으며, 미보존 보정 SHA를 정상 입력으로 승격하지 않는다.

기존 Data `_retain_inputs`가 원 CSV와 input.json을 현재 owner의 retained asset container에 보존한다. 컨테이너는 기존 `portable_snapshot.layer=ACKNOWLEDGED_WORKING` 계약이며, 현재 owner의 `revisions/R…/revision.json`, document identity, retained binding, fingerprint와 원 bytes/receipt를 대조한다. 이 R은 보존 자료 컨테이너이지 사용자의 saved head가 아니다. **resume 동안 owner의 `document.json` 저장 포인터와 saved_revision은 그대로다.** 응답의 `saved_revision_created=false`는 사용자 저장본 미발행을 뜻하며, 검증된 자료의 비공개 revision 컨테이너까지 파일이 전혀 생기지 않는다는 뜻이 아니다.

현재 registry에 원 input.json을 설치하거나 `upload`/등록 API를 호출하지 않는다. 원 `data_id`는 검증된 자료의 identity로 유지한다. 위치는 기존 retained binding의 `revision/file/metadata`이며, 원 receipt의 `file` 문자열을 원 store 접근 경로로 사용하지 않는다. current registry에 같은 ID가 이미 있으면 일치/검증을 확인하고 충돌·손상을 Q로 덮어 감추지 않는다.

원 Q, raw, ack, original identity, receipt/hash, 성공·FAILED 실행 자료는 불변이다. 새 asset container의 `portable_recovery_input_origin`은 HISTORY_ONLY다. 원 recovery/discard/session/command 권한으로 사용하지 않는다. 실제 current owner의 저장 개정은 후속 `document.save`에서만 발행한다.

## 명시 승인과 원자적 acknowledged 쓰기

resume의 기존 preview hash/동일 command/current store/session/generation/input identity/전체 acknowledged document hash/current buffer token 및 덮어쓰기 승인 조건을 유지한다. Data의 추가 `portable_recovery_inputs` 인자는 이 전체 preview와 승인/token을 담는다. Data owner hook도 같은 gate를 다시 확인한다. 일반 Material/Plan UPDATE는 여전히 draft만 허용한다.

기존 UPDATE의 lock 안에서 자료를 검증·보존한 뒤 원래의 `_mutation_command`/whole post-state receipt가 최종 draft와 retained_inputs를 함께 결합한다. 자료 연결만 바뀌는 경우에도 새 current CAS를 발행한다. 메모리/working/응답 유실은 C1의 기존 `recover_mutation`이 복구한다. 별도 journal, coordinator, store 또는 operational Q를 만들지 않는다.

동일 command의 성공 재시도는 전체 post-state와 현재 retained bytes를 다시 확인한다. 다른 편집·run·비교·숨은 이력 또는 보존 파일 변조 뒤에는 오래된 문서를 반환하지 않는다. C2 이전에 이미 입장한 draft-only Data command를 추가 자료 연결의 승인으로 재해석하지 않는다. signature가 다른 옛 command는 거절하고 원 receipt/현재 문서/원문을 보존한다. 자동 새 command나 승인 재사용은 없다.

원 Q 손상은 기존 archive 검사에서 거절한다. 새 보존 자료 쓰기가 실패하면 이번 호출이 만든 미발행 컨테이너만 정리한다. 기존 saved/working/원 archive는 그대로다. 기존 owner의 APPLYING/unconfirmed receipt는 성공으로 바꾸지 않고 남긴다. durable working까지 발행한 뒤의 응답/메모리 유실은 그 정확한 marker로만 복구한다.

## save / 새 Keep / cold / 재복사

현재 Data 읽기는 기존 `_retained_source`, `prepare_job_arguments`, `resolve_job_source`, `document_source_preview`를 사용한다. 주 CSV뿐 아니라 calibration도 현재 owner의 exact retained_data_input reference로 읽을 수 있다. `prepare_job_arguments` 호출은 자료 검증/동결 참조 준비이며 import 제출이 아니다.

명시 save는 기존 `_retain_inputs`가 전체 현재/Undo/Redo/run 및 보정 의존을 다시 검증·보존한다. `unresolved_inputs`를 수동 필터하거나 강제로 비우지 않는다. 존재하는 실제 자료로 해결된 입력만 기존 retention 결과에서 해소된다. 미해결 미제출 ID의 저장 정책과 누락된 제출/보정 자료의 거절을 유지한다.

원 input.json은 Q 연결 때 실제 bytes를 복사하고, 이미 retained된 자료의 다음 save에서도 그 metadata bytes를 보존한다. canonical receipt hash와 input.json raw hash를 혼동하지 않는다. 원 등록소가 없는 새 owner도 `RawRecoveryDrafts.prepare/execute`로 **새 current Q**를 생성하고 close gate를 통과한다. 새 프로세스는 현재 identity와 명시 session-change 승인을 사용해 그 새 Q를 복구한다. 원 Q는 계속 NOT_GRANTED이며 current raw-recovery에 자동 설치되지 않는다.

재복사는 기존 `_internal_revisions`, AcknowledgedReader와 typed projection으로 보존 자료를 순회한다. 원 Q와 새 current Q 모두 명시 선택하여 가져갈 수 있으며 각 archive의 원 bytes/identity/receipt와 현재 탐색 mapping은 분리된다. caller가 현재 미완성 raw를 버리고 복사하거나 raw 적용을 계산 성공으로 표시해서는 안 된다.

## 통합 제한

공통 hunk는 DataDocuments retention과 MaterialDocuments의 Data-only UPDATE hook 두 곳이다. `related_save_edits`/`related_save_recovery`/Core registry, Sol GUI/UTF-8/포커스, Law/Post/PDE/Runner/B13는 수정하지 않았다. 기존 body/파일 한도, 계산·CAS·CAPTURE·승인 관문도 변경하지 않았다. GUI 실제 실행은 별도이며 C2 Windows/Qt/native는 NOT_RUN이다. C3B 다른 owner/managed native 이동은 필수 후속이다.
