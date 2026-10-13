---
id: SPEC-IMPACT-001
title: "Independent impact and damage research"
version: "0.1.0"
status: planned
created: 2026-10-14
updated: 2026-10-14
author: "Codex scope; actual ChatGPT Pro implementation"
priority: "P1 High"
phase: plan
module: "Simulation, Material, Pre, Post"
lifecycle: spec-anchored
tier: L
tags: "explicit, damage, desktop, native"
---

# 충격·낙하와 손상 연구

원본 범위는 [전체 명세 FN-16/17](../../../docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md)와
구현표 D8의 네 작업이다. 현재 담당과 다음 행동은 [CURRENT_STATE](../../../CURRENT_STATE.md)에만
기록한다. 이 명세를 추가했다고 구현이나 Pro 배정이 완료된 것은 아니다.

## 필요한 사용자 동작

- REQ-IMPACT-001-001: When preparing an explicit analysis, the native Pre and
  existing Simulation document shall expose bodies, material assignments, contact,
  consistent length/mass/time units, COM and orientation. Measured velocity and
  angular velocity shall remain distinct from ideal height/gravity-derived speed.
  The selected input mode shall not silently apply both initializations.
- REQ-IMPACT-001-002: When exporting or running, the adapter shall preserve the
  actual model and includes, report unsupported cards or missing assignments and
  block affected execution. End time, output timing, time-step/CFL and mass scaling
  shall be visible where supported. Editing and saving shall not require a solver.
- REQ-IMPACT-001-003: When reading an actual run, Runner and Post shall expose the
  physical clock, time step, added mass and available energy/force/acceleration
  channels with units and frames. Failure times, elements and partial output shall
  remain readable. Filtering shall be a separate, retained operation.
- REQ-IMPACT-001-004: When editing damage or interface behavior, the user shall
  distinguish bulk plasticity, traction-separation, onset/evolution, mode mix and
  compression/reclosure contact. The selected law and adapter shall declare the
  supported topology, units and outputs instead of silently omitting unsupported
  behavior. Editing a law is not proof of solver export support.
- REQ-IMPACT-001-005: When reviewing damage results, the product shall preserve
  original mesh identity, active masks, failure events and bulk/interface energy
  histories. Convergence failure shall remain distinct from physical failure.
- REQ-IMPACT-001-006: When reporting cyclic damage or life, the product shall use
  an explicitly supported cyclic law, accumulation rule and parameter/test range.
  A single cycle shall not imply fatigue life. Missing physical requirements or
  validation shall remain UNKNOWN without blocking unrelated document editing.
- REQ-IMPACT-001-007: Each tool shall independently save/reopen its existing
  document and selected result, and transfer that exact selection to the existing
  Runner, Post, Numerical or Study path without starting a hidden calculation.

## 이번 소스 조사에서 확인한 재사용과 차이

`SimulationDocuments`와 `SimulationWindow(PDEWindow)`는 등록 adapter의 정의·저장·
결과를 이미 소유한다. `explicit.openradioss`는 `plugins/explicit_dynamics/reference.py`의
제한된 강체 정육면체/탄성 정지장치와 선택 가속도 이력을 사용한다.
`caelab/adapters/openradioss.py`의 native deck/실행, `openradioss_history.py`의
실제 이력 읽기를 재사용한다. 이 기록은 일반 조립 모델의 회전·접촉·복합재·손상 지원이 아니다.

현재 Simulation catalogue에는 cohesive/fatigue 전용 adapter가 없다. 손상 입력란만
추가해 FN-17을 완료하지 않는다. 같은 owner 안에서 실제 Domain/Adapter, native export와
result reader를 확장한다. 이미 있는 Material 법칙과 native Pre 할당, Post 선택을 연결하며
새 owner·scheduler를 만들지 않는다. D7의 구성식 등록과 공통 PDEWindow 변경은 해당
인도본을 통합한 뒤 재사용한다.

기존 OpenRadioss/OpenCourant의 실패 결과·원 수치 기준은 보존한다. 이전 충돌 기준의
실패를 지우거나 기존 허용 범위만 늘려 일반 모델 지원으로 표시하지 않는다. 그렇다고 그
기준 전체 재실행을 모든 편집기 개발의 선행조건으로 두지도 않는다. 새로 지원한 기능에
필요한 작은 확인을 고르고 넓은 수치·물리 수용은 관련 구현 뒤에 수행한다.

무료 구현과 native 도구를 사용한다. LS-OPT나 유료 전처리기를 필수 경로로 추가하지 않는다.
기존 설치 유무는 실행 전 해당 환경에서 확인하며 소스의 pin만으로 설치됐다고 가정하지 않는다.
완료 조건은 [acceptance.md](acceptance.md)에 연결한다.
