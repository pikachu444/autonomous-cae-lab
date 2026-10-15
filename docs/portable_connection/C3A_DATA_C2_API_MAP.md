# Data C2의 정확한 접점

| 파일 | 이 증분의 역할 |
|---|---|
| `caelab/portable_recovery_resume.py` | 기존 gate를 `validate_review`로 추출해 재사용. Data에만 검토 context를 기존 UPDATE에 전달하고, 성공/유실 응답 재시도 후 현재 보정 자료 bytes를 검증한다. Material/Plan의 명령 인자는 그대로다. |
| `caelab/portable_recovery_data_inputs.py` | 기존 archive/typed navigation/acknowledged input reader로 검증한 자료를 기존 Data owner retention에 연결한다. 새로운 owner나 입력 registry가 아니다. |
| `caelab/data_document.py` — root 최소 hunk | `_retain_inputs(..., recovery_inputs=None)` 내부 인자. 선언된 Q source/receipt/metadata만 전달되며 실제 closure·원 source 검증을 그대로 사용한다. retained input.json raw bytes를 다음 저장에도 보존한다. |
| `caelab/material_document.py` — root 최소 hunk | 기존 `data.update`에서만 추가 검토 context 허용 및 retention hook 호출. 기존 mutation marker/whole document receipt 발행보다 앞에 있다. |

공개 Workbench/Client/HTTP/GUI의 portable preview/resume 호출 표면과 응답 raw transport는 그대로다. 새 endpoint/owner/dispatcher/메뉴를 만들지 않는다. 현재 보정 자료는 `DataDocuments.prepare_job_arguments`가 반환한 calibration_sources의 retained_data_input ref와 기존 `resolve_job_source`로 검증·읽을 수 있다. 주 CSV의 기존 `document_source_preview`도 그대로다.

## 내부 Data UPDATE 인자

`{'draft': projected_acknowledged_draft, 'portable_recovery_inputs': {'preview': exact_preview, 'approved': True, 'overwrite_approved': True, 'live_buffer': exact_current_token}}`

이 인자를 raw/source 파일 경로 수집용 API로 사용하지 않는다. source ID/path 목록을 받지 않으며 같은 command/current CAS/전체 문서/buffer와 원 Q 검증을 다시 통과해야 한다. 실제 사용자 작업은 기존 portable resume를 호출한다. source-only 원문 읽기는 현재 등록/복구 승인과 별개다.

## 반환 / 실패

기존 `BUFFER_READY`의 document는 현재 owner의 검증된 retained_inputs까지 포함한다. raw와 pending local_draft는 미적용으로 반환한다. `raw_applied=false`, `job_submitted=false`, `original_recover_permission=original_discard_permission=NOT_GRANTED`는 유지한다. 저장 head는 바뀌지 않는다. 원문 복구/포커스는 Sol의 기존 GUI 구현이 이 packet을 소비한다.

ValueError/OSError 및 기존 PortableProjectError는 기존 transport로 그대로 전달한다. 실패를 읽기 전용 성공이나 새로운 BUFFER_READY로 바꾸지 않는다. 누락/변조, 현재 ID 충돌, stale whole document/권한/token, outcome unconfirmed는 원 자료를 보존하며 거절한다. 앱이 자동 다른 command로 재시도해서는 안 된다.
