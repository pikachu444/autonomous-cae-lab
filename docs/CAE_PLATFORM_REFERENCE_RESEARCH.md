# CAE 플랫폼 참고 조사와 재사용 계획

작성: 2026-10-06 KST / 조사: 2026-10-05 UTC. 기준 저장소 main: 535266ae7e4bd03d1bcafb714314bf4ad4599041.

사용자 요청: 요구와 유사한 오픈소스·서비스를 조사하고, 전체 뼈대를 먼저 연결한 뒤 세부 기능을 보완한다. 사용자는 목적을 **제품 불량이 발생하는 조건·메커니즘을 재현하고 원인 가설을 연구하는 것**, **실험용 지그 제작 전에 원하는 시험이 가능한지 판단하는 것**으로 명확히 했다. 기존 52개 요구와 Phase 1–7을 유지한다.

## 결론

이 목적의 가까운 참고는 **시험–해석 비교·역추정·민감도·강건성 연구**다. Dakota, GEMSEO 계열과 LS-OPT/optiSLang의 해당 기능을 우선 비교한다. SimScale Agent는 조건 편집과 실행 화면의 참고이며 사용자가 원하는 불량 연구 전체와 동일한 제품으로 판정하지 않는다. 오픈 솔버의 실제 모델링·후처리는 FreeCAD FEM·PrePoMax·SALOME-MECA를 재사용할 수 있다. 이는 공식 자료 비교에 따른 Root의 판단이며 후보 설치·실행 검증은 아니다.

우리 시스템의 공통 실행 골격도 상당 부분 이미 있다. 새 플랫폼을 처음부터 만들기보다 기존 Core의 연구·개정·작업·실험·캠페인·비교·보고서 경로를 연결하고, 전문 UI·수치 엔진·후처리는 아래 프로젝트에서 재사용할 부분을 선택한다. 조사 범위에서 초기52 요구 전부를 그대로 충족하는 단일 제품은 확인하지 못했다.

## 사용자 연구 목적과 먼저 연결할 흐름

| 연구 | 입력과 연구 순서 | 결과와 현재 한계 |
|---|---|---|
| **제품 불량 재현** | 관찰된 위치·형태·발생 조건/측정 → 경쟁 원인 가설 → 가설에 대응하는 모델·변수·응답 → DOE/민감도·조건 탐색 → 실제 현상과 비교 → 가설을 구별하는 다음 시험 | 재현되는 조건 범위, 일치/불일치하는 응답, 설명하지 못한 현상. 잘 맞는 해석 하나만으로 원인을 확정하지 않는다. 현재 measured response 매핑·일반 역추정은 미구현이며 기존 synthetic MFront 사례로 대신하지 않는다. |
| **제작 전 지그 검토** | 시험 목적·시험체·장비/허용 하중·변위 → 기존 editable 지그 CAD → 재료·체결/접촉·하중·구속 → 간섭·하중 경로·반력·지그/시험체 변형 → 조건/설계 변경·비교 | 시험을 방해하는 지그 변형·미끄럼·접촉/장착 문제와 남은 확인 사항. 기존 CAD 재사용; 단일 지지부 계산과 원본 전체 조립체 mechanics를 구분한다. 전체 조립체 mechanics 및 실제 장비 적합성은 아직 OPEN이다. |

예를 들어 특정 하중에서 한쪽이 휘는 불량은 편심 하중·접촉/체결·재료 편차라는 서로 다른 가설을 둘 수 있다. 불량 위치/변형 모양/하중–변위 응답을 함께 비교하고, 한 조건에서만 맞는 후보와 다른 조건에서도 맞는 후보를 구분한다. 이는 연구 절차의 예이며 실제 제품 데이터를 받은 판정이 아니다. 지그는 자체 강성만 볼 것이 아니라 원래 측정하려는 시험체 응답을 왜곡하는지까지 목적에 맞게 확인한다.

OpenScience는 관찰·가설·계획·해석을 연결한다. Core는 같은 모델/조건/실험/근거의 연결을 보존하고, Domain은 재현 응답·시험 목적별 판정·물리 모델을 정의한다. 수치 engine이 조건/설계 후보를 생성하고 adapter가 솔버를 실행한다. LLM이 임의 후보를 최적해나 원인으로 선언하지 않는다.

Dakota의 공식 [calibration terms](https://snl-dakota.github.io/docs/latest_release/users/usingdakota/reference/responses-calibration_terms.html)는 해석–관측 잔차와 척도/가중치·제약을 정의한다. [실험 데이터 입력](https://snl-dakota.github.io/docs/latest_release/users/usingdakota/reference/responses-calibration_terms-calibration_data_file.html)은 시험 조건·관측값·측정 오차를 함께 다루고, [field calibration](https://snl-dakota.github.io/docs/latest_release/users/usingdakota/reference/responses-calibration_terms-field_calibration_terms.html)은 공간/시간 좌표에 맞춘 비교를 설명한다. [model discrepancy](https://snl-dakota.github.io/docs/latest_release/users/usingdakota/reference/method-bayes_calibration-model_discrepancy.html)는 보정 뒤에도 모델 형식 오류로 불일치가 남을 수 있다고 설명하며 해당 보정 기능 자체는 experimental이다. 우리가 채택할 것은 명시적 관측–응답 연결 원칙이며 Dakota 설치/이식 완료가 아니다.

### 이 목적에 가까운 연구 도구

독립 조사자는 아래 공식 본문을 읽었다. LS-OPT FAQ는 첫 조회 성공 후 재조회 timeout이었다. 설치·실제 역추정은 수행하지 않았다.

| 후보 | 확인한 기능과 참고할 부분 | 적용 한계 |
|---|---|---|
| **OpenTURNS (오픈소스)** | 관측 입출력·사전분포·오차 공분산을 이용한 비선형 Gaussian 보정, 매개변수 불확실성과 민감도 분석. 불량의 재료/접촉/구속 매개변수 역추정 계산 부품 후보. | CAD/물리 가설을 만들어 주는 플랫폼은 아니다. 오차/분포 가정·식별 가능성·반복 실행 비용을 확인해야 한다. |
| **LS-OPT (상용 참고)** | 측정 스칼라·곡선과 해석의 차이, crossplot·MSE/Curve Mapping·물리적 제약·민감도와 보정 이력. 하중–변위·히스테리시스 비교 흐름에 가깝다. | 곡선 비교 방식이 중요한 불량 차이를 숨기지 않도록 응답 정의가 필요하다. 현재 계정/라이선스/실행은 미확인. |
| **optiSLang (상용 참고)** | 기준 변위 신호에 질량·강성·감쇠를 맞추는 예제의 신호 차이→LHS DOE→민감도→최적화, 분포·상관관계를 이용한 강건성 평가. | 교육용 기준 신호는 실제 제품 측정 검증이 아니다. 실패 설계를 통계에서 제외하는 제품 동작과 별개로 우리 Core는 실패/invalid 기록과 영역을 보존한다. |

근거: OpenTURNS [보정 API](https://openturns.github.io/openturns/latest/user_manual/_generated/openturns.GaussianNonLinearCalibration.html), [민감도](https://openturns.github.io/openturns/latest/user_manual/sensitivity_analysis.html), [Chaboche 보정 예제](https://openturns.github.io/openturns/latest/auto_calibration/least_squares_and_gaussian_calibration/plot_calibration_chaboche.html), [공개 소스](https://github.com/openturns/openturns); LS-OPT [Parameter Identification FAQ](https://www.lsoptsupport.com/faqs/application-of-optimization/parameter-identification); optiSLang [시험 신호 보정 예제](https://ansyshelp.ansys.com/public/Views/Secured/corp/v242/en/opti_tut/opti_tut_cali_do_workbench.html), [Robustness Node](https://ansyshelp.ansys.com/public/Views/Secured/corp/v252/en/opti_ug/opti_ug_robustness_analysis.html).

OpenTURNS의 Chaboche 예제는 곡선 일치와 일부 매개변수의 큰 신뢰구간을 함께 보인다. 따라서 여러 가설이 같은 신호를 설명하면 원인은 미확인으로 유지한다. 다른 하중/구속 조건이나 별도 측정 위치에서 가설 간 예측 차이를 확인하는 절차는 이 근거에서 도출한 Root의 연구 설계다. 관찰–응답 매핑과 기존 DOE를 먼저 연결한 뒤 필요한 보정/UQ engine 하나를 선택하며, 후보 전체 설치로 개발을 지연시키지 않는다.

## 조사 방법과 한계

- 현재 세션 도구와 설치된 skill 목록·파일을 검색했으나 전용 Deep Research skill/도구를 찾지 못했다. 일반 웹 도구와 독립 지원 에이전트의 공식 자료 조사를 병행했다. ChatGPT 제품 전체의 Deep Research 가용성에 대한 판정은 아니다.
- Root: GEMSEO/OpenMDAO/RCE/Dakota/ParaView·trame/preCICE/AiiDA 공식 문서·저장소를 열었다. 독립 조사: SALOME·FreeCAD FEM·PrePoMax·SimScale·Rescale·Ansys·PhysicsX의 공식 자료를 비교했다.
- 독립 조사자가 SimScale Agent 본문과 PrePoMax v2.2 PDF, Rescale Assistant 본문을 성공적으로 열었다. Root의 일부 동일 URL 조회는 timeout이었다. Rescale Agents의 확장 Job Builder 설명과 PrePoMax 최신 다운로드 정보는 공식 검색 색인만 확인했으므로 설치·API 실행 사실로 사용하지 않는다.
- 계정 가입, 회사 자료 업로드, 솔버/provider 실행, 후보 설치, 연구 모델·인증 교체는 수행하지 않았다. 상용 서비스의 현재 계정 권한·실제 계산 성능과 제품별 전체 지원 범위는 미검증이다.

## 1. 모델을 만들고 해석하는 실제 플랫폼

| 후보 | 공식 자료에서 확인한 기능 | 우리 시스템에 적용할 부분 | 중요한 경계 |
|---|---|---|---|
| **SimScale + Agent** | 현재 simulation tree를 읽고 analysis/material/BC/mesh 설정을 대화로 변경한다. API에는 CAD·mesh·simulation/run·parametric subrun·결과/취소 경로가 있다. | 모델을 보면서 질문하고 적용된 조건·실행·후속 비교를 같은 작업에서 확인하는 제품 흐름. | 상용 클라우드. Engineering AI는 Enterprise 항목이고 API v1은 beta다. 계정·요금·지원 분석의 실제 사용은 미시험. |
| **PrePoMax** | CalculiX 모델의 재료·section·접촉·구속·하중·실행·field/history 표시. INP 가져오기와 FRD 결과 열기. | 기존 동일 INP/FRD를 사람이 확인하는 경로, 모델 tree·조건 편집·이력 그래프의 UI 참고. | CalculiX 중심. 모든 INP 명령의 import fidelity나 CAD 설계 의도 보존을 가정하지 않는다. CLI GUI-off는 매뉴얼상 regeneration에 한정. |
| **FreeCAD FEM** | 편집 가능한 CAD에 재료·하중/구속·contact/tie·메시·solver controller·결과 pipeline을 붙인다. Python으로 FEM 객체를 만들 수 있다. | 기존 FreeCAD adapter와 FCStd를 재사용해 CAD와 해석 조건을 같은 native 개정에서 확인. | solver별 기능 차이가 있다. 자체 자율 연구 loop가 확인된 것은 아니다. 문서 mirror는 archived, 현 코드의 지원을 별도 확인해야 한다. |
| **SALOME / SALOME-MECA / AsterStudy** | CAD/메시 group·quality·Python/batch, staged case 설정과 local/remote 실행·log/결과 조회. | 기존 Aster 입력과 원본 조립체 group의 인간 inspection, 입력 편집·단계 실행 참고. | AsterStudy는 Code_Aster 중심이며 generic SALOME이 모든 solver의 공통 물리 editor를 제공한다는 뜻은 아니다. |
| **Rescale Assistant + workflows** | 현재 job·log·result/history에 대한 자연어 조회·요약, input-deck validation·troubleshooting·report agent 연결. | 작업에 연결된 AI 맥락, 실패 요약, 실행·후처리·해석 workflow의 사용자 표시. | 상용 플랫폼·조직 feature/권한 필요. 범용 CAD/접촉/물성 editor로 확인한 것은 아니다. |

근거:

- SimScale: [Agent](https://www.simscale.com/docs/the-simscale-agent/), [lifecycle API](https://api.simscale.com/apidoc/swagger/index.html), [postprocessor](https://www.simscale.com/docs/post-processing/new-integrated-post-processor/), [Engineering AI access](https://www.simscale.com/product/pricing/).
- PrePoMax: [features](https://prepomax.fs.um.si/features/), [직접 읽은 v2.2 manual](https://prepomax.fs.um.si/wp-content/uploads/2024/10/PrePoMax-v2.2.0-manual.pdf), [downloads/license](https://prepomax.fs.um.si/downloads/). 최신 색인에는 v2.6.0/.NET4.8/GPLv3가 있으나 본문·설치는 미확인.
- FreeCAD: [FEM documentation mirror](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/FEM_Workbench.md), [Python tutorial](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/FEM_Tutorial_Python.md), [현재 ObjectsFem source](https://github.com/FreeCAD/FreeCAD/blob/main/src/Mod/Fem/ObjectsFem.py), [license](https://github.com/FreeCAD/FreeCAD/blob/main/LICENSE). Core는 LGPL2.1 계열.
- SALOME: [SMESH](https://docs.salome-platform.org/latest/gui/SMESH/index.html), [scripting](https://www.salome-platform.org/?page_id=428), [AsterStudy run management](https://code-aster.org/doc/v17/manuals/man_u/u1/u1.04.00/utilisation_asterstudy.html), [license inventory](https://www.salome-platform.org/?page_id=2630). SALOME LGPL2.1, AsterStudy GPLv3이며 일부 MeshGems component는 상용 runtime 조건이 있다.
- Rescale: [성공적으로 읽은 Assistant](https://rescale.com/documentation/using-the-rescale-assistant/), [workflow builder](https://rescale.com/documentation/main/platform-guides/workflows/), [Agents 색인](https://rescale.com/documentation/agents-product-documentation/).

Ansys PyMechanical/PyWorkbench도 같은 native 프로젝트를 GUI·Python/gRPC로 다루는 실제 참고다. Python client는 MIT지만 Mechanical/Workbench 자체는 별도 상용 의존성이다. [PyMechanical](https://mechanical.docs.pyansys.com/version/stable/), [examples](https://mechanical.docs.pyansys.com/version/stable/examples/index.html), [PyWorkbench](https://workbench.docs.pyansys.com/version/stable/). Mechanical Copilot의 확인된 공개 설명은 맥락 도움말·학습/support 중심이므로 임의 모델의 자율 생성·실행 완료 근거로 쓰지 않는다. [공식 설명](https://www.ansys.com/webinars/smarter-engineering--introducing-ansys-engineering-copilot-in-me).

PhysicsX는 simulation workbench·parameterized runs·traceable dataset·학습된 Deep Physics Model을 설명한다. 공개 코드/API와 임의 CAE 조건 지원은 이 조사로 확인하지 못했다. 오래된 Ai.rplane demo는 현재 종료 안내가 있어 당장 쓸 서비스로 추천하지 않는다. [platform](https://www.physicsx.ai/platform), [automation architecture](https://www.physicsx.ai/newsroom/numerical-simulation-automation-architecting-the-foundation-of-intelligent-engineering), [현재 demo 안내](https://www.physicsx.ai/newsroom/welcome-to-airplane).

## 2. 탐색·후처리·분산 실행은 성숙한 구성요소를 이용한다

| 후보 | 확인한 역할 | 적용 판단 |
|---|---|---|
| **GEMSEO** | 외부 executable/Python/web service를 discipline으로 연결하고 DOE·최적화·MDO·UQ·surrogate·evaluation backup·remote transfer를 제공. | Phase3/7 확장의 우선 수치 framework 후보. 기존 SciPy LHS/DE는 유지하고 필요한 UQ/다목적/다분야 기능 하나를 engine adapter로 연결한다. |
| **OpenMDAO** | Component/Group/Driver, ExternalCodeComp와 file wrapping, 기록·재조회 및 DOE. | 연계 모델·미분 기반 MDO가 필요한 경우의 대안. 기존 독립 solver를 새로 구현하는 framework가 아니다. |
| **Dakota** | simulation 기반 parameter study·optimization/calibration·sensitivity/UQ·surrogate 및 evaluation restart 기록. | file-driven 솔버와 장시간 탐색·재개를 위한 대안. evaluation 재사용과 살아 있는 solver process 재접속은 구분한다. |
| **ParaView / VTK / trame** | 실제 field pipeline, Python/batch, 웹 local/remote rendering와 contour·array·view 상태를 구성. | 범용 field/time-history·대규모 후처리의 우선 재사용 후보. 완료한 fixture/PDE/contact viewer를 보존하고 필요한 공통 후처리 경계를 확장한다. |
| **RCE** | 외부 도구의 표준 input/output를 잇는 executable graph, 자동 실행·분산 공유·결과 관리. | 전체 뼈대의 좋은 구조 참고. 현재 Core를 유지하면서 typed input/output와 dependency 표시를 도입; 도구 전체 교체는 별도 판단. |
| **AiiDA** | CalcJob/WorkChain·입력-계산-출력 provenance·scheduler/plugin 실행. | 향후 원격/HPC adapter 및 보존·재접속 설계의 참고. 도입에는 DB/daemon/adapter 운영과 현재 Core 기록 매핑이 필요하다. |
| **preCICE** | 독립 물리 solver 사이의 partitioned coupling과 기존 CalculiX/Code_Aster/FEniCSx/OpenFOAM adapters. | 실제 열-구조/유체-구조 연계가 필요할 때 후보. 연구 agent·최적화 engine·전후처리 전체를 제공하는 제품은 아니다. |

근거:

- [GEMSEO 기능](https://gemseo.org/), [Python3.12 지원과 설치](https://gemseo.readthedocs.io/en/stable/software/installation.html), [licenses](https://gemseo.readthedocs.io/en/stable/software/licenses.html), [public mirror](https://github.com/gemseo/gemseo). 소스/테스트 LGPL3, examples/tutorial code는 별도 BSD0, docs는 CC-BY-SA4.0. 제품 도입·배포 적합성은 아직 검토하지 않았다.
- [OpenMDAO ExternalCodeComp](https://openmdao.org/newdocs/versions/latest/features/building_blocks/components/external_code_comp.html), [case recording/retrieval](https://openmdao.org/newdocs/versions/latest/basic_user_guide/reading_recording/basic_recording_example.html), [DOEDriver](https://openmdao.org/newdocs/versions/latest/features/building_blocks/drivers/doe_driver.html).
- [Dakota capabilities](https://snl-dakota.github.io/), [evaluation restart](https://snl-dakota.github.io/docs/6.24.0/users/usingdakota/running/restart.html), [surrogate bounds](https://snl-dakota.github.io/docs/latest_release/users/usingdakota/reference/model-surrogate.html).
- [ParaView](https://www.paraview.org/), [companion tools](https://www.paraview.org/companion-tools/), [trame actual application tutorial](https://kitware.github.io/trame/guide/tutorial/application.html), [trame source/license](https://github.com/Kitware/trame). trame는 Apache2.0. 이 조사에서는 새 renderer를 설치/실행하지 않았다.
- [RCE features](https://rcenvironment.de/pages/features.html), [Windows/Linux distribution](https://rcenvironment.de/pages/download.html), [현재 rce-main source/EPL](https://github.com/rcenvironment/rce-main). 과거 rce 저장소는 historical mirror이므로 신규 통합의 기준으로 쓰지 않는다.
- [AiiDA 공식 플랫폼/provenance/plugin 설명](https://aiida.net/). 주 사용 사례가 계산 재료이므로 구조 CAE의 ready-made physics editor로 일반화하지 않는다.
- [preCICE 공식 adapter 목록과 지원 범위](https://precice.org/adapters-overview), [core source](https://github.com/precice/precice). 문서의 CHT/FSI 지원을 arbitrary contact/재료 연동으로 확대하지 않는다.

## 3. 우리 저장소에서 재개발할 필요가 없는 골격

별도 독립 읽기 조사로 public Core/HTTP/UI를 대조했다. 아래의 구현 여부는 callable/API 존재와 기록된 bounded 지원 범위이며 현재 host의 native readiness와 별개다.

| Phase | 재사용할 실제 public 경로 | 남은 연결/개발 |
|---|---|---|
| 1 | study_create, parameter_discover/register, cad_run, editable CAD·STEP·registry | 기존 모델·조건에서 새 개정 입력 불러오기, 제한된 CAD 업로드 경로 |
| 2 | analysis_run(parent_experiment_id), model_analysis_run, fixture U/BC/load viewer | 원본7부품 assembly의 실제 재료·접촉·하중 전달. import 성공은 mechanics 완료가 아님 |
| 3 | doe_plan/run, optimization_plan/run, model_optimization_plan, 후보·재개·termination 기록 | 이전 조건/계획 재사용, 후보 비교. mixed/discrete·다목적은 추가 engine 범위 |
| 4 | pde_run과 등록7종 backend, model_revision·reference·field artifacts | 결과의 원래 form/domain/time 조건을 새 해석으로 불러오기. AI PDEFields admission은 전체 backend보다 좁음 |
| 5 | model_analysis_run의 J2/SVK/Maxwell/contact 등, native histories, contact viewer | 이미 있는 contact backend의 preset 연결, 재료 이력 표시, 실제 구조 constitutive/contact coupling |
| 6 | model_analysis_run/explicit.openradioss의3개 rigid-cube 사례, native history/animation files | history·animation·조건 비교. 일반 surface/rotation/material/failure는 미구현이며 실패 wall case는 REJECTED 유지 |
| 7 | MFront inverse + model variable binding + 공통 optimization_run | 합성1stress/E 입력 범위 밖의 측정 inverse/UQ/surrogate/다목적/MOOSE/HPC/실물 연결 |

코드: [Core](../caelab/engine.py), [HTTP operation와 presets](../apps/lab/service.py), [현재 UI 실행·비교 연결](../apps/lab/static/app.js), [현재 입력 요약](../apps/lab/static/result-presentation.js), [declared model](../caelab/declared_model.py), [MCP](../openscience/mcp_server.py).

Simulation 화면에는 Phase6/7의 제한된 모델도 이미 노출된다. 이를 전혀 손대지 않은 단계로 설명하는 것도, 전체 지원으로 설명하는 것도 부정확하다. 현재 입력 요약은 주로 등록 parameters만 보여준다. 공통 조건 복제와 단위·시간/단계가 있는 결과 표시가 우선 통합 항목이다. 자료 보존과 JSON/HTML/ZIP 보고서는 이미 있다. 전체 캠페인 bundle 이전·재가져오기는 별도 gap이다.

## 4. 채택할 개발 순서

1. **연구 목적을 가진 뼈대 통합(B1):** 관찰/시험 목적 → 경쟁 가설·비교할 응답 → 연구/model/revision → 전체 조건 → public operation → job → 같은 experiment/field/history → 조건 변경·비교 → 다음 시험·저장/재열람. 현재 Core/registry/job/report를 재사용한다. 기존 study는 질문·가설·목적의 text만 저장하므로 이를 여러 가설·측정의 구조화 매핑이 이미 있는 것으로 표시하지 않는다.
2. **조건 변경과 읽기(B2):** 검증된 proposal.execution/모델 선언에서 기존 조건을 불러와 새 experiment ID로 수정한다. 같은 source study·backend·CAD parent와 explicit 가정을 보존한다. immutable 원본을 수정하지 않는다. Phase5–7의 manifested raw/history를 단위와 native 시간/단계로 읽기 쉽게 연결한다.
3. **AI 연구 연결(B3):** 이미 승인한 OpenScience 모델과 실제 지원 ResearchProfile의 tool admission을 이 흐름에 연결한다. UI/API의 존재를 AI 실행 권한으로 바꾸지 않는다. 승인된 gpt-5.6-sol/OAuth를 유지한다.
4. **Phase 순서의 세부 보완(B4):** 지그 흐름에서는 기존150N 변경/수치 탐색과 원본 조립체 mechanics를 연결한다. 불량 흐름에서는 관측의 출처·응답 위치/방향/단위·발생 조건과 모델 입력의 매핑을 먼저 닫고 지원 범위에서 가설 비교를 구성한다. 이후 Phase3–7의 미완료 범위를 연구 목적에 맞춰 확장한다. 새 solver 예제나 전체 모델의 의무 mesh sweep으로 이 흐름을 대체하지 않는다.
5. **재사용 평가(B5):** GEMSEO의 필요한 engine 기능 하나, ParaView/trame의 필요한 field 기능 하나를 기존 Core 결과에 맞춰 확인한다. PrePoMax/SALOME/FreeCAD에서 같은 native 입력/결과를 여는 inspection bridge는 existing artifacts로 먼저 확인한다. 여러 framework를 일괄 설치하지 않는다.

현재 S3-R2의 resident lifetime/원질문 observer 후보는 보존한다. 두 PS 파일의 모의 assertion349 PASS는 provider/native/HTTP 실제 호출0인 source-only evidence다. HTTP product recovery와 실제 native 취소는 아직 미검증이다. 모든 R2 예외의 종결을 B1/B2의 선행조건으로 삼지 않으며, 무감독 장시간 운영·동일 저장소의 불명확 claim은 기존 recovery fence를 계속 적용한다.

## 5. 완료 기준과 현재 근거

- B1/B2 완료: 기존 서로 다른 family의 실제 저장 실험을 같은 작업 화면에서 열고, 원래 조건/단위/결과를 확인하며 새 조건 초안을 만들고, 지원 public operation에서 새 실험·비교·재열람을 수행한다. 기존 native 결과와 수정된 UI/source 검증을 구분한다.
- backend/engine 추가: 선언된 입력과 실제 실행 지원, 의미 있는 reference/보존/거부, 같은 기록을 보는 사용자 흐름을 묶는다. 구현 공식만 복제한 tests로 실제 해석을 대체하지 않는다.
- 물성·강도·내구·실물·회사 배포 UNKNOWN/NOT_RELEASED를 유지한다. 가상 연구 소프트웨어의 사용성과 실제 사용 승인은 별도다.
- exact535 CI37325675240 최종은7SUCCESS/3FAIL. PDE vector/Aster Fz 수치 판정, explicit 설치 실패를 보존한다. 이번 자료 조사는 새 solver 검증·CI PASS가 아니다.
- 현재 source 작업 트리에는 미커밋 R2 후보가 있으며, 이 조사로 실행/합병/자격을 부여하지 않았다. 전체52/Phase1–7은 미완료다.

현재 활성 순서와 상태는 [단일 실행 계획](CAE_RESEARCH_EXECUTION_PLAN.md)에 유지한다. Astra의 [기존 상세 개선안](reviews/20261005-astra-high/IMPROVEMENT-PLAN.md)은 참고로 보존하며, 사용자 최신 skeleton-first 지시가 실행 순서에 우선한다.
