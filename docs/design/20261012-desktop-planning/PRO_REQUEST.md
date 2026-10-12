# 실제 Pro 위임 — 전달할 작업

요청 ID: **PRO-DESKTOP-DESIGN-20261012-01**. 전체 목표/기준과 전송·회수 상태는
CURRENT_STATE가 소유한다. 아래는 실제 보낼 요청 본문이며 Pro 응답이 아니다.

Autonomous CAE Lab의 전체 제품 상세 기획과 GUI 설계의 주 작성자로 작업해 주세요.
이번은 전체 설계와 편집 가능한 기획 시안/별도 Qt 시제품 단계입니다. 사용자에게
산출물을 제시하고 사용자가 개발 시작을 지시한 뒤 본구현합니다. 이전 문서의 기획 완료,
다음 구현, cloud-only, 옛 실행 순서가 이번 요구를 되돌리지 못합니다. 필요한 설계·교정
산출물을 실제 파일로 작성하고 설명이나 계획만으로 끝내지 마세요.

## 최신 요구와 전달한 자료

첨부 USER_DESIGN_REQUIREMENTS.md는 최신 사용자 요청 원문입니다. 그 요청과
AGENTS/PROJECT_SCOPE/REQUIREMENTS_VALIDITY_REVIEW를 함께 읽으세요. 저장소는
https://github.com/pikachu444/autonomous-cae-lab, 코드 기준은
`9a6e3083037630b45694b812b135dc1cd63cf95a`, upstream은
`3e48bf6138f495299f45b1af254bfb4aaff307b8`입니다. 첨부 manifest는 원본/작업 중
문서의 SHA256을 구별합니다. 로컬 미커밋 문서는 이번 새 지시에 맞춘 진입점/배정 정리,
MoAI 연결과 별도 planning prototype입니다. 제품 코드에는 변경이 없습니다.
사용자 `.codex-remote-attachments/`, 인증/비밀/회사 CAD는 포함하지 않았습니다.

첨부 SOURCE_REUSE는 소스 조사이고 ASTRA_BASELINE_REVIEW는 기존 계획의 독립
검토입니다. 기준 코드의 EvaluationDefinition/Study/Data/PDE owner와 native bridge는
이미 있습니다. 과거 계획에서 신규라고 한 owner를 다시 만드는 작업표를 작성하지 마세요.
기존 전체 Pro v2·PDF는 재사용 원본이며 이번 사용자 상세 기획/사용성 수용 증거가 아닙니다.
다른 대화/Space/사용자 디스크를 읽었다고 가정하지 말고 실제 첨부 내용을 판단에 쓰세요.

Qt 기술 시제품은 Codex가 기존 Pro v2와 최신 Material 예시에서 조작 가능성을 확인하는
별도 spike입니다. 모든 피팅은 SIMULATED UI이며 solver/provider와 연결하지 않았습니다.
이 초안이나 Codex 배치를 정답으로 강제하지 않습니다. 실제 작업의 누락을 찾아 수정하세요.

## 고정된 제품/비용/책임 조건

Windows 로컬 데스크톱 공학 프로그램입니다. 독립 Qt/PySide6 Research 도구와 FreeCAD
native CAD/FE, ParaView native Post를 활용합니다. 메뉴/dock/표/tree/plot/3D/파일/keyboard
가 연결된 환경을 설계하세요. 브라우저/localhost/HTML/Streamlit/Gradio/웹 wrapping을
제품 주 GUI로 만들지 않습니다. Data/Material/PDE/Numerical/Runner/Expert/Study 각각은
독립 사용하며 Workbench는 선택입니다. AI와 CAD가 필요한 작업에만 그 의존성을 둡니다.

추가 지출은 0원입니다. 새 유료 API·구독·크레딧·UI library·서버/hosting·유료 plugin·결제
필요 trial은 제외합니다. LS-OPT 불필요. Qt는 기존 PySide6 6.9.1/Core/Gui/Widgets/UiTools,
Matplotlib 환경을 재사용합니다. 추가 library의 무료/배포 license는 실제 확인하세요.
개발용 Pro relay와 제품 Expert inference는 별개입니다. subscription을 임의 API 권한으로
가정하지 마세요. 미연결/limit 시 draft/retained 자료는 유지하고 유료 fallback 금지입니다.

Core는 common record/schema/mapping/gates/artifact/evidence/provenance, Domain은
engineering rule, Adapter는 native syntax/path를 소유합니다. Numerical engines가 DOE/search
후보를 만들고 solvers가 physics를 계산합니다. 같은 문서/revision/result/commands를
GUI/CLI/Python/optional MCP가 다룹니다. invalid draft는 저장 가능, invalid required input/CAD는
export/run 차단. 새 run IDs/store와 이전 결과·실패 metrics 보존. UNKNOWN/NOT_RELEASED 유지.
F05 원값 `3.32295e-6 > 1e-6`을 바꾸거나 전체 기획 선행 gate로 되살리지 않습니다.

Pro는 전체 명세/상세 설계의 주 작성자, Codex는 도구 산출물 작성·실제 실행/시각 확인·통합,
Astra는 최신 자료와 실제 산출물을 읽는 independent reviewer입니다. MoAI는 SPEC/인계
연결을 관리하며 모델/공급자·단계의 자동 전환을 허가하지 않습니다. 이 요청은 본구현이 아닙니다.

## 판단과 실제 산출물

기능을 요구 절 번호별 한 행이나 똑같은 폼으로 만들지 말고 사용자 결과 단위로 재구성하세요.
원요구의 nonlinear implicit/explicit/contact/failure/constitutive/PDE/coupling/inverse/DOE/
optimization/UQ/sensitivity/surrogate/MOO/remote/physical measurement calibration도
scope에 남겨 구체적인 기능으로 분해하세요. 미지원/무료 경로 미확인은 삭제하지 말고
현재 구현·추가 개발·외부 의존·미결을 표시하세요.

실제 downloadable ZIP으로 다음 편집 원본/문서를 작성해 주세요. 파일은
`docs/design/20261012-desktop-planning/pro-authored/` 아래로 한정합니다.
기존 production code/threshold/settings를 변경하지 않습니다.

1. 전체 FUNCTION_SPEC.md: persona/목표/start→end workflow, 단계별 대상/판단/조작,
   inputs/outputs/units/storage/reopen, screen/state/error/cancel/recovery, existing file/command
   reuse, new/changed code/service, dependencies/order와 user completion. 전역 표로 빠진 기능의
   핵심 동작을 추측하게 하지 마세요.
2. IMPLEMENTATION_BACKLOG.csv: requirement→function→screen/state→current source/command→
   gap/change→dependency→acceptance→verification timing/evidence. 구현 과제와 현재 status 구별.
   기존 T번호/UC/요구를 연결하되 개수를 완료율로 쓰지 않습니다.
3. SCREEN_SPEC.md와 편집 가능한 state-specific SVG/screens JSON: 전체 화면 inventory,
   실제 1440×900 desktop detailed samples, 구체 합성 표/곡선/3D/선택/값, menu/toolbar/dock,
   click/context/drag/dialog/shortcut, input type/unit/default/range/dependencies, empty/edit/dirty/
   running/fail/cancel/complete 다음 행동, Undo/save/revision/reopen/tool navigation.
   Study 독립 화면과 Evaluation의 같은 owner/editor를 빠뜨리지 마세요.
4. editable .drawio: 주요 전체 작업/정보 구조/도구 데이터 전달/화면 전환/오류·상태·복구.
5. PROTOTYPE_SCENARIOS.md: 대표 end-to-end clickable task scripts와 화면/상태 ID,
   잘못된 행동→수정/취소/실패/복구/저장/재열기. Penpot 원본은 Codex가 실제 tool에서
   작성하고 local export하지만 연결을 만들 때 추측하지 않도록 화면/flow data를 주세요.
   기존 Qt spike의 수정이 필요하면 planning-only .ui/Qt patch를 의미 있는 단위로 작성하세요.
6. VERIFICATION_PLAN.md: 각 기능의 purpose/timing/prerequisite/completion/reference reuse,
   planning·UI interaction·implementation regression·numerical reference·final integration 구별.
7. DECISIONS.md: 주요 대안/선택 이유·cost/license·미결 사용자 선택(이미 결정한 내용 제외),
   current limitations와 Astra finding별 반영표. 내부 사고 과정의 장문은 필요 없습니다.

Material은 두 CSV의 열 순서/단위 차이→mapping/quantity conversion→strain/stress measure/
횡조건→표–곡선 구간/mask→train/holdout→fit/residual/weights→실패·부분 후보→adoption target
revision conflict→save→cold reopen을 완성하세요. Data/Material/Plan owner는 유지하고
사용자를 창/대화상자 왕복에 가두지 마세요. 접촉은 사용자 face sets→law/friction/gap/normal→
capability/preflight→run→pressure/force/gap/penetration/slip/result time→save→geometry split/normal
flip→rebind/cancel까지 명세합니다. 기존 bounded benchmark를 full user contact로 표시하지 않습니다.

Material+Plan 동시 dirty, cell buffer/owner draft/saved revision, remote client conflict, partial save,
close와 job cancel, native pose preview/design restore, moved dependencies와 changed-content branch,
서로 다른 mesh/coordinate/time/unit comparison의 valid mask도 실제 화면 상태로 설계하세요.
상세 옵션은 context에 배치하고 중요한 상태·오류를 숨기지 않습니다. 설명문 대신 사용자가
다음 조작을 알아볼 수 있는 정보 구조와 시각 표시를 선택하세요.

완료 기준은 개발자가 핵심 조작을 추측하지 않고 구현하고 사용자가 화면/시제품에서 작업
시작·선택·편집·결과·복구·저장/재개를 따라가는 것입니다. 원본·실행 방법은 local로 회수합니다.
실행하지 않은 Qt/native/solver/provider는 미확인이라고 쓰세요. scope가 크므로 산출물은
연결된 whole-product draft를 먼저 완성하고 Codex/Astra finding에 대한 후속 교정을 받습니다.
자료가 실제 없거나 권한/무료 경로가 미확인인 경우 정확히 지적하고 다른 설계 작업은 계속하세요.
