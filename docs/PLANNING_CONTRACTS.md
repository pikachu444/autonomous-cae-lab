# 객체와 프로그램 간 계약

2026-10-08 설계 계약. 기존 `caelab/contracts.py`, `storage.py`, `jobs.py`, `response_history.py`, `response_field.py`의 기록을 어댑터로 연결한다. 별도 범용 DB나 solver 스키마 재작성은 하지 않는다. 아래 신규 필드는 기존 기록에 없는 앱 문서·편집 버전 경계에 한정한다.

## 객체 식별과 호환

모든 앱 문서는 `{id,type,schema_version,revision,label,created_at,updated_at,units,provenance,assets,dependencies,payload,view_state}`를 갖는다. `id`는 UUID, `type`은 `prep|case|run|result|analysis|study|candidate|session|project`, `schema_version`은 major.minor 문자열, `revision`은 같은 ID에서 증가하는 정수다. `id+revision`이 불변 객체 참조이며 `label`과 파일 경로는 식별자가 아니다. 표시명은 Unicode를 허용한다. 파일 저장명은 생성 ID를 사용한다. 시안의 짧은 ID는 시연용이며 본 제품 UUID 전환 대상으로 표시한다.

`units`는 채널별 `{quantity,unit,component,location,coordinate_system,sign_convention}`와 축 정의를 보존한다. 값에 문자열 단위를 섞지 않는다. 무차원은 `1`, 미확정 단위는 `null`로 저장하고 계산을 막는다. MPa→Pa 등 차원 일치 변환은 명시한 scale/offset과 원 단위를 기록한다. 힘과 응력처럼 차원이 다른 연결은 거부한다. 경로 추론이나 LLM으로 단위를 확정하지 않는다.

`provenance`는 원본 표시명, import 시각, 원본 해시, producer 종류/버전, 실제 계산/가져옴/예측/시연 여부를 포함한다. `assets`는 `{asset_id,relative_path,media_type,byte_size,sha256,role}`다. 프로젝트 루트 밖의 외부 파일은 허용된 등록 경로와 해시를 별도로 기록하며 공유 export 시 포함 여부를 확인한다. 파일 URI는 내부 저장 경로와 표시 경로를 분리한다. 서버가 받은 임의 절대 경로나 `..` 경로는 실행/쓰기 대상으로 사용하지 않는다.

지원 schema minor의 추가 필드는 round-trip 보존한다. 알 수 없는 major는 읽기전용 진단과 변환 경로를 제공하고 조용히 덮어쓰지 않는다. native solver 덱/결과는 원 형식을 그대로 보관한다. 공통 응답은 scalar, series, field 참조와 해석에 필요한 메타데이터만 담당한다.

| 생산자 → 소비자 | 계약 | 거부/변환 |
|---|---|---|
| 전처리 → 실행기 | case ID/revision, backend ID, inputs, conditions, validation digest | 미저장 초안은 먼저 저장. 필수조건/단위/backend 누락 시 대상과 수정 위치 반환 |
| 실행기 → 후처리 | completed/partial Result manifest, run ID, input revision, response catalog | 실패 run도 로그 열기 가능. 불완전 field는 partial 표시, 완료 결과로 승격 금지 |
| 외부 ASCII → 후처리 | delimiter, encoding, skip/header, axis+channel mappings, unit/location, source hash | 미리보기와 확정 매핑 필요. 누락/비숫자/시간 역전/중복은 행 번호 진단 |
| 전처리/외부평가기 → 최적화 | 평가기 capability, 변수 path/type/bounds/units, objective/constraint/reduction/target | 도메인 밖 변수·없는 채널·수치 결측은 후보 실패. 0이나 surrogate로 묵시 대체 금지 |
| 최적화 → 다른 앱 | candidate ID, evaluation run/result, frozen parameter set, study revision | surrogate만 있는 후보는 예측 표시; 실제 해석 생성은 별도 명령 |
| 앱 → 전문가 | 선택 evidence ID/revision와 발췌·원문 위치, 허용 계산/전송 범위 | 앱 인증과 개발 Codex 로그인 별개. 허용 밖 데이터는 전달하지 않음 |
| 전문가 → 도구 | proposal ID/version, 근거, 변수/범위/예산/대상 참조, 승인 상태 | 발언 자체는 실행 명령 아님. 사용자가 편집·실행 시 동일 job API 사용 |
| 모든 앱 ↔ Workbench | 문서 참조, typed input/output ports, launch request, saved event | 파일/버전 없음·타입/단위 불일치·그래프 순환을 연결 단계에서 표시 |

## 저장과 파일 충돌

### 독립 문서의 위치·포장·이동

제품 문서는 확장자를 가진 **디렉터리 묶음**이다. 예를 들어 `인장시험.caeprep/document.json`, `assets/`, `history/`를 함께 보관한다. 파일 선택기는 이 디렉터리를 하나의 문서로 표시한다. `.caerun`, `.caepost`, `.caestudy`, `.caechat`, `.caeproject`도 같은 포장을 사용한다. 공유용 내보내기는 묶음을 ZIP으로 압축하며 가져올 때 새 위치에 푼 뒤 경로/해시를 검증한다. 시안의 단일 서버 JSON 저장은 이 제품 포장의 축소 구현이다.

| 행동 | 경로·ID·참조 규칙 |
|---|---|
| 새 문서·첫 저장 | Workbench/Study 없이 생성한다. 저장 전 초안은 `%LOCALAPPDATA%/AutonomousCAELab/drafts/{id}`에 있고 제목에 미저장 표시. 첫 저장 대화상자의 기본은 `Documents/Autonomous CAE Lab`이며 사용자가 선택한 디렉터리에 문서 묶음을 만든다. 취소하면 초안 유지. |
| 원본 가져오기 | 기본은 원본을 bundle의 `assets/`로 복사하고 상대 경로·해시를 기록한다. 큰 외부 파일의 참조만 등록은 명시적 선택이며 portable export 전 미포함 파일 목록을 보여준다. 원본 파일은 수정하지 않는다. |
| 단독 실행 결과 | 제출 전 Case와 실행 묶음을 저장한다. Run은 `.caerun/runs/{run_id}/input,logs,output,manifest.json`에 고정한다. Study가 없어도 이 경로로 완결한다. Study는 소유 Run을 같은 구조로 자기 bundle에 저장하거나 실행 묶음의 Run을 참조한다. Workbench는 소유하지 않는다. |
| 문서 이동 | 앱의 이동 명령은 bundle 전체를 복사→해시 확인→기존 위치의 이동 안내 기록 순으로 처리하고 ID/revision을 유지한다. 열린 job은 종료 후 이동한다. OS에서 옮긴 문서는 열기 때 registry의 위치만 갱신하며 동일 ID가 두 위치에 있으면 원본 위치 선택/사본 분리를 요구한다. |
| 다른 이름으로 저장 | 명시적 사본 생성으로 새 문서 ID와 revision 1을 부여하고 `derived_from`에 원본 ID/revision을 남긴다. 편집 객체 내부 ID는 새 namespace에서 재발급·관계 재매핑한다. 실행/결과는 불변 원본 참조를 유지하며 포함 복사는 해시·원 Run ID를 보존한다. 복사가 새 계산을 뜻하지 않는다. |
| 외부 참조 재연결 | 위치 registry의 ID와 요청 revision을 먼저 찾고 bundle hash로 확인한다. 파일이 없어도 표시 스냅샷/오류를 보존한다. 최신 revision 또는 비슷한 파일명으로 임의 대체하지 않는다. |

`프로젝트 루트`/`연구 루트`는 위 소유 문서 bundle을 가리키며 Workbench 프로젝트 생성을 필수로 뜻하지 않는다. 앱의 파일 선택으로 등록한 경로만 서버의 저장 권한 경계로 사용한다. 네트워크 요청의 임의 경로 문자열이 파일 선택 권한을 대신하지 않는다.

문서 저장은 `PUT /documents/{id}`에 `expected_revision`과 payload를 보낸다. 새 문서는 expected=0, 존재 문서는 읽은 revision이다. 서버는 파일 잠금 내에서 revision 비교→임시 파일 쓰기→원자 교체를 하고 저장된 revision/hash를 응답한다. 실패하면 화면 dirty를 유지한다. 409는 현재 revision·수정 시각·충돌 필드를 반환한다. 사용자는 최신 읽기, 별도 사본 저장, 차이 비교 후 재적용을 고른다. 무조건 덮어쓰기와 백그라운드 병합은 없다.

저장할 때 이전 revision 파일/manifest는 보존한다. Undo는 미저장 편집 스택을 되돌린다. 이미 저장한 revision을 되돌리는 명령은 과거 내용으로 **새 revision을 저장**한다. history 삭제는 본 단계 기능 밖이다. `view_state`는 선택 ID, 열린 문서, 축/카메라/프레임, 접힌 패널을 갖되 해석 입력 fingerprint에서 제외한다.

닫기 때 dirty면 저장 후 닫기/버리기/계속 편집을 제공한다. 서버가 끊기면 저장을 성공으로 표시하지 않는다. 자동 복구 초안은 별도 draft로 보관하고 확정 저장과 구분한다. 재개 시 서버 기록과 draft revision을 비교해 충돌 여부를 먼저 판단한다. 원본 외부 파일 해시가 바뀌면 저장된 스냅샷 열기/새 자료로 가져오기/경로 재연결을 제공한다. 원본을 자동 덮어쓰지 않는다.

## 실행 상태와 결과 소유

실행은 `draft → validating → queued → running → succeeded|failed|cancelled`다. `cancel_requested`는 queued/running에서의 요청 상태이며 프로세스 종료를 확인해야 cancelled가 된다. 연결 단절은 running을 failed로 바꾸지 않고 `connection_lost` 표시와 job 재조회로 복구한다. 프로세스 존재를 확인할 수 없으면 `unknown`으로 표시한다. backend가 지원하는 checkpoint는 `interrupted`와 재개 가능 위치로 기록한다. 미지원 backend는 새 run을 생성한다.

제출 시 입력 revision, source hash, solver 버전, command/env의 비밀을 제외한 실행정보, 자원/허용 범위, 연구/후보 관계를 고정한다. 편집 중인 mutable 객체를 계산이 직접 참조하지 않는다. idempotency key는 한 제출의 중복 클릭만 합치며 명시적 재실행은 새 key/run이다.

결과는 run이 소유한다. 기본 저장은 연구 루트 아래 `runs/{run_id}/input`, `logs`, `output`, `manifest.json`; 외부 import는 `imports/{import_id}`다. 최적화는 개별 run을 참조하고 후처리는 결과를 바꾸지 않는다. backend 원본 파일은 보존하고 변환 응답은 원본과 같은 출처를 갖는다. 실패 시 partial output을 지우지 않는다. GUI 닫기는 계산 취소가 아니다. 앱 종료에서 계속 실행/취소 요청/돌아가기를 보여준다.

재실행은 실패 run과 수정 Case를 모두 가리키는 새 run이다. run 내부 결과 파일을 대체하지 않는다. 취소와 완료가 경합하면 실제 terminal state 한 번만 확정하며, 이미 완료한 결과를 취소 상태로 재분류하지 않는다.

## 변경 영향과 Workbench

연결은 `{source:{id,revision,port},target:{id,port},binding:latest|pinned}`다. 편집 연결의 기본은 latest, 실행 기록은 항상 pinned다. 사용자가 저장하면 `document.saved{id,old_revision,new_revision,changed_domains}` 이벤트가 발생한다. Workbench는 입력 fingerprint가 달라진 하위 case/study만 stale로 표시한다. 라벨/패널/카메라 변경은 실행 fingerprint를 바꾸지 않는다.

예: prep P r3을 사용한 run R1/result X1 및 study S r2가 있다. 재료 계수 수정 후 P r4 저장 → 실행기 Case와 S는 갱신 필요. R1/X1은 r3 결과로 계속 열림. 수동 갱신 미실행이면 새 결과가 없다. 사용자가 Case 갱신/실행을 선택 → r4 기반 R2/X2 추가. S의 기존 후보는 r3 기준으로 보존하고 새 study revision에서 다시 평가한다. 단지 후처리 축 범위를 바꾸면 R/S는 stale이 되지 않는다.

그래프는 방향 비순환 연결을 기본으로 하며, 최적화 반복은 Study의 평가기 내부에 속한다. 연결 오류는 선 위 아이콘·오류 문장·해결 대상 바로가기를 제공한다. missing revision은 최신으로 임의 치환하지 않는다. 깨진 파일은 해시 일치 시 재연결, 불일치 시 새 import다.

도구 열기는 `LaunchRequest{app,object_ref:{id,revision},mode:edit|read,return_project}`다. 기존 창에서 동일 객체/revision이 열려 있으면 포커스한다. 다른 revision이 열려 있으면 별도 문서로 연다. 과거 결과 입력을 편집하려면 복제/새 revision 명령을 사용한다. 저장 이벤트만 Workbench에 알리고 중앙 UI가 종료되어도 앱 저장·실행은 유지한다.

## 전문가 대화와 실행 제안

메시지는 `{message_id,session_id,sequence,author:{role,id},reply_to,content,evidence_refs,issue_refs,status,created_at}`. 역할은 user/expert/moderator/tool/system, status는 pending/streaming/completed/failed/interrupted다. 내부 추론 전문은 저장·표시 대상이 아니다. 공유 가능한 근거와 결과만 남긴다.

사용자가 끼어들면 현재 생성 중인 발언에 중단 요청을 보내고 완료/중단 부분을 명시한다. 새 사용자 발언을 sequence에 추가하고 다음 발언이 이를 reply_to/evidence로 참조한다. 이미 나온 발언을 새 관측을 알고 있었던 것처럼 수정하지 않는다. 재시도는 같은 실패 메시지에서 새 attempt를 만들며 중복 사용자 발언을 추가하지 않는다. 미전송 입력은 draft로 남는다.

논점은 open/disputed/supported/resolved와 관련 message/evidence를 가진다. 전문가 다수 동의가 곧 원인 확정은 아니다. 진행자의 결론은 합의·불일치·필요 시험을 분리한다. 제안은 draft/reviewed/approved/submitted/running/completed/failed/cancelled 상태이며 승인 범위의 변수·예산·전송이 바뀌면 재검토한다. 계산 결과는 완료 job 참조로 들어오고 제출 영수증은 결론 근거로 사용하지 않는다.

## 결정 검증

화면 검증은 ① 두 창에서 동일 revision 편집 후 두 번째 저장이 409 ② 저장 후 앱 닫기/재열기 ③ upstream 변경 뒤 해당 의존자만 stale ④ 과거 결과 그대로 열기 ⑤ 새 실행은 수동 명령에서만 발생 ⑥ 잘못된 단위 연결 거절 ⑦ 취소 후 terminal state 확인 ⑧ 전문가 개입 뒤 reply 관계 유지로 수행한다. 시안의 구현 범위와 실제 시험 범위는 관찰 기록에 따로 표시한다.
