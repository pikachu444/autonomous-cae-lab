---
request: PRO-DESKTOP-DESIGN-20261012-06
linked_spec: SPEC-DESKTOP-001
phase: design-before-implementation
status: reviewable-draft
owned_path: docs/design/20261012-desktop-planning/pro-ux/
auto_run: false
production_implementation: not-started
---

# Existing MoAI SPEC handoff

기존 [SPEC-DESKTOP-001](https://github.com/pikachu444/autonomous-cae-lab/blob/313679843813b63dee44409de5c5abc43c8a373b/.moai/specs/SPEC-DESKTOP-001/spec.md), [plan](https://github.com/pikachu444/autonomous-cae-lab/blob/313679843813b63dee44409de5c5abc43c8a373b/.moai/specs/SPEC-DESKTOP-001/plan.md), [acceptance](https://github.com/pikachu444/autonomous-cae-lab/blob/313679843813b63dee44409de5c5abc43c8a373b/.moai/specs/SPEC-DESKTOP-001/acceptance.md)를 이번 작업에서 실제로 읽고 아래 산출물에 연결했다. 새 SPEC owner, queue, helper project를 만들지 않았다. `.moai` 파일 자체와 CURRENT_STATE는 이번 파일 소유권 밖이므로 수정하지 않았다. MoAI CLI/lint/run이나 모델/provider 전환을 실행했다는 의미가 아니다.

## 산출물과 acceptance 연결

| 기존 acceptance | 이번의 구체적 연결 | 다음 확인 주체/범위 |
|---|---|---|
| AC-D01 | 각 `--tool` 독립 Qt 실행, File/Window, natural filename | Codex Windows 실제 창·파일 연결 |
| AC-D02 | DESIGN의 도구별 입력·조작·판단, D1 FN-01…35 범위 유지 | Pro 교정 + 독립 Astra 설계 검토 |
| AC-D03 | Qt source, screen_states.json, 실제 SVG, Workflows.drawio | 사용자 실제 공학 작업 경로 검토 |
| AC-D04 | required input gate와 셀 이동, precision/partial input 검사 | 현재 Qt 검사; 승인 뒤 owner/adapter gate 통합 |
| AC-D05 | 정확한 old result/geometry, 새 attempt, owner별 candidate Apply/Save | 상태 검사 및 cold reopen, 이후 기존 Core 연결 |
| AC-D06 | Runner request/terminal cancel·reconnect·late result | 현재 fixture interaction, 이후 JobManager/remote 통합 |
| AC-D07 | partial save retry, Material r19/CAL original repair | 현재 state/Qt, 이후 실제 native/managed file 저장 |
| AC-D08 | UNKNOWN/NOT_RELEASED/F05 원값 그대로 | 실제 수치/qualification은 해당 기능 구현 뒤 |
| AC-D09 | 기존 무료 Qt, 무 API 호출, OAuth/local 미확인 상태 | 실제 free route/model 권한은 별도 검증 |
| AC-D10 | Pro 주작성, Astra/Sol/Luna 역할, REVIEW 기록 | 사용자 검토 후 별도 개발 시작 지시 |
| AC-D11 | implementation_map.csv의 기존 74 task ID·source command·dependency·acceptance와 새 화면 연결 | Codex가 승인된 작업만 기존 SPEC/task 인계에 반영 |

## 승인 뒤 개발 단위

D1의 `implementation_prerequisites`와 `runtime_prerequisites`를 분리해 유지한다. 공유 Core/command 연결 담당은 하나이며 각 UI는 기존 Domain owner를 사용한다.

1. **공통 편집과 독립 도구** — 기존 FN-01/FN-02와 Data·CAD·PDE·Expert의 창/저장/정밀 수치 delegate를 함께 통합한다. prototype_state.py를 제품 Core로 복사하지 않는다.
2. **형상에서 결과까지** — FN-10…17/FN-25/FN-27…28의 FreeCAD/Simulation/JobManager/ParaView 경계를 연결한다. 해당 native 설치와 실제 domain 입력만 runtime 조건이다.
3. **연구 정의와 판단** — FN-20…24/FN-29…30의 기존 Numerical/Discussion/Study command에 도구별 표·결과 선택·후속 근거를 연결한다. Plan/Study 자동 adopt를 만들지 않는다.
4. **병행 domain과 coupling** — FN-03…09/FN-18…19의 Data/Material/PDE/Evaluation 확장과 verification을 해당 기능 단위로 수행한다. Material 완료를 전체 선행으로 두지 않는다.
5. **remote/native/device/report와 공통 surface** — FN-26/FN-31…35의 기존 source seam과 D1 상세 acceptance를 따른다. 미지원 backend/장비/출력 기능은 계획 범위에 남는다.

현재 인계 상태는 **planning artifacts ready for user review**다. 실제 Windows·native·solver/provider·수치 acceptance를 완료로 바꾸지 않는다. 사용자의 개발 시작 지시 전에는 이 순서를 자동 실행하지 않는다.
