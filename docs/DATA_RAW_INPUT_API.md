# Data 원문 입력의 비확정 snapshot과 복구

`data_raw_snapshot(window)`는 활성 매핑 편집기를 확정하거나 요청을 보내지 않고 원래 인정된 값·경로, 현재 문자열, 커서·선택, 채널·탭과 전체 로컬 초안을 JSON으로 복사한다. `DataWindow.edited_draft(commit=False)`를 사용하므로 `1e` 같은 편집기 입력이 셀 값에 섞이지 않는다. off-channel 편집, 채널 이름 변경과 잘못된 행 구간 문자열도 별도로 보존한다.

`restore_data_raw(window, raw)`는 호스트가 먼저 Core의 owner/store/session/generation 및 capsule 무결성을 확인한 뒤 새 깨끗한 Data 창에만 호출한다. 원래 값/경로와 편집 범위를 확인하고 provenance 변경을 거절한다. UI 원문과 선택을 복구하며 owner 변경·저장·가져오기·계산을 수행하지 않는다. 활성 셀은 좁은 창에서도 실제로 보이도록 안쪽 표와 바깥 설정 패널을 스크롤한다. 새 편집이 있는 창에는 덮어쓰지 않는다.

실제 Windows Qt에서 미확정 배율 `1e`와 커서를 새 창에 복구하고 정상/좁은 화면에서 편집기가 두 viewport 안에 있는지 확인했다. 채널 이름과 다른 채널의 편집/잘못된 구간 문자열/셀 선택 보존, 숨은 case provenance 변경 거절 검사도 통과했다. 이 모듈은 GUI 데이터 변환만 담당하며 durable Keep/닫기 허가/cold 재개는 C2 Core와 호스트의 별도 연결이다. 그 기능을 이 검사로 완료 처리하지 않는다.

호스트의 복구 검토 모달은 `with RawEditorFocusGuard([source_windows...]): dialog.exec()`로 감싼다. guard는 각 창에서 이미 열린 표 편집기의 FocusOut만 일시 차단해 모달 진입으로 셀이 확정되는 것을 막고, 종료 시 원래 포커스를 복원한다. snapshot은 global focus가 모달에 있어도 자기 표의 살아 있는 편집기를 읽는다. 실제 Windows에서 Data/Material `1e`·부분 텍스트 선택·원래 셀 값·전체 snapshot이 모달 안에서 그대로이고 취소 후 포커스가 돌아오는 것을 확인했다. 이 guard 자체는 닫기나 durable 보관을 허가하지 않는다.

커서와 문자열 선택은 Qt의 UTF-16 위치를 사용한다. 비 BMP 문자와 역방향 선택에서도 원래 caret/선택 길이를 복구하며 잘못된 범위는 표를 바꾸기 전에 거절한다.
