# 원문 보관·열람 GUI 구성 요소

이 구성 요소는 기존 Pro `recovery.*` transport를 사용한다. Material/Data 호스트 연결은 실제 Pro C2 인정 상태·C3 최초 저장 전 원입력 보존과 함께 적용해야 한다. 별도 보관 엔진이나 문서 소유자를 만들지 않는다. 원 ZIP과 Core 통합은 호스트 GUI의 검증과 별개다.

`RecoveryKeepDialog(client, documents, capture_live, parent=None)`의 `capture_live()`는 UI thread에서 현재 인정된 owner별 `{identity, raw}`를 반환한다. identity는 editor가 bind된 기준을 사용한다. 현재 owner를 새로 읽어 옛 raw에 붙이지 않는다. 호스트는 실제 pending editor를 `RawEditorFocusGuard`로 지킨 상태에서 dialog를 연다.

사용자의 **원문 보관**은 검토한 preview를 `recovery.execute`에 전달한다. 전 owner가 보관된 뒤 별도 `recovery.close_permitted`의 최신 gate와 live 원문의 일치를 확인한다. `close_ready`와 `is_still_current()`는 그 두 조건을 모두 충족할 때만 참이며, 호스트는 실제 닫기 직전 다시 비교하고 다른 busy/modal/계산 조건도 지킨다. 쓰기 실패·늦은 입력·gate 실패는 창을 닫지 않는다. 실패 재시도는 같은 preview를 사용자의 명시 동작으로만 전달한다.

`RecoveryReadDialog(client, document, identity, restore_raw, current_identity=..., parent=...)`는 기존 capsule을 읽어 자연스러운 보관 시각·상태·셀 위치와 원문을 보여준다. **이 원문 복구**를 누른 뒤 Core의 RESUME_READY, capsule hash, 검토 identity와 현재 host identity가 모두 같아야 UI 복구 함수를 호출한다. 다른 세션은 명시 확인을 받으며 다른 store의 사본은 열람만 허용한다. **보관 원문 삭제…**는 해당 capsule에만 명시 discard 명령을 보낸다. owner 적용/저장/계산은 호출하지 않는다.

앞선 구성 요소 검사는 transport fixture를 사용했다. Keep 4개는 전 owner 보관·fresh gate·live 원문 일치, 실패 시 같은 요청 재시도를 확인했다. Read 6개는 명시 복구·late identity·BLOCKED·다른 store·명시 discard를 확인했다. 이 대역 증거는 실제 durable recovery의 증거와 구분한다.

`data_material_recovery_host`는 닫기·문서 전환 전에 `RawEditorFocusGuard`를 먼저 설치하고, 셀을 확정하지 않은 채 원문과 선택 상태를 복사한다. **저장**은 기존 저장 동작이며, **편집 원문 보관**은 owner별 기존 `recovery.identity/prepare/execute/close_permitted`만 사용한다. identity를 읽은 뒤에도 원래 editor의 문서 기준과 정확히 같아야 하며 새 owner 기준에 옛 원문을 붙이지 않는다. Material의 연결된 여러 Plan 위젯도 각자 공개 snapshot·readiness API로 따로 보관한다. 미확인 Undo·진행 중 요청, 쓰기 실패, 다른 창의 변경과 최신 원문 불일치는 닫기를 막는다.

파일 메뉴의 **보관한 편집 원문…**에서 문서와 보관본을 선택하고 명시적으로 복구한다. 기존 `recovery.recover`가 허용한 같은 store·문서 기준만 실제 GUI에 복원한다. 편집 중인 새 입력은 덮어쓰지 않는다. 모달 안에서 새로 만들어진 미확정 editor도 focus guard에 추가하여, 모달이 끝날 때 셀이 자동으로 확정되지 않게 한다. 이 흐름은 원문을 owner에 적용하거나 저장·계산하지 않는다. 다른 store로 옮긴 사본의 읽기와 resume 권한은 별도 계약이다.

2026-10-15 current root C2/C3 Core와 전용 GUI 조합에서 실제 Windows Qt/HTTP 5개가 15.95초에 통과했다. Material/Data의 live `1e3`와 역방향 선택을 취소·보관·닫기·새 뷰의 명시 복구까지 유지했고, 다른 창의 변경과 실제 capsule 쓰기 실패는 닫기를 막았다. Material과 두 Plan의 `1e`/`2e`/`3e`도 각 owner의 raw capsule에 따로 보관되었으며 원 owner 초안과 job 목록은 그대로였다. 정상/좁은 크기 8개 이미지를 직접 읽었고 owned process가 종료되어 `job_empty`였다. 검사는 root의 현재 공통 코드와 private GUI overlay를 사용했으며 호스트의 main 적용과 다르다. 다른 OS 프로세스의 GUI 재개·foreign portable resume는 이 검사 범위가 아니다. Core C3의 원 store 삭제·capsule-only cold 검증과도 별도 증거다.
