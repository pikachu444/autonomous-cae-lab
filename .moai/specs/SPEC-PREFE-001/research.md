# 현재 자료와 재사용 판단

## 조사 범위

기준 main `1820cf1`, native upstream pin `3e48bf6138f495299f45b1af254bfb4aaff307b8`.
설치된 MoAI `moai-plan`, `moai-workflow-spec`, `moai/workflows/plan.md`,
`plan/spec-assembly.md`, `run/task-decomposition.md`를 읽고 요구→구현→수용으로 분해했다.
Codex에 없는 manager-spec/Claude Team 도구를 호출했다고 기록하지 않는다.
별도 사용자 인터뷰/재승인은 하지 않는다. 이번 목표·무료 조건·플랫폼·역할은 이미
사용자가 결정했고 기술상세 작성은 허가된 범위다. `.moai/project/tech.md`는 없으므로
재초기화하지 않고 ARCHITECTURE와 제품 계획/계약을 기준으로 사용한다.

## 소스에서 확인한 사실

- `motion.py`, `motion_panel.py`, `motion_path.py`: 복수구동·가동하위조립·참조복구,
  원경로 저장/CSV/Data 연결이 있다. 이를 새 구현으로 다시 세지 않는다.
- `fem_edit.py`: native 재료/조건·메시 품질·선택·국부크기·비동기 생성 경로가 있다.
  현재 허용 메시/실행 family에 한계가 있어 E1–E6의 실제 확대가 필요하다.
- `contact.py::law_errors`: 현 경로는 linear/tie, frictionless/Coulomb, 첫 단계부터
  전체유지 등을 허용한다. hard/cohesive, 다른 미끄럼 방식과 단계활성화는 거절한다.
- `freeze_contact.py`: 이미 static/dynamic 절차와 dynamic 밀도를 처리한다.
  ‘동해석이 전혀 없음’으로 새 계획을 만들면 중복이다. NS2는 그 다음 연결을 정의한다.
- `contact_fem.py`, `contact_results.py`: native접촉 DAT합력/모멘트와 실패 전 증분
  읽기가 이미 있다. R1/R2는 기존 parser를 지우거나 새로운 결과 owner를 만들지 않는다.
- `tie_adjustment.py`: 평면 단일대응 조정과 실제초기좌표/결과 재열기 인도가 있다.
  곡면/경계/복수후보는 별도 작업 C3이며 기존 인도 완료와 혼동하지 않는다.
- `CODEX_WORKFLOW.md`: Pro 큰 기능 작성, Sol 범위명확 연결, Astra 독립검토,
  Codex 공통통합과 상태기록. 사용자 요청대로 개발 중 전수 벤치마크는 하지 않는다.

기존 FN-10–15/25 본문에는 과거 ‘no contact’ 또는 단일 solid 제한이 남아 있다.
그 문장을 현행 구현으로 간주하지 않고 CURRENT_STATE와 위 소스의 실제 차이를 따른다.
전수 과거 문서 재작성은 이번 작업이 아니다.

## 미확정과 실행 위험

무료 backend별 hard/cohesive·주기·pretension·적층·mixed procedure의 정확한 native
지원 조합은 아직 이 SPEC에서 확인하지 않았다. 각 해당 작업의 처음에 공식 소스/문서와
기존 adapter를 대조하고 input→output 경로를 선택한다. 검토만 끝나거나 미지원표시만
추가되면 해당 작업은 미완료다. 새로운 모델·유료API·서버는 연결하지 않는다.
수치 허용치는 기존 기준을 사용하고 미정인 물리 요구는 UNKNOWN이다.

MoAI 형식 검사와 Astra의 기능/수용 검토 결과는 [review.md](review.md)에 남겼다.
형식 통과는 코드 구현이나 공학적 정확성 증명이 아니다.

## E1 셸 재사용 경로 — 2026-10-14 설치 소스 확인

Windows에 설치된 FreeCAD 1.1.4의 `Mod/Fem` 소스를 직접 읽었다. 새 셸 두께
객체나 기본 CalculiX writer를 만들 필요는 없다. `femobjects/element_geometry2D.py`의
`Fem::ElementGeometry2D`가 Thickness(mm)와 Offset을 소유하고,
`femsolver/calculix/write_femelement_geometry.py`가 재료별 요소 집합에
`*SHELL SECTION`과 OFFSET, 두께를 출력한다. 같은 writer에는 막 요소 분기가
있으므로 굽힘이 없는 막을 셸과 같은 선택으로 취급하면 안 된다.

`write_mesh.py`는 shell face variant로 native 메시를 내보내고,
`write_step_output.py`는 BeamShellResultOutput3D에 따라 OUTPUT=2d/3d를 나눈다.
상·하면 구분은 두께 속성만 연결해서 끝나지 않으며, 이 출력 선택과 실제 결과
위치/절점 대응을 함께 설계해야 한다. 정확한 첫 요소명과 상·하면 reader 대응은
아직 확인 전이다. 이를 모든 셸 지원 또는 E1 착수 카드 완성으로 표시하지 않는다.

프로젝트의 `apps/desktop_pre/freeze_analysis.py::_deck`는 C3D10 이외 요소를
거절하고 `caelab/adapters/native_structural_deck.py`도 C3D10 단일 solid를 쓴다.
따라서 native UI에서 셸을 만들 수 있는 것과 Lab에서 저장한 사용자 모델을
실행·결과 재열기까지 연결하는 것은 다르다. E1은 기존 native 두께/영역 편집을
재사용하고 이 입력 동결·실행·결과 연결을 확장하는 작업으로 배정한다.
진행 중인 Pro NS1의 FE 편집·동결 파일과 겹치므로 해당 제출의 공통 변경을
통합한 기준에서 작성 범위를 나눈다. 이번 조사에서는 메시 생성이나 솔버 실행을 하지 않았다.

후속 Luna 조회에서 첫 셸 후보를 균질 선형탄성 S8(8절점 사각형)으로 좁혔다.
FreeCAD 1.1.4의 `write_mesh.py` 기본 shell 분기와 `FemMesh.cpp`는 Quad8을
S8로 내보낸다. S8R은 별도 reduced 분기이므로 기본 출력이라고 가정하지 않는다.
[CalculiX 2.22 매뉴얼](https://www.dhondt.de/ccx_2.22.pdf)의 S8/C3D20 설명에 따르면
S8은 27개 적분점을 갖는 C3D20으로 확장된다. DAT의 S/E/COORD를 함께 읽어
요소·적분점과 두께 방향 좌표를 보존할 필요가 있다. 양끝 두께 적분점은 내부의
위쪽/아래쪽 관측값이며 정확한 표면 응력으로 표시하면 안 된다. 표면 결과 요구를
이 값만으로 완료 처리하지 않는다. offset과 법선 반전, 실제 출력 순서·좌표 매핑은
아직 실제 2.22 출력과 대조하지 않았다.

`structural_family_calculix.py`의 기존 DAT/FRD 경로는 C3D20 전용이다.
별도로 사용자 solid/contact는 `frozen_fem.py::read_frd`를 쓰므로 모든 CalculiX
reader가 C3D20만 지원한다고 확대하지 않는다. 새 reader 작성 여부는 이 기존
숫자/장 읽기와 Pro의 NS1 변경을 먼저 재사용할 수 있는지 보고 결정한다. native
FRD의 평균 절점값을 요소 상·하면 적분점 결과로 바꾸어 부르지 않는다.

## Q2 메시 품질 수정 흐름의 실제 누락 — 2026-10-14

Luna가 main `9630f5a`를 읽었고 Codex가 해당 명령과 화면 코드를 확인했다.
`fem_edit.py::quality`는 C3D10의 네 Gauss 표본에서 최소 Jacobian(mm³)과 정규화
Jacobian을 계산한다. 기존 두 기준과 전체 메시 분포를 재사용하며 요소 전체의 양의
Jacobian을 증명한다고 확대하지 않는다. `pre.fem.mesh_highlight`는 선택 요소의
실제 절점 ID를 native HighlightedNodes에 넣으며 표시 당시 메시가 바뀌면 거절한다.

`fem_panel.py`에는 품질 조회와 선택 요소 표시만 있고 요소 격리/확대는 없다.
`_local_size`의 native Fem::MeshRegion 생성·수정과 `_generate`/`_finish`의
재메시·실패/취소 시 이전 메시 보존은 이미 구현돼 있다. 이전 메시를 FCStd에
보관하지만 품질 화면이 그 보관본을 비교 대상으로 고를 수 없다. 따라서 Q2는
실행 확인만 남은 작업이 아니라 격리/확대와 이전/새 메시 비교 조작의 추가 개발이다.

기존 공개 실행 `runs/product-development/20261013/contact-mesh-350b4d63/receipt.json`은
메시 생성·품질·보관을 재사용할 근거이며 불량 요소 수정의 전체 완료 증거는 아니다.
기존 품질 계산·국부 크기·메시 생성기를 다시 만들지 않는다. Pro가 재료 연결을 작성 중인
`fem_edit.py`/`fem_panel.py`의 소유 범위와 조정한 뒤 실제 비교/뷰 동작을 배정한다.

Luna의 FreeCAD 1.1.4 공식 소스 후속 조회에서 FEM 면 이름은
`Elem<volume_id>F<face_number>`이며 native `ViewObject.partialRender`,
`getBoundingBox(subname)`와 `Std_ViewFitSelection`을 재사용할 후보로 확인했다.
근거는 공식 tag의 `src/Mod/Fem/Gui/ViewProviderFemMesh.cpp`,
`src/Gui/ViewProviderPyImp.cpp`, `src/Gui/CommandView.cpp`다. 실제 FEM 요소의
격리와 카메라 범위가 맞는지는 아직 확인 전이다. `fitAll()`을 선택 확대의
대용으로 처리하지 않는다. 내부 면 표시 `ShowInner`에는 면 수 제한이 있으므로
기존 값을 보존하고 격리 해제/창 닫기/문서 변경 시 화면 상태를 복구해야 한다.
Sol에게 보관된 공개 메시를 재사용하는 좁은 native 확인만 배정했다. 확인 결과에
따라 기존 native 뷰를 우선 사용하고 불필요한 임시 형상/새 표시 엔진은 추가하지 않는다.

Sol의 설치 FreeCAD 1.1.4 실행에서 표면 요소477과 내부 요소479의 facet 지정은
`partialRender`가4를 반환해도 전체 메시를 표시했다. subelement bbox는 전체
30×20×5mm였고 native 선택은 면 이름을 유지하지 않아 선택 확대도 전체에 적용됐다.
Codex가 `runs/q2-native-view/receipt.json`과 surface-isolated.png를 직접 읽었다.
소스에 API가 존재한다는 것만으로 이 조합의 요소 격리를 지원한다고 하지 않는다.
원메시/visibility/ShowInner/선택을 복구했고 원파일은 보존했다. 대안은 정확한
선택 요소만 복사한 native 일시 미리보기이며, 원모델 저장에 섞이지 않는 연결을
Sol의 `mesh_view.py` 작성 범위로 배정했다. 새 솔버·메셔를 실행하지 않았다.
후속 native viewer는 원문서를 활성 상태로 유지했지만 화면이 비었다. volume-only
복사본의 ShowInner 누락을 고쳐도 같아서 미확인 helper를 제품에 넣지 않았다.
후속 소스 조사 뒤 DisplayMode의 실제 switch가 기존3에서 명시적 Faces의0으로
전환되는 것을 확인했지만 최종 캡처도 비었다. 표시 모드 누락을 원인으로 확정하지
않으며 이 실패를 Q2 완료로 처리하지 않는다. 추가 native 표시 실험은 멈춘다.

별도로 Sol의 `mesh_quality_compare.py`를 main `9de03e4`에 통합했다. 현재 메시와
완료 기록의 보관 메시를 기존 `FEMEditor.quality`로 읽는다. 선택한 보관 기록은
가장 최근 세대일 필요가 없으며 현재/보관 파일의 각각의 내용을 확인한다. 재메시 뒤
요소 번호가 같은 위치를 뜻한다고 가정하지 않는다. 두 분포의 경계가 다르면 구간별
차이를 계산하지 않는다. 읽기 전용 `pre.fem.mesh_compare` 연결과 관련16검사가
통과했다. 비교 GUI와 격리/확대는 별도 잔여 작업이며 Q2 완료 수는 바꾸지 않는다.
