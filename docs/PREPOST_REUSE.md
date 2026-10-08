# 전처리·후처리 독립 앱 재사용 조사

조사일: 2026-10-08. 범위: 저장소 코드와 ADR, 공식 upstream 문서, 현재 Windows 배포물 정보. 이 문서는 구현 또는 제품 수락 판정이 아니라 `PREPOST_APP_SPEC.md`의 선택 근거다. 현재 세션의 GUI 실행·조작·재시작 검증은 root 소유의 `PREPOST_VERIFICATION.md`에 따로 기록한다.

## 1. 결론과 근거의 수준

전처리는 **FreeCAD 기존 앱 + 전용 workbench + 현재 pinned adapter**, 후처리는 **ParaView 기존 앱 + reader/plugin + 결과·상태 묶음**을 우선 검증할 가치가 가장 높다. 이 경로는 이미 있는 CAD 편집기와 결과 탐색기를 실제 제품 기반으로 재사용한다. 별도 PySide6 창 안에 Gmsh·PyVista만 넣는 경로는 뷰포트를 빨리 만들지만, 문서 수명주기·모델 트리·선택 동기화·undo·프로젝트 저장·결과 탐색 명령을 추가로 구현해야 한다. 아래 비교는 이 기능 차이에 따른 판단이며 일정이나 비용 숫자를 산정한 것이 아니다.

두 앱은 각각 파일만으로 시작하고 저장·재개할 수 있어야 한다. Core의 공통 데이터 계약과 검증은 재사용하되, 연구 에이전트 또는 실행 중인 솔버가 파일 열기·CAD 편집·기존 결과 읽기의 필수 조건이 되면 안 된다. 과거 ADR의 OpenScience 필수 진입점/하나의 Lab 화면이라는 제품 전제는 최신 독립 앱 방향에 맞춰 갱신해야 한다. Core/도메인/adapter 소유권, 결정적 수치 탐색, 원본 보존, 명시 단위, UNKNOWN 판정은 그대로 유효하다.

근거를 구분한다.

- **이번 세션 실행:** 로컬 보존 코드의 portable 계약 시험 254 passed, 2 skipped. 네이티브 CAD·솔버 검증은 아니다.
- **이번 세션 읽기 확인:** pinned upstream 및 local/remote 코드, 모든 local ADR 0001–0057와 remote-only ADR 0058–0059, 정확 source commit의 CI 결과, 공식 배포 및 확장 문서.
- **과거 산출물 읽기:** 별도 작업 폴더의 STEP→Gmsh→VTU spike. 이번 조사에서 재실행하지 않았다.
- **미검증:** FreeCAD workbench 완성품, ParaView plugin 완성품, 양 앱의 통합 GUI 수락, 일반 CAD topology 재결합, 임의 상용 솔버 파일 지원, 기업 배포 승인.

## 2. 조사한 저장소 상태

| 항목 | 확인 값/한계 |
|---|---|
| 작업 폴더 | `C:/SourceCodes/autonomous-cae-lab` |
| local HEAD | `4843c66e482ded31c59604d7cc19d1800be388f4` |
| `origin/main` 및 `git ls-remote`로 확인한 원격 main | `fc7c82dfcf4a6155ff18b7ebd5b91388916e6a9e`; local보다 32 commits 앞섬 |
| fixture upstream pin | `3e48bf6138f495299f45b1af254bfb4aaff307b8` |
| 보존한 기존 수정 | `apps/lab/service.py`, `scripts/verify_fixture_selected_research_source.ps1`, `scripts/verify_mcp.py`; 미추적 `docs/CAE_SYSTEM_IMPLEMENTATION_SPEC.md` |
| 조사 방법 | local 파일 직접 읽기, remote는 `git show origin/main:<path>`로 읽기. pull/reset/복사 통합/다운로드/설치/공통 interface 변경 없음 |

local exact source의 [CI run 37547439489](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/37547439489)는 core와 research-source 실패, 다른 8 jobs skipped였다. remote exact source의 [CI run 37698069804](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/37698069804)는 9 jobs 성공, Code_Aster 실패였다. 어느 쪽도 전체 CI 성공으로 표현할 수 없다. 이후 문서 commit은 해당 solver 실행의 source identity를 바꾸지 않는다.

## 3. 기존 제품·라이브러리 비교

| 후보/통합 방식 | 직접 재사용하는 기능 | 우리 쪽에서 구현·검증해야 하는 부분 | Windows·라이선스 공식 근거 | 판단 |
|---|---|---|---|---|
| **FreeCAD 기존 앱 + workbench** | native CAD 문서, 형상/스케치/파라미터 편집, 모델 트리, 선택, 속성, 기존 작업대. Python workbench의 명령·메뉴·도구막대와 App/Gui 분리 | 공통 프로젝트 manifest, typed 조건 UI와 export adapter, face/mesh selection receipt, revision gate, 지원 작업 범위와 오류 표시, 결과 앱 handoff | [기능](https://www.freecad.org/features.php), [workbench 소스 문서](https://raw.githubusercontent.com/FreeCAD/FreeCAD-documentation/main/wiki/Workbench_creation.md), [FreeCAD LICENSE](https://github.com/FreeCAD/FreeCAD/blob/main/LICENSE): LGPL-2.1 기반. 공식 Windows 배포 있음 | 전처리 우선 경로. 기존 pinned FCStd 통합과 결합 가능 |
| **FreeCAD macro** | 반복 CAD 조작 및 기존 명령 조합, 제한된 acceptance fixture 생성 | 영속 상태·패널·선택 모드·명령 enable/disable·설치/업데이트·오류 복구를 별도로 갖춰야 함 | [공식 Macros 문서](https://raw.githubusercontent.com/FreeCAD/FreeCAD-documentation/main/wiki/Macros.md) | 설치 검증/수락 시나리오의 재현 수단. macro 하나 실행된 것을 완성 앱이라고 판정하지 않음 |
| **OCCT 직접 통합** | BREP geometry/topology, CAD 형상 연산과 데이터 교환 기반 | 모델링 명령 UX, 문서/undo, 선택 식별, tree/property 동기화, CAD 오류 안내, 저장/복구, renderer 연결 | [OCCT 공식 license](https://occt3d.com/dev/doc/overview/html/occt_public_license.html): LGPL-2.1와 special exception | 기존 앱이 충족하지 못하는 기능이 구체적으로 입증될 때 고려. CAD kernel 자체는 CAD 앱이 아님 |
| **Gmsh 외부 실행/API** | OpenCASCADE 기반 형상 import/연산, mesh generation, physical groups와 mesh export, Python API | mesh sizing UI, quality 기준/표시, CAD→mesh group 계약, 단위/좌표계, cancel/실패 artifact, solver별 export | [Gmsh 공식 site/manual 및 license](https://gmsh.info/): Windows 배포와 API, GPL-2-or-later 및 문서상 linking exception/별도 proprietary license 경로 | mesh engine 재사용. 원래 CAD 편집 이력 보존을 대체하지 않음 |
| **SALOME 기존 앱/모듈** | SHAPER/GEOM, SMESH, mesh groups, ParaVis 기반 통합 기능 | 큰 통합 환경 배포, 공통 프로젝트 연결, solver-independent 조건 및 결과 계약, 두 독립 앱 제품 경계 | [Windows 9.16 배포](https://www.salome-platform.org/?page_id=2430), [FAQ](https://www.salome-platform.org/?page_id=428), [terms](https://www.salome-platform.org/?page_id=2618): LGPL 계열 구성요소 및 PyQt/PyQtChart의 별도 조건 | 고급 meshing 경로로 비교 가치 있음. 현재 프로젝트의 기본 필수 의존성으로 바로 확정하지 않음 |
| **PrePoMax 기존 Windows 앱/외부 연계** | CAD import, Netgen/Gmsh mesh, node/element/surface set, 구조 FEA 조건과 field/history 후처리 | 일반 PDE/curve 중심 계약, backend 확장, 두 앱의 독립성, C#/Windows Forms/ActiViz 기반과 Python 코드 연결 | [공식 site](https://prepomax.fs.um.si/), [downloads](https://prepomax.fs.um.si/downloads/), [2.6.0 manual](https://prepomax.fs.um.si/wp-content/uploads/2026/09/PrePoMax-v2.6.0-manual.pdf): Windows portable/.NET 4.8, GPLv3 | 구조 FEA 작업 흐름의 강한 비교 대상. CalculiX 중심 결합을 일반 전후처리 계약으로 그대로 간주할 수 없음 |
| **ParaView 기존 앱 + reader/plugin** | pipeline/tree/properties, 3D field 렌더링, 선택·probe·slice, 여러 결과 표시, chart, 색상/범례, 상태 저장 | Core response semantics, native IDs/단위/좌표계, read-only retained source receipt, project relocation, selection→표/그래프, 범위가 맞는 비교, missing-data UX | [공식 license](https://www.paraview.org/license/): BSD-3 및 배포 의존성별 조건. [상태 저장 공식 문서](https://docs.paraview.org/en/latest/UsersGuide/savingResults.html) | 후처리 우선 경로. 실제 GUI 재사용 비중이 큼 |
| **VTK/PyVista/PyVistaQt + 자체 PySide6 앱** | mesh/data model, rendering/filter/picking; `QtInteractor`를 Qt layout에 삽입 | reader chooser, 문서/pipeline tree, 명령·속성·선택 동기화, legend 정책, 비교/plot layout, undo, project save/reopen, 오류·취소·대용량 수명주기 | [VTK](https://vtk.org/about/): BSD. [PyVista LICENSE](https://github.com/pyvista/pyvista/blob/main/LICENSE): MIT. [PyVistaQt usage](https://qt.pyvista.org/usage.html), [Qt for Python licenses](https://doc.qt.io/qtforpython-6/licenses.html) | 맞춤 shell이 꼭 필요한 경우의 대안. 작은 rendering spike를 기능 완성 근거로 확대하면 안 됨 |

라이선스 열은 upstream의 공개 조건을 기록한 것이다. 전체 배포에는 Python/Qt/렌더링/solver/포맷 reader 등 실제 함께 전달하는 구성요소의 목록이 필요하다. 공공 저장소에 올리는 코드의 라이선스와 회사 설치·보안 승인은 별도 현안으로 남아 있다.

### 이번 조사에서 확인한 정확한 portable 후보

| 제품 | 공식 artifact | 확인 정보 |
|---|---|---|
| FreeCAD **1.1.4**, Windows x86_64, Python 3.11 | [공식 7z](https://github.com/FreeCAD/FreeCAD/releases/download/1.1.4/FreeCAD_1.1.4-Windows-x86_64-py311.7z), [공식 SHA256](https://github.com/FreeCAD/FreeCAD/releases/download/1.1.4/FreeCAD_1.1.4-Windows-x86_64-py311.7z-SHA256.txt), [release](https://github.com/FreeCAD/FreeCAD/releases/tag/1.1.4) | 2026-09-28 published; 418,088,341 bytes; `4828741fc91ee37fafcdb97a1abacb18b04ba451ac4372d9ff7a7349b36f4d6d` |
| ParaView **6.2.0**, Windows Python 3.12, non-MPI | [공식 ZIP](https://www.paraview.org/files/v6.2/ParaView-6.2.0-Windows-Python3.12-msvc2017-AMD64.zip), [공식 directory](https://www.paraview.org/files/v6.2/), [공식 release announcement](https://discourse.paraview.org/t/paraview-6-2-0-is-now-available/17753) | HEAD 200; 1,392,860,131 bytes; Last-Modified 2026-09-29; announcement 2026-09-30. 이 조사에서는 공식 checksum sidecar를 찾지 못함 |

이 조사자는 내려받거나 설치하지 않았다. root가 새로 확보한 파일의 실제 SHA-256·압축 해제 경로·실행 버전·GUI 증거를 검증 기록에 추가해야 한다. ParaView의 ZIP 파일명에 들어 있는 compiler token과 Python 버전은 이 artifact의 실제 이름이며, 현재 프로젝트에 같은 toolchain을 강제한다는 뜻이 아니다.

## 4. 전처리 코드: 다시 만들지 않아야 할 부분

| 재사용 위치 | 이미 구현된 계약 | 한계와 앱에서의 표현 |
|---|---|---|
| [pinned `fixturelab/native_cad.py`](../plugins/fixture_design/upstream/fixturelab/native_cad.py)와 native worker | native FCStd import/inspect, final object 선택, regeneration과 editable 파일 보존. import는 FCStd ZIP/`Document.xml`을 확인하고 100 bytes–25 MB 제한 | 범용 STEP 편집기나 임의 assembly 처리 전체를 의미하지 않음. FreeCAD 앱의 STEP import와 이 managed FCStd 계약은 서로 다른 경로임을 명시 |
| [`FixtureFreeCADAdapter`](../caelab/adapters/fixture_freecad.py) | `import_document`, `inspect_model`, `select_final`, `discover`, `probe_effect`, `prepare_bind`, `preflight_effects`, `regenerate`. pinned native implementation을 bridge로 호출 | native 경로/문법은 adapter 소유 유지. workbench가 Core registry를 우회해서 동일 parameter를 임의 등록하면 안 됨 |
| [`freecad_parameters.py`](../caelab/adapters/freecad_parameters.py) | `registered_targets`, `discovery_candidates`, `resolve_selection`; named identity와 source hash를 포함한 opaque sketch-constraint selector | constraint index나 화면의 이름만을 영구 ID로 사용하지 않음. 새 source revision에서 이전 discovery selector는 재검증 필요 |
| [`native_face_catalog.py`](../caelab/adapters/native_face_catalog.py) | `build_face_catalog`, `read_face_catalog`, `validate_catalog`; editable/STEP/BREP hashes, single-solid volume 비교, native→STEP unique geometry/common-area 대응, `F-{revision}-FaceN` ID | 현재 single-solid/frame-mm 계약. frame alignment/physical qualification은 UNKNOWN. FaceN 문자열만 같다고 새 형상에 조건을 자동 재결합하지 않음 |
| [`analysis_conditions.py`](../caelab/analysis_conditions.py) | `describe`, `save`, `inspect`, `execution`, `verify_child`; CAD revision/catalog revision에 묶인 typed material/BC/load, immutable receipt, child 실행에 frozen copy | unsupported 선언은 보존하되 실행을 막음. 삭제·기본값 대체·임의 단위 추정을 하지 않음. 현재 없는 solver 때문에 과거 child result를 읽지 못하게 하면 안 됨 |
| ADR0015의 registration recovery | private preparation과 native/registry publish journal, 충돌 확인, 실패 복구 | GUI의 Save/Apply도 이 거래 경계를 사용. 중간 실패 뒤 기존 사용자 파일을 덮어쓰는 복구 금지 |

형상 변경 전후 `Face3`이 우연히 같아도 같은 참조가 아니다. [`test_native_face_catalog.py`](../tests/test_native_face_catalog.py)의 `test_new_source_bytes_get_new_face_ids_without_rebinding_old_ids`가 바로 이 경계를 검증한다. 새 revision을 만든 뒤 이전 face 조건을 **다시 선택 필요** 상태로 보여 주고, 지원되는 명시적 remap을 사용자가 확인한 후 새 조건 기록을 만든다. 이는 CAD의 topology renaming 문제가 해결되었다는 주장이 아니다.

mesh remesh도 별도 revision이다. CAD face에 연결한 조건과 mesh node/element에 직접 연결한 조건을 구별해야 한다. 후자의 native ID는 remesh 후 계속 유효하다고 가정할 수 없다. mesh coordinate unit, CAD-to-mesh transform, physical group 이름/ID, source face receipt, element connectivity와 native node/element ID를 manifest에 함께 보존해야 한다. 이러한 일반 mesh-project 계약은 현재 fixture catalog만으로 완성되어 있지 않다.

## 5. 후처리 코드와 데이터 계약

| 위치 | 재사용할 동작 | 아직 제공하지 않는 것 |
|---|---|---|
| [`response_field.py`](../caelab/response_field.py) | `display_catalog`, `selected_response`; verified retained resources를 adapter가 읽고 정확한 response selection을 반환 | 범용 GUI scene 또는 모든 solver 포맷 지원 |
| [`response_history.py`](../caelab/response_history.py) | `history_catalog`, `source_channels`; retained native bytes를 source hash와 연결하고 bounded JSON reading | 임의 time resampling, 자동 시간축 병합/정렬 |
| [`pde_response_fields.py`](../caelab/adapters/pde_response_fields.py) | native node ID 0 포함, field dimension/component/time, imported mesh와 source binding, dimensionless unit 보존 | 모든 PDE 형태와 arbitrary mesh/field 위치 지원 |
| [`plasticity_response_fields.py`](../caelab/adapters/plasticity_response_fields.py) | node/element/Gauss point/subpoint 위치, displacement mm·Cauchy stress MPa·reaction N, signed component와 derived magnitude 구별 | integration point 값을 자동 nodal smoothing/extrapolation한 것처럼 표시하는 기능 |
| [`openradioss_history.py`](../caelab/adapters/openradioss_history.py) | native history channel semantics, `TIME`와 `TIME-dt/2`, wall `FNZ`/impulse 등 source channel 보존 | 서로 다른 sampling convention을 이름이 비슷하다는 이유로 동일 시간축으로 간주하는 기능 |
| remote [`file_table.py`](https://github.com/pikachu444/autonomous-cae-lab/blob/fc7c82dfcf4a6155ff18b7ebd5b91388916e6a9e/caelab/adapters/file_table.py) | `preview_table`, `read_table`, `TableReaderAdapter`; solver/runtime 없이 CSV/semicolon/tab/space/fixed-width, UTF-8 BOM, Fortran D exponent, `allow_pickle=False` NPZ. column/unit/component/location/axis를 명시. NaN/Inf 차단, source hash 기록 | field는 flat values; 일반 spatial topology와 native node/element ID mapping은 이 reader에 없음. 축은 strict increasing을 요구하므로 restart/중복 시각은 명시 segment/정리 정책이 필요 |
| remote [`evaluation.py`](https://github.com/pikachu444/autonomous-cae-lab/blob/fc7c82dfcf4a6155ff18b7ebd5b91388916e6a9e/caelab/evaluation.py) | `normalize_evaluation`, `save_evaluation`, `read_result`; JSON metadata와 개별 hashed NPY, memory mapping, selected response/row/time, retained native read. live solver 없이 재열기 | selected verification과 all-artifacts verification은 다름. GUI에서 한 response 읽기 성공을 전체 결과 무결성 확인으로 표시하면 안 됨 |
| remote [`external_files.py`](https://github.com/pikachu444/autonomous-cae-lab/blob/fc7c82dfcf4a6155ff18b7ebd5b91388916e6a9e/caelab/adapters/external_files.py) | operator-registered executable/argv template, token/fixed-column patch, source preservation, stale output 거부 | client가 임의 shell/program/path를 지정하는 실행기. 독립 후처리에는 실행 권한 없이 reader만 사용할 수 있어야 함 |

remote-only 코드는 이 작업 폴더에 존재하지 않으므로 현재 실행 가능한 local 기능으로 적지 않는다. 기존 구현을 이력과 함께 통합하거나 공통 reader로 명시적으로 추출하는 결정이 필요하다. 새 CSV parser를 병렬로 또 만드는 것은 우선순위가 낮다.

### 사용자에게 보이는 response 의미

후처리 선택은 최소한 source dataset/revision, part 또는 block, native node/element/integration point ID, component, time/step, unit, coordinate frame, source/derived 여부를 반환해야 한다. 화면 배열의 row index와 native ID는 별도 값이다. `stress magnitude`와 signed `Sxx`는 서로 대체할 수 없으며 integration-point stress를 nodal field처럼 표시하면 안 된다.

curve/CSV 전용 문서는 mesh나 CAD 없이도 열려야 한다. 반대로 spatial field는 topology/좌표가 없으면 유효한 3D contour인 것처럼 추정하지 않는다. 결측·unsupported component·잘린 파일·NaN/Inf는 0으로 채우지 않고 구체적인 오류 또는 빈값 상태로 표시한다. 서로 다른 결과를 비교할 때 시간·좌표·위치·단위가 맞지 않으면 차이 계산을 막거나 사용자가 선언한 변환/보간을 별도 derived artifact로 남겨야 한다.

### ParaView state의 실제 경계

공식 [Saving results](https://docs.paraview.org/en/latest/UsersGuide/savingResults.html)에 따르면 PVSM은 pipeline/views/properties 등을 복원하는 XML state이며 원래 data source를 다시 찾아야 한다. **PVSM 하나가 결과 데이터 복사본은 아니다.** project bundle에는 원본 결과/공통 manifest/reader 설정/PVSM을 함께 보존하고 상대경로 재배치 또는 명시 source remapping을 검증해야 한다. 현재 selection 및 일부 widget 등 transient GUI 상태가 모두 보존된다고 가정하지 않는다. 저장→앱 종료→다른 경로에서 열기를 실제로 시험한다.

## 6. 관련 시험과 이번 실행 결과

2026-10-08 13:51 KST, Windows, Python **3.13.5**, pytest **9.1.1**. 기존 dirty 파일을 보존한 local HEAD에서 다음 범위를 실행했다. 아래 네 개 시험 파일과 직접 조사한 코드에는 작업 변경을 가하지 않았다.

```text
python -B -m pytest -q -p no:cacheprovider tests/test_native_face_catalog.py tests/test_pde_response_fields.py tests/test_plasticity_response_fields.py tests/test_response_history.py
254 passed, 2 skipped in 16.08s
```

이는 synthetic/portable protocol fixture 시험이다. native geometry correspondence, 실제 FE solver 결과, 재료 물성 또는 engineering release를 입증하지 않는다. `test_native_face_catalog.py`에는 Windows symlink 생성 불가 시 skip과 POSIX-only native capture skip 경로가 있다. 이 실행에서 2 skips의 상세 reason은 별도 출력하지 않았다.

앞서 위 네 파일에 `tests/test_analysis_conditions.py`를 함께 지정한 수집은 `ModuleNotFoundError: No module named 'cadquery'`로 중단됐다. 그 실패에서 다섯 파일 시험이 통과했다고 세지 않았다. 의존성을 임의 설치하지 않고 portable 네 파일만 다시 실행했다. `test_analysis_conditions.py`는 CAD admission/projected condition 계약과 TEST_ONLY capturing solver를 사용하는 시험으로, 실행 가능해져도 native FEA proof가 되지는 않는다.

| 시험 | 코드 검토에서 확인한 의미/이번 실행 |
|---|---|
| [`test_native_face_catalog.py`](../tests/test_native_face_catalog.py) | 원본·catalog hash 변조/경로/revision 오류, 변경 source의 face ID 자동 재사용 거부. 위 portable 범위 실행 |
| [`test_pde_response_fields.py`](../tests/test_pde_response_fields.py) | 정확 node/time/component, native ID 0, mesh/source binding와 malformed input. 위 범위 실행 |
| [`test_plasticity_response_fields.py`](../tests/test_plasticity_response_fields.py) | integration point/subpoint, stress/displacement/reaction semantics, signed component 및 source guards. 위 범위 실행 |
| [`test_response_history.py`](../tests/test_response_history.py) | synthetic native history의 retained sample과 comparison join, source tamper 등. 위 범위 실행 |
| [`test_analysis_conditions.py`](../tests/test_analysis_conditions.py) | stale CAD/catalog, missing receipt, late condition mutation, 부분 제약/unsupported 선언, frozen child. **이번 실행은 cadquery import에서 막힘** |
| [`test_native_face_catalog_actual.py`](../tests/test_native_face_catalog_actual.py) | 실제 FreeCAD geometry acceptance용 경로. **이번 조사에서 미실행** |
| remote [`test_workbench_table_preview.py`](https://github.com/pikachu444/autonomous-cae-lab/blob/fc7c82dfcf4a6155ff18b7ebd5b91388916e6a9e/tests/test_workbench_table_preview.py) | 원문 보존, preview→실제 reader roundtrip, BOM/D exponent, chopped row, NaN/Inf를 header로 숨기지 않음, 잘못된/quoted/unsupported-comment 자료에 자동 mapping 제안 안 함. **읽기만, local 미실행** |

## 7. 이전 STEP/mesh spike의 활용 범위

읽기 참조 경로는 `C:/Users/pikac/Documents/Codex/2026-10-08/new-chat/work/cad-reuse-spike`의 `step_mesh_vtu.py`와 `artifacts/report.json`이다. 기록에는 Gmsh 4.15.2, meshio 5.3.5, PyVista 0.49.0으로 30×20×8 box STEP을 재import하고 관통공을 절삭한 뒤 7 faces, 564 nodes, 1,894 tetrahedra 및 VTU를 만든 내용이 있다. 조회 예제의 배열 row 429와 native element 670은 다르며 이 구분을 계속 보존해야 한다.

| 기존 artifact | 기록된 SHA-256 |
|---|---|
| 최초 STEP | `5e3d0bc41a73caac6faf8b0fa5a5353092950013201a16d5be17a1a4fdcaf158` |
| 절삭 후 STEP | `db181dd014b4ef52b25325af10731751e8710a57a6cd7646aab1d836a1aeffc8` |
| VTU | `d1ecbc41899fe088a8ddac9e8af48b63282b06b1b7233bf12e75847aa8333ac6` |

`synthetic_height_fraction`은 시연용 좌표 함수이며 stress/해석 결과가 아니다. offscreen PNG는 실제 GUI 조작·선택·저장 재개 proof가 아니다. 이번 조사자는 이 spike를 재실행하거나 artifact를 덮어쓰지 않았다. 새 acceptance에는 새 경로·ID를 사용한다.

## 8. 모든 ADR의 재사용 영향

표의 “갱신”은 기존 수치 증거/요구를 삭제한다는 뜻이 아니라 최신 독립 앱 방향에서 제품 결합 전제를 바꿔야 한다는 뜻이다. local 0001–0057은 현재 파일을 읽었고 0058–0059는 위 remote exact source를 읽었다. 세부 수락 상태는 해당 ADR이 참조하는 acceptance 문서를 계속 따른다.

| ADR | 결정의 요지 | 전처리·후처리 영향 |
|---|---|---|
| 0001 | Core/도메인 plugin/backend adapter 분리, pinned reuse | 유지. 앱은 동일 계약을 사용하고 native syntax는 adapter에 둠 |
| 0002 | 검증된 CAD revision에 붙는 append-only child analysis | 유지. 재실행은 새 child/result; 과거 수정 금지 |
| 0003 | 재현 가능한 DOE와 수치 sampling | 유지. 앱의 campaign UI는 기존 수치 engine을 호출 |
| 0004 | saddle load를 명시적으로 discretize | 유지. 화면 load와 실제 node/element projection 근거 연결 |
| 0005 | bounded adaptive numerical optimization | 유지. LLM에 수치 optimizer 역할을 넘기지 않음 |
| 0006 | 공통 Core의 declared weak-form PDE | 유지. CAD 없이 PDE 문서 가능 |
| 0007 | fixture CAD를 넘어선 declared-model analysis | 유지. CAD가 모든 문서의 필수 parent가 아님 |
| 0008 | 공통 Lab API 위 local engineer surface | API 경계 유지; 하나의 browser surface 전제는 독립 앱에 맞춰 갱신 |
| 0009 | declared-model inputs를 기존 campaign에서 탐색 | 유지. 별도 앱용 numerical scheduler를 중복 생성하지 않음 |
| 0010 | material inverse runtime을 명시 admission | 유지. 작업별 runtime capability와 read capability 구분 |
| 0011 | pinned OpenScience runtime/command ownership | 연구 연계 시 유지; CAD/결과 앱의 필수 startup 조건은 갱신 |
| 0012 | 명시 research model과 공식 ChatGPT 인증 | 연구 연계 시 유지; 독립 file workflow에 인증 강제 안 함 |
| 0013 | managed research project와 external source root | source 경계 유지; 앱 project bundle의 경로와 연결 명시 |
| 0014 | positional collision 없는 native sketch selector | 유지. UI 표시 index를 영구 key로 사용하지 않음 |
| 0015 | private native preparation과 registry publish 복구 | 유지. Save/Apply 실패 때 기존 파일/등록 보호 |
| 0016 | 기존 Core 위 명시된 research purpose | 연구 옵션에 유지; 단순 결과 보기의 필수 입력은 아님 |
| 0017 | bounded structural family research | 유지. 지원 family와 일반 기능을 구별해 표시 |
| 0018 | long-running job과 별도 verification scheduling | 실행 연계 시 유지. 앱 종료/취소와 job 상태 의미 명시 |
| 0019 | rectangle PDE와 named mixed scalar boundaries | 유지. boundary names/수치 의미를 condition UI에 보존 |
| 0020 | transient scalar PDE와 complete histories | 유지. time step과 전체 retained history를 보존 |
| 0021 | vector Lamé weak form | 유지. vector component/frame/단위와 scalar를 구별 |
| 0022 | conforming material interface의 coupled fields | 유지. field별 위치와 interface identity 유지 |
| 0023 | immutable imported mesh/named physical boundaries | 유지. native mesh/physical group/source hash의 핵심 근거 |
| 0024 | 명시 PDE research scope와 same-record field inspection | 유지. 표시 값과 연구 해석이 같은 retained record를 참조 |
| 0025 | bounded finite-rotation beam adapter | 유지. 지원 이론 범위와 결과 단위를 명시 |
| 0026 | finite-strain SVK material point | 유지. point-only 문서/response 허용 |
| 0027 | bounded material-point research | 유지. spatial mesh를 임의 만들어 의미를 바꾸지 않음 |
| 0028 | Maxwell state/정확 ramp reference/execution evidence | 유지. 초기 상태·history·reference 출처를 보존 |
| 0029 | bounded viscoelastic point research | 유지. 모델/물성 scope와 history conventions 표시 |
| 0030 | bounded frictionless contact foundation | 유지. 일반 접촉 기능 또는 물리 승인으로 확대하지 않음 |
| 0031 | bounded contact-patch research | 유지. 실패/invalid metrics도 비교에서 남김 |
| 0032 | original fixture assembly를 CAD parent로 보존 | 유지. 시각화 편의를 위해 원본 assembly를 대체하지 않음 |
| 0033 | Lab 질문을 공식 research control plane으로 전달 | optional research 연계로 재배치; 앱 기본 조작과 분리 |
| 0034 | 명시 fixture refinement input와 truthful answers | 유지. refinement/mesh 변경을 새 입력·결과로 기록 |
| 0035 | 목적별 verification, full mesh sweep 비강제 | 유지. inspection 성공과 numerical/engineering 검증을 구분 |
| 0036 | explicit selected-mesh research scope | 유지. 선택된 mesh/조건/단위 범위를 UI에서 확인 |
| 0037 | durable HTTP job journal/conservative restart | 실행 연계 시 유지. 프로그램 종료 후 임의 성공/재시작 금지 |
| 0038 | immutable scalar response와 declared observation 비교 | 유지. comparison source와 위치를 기록 |
| 0039 | exact retained native history samples | 유지. 자동 sampling/보간을 원본 값으로 표시하지 않음 |
| 0040 | 같은 retained observation comparison 해석 | 유지. 그래프·연구 답·수치 표가 같은 record를 참조 |
| 0041 | native plugin admission 직렬화, 실행 독립 | 유지. 앱 plugin discovery가 global solver lock이 되지 않음 |
| 0042 | human FCStd input을 native workflow로 연결 | 전처리 재사용 핵심. managed import/원본 보존 |
| 0043 | revision-bound mechanical conditions | 전처리 재사용 핵심. stale condition 실행 차단 |
| 0044 | numerical campaign의 frozen human conditions | 유지. campaign 중 조건을 현재 GUI 값으로 바꾸지 않음 |
| 0045 | cancelled result와 consistent read semantics | 유지. 취소 후 얻은 artifact/status를 정직하게 표시 |
| 0046 | native face mechanics와 one engineering workspace | face semantics 유지. 하나의 workspace 화면 결합은 독립 앱에 맞춰 갱신 |
| 0047 | fixed CAD에서 declared scalar condition 탐색 | 유지. geometry 고정과 조건 변화의 차이를 표시 |
| 0048 | exact retained field location의 general observations | 후처리 핵심. native IDs/component/time 위치 보존 |
| 0049 | retained assembly evidence와 verifier version 명시 | 유지. 현재 verifier와 과거 solver source를 구분 |
| 0050 | common native condition/retained response reader | 양 앱의 공통 계약 재사용 핵심 |
| 0051 | common numerical targets/selected PDE research | 유지. 목표 response와 field scope를 명시 |
| 0052 | selected material FE input/native responses | 유지. Gauss point/subpoint와 material input source 보존 |
| 0053 | selected explicit conditions/native history | 유지. native 시간축/힘/에너지 의미를 유지 |
| 0054 | frozen observed targets/common numerical reports | 유지. 후처리 comparison/report의 입력을 frozen source로 기록 |
| 0055 | declared distributions/multiobjective/coupled inputs | 유지. 수치 의미·조건을 UI 기본값으로 조용히 변경하지 않음 |
| 0056 | request-local verified read/explicit family routing | 유지. 효율적 읽기와 정확 adapter routing을 함께 보존 |
| 0057 | qualified runtime/retained numerical interpretation | numerical/runtime 증거 유지. 연구 실행을 independent inspection의 필수 조건으로 삼지 않음 |
| 0058 (remote) | local workbench의 native responses/scoped expert host | retained reader·공통 execution owner 재사용. host는 optional; mock/CI가 GUI 수락을 대신하지 못함 |
| 0059 (remote) | 별도 pinned OpenCourant explicit successor admission | old/new runtime identity·history schema 분리 유지. post reader가 pin별 채널 차이를 지우지 않음 |

remote ADR: [0058](https://github.com/pikachu444/autonomous-cae-lab/blob/fc7c82dfcf4a6155ff18b7ebd5b91388916e6a9e/ADR/0058-local-workbench-native-responses-and-expert-host.md), [0059](https://github.com/pikachu444/autonomous-cae-lab/blob/fc7c82dfcf4a6155ff18b7ebd5b91388916e6a9e/ADR/0059-pinned-explicit-solver-successor.md). 이 조사 문서는 ADR를 변경하거나 제품 방향 변경을 최종 승인하지 않는다.

## 9. 다음 구현 결정에 필요한 구체 수락

1. **전처리:** FreeCAD에서 실제 STEP/native CAD 열기→형상 편집→face 선택→typed 조건→Gmsh volumetric mesh→node/element/face group 점검→editable CAD+mesh+manifest 저장→종료/재열기. 화면 선택과 저장된 ID/좌표/단위를 대조한다.
2. **변경 실패 경로:** geometry revision 변경 후 stale face/mesh 조건을 표시하고 export/solver submission을 차단한다. 잘못된 형상·mesh·단위·unsupported 조건·중간 저장 실패에서 이전 revision/result를 보존한다.
3. **후처리:** 실제 mesh-associated 결과와 CSV-only 문서를 별도로 열기→원본 native ID 선택→값/단위/component/time 확인→slice/probe/curve→여러 결과 비교→source 포함 project 저장→다른 경로/새 프로세스에서 복원. synthetic field는 시연 자료로 표시한다.
4. **계약·성능:** selected read와 all-artifact integrity 구분, 대용량 bounded read/메모리 수명주기, 잘린/변조 파일, 결측, repeated/restart time, integration-point 위치, mesh 없는 curve, 지원 안 되는 포맷을 확인한다.
5. **제품 판단:** 위 GUI 수락을 실제 기존 앱 확장으로 통과시킨 뒤 필요한 custom shell 범위를 확정한다. 렌더링 screenshot 한 장이나 command exit 0만으로 mature GUI 대안이 동등하다고 판단하지 않는다.

이 수락은 기존 52-section ledger의 잔여 요구를 삭제하지 않는다. 실제 native solver별 numerical qualification, 물리/강도/내구 검증과 회사 배포 승인은 각 acceptance record의 열린 gate로 계속 남는다.
