"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { draft } = require("../apps/lab/static/comparison-research.js");
const hash = (character) => character.repeat(64);

// Small TEST_ONLY HTTP comparison response shapes, not real evidence or qualification.
function scalar(id = "C-scalar", experimentId = "E-alpha", studyId = "S-test") {
  const request = { comparison_id: id, experiment_id: experimentId, purpose: "JIG_FEASIBILITY", hypothesis: "OPAQUE_TEST_ONLY_HYPOTHESIS",
    observation: { name: "TEST_ONLY target", value: 149, unit: "N", source_kind: "SYNTHETIC", source: "TEST_ONLY illustrative input",
      quantity: "force", component: "user-declared scalar", location: "TEST_ONLY location", coordinate_frame: "USER_DECLARED_TEST_FRAME",
      condition: "TEST_ONLY force case", tolerance: 1, conditions: [] }, response: { metric: "test_force" } };
  return { integrity: "VERIFIED", record: { schema_version: "1.0", id, request,
    source: { experiment_id: experimentId, study_id: studyId, result_sha256: hash("a"), proposal_sha256: hash("b"), thread_sha256: hash("c"),
      original_decision: "NOT_RELEASED", execution: { force_N: 150 }, parameters: {}, validation_counts: { PASS: 1, FAIL: 0, UNKNOWN: 7, WARNING: 0 } },
    comparison: { status: "NUMERIC_DIFFERENCE_ONLY", response_value: 150, observed_value: 149, unit: "N", difference: 1, absolute_difference: 1,
      declared_absolute_tolerance: 1, within_declared_tolerance: true, declared_condition_checks: [], condition_bindings_supplied: false,
      scope_alignment: "USER_DECLARED_UNVERIFIED", selection_kind: "SCALAR_METRIC", source_metric: { value: 150, unit: "N", valid: true },
      physical_validation: "UNKNOWN", decision: "NOT_RELEASED", causal_verdict: "NOT_EVALUATED" } } };
}
function history(id = "C-history", experimentId = "E-beta") {
  const row = scalar(id, experimentId), { request, comparison } = row.record;
  row.record.schema_version = "1.1";
  request.observation.unit = comparison.unit = comparison.source_metric.unit = "MPa";
  request.observation.value = comparison.observed_value = -15.5;
  request.observation.axis = { quantity: "time", value: 0.5, unit: "s" };
  request.response = { history_channel: "mgis-stress-xz", sample_index: 1 };
  comparison.response_value = -16; comparison.difference = -0.5; comparison.absolute_difference = 0.5;
  comparison.selection_kind = "EXACT_RECORDED_HISTORY_SAMPLE";
  comparison.source_metric.value = [[0, 0, 0, 0, 0, 0], [-6, 10, 12, -14, -16, -18]];
  comparison.source_channel = { id: "mgis-stress-xz", label: "TEST_ONLY native stress xz", metric: "stress_history", quantity: "stress", component: "xz",
    measure: "infinitesimal Cauchy stress", coordinate_frame: "material Cartesian X/Y/Z", location: "single homogeneous material point", unit: "MPa",
    axis: { quantity: "time", unit: "s", values: [0, 0.5] }, values: [0, -16],
    origin: { kind: "NATIVE", driver: "mgis", artifact: "simulation/native_raw.json", sha256: hash("d"), native_field: "stress_physical_mpa", mapping: "RECORDED_PHYSICAL_COMPONENT" },
    initial_state: { index: 0, kind: "UNPREPARED_INITIAL_CONDITION" } };
  comparison.response_axis = { quantity: "time", value: 0.5, unit: "s" };
  comparison.declared_axis_check = { declared: { ...request.observation.axis }, actual: { ...comparison.response_axis }, matched: true };
  return row;
}
function array(id = "C-array", experimentId = "E-alpha") {
  const row = scalar(id, experimentId), { request, comparison } = row.record;
  request.response = { metric: "test_vector", component: 2 };
  request.observation.value = comparison.observed_value = -100.25;
  comparison.source_metric.value = [-0, 2, -100]; comparison.response_value = -100;
  comparison.selection_kind = "USER_SELECTED_ARRAY_ITEM"; comparison.difference = comparison.absolute_difference = 0.25;
  return row;
}
function nullDifference(comparison, status) {
  comparison.status = status; comparison.difference = comparison.absolute_difference = comparison.within_declared_tolerance = null;
}
function mismatch() {
  const row = scalar("C-condition"), { request, comparison } = row.record;
  const condition = { source: "execution", path: ["force_N"], value: 100, unit: "N" };
  request.observation.conditions = [condition]; comparison.declared_condition_checks = [{ declared: { ...condition, path: condition.path.slice() }, actual: 150, matched: false }];
  comparison.condition_bindings_supplied = true; nullDifference(comparison, "DECLARED_CONDITION_MISMATCH");
  return row;
}
function axisMismatch() {
  const row = history("C-axis"), { request, comparison } = row.record;
  request.observation.axis.value = 0.75; comparison.declared_axis_check.declared.value = 0.75; comparison.declared_axis_check.matched = false;
  nullDifference(comparison, "DECLARED_AXIS_MISMATCH"); return row;
}
function freeze(value) {
  if (value && typeof value === "object") { Object.values(value).forEach(freeze); Object.freeze(value); }
  return value;
}

test("1.0 scalar/array and 1.1 history references retain selection order and distinct source experiment order", () => {
  const rows = [history(), scalar(), array()], question = draft(rows, "S-test");
  assert.deepEqual(Object.keys(question), ["question", "studyId", "comparisonIds", "experimentIds"]);
  assert.deepEqual(question.comparisonIds, ["C-history", "C-scalar", "C-array"]);
  assert.deepEqual(question.experimentIds, ["E-beta", "E-alpha"]); assert.equal(question.studyId, "S-test");
  assert.match(question.question, /비교 기록: C-history, C-scalar, C-array/); assert.match(question.question, /원 실험: E-beta, E-alpha/);
  const single = draft([scalar()], "S-test"); assert.deepEqual(single.comparisonIds, ["C-scalar"]); assert.deepEqual(single.experimentIds, ["E-alpha"]);
});
test("question asks for authoritative summaries and comparison context with retained source and physical limits", () => {
  const question = draft([history(), mismatch()], "S-test").question;
  for (const text of ["저장된 결과 요약", "comparison_context", "가설별", "조건·위치·성분·좌표계·시간축·단위", "SYNTHETIC", "MEASURED_REPORTED", "SPECIFICATION",
    "null", "t=0", "수치 초기 상태", "원본 driver", "참조 체적당 에너지", "UNKNOWN", "USER_DECLARED_UNVERIFIED", "NOT_RELEASED", "NOT_EVALUATED",
    "다음 실험", "필요한 측정·입력 자료", "새 계산이나 최적화 없이"]) assert.equal(question.includes(text), true, text);
  assert.equal(question.includes("OPAQUE_TEST_ONLY_HYPOTHESIS"), false);
  assert.equal(question.includes("TEST_ONLY illustrative input"), false); assert.equal(question.includes("stress_physical_mpa"), false);
  assert.equal(question.includes(JSON.stringify(history().record.comparison.source_metric.value)), false);
  assert.equal(question.includes("149"), false);
});
test("physical UNKNOWN and condition/axis mismatch null values remain accepted and untouched", () => {
  const rows = [mismatch(), axisMismatch()], originals = structuredClone(rows);
  assert.deepEqual(draft(freeze(rows), "S-test").comparisonIds, ["C-condition", "C-axis"]);
  assert.deepEqual(rows, originals);
  rows.forEach((row) => {
    const comparison = row.record.comparison;
    assert.equal(comparison.difference, null); assert.equal(comparison.absolute_difference, null); assert.equal(comparison.within_declared_tolerance, null);
    assert.equal(comparison.physical_validation, "UNKNOWN"); assert.equal(comparison.decision, "NOT_RELEASED");
  });
});
test("input records are deeply immutable and returned reference arrays do not alias them", () => {
  const rows = [scalar(), history()], original = structuredClone(rows); freeze(rows);
  const result = draft(rows, "S-test"); result.comparisonIds[0] = "C-edited"; result.experimentIds.push("E-edited");
  assert.deepEqual(rows, original); assert.equal(rows[0].record.request.observation.source_kind, "SYNTHETIC");
});
test("UNKNOWN integrity, duplicates and cross-study selections refuse the entire list instead of dropping rows", () => {
  assert.throws(() => draft([scalar(), { id: "C-corrupt", integrity: "UNKNOWN", error: "TEST_ONLY hash failure" }], "S-test"), /VERIFIED/);
  assert.throws(() => draft([scalar(), structuredClone(scalar())], "S-test"), /중복/);
  const other = history(); other.record.source.study_id = "S-other";
  assert.throws(() => draft([scalar(), other], "S-test"), /선택한 연구/);
  const unverified = scalar(); unverified.integrity = "NOT_CHECKED"; assert.throws(() => draft([unverified], "S-test"), /VERIFIED/);
});
test("safe joined IDs, supported versions and source document hashes are mandatory", () => {
  for (const mutate of [
    (r) => { r.record.id = "C-other"; }, (r) => { r.record.request.comparison_id = "C-other"; },
    (r) => { r.record.request.experiment_id = "E-other"; }, (r) => { r.record.source.experiment_id = "E-other"; },
    (r) => { r.record.id = r.record.request.comparison_id = "C-scalar\n"; },
    (r) => { r.record.request.experiment_id = r.record.source.experiment_id = "../experiment"; },
    (r) => { delete r.record.source.result_sha256; }, (r) => { r.record.source.result_sha256 = hash("A"); },
    (r) => { r.record.schema_version = "2.0"; }, (r) => { delete r.record.comparison; }
  ]) { const row = scalar(); mutate(row); assert.throws(() => draft([row], "S-test")); }
  for (const studyId of ["", "S-test\n", "1-invalid", "S".repeat(81)]) assert.throws(() => draft([scalar()], studyId), /연구 식별자/);
});
test("malformed observations, scopes and nonfinite or nonnumeric comparison values are refused", () => {
  for (const mutate of [
    (r) => { r.record.request.observation.source_kind = "NATIVE"; },
    (r) => { r.record.request.observation.quantity = ""; }, (r) => { r.record.request.hypothesis = " "; },
    (r) => { r.record.request.extra = true; }, (r) => { r.record.request.observation.extra = true; },
    (r) => { r.record.comparison.response_value = true; }, (r) => { r.record.comparison.response_value = null; },
    (r) => { r.record.comparison.observed_value = 10; }, (r) => { r.record.comparison.difference = Infinity; },
    (r) => { r.record.comparison.absolute_difference = NaN; }, (r) => { r.record.comparison.unit = ""; },
    (r) => { r.record.comparison.scope_alignment = "QUALIFIED"; }, (r) => { r.record.comparison.physical_validation = "PASS"; },
    (r) => { r.record.comparison.decision = "RELEASED"; }, (r) => { r.record.comparison.causal_verdict = "UNIQUE_CAUSE"; }
  ]) { const row = scalar(); mutate(row); assert.throws(() => draft([row], "S-test")); }
  for (const source_kind of ["SYNTHETIC", "MEASURED_REPORTED", "SPECIFICATION"]) {
    const row = scalar(); row.record.request.observation.source_kind = source_kind; assert.doesNotThrow(() => draft([row], "S-test"));
  }
});
test("mismatch records cannot replace null with zero, a numeric tolerance verdict or inconsistent status", () => {
  for (const mutate of [
    (r) => { r.record.comparison.difference = 0; }, (r) => { r.record.comparison.absolute_difference = 0; },
    (r) => { r.record.comparison.within_declared_tolerance = true; }, (r) => { r.record.comparison.status = "NUMERIC_DIFFERENCE_ONLY"; },
    (r) => { r.record.comparison.declared_condition_checks[0].declared.value = 150; },
    (r) => { r.record.comparison.condition_bindings_supplied = false; }
  ]) { const row = mismatch(); mutate(row); assert.throws(() => draft([row], "S-test")); }
  const missingDifference = scalar(); missingDifference.record.comparison.difference = null;
  assert.throws(() => draft([missingDifference], "S-test"));
});
test("scalar/array selection preserves original response and does not accept nested values or mixed response kinds", () => {
  for (const mutate of [
    (r) => { r.record.request.response.component = 0; }, (r) => { r.record.request.response.history_channel = "mgis-stress-xz"; },
    (r) => { r.record.request.response.extra = 1; }, (r) => { r.record.comparison.source_metric.valid = false; },
    (r) => { r.record.comparison.source_metric.unit = "kN"; }, (r) => { r.record.comparison.response_value = -150; }
  ]) { const row = scalar(); mutate(row); assert.throws(() => draft([row], "S-test")); }
  const nested = array(); nested.record.comparison.source_metric.value = [[-100]]; assert.throws(() => draft([nested], "S-test"));
  const unselected = array(); delete unselected.record.request.response.component; assert.throws(() => draft([unselected], "S-test"));
});
test("1.1 record retains explicit channel/sample/axis/native origin links and rejects conflicting or incomplete history metadata", () => {
  for (const mutate of [
    (r) => { r.record.schema_version = "1.0"; }, (r) => { r.record.request.response.sample_index = 2; },
    (r) => { r.record.request.response.sample_index = "1"; }, (r) => { r.record.comparison.source_channel.id = "mgis-stress-xx"; },
    (r) => { r.record.comparison.source_channel.values[1] = -18; },
    (r) => { r.record.comparison.source_channel.axis.values[1] = 0; },
    (r) => { r.record.comparison.source_channel.origin.kind = "REFERENCE"; },
    (r) => { r.record.comparison.response_axis.value = 0.75; },
    (r) => { r.record.comparison.declared_axis_check.matched = false; },
    (r) => { delete r.record.comparison.declared_axis_check; },
    (r) => { r.record.request.observation.axis.unit = "ms"; }
  ]) { const row = history(); mutate(row); assert.throws(() => draft([row], "S-test")); }
  const initial = history(); initial.record.request.response.sample_index = 0;
  initial.record.request.observation.axis.value = initial.record.comparison.response_axis.value = 0;
  initial.record.comparison.declared_axis_check.declared.value = initial.record.comparison.declared_axis_check.actual.value = 0;
  initial.record.comparison.response_value = 0; initial.record.comparison.difference = initial.record.comparison.absolute_difference = 15.5;
  initial.record.comparison.within_declared_tolerance = false;
  assert.match(draft([initial], "S-test").question, /t=0.*수치 초기 상태/);
});
test("selection envelope is exactly 1..12 rows and the maximal ID case stays within the existing UTF8 question limit", () => {
  assert.throws(() => draft([], "S-test"), /1~12/); assert.throws(() => draft({}, "S-test"), /1~12/);
  const studyId = "S" + "x".repeat(79), rows = Array.from({ length: 12 }, (_, index) => scalar("C" + String(index).padStart(79, "0"), "E" + String(index).padStart(79, "0"), studyId));
  const result = draft(rows, studyId), bytes = new TextEncoder().encode(result.question).length;
  assert.equal(result.comparisonIds.length, 12); assert.equal(result.experimentIds.length, 12); assert.ok(bytes <= 16384);
  result.comparisonIds.forEach((id) => assert.equal(result.question.includes(id), true));
  result.experimentIds.forEach((id) => assert.equal(result.question.includes(id), true));
  assert.throws(() => draft([...rows, scalar("C-thirteen", "E-thirteen", studyId)], studyId), /1~12/);
});
test("unsafe JSON, inherited data and getters refuse without executing source attributes", () => {
  const row = scalar(); assert.throws(() => draft([Object.create(row)], "S-test"), /JSON/);
  let reads = 0; const getter = scalar(); Object.defineProperty(getter, "record", { enumerable: true, get() { reads += 1; return row.record; } });
  assert.throws(() => draft([getter], "S-test"), /JSON/); assert.equal(reads, 0);
  for (const name of ["__proto__", "prototype", "constructor"]) {
    const unsafe = scalar(); Object.defineProperty(unsafe.record.source, name, { value: { polluted: true }, enumerable: true });
    assert.throws(() => draft([unsafe], "S-test"), /JSON/); assert.equal({}.polluted, undefined);
  }
  const cycle = scalar(); cycle.record.source.extra = cycle; assert.throws(() => draft([cycle], "S-test"), /JSON/);
  const sparse = new Array(1); assert.throws(() => draft(sparse, "S-test"), /JSON/);
});
test("browser/CommonJS API makes the same pure question without providers, sessions or DOM", () => {
  const rows = [history(), scalar()], context = vm.createContext({ window: {}, TextEncoder, rowsJson: JSON.stringify(rows) });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../apps/lab/static/comparison-research.js"), "utf8"), context);
  assert.equal(typeof context.window.comparisonResearch.draft, "function");
  const result = vm.runInContext("window.comparisonResearch.draft(JSON.parse(rowsJson), 'S-test')", context);
  assert.deepEqual(JSON.parse(JSON.stringify(result)), draft(rows, "S-test"));
});
