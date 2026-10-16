---
id: SPEC-PREFE-001
title: "전처리·구조해석 15개 작업의 구현 범위와 완료 조건"
version: "0.1.0"
status: in-progress
created: 2026-10-14
updated: 2026-10-14
author: "Codex 작업 구체화, 기존 Pro 제품 명세 기반"
priority: P1
phase: "전처리 사용자 모델 인도"
module: "apps/desktop_pre, caelab/adapters, apps/research/runner_window.py"
lifecycle: spec-anchored
tags: "freecad, fem, contact, assembly, delivery"
tier: L
---

## HISTORY

2026-10-14: 사용자가 MoAI를 이용해 추상적인 전처리·해석 15항목을 구현 작업과
달성 조건으로 나누라고 지시했다. 기존 Pro의 FN-10–15/25를 대체하지 않고 아래처럼
배정 가능한 단위로 구체화한다. 현재 상태와 담당은 [CURRENT_STATE](../../../CURRENT_STATE.md)가
유일한 원본이며 이 문서 작성은 제품 구현 완료가 아니다.

## 범위와 판정

대상은 기존 74작업 중 D2의 15행이다. 충격·손상(D8), 후처리 전체(D4), PDE·재료·최적화는
각 기존 명세를 유지한다. 이 명세가 필요한 연결을 가리켜도 다른 도구 전체를 재구현하지 않는다.
기존 [전체 제품 명세](../../../docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md),
[접촉 명세](../SPEC-CONTACT-001/spec.md), [CAD 후보 명세](../SPEC-CAD-NUMERICAL-001/spec.md)를
재사용한다. 15개는 상위 기능이지 15개의 동일 크기 개발 일이 아니다.

현재 표의 완료7·부분6·확인보류2는 `1820cf1`의 기록이다. 상위 완료 표시는 그때 지원한
범위에 한정되며 아래 추가 개발 조건을 충족했다고 소급 표시하지 않는다. 새 조건과 기존
완료 근거가 어긋나면 CURRENT_STATE에 그 차이를 남긴다.

## 사용자 요구 — 기존 15행과 일대일 대응

- REQ-PREFE-001-001: WHEN users register or edit CAD variables, the Pre tool SHALL preserve the native target, unit and dependency, and require explicit repair for deleted or ambiguous targets.
- REQ-PREFE-001-002: WHEN invalid inputs, recompute errors or no observed effect are detected, the Pre tool SHALL distinguish these states, preserve editable drafts and Undo, and block only affected execution.
- REQ-PREFE-001-003: WHEN users edit assembly joints and drives, the motion tool SHALL support the M1-M4 workflows with exact occurrences, retained design poses and paths.
- REQ-PREFE-001-004: WHILE motion preview is active, the Pre tool SHALL distinguish pause, stop and adopt, verify restoration before save or FEM transition, and report non-cancellable native phases accurately.
- REQ-PREFE-001-005: WHEN users assign materials, loads and constraints, the Pre tool SHALL align table and native selection, preserve quantity, direction and units, and export the exact selected sets.
- REQ-PREFE-001-006: WHERE an E1-E6 representation is selected, the Pre tool SHALL preserve its section, orientation, layers, conditions and connection data, and block unsupported export without deleting the draft.
- REQ-PREFE-001-007: WHEN users refine selected poor-quality elements, the Pre tool SHALL connect native selection, isolation, local sizing and remeshing and compare the same quality definitions and checked ranges.
- REQ-PREFE-001-008: WHEN meshing fails, is cancelled or returns after geometry changes, the Pre tool SHALL retain the old mesh, distinguish cancellation requests from termination and prevent stale application.
- REQ-PREFE-001-009: WHEN users configure C1-C6 contact or boundary behavior, the Pre tool SHALL preserve the distinct law, region and step semantics and generate the actual selected solver formulation.
- REQ-PREFE-001-010: WHEN users inspect a contact pair and increment, the result tools SHALL expose R1-R2 fields with actual association, units and sign and distinguish missing output from zero.
- REQ-PREFE-001-011: WHEN contact references become invalid, the Pre tool SHALL provide old/new comparison and explicit one-to-many preview, apply and cancel without making the old mesh current.
- REQ-PREFE-001-012: WHEN users configure nonlinear analysis, the domain editors SHALL preserve NS1/NS2/N3 material history, initial conditions, damping, mixed-step state and numerical controls and reopen failed settings.
- REQ-PREFE-001-013: WHERE an NS1/NS2/S2 solver route is selected, the adapter SHALL execute the user's actual model through the existing job owner and retain increments and partial results.
- REQ-PREFE-001-014: WHEN users select a Runner attempt, Runner SHALL open that attempt's input, logs, result and source settings without resubmission.
- REQ-PREFE-001-015: WHEN cancellation, retry or connection loss occurs, Runner SHALL distinguish observed process and cleanup state, preserve earlier results and separate same-input retries from changed-input runs.

## Acceptance Criteria

- AC-01: (maps REQ-PREFE-001-001) — [acceptance.md의 AC-01](acceptance.md)의 시작 자료·사용자 조작·관측 결과를 충족한다.
- AC-02: (maps REQ-PREFE-001-002) — [acceptance.md의 AC-02](acceptance.md)의 시작 자료·사용자 조작·관측 결과를 충족한다.
- AC-03: (maps REQ-PREFE-001-003) — [acceptance.md의 AC-03](acceptance.md)의 시작 자료·사용자 조작·관측 결과를 충족한다.
- AC-04: (maps REQ-PREFE-001-004) — [acceptance.md의 AC-04](acceptance.md)의 시작 자료·사용자 조작·관측 결과를 충족한다.
- AC-05: (maps REQ-PREFE-001-005) — [acceptance.md의 AC-05](acceptance.md)의 시작 자료·사용자 조작·관측 결과를 충족한다.
- AC-06: (maps REQ-PREFE-001-006) — [acceptance.md의 AC-06](acceptance.md)의 시작 자료·사용자 조작·관측 결과를 충족한다.
- AC-07: (maps REQ-PREFE-001-007) — [acceptance.md의 AC-07](acceptance.md)의 시작 자료·사용자 조작·관측 결과를 충족한다.
- AC-08: (maps REQ-PREFE-001-008) — [acceptance.md의 AC-08](acceptance.md)의 시작 자료·사용자 조작·관측 결과를 충족한다.
- AC-09: (maps REQ-PREFE-001-009) — [acceptance.md의 AC-09](acceptance.md)의 시작 자료·사용자 조작·관측 결과를 충족한다.
- AC-10: (maps REQ-PREFE-001-010) — [acceptance.md의 AC-10](acceptance.md)의 시작 자료·사용자 조작·관측 결과를 충족한다.
- AC-11: (maps REQ-PREFE-001-011) — [acceptance.md의 AC-11](acceptance.md)의 시작 자료·사용자 조작·관측 결과를 충족한다.
- AC-12: (maps REQ-PREFE-001-012) — [acceptance.md의 AC-12](acceptance.md)의 시작 자료·사용자 조작·관측 결과를 충족한다.
- AC-13: (maps REQ-PREFE-001-013) — [acceptance.md의 AC-13](acceptance.md)의 시작 자료·사용자 조작·관측 결과를 충족한다.
- AC-14: (maps REQ-PREFE-001-014) — [acceptance.md의 AC-14](acceptance.md)의 시작 자료·사용자 조작·관측 결과를 충족한다.
- AC-15: (maps REQ-PREFE-001-015) — [acceptance.md의 AC-15](acceptance.md)의 시작 자료·사용자 조작·관측 결과를 충족한다.

### Out of Scope — excluded work

- CAD kernel, mesher, job scheduler 또는 결과 저장소를 새로 만드는 작업.
- 다른 도구 전체나 과거 솔버 캠페인을 이 15항목의 선행조건으로 재실행하는 작업.
- 유료 solver/API 도입 또는 프로그램 실행 성공을 공학적 승인으로 처리하는 작업.

## 공통 완료 기준

각 배정은 plan.md의 구현 대상과 acceptance.md의 해당 경로를 함께 인도한다.
메뉴/폼만 존재하거나 미지원 표시만 추가한 것은 물리 기능의 완료가 아니다.
실제 사용 가능한 무료 구현 경로가 아직 없으면 해당 작업은 미완료로 남긴다.
일반 화면에는 한국어 작업명·단위·오류 해결 행동을 표시하고 내부 ID/해시는 상세 정보로 둔다.
독립 편집·저장·보존 결과 열기는 AI/유료 API/WSL을 요구하지 않는다.
실행 환경 없는 솔버는 해당 계산만 막고 설치 가능한 플랫폼을 알려준다.
소프트웨어 인도와 물리 검증·공학적 승인을 구분하며 기존 수치 기준을 낮추지 않는다.
