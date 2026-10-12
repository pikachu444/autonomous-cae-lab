# Autonomous CAE Lab — desktop UX draft

**검토 가능한 독립 Qt 기획 시제품입니다. 본제품 개발 착수나 공학 계산 완료를 뜻하지 않습니다.**

요청 `PRO-DESKTOP-DESIGN-20261012-06`, UX-STEER-01 및 UX-FIX-01…04를 반영했습니다. 주 설계와 Qt·SVG 상태 작성은 ChatGPT Pro, 독립 검토는 Astra/xhigh, 제한 코드·Qt 검사는 Sol/high, 원본 조사는 Luna/high입니다. 다른 모델의 작업을 Pro 작성으로 표시하지 않습니다.

## Windows에서 실행

검토용 `design/product-ux-20261012` checkout에서 기존 Python/PySide6를 사용합니다. 설치 명령은 없습니다.

```powershell
Set-Location C:\SourceCodes\autonomous-cae-lab\docs\design\20261012-desktop-planning\pro-ux
py -3.13 qt_prototype.py --tool cad
```

`--tool` 값은 `cad`, `simulation`, `thermal`, `thermoelastic`, `post`, `numerical`, `runner`, `expert`, `study`, `data`, `material`, `pde`, `evaluation`, `workbench`입니다. **Window 메뉴에서 다른 독립 도구를 같은 검토 세션으로 엽니다.** 각각 별도 명령으로 실행하면 별도 세션이므로, 도구 전달을 볼 때는 Window 메뉴를 사용하세요.

```powershell
py -3.13 qt_prototype.py --tool expert --workspace "$env:TEMP\caelab-ux-review"
py -3.13 qt_prototype.py --session "C:\Review\Clamp research.json"
py -3.13 qt_prototype.py --scenario material-repair --tool material
```

`--workspace`는 검토 JSON을 저장할 위치입니다. 생략하면 임시 폴더를 씁니다. File → Save/Save as에서 원하는 자연스러운 파일명을 고를 수 있습니다. 여러 도구·작업·후보 채택을 통째로 이어서 보려면 **File → Save review session…**을 사용합니다. 일반 Post Save에도 선택한 합성 결과와 해당 attempt/input이 들어가며, Expert/Study Save에는 연결된 합성 결과 근거가 들어갑니다.

필수 실행 소스는 `qt_prototype.py`, `qt_widgets.py`, `prototype_state.py`, `fixtures/`입니다. PySide6 Core/Gui/Widgets를 사용하며 SVG 내보내기만 QtSvg가 필요합니다. 브라우저, localhost 서버, Matplotlib, 유료 API나 추가 UI kit가 필요하지 않습니다.

## 먼저 조작할 경로

### 형상 → 해석 → 결과 → 설계 비교

1. CAD에서 Sketch → Draw line으로 선을 그립니다. Width/Height와 선 좌표를 바꾸고 Constrain rectangle을 누릅니다. Features에서 두께와 구멍을 바꾸면 그림이 변합니다.
2. Assembly에서 부품·인스턴스·joint를 고릅니다. Motion에서 해당 부품의 상대 자세를 미리 보고 Use pose 또는 Restore pose를 선택합니다.
3. Mesh에서 크기/요소 유형을 바꾸고 Preview mesh를 누릅니다. 불량 요소 행을 선택하면 강조됩니다. 1 mm 예시는 개선된 합성 메시를 보여 줍니다.
4. Conditions/Contact에서 면·하중·구속·접촉을 편집합니다. Save 후 Use in Simulation, 또는 Simulation의 Update geometry…로 저장 형상을 명시적으로 가져옵니다.
5. Simulation에서 솔버·해석 종류와 선택 단계의 값·초기 조건·failure·출력을 편집합니다. Save → Run analysis… → Create review attempt를 누르면 Runner의 PREPARED 행으로 이어집니다. **프로세스는 제출되지 않습니다.**
6. Runner의 Review 메뉴에서 running/failed/cancel/result 합성 상태를 명시적으로 불러옵니다. Open result → Post에서 배열, association, 프레임, Clip/Slice/Warp/Plot over line, 두 점 gauge, A/B 비교를 조작합니다.
7. Post 측정을 Numerical 응답으로 등록합니다. Numerical에서 변수/목표/제약과 후보를 비교합니다. p19만 feasible non-dominated 점이며 p04는 지배된 후보입니다.
8. Apply to owners…에서 CAD/Material을 각각 Apply하고 Save합니다. 실패 경로는 먼저 **Review → Fail next Material adoption save**를 선택합니다. 성공한 CAD 저장은 유지하고 Material만 다시 Save한 다음 Confirm saved selection을 누릅니다. 전체 세션을 저장해 새 프로세스에서 이어갑니다.

### 독립 질문 → 연구 정의 → 결과 근거 → 후속 논의

1. Expert에서 질문·논점·사용자 reply를 작성합니다. Models…에서 기존 OAuth 또는 기존 local endpoint의 역할 모델을 제안할 수 있습니다. 모두 미확인/미연결이며 실제 provider를 호출하지 않습니다.
2. Plan… → Open editable Numerical plan에서 평가기를 선택하고 Add variable…/Add response…로 실제 필드·단위·범위를 지정합니다. Save proposal만으로 연구가 완성되었다고 표시하지 않습니다.
3. 방법을 고르고 Method/방법 입력 탭을 편집합니다. Example matrix는 작성된 입력 예시를 불러옵니다. DOE 예시는 Design points=4이며, budget도 최소 4가 필요합니다. UQ/Sobol의 표본 예산도 검사됩니다.
4. Save → Run study… → Runner. **Review → Load retained result fixture**는 해당 방법의 작성된 합성 결과를 불러옵니다. 실제 계산이나 현재 입력에 대한 예측은 아닙니다.
5. Open result의 방법별 표에서 행을 선택하고 Discuss selection 또는 Use as Study evidence…를 누릅니다. 동일한 결과와 선택 위치가 근거로 연결됩니다. 사용자 reply와 Study의 명시적 판단·이유를 작성하고 Save/reopen합니다.

### 별도 도구

Data는 조밀한 workbook과 연결 curve, Material은 시험·계수·큰 curve·output, PDE는 Model Builder/식·경계·Graphics, Evaluation은 기존 Heat/Expand 단계와 field transfer를 사용합니다. 이 도구들은 CAD·Material·AI 작업 완료를 전역 선행조건으로 요구하지 않습니다.

`F2`, `Enter`, `Esc`, `Tab`/`Shift+Tab`, `Ctrl+S`, `Ctrl+Z`/`Ctrl+Y`, `Ctrl+O`, dock·splitter resize를 사용합니다. CAD/field 그림은 우측/가운데 drag로 시점을 바꾸고 wheel로 확대하며 F로 복원합니다. Expert의 `Ctrl+Enter`는 로컬 사용자 reply 저장입니다.

## 편집 원본

| 파일 | 용도 |
|---|---|
| [screen_states.json](screen_states.json) | 각 1440×900 상태의 도구·입력 patch·선택·탭·다음 작업·D1 기능 연결 |
| [screens/](screens/) | 실제 Qt에서 렌더한 개별 편집 SVG. 작업 대상·곡선·텍스트는 벡터입니다. Qt 기본 버튼·헤더 배경의 작은 내장 래스터는 포함됩니다. |
| [export_screens.py](export_screens.py) | JSON 상태에서 SVG를 재생성하는 QtSvg 코드 |
| [Workflows.drawio](Workflows.drawio) | 형상/해석/채택, Expert/Study, 자료/교정 흐름의 편집 원본 |
| [DESIGN.md](DESIGN.md) | 도구별 구체적 조작·입력·판단·대안·남은 구현 범위 |
| [implementation_map.csv](implementation_map.csv) | 기존 D1 74개 task ID/35개 FN과 실제 소스·새 상태·검증의 연결 |
| [MOAI_HANDOFF.md](MOAI_HANDOFF.md) | 기존 SPEC-DESKTOP-001과 승인 후 개발 단위의 연결. 자동 run 없음. |
| [REVIEW.md](REVIEW.md) | 적용 교정과 실제 검사·미확인 범위 |

SVG 생성:

```powershell
py -3.13 export_screens.py --offscreen
py -3.13 export_screens.py --offscreen --state cad-sketch --output "$env:TEMP\caelab-svg"
```

SVG는 **1440×900 Qt client 영역**입니다. OS 창틀은 포함하지 않습니다. 영문 합성 문구는 원격 Linux에 한국어 글꼴이 없어서 내보내기에 사용한 검토 데이터입니다. 실제 Qt 문서는 Unicode를 유지하며, Windows의 원래 한국어 입력을 바꾸거나 사용자 파일명을 자동 변경하지 않습니다.

### 기존 설치 글꼴 사용 — UX-FIX-05

실행 창과 exporter는 같은 글꼴 정책을 사용합니다. Windows는 기존 `%WINDIR%\Fonts\segoeui.ttf`와 `malgun.ttf`가 있으면 현재 Qt 프로세스에 등록하고 Segoe UI/Malgun Gothic을 우선 사용합니다. 파일이 없거나 로드에 실패하면 Qt가 확인한 설치 글꼴과 시스템 기본 글꼴로 이어집니다. Linux는 Qt가 실제로 찾은 시스템 글꼴을 우선하며, 설치되어 있지 않은 Segoe UI나 DejaVu Sans를 강제하지 않습니다. stylesheet와 도형·그래프 글자도 이 선택을 따릅니다. 글꼴 설치·다운로드·저장소 복사는 없습니다.

기존 wrapper 없이 같은 export 명령을 실행하면 됩니다. 이번 교정만 먼저 볼 때는 다음과 같이 별도 검토 폴더로 내보낼 수 있습니다.

```powershell
py -3.13 export_screens.py --offscreen --state post-compare --state expert-discussion --output "$env:TEMP\caelab-font-svg" --png-output "$env:TEMP\caelab-font-png"
```

생성한 `render_manifest.json`의 `font_policy`에는 선택·실제 해석된 family와 기존 파일 로드 결과가 기록됩니다. 이 기록은 화면에 설명 띠를 추가하지 않습니다. 원격 Linux의 글꼴·렌더 확인과 Codex의 실제 Windows 확인은 별도입니다. 이 원격 Linux에는 Hangul 글꼴이 없으며, 한국어 glyph의 Windows 렌더 성공을 대신 검증하지 않습니다. 기존 `screens/`의 전체 SVG/manifest는 해당 파일에 기록된 이전 소스의 렌더이며, 최신 플랫폼별 결과는 위 명령으로 다시 생성합니다.

## 제한 기술 검사

아래 스크립트는 실제 Qt offscreen 입력 또는 stdlib 상태 검사만 수행합니다. Windows OS 입력·native host·solver/provider 수용 검사로 확대하지 않습니다.

```powershell
py -3.13 qt_acceptance.py --source . --offscreen --output "$env:TEMP\caelab-check-base"
py -3.13 qt_followup_acceptance.py --source . --output "$env:TEMP\caelab-check-methods"
py -3.13 qt_ux04_acceptance.py --source . --output "$env:TEMP\caelab-check-ux04"
py -3.13 state_acceptance.py --source . --output "$env:TEMP\caelab-check-state"
```

실제 FreeCAD/ParaView 실행·도킹, solver/optimizer/PDE 계산, provider 권한·호출, remote scheduler, 장비 연결은 이 시제품에서 실행하지 않았습니다. weak form/ODE·확장 구성모델의 정의는 편집할 수 있으며 미연결 실행은 명시적으로 남아 있습니다. **UNKNOWN, NOT_RELEASED, F05 `3.32295e-6 > 1e-6`은 그대로입니다.**
