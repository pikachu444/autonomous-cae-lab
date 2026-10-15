# C2 최소 owner/projection 계약

## 두 identity와 검증 순서

편집 identity는 사본 document/input/revision이다. 실행 identity는 원 document/input/job/candidate/selected attempt와 immutable 결과다. 원 args/result/fit snapshot/evidence를 문자열 치환하지 않는다.

`portable_project_execution.py`의 선언 파일은 기존 Numerical revision의 manifest 자산이다. 원 input JSON과 job JSON의 **raw bytes SHA**를 저장하고, original input draft SHA·job operation/arguments·terminal state/error를 교차검사한다. 각 hop은 실제 source scope → target project, 원/새 document·input·revision, source logical-run SHA → typed projection SHA를 기록한다. 실제 `_Fork` 출력과 allowlisted typed-path replay 결과가 같아야 한다. copy-of-copy는 원 raw 자료를 재작성하지 않고 hop을 추가한다. 일반 save는 경로만 바꿔 같은 proof bytes를 재보존한다. 무제한 lineage/파일 읽기를 하지 않는다.

검증은 현재 owner가 manifest로 승인한 정확한 run과 proof link인지 먼저 확인한다. 해당 파일의 raw hash, 원 job/input, projection hop, 현재 input/args, 원 result digest, saved candidate snapshot/selected attempt를 이어서 확인한다. informational `portable_origin`만으로는 통과할 수 없다. 원 scope/map/input/result 중 하나라도 모순이면 fail closed다. 이것은 기존 unsigned file-hash 저장 계약의 검증이며, 저장소 전체를 다시 위조한 공격자에 대한 전자서명이나 외부 공증이라고 주장하지 않는다.

`execution_read`는 **read/result만 있는 현재 owner의 읽기 facet**이다. owner/store/command coordinator가 아니다. 기존 Numerical `_frozen_input`, 상세 입력 검증, `_verified_chain`, evidence reconstruction을 원실행 데이터에 대해 그대로 수행한다. 상세 결과의 source는 현재 navigation ref, execution_source는 원 ref로 구분하며 original_plan/fit_input/trial values는 원래 데이터다. immutable evidence snapshot은 원 source를 유지하고 evidence_reference의 외부 navigation source만 검증된 사본 ref다.

기존 `storage.revision_read_scope`를 한 읽기 호출에 재사용해 동일 immutable revision의 반복 검사를 공유한다. 요청 간 영속 캐시는 없고, 저장/CAPTURE 승인 scope를 대체하지 않는다. 다음 독립 읽기는 다시 파일을 검증한다.

## pending 및 published evidence

`portable_project_evidence.py`는 acknowledged candidate_evidence row와 해당 `candidate_evidence/H*.json`를 함께 수집한다. 원 binding/canonical digest/원후보/attempt를 기존 C2 함수로 재검증한다. pending REGISTERED의 row 누락·owner 모순, completed ref 또는 publication witness 모순도 검사한다. 수집 대상은 해당 owner의 명시 CAPTURE journal뿐이며 arbitrary path/계정/UI를 수집하지 않는다.

raw pending snapshot은 사본 owner의 기존 candidate_evidence 폴더에도 발행한다. 아직 retained_revision이 없는 행을 임의 saved로 만들지 않는다. 원 저널은 `portable_execution/history`의 HISTORY_ONLY 자료다. `_candidate_evidence_publications`는 새 owner active witness에 이식하지 않고 별도 history로 남긴다. 사본의 명시 save/CAPTURE는 기존 C2 gate/savehook를 사용한다. snapshot을 저장할 때 canonical 검증은 유지하고, portable 자료는 원 raw LF/CRLF serialization을 byte-copy한다.

원 `_capture_scope`, `_capture_current`, `_record_capture_publication`, `_CAPTURE_SAVE`의 승인 계산과 publication/recovery 판정은 변경하지 않는다. `_recover_capture_publication`에서는 기존 evidence_reference를 owner-aware로 포맷하는 호출만 변경한다. 기존 session/CAS/hash/동일 command 재시도 검사는 그대로다. acknowledged 보존 컨테이너를 실제 published candidate evidence revision으로 받아들이지 않는다.

## 기존 Client/HTTP/GUI 경계

기존 Client의 `numerical_candidate_detail`은 파일 owner가 아닌 `document_read/result`를 이용한다. 서버 Numerical `_public`은 portable run에 **검증된 `portable_execution_read` 읽기 정보만** 추가한다. persisted working/saved 내용이나 fingerprint는 바꾸지 않는다. 원 실행 input/job/result의 검증은 서버의 실제 파일 owner가 수행한다. 클라이언트는 현재 logical-run SHA와 읽기 정보의 원 run·원 result digest를 대조한 뒤 같은 기존 상세 reader를 사용한다.

새 endpoint/API command가 없다. GUI·Client·기존 CLI 요청 adapter·HTTP가 기존 문서/명령 경로를 쓴다. 서버 CAPTURE/report/adoption은 이 public 읽기 필드를 권한으로 믿지 않고 실제 owner retained 파일을 다시 검증한다. 일반128KiB/upload16MiB/create8MiB body cap은 수정하지 않는다. 큰 binary/CSV 자료는 public projection에 포함하지 않는다.

`evidence_reference(document_id, revision, snapshot, *, owner=None)`의 owner 인자는 기존 호출과 호환된다. native snapshot/doc ID가 같으면 기존 호출도 가능하다. portable의 source가 다를 때는 실제 owner가 필요하다. 내부 CAPTURE/recovery/resolve 호출은 모두 실제 owner를 전달한다. 임의 old/new 문자열 치환용 함수를 제공하지 않는다.

## 전용·공통 소유

전용 수정은 portable_project*, connection_graph* 및 전용 tests/examples/docs다. 추가한 실제 typed path는 frozen observation_source.data_source와 Material adoptions[].candidate_evidence다. 기존 relation 명령/취소/CAS/배치 로직과 Qt 창은 바꾸지 않는다. 새로운 도메인 editor도 없다.

공통 C2 hunk는 Numerical 두 파일의 읽기 dispatch, public-read projection, 기존 savehook의 proof/evidence retention과 기존 evidence 소비자의 exact source 경계다. evaluator·threshold·holdout 판단·lazy retention defaults를 변경하지 않는다. 원 C1 common5는 root 미적용 상태였으므로 combined integration.patch에 그대로 포함한다. 동시 root 변경은 hunk 검토로 병합하며 전체 shared 파일을 교체하지 않는다.

Data C01 raw-cell capsule와 related-save API는 여전히 미확정이고 CAPSULE_CONTRACT=NOT_INTEGRATED다. 별도 Numerical 원실행 보존 층을 그 API인 것처럼 표시하지 않는다. FN26 remote/Runner 및 다른 팀 provider/native/GUI 코드는 작성하지 않는다.
