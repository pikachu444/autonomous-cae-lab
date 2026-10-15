# 원문 보관·열람 GUI 구성 요소

이 구성 요소는 기존 Pro `recovery.*` transport를 사용한다. **현재 Material/Data 닫기 경로에는 연결하지 않았으며**, C2 Core의 불변 기준 문서·정상 저장 후 인정·실제 소비자 교정이 검토되기 전 C01 완료로 공개하지 않는다. 보관/복구 엔진이나 새 문서 소유자를 구현하지 않는다.

`RecoveryKeepDialog(client, documents, capture_live, parent=None)`의 `capture_live()`는 UI thread에서 현재 인정된 owner별 `{identity, raw}`를 반환한다. identity는 editor가 bind된 기준을 사용한다. 현재 owner를 새로 읽어 옛 raw에 붙이지 않는다. 호스트는 실제 pending editor를 `RawEditorFocusGuard`로 지킨 상태에서 dialog를 연다.

사용자의 **원문 보관**은 검토한 preview를 `recovery.execute`에 전달한다. 전 owner가 보관된 뒤 별도 `recovery.close_permitted`의 최신 gate와 live 원문의 일치를 확인한다. `close_ready`와 `is_still_current()`는 그 두 조건을 모두 충족할 때만 참이며, 호스트는 실제 닫기 직전 다시 비교하고 다른 busy/modal/계산 조건도 지킨다. 쓰기 실패·늦은 입력·gate 실패는 창을 닫지 않는다. 실패 재시도는 같은 preview를 사용자의 명시 동작으로만 전달한다.

`RecoveryReadDialog(client, document, identity, restore_raw, current_identity=..., parent=...)`는 기존 capsule을 읽어 자연스러운 보관 시각·상태·셀 위치와 원문을 보여준다. **이 원문 복구**를 누른 뒤 Core의 RESUME_READY, capsule hash, 검토 identity와 현재 host identity가 모두 같아야 UI 복구 함수를 호출한다. 다른 세션은 명시 확인을 받으며 다른 store의 사본은 열람만 허용한다. **보관 원문 삭제…**는 해당 capsule에만 명시 discard 명령을 보낸다. owner 적용/저장/계산은 호출하지 않는다.

현재 검사는 transport fixture를 사용한 GUI 계약 검사다. Keep 4개는 전 owner 보관·fresh gate·live 원문 일치, 실패 시 같은 요청 재시도를 확인한다. Read 6개는 명시 복구·late identity·BLOCKED·다른 store·명시 discard를 확인한다. Windows 실제 Qt 정상/좁은 창을 읽고 프로세스를 종료했으며, 이 결과는 실제 C2 durable recovery/close/cold resume의 검증을 대신하지 않는다. 최종 C2 실제 owner와 합성하는 검사는 별도로 남아 있다.
