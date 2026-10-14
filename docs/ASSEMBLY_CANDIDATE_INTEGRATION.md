# M4 준비 상태·재열기 편집 교정

## 현재 통합 결과

2026-10-15 Codex 통합: 아래 Pro 제출물을 공통 Pre 명령·문서 열기·일반 FEM 관문에
연결했다. 잘못된 후보는 메시 생성·적용·입력 생성과 자동 저장 전에 차단하며 일반
초안 저장은 유지한다. Astra가 전용·공통 소스와 원 지적 해소를 독립 검토했다.
현재 소스의 영향 검사 53개와 별도 기존 메시 보관 검사 1개가 통과했다.

Windows FreeCAD에서 네 부품의 실제 Gmsh/설정/저장·재열기 후 재료 수정까지 확인했다.
03 적용 후에는 기존 모델의 새 사본으로 native 패널 상태·선택·직접 콜백과 공개 실행기의
cold-edit/cold-resaved 두 단계만 추가 확인했다. 네 재료·메시 크기·조건 면 수정/적용/저장과
새 프로세스 읽기가 일치했고 기존 메시와 원자료는 불변이다. 모든 소유 프로세스를 정리했다.
새 solver·OS 마우스 전체 동선·일반 기구 전체나 공학 승인으로 확대하지 않는다.
정확한 기록 위치와 다음 작업은 [CURRENT_STATE](../CURRENT_STATE.md)를 따른다.

## Pro 제출 당시 기록

다음은 작성 환경에서의 범위와 미실행을 보존한 기록이다. 위 Windows 통합 확인과 구별한다.

요청: **PRO-M4-ADMISSION-CORRECTION-20261015-03**.
기준은 회수된 `M4_Native_Correction_20261015_02.zip`의 실제 `files/`입니다. 부족한 기존 테스트 의존성은 첨부 `m4-native-correction-source-02.zip`, 최초 M4 및 4ba6de9 첨부로 구성했습니다. 최신 전체 main이나 Codex/Sol의 미커밋 공통 수정 사본이라고 주장하지 않습니다.

## 적용

`product.patch`를 02 적용본 위에 적용합니다. `files/`는 동일 변경 파일이며, 패치와 중복 적용하지 않습니다. `BASE_SHA256.json`에 교정 전 파일 hash, `MANIFEST.sha256`에 제출물 hash를 넣었습니다. 충돌이 있으면 현재 파일을 통째로 덮지 말고 해당 hunk를 대조합니다.

제품 변경은 `assembly_pose_candidate.py`, `assembly_pose_panel.py`뿐입니다. 나머지는 M4 전용 검사·실행 예제·안내입니다. geometry/source 모듈, 전체 형상/면 대응 알고리즘과 허용치, `makeSolverCalculiXCcxTools`, `owner.export_root`는 그대로입니다. fem_edit, freeze_analysis, freeze_contact, bridge, connection, projects, fem_panel, native_commands, CURRENT_STATE와 다른 담당 영역은 수정하지 않았습니다. **공통 integration.patch는 없습니다.**

## P1 공통 FEM 호출부가 사용하는 계약

`KEY = 'assembly_pose_candidate'`, `validate_model(owner, *, exact=False)`, `require_valid(owner, *, exact=False)`와 기존 반환 `state/errors/bodies/frame/time/frame_kind/analysis_id`는 유지합니다.

일반 FEM 메싱·입력·실행에서는 KEY의 **존재**를 검사하고, 작업 직전에 `require_valid(owner, exact=False)`를 직접 호출해야 합니다. 반환 `state == 'READY'`도 확인할 수 있습니다. UI의 descriptor나 이전 검사 결과를 실행 허가로 재사용하지 않습니다. 비어 있거나 잘못된 KEY 값은 일반 문서로 취급하지 않습니다.

```python
# Codex/Sol 소유 공통 admission에 붙는 소비 계약. 이 제출물의 공통 수정 아님.
if KEY in owner.read_metadata():
    report = require_valid(owner, exact=False)
    if report['state'] != 'READY':
        raise ValueError(report['blocked_reason'])
```

M4의 READY는 기존 FEM material/mesh binding/face target/contact/solver 검사에 **추가되는** 전제입니다. 이를 기존 검사 대신 사용하면 안 됩니다. CAD와 Binder가 함께 정상 수정되어도 과거 메시·면 fingerprint를 새 값으로 덮지 않습니다.

이번 직접 계약 검사는 같은 BREP의 잘못된 SourceIdentity/SourcePart/Link/Support와 stale Binder가 `require_valid`에서 차단되는지 확인했습니다. **generic mesh_generate/_generate/validate_for_run/pre.freeze/contact.freeze의 실제 호출 연결은 Codex/Sol 소유이며, 이 사본에는 그 통합 변경이 없습니다. 해당 경로의 종단 차단 성공을 주장하지 않습니다.**

## P2 전용 교정

검증 결과에 `preparation_state`, `preparation_complete`, `geometry_valid`, `ready`, `blocked_reason`을 추가합니다. 저장 포맷 v1이나 기존 native 정체성 기록을 변경하지 않습니다. `preparation_complete`는 저장된 READY 완료 표식, `geometry_valid`는 이번 읽기 전용 형상·정체성·참조 검사에 오류가 없다는 뜻이며, `ready`는 둘 모두 만족할 때만 true입니다. solver 입력 완비나 계산 성공 표시가 아닙니다.

| 보존 상태와 대응 | 읽기·수정·저장 | 일반 require_valid | 준비 내부 exact=True |
|---|---|---|---|
| READY, 전체 기록/형상 일치 | 유지 | 허용 | 허용 |
| PREPARING, 검사 오류 없음 | 유지 | 차단 | 허용 |
| FAILED/CANCELLED/INTERRUPTED/DRAFT | 유지 | 차단 | 차단 |
| 정체성·형상·참조 불일치 | 사본 보존 | 차단 | 차단 |

`validate_model`은 실패 사본을 열람하기 위한 보고서를 반환하며 상태 자체 때문에 문서 저장을 막지 않습니다. 첫 부품 뒤 실패·취소한 사본은 실제 `errors=[]`일 수 있지만 `ready=False`이고, `require_valid`는 거절합니다. 빈 재료를 가진 정상 READY 문서는 초안 저장이 가능합니다.

native에 남은 M4 Binder와 metadata 목록도 역대조하여, 목록에서만 부품을 빼는 경우를 차단합니다. 기존 source/path/Link/Support/현재 CAD 대조는 유지합니다. 원자료나 fingerprint를 보정하지 않습니다.

descriptor 캐시는 generation뿐 아니라 M4 metadata도 비교합니다. 준비 상태가 generation 증가 없이 바뀌어도 READY를 계속 표시하지 않습니다. 패널의 트리 선택 신호와 주기 갱신이 같은 버튼 정책을 사용하고, 버튼 콜백도 새 `require_valid` 검사 없이 FEM 편집창을 열지 않습니다. 실패 사본의 CAD 편집은 유지하고 문서 저장 경로는 변경하지 않습니다.

## 재열기 후 실제 적용·재저장 검사

전용 실행기는 세 개의 새 FreeCAD 프로세스를 사용합니다. 첫 프로세스가 네 대상의 실제 Gmsh 생성·초기 편집·저장, 둘째가 무재계산 읽기 확인 **이후** 실제 입력 수정·적용·별도 저장, 셋째가 그 수정 파일을 새로 읽어 저장값을 대조합니다.

둘째 단계는 네 대상 각각의 E/ν, 전역 최소·최대 크기, 국부 크기와 실제 조건 면을 기존 `pre.fem.*` 명령으로 변경합니다. mesh/material/condition/refinement 객체 ID는 유지합니다. 반환값만 믿지 않고 요청 값과 실제 native 속성·면 참조를 대조합니다. 이전 영역 기록과 원 `.caepre`는 보존하고, 새 면 선택만 명시적 사용자 편집으로 기록합니다.

cold read에서 재계산 없음과, 그 뒤 명시적 적용 transaction에서 발생한 재계산은 별도 기록합니다. 편집 단계에서는 운동/FEM 계산이나 Gmsh 재생성을 하지 않습니다. 이전 메시 노드·요소·binding은 그대로이며, 새 메시 크기가 이미 메시로 생성되었다고 표시하지 않습니다. 셋째 과정은 변경된 입력과 보존 메시를 모두 읽습니다. GUI 클릭/미적용 폼 값 보호는 이 typed API 검사와 별도 Windows 확인입니다.

## 소유 프로세스 정리

02 예제에 있던 독자 `WindowsJob` 구현을 제거했습니다. 기존 `scripts/native_check.py`의 `run_native_check(command, output_dir, timeout_seconds, cwd)`를 호출합니다. 읽어 확인한 공통 파일 Git blob은 `9f19fc803057e697e41e07492d13161482dd20e0`이며, 그 파일을 제출하거나 교체하지 않습니다.

공통 helper가 만든 root PID, 정상 종료, timeout 없음, `cleanup == 'job_empty'`, native 단계 결과가 모두 맞아야 통과입니다. 환경 nonce와 직접 부모 PID는 사용자/다른 프로세스에서 매크로가 문서에 접근하는 것을 막습니다. 임시 환경은 예외에도 복구합니다. 새 Windows Job/API/프로세스 이름 종료 코드는 추가하지 않습니다. 공통 helper가 없거나 정리 확인이 실패하면 대체 구현 없이 실패합니다.

## 실제 확인과 경계

교정 전 02에서 첫 부품 뒤 FAILED/CANCELLED가 `require_valid`를 통과하는 두 회귀를 실제 재현했습니다. 교정 후 집중 검사 118개 통과, Qt 검사 모듈 1건 skip입니다. 이 중 기존 실제 OCC 검사 13개도 통과했습니다. 인접 중첩 조립·닫힌 기구·저장 전달 검사 40개 통과, Qt 4건 skip입니다.

새 cold-edit 검사는 실제 FEMEditor 명령을 native 대역에 적용하고 실제 `.caepre` 컨테이너를 저장·재열기합니다. material/mesh/condition/local 적용이 no-op이면 실패하는 것도 확인합니다. **대역의 native 직렬화는 실제 FCStd나 별도 FreeCAD 프로세스가 아닙니다.** 소유 실행기 검사는 주입한 공통 runner 대역의 호출/실패 전파 검사입니다.

**미실행:** Windows FreeCAD, native Qt 화면·입력, Gmsh, native cold edit/re-save/third-process reopen, 실제 Windows process cleanup. P1 공통 경로 통합, 최신 main 전체 회귀, 이번 변경의 독립 검토도 완료로 보고하지 않습니다. 검증 로그와 패치 적용·파일 일치 검사는 ZIP의 `validation/`에 있습니다. native 성공 JSON은 동봉하지 않습니다.
