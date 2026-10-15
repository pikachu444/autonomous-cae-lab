---
id: SPEC-NUMERICAL-002
title: "Independent numerical research and connected result use"
version: "0.1.0"
status: in-progress
created: 2026-10-14
updated: 2026-10-16
author: "Actual Pro product design and original implementation; Sol scoped extensions; Codex integration"
priority: "P1 High"
phase: implementation
module: "Numerical research"
lifecycle: spec-anchored
tier: L
tags: "numerical, desktop, research"
---

# 수치 연구의 방법별 작업 완성

범위 원본은 [전체 명세 FN-20~24](../../../docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md)와
[구현표의 D6 11개 항목](../../../docs/design/20261012-desktop-planning/pro-ux/implementation_map.csv)이다.
기존 SPEC-NUMERICAL-001의 DOE/최적화 표와 토론 반환을 재사용한다. 현재 배정과 실행
상태는 [CURRENT_STATE](../../../CURRENT_STATE.md)만 갱신한다. 전체 요구를 이 SPEC의
첫 구현으로 축소하지 않으며 추가 방법의 미지원 상태도 작업표에 남긴다.

## 요구

- REQ-NUMERICAL-002-001: When the user selects a research method, the Numerical
  window shall offer meaningful variables, responses and method-specific settings
  without requiring raw JSON for its supported primary workflow. Independent entry
  shall not require CAD, Material, AI or a previous originating tool unnecessarily.
- REQ-NUMERICAL-002-002: When an explicit run is requested, the existing Plan owner,
  JobManager and selected evaluator shall execute the saved input with declared units,
  bounds, response meaning, seed and total evaluation budget. Invalid required input
  shall remain editable and block execution with a location-specific explanation.
- REQ-NUMERICAL-002-003: When a case or graph point is selected, the result view shall
  display that retained case, its actual response, failures and constraints. Opening,
  selection and reopening shall not implicitly calculate, train or adopt a result.
- REQ-NUMERICAL-002-004: The UQ view shall retain marginal assumptions and source,
  all attempted/failed samples, and the conditioning of statistics on valid samples.
  Normal tails shall not be silently clipped; correlation shall require a real sampler.
- REQ-NUMERICAL-002-005: The sensitivity view shall distinguish regression influence
  from matched Sobol sampling and analysis. Missing/failed outputs shall not be removed
  to fabricate a complete Sobol design or a successful analysis.
- REQ-NUMERICAL-002-006: The surrogate workflow shall distinguish train/holdout,
  predictions, support limits and actual evaluator confirmation. Reopening a retained
  model shall not trigger hidden training; confirmation shall be a separate evaluation.
- REQ-NUMERICAL-002-007: The optimisation and multiobjective workflow shall preserve
  physical objectives separately from penalties, feasible/infeasible/failed cases,
  objective directions, thresholds and total child evaluation counts. Exact selected
  candidates shall support explicit owner-specific adoption and stale/partial recovery.
- REQ-NUMERICAL-002-008: When cancel or reopen is requested, the tool shall distinguish
  pending cancellation, retained history, supported continuation and a genuinely new run.
  Absent engine checkpoint support shall not be described as resumed execution.
- REQ-NUMERICAL-002-009: The implementation shall reuse existing native Qt components,
  numerical engines, document ownership and tool links at no additional cost. Discrete,
  correlated, gradient and coupled requirements shall have explicit capability and
  implementation status; unsupported methods shall not disable unrelated supported work.

## 책임 범위

Pro owns meaningful method editor/engine connection/result/test/usage implementation.
Codex owns common boundary decisions, local execution, integration and current records.
Astra independently reviews scientific meaning and actual user paths. Small unrelated
UI work has separate ownership; no simultaneous writer changes the same interface.

## Out of Scope

- Unchanged full solver campaigns and replacing native CAD/Post viewers. All D6
  method requirements remain in scope; unavailable paths retain explicit status.
