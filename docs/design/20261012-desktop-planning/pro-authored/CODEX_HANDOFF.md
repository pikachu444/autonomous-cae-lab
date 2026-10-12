# Codex 통합·실제 실행 인계

요청 PRO-DESKTOP-DESIGN-20261012-01의 **Pro D1 원본 제출**이다. 이 문서는 사용자 PC에서 실행한 기록이 아니다. 이번 ZIP은 경로 `docs/design/20261012-desktop-planning/pro-authored/`만 포함하는 overlay이며 production patch가 아니다.

## 1. 실제 회수와 현재 상태 반영

1. ZIP의 ARCHIVE_MANIFEST.json과 SHA256을 확인하고 같은 경로에 회수한다. 기존 사용자 미커밋 작업은 보존한다. 기존 Pro v2/PDF/Qt spike를 교체하거나 이번 산출물의 검증 근거로 합치지 않는다.
2. pinned base `9a6e3083037630b45694b812b135dc1cd63cf95a`와 upstream gitlink `3e48bf6138f495299f45b1af254bfb4aaff307b8`를 현재 checkout에서 대조한다. 차이가 있으면 사용자가 바꾼 파일을 덮어쓰지 않고 해당 변경의 설계 영향만 조사한다.
3. 기존 CURRENT_STATE에 요청 ID, 실제 수신한 ZIP/manifest, Pro 작성물, Astra 검토 결과, Codex가 직접 확인한 항목과 미확인을 구별해 기록한다. HANDOFF는 같은 산출물 경로와 다음 실제 조작을 참조한다. 이 D1 안에 현재 업무 상태의 새 소유자를 만들지 않는다.
4. 문서 수·screen 수·test 수를 완료율로 쓰지 않는다. 구현 status는 NOT_STARTED_IN_THIS_REQUEST다. review 수정으로 제품 실행/수치/공학 PASS를 추가하지 않는다.

## 2. MoAI·relay·설정 확인

사용자가 지정한 `C:\Users\pikac\AppData\Local\Programs\moai\moai.exe`, 당시 버전3.2.0-dev.2aab5f7와 verification JSON은 이번 Pro 환경에서 접근하지 못했다. 설치 사실과 현재 세션 callable skills/commands/MCP를 구별해 실제 조회한다. 기존 AGENTS/.codex/config/user settings/skills를 백업·diff하고 **merge**한다. 기본 초기화로 model/permission 설정을 덮어쓰지 않는다.

`chatgpt-pro-relay`, `ouroboros-interview`, `ouroboros-pm`, `ponytail`, `computer-use`와 MoAI 실제 installed skill은 사용자 Windows의 실제 파일을 읽어 필요한 단계에만 적용한다. 여기서 해당 Windows skill이 있다고 가정해 호출하거나 새 공급자·유료 API를 연결하지 않았다. Pro relay는 개발 협업이며 product Expert entitlement가 아니다. 지정한 model/effort의 실제 사용 가능성을 확인하고 미사용 모델의 결과로 표기하지 않는다.

현재 작업은 whole-product planning/correction이다. MoAI SPEC/task handoff를 연결해도 자동으로 implementation 단계로 전환하지 않는다. 사용자 승인 전 구현 authoring/production integration을 시작하지 않는다.

## 3. 편집 가능한 도면과 시안

- `DESKTOP_WORKFLOWS.drawio`를 실제 draw.io Desktop에서 열어 페이지·edge label·화살표·wrap을 확인하고 같은 원본으로 저장한다. 여기서는 XML parse/참조 확인까지만 했다. GPLv3 Desktop의 exact 설치 build/notice는 실제 환경에서 확인한다.
- `screens/*.svg`는 텍스트·선·표·도형을 개별 편집할 수 있다. `screens/screens.json`은 같은1440×900 좌표의 layers/field types/units/defaults/ranges/owner/hotspots/target/scenarios를 가진다. PNG를 다시 디자인 원본으로 추적할 필요가 없다.
- Penpot Professional은 공식0원 경로를 조사했지만 실제 계정 접근·편집·export는 수행하지 않았다. 실제 무료 계정에서 SVG import→공통 components/tokens→hotspot 연결→SC 경로 클릭→native `.penpot` export를 수행한다. 선결제를 요구하는 trial이나 paid upgrade는 선택하지 않는다. 원본/내보내기/hash/실제 작업 기록을 회수한다.
- Penpot이 막히면 SVG/JSON/.drawio/Qt .ui 원본을 그대로 검토할 수 있다. 없는 native export를 만들었다고 보고하지 않는다. Penpot을 제품 GUI/runtime으로 포함하지 않는다.

## 4. 별도 Qt 시제품 실행

기존 사용자 Python3.13/PySide6 **6.9.1**/Matplotlib 환경을 실제로 선택한다. `%LOCALAPPDATA%/AutonomousCAELab/windows-runtime/venv`에 PySide6가 있다고 추정하지 않는다. FreeCAD/ParaView bundled Python과 혼합하지 않는다. 아래 경로는 **실제 interpreter를 넣는 자리 표시자**다.

```powershell
cd C:\SourceCodes\autonomous-cae-lab\docs\design\20261012-desktop-planning\pro-authored\prototype
.\Start-PlanningPrototype.ps1 -PythonPath 'C:\actual\existing-environment\python.exe'
.\Start-PlanningPrototype.ps1 -PythonPath 'C:\actual\existing-environment\python.exe' -MaterialOnly
```

launcher는 새 package 설치·결제·서비스 실행을 하지 않는다. Gallery는 PNG+focusable hotspot으로 시안 경로를 확인한다. Material 모드는 QUiLoader로 실제 `.ui`를 읽고 Qt 표/Matplotlib/owner draft/save/receipt/recovery 상태를 조작한다. 두 모드 모두 production import, solver, actual fit/holdout, provider를 호출하지 않는다. GUI에 SIMULATED/FUTURE/CURRENT BLOCKED 표시를 유지한다.

시제품의 기본 JSON 저장 위치는 `~/CAE_Planning_Demo/material-neo-hooke-planning.json`이다. 이는 별도 planning state이며 제품 파일 형식 제안이 아니다. `--state`/`-StatePath`로 새 임시 위치를 선택할 수 있다. 사용자가 중단한 기존 FreeCAD 세션이나 열려 있는 production 문서를 재사용하지 않는다.

### 실제로 추가 확인할 항목

1. 1440×900, 1920×1080과100/125/150/200%에서 메뉴·dock·표·곡선·하단버튼 잘림, 한글/IME, focus/selection을 확인한다. offscreen PNG/XML을 Windows 수용으로 표시하지 않는다.
2. F2/Enter/Tab/Esc, 같은 셀 재focus, Material/Plan 번갈아 편집 후 focused Ctrl+Z, view hide와 mask 분리, table↔plot 정확 source sample 선택을 확인한다. Redo는 이 bounded harness에서 미구현임을 유지한다.
3. Material+Plan 두 dirty, invalid raw text, Material save success/Plan failure, source refresh Cancel/Apply/Save, current client conflict, adoption Apply→dirtyr18→explicitSaver19, Save 전/후 cold reopen을 조작한다.
4. window close와 job cancellation을 따로 확인한다. 순수 시제품의 cancel state가 실제 native/solver process termination 증거가 아님을 유지한다.
5. sample selection/retained candidate 열기에서 evaluation ID가 늘지 않는지, 명시 detail만 새 모의sidecar를 만드는지 확인한다. 실제 traction-free는 여전히 미구현이다.

## 5. 사용자 검토와 후속 교정

먼저 SC-01(Material), SC-02(contact), SC-03(Post comparison/repair), SC-06(Evaluation), SC-09/12(Study·다음 연구·measurement)를 사용자에게 보여준다. 잘못된 행동·취소·실패·저장·재열기를 실제로 따라가고 screen/state별 교정 요청을 기록한다. 문서 개수나 Astra의 문장상 통과를 사용자의 작업 수용으로 대체하지 않는다.

사용자가 개발 시작을 지시하면 IMPLEMENTATION_BACKLOG의 해당 task를 MoAI SPEC에 연결한다. implementation_prerequisites는 구현 DAG, runtime_prerequisites는 선택 경로의 실행 조건이다. 필요한 기존 owner/handler 최소 부분을 재사용해 각 독립 lane을 병행한다. Pro가 의미 있는 기능 단위의 코드를 작성하고 Codex가 실제 실행·검토·통합하며 Astra가 중요한 계약을 검토한다.

검토한 변경만 의미 있는 단위로 commit한다. 이번 Pro 응답 자체는 commit/push를 수행하지 않았다. Codex는 실제 commit ID와 remote 반영 결과를 확인한 사실대로 기록한다. F05 원값, 실패 metric, UNKNOWN/NOT_RELEASED와 이전 runs/artifacts는 그대로 보존한다.
