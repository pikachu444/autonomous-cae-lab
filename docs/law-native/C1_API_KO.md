# LAW-C1 — 저장 할당의 실행 provenance와 native 재고정

요청: PRO-LAW-NATIVE-20261015-01-C1. 원 요청의 법칙/fit/GUI를 재작성하지 않는 두 코어 경계 교정이다.

## 원인과 수정

`Workbench._execute`와 `research_execution.run_domain`은 모두 `_settings`를 호출한다. 이전 공통 재귀 검사는 실행 경로와 `source_receipt.review.source.source_guard[0..2].path`의 원 Apply CAS 증거를 구분하지 않아, 실제 FE worker 이전에 거절했다. C1은 두 진입점을 그대로 두고 같은 공통 관문에서 정확한 세 위치만 구분한다. receipt를 삭제하거나 경로 키를 바꾸거나 입력을 재서명하지 않는다.

`caelab.law_native_provenance.admitted_guard_paths(settings) -> frozenset[tuple]`는 원 입력을 변경하지 않는다. 다음 조건을 모두 검사한 뒤에만 세 경로 위치를 반환한다.

- 기존 `law_native_fe.validate_settings`의 정확한 실행 필드/수치/단위/측도/mesh/solver/초기상태 검사를 통과한다. 실제 settings와 검토 interface settings가 같고 원 assignment/review/source 해시와 현재 신뢰 코드 10개가 맞아야 한다.
- assignment/source/build/source 파일 목록과 상태가 기존 고정 interface 계약을 따른다. 세 guard는 정확히 path/sha256 두 필드이며 동일 Material 문서의 document.json, working.json, 동일 저장 revision의 revision.json이어야 한다.
- 경로는 PureWindowsPath/PurePosixPath로 문자열 구조만 검사한다. resolve/stat/open/read/execute하지 않는다. 원 Windows Material workspace가 Linux 또는 cold 환경에 존재할 필요가 없다.
- 저장 source→단위 mapping→interface를 독립적으로 다시 구성해 비교한다. 실행 필드가 손상되거나 자가 해시를 다시 계산한 공격 입력은 허용되지 않는다. 새 review를 발행하거나 원 review를 교체하지 않는다.
- 원 card_preview 문자열은 원 해시와 함께 보존한다. 비교용 사본에서만 JSON을 파싱해 키 순서와 독립적으로 의미를 확인한다. 중복 키/비유한 값은 거절한다. live Apply의 byte-exact `verify_review`는 바꾸지 않았다.
- native selection, 적용 토큰, 적용 전후 물리 target이 검토와 일치해야 한다.

Workbench는 그 뒤에도 전체 입력을 재귀 검사한다. `command`, `argv`, `module`, `factory`, `script`, `executable`, `output`, `output_root`, `runtime`, `snapshot_path`는 receipt 안에서도 계속 거절한다. `path`는 검증된 세 위치 외에는 기존대로 거절한다. 기존 files.table의 등록 data_id 해석, frozen FEM의 등록 입력 전용 처리, MFront exact-source 승인 경계는 변경하지 않았다. hash는 무결성 자료이지 임의 실행 권한의 인증서가 아니다.

## Native 물리 identity

`caelab.law_native_identity`는 FreeCAD를 import하거나 파일을 읽지 않는 비교 모듈이다.

`require_native_version(version)`은 live capture/re-freeze를 FreeCAD 1.1.4로 한정한다. `capture_proxy(value, native_type)`는 다음 두 선언만 받는다.

| Native type | Python class |
|---|---|
| Fem::MaterialCommon | femobjects.material_common.MaterialCommon |
| Fem::SolverCcxTools | femobjects.solver_ccxtools.SolverCcxTools |

실제 클래스 module/qualname과 Proxy.Type을 대조하고 `freecad-specimen-proxy/1`, python_class, native_type을 저장한다. Proxy의 str/repr 또는 메모리주소는 호출하거나 저장하지 않는다. 다른 scripted class, 맞지 않는 type, 알 수 없는 generic 객체의 주소 repr은 거절한다. Material/solver의 실제 PropertiesList 물리 값은 여전히 별도로 캡처한다.

`semantic_target(target)`은 comparison-only 사본을 만든다. 기존 session_id/generation은 live CAS 값으로 구분하고, material/native_context_solver/native_analysis_members의 정확한 Proxy 필드에 있는 알려진 legacy 기본 repr만 동일 선언으로 정규화한다. 다른 물리 텍스트에서 주소를 임의 제거하지 않는다. 기존 원 applied_target과 assignment/review/source 해시는 그대로 남는다.

같은 원 입력에 있던 `Material.References`의 FreeCAD 내부 문서명도 영구 ID가 아니었다. FreeCAD 1.1.4 `Application::openDocumentPrivate`는 연 FCStd의 파일명으로 내부 문서 이름을 만든다. 따라서 `LawNativeSpecimen`에서 저장한 `specimen.FCStd`를 다시 열 때 이름이 달라질 수 있다. C1의 live native 객체 참조는 실제 `value.Document is owner.doc`를 먼저 확인하고 영구 owner.document_id + object_id로 캡처한다. 같은 이름의 외부 문서/객체는 거절한다.

Legacy 비교는 이미 whole-solid로 admission된 Material References 한 슬롯과 그 Analysis 내 중복 캡처에만 적용한다. geometry object_id, []/Solid1 subelements, 중복 legacy 문서명 일치를 확인하고 그 target의 보존 document_id로 해석한다. 임의 solver link, 다른 metadata, external reference를 정규화하지 않으며 현재 객체를 이름으로 찾아 원 참조를 다시 바인딩하지 않는다. 오래된 record에 없던 version/UUID를 새로 추정하여 서명하지 않는다.

현재 `capture`의 실제 native 타입/solver admission, geometry/mesh/region/member/step 검사는 그대로 필요하다. `freeze`는 양쪽 target의 안정된 의미를 비교한 뒤 **원 review.interface.settings와 원 receipt 그대로** 새 입력을 반환한다. Material 계수·solver 설정·region/geometry·mesh·node/connectivity·Analysis membership·metadata·assignment·step·영구 문서 ID 변화는 계속 차단한다. 새 물성 revision을 자동 채택하지 않는다.

## Live Apply와 FE/cold 구분

| 경로 | 검증 | 원 source guard 읽기 |
|---|---|---|
| preview→명시 Apply | 기존 전체 live target(session/generation 포함), live source CAS, 현재 코드 | 기존대로 필요 |
| 같은 저장 할당 re-freeze | 보존 무결성, 현재 native 물리/영구 identity, 현재 원 10개 코드 | 불필요 |
| 명시 Simulation FE | 엄격한 실행 settings, 원 receipt, 현재 원 10개 코드, 검토와 실제 입력 일치 | 불필요 |
| 저장 결과 cold read | 기존 owner/reader의 보존 input/job/result/source 무결성 | 불필요; solver도 불필요 |

`material_fe_transfer.py`, `law_native_fe.py`, 수치 adapter/worker와 10개 source의 원문은 모두 변경하지 않았다. `verify_source(...live=True,current_code=True)`와 Apply transaction/CAS는 유지한다. helper 추가는 수치식/한계/원 source identity의 새 개정이 아니다.

## 호환성과 소유

LAW-C1의 기존파일 수정은 전용 `apps/desktop_pre/law_native_material.py`와 공통 `caelab/workbench.py`뿐이다. root solver-type guard/FEM assert_thread 순서, Sol 전송 GUI/fit 연결, 기존 FreeCAD smoke 철자 교정은 이 패치에서 편집하지 않는다. 현행 비공개 WIP 전체를 받은 것은 아니므로 그 파일들의 전체본을 제공하거나 덮지 않는다.

전용 delta 기준은 실제 보존된 첫 LAW ZIP을 원 3ba7c97 source에 적용한 상태다. 공통 patch는 GitHub에서 확인한 공개 4e2cf2c Workbench blob `4dfe1c2a41df760da44c631ddf6747670f87939e`를 기준으로 작성한다. 그 전체 blob을 원 source와 조회한 네 hunk로 복구하고 Git blob hash 일치를 확인했다. 원 LAW 적용 baseline과 이 공개 공통 파일 각각에 clean patch 적용을 검사한다. 실제 current WIP에 적용하거나 Windows에서 통합 실행한 것으로 표시하지 않는다.

## 공식 native 소스 근거

FreeCAD/FreeCAD tag 1.1.4, `src/App/Application.cpp`, `openDocumentPrivate`, 약 941–995행. 조회 blob: `40abf1c1ce8d375da153f6c9774f4cb2e6afb7d7`. 이는 소스 검토이며 실제 FreeCAD 실행 증거가 아니다.

https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/App/Application.cpp
