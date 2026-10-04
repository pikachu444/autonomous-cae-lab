"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const presentation = require("../apps/lab/static/result-presentation.js");

test("displayed inputs use the captured mapping, not a guessed parameter ID or current registry", () => {
  const record = { result: { input_parameters: { "P-width": 80, "P-custom": 10, "P-unmapped": 4 } },
    registry_snapshot: { entries: [
      { parameter_id: "P-width", native: { path: "specimen.length" }, unit: "mm" },
      { parameter_id: "P-custom", display_name: "사용자가 정한 변수", unit: "N" },
    ] } };
  const before = JSON.stringify(record);
  assert.deepEqual(presentation.inputs(record), [
    { id: "P-width", name: "시편 길이", value: 80, unit: "mm" },
    { id: "P-custom", name: "사용자가 정한 변수", value: 10, unit: "N" },
    { id: "P-unmapped", name: "입력 3", value: 4, unit: null },
  ]);
  assert.equal(JSON.stringify(record), before);
});

test("inspection counts preserve failed, unknown, warning and unrecognized checks without promoting release", () => {
  const result = { status: "COMPLETED_REVIEW_REQUIRED", decision: "NOT_RELEASED", solver_status: "NOT_RUN",
    metrics: { displacement: { value: -0, unit: "mm", valid: false } },
    validations: [{ type: "static_strength", status: "UNKNOWN", blocking: true },
      { type: "mesh", status: "FAIL" }, { status: "PASS" }, { status: "WARNING" }, { status: "NEW_CODE" }] };
  const before = JSON.stringify(result), report = presentation.checks(result);
  assert.deepEqual(report.counts, { PASS: 1, FAIL: 1, UNKNOWN: 1, WARNING: 1, other: 1 });
  assert.equal(report.total, 5); assert.equal(report.unresolved.length, 4);
  assert.deepEqual(report.unresolved.map(item => item.status), ["UNKNOWN", "FAIL", "WARNING", "NEW_CODE"]);
  assert.equal(result.decision, "NOT_RELEASED"); assert.equal(result.metrics.displacement.valid, false);
  assert(Object.is(result.metrics.displacement.value, -0)); assert.equal(JSON.stringify(result), before);
});

test("friendly face captions retain original face identity without treating display IDs as native IDs", () => {
  const face = { component_id: "printed_support_right", type: "PLANE", id: 98,
    catalog_face_id: "printed_support_right:face:7:" + "c".repeat(64) };
  const before = JSON.stringify(face);
  assert.equal(presentation.faceDescription(face), "오른쪽 받침 · 평면 · 원본 면 7");
  assert.equal(presentation.faceDescription({ id: 98, type: "PLANE" }), "선택한 부품 · 평면");
  assert.equal(JSON.stringify(face), before);
  assert(!presentation.faceDescription(face).includes("98"));
});

test("unknown names and prototype properties have neutral display labels", () => {
  assert.equal(presentation.title("__proto__"), "해석·모델 실험");
  assert.equal(presentation.validationName("new_physics", 2), "확인 항목 3");
  assert.equal(presentation.metricName("new_response", 1), "결과값 2");
  assert.equal(presentation.title("fixture.assembly"), "굽힘 시험 치구");
});
