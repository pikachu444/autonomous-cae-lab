---
id: SPEC-IMPACT-001
title: "Independent impact and damage research"
version: "0.1.0"
status: in_progress
created: 2026-10-14
updated: 2026-10-14
author: "Codex scope; actual ChatGPT Pro implementation"
priority: "P1 High"
phase: run
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
- REQ-IMPACT-001-008: When WSL is unavailable, the Windows tools shall still open,
  edit, save and read retained results. Explicit analysis shall have a Windows
  native runtime path, with platform-specific executable/library discovery and
  cancellation. Missing runtime dependencies shall block only affected runs.
  The application shall not silently replace an active service or move its store.

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

## 사용자 모델 연결의 구현 경로

Sol과 Astra의 소스 조사 및 직접 토론 결과, 기존 FreeCAD FEM의 mesh/sets/재료와
접촉 face 추출을 재사용하고 별도 명시적 충격 정의를 거쳐 변환한다. 기존 static
freeze의 허용 카드에는 density가 없으므로 static deck 자체를 동적 입력으로 간주하지
않는다. 일반 모델용 adapter와 결과 reader를 추가하며 기존 강체 예제의 엄격한
topology·단위·회전 제한은 유지한다.

우선 검토한 무료 변환기는 [OpenCourant Tools의 INP2RAD](https://github.com/OpenCourant/Tools/blob/beaf8a17c880242bb7ad43325a20bd589dc0f533/input_converters/inp2rad/inp2rad/inp2rad.py)다.
검토 소스 `beaf8a17c880242bb7ad43325a20bd589dc0f533`의 MIT 허가문을 재배포물에
포함한다. 실제 설치·실행 수용은 아직 하지 않았다. Qt 내부로 tkinter와 전역 상태를
가져오지 않고 기존 소유 subprocess 경로에서 호출하는 안을 우선한다. converter가
지원하지 않는 카드의 직접 작성은 해당 차이를 확인한 뒤 한정한다.

변환 출력의 Mg/mm/s를 기존 kg/m/s와 혼동하지 않는다. 원 mesh/part/material/set,
밀도와 총질량·COM·관성, 초기 자세·속도·각속도, 시간 제어를 전후 대조한다. 누락 시
converter가 넣는 기본 시간 간격과 종료 시간을 사용자가 정한 조건으로 채택하지 않는다.
원 INP/includes와 합쳐진 변환 deck을 함께 보존하고 카드별 지원 여부를 표시한다.

높이 모드는 출발 위치에서 v=0과 중력을 적분하는 경우와 충돌 직전 위치에 유도 속도를
주는 경우를 구별한다. 같은 낙하 구간을 두 번 적용하지 않되 중력 on/off만으로 모드를
판별하지 않는다. 회전 초기값은 COM·기준계와 일관된 절점 속도로 연결한다.

공식 ANIM→VTK 변환 자산을 기존 ParaView 결과 등록에 연결하는 경로도 재사용한다.
실제 시각·절점/요소·배열 단위·삭제 상태를 보존해야 하며 H3D를 ANIM처럼 읽지 않는다.
CAD 없이 원 Radioss 입력 묶음을 여는 독립 경로도 유지한다. converter의 cohesive나
손상 시작 지원 목록만으로 혼합 모드·재닫힘·반복 손상·피로 수명을 완료하지 않는다.

2026-10-14 사용자 지시에 따라 WSL 없는 Windows 실행도 구현 대상으로 둔다.
[OpenCourant 20261011 배포](https://github.com/OpenCourant/OpenCourant/releases/tag/latest-20261011)는
Windows x86-64 패키지와 필요한 Intel runtime을 제공한다. 현재 로컬 WSL 설치를 유일한
계산 경로로 고정하지 않고 Windows Starter/Engine 및 결과 변환기 연결을 구현한다.
AGPL-3.0과 번들 reader/H3D/Intel runtime의 개별 허가문을 확인해 유지한다.
공식 배포 존재 확인과 우리 adapter의 Windows 실행 완료는 구별한다. 아직 후자는 미완료다.
