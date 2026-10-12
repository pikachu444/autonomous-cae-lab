# Autonomous CAE Lab — 전체 데스크톱 상세 설계 D1

요청 ID **PRO-DESKTOP-DESIGN-20261012-01** · 2026-10-12 · **연결된 whole-product draft / 별도 planning prototype**.

이 폴더는 실제 전달된 최신 요구를 기준으로 작성한 편집 원본이다. 본구현, 사용자 업무 수용 또는 공학적 출시 승인 기록이 아니다. 사용자가 화면과 시제품을 검토한 뒤 개발 시작을 지시하면 Codex가 아래 backlog를 실제 저장소에 통합한다.

## 먼저 볼 것

1. `screens/MAT-FIT-PARTIAL.svg`, `screens/PRE-CONTACT-REBIND.svg`, `screens/POST-COMPARE.svg`, `screens/STUDY-DECISION.svg`, `screens/EVAL-NONCONVERGED.svg`를 실제 1440×900 크기로 연다. 같은 이름의 PNG와 `screens/contact-sheet-*.png`는 열람용이다.
2. `PROTOTYPE_SCENARIOS.md`의 SC-01 Material 전체 흐름, SC-02 접촉·형상변경 복구, SC-03 비교·파일 복구부터 따라간다. 모든 시나리오는 `screens/screens.json`의 정확한 버튼·화면 ID와 연결된다.
3. `FUNCTION_SPEC.md`에서 사용자 결과별 시작·판단·조작·단위·오류·저장·재열기를 읽고 `IMPLEMENTATION_BACKLOG.csv`에서 기존 코드와 추가 작업을 대조한다.
4. `DECISIONS.md`, `QA_REPORT.md`, `reviews/ASTRA_DRAFT_REVIEW.md`에서 선택 이유와 실제 확인 범위·남은 제한을 확인한다.

## 산출물 안내

| 파일 / 폴더 | 용도 / 편집 원본 |
|---|---|
| `FUNCTION_SPEC.md` | 35개 사용자 결과의 상세 명세와 Material·접촉·저장·연성·비교 계약 C01–C09 |
| `IMPLEMENTATION_BACKLOG.csv` | 74개 구현 작업. 현재 source/status와 미착수 구현을 분리하고 task DAG·실행 환경 선행을 별도 열로 기록 |
| `function_catalog.json` | 기능·요구·UC·기존 T·화면·변경·수용 조건의 편집 가능한 명세 데이터 |
| `SCREEN_SPEC.md` | 전체 state inventory, 구체 입력·단위·기본값·range·핫스팟·keyboard·owner·상태별 다음 행동 |
| `screens/*.svg` | 1440×900 텍스트/도형/표/곡선/선택/3D illustration의 편집 원본 |
| `screens/*.png`, `screens/contact-sheet-*.png` | SVG와 같은 레이어·값에서 만든 열람용 이미지. 제품 실행 캡처가 아님 |
| `screens/screens.json` | state IDs, layers, hotspot bounds/targets, owner·function 연결, 시나리오. Penpot 연결을 위한 기획 데이터이며 제품 schema가 아님 |
| `DESKTOP_WORKFLOWS.drawio`, `flows.json` | 9개 페이지의 전체 작업·정보 구조·owner 전달·상태/오류/복구. 편집 가능한 비압축 mxGraph XML |
| `PROTOTYPE_SCENARIOS.md` | 클릭 가능한 대표 12개 end-to-end 작업, 잘못된 조작·취소·실패·복구·저장·cold reopen |
| `prototype/` | 별도 Qt gallery, Material table/plot·buffer·draft·save·CAS harness, `.ui`, PowerShell launcher, 순수 로직 tests와 정확 검증 기록 |
| `data/` | 서로 다른 열 순서·단위의 합성 CSV 2개와 material/contact/PDE용 reference fixtures. 수치·mask·시안 상태의 의미는 `data/README.md` |
| `VERIFICATION_PLAN.md` | 기능별 planning / UI / regression / numerical reference / final integration 목적·시점·선행·재사용 기준 |
| `REQUIREMENT_COVERAGE.csv` | 52개 R 번호의 현재 역할과 기능·작업 추적. 기능 개수나 완료율로 해석하지 않음 |
| `DECISIONS.md` | 주요 대안·선택·비용/라이선스·미결과 Astra baseline/실제 D1 finding 반영표 |
| `SOURCE_EVIDENCE.md`, `source_evidence.json`, `reviews/` | 이번에 실제 읽은 pinned 파일·심볼·한계와 독립 검토 |
| `QA_REPORT.md`, `artifact_validation.json` | 실제 산출물·fixture·연결 검사 결과와 미실행 환경 |
| `CODEX_HANDOFF.md` | 실제 Windows/MoAI/relay/Penpot/Qt/native 확인, CURRENT_STATE 연결, 사용자 검토 후 구현 인계 |
| `build_*.py`, `verify_artifacts.py`, `spec_sections/` | 이 폴더 안에서 문서·도면·화면을 다시 생성하고 검증하는 편집 원본 |
| `ARCHIVE_MANIFEST.json` | ZIP에 포함된 파일별 크기·SHA256. 전달받지 못한 원 ZIP의 manifest를 대신하거나 그 hash를 주장하지 않음 |

문서·화면·작업 수는 찾기 위한 inventory다. 완료는 자신의 자료로 시작해 편집·결과·복구·저장·재개를 따라갈 수 있는지로 판단한다.

## Qt 시제품 실행

기존 사용자 Python 3.13 / PySide6 6.9.1 / Matplotlib 환경의 **실제 python.exe 경로**를 지정한다. 새 package 설치나 유료 서비스 연결을 하지 않는다.

```powershell
cd .\docs\design\20261012-desktop-planning\pro-authored\prototype
.\Start-PlanningPrototype.ps1 -PythonPath 'C:\actual\existing-environment\python.exe'
.\Start-PlanningPrototype.ps1 -PythonPath 'C:\actual\existing-environment\python.exe' -MaterialOnly
```

첫 명령은 상태별 화면을 클릭해 검토하는 Qt gallery다. 두 번째는 표·곡선 선택, owner별 입력/저장, 충돌·부분 저장·재열기를 조작하는 별도 Material harness다. `prototype/README.md`에 상태 초기화·저장 위치·조작과 한계가 있다. harness의 초기 Data r3는 301/241행 전체 사용이며, gallery의 Data r4는 각 원본 index82를 제외한 300/240행 상태다. 두 상태를 같은 개정으로 표시하지 않는다.

**SIMULATED UI / 합성 자료**: gallery의 solver 결과·3D·후보·진행과 harness의 후보 평가값은 계획 fixture다. 실제 혼합제어 traction-free evaluator·fit·native solver/provider를 호출하지 않는다. 핵심 상태 로직의 순수 검사 통과와 실제 Qt 창 실행은 별도이며, 이 환경에 PySide6가 없어 실제 Qt 실행은 미확인이다. Redo·cross-process CAS·crash-atomic bundle·native dock/IME/DPI도 실제 수용으로 보고하지 않는다.

## 원본 재생성과 검증

Python, Pillow, Matplotlib/NumPy가 있는 산출물 작성 환경에서 이 폴더 안에서 실행한다. Windows 제품 runtime에 새 의존성을 추가하는 명령이 아니다.

```text
python build_specs.py
python build_visuals.py
python build_flows.py
python build_verification.py
python verify_artifacts.py
```

`.drawio`는 draw.io Desktop으로 편집할 수 있도록 작성한 XML이지만 이번 세션에서 실제 Desktop 앱으로 열지는 않았다. Penpot native `.penpot` 파일은 이번 환경에서 실제 작성·내보내기하지 못했다. 대신 SVG의 텍스트·도형과 JSON의 정확한 상태/좌표/연결을 제공한다. Codex는 `PROTOTYPE_SCENARIOS.md`와 `CODEX_HANDOFF.md`에 따라 실제 무료 계정에서 원본을 만들고 native export·클릭 확인 기록을 추가한다. 이 파일을 Penpot export라고 가장하지 않는다.

## 근거와 변경 경계

본문으로 받은 **7개 문서**만 원전으로 전달받았다. 원 ZIP, 원 manifest, 기존 Qt spike, 이전 PDF 원본은 받지 않았다. 다른 대화·Space·사용자 Windows 디스크를 조회했다고 가정하지 않는다. 사용자가 이름을 준 Windows MoAI/relay/interview/pm/ponytail 스킬 경로는 현재 컨테이너에서 사용 가능하다고 확인하지 못했으며 대체 결과를 그 도구 실행으로 표시하지 않는다.

기준 commit은 `9a6e3083037630b45694b812b135dc1cd63cf95a`, 공개 tree의 upstream gitlink는 `3e48bf6138f495299f45b1af254bfb4aaff307b8`이다. 공개 GitHub에서 실제 조회한 파일·심볼·확인 한계는 SOURCE_EVIDENCE에 남겼다. source가 존재하는 사실, 사용자 문서가 보고한 과거 실행, 이번의 산출물 검사, 사용자 실제 수용을 구별한다.

기존 Data/Material/PDE/Numerical/Simulation/Evaluation/Study/Discussion owner, native bridge, JobManager와 numerical engines를 재사용·확장한다. 기존 owner를 신규로 재작성하는 backlog는 제거했다. 새 `.caelab` universal format·scheduler·optimizer는 도입하지 않는다. 독립 Research·FreeCAD native Pre·ParaView native Post와 선택 Workbench를 유지한다.

파일 작성 범위는 `docs/design/20261012-desktop-planning/pro-authored/`뿐이다. production code, threshold, settings, CURRENT_STATE/HANDOFF를 수정하거나 git commit/push하지 않았다. Codex가 실제 로컬 변경을 보존하며 이 overlay를 검토·통합하고 현재 상태를 갱신한다.

추가 지출은 0원이다. 새 유료 API·구독·크레딧·UI library·hosting·payment trial 또는 LS-OPT를 도입하지 않았다. 제품 Expert inference 권한을 개발 Pro relay 사용권에서 추정하지 않는다. 무료 후보의 설치·정확 build/license·해당 Windows 지원이 미확인이면 그 상태를 유지한다.

F05 원값 **`3.32295e-6 > 1e-6`**, 실패 metrics, **UNKNOWN/NOT_RELEASED**를 유지한다. 이번 설계 검토 때문에 과거 solver 전체 검증을 다시 돌리지 않는다. 본구현 시작은 사용자 검토와 명시 지시 뒤다.
