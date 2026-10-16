# 코드 구조와 단계별 정리안

2026-10-16. **Codex가 실제 코드 분석을 바탕으로 작성한 검토용 구조 초안**이다.
Codex 작성이며 Pro 원안으로 표시하지 않는다. 2026-10-16 최신 사용자 지시로 아래 재개 작업의
리팩토링을 수행한다. 전체 폴더 트리 채택·모든 기능 구현 완료를 뜻하지 않는다.
독립 구조 진단에 따라 전체 폴더 이동과 모든 창의 MVP 전환을 필수 과제로 삼지 않는다.
아래 트리는 위치 후보이며, 실제로 확인한 책임 경계부터 선택해 이관한다.
최신 독립 검토의 판단과 첫 수정 단위 제안은 [구조 진단 보고서](../_workspace/code-state-audit-20261016/architecture/REVIEW_KO.md)에 있다.
이 문서의 전체 트리나 이관 예시는 현재 배정이나 필수 선행 작업이 아니다.
사용자 후속 지시에 따라 **기존 전처리 기능과 겹치는 자체 설정 UI·변환을 줄이는 작업**도
이번 수정안에 포함한다. 기존 FreeCAD Tasks·native writer를 우선 사용하고,
연구 앱/MCP 연결 또는 native에 없는 요구 기능에 필요한 코드만 남기는 기준으로 검토한다.
구체 변경 범위는 다음 재개 작업에 한정한다. 현재 담당·상태는 CURRENT_STATE 한 곳에서 관리한다.

## 재개 작업의 변경 계약

1. **native Pre 재사용:** 기존 FreeCAD 트리·Tasks를 재료와 기본 하중/구속 편집의 주 경로로
   사용한다. `apps/desktop_pre/fem_panel.py`의 중복 폼을 native 편집 진입으로 전환한다.
   기존 `pre.fem.task_edit`, native 객체와 broker를 사용하고 새 편집 상태 계층을 만들지 않는다.
   동등하지 않은 Lab 전용 재료·조건은 없애지 않고 구분한다. 현재 native 객체의 변경을
   기존 실행 경로가 올바르게 읽는지 확인하며, 필요한 보완은 호출자·CAE 자문과 먼저 합의한다.
2. **Expert 자료 팩 배포:** `expert_library_pack.py`가 `examples`에 기대는 import를 없앤다.
   `load_pack`과 실제 제공 자료·라이선스 고지는 제품 패키지에 포함하고 예제 CLI는 그 코드를
   사용한다. 원문 내용·라이선스·출처·무결성 검사와 기존 API/예제 사용법은 유지한다.
3. **VTU writer 경계:** `apps/desktop_post/prepare.py`의 순수 `data_array/write_vtu`를
   adapter 소유 모듈로 추출하고 기존 앱 경로는 호환 재노출한다. 직접 호출자를 함께 수정한다.
   원본 절점 순서·단위·association·NaN/Inf·출력 포맷을 바꾸지 않는다. FreeCAD/PV/solver
   실행이나 성능 캠페인은 이 추출의 선행조건이 아니다.
4. **기존 전처리 도구 연결:** native 프로그램 검색·선택·실행기를 먼저 재사용한다.
   Code_Aster의 SALOME-MECA/AsterStudy와 OpenCourant의 기존 입력 작성 도구를 각각
   구분한다. 무료 사용·실제 입력 호환·실행 경로가 확인되지 않은 도구를 설치하거나 지원 완료로
   표시하지 않는다. 조사 결과로 수정 파일·호출·사용자 동작을 확정한 뒤 해당 코드만 바꾼다.

각 범위는 한 writer가 수정하고 공통 파일은 root가 통합한다. native Pre GUI 담당과 CAE
자문은 실제 객체·입력 의미를 직접 논의한다. 계획 검토 후 의미 있는 묶음에 독립 통합 검토를
수행하며, 작은 변경마다 전체 검사를 반복하지 않는다. 기존 사용자 변경은 커밋에 섞지 않는다.

현재 판정과 결함은 [전체 분석 보고서](../_workspace/code-state-audit-20261016/full/REPORT_KO.md),
실제 파일·함수는 [코드 탐색기](../_workspace/code-state-audit-20261016/full/CODE_EXPLORER.html),
제품 지원 범위와 종료 조건은 [기존 개발 목록](DEVELOPMENT_ITEMS.md)을 따른다.
이 정리안의 묶음을 새로운 제품 기능 개수로 더하지 않는다.

## 이번에 적용한 코드 경계

| 책임 | 실제 코드와 보존한 진입 |
|---|---|
| FreeCAD 기본 재료·조건 편집 | `fem_panel.py`와 `material_panel.py`는 기존 `pre.fem.task_edit`를 호출한다. 탄성 물성과 기존 고정·힘 값의 중복 폼을 없애고 native 객체를 편집한다. 지정 변위·소성 곡선 등 동등하지 않은 범위는 유지한다. |
| 변경한 적용 대상의 연결 | `fem_edit.py`의 기존 `condition_repair`에 명시 확인 분기를 추가했다. 현재 문서의 정확한 native 대상만 기록하며 힘·방향·진폭 값을 다시 쓰지 않는다. 형상이 바뀌면 별도 면·방향 복구를 요구한다. |
| 배포하는 참고 자료 | `caelab/research_knowledge_pack.py`와 `caelab/research_knowledge/`가 loader·원문·배포 고지를 소유한다. GUI는 제품을 import하고 예제 CLI는 같은 API를 재노출한다. |
| 순수 결과 직렬화 | `caelab/adapters/vtu.py`가 기존 두 함수를 소유한다. 여섯 library 호출부는 이 모듈을 쓰고 `apps/desktop_post/prepare.py`는 이전 이름을 그대로 제공한다. |

Astra의 독립 검토에서 찾은 방향 복구 누락과 숨겨진 과거 선택의 재전송은 수정했다.
자료 배포·출력 호환과 Qt 대역 검사는 수행했으나 실제 FreeCAD Task의 수락·취소·변경값
입력 생성·저장 재열기는 미완료다. 현재 확인 범위와 다음 행동은 CURRENT_STATE를 따른다.
SALOME-MECA/AsterStudy나 OpenCourant용 외부 전처리기는 이번에 연결한 기능이 아니다.
기존 실행파일 검색·선택 코드를 재사용할 수 있지만 환경과 입력 전달을 별도로 연결해야 한다.

후속 정리에서는 남아 있던 기록 취득과 고차면 Post를 현재 owner·JobManager·자료 구조로
통합했다. 취득의 저장 상태·원문 보존·문서 전환과 Post 이력 비교를 고쳤으며 별도 실행 기반을
추가하지 않았다. 미완성 3D/FELUPE 온도 확장은 제품 경로에서 제거했다. 기본 온도는 기존
native 도구를 사용하고 독립 재료 연구 및 일반 절점 온도장 수신 요구는 미완료로 남긴다.

## 실제 문제와 설계 목적

`apps/research`에는 창·대화상자·요청/복구 처리 등이 평평하게 놓여 있고,
`caelab` 최상위에는 도구별 문서와 업무 처리, 공통 저장·실행 코드가 함께 있다.
`Workbench._execute`는 약 345줄 안에서 분야별 검증·준비·실행을 분기한다.
이 분기 중 상당수는 유효한 실행 조정이므로 크기만으로 잘못된 구조로 판정하지 않는다.
실제 재검토 대상은 여러 실행 경로에 흩어진 native 결과 발행 불변식, 공통 owner 안의
Data/Expert 업무 분기, Study가 Numerical 기능까지 상속하는 관계와 일부 복잡한 GUI 작업이다.

backend registry/lazy factory, Adapter Protocol, 준비된 평가, Template Method 형태의
문서 owner와 JobManager는 실제 존재하는 재사용 구조다. ‘설계 패턴이 거의 없다’는
설명은 부정확하다. 이 구조를 유지하면서 역의존·정책 누출·중복된 불변식을 줄인다.

목적은 기능별 코드를 찾기 쉽게 모으고, 화면·업무 규칙·문서 수명·native 입출력의
수정 책임을 나누는 것이다. 공통 문서 기능을 Material 클래스의 상속에만 의존하는
구조도 줄인다. 기존 reader, 계산 엔진, JobManager와 native 프로그램을 재사용한다.

선택은 **기능별 폴더 + 실제로 공유하는 기반**이다. 모든 도구를 하나의 거대한
`controllers/services/models` 묶음으로 나누면 한 사용자 작업의 코드가 다시 흩어진다.
전면 재작성은 현재 reader·계산·native 연결과 저장 호환을 모두 다시 확인하게 된다.
기능별 이관은 기존 실행 가능한 경로를 유지하면서 해당 기능의 변경을 묶을 수 있다.
이는 기존 Core/Domain/Adapter의 논리 책임을 실제 소스 배치로 구체화하는 안이다.

## 장기 배치 후보

아래는 기능별 배치를 검토하기 위한 후보다. 현재 폴더나 이번에 전부 적용할 계획이 아니다.
빈 폴더를 먼저 만들지 않고, 이후 실제 이관을 선택한 범위에서만 코드와 함께 결정한다.

```text
autonomous-cae-lab/
├─ apps/
│  ├─ desktop_pre/             FreeCAD 프로세스의 UI·선택·명령 연결
│  ├─ desktop_post/            ParaView 프로세스의 UI·pipeline·선택
│  ├─ research/
│  │  ├─ desktop.py            기존 독립 앱 진입점
│  │  ├─ common/               Research 공통 메뉴·테마·요청/복구 UI
│  │  ├─ data/                 Data 창·표·그래프·취득 UI
│  │  ├─ material/             Material 창·피팅 UI
│  │  ├─ numerical/            Numerical 창·후보 상세·채택 UI
│  │  ├─ pde/                 PDE 트리·설정·결과 UI
│  │  ├─ simulation/          해석 입력·실행·결과 UI
│  │  ├─ post/                native Post의 Research 설정 보조 UI
│  │  ├─ runner/              작업·로그·취소 UI
│  │  ├─ expert/              토론·자료·연구팀 UI
│  │  ├─ evaluation/          연계 계산·전달 UI
│  │  ├─ study/               연구 계획·비교 UI
│  │  ├─ report/              보고서 편집 UI
│  │  └─ connection/          선택적 Workbench 연결 보기
│  └─ lab/                    기존 HTTP 전송·인증·경로 연결
├─ caelab/
│  ├─ workbench.py            기존 공개 진입 유지, 서비스 조립·연결
│  ├─ core/
│  │  ├─ documents/           명령·편집 이력·저장·결과 보존
│  │  ├─ execution/           기존 JobManager·취소·프로세스 소유
│  │  ├─ storage/             기존 파일·잠금·원자적 저장·보존본 I/O
│  │  ├─ registry/            공통 참조·등록·등록 복구
│  │  └─ artifacts/           공통 아티팩트 등록·검사·해소
│  ├─ tools/
│  │  ├─ execution.py         여러 도구의 연구 실행 조정, 도구별 검증 사용
│  │  ├─ references.py        도구 간 저장 참조 해소·메타데이터 조정
│  │  ├─ pre/                 CAD/FE 공통 서비스와 native 문서 연결
│  │  ├─ post/                결과 문서·측정·비교·도구 간 전달
│  │  ├─ data/                Data 문서·처리·교정·취득
│  │  ├─ material/            Material 문서·계수·시험/피팅 업무
│  │  ├─ numerical/           Numerical 문서·계획·후보·채택
│  │  ├─ pde/                 PDE 문서와 실행 업무
│  │  ├─ simulation/          Simulation 문서와 실행 업무
│  │  ├─ runner/              로컬·원격 실행 대상과 회수 업무
│  │  ├─ expert/              토론 문서·허가·자료 연결 업무
│  │  ├─ evaluation/          연계 계산 정의·전달 업무
│  │  ├─ study/               연구 문서·비교·판단 업무
│  │  └─ report/              보고서 문서·출처 연결 업무
│  ├─ adapters/               기존 solver/format/native adapter
│  ├─ assist/                 기존 검색·Co-STORM·모델 연결 구현
│  └─ optimizers/             기존 수치 탐색 엔진
├─ plugins/                   기존 물리·공학 규칙과 pinned upstream
├─ openscience/               기존 MCP 진입·도구 인자 연결
├─ schemas/                   기존 공개 계약
├─ tests/
│  ├─ core/                   문서·저장·실행의 공통 계약
│  ├─ tools/                  각 도구의 업무·문서 규칙
│  ├─ adapters/               native 입력·reader·runtime 경계
│  ├─ gui/                    Presenter·Qt 조작과 창 수명
│  └─ workflows/              도구 사이 실제 작업과 저장/재열기
├─ examples/                  사용자 실행 예제·예제 자료
├─ scripts/                   설치·시작·빌드·운영 도구
└─ docs/                      제품·설계·사용법
```

각 Research 기능 폴더는 실제 필요한 화면과 대화상자를 가진다. `presenter.py`는
도메인 규칙이나 다단계 요청 수명을 분리할 근거가 있는 작업에만 도입한다.
작은 대화상자·delegate·plot 조작에 일률적으로 새 Model/Presenter를 생성하지 않는다.
각 `caelab/tools/<기능>`은 해당 `document.py`와 필요한 업무 서비스를 가진다.
예를 들어 Numerical의 `adoption.py`는 제약·원본·채택 조건을 검사하고,
GUI는 후보를 선택하고 명시적으로 채택을 요청한다. 없는 역할을 채우려고 빈
`models/repositories/factories` 묶음을 모든 기능에 복제하지 않는다.

FreeCAD·ParaView·Research의 서로 다른 Python/Qt 환경은 유지한다.
이 트리 때문에 native 앱을 Research 프로세스에 임베딩하지 않는다.

## 의존 방향과 책임

```text
Research 화면 → Presenter → 기존 Client/HTTP → 기능 서비스
CLI·MCP ─────────────────────────────────────→ 같은 기능 서비스
                                                 │
                  ┌──────────────────────────────┼──────────────────┐
                  ▼                              ▼                  ▼
              공통 문서·실행                 Domain plugin       Adapter
                  │                                                 │
                  ▼                                                 ▼
             공통 저장·참조                               FreeCAD/solver/ParaView
```

- `apps/research/<기능>`은 QWidget 배치·선택·입력 buffer·사용자 메시지를 맡는다.
  저장 완료/결과 채택의 공학·문서 규칙은 기능 서비스에서 검사한다.
- Presenter는 화면 사건을 명령으로 연결하고 요청·선택·화면 수명 상태를 관리한다.
  직접 JSON 파일을 쓰거나 solver를 실행하지 않는다. 기존 Post/Report의 같은 요청
  재확인 패턴을 공통 Research 요청 처리로 추출해 재사용한다.
- `tools`는 사용자 작업 순서와 도구별 문서를 맡는다. 서로의 내부 파일을 수정하지
  않고 공통 문서 명령과 정확한 저장 참조를 사용한다. Data는 Material을 가변 소유자로
  삼지 않는다. 계수 채택은 원 Material 문서의 검사를 통과한 한 번의 변경이다.
- `core`는 Qt, `apps`, 도구별 물리 규칙을 import하지 않는다. 분야별 callback으로
  유효성·원본 수집·내용 지문을 받아 공통 편집/저장 동작을 수행한다.
  `tools`, `workbench`와 과거 façade로 돌아가는 역의존도 금지한다. 모든 owner를 담은
  범용 Context를 새로 만들어 기존 Workbench 결합을 이름만 바꾸지 않는다.
- Domain plugin은 공학 규칙을, Adapter는 native 구문·경로·실행·결과 의미를 맡는다.
  기존 `assist`와 `optimizers`의 실제 엔진을 새 tools 폴더에 복제하지 않는다.
- `Workbench`와 앱 시작 코드는 실제 서비스를 조립한다. `_execute`의 작업별 본문은
  기능 서비스로 옮기고 명령 이름→기존 handler 연결을 사용한다. handler에 전체
  Workbench를 다시 넘기지 않고 필요한 문서 접근·작업·입력 해소 기능만 전달한다.
- 기존 인증·권한·명령 재확인·세대 검사·실행 허가는 공통 경계에서 유지한다.
  CLI/MCP도 같은 검사를 거치며 GUI의 버튼 활성 여부를 실행 권한으로 사용하지 않는다.
  서비스를 직접 부르는 새 경로가 기존 검사를 우회하지 않게 한다.
- native host 안에서 실행할 worker의 FreeCAD/ParaView import는 허용한다.
  공통 라이브러리에서 native UI 모듈을 가져와 규칙을 재사용하던 경로는 순수
  검증/파일 처리와 host UI로 분리한다. 외부 프로세스 호출 경계는 유지한다.
- native broker는 하나로 유지한다. host/token/command/receipt의 소유자는 공통 broker이며
  Pre/Post별로 복제하지 않는다. 분야별 명령 선언·검증만 해당 기능에서 제공한다.
  아티팩트 공통화는 containment·hash·copy·receipt에 한정하고 mesh/manifest/native 의미의
  해석은 해당 tool/adapter에 남긴다.

## 실제 코드의 이동·분리 대상

경로는 현재 실제 파일 기준이다. 화살표 오른쪽은 신규 목표이며 아직 존재하지 않는다.
다음 표는 우선 경계의 지도이며 전체 파일을 무검토 자동 이동할 목록은 아니다.

| 현재 파일 | 목표 책임·위치 | 이동하며 함께 확인할 것 |
|---|---|---|
| `caelab/workbench.py` | 진입·조립은 유지, 작업 본문은 `tools/*/service.py` | 공개 명령·권한·자원 예약·기존 주입 경로 동일 |
| `caelab/material_document.py` | `tools/material/document.py`와 `core/documents/`의 실제 공통 동작 | 편집·Undo·명령 재확인·저장 순서와 실패 보존 |
| `caelab/data_document.py` | `tools/data/document.py` | Material 전용 상속과 공통 동작 분리, 취득 변경 표시 |
| `caelab/numerical_document.py` | `tools/numerical/document.py`, `adoption.py` | 후보 제약·원본 개정·확인된 결과의 채택 경계 |
| `caelab/pde_document.py`, `caelab/pde.py` | `tools/pde/document.py`, `service.py` | 원 worker 결과·필드 보존과 기존 Post publisher 사용 |
| `caelab/simulation_document.py` | `tools/simulation/document.py` | adapter별 원 입력·결과·runtime 전달 |
| `caelab/research_execution.py` | 아래 함수별 책임표에 따라 공용 실행·Post 발행 분리 | PDE/Material/Simulation의 같은 실행 보존 경계 |
| `caelab/evaluation_definition.py`, `caelab/research_workflows.py` | 정의는 `tools/evaluation/`, 혼합 파일은 아래 함수별 분리 | 결합 단계·전달·취소, 물리 규칙은 Domain에 유지 |
| `caelab/study_document.py`, `caelab/report_document.py` | `tools/study/`, `tools/report/` | 원 참조·저장·응답 유실·편집 보존 |
| `caelab/data_material_service.py` | 공유 경로는 작은 조립 façade, 업무는 각 `tools`로 | Data→Material→Numerical의 기존 문서와 명령 동일 |
| `caelab/jobs.py`, `caelab/execution_control.py`, `caelab/windows_job.py` | `core/execution/` | 기존 실행기 재사용, Windows 자식 프로세스 종료 |
| `caelab/storage.py`, `caelab/portable_project_io.py` | `core/storage/` | 원자 저장·기존 파일 배치·portable 읽기 동일 |
| `caelab/engine.py`, `caelab/condition_parameters.py` | 공통 등록 부분만 `core/registry/` | 현재 등록/이력의 같은 복구 transaction 사용 |
| `caelab/native_inputs.py` | 중립적인 파일 보존·해소만 `core/artifacts/`; native 형식·의미 해석은 tool/adapter | manifest·mesh 의미를 공통 Core로 끌어올리지 않음 |
| `caelab/native_commands.py` | 단일 broker는 `core/documents/native_broker.py`, 명령 선언·분야 검증은 `tools/pre`·`tools/post` | host/token/receipt·thread·ID는 한 소유자 유지 |
| `apps/research/material_window.py` | `research/material/window.py`, `presenter.py` | 독립 진입·메뉴·차트·닫기·기존 명령 연결 |
| `apps/research/numerical_window.py` | `research/numerical/window.py`, `presenter.py`, 관련 대화상자 | 후보 상세·원본 선택·응답 유실·계수 채택 |
| `apps/research/data_window.py`, `apps/research/acquisition_panel.py` | `research/data/` | 표·열·단위·구간·취득과 부분 Data 연결 |
| `apps/research/pde_window.py`, `apps/research/simulation_window.py` | `research/pde/`, `research/simulation/` | 트리 선택과 설정·동일 문서의 결과 |
| `apps/research/post_window.py` | `research/post/`에 해당하는 Post 보조 UI 묶음 | native ParaView 주 화면과 기존 설정창 유지 |
| `apps/research/appearance.py`, `apps/research/readable_text.py` | `research/common/` | 직접 진입의 폰트·focus·안전한 원문 표시 |
| `openscience/workbench_mcp.py` | 외부 경로 유지, 실제 서비스와 같은 인자 계약 사용 | 원문 개정/위치, workspace 권한, 동일 명령 |

Post 보조 UI용 `research/post/`는 Research 설정창을 묶는 위치다.

여러 도구가 섞인 파일은 통째로 한 기능으로 옮기지 않는다.

| 현재 함수 | 목표 책임 |
|---|---|
| `research_execution.run_domain` | `tools/execution.py`의 공용 조정. PDE/Material/Simulation 검증·지원 범위는 각 tool에서 공급. Core에는 중립 실행·보존만 추출 |
| `research_execution.publish_fields` | `tools/post/publication.py`의 원 필드 발행. 공통 파일 보존은 Core, adapter의 물리 의미는 유지 |
| `research_workflows.execute_definition`, `evaluation_progress`, `evaluation_stage_result` | `tools/evaluation/`의 실행·진행·단계 읽기 |
| `research_workflows.numerical_evaluation_result`, `_candidate_reference_view` | `tools/numerical/`의 후보 결과·참조 표시 |
| `research_workflows.result_folder`, `resolve_reference`, `reference_metadata` | `tools/references.py`의 다도구 참조 조정. 중립적인 경로 검사는 Core에 위임 |

## 사용할 구조와 상태 규칙

1. **선택적 MVP:** Numerical의 처리 결과→trial 구성, Post 측정→Data/Plan 인계,
   Expert 단계 전달처럼 규칙·요청 수명이 복잡한 작업부터 분리한다. 단순 View와 native
   host UI는 필요한 처리를 유지하며, 모든 창을 일괄 전환하지 않는다.
2. **Command:** 기존 명령 이름·세션·세대·요청 ID를 유지한다. 새 명령 규격이나 별도 버스를
   추가하지 않고 큰 분기 본문을 해당 기능 handler로 옮긴다.
3. **Adapter/Strategy:** 기존 solver adapter와 수치 엔진을 끝까지 사용한다.
4. **기존 Template Method와 필요한 Composition:** 현재 owner hook을 먼저 활용해
   구체 Data/Expert 업무를 공통 owner에서 위임한다. 상속을 모두 새 객체 조합으로
   교체하지 않고 실제로 분리가 필요한 정책만 추출한다.

편집 상태, 계산 상태, 결과 보존 상태를 분리한다. 예를 들어 ‘입력이 저장됨 + 계산 중’과
‘입력은 그대로 + 새 계산 완료 결과는 아직 미저장’은 다른 상태다. 완료 후 저장 필요
표시는 바뀌고, 새 저장은 새 보존본을 만든다. 과거 저장본을 나중 결과로 덮어쓰지 않는다.
실패·취소·원 입력·UNKNOWN과 수치 허용치는 그대로 보존한다.

## 선택한 파일을 옮길 때의 절차와 종료 조건

아래 순서는 Data/Material/Numerical 이관을 선택한 경우의 예시다. 실제 첫 수정 단위는
독립 검토 보고서에서 별도로 권고했으며, 전체 도구를 이 순서대로 옮기는 과제를 배정하지 않았다.

1. 현재 제품 소스와 미통합 후보의 기준을 보존하고 기존 공개 진입·명령·저장 자료를
   이관 기준으로 정한다. 알려진 실패를 숨기거나 전체 suite 통과를 거짓 선행조건으로 삼지 않는다.
2. 첫 Data/Material/Numerical 흐름에 필요한 공통 부분부터 추출한다. 같은 owner 인스턴스,
   lock·session·generation·command receipt·저장 형식을 유지한다. 공통 기반 전체 교체를
   기능 이관의 선행조건으로 만들지 않는다. 기존 모듈은 필요한 기간 얇은 재노출 경로로
   유지해 imports, `python -m`, pickle 대상, worker argv, 설치 스크립트를 함께 옮긴다.
3. Data/Material/Numerical 한 사용자 흐름을 새 구조로 연결한다. 읽기→편집→계산→결과
   선택→채택→저장→새 프로세스 재열기와 실패/취소/응답 유실을 해당 변경 범위에서 닫는다.
4. 같은 경계를 이용해 PDE/Simulation/Post, Expert/Study/Report를 독립 소유로 이관한다.
   공통 파일은 한 담당이 쓰고 기능 폴더별 작업은 그 인터페이스에 맞춰 병렬 분리한다.
5. 모든 호출자와 배포·문서가 새 경로를 쓰면 불필요한 호환 파일을 제거한다.
   소스 위치를 실제 기록으로 사용하는 native worker와 pinned upstream 경로는 검토 없이 옮기지 않는다.

각 묶음은 적용한 코드·호출자·공개 진입·관련 기존 저장본·오류 복구를 함께 확인하면 끝난다.
폴더 이동과 lifecycle 동작 교정은 변경 이유를 추적할 수 있는 단위로 구분한다.
폴더 개수나 클래스 개수를 완료 기준으로 사용하지 않는다. 위치 의존 코드
(`__file__`, 상대 자산 경로, 동적 import, subprocess의 모듈명, 패키징 데이터)를 빠뜨리지 않는다.
native 앱은 해당 확인이 끝날 때 소유 프로세스만 정리한다.

기존 제품 기능 71개의 미완료 요구는 원 목록에 남는다. 구조 정리가 user-model hard
contact 등 미구현 기능을 자동으로 완성하지는 않는다. 이 문서에서 프로그램 재작성,
물리 범위 축소, 새 공개 schema, 유료 의존성 또는 제품 개발 재개를 승인하지 않는다.

검사 파일도 해당 기능 이관과 함께 정리하며, 기존 support 모듈·fixture·명령의 import를
같이 바꾼다. native 검사의 실제 환경 조건과 과거 실패 기록을 빠른 단위 검사로
대체하거나, 매 수정마다 모든 native 검사를 먼저 실행하도록 바꾸지 않는다.

이 초안은 Astra 독립 검토의 broker 단일 소유, 혼합 파일의 함수별 분리, 첫 작업 흐름부터
공통 부분 추출이라는 세 수정안을 반영했다. 이는 문서 검토이며 실행·이관 검증은 아니다.
