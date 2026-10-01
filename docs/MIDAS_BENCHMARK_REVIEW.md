# MIDAS 벤치마크 전체 검토와 시스템 적용

검토일: 2026-10-01. 주 담당: 로컬 Root. 조사 소스 기준:
`f2fecd9284601813b41b19ea689bec1e13d83920`, fixture pin `3e48bf6`.
이 문서는 벤치마크 자료 검토와 구현·실행 계획을 구분한다.
아래 사례의 우리 시스템 numerical acceptance는 모두 **NOT_RUN**이다.

## 범위와 출처

사용자의 지시는 MIDAS 벤치마크 전체를 검토하라는 것이다. 한 사례에
집중했던 작업 순서를 수정했다. 기존 단일 사례 소스와 증거는 보존하되
추가 구현·실행은 `DEFERRED_BY_OWNER`로 두었다. 프로젝트 전체 목표와
52개 요구사항, Phase 1~7의 순서는 계속 유효하다.

| 자료 | 실제 확인한 범위 | 출처와 한계 |
| --- | --- | --- |
| MIDAS NFX Benchmark Series | 공개 본문 2~12장, 11개 분야/139개 사례의 문제·응답·참고문헌 검토. 호스팅 페이지는 337쪽이라고 표시한다. | [원본 내용의 공개 미러](https://www.scribd.com/document/111575083/benchmarkmanual). 공급사 작성 내용이지만 현재 공식 배포판·전체 PDF bytes·모든 도면·원본 모델 묶음은 확보/검증하지 못했다. |
| MIDAS NFX-CFD Verification Manual | 공식 링크에서 받은 원본 PDF 55쪽/18개 사례. 본문·표·참고문헌과 선택한 도면 대조. | [MIDAS 공식 안내](https://gtc.midasuser.com/helpdesk/KB/View/32637163-midas-nfx-manuals-and-tutorials)의 [CFD PDF](https://www.dropbox.com/s/wlsa705ck97iuic/CFD%20Verification%20Manual.pdf?dl=1). 안내는 2020-11-04 갱신이며 최신 판본이라는 뜻은 아니다. |
| NFX Analysis Manual | 해석 이론/요소/재료 설명 자료이며 139개 벤치마크 매뉴얼과 다르다. | 위 공식 안내의 별도 링크. 전체 이론 매뉴얼 검토를 완료했다고 주장하지 않는다. |
| MIDAS MeshFree NAFEMS 보고서 | 별도 제품 자료임을 구분했다. | [MIDAS 호스팅 보고서](https://www.midasmts.com/hubfs/MTS_KO/data/NAFEM.pdf?hsLang=en). NFX 139개 또는 CFD 18개로 합산하지 않는다. |

구조 매뉴얼 Table 1.1의 **발행자 집계**는 NAFEMS 75/논문 21/책·기타 43,
총139이다. 실제 장별 직접 인용 문헌의 형식과 이 표의 일부 분류가 다르다.
문제 원출처와 직접 인용을 분류하는 기준은 확인하지 못했으므로 총계를
억지로 맞추거나 전체가 NAFEMS 문제라고 표시하지 않는다. 각 사례의 실제
reference label은 [전체 목록](../benchmarks/catalogs/midas-nfx-survey.json)에
별도로 보존한다. NAFEMS 원 문제지의 조건·수정본 확인은 실행할 사례별 gate다.
139+18은 두 자료의157개 항목 수다. 일부 열전달 family가 두 매뉴얼에
중복되므로157개의 서로 다른 물리 문제라고 주장하지 않는다.

## 전체 분야와 필요한 검증

| 장 | 분야 | 사례 수 | 우리 시스템에서 확인할 내용 |
| --- | --- | ---: | --- |
| 2 | 선형 정적 | 22 | 축력·굽힘·비틀림, 2D/축대칭/3D 응력, 얇은/두꺼운 판·쉘, 적층·열응력; 지정 성분·위치와 요소 formulation을 맞춘다. |
| 3 | 자유진동 | 23 | 고유진동수와 모드 대응, 강체 모드, 집중질량/관성, 지지 회전 DOF, 메시 왜곡. |
| 4 | 선형 좌굴 | 6 | 하중 배율·좌굴 모드와 초기 응력; 선형 임계값과 실제 비선형 붕괴를 구분한다. |
| 5 | 정상 열전달 | 6 | 열원·대류·복사·이종 재료의 온도와 열유속; 열수지와 경계 단위를 확인한다. |
| 6 | 비정상 열전달 | 5 | 초기조건, 시간별 온도/구배, 비열·밀도·대류, 공간 및 시간 수렴. |
| 7 | 선형 동역학 | 12 | 변위·속도·가속도/주파수 응답·스펙트럼, 감쇠·기저 가진·모드 절단/잔여 모드. |
| 8 | 초기 응력 | 3 | 정적 평형 후 진동, 케이블 장력과 회전의 초기 응력 효과. |
| 9 | 기하 비선형 | 22 | 큰 회전/변위, 분기·snap-through·snap-back, 전체 하중-변위 경로와 경로 제어. |
| 10 | 재료 비선형 | 19 | 소성/경화·하중과 제하·열 ratcheting·잔류응력·초탄성·수치 반복; 재료점과 구조 응답을 구분한다. |
| 11 | 접촉 | 8 | patch/압입/Hertz·미끄럼/구름·링/파이프 변형, 압력·접촉폭·침투·마찰 및 전체 경로. |
| 12 | 명시적 동역학 | 13 | 충격·응력파·쉘/복합재·회전 마찰·성형·관절, 시간 이력·질량·운동량·에너지·시간 간격. |
| 별도 CFD | 유동/열/자유표면/수송 | 18 | 공동·외부유동·후향 계단·관·노즐·회전유동·자연대류/복합 열전달·댐 붕괴·슬로싱·종 수송. |

이 목록은 자료의 분야를 우리 검증 항목으로 연결한 검토 결과다. 같은 물리를
다른 요소·형상·지지·추출 위치로 검사하는 사례를 하나로 합쳐 통과 처리하지
않는다. 공급사 결과표에도 오차와 formulation 한계가 있으므로 표에 수치가
있다는 이유로 우리 결과의 허용 오차를 넓히지 않는다.

## 전체 읽기에서 확인한 주의점

- 진동/동역학의 지지 회전 DOF, 강체 모드, 속도 응답과 변위 응답을 별도로
  확인해야 한다. 하나의 가까운 수치로 다른 출력이나 mode를 통과 처리하지 않는다.
- 기하 비선형은 최종 변위 한 점보다 분기·snap-back을 포함한 하중 경로와
  제어법이 핵심이다. 재료 비선형은 경화/제하·열 cycle·잔류응력·접선까지
  필요하며 기존 단순 J2/재료점 모델과 적용 범위가 다르다.
- 접촉에서는 원형 해석해와 polygon 메시의 기준을 구분한다. 공급사 출력이
  reference와 다른 사례도 보존하며, geometry/response를 바꿔 맞추지 않는다.
- 직접 인용 문헌의 유형/일부 보고서 ID·제목·출판 정보와 소개 집계 사이에
  차이가 있다. 매뉴얼 주장, 원출판자 확인, 미확인 원문을 따로 기록한다.
- CFD §2/5/8/12에는 도형·표·설명 사이의 정의 충돌, §14/16에는 응답을
  재현할 시간·계수·단위 정보의 gap이 있다. 선택한 PDF 도면을 대조한 항목과
  텍스트 추출만 확인한 항목을 catalog에서 구분한다. 수정값은 추측하지 않는다.

전체 목록의 case별 source note는 실행 전 definition admission 과제다.
전 항목의 모든 그림·원 문제지·native 모델을 확보했다고 주장하지 않는다.

## 이미 연결된 기능과 추가 개발의 경계

`git show f2fecd9:caelab/engine.py`의 등록 상태와 기존 acceptance 기록을
확인했다. 작업 중인 단일 사례 초안을 완료된 capability에 포함하지 않는다.

| 영역 | 기존에 재사용할 구현/증거 | MIDAS 전체 범위에 대해 남은 것 |
| --- | --- | --- |
| CAD/메시/선형 구조 | pinned fixture discovery/native CAD, exact-STEP Gmsh/CalculiX, Code_Aster affine elasticity, 공통 model-analysis | 임의의 구조 benchmark 형상·BC·하중·응답을 받는 domain profile; 판/쉘·축대칭·적층·modal·buckling·prestress는 현재 전체 검증 완료가 아니다. |
| 탐색 | 공통 registry와 SciPy LHS/DE, 유효하지 않은 CAD 차단, candidate journal/replay | 각 응답의 유효성/단위/제약 정의, 수렴·활성 제약·변경 조건 검증. 매뉴얼이 optimizer 통과 근거를 대신하지 않는다. |
| PDE/열 | FEniCSx의 제한된 scalar linear/nonlinear weak form, 해석해/잔차/오차 및 reference rejection | 새 형상·경계·시간/벡터/열복사·공액 모델; 현재 fluid solver adapter는 없다. |
| 재료/비선형 | Code_Aster small-strain J2 하중·제하, MFront 재료점/접선, 합성 inverse | 대변형·kinematic hardening·ratcheting·초탄성·접촉·solver constitutive coupling. 기존 소규모 증거를 모든 재료 모델에 일반화하지 않는다. |
| 충격/명시적 | OpenRadioss flight/compliant-stop의 제한된 native 이력, 기존 벽 접촉 rejection | 일반 표면/회전 접촉·성형·재료 파손·관절·전처리 및 변환, 동기화된 native field/animation. |
| 연구/사람의 확인 | 실제 OpenScience 5.6 Sol의 P1.3 CAD/CalculiX/SciPy/scalar PDE 연구 loop와 동일 Core 결과 | 새 capability를 공식 연구 프로필에 명시적으로 연결하고 실제 호출·변경조건·비교·해석·공통 report/GUI까지 검증. Core method가 존재하는 것만으로 AI 연결 완료가 아니다. |

Code_Aster/CalculiX, FEniCSx, MFront, OpenRadioss는 위의 기존 증거 범위에서
재사용한다. CFD용 OpenFOAM 등은 **후보**이며 새 adapter/실행 증거가 없다.
solver 문서가 기능을 설명하는 것과 우리 시스템의 설치·연결·검증은 구분한다.
기존 backend 검토는 [BACKEND_EVALUATION](BACKEND_EVALUATION.md), 실제 증거는
각 acceptance 문서와 [CURRENT_STATE](../CURRENT_STATE.md)를 따른다.

## 실행 순서에 반영할 작업

기존 [단계별 계획](SYSTEM_EXECUTION_PLAN.md)과
[구체적 작업 목록](SYSTEM_WORKLIST.md)을 유지한다. 이번 조사 때문에 뒤 단계를
동시에 개발하지 않는다. 아래 family는 사례 선택의 근거이며, 아직 실행 가능한
완전한 specification/허용 오차를 갖췄다는 뜻은 아니다.

1. **현재 P2 조사 gate:** 139+18개를 빠짐없이 목록화하고 문제·응답·출처·정의
   gap을 검토한다. 전체 자료를 읽는 지시를 특정 사례 구현으로 바꾸지 않는다.
2. **P2 구조 실행:** 먼저 beam의 축력/굽힘/비틀림(§2.3), 압력 cylinder의
   응력/차원 모델(§2.12), 판/쉘 두께·요소 family(§2.15 등)에서 기존 코드의
   gap과 완전한 정의를 비교한다. 입력·지지·측정 위치·단위·reference·mesh/error
   gates를 동결한 작은 단위부터 adapter→Core→OpenScience→공통 사람의 결과
   확인까지 수행한다. modal/buckling/prestress는 별도 capability gate로 남긴다.
3. **P3 탐색:** 앞 단계의 유효한 변위/응력/온도 등 응답을 목적/제약으로 연결해
   deterministic engine이 조건을 바꾸고 실패/replay/stop reason을 보존한다.
   기존 optimizer를 새로 만들지 않는다.
4. **P4 PDE:** §§5~6와 CFD §14/17/18을 공간·시간·경계/이종 매질 참고군으로
   사용한다. 해석해·열수지·시간 수렴을 추가하고 vector/coupled 확장은 별도 gate다.
5. **P5 비선형:** §§9~11의 경로 제어, cyclic material, 초탄성, 접촉을 그 순서의
   bounded units로 검증한다. 기존 J2/MFront와 보존된 제안을 재사용하며, 이후
   fixture fastener/contact의 P2 의존성을 닫는다.
6. **P6 명시적:** §12의 응력파/충격부터 일반 접촉·회전·재료/파손과 전체 history를
   검증한다. 기존 reduced stop 성공과 벽 접촉 실패를 유지한다.
7. **P7 확장:** constitutive solver coupling/관측 inverse, 수치 UQ/MDO,
   CFD와 열-유동 coupling/MOOSE, 실제 HPC와 실험 장비를 기존 순서로 연결한다.
   CFD 18개를 Phase6의 explicit structural acceptance로 잘못 분류하지 않는다.

대표 사례 PASS는 목록의 나머지 사례 PASS가 아니다. 전체 실행 수와 family별
coverage를 별도로 유지한다. 자료 검토나 이 계획만으로 Phase2 또는 전체52개를
완료 처리하지 않는다.

## 재현과 기록 규칙

선택한 문제마다 geometry/units/material/IC/BC/load/time/mesh/element/output
location/component/reference/thresholds/source revision을 predeclare한다.
그림·표·수식이 충돌하거나 수치가 누락되면 원본/수정본을 조사하고 해소할 때까지
`UNKNOWN`으로 둔다. 평균·extrapolation·nodal/Gauss stress·모드 번호·곡선 시간
범위를 바꿔 reference에 맞추지 않는다. 원래 published output과 우리 native
output을 별도 artifact로 둔다.

모든 실행은 새 store/experiment ID를 사용한다. Core가 immutable proposal,
revision, metrics의 validity, evidence/validation, raw field/deck/log/hash를
관리한다. Domain plugin은 물리와 reference, adapter는 native syntax를 소유한다.
OpenScience는 질문·가설·campaign 선택/해석을 하고 numerical engine이 후보를
생성한다. 사람과 AI는 같은 결과/원본을 확인한다. 물성·하중·강도·실물·내구의
미검증은 `UNKNOWN`, engineering decision은 `NOT_RELEASED`를 유지한다.

조사 run: `p2-midas-survey-20261001-01`. CFD 원본: 609258bytes,
SHA256 `bb91f063ece5746978eb9a8fe69ba36b186bc6933b7263dfe5b4ce6a5284af9c`.
직접 structural HTTP 응답은 200이지만 browser challenge(3038bytes)였고
매뉴얼로 취급하지 않았다. 공개 웹 본문으로 검토했다. 원본 PDF/로컬 분석/보존한
초안 bytes는 ignored artifacts에 있으며 Git clone에 포함되지 않는다.
공개 저장소에는 사실 목록·짧은 검토·출처/hash만 반영한다.

조사 기록: [20261001-midas-full-survey.json](../benchmarks/records/20261001-midas-full-survey.json).
기존 실제 solver/research proof는 `04ff148`/`p1-research-20261001-03`이다.
이번 조사 및 문서 commit은 새로운 solver 검증이나 RELEASED가 아니다.
