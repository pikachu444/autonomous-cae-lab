---
id: SPEC-RESEARCH-003
title: "Independent constitutive, PDE and coupled research"
version: "0.1.0"
status: in-progress
created: 2026-10-14
updated: 2026-10-14
author: "Codex scope; actual ChatGPT Pro implementation"
priority: "P1 High"
phase: implementation
module: "Material, PDE, Evaluation"
lifecycle: spec-anchored
tier: L
tags: "desktop, constitutive, pde, coupling"
---

# 구성식, PDE, 연성 연구의 독립 사용과 연결

범위는 [전체 명세 FN-08/18/19](../../../docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md)와
[구현표 D7의 7개 작업](../../../docs/design/20261012-desktop-planning/pro-ux/implementation_map.csv)다.
다음 Pro 구현을 준비하는 명세이며, 배정·구현·실행 상태는
[CURRENT_STATE](../../../CURRENT_STATE.md)에서 관리한다. D6의 작성 파일을 동시에 변경하지 않는다.

## 요구

- REQ-RESEARCH-003-001: When a retained constitutive run is opened, Material shall
  let the user select an increment and inspect the actual stress, strain, available
  state, residual and tangent components with their measures, frame and units.
  Missing output shall remain unavailable rather than be synthesized.
- REQ-RESEARCH-003-002: When a user law is registered or built, the existing domain
  and adapter shall retain its source/build/interface and supported tangent pairs.
  Unsupported FE export shall be blocked without preventing draft editing.
- REQ-RESEARCH-003-003: When a PDE field, equation, region, boundary or initial
  condition is selected, its relevant editor and declared units shall be shown.
  Expression diagnostics shall identify the affected input. Checking an expression
  shall not execute a solver. Supported results shall expose their actual field,
  error definition, mesh level and reference for comparison.
- REQ-RESEARCH-003-004: The product shall retain general dimensioned weak-form and
  ODE requirements as implementation work. Executable support shall use a distinct
  declared adapter and reference coverage; widening the old bounded validator or
  relabeling a dimensionless result shall not count as implementation.
- REQ-RESEARCH-003-005: When an Evaluation transfer is selected, the user shall see
  its actual producer field, receiver input, units, mesh/time alignment and required
  mask, separately from static port compatibility. Missing required data shall
  prevent the receiver solve. Absolute temperature, temperature difference and
  structural reference temperature shall retain their physical meanings.
- REQ-RESEARCH-003-006: When a coupled run fails, is cancelled or does not converge,
  the view shall retain completed attempts and show the affected stage, residual,
  tolerance and available retry/reuse action. Process success shall not imply
  convergence. Unsupported checkpoint continuation shall not appear available.
- REQ-RESEARCH-003-007: Each tool shall edit, save and reopen its existing document
  independently. Post, Runner, Numerical and Expert links shall use the selected
  saved definition/result. Opening or transferring a result shall not submit a run.
  Invalid drafts, pending edits, Undo and conflict recovery shall remain usable.
- REQ-RESEARCH-003-008: Native Qt views shall prioritize fields, curves and tables,
  with readable Korean labels and consistent focus, spacing and selection. Technical
  identifiers shall be available in details. All new dependencies shall have a
  verified free implementation and distributable license path.

## 구현 인계

기존 MaterialDocuments, PDEDocuments, EvaluationDocuments, JobManager와 native
adapters를 확장한다. 별도 owner·scheduler·범용 새 파일 형식을 만들지 않는다.
조사 원본은 `runs/product-development/20261014/pde-coupling-workflows/reuse-map.md`다.
NativeMaterialWindow의 PDEWindow 상속과 D6의 평가기 참조 변경은 구현 전에 다시 맞춘다.
Windows 주 Python에 native FEniCSx/MGIS가 없다는 사실을 모든 연결 환경의 부재로
확대하지 않는다. 관련 실행 환경은 필요 기능에 한해 조사한다.

완료 조건과 최소 확인은 [acceptance.md](acceptance.md)를 따른다. 구성식/일반식/
mapping의 추가 capability를 화면 inspector만으로 완료 처리하지 않는다.
