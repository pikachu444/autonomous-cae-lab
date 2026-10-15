# B13 C1 — 무압력 영역과 동일 저장 member의 cold binding

요청: PRO-B13-C1-FRESH-20261015-01. 기준은 첨부 source.zip/source의 exact bytes이다.
현재 HEAD는 5757547d828ac16bf484e8a73e1b8eea722fb5b6, 공개 Law 기반은
583ad1ae473787ea580fdafcf89b01a5a6ec1e5e이다. 오래된 전체 파일 overlay는 사용하지 않는다.

## 이번에 작성한 범위

`caelab/shell_model.py`, `caelab/shell_regions.py`, `apps/desktop_pre/shell_edit.py`를
수정했다. 기존 API 호출의 기본값은 유지했다. 공통 `projects.py`는 아래 이유의
3개 hunk, 7개 추가 행만 별도 root-integration.patch로 제공한다. 공통 raw 파일은
교체용으로 제공하지 않는다. GUI, CSV/물리량 표시, 한국어/UTF-8, 기존 checker,
native Apply/writer/adapter, mesh_binding/fem_edit, Law/PDE/Post/C3A/Runner는 수정하지 않았다.
기존 네 수정 파일은 원 CRLF를 유지한다.

## 1. 영역별 0 압력

`_validate_uniform_draft`와 `_prepare_uniform_mesh`에 keyword-only 내부 정책
`require_nonzero_pressure=True`를 추가했다. 기존 단일 영역 호출은 계속 0을 거절한다.
regional validate와 prepare만 False를 넘겨 각 영역의 0/-0을 수치 그대로 유지한다.
전체 regional validate에서는 파싱된 실제 압력이 비영인 영역이 하나 이상인지 검사한다.
압력을 합산하지 않으며, 누락/미완성/비유한 값을 0이나 임시 비영 값으로 바꾸지 않는다.

실제 적용 경로는 기존 prepare_mesh → shell_region_native.Apply → 실제 참조 Python
pressure writer → shell_deck.build이다. 무압력 영역도 native 압력 객체와 요소별 0 행을
갖는다. 기존 부호, 법선 반전과 offset 연동, 참여 요소 exact coverage 검사는 그대로다.
writer를 수정하거나 0 행을 생략하지 않는다. 모든 영역 0, uniform 0, invalid raw,
변조된 0 행/누락/중복/다른 요소/잘못된 부호는 계속 차단한다.

## 2. 원 saved member와 BREP 증거

원 public ZIP은 29,632 bytes이며 SHA256은
543356fc526483866e94eadfbf21d9b1f46286c9008283370896fb758239cd6e이다.
원 `.caepre`의 `documents/B13Shell_7b144577.FCStd` SHA256은
12e0723e2da2c519859b65e5692e8461dfcb0876616490395643a4cb62b9ac5d이다.
원 Windows 실패 및 STAMP_DIFFERENCES_RECORDED 관측은 수정하지 않았다.

저장 전 runtime BREP를 새로 관측한 것은 아니다. 대신 saved FCStd의 실제 ASCII
`CurvedPatch.Shape.brp`를 가능한 runtime stream 형식으로 다시 표현한 2,620-byte
후보를 만들었고, 그 후보의 기존 `shell_model.digest`가 원 binding의
`27afc7c35af53bb1513dcc5240add61b24edbd94a794fb26694573d3974f7d27`과 정확히 일치했다.
따라서 단순한 digest 차이 추정이 아니라 **이전 SHA256으로 인증된 원문 후보**를 얻었다.

후보와 실제로 보존된 cold export(2,622 bytes)의 전체 비교에서 다른 토큰은 두 개다.
각각 analytic plane의 Y축 x 성분 `0` → `-0`이다. cold 문자열의 JSON digest는
`ae5f0ef0decb14132f2f9bcf1ad599a76a7ebb2fc20042c024cb8ca38eed61c6`이고 raw SHA256은
`9176910a038b552e2433a0befbaea45b51ac9abbc51d628fbe5ae50c8701e253`이다.
이 두 종류의 hash를 혼용하지 않는다. 후보의 raw SHA256은
`a9ff3d59cfba07d8aab116b696a80e8466fcd579c49206e8afc0a959c4dbc8c7`이다.

새 비교의 순서는 다음과 같다.

1. 원 stamp와 current stamp의 mesh ID/hash, 좌표/연결, mesh/source placement,
   source ID, 참조 객체 집합, fixed references를 기존 방식으로 비교한다.
2. BREP digest가 다를 때만 과거 digest에 일치하는 원문을 요구한다. 기존 저장
   FCStd의 정확한 Shape property member 또는 이미 보존한 인증 원문을 읽는다.
   원 digest와 맞지 않는 후보는 사용하지 않는다.
3. current export를 다시 읽어 current stamp digest와 맞는지 확인한다.
4. 인식 가능한 V1 analytic Surfaces table에서 **plane 축의 정확한 -0 토큰만**
   0과 동일시한다. 그 밖의 문자/숫자/공백은 그대로 비교한다.

일반적인 수치 tolerance, 좌표 반올림, 형상 근사 비교가 아니다. 후보 생성 단계의
15/17-digit stream 재표현은 과거 원문의 후보를 만들 뿐이며 SHA 검증 전에는 아무
허용 권한도 없다. 실제 identity 비교에는 float 변환이나 반올림이 없다. shape
orientation, topology/index/flag, plane 원점, cylinder, 비영 축 성분, 알 수 없는
surface 표현은 이 bridge로 정규화하지 않는다. 증거가 없으면 기존 stale 거절을 유지한다.
원 `_geometry`, `_stamp`, 실제 `_mesh_hash` 계산과 native 형상 isValid/참조 존재 검사는
그대로다. `_binding`뿐 아니라 `effective`의 applied.native.binding 비교에도 같은
증거 비교를 적용하며 나머지 실제 native 속성은 계속 exact 비교한다.

## 3. 공통 저장 hunk가 필요한 이유

첫 cold에서 원 saved BREP로 인증한 과거 원문이 있어도, 두 번째 저장은 이미 읽힌
새 signed-zero 표현을 저장할 수 있다. 그러면 오래된 binding은 그대로인데 그 과거
원문을 다시 구할 수 없어진다. current stamp로 binding을 덮는 대신 기존 Project.save가
`saveCopy` 전에 인증된 과거 BREP만 `shell_binding_evidence` manifest 항목에 보존한다.
기존 unpack/remember_open → Project.attach_opened가 검증된 manifest를 통해 이를 읽는다.

추가 항목은 schema `caelab-shell-brep-evidence/1`, `{historical_json_digest: exact_text}`
사전이다. 모델, native 속성, draft, applied, binding, 기존 결과를 대체하지 않는다.
restore는 원문 hash를 전부 확인한 뒤 과거 증거 cache에만 붙인다. 늦은 restore는 새
raw edit를 수정하지 않는다. 이는 별도 store/owner/solver가 아니라 기존 프로젝트의
보조 증거다. 원 `.caepre`를 직접 수정하지 않고, 사용자의 기존 명시 Save만 새 파일을 만든다.

원문 읽기 상한은 64 MiB, manifest에 보존하는 원문 합은 2 MiB다. 너무 크거나 구할 수
없는 증거를 생략해도 숫자나 binding을 만들어 내지 않으며, 해당 cold bridge는 계속
거절한다. 알려지지 않은 직렬화/실제 topology flag 변화/비영 형상 변화까지 복구하는
범용 CAD 동등성 기능은 아니다.

## 검사와 한계

최종 Linux/Python 3.13.5 검사: 지정한 13개 파일에서 **185 passed**, 그중 신규
C1 회귀 **65개**. assertion/threshold/skip을 완화하지 않았다. Native 객체 접근과
saveCopy는 명시 대역이지만 실제 production validator/prepare/stamp/_mesh_hash/
_binding/effective/native-state/Project.save/attach_opened/native_cad 및 실제 참조
FreeCAD 1.1.4 Python writer 본문은 실행했다. 37 nodes/8 S8과 원 실제 BREP/FCStd를
사용했다. 기존 input/deck와 record 불변, 재저장 뒤 새 owner, 변경 반례를 검사했다.

pressure writer SHA256은
98b9c4685192cec7f598bbdfbc7762308880ff4b3edf785a81d297d5384e5b3d이며 변경하지 않았다.
참조 geometry/material writer SHA 검사도 기존 테스트 그대로 수행했다.

원 소스에서 두 core 실패를 재현했다. 넓은 영향 검사에는 Qt 부재 4건(1 failed,
3 setup errors)과 Post 대역의 HideUnusedScalarBars 누락 2 failed가 남아 있다.
Post 2 failed는 원 소스에서도 동일하게 재현했으며 수정하지 않았다. 별도 portable
검사는 첨부에 examples/portable_connection_public.py가 없어 collection error였다.
이 결과와 초기 의존성/수집 실패 로그를 삭제하지 않았다.

Windows, 실제 FreeCAD kernel/GUI/FCStd 복원, 실제 Qt, 실제 CalculiX 실행/prepare 수용은
**NOT_RUN**이다. 이 환경에는 해당 native 모듈이 없다. 위 Python writer 검사와
보존 바이트 재현을 native 성공으로 세지 않는다. 최종 engineering qualification은 아니다.

## Root 적용과 같은 저장본의 native 확인

product.patch 적용 전 CHANGE_MANIFEST의 before SHA를 확인한다. 공통 WIP가 다르면
root가 root-integration.patch의 3개 hunk만 현재 파일에 통합한다. 공통 whole-file 교체 금지.
다른 팀 파일을 덮지 않는다. 별도 test-support에는 첨부에서 빠졌지만 동일 HEAD에서
조회하고 Git blob SHA로 확인한 원본 5개가 있다. 이미 있는 root 파일에 덮지 않는다.

보존 증거만 확인하는 명령:

```text
python -m examples.b13.c1_binding_probe <원-public-inputs.zip> <새-proof-폴더>
```

실제 native 확인은 root의 기존 Windows owned launcher 안에서, 원 ZIP에서 꺼낸
`source/design.caepre`를 그대로 지정한다. `CAELAB_B13_C1_OWNED_CHECK`를 이 요청 ID로
설정한 새 FreeCAD 1.1.4 GUI 프로세스에서 다음 함수를 한 번 호출한다.

```python
from examples.b13.c1_binding_probe import native_cold_check
observation = native_cold_check(new_owned_output_directory, original_saved_caepre)
```

이 함수는 기존 `check_in_freecad.read_saved_project`를 재사용한다. 새 geometry,
Apply/rebind/save/freeze/solver를 실행하지 않는다. 반환 JSON의
`execution == 'SAME_SAVED_MEMBER_COLD_READY'`와 draft/applied equality를 확인해야 한다.
프로세스 exit 0만으로 수용하지 않는다. 이 native 함수의 실행은 이번 인도에서 NOT_RUN이다.
0 영역 native Apply와 실제 재저장/새 프로세스 확인은 root의 같은 소스 수용에서 별도 기록한다.

native generalized rotation DOF, 완전한 MPC/이산 반력, B32R 50IP native COORD,
B13 전체 및 상위 FN/engineering 승인은 이번 두 교정으로 닫지 않는다.

## 이후 Windows 통합

위 NOT_RUN은 Pro 작성 당시 기록이다. Codex 통합 뒤 같은 원 `.caepre`를 새 FreeCAD 1.1.4
owner에서 한 번 읽어 초안·할당 일치와 해석 준비 상태를 확인했다. 원 형상·37절점/8 S8
메시·참조와 원파일은 그대로이며, 적용·재결합·저장·솔버 호출은 없었다. 테스트 창은 종료했다.
실행 기록은 `_workspace/delivery-cad-pre/b13-c1-native-windows/summary.json`에 있다.

후속 소스 검토에서 선택적 BREP 증거 때문에 기존 저장이 막힐 수 있는 두 경계도 보완했다.
Codex는 기존 manifest의 8 MiB 한도를 넘기지 않도록 선택적 증거만 생략하며, 원 manifest
자체가 큰 경우의 거절은 유지했다. Sol은 과거 FCStd XML을 읽지 못하면 증거를 생략하도록
예외 처리했다. 과거 형상과 같다고 추정하지 않으므로 유효한 증거가 없는 실행은 계속 막힌다.
이 두 반례는 별도 Windows 단위 검사로 확인했으며 기존 native 확인을 반복하지 않았다.
이는 새 FreeCAD 저장 왕복이나 전체 빔 출력 수용을 완료했다는 뜻이 아니다.
