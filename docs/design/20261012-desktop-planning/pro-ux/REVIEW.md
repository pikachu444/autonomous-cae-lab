# Desktop UX review record

**상태: 사용자 검토용 planning draft. 실제 Qt 조작을 확인했으며 본제품 개발은 시작하지 않았다.**

요청 `PRO-DESKTOP-DESIGN-20261012-06`, UX-STEER-01, UX-SOURCE-01, UX-FIX-01…04의 Qt core는 [827ee9e](https://github.com/pikachu444/autonomous-cae-lab/commit/827ee9e71c0315d3b76f9ed8197e971c2d944e7c)에 먼저 게시했다. `fef3016`의 전체 편집 원본은 같은 core로 렌더했다. 아래 전체 검사와 SHA-256은 그 시점의 기록이다. 이후 제한 교정은 바로 아래에 별도로 기록한다.

## 이후 제한 교정 — UX-FIX-05 / UX-VISUAL-01

실행 main과 exporter가 `configure_application_fonts`를 함께 사용한다. Windows 기존 Segoe UI/Malgun Gothic 파일을 프로세스에만 등록하고 실제 설치 family를 선택한다. Linux는 Qt의 실제 시스템 family를 우선한다. stylesheet와 QPainter/GraphNode의 고정 family를 제거했다. 글꼴 복사·설치·다운로드는 없다. 사용법은 README의 기존 설치 글꼴 절에 있다.

Sol/high는 기존 Linux PySide6 6.9.1/offscreen에서 선택·resolved·widget family와 10pt, 반복 호출, QLabel/GraphNode의 in-memory SVG text를 확인했다. 실제 설치 DejaVu Sans를 사용했고 없는 Windows family를 강제하지 않았다. root는 Post compare/gauge, Numerical MOO, Inverse result, Expert discussion 상태를 실제 export했다. Compare의 Quantity/A/B/Unit을 채운 뒤 폭을 정해 0.31/0.29 mm를 읽을 수 있게 했다. 같은 빈 표 초기 폭 문제가 보인 Post measurement 이름과 Numerical response 이름/role도 실제 데이터 기준으로 초기 폭을 정했다.

이 확인은 원격 Linux의 제한 글꼴·레이아웃 확인이다. 최신 Windows glyph/OS 창 확인은 Codex 담당이며 이 기록을 Windows PASS로 확대하지 않는다. 사용자가 보고한 `fef3016`의 Windows Python3.13.5/PySide6 6.9.1 followup 6그룹·UX04 4경로 PASS와 52state export는 사용자 측 실행이고, 당시 Segoe/Malgun wrapper를 사용한 시각 확인과 이번 source 교정을 구별한다. 기존 전체 SVG/manifest와 `checks.json`은 이전 source의 기록을 유지한다.

## 실제로 교정한 사용자 작업

### UX-MAP-01 / UX-MAP-02 — 정확한 개발 연결

FN-20의 DOE/Sobol, FN-21의 Optimization/Inverse, FN-22의 UQ, FN-23의 RBF, FN-24의 MOO/MDO를 task별로 다시 연결했다. 추가 `ux_source`, `ux_screen_states`, `ux_actions`, `ux_acceptance_focus`와 시제품 상태를 교정하고 JSON의 functions, 화면 색인, DESIGN의 대응표를 같은 기준으로 맞췄다. mixed-domain/gradient/trained-artifact 확장은 현재 숫자 표나 합성 결과만으로 구현되었다고 표시하지 않는다.

FN-01은 실제 기존 File Open/Save as dialog와 review-file cold reopen을 연결한다. FN-34는 기존 제품 명령의 GUI/CLI/Python/MCP 동등성 계약 참조다. FN-32/FN-35의 현재 시제품 state 연결은 비워 두고 D1의 정확한 REPORT-REVIEW/REOPEN-REPORT 및 DEVICE-PLAN/DATA-CALIBRATION/RUN-ACTIVE/C09 prior reference와 미연결 상태를 명시했다. 기본 Post/Study/Data 화면을 전용 report/acquisition 작업 완료로 간주하지 않는다.

Luna/high의 독립 읽기 재확인과 root의 비교에서 기존 74행의 순서·18개 원 열·모든 원 값은 동일했고, 변경은 추가 UX 정보와 링크뿐이었다. 방법별 연결과 prior-only 분류에서 남은 구체적 불일치는 없었다. 새 화면·engine·owner는 추가하지 않았다.

### UX-FIX-06 — step 이름과 발언별 근거

Step dialog는 선택 step을 복사한 뒤 name/duration/control만 갱신한다. Hold의 `time_step=2e-5`, `force=-125`를 입력한 뒤 이름만 바꾸어도 다른 필드를 유지한다. Expert의 pending/turn 첨부는 `{id, locator}` 쌍이다. Evidence dock의 Document evidence와 Selected turn attachments를 구별하고, 발언 선택은 그 발언에 붙인 쌍만 보여 준다. Open selected는 해당 method tab/row로 이동하며 잘못된 locator는 unavailable로 처리한다. 과거 result ID만 있는 첨부는 유일한 위치일 때만 해석하며 여러 위치를 모두 그 발언에 붙이지 않는다.

Sol/high가 별도 immutable snapshot에서 위 두 경로를 실제 Linux Qt offscreen으로 확인했다. Hold 이름 변경·다른 step 왕복·ordinary Save/별도 프로세스·cold Qt, 같은 DOE result의 d1/d2 개별 reply·선택 근거·정확 row 열기·ordinary Save/별도 프로세스·cold Qt 모두 PASS였다. Qt callback error는 없었다. `qt_ux06_acceptance.py`와 `checks.json`의 followup 기록에 확인 범위와 source hash를 남겼다. 기존 UX04 검사의 첨부 기대값도 result ID 단독에서 정확한 쌍으로 고쳤다. 전체 이전 검사를 새로 실행한 것으로 표시하지 않는다.

| 문제 | 현재 동작 | 확인 근거 |
|---|---|---|
| 작은 time step이 기본 float delegate에서 0으로 반올림 | 숫자를 text editor에서 편집한다. `.001`, `1e-6`, `1.2e-5`, 음수와 미완성 draft를 표현하고 저장한다. 필수 입력 검사는 별도로 수행한다. | F2/Enter, Save/reopen 실제 Qt 검사. 미완성 입력 repair는 이전 Windows 검사에서도 사용자 보고 PASS. |
| invalid input으로 review attempt 생성 | negative time step, stale mesh, 빈 활성 contact 면, 알 수 없는 response role/invalid limit는 막고 해당 편집 위치로 이동한다. signed load와 의미 있는 zero는 허용한다. | Qt base 검사, stdlib required-parameter 검사. |
| Sketch 치수·구속이 선을 삭제 | constraint 필드만 patch한다. Draw line → Width90 → Constrain → Save/reopen에서 선/표/뷰가 같다. | UX04 실제 mouse drag와 재열기 검사. |
| saved shape가 다른 도구에서 달라짐 | saved pose45°, instances4, hole, mesh1을 Simulation에 전달한다. Post A/B는 각 결과의 thickness13.7/14.6을 그린다. | UX04 검사. 현재 CAD draft thickness99로 바꾸어도 비교 형상 유지. |
| Steps 선택과 하단 값 불일치 | Hold 선택·편집은 Hold만 바꾸고 Load 값은 유지한다. thermal은 구조 impact/contact/failure를 노출하지 않는다. | Hold2 → 3, Load1 유지와 thermal 페이지 actual Qt 검사. |
| Post Undo·시간·측정 불일치 | array/unit/association을 한 명령으로 Undo한다. frame0의 표/curve/측정은 0이며 없는 frame은 unavailable이다. | Qt base 검사와 ordinary Post Save 후 별도 프로세스 재열기. |
| Numerical Undo 후 보이는 값 불일치 | 변수·응답·방법 표가 현재 문서로 갱신된다. 미완성 편집 buffer도 Undo/Redo/reopen으로 복구된다. | Qt base/followup 검사. |
| 새 Plan이 빈 평가기/변수/응답에서 막힘 | 평가기와 typed owner/field/unit, 변수와 응답을 실제 dialog로 추가·삭제·편집한다. | 새 Plan 작성과 freeze 입력 검사. |
| 방법 이름만 달라지는 연구 | DOE, Inverse, Optimization, Sobol, UQ, RBF/surrogate, MDO 입력과 별도의 authored result 표·curve를 작성했다. 선택 결과를 원 Expert/Study 근거로 연결한다. | 방법별 SVG 실제 렌더, DOE end-to-end Qt 검사. 모든 방법의 엔진 결과 검증은 아님. |
| Inverse train/holdout 혼동 | observation source/mask/weight/residual scale과 Train/Holdout을 구별한다. train 부재·음수 weight·잘못된 표본 예산을 막는다. | followup 실제 Qt 검사. Data A82 제외 후 300개 training ID 확인. |
| 지배된 p04가 Pareto front에 포함 | 모든 후보는 볼 수 있고 feasible non-dominated p19만 front marker다. 제약 위반·실패는 별도 상태다. | 원 fixture의 두 Minimize 방향을 이용한 소스 검토 및 Numerical 화면 확인. |
| Expert/Workbench node 글자 소멸 | node 자체 paint가 label을 그린다. 지역 QGraphicsTextItem 수명에 의존하지 않는다. | Qt label pixel 검사. Windows 글자 표시 성공은 UX-FIX-03의 사용자 보고. |
| Expert가 미연결 표시만 갖고 역할 설정이 없음 | Models…에서 기존 OAuth/local/unconfigured 경로와 역할 model override를 저장한다. 권한은 UNVERIFIED이며 provider 호출은 없다. | 소스 검토, 실제 dialog 렌더 및 이전 재열기 검사. |
| 결과가 Expert 후속 논의로 돌아가지 못함 | Numerical authored result의 선택 행을 원 Discussion에 연결하고 실제 로컬 사용자 reply와 함께 저장한다. Study 판단은 사용자가 명시한다. | DOE Plan → attempt → result → reply → ordinary Save/cold reopen → Study judgment 경로 PASS. |
| PDE가 같은 boundary 문자열만 편집 | 각 target/type/expression을 독립 Apply/Reset한다. weak form의 test/trial/domain과 ODE state/IC/time/curve 화면이 있다. | 실제 Qt 화면 렌더 및 소스 검토. PDE solve는 미실행. |
| MOO owner 채택의 끝이 없음 | CAD/Material을 별도로 Apply/Save하고 실패한 쪽만 retry한다. 성공 조합 확인 후 cold reopen한다. debug 실패 선택은 Review 메뉴로 옮겼다. | stdlib partial-save/취소/stale/cold reopen 검사. 실제 dialog 렌더 확인. |
| r19 복구·thermal 재열기·Calibration 원문 오경로 | r19 동일 복구/변경 분기/Cancel, Heat V-02/r4와 Expand V-03/r6, CAL-018/r2 Calibration.txt를 각각 올바른 대상으로 연다. | stdlib 상태 검사. 실제 backend 실행을 포함하지 않음. |

## 실행한 검사와 역할

최종 core에 대해 **Linux Python 3.12.14 / PySide6 6.9.1 / Qt platform=offscreen**을 사용했다. 사용자 허용에 따라 원격 임시 환경에 무료 PySide6를 한 번 설치했다. Windows 사용자 환경이나 제품 dependency 파일을 변경하지 않았다.

| 검사 | 최종 결과 | 범위 |
|---|---|---|
| `qt_acceptance.py` | 9개 집중 그룹 PASS, Qt callback error 없음 | F2 정밀 수치, invalid gate/repair, typed binding, table Undo, Post frame, Tab/Backtab, graph text, compact evaluator row |
| `qt_followup_acceptance.py` | 6개 집중 그룹 PASS, Qt callback error 없음 | matrix field remap, MOO response binding, budget, train mask/weight, invalid buffer history, ordinary Post Save/cold reopen |
| `qt_ux04_acceptance.py` | 4개 사용자 경로 PASS, Qt callback error 없음 | Sketch, saved geometry/step, exact A/B geometry, Expert→연구 결과→reply→Study |
| `state_acceptance.py` | 14개 상태 그룹 PASS | partial retry, cancel/stale gate, Data 선택/전달, exact reopen, repair, Runner 관계, provider/release 경계 |
| `export_screens.py` | 52개 상태가 1440×900 Qt client 영역으로 렌더됨 | 각 SVG의 실제 QWidget 렌더. 전체 물리 의미·전체 OS 조작을 검증했다는 뜻은 아님. |

정량 기록은 [checks.json](checks.json), 렌더별 기록은 [screens/render_manifest.json](screens/render_manifest.json)에 있다. 실행 방법은 [README.md](README.md)에 있다.

최종 편집 원본 검사는 SVG XML/1440×900 viewBox/텍스트·경로, 외부 이미지 의존 없음, source hash 일치, drawio 3개 페이지와 문서 링크를 확인했다. Qt 스타일이 그린 작은 버튼·헤더 배경은 내장 래스터다. 작업 형상·곡선·텍스트는 벡터이고 전체 화면 PNG를 붙인 파일은 없다. Inverse SVG는 별도로 Inkscape에서 렌더해 표·curve·하단 action의 배치도 확인했다. Luna의 마지막 읽기 전용 확인에서 74개 원 task의 기존 18개 열은 값 단위로 모두 동일했고, 추가 화면 참조는 모두 상태 JSON으로 연결됐다.

**작성/검토 분담:** ChatGPT Pro가 주 설계·Qt code·상태·편집 원본을 작성했다. Sol/high는 제한된 코드·실제 Qt 검사를 별도 immutable source snapshot에서 수행하고 검사 스크립트를 작성했다. root는 그 스크립트를 최종 core에 다시 실행했다. Astra/xhigh는 독립 핵심 설계/소스 검토와 선택 화면 시각 검토를 수행했다. Luna/high는 기존 source와 backlog를 읽었다. 다른 모델의 작업을 Pro 작성으로 표시하지 않는다.

Astra의 마지막 시각 재검토는 Inverse/Sobol/MDO/ODE/Models/partial-save 여섯 화면에서 앞서 지적한 세 항목을 확인하는 범위였다. MDO 평가기·discipline 일치, 열 잘림, x축 제목 겹침을 고친 뒤 추가 요청 없이 종료했다. 이는 별도의 전체 GUI acceptance가 아니다.

사용자가 전달한 Windows 검사에서 `48cbac3`의 정밀 수치·미완성 입력 repair·compact row가 PASS였다는 사실은 **사용자 측 실행 보고**다. 원격 root가 Windows OS 입력을 확인했다고 주장하지 않는다. 최신 `827ee9e`의 실제 Windows 창·OS 입력 확인은 Codex 검토 대상이다. 앞서 Windows native capture가 검은 화면이었던 제약을 제거했다고 주장하지 않는다.

### 검사한 core의 SHA-256

```text
prototype_state.py  a13bf19203db1a2468ae813ad31f574291afa39c914a25549f290bef366be4d2
qt_prototype.py     c168fed9ca2a7abe5e512cfa533414bdcb0abc3dd7a9d97f83f598e90cd42733
qt_widgets.py       a4d4de78a65cf213b23c22662e11cf6af6c7473e9c933d6864227d7179c267fe
```

## 읽은 원본과 미확인 자료

- 요구·방향·재사용: [3136798 원사용자 요구](https://github.com/pikachu444/autonomous-cae-lab/blob/313679843813b63dee44409de5c5abc43c8a373b/docs/design/20261012-desktop-planning/USER_DESIGN_REQUIREMENTS.md), 같은 pin의 `AGENTS.md`, `docs/PRODUCT_PLAN.md` 특히 §3, `PRODUCT_UI_MCP_PLAN.md`, `SOURCE_REUSE.md`, `CODEX_WORKFLOW.md`와 planning 전후 문맥을 읽었다. 과거 CURRENT_STATE의 다음 구현보다 최신 사용자 지시를 적용했다.
- D1: [95a2389 pro-authored](https://github.com/pikachu444/autonomous-cae-lab/tree/95a2389ca534b807420a4e7dbe2397f5e60953c9/docs/design/20261012-desktop-planning/pro-authored)의 `FUNCTION_SPEC.md`, `SCREEN_SPEC.md`, `IMPLEMENTATION_BACKLOG.csv`, `PROTOTYPE_SCENARIOS.md`, `spec_sections/WORKFLOW_CONTRACTS.md`와 관련 Qt/state/fixture source를 읽었다. 원본은 수정하지 않았다. 아직 게시되지 않은 D1 전체 SVG/JSON이 있다고 가정하지 않았다.
- 제품: [9a6e308 source](https://github.com/pikachu444/autonomous-cae-lab/tree/9a6e3083037630b45694b812b135dc1cd63cf95a)의 관련 owner/reader/desktop/native bridge/Evaluation/Expert 코드를 읽었다. 전체 저장소 전수 감사는 아니다. `apps/desktop_pre/commands.py`는 조회에서 없었으며 실제 `cae_prep.py`, `fem_edit.py`, `motion.py`, `parameters.py`, `mesh_binding.py`, `freeze_analysis.py`를 재사용 대상으로 삼았다.
- MoAI: [기존 SPEC-DESKTOP-001](https://github.com/pikachu444/autonomous-cae-lab/tree/313679843813b63dee44409de5c5abc43c8a373b/.moai/specs/SPEC-DESKTOP-001)의 `spec.md`, `plan.md`, `acceptance.md`를 실제 읽고 [MOAI_HANDOFF.md](MOAI_HANDOFF.md)에 연결했다. MoAI CLI/자동 run이나 `.moai` 수정은 하지 않았다.
- 공식 작업 구조: [MCalibration Quick Tutorial](https://www.ansys.com/content/dam/resource-center/datasheet/mcalibration-quick-tutorial.pdf), [ParaView 공식 filtering guide](https://docs.paraview.org/en/v6.2.0/UsersGuide/filteringData.html)를 읽었다. 상용 source/asset을 복사하지 않았다.
- [Co-STORM arXiv Figure 15](https://arxiv.org/html/2408.15232v2)의 이번 직접 재열람은 도구의 DisabledError로 실패했다. Figure 15를 새로 시각 확인했다고 표시하지 않는다. 사용자 지정 논점 지도/다자 turn/reply/evidence/개입 구조와 공개 PRODUCT_PLAN의 확정 방향을 적용했다.
- upstream `3e48bf6138f495299f45b1af254bfb4aaff307b8` 전체를 새로 전수 조사하거나 solver campaign을 재실행하지 않았다.

## 미실행과 남은 제품 구현

FreeCAD/ParaView native host 실행·도킹·실제 3D 조작, solver/optimizer/PDE 계산, provider/OAuth 권한 확인·호출, local model/tool call, remote scheduler, 실제 장비·측정 acquisition은 **NOT_RUN**이다. 합성 수치·mesh·3D·method result는 authored illustration이다. Numerical result에는 `computed_from_input=false`가 있으며, 편집한 입력을 계산한 결과라고 표시하지 않는다.

모든 FN-01…35를 제품 구현 완료라고 주장하지 않는다. 특히 report/device/setup/cross-surface 확장은 D1 상세 scope와 작업표에 남겨 두었으며 별도 실제 장비/report GUI를 새로 구현하지 않았다. Formula는 editable recipe이고 general expression engine이 아니다. 구성모델·weak form/ODE는 정의 편집 범위이며 backend solve는 이후 구현 대상이다. 기존 threshold, `UNKNOWN`, `NOT_RELEASED`, F05 `3.32295e-6 > 1e-6`은 바꾸지 않았다.

이번 변경의 소유권은 `pro-ux/`뿐이다. 제품·pro-authored·main·settings·CURRENT_STATE·회사 파일은 수정 대상이 아니다. 사용자 검토 뒤 개발 시작 지시가 있을 때 [implementation_map.csv](implementation_map.csv)와 [MOAI_HANDOFF.md](MOAI_HANDOFF.md)를 따라 기존 owner에 연결한다.
