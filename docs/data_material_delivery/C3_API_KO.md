# C3 공개 API: 원 Data 입력의 보관과 읽기

기존 C2 API/owner/CAS를 유지한다. 같은 `DataMaterialService`와 HTTP/Client 운반 경계를 사용한다.
새 HTTP route, schema, owner, source registration은 없다. 모든 예제 ID는 실제 호출 응답에서 얻는다.
아래 예제는 GUI가 owner draft에 적용하지 못한 문자열과 기존 source를 구별하는 연결 예제다.

## 1. Keep → 닫기 검토

```python
from caelab.data_material_service import DataMaterialService
service = DataMaterialService(workbench)
doc = workbench.document_read(data_document_id)
identity = service.dispatch('recovery.identity', {'document_id': doc['id']})
raw = {
    'editor_revision': editor_token,
    'cells': [{
        'field_path': ['data_id'], 'original_value': doc['draft']['data_id'],
        'raw_text': '1e', 'position': {'row': 0, 'column': 1, 'table': '원본'},
        'editor_kind': 'text'
    }],
    'focus': {'field_path': ['data_id'], 'cursor': 2},
    # local_draft를 제공한다면 미전송 GUI buffer 그대로 넣는다.
}
review = service.dispatch('recovery.prepare', {'requests': [{'identity': identity, 'raw': raw}]})
# review.targets[].problems와 acknowledged.data_inputs의 원본 상태를 표시한다.
# 사용자가 Keep를 선택한 이후에만 execute를 호출한다.
kept = service.dispatch('recovery.execute', {'preview': review})
target = kept['targets'][0]
# close_permitted가 false면 해당 live editor/raw를 절대 폐기하지 않는다.
# true라도 닫기 직전에 새 live snapshot으로 gate + editor token을 비교한다.
gate = service.dispatch('recovery.close_permitted', {
    'preview': review, 'live_requests': [{'identity': live_identity, 'raw': live_raw}]
})
```

둘 이상의 dirty owner도 기존 `requests` 배열을 사용한다. 각 target 결과를 독립적으로 처리한다.
`all_kept`는 capsule write 상태의 요약이지, source가 없는 draft의 닫기 허가나 계산 승인 대신이 아니다.
반드시 `targets[].close_permitted`와 전체 `close_permitted`를 사용하고 실패한 창의 raw를 유지한다.

## 2. 보관된 source의 의미

`recovery.inspect`의 기존 `acknowledged`에 `data_inputs`가 추가된다. `source_retention`은
`COMPLETE`, `INCOMPLETE_UNSUBMITTED_DECLARATIONS`, `LEGACY_INPUT_CLOSURE_NOT_RETAINED` 중 하나다.
COMPLETE는 **참조된 원본 byte closure**가 있다는 뜻이며 유효한 calibration/physics/engineering 승인이라는 뜻이 아니다.

실제 RETAINED entry의 구조는 다음과 같다(값은 각 응답의 원본을 사용).

```python
entry = {
    'data_id': original_data_id,
    'state': 'RETAINED',
    'resolution': 'registered_input',  # 또는 retained_data_input
    'uses': [{
        'data_id': original_data_id,
        'path': ['runs', 0, 'arguments', 'source_ref'],
        'role': 'frozen_source', 'required': True,
        'claim': original_frozen_source_reference,
    }],
    'source_file': original_store_relative_source_path,
    'metadata_file': original_store_relative_input_json_path,
    'sha256': original_source_hash, 'bytes': original_source_length,
    'receipt': original_registration_receipt,
    'receipt_sha256': canonical_hash_of_original_receipt,
    'metadata_sha256': sha256_of_actual_input_json_bytes,
}
```

`uses`에는 현재/Undo/Redo/run과 mapping/acquisition calibration의 실제 JSON path가 모두 들어간다.
한 ID는 하나의 검증된 원 bytes/receipt에만 연결되며 conflicting frozen claims는 오류다.
`source_file`과 `metadata_file`은 capsule의 `.assets`에 보관된 **원 store 상대 경로**다.
`receipt.file`, original Data ID, capsule.identity.store_id 등을 이동 경로에 맞추어 수정하지 않는다.
원본은 보존된 receipt/file manifest와 대조하고 미확정 raw.local_draft는 별도 필드로 남긴다.

## 3. 기존 GUI/Client에서 읽기

```python
info = service.dispatch('recovery.inspect', {
    'document_id': doc['id'], 'capsule_id': target['capsule_id']
})
source = next(row for row in info['acknowledged']['data_inputs'] if row['state'] == 'RETAINED')
preview = service.dispatch('recovery.source_preview', {
    'document_id': doc['id'], 'capsule_id': target['capsule_id'],
    'data_id': source['data_id']
})
# 기존 client.data_material('recovery.source_preview', 동일 arguments)도 같은 운반이다.
```

`preview`는 original receipt와 최대 16,384 UTF-8 문자, 기존 `preview_table` 출력이다.
문자열을 재료 상수로 적용하거나 새 import 결과를 게시하지 않는다. 비문자 원파일은 raw binary 보관 사실을
반환한다. binary 원본은 아래 path-level resolve_source로 읽으며 변환하지 않는다.

## 4. 원 store 없는 capsule-only 읽기

`recovery.portable_payload`가 열거한 파일들을 기존 portable writer가 원 hash와 대조해 복사한다.
독립 예제에서는 원 `Q....json`과 동명 `Q....assets/` 폴더를 함께 옮긴다. 파일명/identity를 바꾸지 않는다.

```python
from pathlib import Path
from caelab.data_recovery_inputs import (
    inspect_capsule, resolve_source, preview_source, read_table_source,
)

capsule_path = Path(portable_folder) / original_capsule_filename
bundle = inspect_capsule(capsule_path, expected_capsule_sha256=keep_receipt_capsule_hash)
# owner 생성, 원 store, backend/model registration이 필요하지 않다.

source_path, original_receipt = resolve_source(
    capsule_path, original_data_id,
    expected_capsule_sha256=keep_receipt_capsule_hash,
)
# source_path는 검증된 보관 파일의 읽기 경로다. 새 등록 receipt가 아니다.
# 직접 다른 reader에 path를 전달했다면 읽기 종료 뒤 resolve_source를 다시 호출해 검증한다.

preview = preview_source(capsule_path, original_data_id,
                         expected_capsule_sha256=keep_receipt_capsule_hash)
# 현재의 acknowledged mapping으로 기존 files.table reader를 호출하는 읽기:
view = read_table_source(capsule_path,
                         expected_capsule_sha256=keep_receipt_capsule_hash)
# 특정 과거 import에 실제 쓰였던 mapping을 같은 reader로 재열람:
old_view = read_table_source(capsule_path, draft_path=['runs', 0, 'draft'],
                            expected_capsule_sha256=keep_receipt_capsule_hash)
```

`read_table_source`의 draft_path는 `['draft']`, `['_undo', i]`, `['_redo', i]`, `['runs', i, 'draft']`만 허용한다.
caller가 새 mapping을 넣는 API가 아니다. 계산된 처리 recipe를 다시 실행하거나 result를 등록하지 않는다.
반환 `table`은 기존 reader 결과(NumPy arrays 포함)이며 `interpretation='READ_ONLY_PARSE_NOT_IMPORT'`,
`job_submitted=False`다. 당시 처리 결과는 기존 `read_result(보관된_processing_folder, verify='all')`로 읽는다.
원 import/result hash·단위·측도·행·DAG는 capsule.assets 안에 그대로 보존한다.

`inspect_capsule`의 `resume_permission`은 항상 `NOT_GRANTED`이다. 원 identity를 새로운 portable owner로
수정하는 API는 없다. 실제 resume/discard는 원 store의 기존 RawRecoveryDrafts gate를 통과해야 한다.
과거 C2 Data capsule에 누락된 input bytes를 이 API가 재구성하거나 원 inputs 대신 다른 파일을 쓰지 않는다.

## 5. 실패와 GUI의 책임

source/receipt/revision/hash/required input 누락 또는 부분 복사·readback 실패 때
`execute.targets[].close_permitted=False`다. 같은 review의 늦은 응답이 오더라도 기존 live raw 토큰 검사를
우회하지 않는다. `inspect`와 source preview는 현재 GUI draft·모델·Plan을 바꾸지 않는다.

완전히 미정인 source identity의 raw draft 보관과, 이미 사용한 source가 소실된 경우를 구별한다.
형식상 유효한 미등록 ID는 capsule에 미해결 사실을 기록할 수 있지만 source 보관이 완성되지 않았으므로 close는
거절한다. 이미 사용한 import/calibration 원본의 누락을 성공·UNKNOWN 원본으로 만들어 통과시키지 않는다.
원본을 확보한 다음 명시적인 새 review를 수행한다. 자동 retry/rebase/apply/source 등록은 없다.

`examples/data_material_c3/inspect_capsule.py`는 별도 프로세스 read-only 사용 예이고,
`tests/data_material_c3/cold_reader.py`는 owner 생성·쓰기·Job 제출을 금지한 실제 수용 검사이다.
