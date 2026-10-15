# C2 — 선택 후보 상세근거 CAPTURE의 owner CAS 교정

요청: `PRO-NUMERICAL-DETAIL-20261015-01-C2`.
정확 기준: 원 `e2f95b2` 두 첨부 → 이전 공식 인도 → C1 공식 인도.
C1 ZIP SHA256: `091f9f9f4354d1ceff9e1194c860486ffb74a3eeb8bd5592728a804c96d22e6d`.

## 교정 범위

C1의 exact candidate/선택 attempt/raw·curve/holdout/실패 보고 구조는 유지한다. C2는 `numerical.evidence.capture`가 실패 후 동일 명령을 재시도할 때 다른 창의 미승인 Plan을 저장하는 경합만 교정한다. evaluator/JobManager/저장기/owner/public command signature를 교체하지 않는다. GUI·Report 표현, Data compiler/coordinator, 공통 schema/서비스 파일은 변경하지 않는다.

기존 `PRESERVING` receipt 존재만으로 generation 검사를 건너뛰던 경로를 제거했다. 원 fit/Plan hash를 현재 값으로 고치거나 `expected_generation`을 최신값으로 바꾸어 재승인하지 않는다. 이전 C1 완료 receipt는 계속 읽을 수 있다. CAS capsule이 없는 C1 미완료 `PRESERVING` receipt는 안전한 재시도 범위를 증명할 수 없으므로 `STALE_CAPTURE`로 거절한다. 이를 성공이나 0으로 복구하지 않는다.

## 상태별 동작

| 상태 | 같은 요청의 결과 | owner 쓰기 |
|---|---|---|
| 최초 CAPTURE | 현재 session·generation과 실제 owner/디스크 상태를 확인하고 근거 저장 | 승인한 정확한 상태만 저장 |
| 실패, CAPTURE 자체의 snapshot registration만 있음 | 동일 session/generation/args/command ID로 재시도 | 최초 pending 상태만 저장; generation 추가 증가 없음 |
| 실패 후 peer update/new run/Undo/Redo/다른 저장/외부 working 변경 | `DetailEvidenceConflict`, `code='STALE_CAPTURE'` | 없음 |
| `_save`가 commit했으나 응답 기록/반환/working 갱신이 유실됨 | exact original saved revision/ref를 검증해 과거 결과 회수 | 없음; receipt도 다시 쓰지 않음 |
| 완료 response가 이미 있음 | exact immutable ref 검증 후 저장된 response 그대로 반환 | 없음; `owner.read()`조차 호출하지 않음 |
| revision 폴더는 완성됐으나 manifest 게시가 실패함 | 미완료/UNKNOWN. 자체 pending 상태가 그대로면 명시 재시도 가능 | 증명된 원 pending만 새 revision으로 저장 |
| 같은 ID에 session/generation/args 중 하나가 다름 | 기존 request signature 충돌 | 없음 |

`new run`과 `document.save`는 항상 generation을 올리는 작업이 아니다. 따라서 generation 숫자만 비교하지 않는다. raw owner 전체의 `canonical_hash`에는 draft, title, runs, input revision, `_undo`/`_redo`, saved fingerprint와 disk revision, 기존 publication witness도 들어간다. Undo→Redo로 내용만 같아지는 ABA도 승인 범위를 되살리지 않는다. 별도의 manifest와 working.json 해시로 in-memory owner가 모르는 외부 변경도 거절한다.

원 저장기는 `document.save` 직후 working.json을 갱신하지 않을 수 있다. C2는 이 경우를 외부 편집으로 잘못 차단하지 않도록 기존 cold-open과 동일한 **검증된 saved revision fallback**만 최초 승인 상태로 인정한다. 실제 working 파일 해시도 capsule에 별도 고정한다. retry 시 이를 임의 새 값으로 교체하지 않는다.

## 기존 저장 트랜잭션 안의 commit 증거

기존 commands receipt에 작은 `capture_scope`를 저장한다. 승인 owner identity/session/generation/input revision, 승인 상태와 정확한 pending 상태의 해시, 승인 시 manifest 및 working 해시를 담는다. `PREPARED`는 자기 snapshot 등록 전/등록 write 응답 유실을, `REGISTERED`는 등록된 정확 pending 상태만 허용한다. 원 Plan이나 evaluator inputs는 수정하지 않는다.

`CandidateDetailMixin._retain_inputs`의 시작에 2줄 hook을 추가했다. 기존 comparison/evidence/run retention 변환 전에 pending 상태를 검사하고, 해당 CAPTURE의 `_save` 호출 안에서만 provisional revision locator를 receipt에 기록한다. 명령별 witness는 저장기가 만든 **saved copy**의 private `_candidate_evidence_publications`에 들어간다. pending working document에는 commit 전에 넣지 않는다. 기존 manifest가 여전히 유일한 게시 지점이다.

따라서 orphan revision과 다른 창의 나중 일반 저장은 해당 CAPTURE의 commit으로 오인되지 않는다. 응답 유실 복구는 현재 manifest에 게시된 witness 계보와 최초 exact revision의 witness·assets·snapshot·선택 refs를 함께 확인한다. 나중의 peer 저장이나 다른 후보 CAPTURE가 있어도 첫 revision/ref를 회수한다. 현재 draft/generation/dirty/saved_revision을 과거 값으로 되돌리거나 새로 저장하지 않는다.

hook은 scoped `ContextVar`로 CAPTURE의 해당 저장 호출에만 적용되고 `finally`에서 해제된다. 새 coordinator, DB, provider, 저장 엔진 또는 공통 owner transaction은 추가하지 않았다. 다른 owner/session이 같은 작업 폴더를 계속 동시에 쓰도록 지원을 확대한 것도 아니다. 기존 단일 controller/owner lock과 manifest CAS를 유지하며, 확인한 외부 상태 변경은 fail-closed로 거절한다.

## 새 owner/process와 경로 이동

기존 request signature의 session은 변경하지 않는다.

- 같은 session identity로 복원한 owner/process이고 저장된 pending capsule이 정확히 같으면 미완료 쓰기를 재시도할 수 있다.
- 서비스 재시작으로 **새 session**이 생겼으면 옛 pending 요청의 저장 승인을 승계하지 않는다. 같은 command ID에 새 session/generation을 넣어도 signature 충돌이다.
- 이미 완료됐거나 exact commit을 증명할 수 있는 요청은 새 owner/session에서도 **원 signature 그대로** 읽기 전용 회수가 가능하다. current owner를 열거나 재저장하지 않는다.

복구된 response의 `document`는 해당 과거 CAPTURE의 상태다. 현재 편집 상태의 갱신 명령이 아니다. GUI는 이 응답으로 현재 편집 버퍼를 덮지 말고, 표시를 갱신할 필요가 있을 때 별도의 기존 document read로 현재 상태를 읽어야 한다. GUI 코드 자체는 C2에서 변경하지 않는다.

실패/conflict 후 저장하려면 사용자가 현재 상태를 읽고 검토한 뒤 **새 command ID와 현재 session/generation**으로 명시 요청한다. C2가 이것을 자동 수행하지 않는다. peer가 이미 상세근거까지 명시 저장한 경우 새 요청은 그 검증된 ref를 읽기 전용으로 사용할 수 있다. 옛 command ID는 계속 stale로 남는다.

## 호출과 호환성

공개 CAPTURE payload와 command signature는 C1과 같다.

```python
from caelab.numerical_candidate_evidence import CAPTURE, DetailEvidenceConflict

try:
    response = owner.command(document_id, CAPTURE, original_arguments,
        session_id=original_session_id,
        expected_generation=original_expected_generation,
        command_id=original_command_id)
except DetailEvidenceConflict as error:
    assert error.code == 'STALE_CAPTURE'
    # 현재 Plan을 자동 저장하거나 generation/command ID를 바꾸어 자동 재시도하지 않는다.
    # 기존 read를 통해 현재 상태를 표시하고 사용자의 새 명시 동작을 받는다.
```

기존 Python owner, generic Workbench document-command, Client wire format, CLI의 경로가 같은 core를 호출한다. C2의 CLI/service 검사는 기존 C1 좁은 in-process Client/Workbench dispatcher를 실행한 것이며 실제 HTTP 서버나 Windows GUI 검사가 아니다.

## 적용

`product.patch`는 **C1 완료 복원본**에 대한 전용 파일의 증분이다. 공유 변경이 없어 `integration.patch`는 제공하지 않는다. C1 integration.patch를 대체하거나 원본 `e2f95b2`에 C2를 바로 적용하지 않는다. root의 GUI/main `eb18588` 파일을 기준으로 만들거나 덮어쓰지 않았다.

```text
git apply --check /path/to/C2/product.patch
git apply /path/to/C2/product.patch
```

전용 core 두 파일과 tests/docs의 실제 내용도 ZIP에 있다. patch 적용과 전체 전용 파일 복사는 대안이며 둘을 연속으로 수행하지 않는다. C1 core가 이미 로컬 교정됐다면 `FILES.json`의 기준 hash와 hunk를 대조해 병합한다. 공유 파일을 통째로 교체하지 않는다.

## 검사

C1의 `_numerical_candidate_detail_support.py`, C1 core tests의 `complete` helper를 그대로 재사용한다. 합성 대수 evaluator인 기존 DetailHost에서 실제 fit engine, JobManager, owner 명령, 저장 revision 및 결과 reader를 실행한다. 파일 write fault와 정해진 return-loss boundary만 주입한다. 이것을 FELUPE 계산이라고 부르지 않는다.

```text
python -m pytest -q tests/test_numerical_candidate_evidence_c2_repro.py tests/test_numerical_candidate_evidence_c2.py -k "not moved_storage" -o faulthandler_timeout=30
python -m pytest -q tests/test_numerical_candidate_evidence_c2.py -k moved_storage -o faulthandler_timeout=30
python -m pytest -q tests/test_numerical_candidate_evidence_c1.py
python -m pytest -q tests/test_numerical_candidate_evidence_consumers_c1.py tests/test_numerical_fit_lineage_c1.py
python -m pytest -q tests/test_numerical_candidate_detail.py tests/test_numerical_candidate_detail_boundaries.py
```

전용 테스트는 사용자 원 반례, 자체 등록 전후 IO 실패/응답유실, peer edit/newrun/save/Undo/Redo, orphan/commit 구분, session/signature 변조, 실제 별도 Python process 5경로와 한글 경로 이동, 새 current owner 미접근 tripwire, immutable 원값 보존, 동시 동일 요청의 저장 1회, CLI/service stale gate를 검사한다. `DetailHost`는 종료 시 기존 JobManager의 joined를 확인한다.

관측 수치와 실행 실패/중간 timeout·최종 분리 실행 로그는 인도 `DELIVERY.md` 및 `evidence/`를 따른다. Windows/FELUPE/PySide6와 사용자의 Windows 검사 결과를 C2 로컬 통과로 계산하지 않는다. FN08/18~24 전체 잔여, Data 파생 표본 독립성, holdout 합격과 공학 승인은 이번 교정의 완료 대상이 아니다.
