# Material 입력 원문과 Qt 복원 API

`material_raw_snapshot(window)`은 owner 요청이나 셀 확정 없이 현재 표·단위·모델의 원문을
JSON으로 복사한다. 미확정 QLineEdit의 텍스트/커서/선택은 item 값보다 우선한다. 각 셀은
기준 draft의 field_path/original_value와 표 위치를 갖는다. 추가 행은 original_exists=false다.
local_draft는 이미 편집한 typed 입력이며 raw 셀과 별도로 남는다. 같은 상태의 editor_revision은
같으며 새 텍스트·선택·커서·입력이 생기면 달라진다. 숫자를 읽는 기존 edited_draft에는
선택적 commit=False를 추가했으며 기존 호출은 계속 확정 후 읽는다.

`restore_material_raw(window, raw)`는 **호스트가 recovery의 owner/store/session/generation을
검증한 후** 깨끗한 Material 뷰에 호출한다. 이 함수 자체는 서비스 recovery 권한을 부여하지
않는다. 원래 셀 값·경로를 다시 대조하고 숨은 필드 변경을 거절한다. typed 초안·원문 표와
표시된 미확정 에디터를 복원하며 owner update/save/evaluate를 하지 않는다. local Undo에
복원 전 입력을 남긴다. 미확정 에디터를 복원하려면 먼저 해당 창을 표시해야 한다.

2026-10-15 두 Qt 검사는 live1e의 무확정 snapshot/안정 토큰, 다른 깨끗한 뷰의1e·커서 복원,
기준값 불일치 거절, 새 행의 원래값 없음 보존을 확인했다. Windows native에서도 셀 item은1000,
live editor는1e인 상태를 유지해 snapshot/복원했고 실행한 두 창은 닫았다. 문서·snapshot은
명시 시험 fixture이며 실제 Core 복구 쓰기나 cold 저장·재열기를 수행한 결과가 아니다.
C01 호스트 연결과 actual HTTP/Qt 수용 범위는 [DATA_MATERIAL_RECOVERY_DIALOGS.md](DATA_MATERIAL_RECOVERY_DIALOGS.md)에 기록한다. 이 복원 함수 자체의 검사와 Core 권한 검사를 구분한다.
