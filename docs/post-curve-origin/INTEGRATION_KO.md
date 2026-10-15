# 구현 계약·통합 경계

## 기준 및 권한

입력 ZIP은 3,039,198 bytes, SHA256 `c31945ac050083c00e6b2e65b153bce8d5635aa18a8a5973d328892c96940fe3`이다. 첨부 SOURCE_MANIFEST의 528개 원파일을 크기/SHA256/Git blob SHA1로 대조한다. 기준 public blob은 `3ba7c97cb7c5de496a1b2ac7fdf8d83c0dc7dfad`, upstream gitlink는 `3e48bf6138f495299f45b1af254bfb4aaff307b8`이다. 로컬 diff 생성을 위한 synthetic git commit은 해당 public commit 자체가 아니다.

사용자가 알려준 이후 main `4dac8c2`는 이 작업에서 취득·검사하지 않았다. 패치는 첨부 기준에만 검증하며, 이후 Post 의미 보호·Expert/Numerical·R2/Runner·다른 담당 변경을 덮지 않는다. 새 공통 backend/store/route/schema, 새 reader/solver/곡선 수학, Report engine 수정은 없다. GitHub 게시나 다른 담당의 검토·Windows 실행을 수행했다고 주장하지 않는다.

## 전용 파일

| 파일 | 책임 |
|---|---|
| `caelab/post_curve_origin.py` | 보존 a_row/b_rows를 정확 원행에 대응; 품질/표시/계산/구간·선언 대조; Data 기존 `_resolve`/`post_observation` 재사용; 취득값과 변환 후 값 구분 |
| `apps/desktop_post/curve_origin_native.py` | owner-thread 읽기/full saved receipt 발급/원파일 재검증/정확 native 선택/선택 복원/실패 표시 복원/기존 Windows owner handle 활성화 |
| `apps/research/post_curve_origin.py` | 기존 broker 명령 상태와 registry, 검증→선택→활성화 분리; 응답 유실 시 동일 ID 조회; 기존 launcher/claim 사용 |
| `apps/research/post_curve_origin_ui.py` | 기존 CurvePlot에 명시 버튼; A/B bracket 선택; 읽기 전용 Data ReferenceContent; 5basis+편집+원행+창 생존 callback guard |
| `examples/post_origin_return.py` | 기존 예제의 명시적 작은 Data 준비 후 두 원행 조회/서비스 종료·재개방; native fixture로 가장하지 않음 |
| `tests/test_post_curve_origin*.py` | core/retained Data, 실제 VTK+scripted owner, broker/launcher doubles, Qt 조건부 검사 |

## 공유 변경은 integration.patch만

`workspace.py`의 세 operation/dispatch와 기존 selection 저장·복원 hook, `bridge.py`의 검증된 owner-window 활성화 capability, `native_commands.py`의 operation allowlist, `desktop.py`의 작은 `--curve-origin` 분기와 기존 measurement launch 환경 재사용, `post_window.py`의 두 줄 연결이다. 공유 파일 전체본은 배포하지 않는다. `product.patch`는 새 전용 파일만 추가한다. 두 patch는 source bytes와 일치해야 한다.

`apps/desktop_post/startup.py`와 native SDK/runtime은 첨부 528개 원문에 없다. 기존 launcher가 사용하는 경로와 진짜 `CAE_POST_MEASUREMENT` full-origin 환경을 유지하지만, 실제 bootstrap/SDK/Exit의 동작을 이 인도에서 실행 검증하지 못했다. root의 실제 기존 배포본/설치와 합쳐야 한다.

## 실제 명령 계약

모든 명령은 기존 `document_command`의 current document/session, expected_generation, capability, exact command ID 및 native DispatchGate를 통과한다. 공개 IDs는 owner를 찾는 단서일 뿐 host token을 얻는 증명이 아니다. 등록 nonce/비공개 owner token 계약을 변경하지 않는다.

* `post.curve_origin_read`: `object_ref, revision, table(a|b|aligned), row_index, expected_view_generation`. 실제 저장·적용된 v3 comparison만 읽는다. bounded 기존 `curve_native.sample` 페이지로 양쪽 B를 포함한 원행을 수집하고 실제 `selected`를 다시 대조한다. 결과 `ORIGINALS_READ`는 검증된 원행 target과 project/workspace 핀, generation/view_generation을 포함하며 선택 명령은 아니다.
* `post.curve_origin_verify`: `target, expected_view_generation`. 정확 저장 measurement, 현재 owner 경로/ID/record/초안, 전체 결과·기존 원결과 의존 및 실제 native samples를 확인한다. 결과 `SOURCE_VERIFIED`는 target/origin hash, object/revision/result SHA, 실제 PID, selection, row/raw, 세대, `clock_changed:false`이다. 읽기 검증과 창 활성화를 섞지 않는다.
* `post.curve_origin_select`: `target, verified, expected_view_generation`. 동일 검증을 다시 수행해 영수증 전체가 일치할 때만 기존 source/view를 표시하고 원 component/axis/block/row를 선택한다. 실제 차트 속성 readback과 selection input을 확인한다. 결과 `SOURCE_SELECTED`는 exact selection hash와 변경 후 세대이다.

현재 GUI callback에서는 위 단계 사이마다 비교 doc/session/object/revision/preview, 로컬 edit serial, 원행 선택 serial, host/plot 생존·미저장 여부를 확인한다. worker는 한 단계만 수행한다. 알려지지 않은 응답/세션 교체/늦은 callback으로 자동 재전송하지 않는다.

`document.activate`는 이미 설치된 같은 native owner의 private callback이 있을 때만 노출한다. request의 HWND/실행 경로/명령 문자열을 받지 않는다. owner GUI thread에서 기존 native_controls가 가진 정확 handle의 PID/thread를 대조한다. Windows foreground가 확인됐을 때만 `ACTIVATED`; 그렇지 않으면 `NOT_PERFORMED`이다.

## origin 종류를 합치지 않은 이유

1. `curve_native.selected()`의 native origin은 5개 필드의 간소 원참조이다. 이 객체는 수정하지 않는다. `saved_origin`은 **현재 owner의 실제 저장 project 안에서** saved record/draft/result pins와 원결과 의존을 검증한 후 별도로 발급한다. `measurement_snapshot`/새 export를 부르지 않는다. 저장하지 않은 프로젝트는 거절한다.
2. Data origin은 `reference/response/response_sha256` 그대로이며 기존 Data owner와 `_resolve`를 사용한다. job/input/result/response의 정확 retained 참조를 두 번 확인한다. Data에서 기존 full measurement 계보를 읽을 수 있을 때만 별도 `measurement_lineage` target을 만든다. CSV row와 실제 native row의 기존 mapping을 재검증한다.
3. Report `read_source`는 Report immutable binding용이고 `saved_post_result`는 3D filter/comparison용이다. 원자료 복귀를 위해 fake PNG/Report asset을 만들지 않는다. 검증 구조의 공통 취지는 참고했지만 engine/등록/저장 계약을 재작성하지 않았다.
4. source_ref/revision/row/해시는 provenance이지 실행 권한이 아니다. launcher 실행파일/service URL은 현재 기존 desktop context에서만 얻는다. full origin이나 source 경로를 executable로 사용하지 않는다.

## 저장 및 복구 정책

기존 analysis object에 `selection_context.kind=post_curve_origin`, owner-local target, `selection`, `selection_revision`, `selection_hash`만 저장한다. 새 full origin의 session/PID를 권한으로 재사용하지 않도록 제거한다. 원 measurement record와 선택 값은 다음 저장본에서 재대조한다. 사용자 일반 point/row 선택이 새로 들어오면 이전 context를 제거한다.

새 세션에서는 실제 현재 저장본과 owner의 새 session/PID로 origin을 다시 발급한다. 현재 적용 record와 저장본이 다르면 과거 record를 몰래 최신값으로 대체하지 않는다. 비교가 다른 프로젝트에서 가져온 간소 native origin뿐인 경우 자동 fullpin 합성이 불가능하므로 거절하고 원저장본에서 다시 명시 선택해야 한다. 이는 새 project locator/store를 추가하지 않는 작은 구현 선택이다.

검증 후 Fetch 도중 원 PVD frame/sidecar가 바뀌는 경우를 잡기 위해 기존 의존 검증을 읽기 전후 반복한다. 이것이 native OS 파일 잠금이나 원자적 cross-process transaction을 제공한다고 주장하지 않는다. 실제 ParaView/파일시스템 수용은 별도이다.

명령 실패 시 object/selection과 adapter가 만진 view/representation 속성·활성 source/view를 복원하고 이번 요청이 만든 view/representation/layout만 정리한다. 원 source/reader와 사용자 창은 삭제하지 않는다. 복원 자체가 실패하면 복원 미확정으로 반환한다. 세대 숫자는 소급하여 낮추지 않는다. 이미 실행된 명령에 대한 UI 닫기는 취소 증거가 아니다.

## 예제

`python -m examples.post_origin_return <새-출력-디렉터리>`는 기존 `examples.post_curves.create`로 명시적 1회 Data import/snapshot을 준비하고, 복귀 단계에서 신규 작업 0으로 두 원행을 읽고 서비스 재개방 뒤 동일성을 확인한다. fixture 준비와 읽기를 혼동하지 않는다. A는 계산 절차를 보이는 제조 예제 곡선이고 저장 native 측정은 아니다. 원 Data 예제의 quantity는 미선언이므로 비교 recipe에 force를 **명시 선언**한다. 원 Data 응답/해시는 고치지 않으며 기존 `configured`의 UNKNOWN 경계 안에서만 사용한다.

`examples/post_origin_return_raw/`는 요청 ZIP의 작은 공개 VTU/PVD/CSV 원문이다. runtime receipt/project/fullpin이 아니고 단독으로 native 완료 증거가 되지 않는다. 거기에 들어 있는 NativeNodeId와 VTK index도 다르다.

## 참고한 원문과 외부 API

첨부 `REQUEST.md`, `README.md`, `AUTHORITY.md`, `API_MAP.md`, `SOURCE_MANIFEST.json`, `SYMBOL_INDEX.json`, source의 `CURRENT_STATE.md`와 관련 정책·주 구현을 기준으로 작성했다. API_MAP의 조합 제안은 사용자 승인된 새 schema로 취급하지 않았다.

공식 ParaView selection 구현: https://www.paraview.org/paraview-docs/latest/python/_modules/paraview/selection.html — SelectIDs는 process/index, SelectCompositeDataIDs는 flat block/process/index를 받는 기존 API이다. 행을 solver global ID로 취급하지 않는다.

공식 ParaView v5.13.3 proxy XML: https://raw.githubusercontent.com/Kitware/ParaView/v5.13.3/Remoting/Views/Resources/views_and_representations.xml — `CompositeDataSetIndex`, `AttributeType`, `XArrayName`, `SeriesVisibility`의 native domain을 확인한 뒤 사용한다. 설치 버전의 실제 domain이 맞지 않으면 거절하며 새 차트/reader로 우회하지 않는다.

Microsoft SetForegroundWindow 계약: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow — foreground 제한을 우회하지 않고 실제 foreground 결과로 활성화 상태를 구분한다. 문서 확인은 실제 Windows 실행 증거가 아니다.
