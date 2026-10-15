# Data / Material C2 — 실행 API와 보존 계약

요청: PRO-DATA-MATERIAL-DELIVERY-20261015-01-C2. 이 문서는 C1 API에 추가되는 계약이다.
새 owner, transaction engine, compiler, schema, Qt widget, candidate evaluator는 만들지 않는다.
아래 service는 기존 Workbench owner를 감싸며 기존 document command/CAS를 사용한다.

## 1. Keep Recovery: 작은 검토, 전체 불변 base, 원문은 별도

```python
from caelab.data_material_service import DataMaterialService
service = DataMaterialService(existing_workbench)
r = service.recovery
identity = r.owner_identity(material_document_id)
raw = {
    "editor_revision": "Material-cell-editor-23",  # 편집마다 GUI가 갱신하는 token
    "cells": [{"field_path": ["settings", "parameters", "E"],
               "position": {"row": 0, "column": 1},
               "original_value": 1000.0, "raw_text": "1e"}],
    "focus": {"row": 0, "column": 1},
}
# raw.local_draft는 선택 사항인 미전송 GUI draft이다. acknowledged base가 아니다.
# 여러 owner는 각각 자기 identity/raw로 같은 배열에 넣는다.
requests = [{"identity": identity, "raw": raw}]
preview = r.prepare(requests)
# 사용자 검토와 명시 Keep 선택 뒤에만 호출한다.
kept = r.execute(preview)
# 응답을 기다리는 동안에도 GUI 원문을 지우지 않는다. 최신 editor snapshot으로 확인한다.
close = r.close_permitted(preview, live_requests=requests)
```

`prepare`는 기존 owner의 `acknowledged_state`로 내부 전체 문서와 durable `working.json`의
정확한 일치, 현재 saved manifest·revision·fingerprint를 확인한다. public projection은
이 비교에 사용하지 않는다. `is_current_input` 하나를 제거하는 예외도 없다.
새 문서를 저장한 뒤에는 기존 save command가 게시된 saved pointer까지 working에 기록하고
인정한다. working 쓰기 실패는 saved revision을 되돌리지 않으며 정상 acknowledgement로
간주하지 않는다.

검토 응답의 `targets[].acknowledged`는 작은 `review_only: true` 요약이다. 전체 내부 문서,
명령 receipt, job/result, saved source, 실제 파일 manifest를 모두 해시한
`acknowledged_sha256`에 묶인다. execute가 owner lock 안에서 같은 전체 증거를 다시 읽어
일치하는지 확인한다. 검토 후 receipt/job/base가 바뀌면 실패하며 새 명시 검토가 필요하다.
서버에 별도 preview owner/cache/registry를 두지 않는다.

Keep가 성공한 capsule의 `acknowledged`에는 요약이 아니라 다음 원본 전체가 들어간다.

| 구분 | 보존 내용 | 의미 |
|---|---|---|
| `raw` | `1e`, 빈 문자열, invalid enum, 붙여넣기 원문·셀·field path·focus·token | 파싱·수정·적용하지 않은 GUI 원문 |
| `raw.local_draft` / `pending_local_draft` | 선택적 미전송 draft | owner가 인정한 draft가 아님 |
| `acknowledged.document` | 내부 문서 전체·draft·runs·undo/redo·참조·mutation/save marker | 검토한 acknowledged base, 현재 working과 독립 |
| `acknowledged.saved_reference/saved_sources` | 당시 정확한 revision·문서·입력·manifest hash | 원 saved source; Keep가 만든 새 revision이 아님 |
| `acknowledged.jobs` | 실제 job record·입력·상태·원 run 관계·당시 result 유무 | FAILED/CANCELLED/UNKNOWN/미결 상태를 그대로 기록 |
| `owner_commands/related_save_receipts` | 실제 저장된 JSON snapshot·원본 byte hash·명령/관련 receipt ID | `AS_RECORDED`; 조회로 자동 재조정하지 않음 |
| `acknowledged.artifacts` | 위 source/result/processing/detail/receipt의 실제 파일 복사·크기·hash | 이후 working/원본/live 결과 교체·삭제와 독립 |

cap­sule JSON, 별도 asset 폴더, 각 saved revision의 기존 manifest, 각 결과 reader의 검증을
함께 사용한다. 바깥 capsule hash만 재계산해 내부 base·원 파일 불일치를 통과시키지 않는다.
이는 저장 무결성 검증이다. 공격자가 모든 원본과 해시를 다시 작성할 수 있는 환경의
전자서명/사용자 인증을 주장하지 않는다.

`execute`는 owner별 `STORED/CONFLICT/FAILED`, `error`, `close_permitted`와
`live_buffers_must_be_preserved`를 돌려준다. 복사·부분 쓰기·readback 실패 owner는 닫을 수 없다.
성공한 다른 owner의 save/Keep는 취소하지 않는다. 완전한 capsule이 없는 asset prefix는
성공 표시가 아니다. 응답 유실 후에는 read 또는 동일 명시 execute로 검증하며 자동 stale
재시도하지 않는다. 마지막 GUI editor token 비교와 기존 실행 중·modal·native 종료 gate는
여전히 GUI/기존 owner의 책임이다. 이 API의 true가 모든 종료 gate를 대신하지 않는다.

## 2. Inspect / explicit resume / portable

```python
cid = kept["targets"][0]["capsule_id"]
inspected = r.inspect(material_document_id, cid)
portable = r.portable_payload(material_document_id, cid)
resume = r.recover(material_document_id, cid,
    identity=r.owner_identity(material_document_id), acknowledge_session_change=True)
# resume["state"] == "RESUME_READY"인 경우에만 raw를 해당 GUI editor로 명시 복원한다.
# 이 호출은 owner draft를 적용하지 않는다. BLOCKED여도 inspect로 원 base를 읽을 수 있다.
# 사용자가 명시 폐기한 경우만:
# r.discard(material_document_id, cid, identity=r.owner_identity(material_document_id),
#           capsule_sha256=inspected["capsule_sha256"])
```

`inspect.verification=VERIFIED`는 보관물의 무결성을 뜻한다. 현재 owner에 대한 resume 허가가
아니다. 같은 store, 현재 identity, 원 generation/input/content/saved reference가 맞아야 하며,
session 변경에는 별도 명시 확인이 필요하다. 다른 store·peer update/save·stale generation은
자동 rebase/apply하지 않는다. cold process에서도 원 unsaved base를 읽을 수 있다.

`portable_payload.files`는 기존 workbench root 상대경로·hash 목록이다. 기존 portable writer는
이 목록의 실제 bytes를 복사하며 복사 전후 hash를 검증해야 한다. capsule과 assets, 존재하는
explicit discard marker를 함께 보존한다. 저장 성공 refs, acknowledged base, raw/local buffer를
각각 유지하며 implicit save/apply는 하지 않는다. portable writer 자체는 이 패킷에서 새로
만들지 않았다. 한글·공백 경로 이동과 목록 기반 복사 후 검증을 전용 시험에서 실행했다.

기존 C1 capsule에 whole base가 없으면 `LEGACY_BASE_NOT_RETAINED`이다. 현재 working을 원 base로
꾸며 채우지 않으며 resume gate를 열지 않는다. 원 C1 파일은 계속 inspect할 수 있다.

기존 HTTP: `Client.data_material(operation, arguments)` / `POST /api/workbench/data-material`.
`recovery.identity`, `prepare`, `execute`, `read`, `inspect`, `portable_payload`, `recover`,
`discard`, `close_permitted`를 같은 `recovery.*` 이름으로 dispatch한다. raw는 owner당512KiB,
검토1–16owner. 이 전용 endpoint의 envelope 상한은12MiB이며 recovery 외 action은 기존2MiB이다.
일반 요청128KiB·native event2MiB 등 다른 경로 한도와 인증을 넓히지 않았다.

## 3. canonical compiler와 실제 Numerical 소비

생산자와 검증자는 계속 `caelab.data_processing_selection.freeze_fit_inclusion` /
`consume_frozen_fit_inclusion` 한 곳이다. format은 기존 `frozen-fit-inclusion.v1`, producer는
`caelab.data_processing`. `trials`, `independence`, `packet_sha256`을 유지한다.

실제 owner 경로:

```python
proposal = service.sample_policy_preview(data_id, processing_revision, "P_grid")
# proposal은 미채택 상태다. GUI가 사용자에게 검토한 entries를 보여준다.
adoption = service.sample_policy_adopt(plan_id, experiment_id, proposal,
    entries=reviewed_entries, session_id=session_id,
    expected_generation=generation, command_id=explicit_command_id)
# 다음 numerical.run은 기존 Numerical owner/JobManager 명령이다.
# owner.job_arguments(adoption['document']['draft'])가 exact experiments와
# frozen_inclusion을 canonical compiler에서 만든다.
```

전달 경로는 `Workbench fit arguments.frozen_inclusion` → 실제 `fit_model`의 Data consumer →
원 `fit_input_snapshot.inputs.frozen_inclusion` → 기존 candidate/detail/holdout reader →
immutable evidence/saved revision/report input이다. 문자열 alias나 hash 복사가 아니라 각
입력 경계에서 exact 원 packet과 실제 observation/settings/policy/DAG를 검증한다.

Numerical의 기존 `fit_inclusion` → `snapshot.inclusion_packet`은 별도 **legacy** 경로로 남긴다.
canonical 관측에 원 packet이 없거나 둘을 같이 전달하면 차단한다. legacy NOT_VERIFIED를
canonical VERIFIED로 바꾸지 않는다. 전용 `data_processing_consumer`는 얇은 운반/소비 adapter일
뿐 compiler·collector·detail evaluator가 아니다.

원 packet의 작은 header를 각 experiment의 `frozen_fit_packet`에, 원 trial을
`frozen_fit_inclusion`에 deepcopy로 보존한다. 보존된 전체 header/trials를 다시 조립해 원
packet hash와 **같은 Data validator**로 읽는다. 새 packet을 freeze하거나 누락된 계보를
계산해 채우지 않는다. 추가 provenance도 deepcopy 보존한다.

| 식별자/해시 | 정확한 의미 |
|---|---|
| raw `source_rows` | 기존 integer 원행. 파생 ID를 덮어쓰지 않는다 |
| `sample_ids` | response channel별 derived sample identity |
| `coordinate_sample_ids` / `target_grid.grid_id` | 관측·driver가 공유하는 frozen 좌표 격자 |
| `response_channel_id` | 물리 응답 채널 |
| `trial.source_sha256` | **observation_source 전체**의 canonical hash |
| `trial.extra_provenance.source.source_sha256` | 원 source 파일 hash |
| `frozen_fit_packet.packet_sha256` | 전체 원 canonical packet의 무결성 |

각 output의 value contributors와 validity footprint를 구별한다. 정확한 input sample/value,
부호 있는 weight와 원 DAG를 따라간다. nearest에서 쓰지 않은 bracket은 value contributor가
아니다. 실제 value contributor를 validity footprint에서 숨겨 excluded raw를 통과시키는 경우,
raw-quality/calculation/operation-invalid 표본을 통과시키는 보간, missing DAG, observation/driver
시간 단위·grid·coordinate mismatch는 차단한다. training/holdout의 이름이 달라도 raw value
contributor를 공유하면 canonical independence가 차단한다. driver 기여자도 같은 검사에 든다.

정책 순서는 raw quality/calculation → 해당 output의 operation validity → 명시 채택한 frozen
sample policy의 inclusion/role/weight이다. display hide는 계산mask가 아니다. 새 grid 정책은
자동 채택하지 않는다. proposal·채택 당시 domain·mask 순서·stage/recipe·driver 근거가 원 packet에
남는다. 기존 row-domain 기록은 당시 계약으로 읽고 파생 sample ID를 가짜 원행으로 바꾸지 않는다.

후보 행의 `source_row=None`을 유지하면서 `sample_id`, `coordinate_sample_id`,
`response_channel_id`, `sample_weight`, `lineage_ref`, `value_lineage`, `mask_order`, `recipe_refs`를
제공한다. 상세가 없는 원 후보는 그대로이며 explicit detail_eval의 attempt ID·holdout 증거와
분리한다. 실패·취소·UNKNOWN은 원 summary/holdout 성공으로 소급하지 않는다.

## 4. 실행 예제와 확실히 구분할 범위

`tests/data_material_delivery/test_c2_workbench_chain.py`는 실제 Workbench·owner·JobManager·SciPy와
기존 Numerical candidate/evidence 엔진을 조합한다. 오직 평가식만 명시적인 별도 test backend
`P(t)=mu*t`이다. `material.felupe`를 교체하지 않는다. 공개 Windows138sample demo는 별도 불변
fixture 검사에만 쓰며 사용자 owner 채택 receipt로 취급하지 않는다.

`evidence/canonical-owner-payload.json`은 실제 테스트 owner가 채택한 작은14sample 동선의 payload다.
이는 사용자 GUI 조작 기록이나 FELUPE/engineering release가 아니다. 실제 policy command ID는
`Cactual_sample_policy`이고 demo IDs와 구별된다. 숫자형/물리 결과 benchmark는 이번 검사 대상이 아니다.

PlanVariablesWidget은 이미 Numerical GUI 팀이 작성한 실제 widget을 사용해야 한다. 이번 반환은
widget/Material embed/labels/native 창을 작성하거나 되돌리지 않는다. source와 patch를 통합한 뒤
Sol/Root가 실제 Windows 저장·Keep·닫기·재열기·선택 상세 동선을 인수 확인해야 한다.
