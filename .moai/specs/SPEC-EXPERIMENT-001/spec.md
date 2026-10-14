---
id: SPEC-EXPERIMENT-001
title: "Measurement calibration and research reporting"
version: "0.1.0"
status: in-progress
created: 2026-10-14
updated: 2026-10-14
author: "Codex scope; actual ChatGPT Pro implementation"
priority: "P1 High"
module: "Data, Numerical, Study, Report"
lifecycle: spec-anchored
tier: L
tags: "measurement, calibration, report, desktop"
---

# 측정 자료를 보정하고 연구 보고서로 연결하기

이 명세는 [전체 제품 명세](../../../docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md)의
FN-05, FN-32, FN-35와 구현표 D9 네 작업을 실제 구현에 연결한다. 현재 배정은
[CURRENT_STATE](../../../CURRENT_STATE.md)만 따른다. Pro D8 작성 중에 준비하는 인계이며
이 문서 작성이나 시제품의 화면 존재가 D9 제품 구현 완료를 뜻하지 않는다.

## 사용자 작업

시험 파일 열기 → 채널·단위·시편과 교정 자료 지정 → 원값과 보정값 비교 →
해석의 같은 관측량과 비교 → 구별 가능한 계수와 다음 시험 판단 → 보고서 편집·
내보내기 → 다시 열어 같은 원자료와 판단 확인. 장비 연결 없이 이 경로를 사용할 수
있어야 한다. 보고서는 Study 또는 독립 결과에서 시작하며 문헌만으로도 작성한다.

## 요구

- REQ-EXPERIMENT-001-001: When importing measured files, the Data tool shall retain
  raw samples and permit explicit channel, unit, specimen, fixture, instrument,
  calibration and observation-time assignments without requiring a device driver,
  AI account, CAD application or WSL. Missing information shall remain unknown.
- REQ-EXPERIMENT-001-002: When applying calibration, the Data tool shall retain
  the selected calibration source, coefficient units, offset, valid input range,
  validity period and supplied uncertainty information with the processing revision.
  The tool shall show raw and corrected samples together, identify saturation and
  out-of-range samples, and preserve editable invalid drafts and previous results.
  Raw calibration range and sensor saturation shall be distinct, with explicit
  input-zero and output-offset units and application order.
- REQ-EXPERIMENT-001-003: When comparing measurement and prediction, the comparison
  shall use an explicitly selected physical quantity, unit, gauge definition,
  direction, coordinate system and time alignment. Actuator travel shall not be
  silently treated as specimen strain, and missing calibration shall block only
  the dependent conversion while leaving the original data readable.
- REQ-EXPERIMENT-001-004: When interpreting an inverse study, the Numerical and
  Study tools shall distinguish fitted, fixed and unidentified parameters, expose
  supported sensitivity/correlation diagnostics and record the user's next test
  with its intended discrimination. Missing observations shall not produce invented
  uncertainty or a claim that a material and fixture cause have been distinguished.
  Fitting and holdout observations shall remain separate by original source
  rows, and optimization success alone shall not establish identifiability.
  Quality/calibration masks, fit/holdout membership and display-only hiding shall
  remain separate selections.
- REQ-EXPERIMENT-001-005: When creating a research report, the desktop tools shall
  allow source selection, section inclusion, reordering and editing, page preview,
  local export and reopening. Saved reports shall retain the exact selected values,
  units, curves, field locations, time points, processing descriptions and judgments.
  Report creation shall not execute a solver or require an AI provider.
  Preview, export and reopening shall use the saved selections applied to the
  report, not follow later source-window changes. Replacing edited sections from
  a newer Study shall require explicit application with Cancel and Undo support.
- REQ-EXPERIMENT-001-006: When a report source is missing or an export fails, the
  report shall identify the affected section and preserve the existing draft and
  previous export. The report shall distinguish program completion, numerical
  validation and engineering approval, preserving failed values and unknown checks.
  It shall never replace a missing source with a later result automatically.
- REQ-EXPERIMENT-001-007: When configuring acquisition, the tools shall save channel
  roles, units, calibration, sample-rate, duration and timestamp alignment as a
  reusable setup. Where no identified authorized device and supported driver exist,
  actual acquisition and physical control shall remain unavailable while recorded
  file import and calibration remain usable. Requested settings shall not fabricate
  live samples or physical stop acknowledgments.
- REQ-EXPERIMENT-001-008: When the user saves, reopens or transfers a measurement,
  study or report, each tool shall preserve the selected source revision and result
  through the existing document owners and commands. A new calibration shall create
  a new processing revision and identify affected comparisons and plans without
  rewriting previous observations or judgments.

제공된 불확실성은 값·단위와 표준/확장 구분, 포함인자 k, 상관 정보 중 제공된 것을
보존한다. 미제공 정보를 0·독립·피팅 잔차로 대신하지 않는다. 미지원 전파 계산은
그 계산의 한계로 표시하며 지원되는 교정값 계산 전체를 막지 않는다.

## 구현 경계

기존 Data, Numerical, Study와 결과 참조를 재사용한다. 실제 Qt 창에는 표·그래프·
보고서 페이지와 문맥별 조작을 배치한다. 내부 식별자·해시·JSON을 주 작업 화면으로
노출하거나 설명문과 입력 폼만으로 작업을 대신하지 않는다. 추가 비용은 0원이며,
기존 무료 Qt 출력·로컬 파일 경로를 우선한다. 웹 화면을 제품 주 화면으로 만들지 않는다.

특정 장비 모델·프로토콜·물리 중지 규약은 제공되지 않았다. 이 외부 조건을 미결정으로
남기되 파일 처리, 수집 설정 저장, 보고서 개발을 멈추지 않는다. 실제 장비 기능은
요구 범위에 유지하며 모의 응답만으로 완료 처리하지 않는다. 공통 Job 취소를 장비의
비상 정지로 간주하지 않는다. 새로운 scheduler나 검증 승인 엔진을 만들지 않는다.

원 실패값과 허용치를 보존한다. 과거 F05 등 특정 예제를 모든 보고서의 기본 내용이나
전체 개발 선행조건으로 넣지 않는다. 사용자가 선택한 자료와 이번 판단만 보고서에 넣는다.

현재 기술 기준은 [ARCHITECTURE](../../../ARCHITECTURE.md)와 프로젝트 문서에 있다.
`.moai/project/tech.md`가 없으므로 존재한다고 가정하거나 중복 기준 파일을 만들지 않는다.
구현 순서는 [plan.md](plan.md), 사용자 완료 조건은 [acceptance.md](acceptance.md)를 따른다.

## Out of Scope

- 새 유료 서비스와 독립적인 공통 저장·작업 실행 프레임워크를 도입하지 않는다.
- 장비 미제공 상태에서 임의 드라이버나 가짜 물리 측정을 만들지 않는다. 실제 장비
  연동 요구는 FN-35-01에 유지하며 외부 조건이 제공된 뒤 구현·인수한다.
