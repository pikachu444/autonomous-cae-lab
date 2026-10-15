# 공통 통합용 최소 owner 계약

기준 공개 소스: `90d0869ba17e19671538f11e0630e1f35799ae51`. 구현 기준은 첨부 ZIP의 실제 파일이며 `current-wip/`는 읽기 전용으로 남겼다. 본문과 원 저장 helper를 확인한 파일은 `material_document.py`, `data_document.py`, `numerical_document.py`, `retained_comparisons.py`, `research_workflows.py`, `research_operations.py`, `evaluation_definition.py`, `study_document.py`, `report_document.py`, `discussion_document.py`, `desktop_links.py`, `native_commands.py`, `workbench.py` 및 기존 Qt 진입/참조/appearance 모듈이다.

## 파일 소유와 패치

`product.patch`는 새 전용 모듈, 전용 tests/examples/docs만 추가한다. `integration.patch`는 기존 `caelab/workbench.py`, `caelab/workbench_client.py`, `apps/lab/workbench_routes.py`, `apps/research/desktop.py` 네 파일의 얇은 연결만 변경한다. 기존 파일의 CRLF를 보존했다. domain owner, storage, schema, registry, DataMaterial related_save, Runner remoteadapter, Numerical/Expert/Post/dynamic GUI는 수정하지 않는다. 소스 ZIP에는 두 패치를 이미 적용했다.

root가 공통 변경을 다른 팀의 변경과 합칠 때 아래 API 경계를 보존한다. 프로젝트 전역 CLI/MCP registry의 신규 도구 등록은 이 패치의 완료 항목이 아니다. 제공한 전용 CLI의 `--service`는 HTTP와 같은 owner를 실제 사용하며 별도의 Workbench controller를 띄우지 않는다.

## 기존 구조의 재사용

`SnapshotReader`는 실제 `workbench.research_owners()`와 각 owner의 prefix별 폴더/열린 문서 목록으로 문서를 찾는다. `owner.list()/open()/read()`는 재열기 또는 실행 복구 부수효과를 가질 수 있으므로 graph 수집에서는 호출하지 않는다. 현재 열린 문서는 owner lock 아래 사본만 읽고, 닫힌 문서는 기존 working/pointer와 저장 개정을 읽는다.

저장 검증은 `owner._verify_revision(id, revision)`을 재사용하되 파일 경로·소유자·대소문자 충돌·symlink 경계를 먼저 검사한다. Data의 `_retained_source`, 기존 `read_result(verify='all')`, comparison reader와 fingerprint도 재사용한다. root에서 공개 read-only snapshot API를 추가할 경우 이 좁은 adapter만 교체하면 된다. 이번 구현을 위해 owner 저장 형식을 새로 만들지 않는다.

Native graph는 `native_commands` lock 아래 이미 보고된 descriptor의 복사만 읽는다. `_expire`, `read`, `documents`를 호출해 live host를 몰래 끊거나 명령 상태를 바꾸지 않는다. timeout된 보고는 UNKNOWN이다. host token/등록 nonce를 반환하지 않는다. `pre.project.links`의 정확한 `job_id/origin/operation`만 기존 JobManager 기록과 대조한다. native 파일을 경로로 찾아 수집하거나 Post proxy ID를 문서 관계로 해석하지 않는다.

## 인정하는 typed 참조

| 실제 위치/형식 | 읽기 및 사본 처리 |
| --- | --- |
| Numerical `material` | `document_id/generation/input_revision/draft`의 정확한 Material 입력. 이 구조에는 **saved_revision이 없다**. 같은 입력의 재저장을 임의로 원래 고정 개정이라고 주장하지 않는다. |
| Numerical `experiments[].source` | 실제 Data document/job/input revision/hash와 응답 이름을 대조한다. |
| Numerical request `source` | 저장 domain/document, PDE 문서, 실제 Expert proposal의 서로 다른 형태를 명시적으로 분기한다. |
| request `model_source`, `method_model_sources` | 현재 방법 및 보존한 방법의 정확한 모델 참조. |
| request/method inputs `result_refs`, `experiments[].observation_ref.result` | 정확한 owner/job/input/result 식별값. 원 결과와 다르면 BROKEN. |
| 문서 `adoptions[]` | 실제 `plan_id/plan_revision/job_id/input_sha256` 계약. |
| Study `evidence[].reference` | 저장 문서/결과/비교/대화/문헌의 명시적 참조. |
| Report `sections[].asset.reference` | 보존 보고서 asset의 원본 참조. |
| Evaluation `stages[].source`, `reuse.source` | 저장 domain 모델과 재사용 결과. |
| Expert `composer.evidence[]` | 실제 참조 객체만 수집한다. authored context 문자열은 검색하지 않는다. |
| 비교 `binding.source/prediction_source` | 정확한 응답과 response hash 검증. |
| Data retained inputs / runs | 원자료 보존 receipt, 원 실행 입력, 성공/실패 기록. |

기본 graph는 현재 문서 관계와 보존 계산을 보여 준다. `include_history=true`일 때만 run의 원 draft와 Undo/Redo의 typed 참조를 추가한다. 사본 검사에서는 복원 가능한 입력 이력도 포함하므로 이력의 의존 문서 누락도 막는다. 알 수 없는 필드나 문장에 들어 있는 오래된 ID는 수정을 시도하지 않고 그대로 보존한다.

정확한 저장 참조가 유효하면서 현재 원문서의 저장 개정이 달라진 경우 NEWER_REVISION, 입력이 달라진 경우 INPUT_CHANGED, 필요한 정확한 증거가 없거나 달라진 경우 BROKEN이다. 깨진 참조를 최신 초안으로 대체하지 않는다. 참조가 없는 외부 문헌은 EXTERNAL이며 provider를 호출하지 않는다. 실제 저장 참조 열기는 기존 `desktop.open_saved_reference` → `ReferenceWindow`를 재사용한다. 현재 owner 열기는 기존 `desktop.launch_tool/desktop_links` 계약을 재사용한다.

## 사본 구성

```text
portable-project.json                 # 대응표, 명시적 포함 목록, 생성 receipt
portable/originals/<old doc>/<old R>/  # 원 저장 개정/원입력/원결과를 바이트 그대로 보존
portable/repair-history/              # 명시적 동일 바이트 복구와 손상 파일 보존
workbench/documents/<new doc>/
  document.json                      # 기존 owner pointer
  revisions/<new R>/                 # 기존 owner가 읽는 편집용 개정
    document.json / revision.json
    sources/ inputs/ jobs/ results/ comparisons/
```

문서 ID, 저장 개정, 입력 개정은 새 값이다. 원본과의 대응은 별도로 보존한다. 계산 J ID와 원자료 D ID는 새로운 독립 보관소의 소유 문서 아래 보존된 과거 기록 식별자이며, 원 보관소의 실행 큐를 다시 생성하지 않는다. 사본 두 개는 서로 다른 문서 ID를 갖는다. 같은 J ID가 남는다고 새로 실행한 계산이 되는 것은 아니다.

원본 revision 전체는 byte-identical archive다. 작업 개정의 알려진 typed 참조와 검증용 입력 hash/manifest는 새 문서에 맞게 재구성한다. Data frozen source 참조, 보존한 시험의 `observation_source.data_source`, 비교 binding도 이에 포함한다. 결과 JSON/숫자 배열 자체는 원본 값 그대로 보존하며 비교의 숫자/곡선은 그대로 두고 비교 binding과 그 checksum만 작업 사본 참조로 갱신한다. `portable_origin.execution_replayed=false`가 원결과와 새 입력 투영을 구분한다.

저장 후 owner가 만드는 새 개정은 그대로 허용한다. 초기 복사 때의 immutable inventory는 변경하지 않고, 검사는 현재 owner pointer와 새 개정의 파일들도 별도로 대조한다. 복사 완료 직후의 문서 head 파일을 고정시켜 이후 정상 저장을 손상으로 오판하지 않는다.

## 명령/응답

기존 Workbench와 Client에 동일 이름의 다음 함수를 연결한다.

```python
inspection = client.portable_inspect([data_id, material_id, plan_id])
receipt = client.portable_create(
    inspection, new_folder, approved=True,
    command_id="Ccaller_generated_unique_id",
    session_id=inspection["service_session_id"],
)
graph = client.connection_graph([plan_id], include_history=False)
checked = client.portable_verify(copy_folder)
repaired = client.portable_repair(copy_folder, relative_path, exact_file, approved=True)
```

POST 경로는 `/api/workbench/connection-graph`, `/api/workbench/portable-project/{inspect,create,verify,repair}`이다. 기존 loopback/Origin/token 검사를 그대로 거친다. create에만 8 MiB 본문 한도를 부여한다. 쓰기 요청의 알 수 없는 필드는 거절한다. 원래 Client의 임의 POST 자동 재시도는 추가하지 않았다.

`inspect`는 READY/BLOCKED, 문서·파일·소스 generation/input/pointer pin, 사용자 경고, 정확한 위치와 복구 방법을 반환한다. `create`는 현재 서비스 세션과 포함 목록/원본 파일을 다시 대조하고 정렬된 기존 owner lock을 사용한다. 새 staging → 검증 → 배타적 새 목적지 예약 → manifest 마지막 발행 순서다. 실패한 목적지는 불완전 상태가 눈에 보이며 기존 폴더를 덮지 않는다. 동시에 들어온 같은 요청과 응답 유실 후 같은 요청은 CREATED/ALREADY_CREATED와 동일 project_id로 수렴한다.

`verify`와 `repair`는 계산 명령이 아니다. 작업 사본의 파일/폴더에 숨은 symlink도 controller 생성 전에 거절한다. `Workbench` constructor의 작은 공통 gate 때문에 기존 서비스/직접 Python 재열기도 불완전·손상 사본을 우회하지 않는다. 기존 일반 보관소에는 이 gate를 적용하지 않는다.

서비스 재시작 후 예전 세션의 create는 거절하고 새 inspection을 요구한다. 서로 다른 보관소를 하나의 기본 ID 공간으로 합치지 않는다. 원 store를 찾기 위한 fallback, 환경변수/회사 폴더/SSH credential 수집, provider/solver 실행은 없다.

## UI 선택과 검증 경계

프로젝트 `cae-desktop-ux`의 WIN-COMMAND에 맞춰 주행동을 메뉴와 선택 위치의 context menu/도구 모음에 두었다. QT-PANELS에 맞춰 도크 하나와 큰 중앙 그래프/목록을 사용하고 강제 세 칸 설정 폼은 쓰지 않았다. VIS-TYPE/QT-STYLE에 따라 기존 `apply_appearance`와 폰트 fallback/팔레트를 재사용한다. 긴 이름은 tooltip을 갖고 진단 ID/hash는 별도 대화창으로 보낸다. 배치 변경은 입력 수정이나 관계 저장이 아니다.

실제 Qt render·이벤트 검사를 못 했으므로 이 선택의 시각적 적합성은 승인하지 않았다. 실행 가능한 두 크기 테스트는 인도하며 가짜 이미지나 시제품 화면으로 대체하지 않는다. 다른 담당자의 독립 검토를 수행한 것으로 표시하지 않는다.
