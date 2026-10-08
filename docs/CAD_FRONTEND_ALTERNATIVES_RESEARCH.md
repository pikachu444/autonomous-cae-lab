# CAD 전처리 후보 재검토

조사일: 2026-10-08. 범위: FreeCAD, SALOME/SHAPER/SMESH, PrePoMax의 공식 자료와 기존 저장소 조사 기록. 후보 설치·새 GUI 조작·동일 모델의 비교 실행·솔버 실행은 수행하지 않았다. 이 문서는 도구 선택의 조사 근거이며 구현 수락이나 최종 채택 ADR이 아니다.

## 기존 검토가 있었는가

[PREPOST_REUSE.md](PREPOST_REUSE.md) 3절은 SALOME과 PrePoMax를 포함해 FreeCAD workbench, OCCT, Gmsh, ParaView, 자체 Qt/VTK 앱을 비교했다. [CAE_PLATFORM_REFERENCE_RESEARCH.md](CAE_PLATFORM_REFERENCE_RESEARCH.md)도 SALOME·FreeCAD FEM·PrePoMax를 검토했으며 후보 설치·실행 검증이 아니라 공식 문서 비교라고 명시했다. 따라서 대안을 전혀 조사하지 않았다는 설명도, 동일 모델을 직접 비교해 FreeCAD가 최선임을 증명했다는 설명도 정확하지 않다.

현재 로컬 HEAD는 `4843c66e482ded31c59604d7cc19d1800be388f4`, fixture submodule pin은 `3e48bf6138f495299f45b1af254bfb4aaff307b8`이다. 작업 트리에 다른 담당자의 전후처리 작업과 기존 수정이 있다. 이 조사에서는 이를 변경하지 않았다. exact CI와 배포 파일 확보는 기존 [PREPOST_VERIFICATION.md](PREPOST_VERIFICATION.md)에 기록되어 있으며, 이번 조사는 새 CI·네이티브 검증을 추가하지 않는다. 과거 검증 기록의 상태를 현재 후보별 실행 사실로 확대하지 않는다.

## 공식 기능과 미검증 영역

| 요구 | FreeCAD | SALOME / SHAPER / SMESH | PrePoMax |
|---|---|---|---|
| 편집 가능한 설계 CAD | 객체 속성·재계산·undo/redo·모델 이력과 Python 확장. 기존 FCStd adapter를 재사용할 수 있다. [공식 기능](https://www.freecad.org/features.php), [현재 재사용 기록](PREPOST_REUSE.md) | SHAPER는 파라메트릭·구속 기반 CAD이며 치수 변경에 따른 형상 업데이트와 다부품 결합을 설명한다. 해석용 영역/group 구성도 설계 목표다. [공식 SHAPER 설명](https://www.salome-platform.org/?page_id=327) | CAD 교환 파일을 가져와 해석 모델을 준비한다. 조사한 공식 기능에서 일반 스케치·피처 이력 설계 편집기의 대체 근거는 확인하지 못했다. [제품 설명](https://prepomax.fs.um.si/) |
| 스케치 구속 | 파라메트릭 설계 환경과 기존 sketch constraint adapter가 있다. 현재 앱의 실제 수락은 별도다. [공식 기능](https://www.freecad.org/features.php), [재사용 adapter 기록](PREPOST_REUSE.md) | 거리·각도·반지름·접선·일치 등의 구속, 잔여 자유도 표시, 과구속 안내와 복구, Python `model.addSketch`가 문서화되어 있다. [Sketch 문서](https://docs.salome-platform.org/latest/gui/SHAPER/SketchPlugin/SketchPlugin.html) | 전통적 CAD sketch constraint editor로는 미확인. CAD import가 해당 기능을 의미하지 않는다. [제품 설명](https://prepomax.fs.um.si/) |
| 조립·관절·기구 운동 | 내장 Assembly는 1.0부터, joint simulation/animation은 1.1 release의 기능으로 구분한다. 현재 source에도 revolute·slider·ball 등의 joint가 있다. 실제 사용자 모델에서의 운동·저장·복원은 미검증. [공식 기능](https://www.freecad.org/features.php), [1.1 release](https://freecad.github.io/Website/download/releases/1-1/), [joint source](https://github.com/FreeCAD/FreeCAD/blob/main/src/Mod/Assembly/JointObject.py) | 공식 자료는 단순 다부품 조립과 placement를 설명한다. 조사한 문서에서는 관절을 구동하는 기구 운동 검토와 동일 수준의 저장·복원을 확인하지 못했다. 기능 부재의 확정은 아니다. [SHAPER 설명](https://www.salome-platform.org/?page_id=327), [기능 목록](https://docs.salome-platform.org/latest/gui/SHAPER/index.html) | spring·rigid·tie·frictional contact 등 해석 연결을 제공한다. CAD 관절 기구 운동 검토와는 수락 대상이 다르다. [공식 기능](https://prepomax.fs.um.si/features/) |
| 메시·영역·품질 | 기존 Gmsh/해석 adapter와 연결하는 경로가 있다. 이 사실만으로 고급 mesh editor의 깊이를 판정할 수 없다. [재사용 기록](PREPOST_REUSE.md) | SMESH의 submesh, group/filter, smoothing/remesh, quality control와 Python interface가 문서화되어 있다. skew·aspect ratio·scaled Jacobian 등 inspection 기능이 명시되어 있어 고급 mesh 작업의 직접 비교 후보다. [SMESH 문서](https://docs.salome-platform.org/latest/gui/SMESH/index.html) | Netgen/Gmsh mesh, geometry 또는 mesh 선택을 통한 node/element/surface set, field animation/history plotting이 있다. CalculiX 중심 전후처리의 강한 후보다. [제품 설명](https://prepomax.fs.um.si/), [기능](https://prepomax.fs.um.si/features/) |
| Windows·파일 재개 | 공식 Windows 배포 후보와 기존 FCStd 경로는 이미 조사되었다. 새 전처리 완성품의 독립 저장·재개 수락과 구분한다. [재사용 기록](PREPOST_REUSE.md) | 공식 다운로드에 Windows 10 exe/zip 선택이 있고 Study 저장·모듈 데이터 persistence를 설명한다. 현재 Windows host에서 재개를 실제 실행하지 않았다. [배포](https://www.salome-platform.org/?page_id=2430), [Study FAQ](https://www.salome-platform.org/?page_id=428) | Windows portable 후보가 기존 조사에 기록되어 있다. 현재 host 설치·실행과 범용 solver 독립성은 미검증이다. [공식 배포](https://prepomax.fs.um.si/downloads/), [재사용 기록](PREPOST_REUSE.md) |
| Python·headless·MCP | Python console/macro/workbench와 FreeCADCmd가 있다. headless에는 GUI document/view-provider 제한이 있다. Python 가능성을 모든 GUI 명령의 headless 실행이나 범용 공식 MCP로 확대하지 않는다. [공식 기능](https://www.freecad.org/features.php), [공식 저장소 headless 문서](https://raw.githubusercontent.com/FreeCAD/FreeCAD-documentation/main/wiki/Headless_FreeCAD.md) | GUI의 Python dump, TUI batch, Windows sessionless 설정과 Python API가 문서화되어 있다. MCP가 필요한 경우 별도 adapter 계약과 실행 검증이 필요하며, 이번 조사에서는 공식 범용 MCP를 확인하지 못했다. [FAQ](https://www.salome-platform.org/?page_id=428) | 공식 자료의 확인 범위는 CalculiX 전후처리와 파일 연계다. 일반 Python CAD automation 또는 범용 MCP를 확인하지 못했다. 명령행 regeneration 범위는 기존 조사에 기록되며 모든 GUI 동작의 headless 실행 근거가 아니다. [제품 설명](https://prepomax.fs.um.si/), [기존 조사](CAE_PLATFORM_REFERENCE_RESEARCH.md) |

## 선택에 대한 판단

사용자가 요청한 Ponytail의 기존 도구·API 재사용 원칙도 선택 기준에 포함한다. 기존 native 앱과 필요한 API/MCP 연결로 전체 작업을 충족할 수 있는지를 먼저 평가하고, 새 frontend·대규모 wrapper 구현량을 후보의 장점으로 계산하지 않는다. skill 적용과 Onshape/Fusion/CadQuery 조사 상세는 주 담당자가 보완한다. [Ponytail skill](https://github.com/DietrichGebert/ponytail/blob/main/skills/ponytail/SKILL.md)

**FreeCAD가 보편적으로 최선이라는 결론은 아직 근거가 없다.** 기존 FCStd·pinned adapter·Python workbench를 재사용하면서 설계 이력과 관절 운동까지 제공하려는 현재 요구에서는 우선 검증 후보로 설명할 수 있다. 이는 전환·통합 범위에 대한 판단이고, 성능·안정성·사용성의 우승 판정은 아니다.

SALOME는 실제 설계 CAD 대안이다. 특히 simulation group·비정상 연결 형상·SMESH의 mesh 편집과 품질 관리가 핵심 작업이라면, FreeCAD 중심 설계만으로 배제할 이유가 없다. 다만 단순 조립 지원이 현재 요구인 관절·운동 경로·기구 동작 검토까지 충족한다는 증거는 따로 필요하다. 공식 SHAPER의 group 업데이트 설명도 프로젝트의 revision/face 재결합이 자동으로 안전하다는 판정으로 사용할 수 없다. [SHAPER 공식 설명](https://www.salome-platform.org/?page_id=327), [SMESH](https://docs.salome-platform.org/latest/gui/SMESH/index.html)

PrePoMax는 CalculiX 구조 FEA의 조건 편집·mesh·결과 작업을 비교할 때 적합하다. 해석 연결과 모델 준비가 강점이라는 공식 근거를, 스케치부터 관절 조립까지 갖춘 CAD 설계 도구의 대체 증거로 사용하면 안 된다. [공식 제품 설명](https://prepomax.fs.um.si/)

실제 채택을 확정하려면 동일 요구에 대해 대표 CAD의 치수/구속 편집, 실패·undo 복구, 관절 운동, native 저장·종료·재열기, group와 조건 연결, mesh 품질 inspection, GUI와 headless의 동일 revision을 비교해야 한다. 제품별 지원하지 않거나 미확인인 항목을 명시하고 기존 역사적 실험과 다른 경로/ID에 증거를 남긴다. 이는 다음 비교 수락의 제안이며 이번에 실행한 벤치마크가 아니다. 기존 Core/Domain/adapter 소유권이나 pinned 구현은 이 조사로 변경하지 않는다.

## Root 보강: 코드 CAD와 상용/클라우드 후보

2026-10-08 공식 자료를 확인했다. 후보 설치, 계정 로그인, 회사 CAD 업로드, MCP 연결 또는 같은 모델의 성능 비교는 실행하지 않았다.

- **CadQuery / build123d:** Python으로 BREP 파라메트릭 모델을 생성하는 코드 CAD. CadQuery는 의도적으로 GUI 없이 사용할 수 있는 라이브러리이며 CQ-editor 등 GUI를 별도로 둔다. 반복 생성·변수 탐색을 위한 후보지만, 사용자가 스케치/형상 이력을 화면에서 직접 편집하는 완성 CAD 앱의 대체 여부는 별도 검증해야 한다. 이 저장소는 이미 pinned CadQuery adapter를 사용하므로 새 도입 후보라고 표현하지 않는다. [CadQuery 소개](https://cadquery.readthedocs.io/en/latest/intro.html), [build123d 소개](https://build123d.readthedocs.io/en/latest/introduction.html).
- **Onshape:** 공식 Onshape Labs FeatureScript MCP(발표 2026-08-11)가 자연어→FeatureScript 생성·문서 삽입·실행·오류 평가·수정 경로를 제공한다. 이는 편집 가능한 재사용 파라메트릭 custom feature 생성 후보다. Labs early access이며 자료의 범위는 FeatureScript: 임의 assembly/CAE/solver 전체 자동화를 입증하지 않는다. 계정·App Store 구독·HTTP MCP 연결이 요구된다. 무료 플랜 문서는 공개된다고 공식 안내한다. 로컬 독립 앱/회사 비공개 CAD 요구와의 적합성은 구분해야 한다. [공식 MCP 소개](https://www.onshape.com/en/blog/featurescript-mcp-server-enables-text-code-cad), [공식 플랜/데이터 안내](https://www.onshape.com/en/blog/understand-your-cad-plan), [FeatureScript 도입](https://cad.onshape.com/FsDoc/intro.html).
- **Autodesk Fusion:** Python/C++ scripts/add-ins와 parameter 편집 공식 예제가 있어 확장 가능한 상용 CAD 후보다. CAD API가 있다는 사실을 simulation 전체 API/무인 solver 지원으로 확대하지 않는다. 이번 조사는 설치·MCP 채택·전체 해석 automation 검증이 아니다. [공식 Fusion API](https://aps.autodesk.com/developer/overview/autodesk-fusion-api), [scripts/add-ins](https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-9701BBA7-EC0E-4016-A9C8-964AA4838954).
- **FreeCAD 기능 부재와 검증 부재 구분:** 공식 1.1 release notes에는 assembly joint motion simulation/animation이 있다. 현재 prototype에서 조립 운동을 검증하지 않았다는 사실은 upstream에 기능이 없다는 뜻이 아니다. [FreeCAD 1.1 notes](https://freecad.github.io/Website/download/releases/1-1/). 앞서 확인한 [FreeCAD MCP](https://github.com/neka-nat/freecad-mcp)는 third-party 구현이며 현재 설치 환경의 연결 acceptance는 NOT_RUN.

## 현재 판단과 다음 비교 기준

FreeCAD가 무조건 최선이라는 판정은 없다. 무료/local/native 편집/Python 확장/현재 FCStd adapter 재사용 조건에서는 유력한 기본 후보다. CAE 메시/group/quality가 우선이면 SALOME을 직접 비교할 가치가 높고, CalculiX 중심 구조 해석 UX라면 PrePoMax가 후보, 코드로 반복 생성한다면 이미 있는 CadQuery와 build123d, 클라우드/상용을 허용하는 AI CAD라면 Onshape/Fusion을 별도 후보로 삼을 수 있다. 이는 공식 기능과 현재 통합 상태를 바탕으로 한 판단이지 runtime benchmark 승자가 아니다.

판정 전 동일 모델로 CAD 생성/수정, sketch 제약, assembly joint motion, face/group 재결합, mesh quality/local refinement, 조건 설정, AI/API 제어, 저장/종료/재열기, 원본 ID/개정 보존을 비교해야 한다. 현재 새로 완료된 native run 또는 solver acceptance는 0이다. 기존 numerical/engineering verdict는 바뀌지 않는다.
