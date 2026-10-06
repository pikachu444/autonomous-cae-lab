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

function field(id = "C-field", component = "UZ") {
  const row = scalar(id, "E-native"), { request, comparison } = row.record;
  row.record.schema_version = "1.2"; row.record.source.cad_revision = hash("f"); request.purpose = "GENERAL_CAE_RESEARCH";
  request.observation.quantity = "DISPLACEMENT"; request.observation.component = component; request.observation.coordinate_frame = "CAD_DOCUMENT_GLOBAL";
  request.observation.unit = comparison.unit = "mm"; request.observation.value = comparison.observed_value = component === "MAGNITUDE" ? 0.0032 : -0.0022;
  request.observation.tolerance = comparison.declared_absolute_tolerance = 0.0004;
  request.response = { field: { artifact: "simulation/field.json", sha256: hash("d"), cad_revision: hash("f"), node_id: 17, component } };
  comparison.selection_kind = "EXACT_RECORDED_FIELD_NODE"; delete comparison.source_metric;
  comparison.response_value = component === "MAGNITUDE" ? 0.003 : -0.002;
  comparison.difference = comparison.response_value - comparison.observed_value; comparison.absolute_difference = Math.abs(comparison.difference);
  comparison.within_declared_tolerance = comparison.absolute_difference <= comparison.declared_absolute_tolerance;
  comparison.source_field = { ...request.response.field, quantity: "DISPLACEMENT", position_mm: [16, 5, 4], position_unit: "mm",
    coordinate_frame: "CAD_DOCUMENT_GLOBAL", value_origin: component === "MAGNITUDE" ? "DERIVED_MAGNITUDE" : "NATIVE_COMPONENT",
    static: { step: 1, increment: 1, load_parameter: 1 }, coverage: "ALL_MESH_NODES" };
  comparison.field_qualification = "UNKNOWN";
  comparison.declared_field_checks = ["quantity", "component", "coordinate_frame"].map(property => ({ property,
    declared: request.observation[property], actual: comparison.source_field[property], matched: true }));
  return row;
}

function feField(nodal=false) {
  const row=scalar(nodal?"C-fe-node":"C-fe-gauss"), {request,comparison,source}=row.record;
  row.record.schema_version="1.5"; source.backend="structural.code_aster.plasticity"; source.model_revision=hash("f");
  request.purpose="GENERAL_CAE_RESEARCH";
  const field={kind:nodal?"fe_nodal":"fe_gauss",artifact:"simulation/level_0/parsed_history.json",sha256:hash("e"),
    model_revision:source.model_revision,mesh_index:0,time_index:1,component:nodal?"REAC_NODA.DX":"SIEF_ELGA.SIXX",
    ...(nodal?{node_id:3}:{element_id:7,point:2,subpoint:0})};
  request.response={field}; const quantity=nodal?"NODAL_REACTION":"STRESS",unit=nodal?"N":"MPa";
  const coordinate_frame="global Cartesian model; sensor/world alignment UNKNOWN";
  Object.assign(request.observation,{quantity,unit,component:field.component,coordinate_frame,value:-15.5,axis:{quantity:"time",unit:"s",value:.5}});
  delete comparison.source_metric;
  Object.assign(comparison,{unit,response_value:-16,observed_value:-15.5,difference:-.5,absolute_difference:.5,
    selection_kind:nodal?"EXACT_RECORDED_FE_NODE":"EXACT_RECORDED_FE_INTEGRATION_POINT",
    source_field:{...field,quantity,coordinate_frame,coordinates_mm:[1,2,3],coordinates_unit:"mm",actual_result_order:1,time_s:.5,
      measure:nodal?"signed native nodal reaction":"small-strain Cauchy stress",raw_artifact:"simulation/level_0/worker_result.json",raw_sha256:hash("d"),value_origin:"NATIVE_COMPONENT"},
    field_qualification:{numeric:"RECORDED_NATIVE_VALUE",reference:"RECORDED_DOMAIN_VERDICT_UNCHANGED",physical:"UNKNOWN",decision:"NOT_RELEASED"},
    response_axis:{quantity:"time",unit:"s",value:.5},declared_axis_check:{declared:{...request.observation.axis},actual:{quantity:"time",unit:"s",value:.5},matched:true},
    declared_field_checks:["quantity","component","coordinate_frame"].map(property=>({property,declared:request.observation[property],actual:request.observation[property],matched:true}))});
  return row;
}
test("FE saved point interpretation preserves native tensor/node distinction, time, units and UNKNOWN",()=>{
  const rows=[feField(),feField(true)], before=structuredClone(rows), result=draft(rows,"S-test");
  assert.match(result.question,/요소\/적분점\/하위점 7\/2\/0/); assert.match(result.question,/원 절점 3/);
  for (const item of ["원 시간 0.5 s","small-strain Cauchy","UNWEIGHTED","체적 평균","INITIAL_STATE_NO_NEWTON_INCREMENT","NOT_RELEASED"]) assert.ok(result.question.includes(item));
  assert.deepEqual(rows,before);
  const mismatch=feField(); mismatch.record.request.observation.axis.value=.75;
  mismatch.record.comparison.declared_axis_check.declared.value=.75; mismatch.record.comparison.declared_axis_check.matched=false;
  nullDifference(mismatch.record.comparison,"DECLARED_AXIS_MISMATCH");
  assert.match(draft([mismatch],"S-test").question,/차이 null/);
});
test("foreign FE revision or identity, native component/unit/axis corruption and disguised qualification refuse interpretation",()=>{
  for (const mutate of [r=>{r.record.source.model_revision=hash("b");},r=>{r.record.comparison.source_field.point=4;},
    r=>{r.record.request.response.field.node_id=3;},r=>{r.record.comparison.response_axis.unit="1";},
    r=>{r.record.comparison.source_field.time_s=.75;},r=>{r.record.comparison.field_qualification.physical="PASS";},
    r=>{r.record.request.response.field.component="PK1.XX";},r=>{r.record.comparison.difference=.5;}]) {
    const row=feField(); mutate(row); assert.throws(()=>draft([row],"S-test"));
  }
});
function fieldMismatch(property = "coordinate_frame") {
  const row = field("C-field-mismatch"), { request, comparison } = row.record;
  request.observation[property] = `USER_DECLARED_OTHER_${property}`;
  const check = comparison.declared_field_checks.find(item => item.property === property); check.declared = request.observation[property]; check.matched = false;
  nullDifference(comparison, "DECLARED_FIELD_MISMATCH"); return row;
}

function pdeField(timed=false) {
  const row=scalar("C-pde","E-pde"), {request,source,comparison}=row.record;
  row.record.schema_version="1.4"; source.model_revision=hash("f");
  request.response={field:{kind:"pde_nodal",artifact:"pde/level_n16/dofs.json",sha256:hash("e"),model_revision:source.model_revision,
    study_index:0,step_index:timed?1:null,node_id:0,component:"u"}};
  Object.assign(request.observation,{unit:"1",quantity:"PDE_SCALAR_FIELD",component:"u",coordinate_frame:"PDE_MODEL_CARTESIAN",value:1});
  delete comparison.source_metric;
  Object.assign(comparison,{unit:"1",response_value:-2,observed_value:1,difference:-3,absolute_difference:3,
    within_declared_tolerance:false,selection_kind:"EXACT_RECORDED_FIELD_NODE",
    source_field:{...request.response.field,quantity:"PDE_SCALAR_FIELD",coordinates:[0,0],coordinates_unit:"1",coordinate_frame:"PDE_MODEL_CARTESIAN"},
    field_qualification:{numeric:"RECORDED_NATIVE_VALUE",physical:"UNKNOWN",decision:"NOT_RELEASED"}});
  comparison.declared_field_checks=["quantity","component","coordinate_frame"].map(property=>({property,
    declared:request.observation[property],actual:comparison.source_field[property],matched:true}));
  if (timed) {
    request.observation.axis={quantity:"time",unit:"1",value:.125};
    comparison.response_axis={...request.observation.axis};
    comparison.declared_axis_check={declared:{...request.observation.axis},actual:{...comparison.response_axis},matched:true};
  }
  return row;
}
test("common research accepts the exact PDE model/mesh/node and signed field, retaining dimensionless time", () => {
  const row=pdeField(true), question=draft([row],"S-test").question;
  assert.match(question,/PDE/); assert.match(question,/원 절점 0/); assert.match(question,/time=0.125 \(1\)/);
  assert.match(question,/-2/); assert.match(question,/UNKNOWN/);
  assert.doesNotMatch(question,/CAD 개정|UX\/UY\/UZ|원 TH 속도/);
  assert.match(question,/UNINTEGRATED_INITIAL_CONDITION\/NOT_RUN/);
  const mismatch=pdeField(true); mismatch.record.request.observation.axis.value=.13;
  const check=mismatch.record.comparison.declared_axis_check; check.declared.value=.13; check.matched=false;
  Object.assign(mismatch.record.comparison,{status:"DECLARED_AXIS_MISMATCH",difference:null,absolute_difference:null,within_declared_tolerance:null});
  assert.match(draft([mismatch],"S-test").question,/DECLARED_AXIS_MISMATCH/);
  for (const mutate of [r=>{r.record.source.model_revision=hash("a");},r=>{r.record.comparison.source_field.node_id=1;},
    r=>{r.record.comparison.response_axis.unit="s";},r=>{r.record.comparison.field_qualification.physical="PASS";}]) {
    const changed=pdeField(true); mutate(changed); assert.throws(()=>draft([changed],"S-test"));
  }
});

test("1.2 field research draft retains exact original node, coordinates, signed component and field source without a metric", () => {
  const row = freeze(field()), before = JSON.stringify(row), result = draft([row], "S-test"), question = result.question;
  assert.deepEqual(result.comparisonIds, ["C-field"]); assert.deepEqual(result.experimentIds, ["E-native"]);
  for (const text of ["simulation/field.json", hash("d"), hash("f"), "원 절점 17", "[16, 5, 4] mm", "CAD_DOCUMENT_GLOBAL",
      "DISPLACEMENT/UZ = -0.002 mm", "NATIVE_COMPONENT", "EXACT_RECORDED_FIELD_NODE", "field 자격 UNKNOWN", "USER_DECLARED_UNVERIFIED", "NOT_RELEASED"]) {
    assert.equal(question.includes(text), true, text);
  }
  assert.match(question, /load_parameter=1/); assert.match(question, /정적 step\/increment\/load_parameter를 시간축으로 쓰지/);
  assert.match(question, /센서\/world 정렬.*같은 절점 ID.*검증된 물리 위치 대응이 아닙니다/);
  assert.equal(question.includes("source_metric"), false); assert.equal(Object.hasOwn(row.record.comparison, "source_metric"), false);
  assert.equal(question.includes("지그"), false); assert.equal(JSON.stringify(row), before);
});

test("derived magnitude and signed native components remain distinct alongside legacy scalar/history records", () => {
  const rows = [field("C-vector", "MAGNITUDE"), field("C-signed"), scalar(), history()], original = structuredClone(rows);
  const result = draft(freeze(rows), "S-test");
  assert.deepEqual(result.comparisonIds, ["C-vector", "C-signed", "C-scalar", "C-history"]);
  assert.match(result.question, /DISPLACEMENT\/MAGNITUDE = 0\.003 mm · DERIVED_MAGNITUDE/);
  assert.match(result.question, /DISPLACEMENT\/UZ = -0\.002 mm · NATIVE_COMPONENT/);
  assert.match(result.question, /벡터에서 계산한 크기/);
  assert.match(result.question, /이력이 있으면 원본 driver/);
  assert.deepEqual(rows, original);
  const generalScalar = scalar(); generalScalar.record.request.purpose = "GENERAL_CAE_RESEARCH";
  const generalHistory = history(); generalHistory.record.request.purpose = "GENERAL_CAE_RESEARCH";
  assert.doesNotThrow(() => draft([generalScalar, generalHistory], "S-test"));
});

test("declared field quantity/component/frame mismatches preserve null and condition mismatch has its original priority", () => {
  for (const property of ["quantity", "component", "coordinate_frame"]) {
    const row = fieldMismatch(property), before = JSON.stringify(row), question = draft([freeze(row)], "S-test").question;
    assert.match(question, /DECLARED_FIELD_MISMATCH.*차이 null.*허용 차이 판정 null/);
    assert.equal(question.includes(`USER_DECLARED_OTHER_${property}`), true); assert.equal(JSON.stringify(row), before);
  }
  const both = fieldMismatch(), condition = { source: "execution", path: ["force_N"], value: 100, unit: "N" };
  both.record.request.observation.conditions = [condition]; both.record.comparison.condition_bindings_supplied = true;
  both.record.comparison.declared_condition_checks = [{ declared: structuredClone(condition), actual: 150, matched: false }];
  both.record.comparison.status = "DECLARED_CONDITION_MISMATCH";
  assert.match(draft([both], "S-test").question, /DECLARED_CONDITION_MISMATCH.*차이 null/);
  for (const patch of [{ difference: 0 }, { absolute_difference: 0 }, { within_declared_tolerance: true }, { status: "NUMERIC_DIFFERENCE_ONLY" }]) {
    const row = fieldMismatch(); Object.assign(row.record.comparison, patch); assert.throws(() => draft([row], "S-test"));
  }
});

test("field identity tamper, conflicting source kinds, forged origin and mismatched check receipts refuse the complete draft", () => {
  const changes = [
    row => { row.record.comparison.source_field.sha256 = hash("e"); },
    row => { row.record.comparison.source_field.node_id = 18; },
    row => { row.record.source.cad_revision = hash("a"); },
    row => { row.record.request.response.field.artifact = row.record.comparison.source_field.artifact = "../field.json"; },
    row => { row.record.comparison.source_metric = { value: -0.002, unit: "mm", valid: true }; },
    row => { row.record.request.observation.axis = { quantity: "time", value: 1, unit: "s" }; },
    row => { row.record.comparison.source_field.value_origin = "DERIVED_MAGNITUDE"; },
    row => { row.record.comparison.source_field.position_mm = [1, 2]; },
    row => { row.record.comparison.field_qualification = "PASS"; },
    row => { row.record.comparison.declared_field_checks[2].matched = false; },
    row => { row.record.comparison.difference = -0.002; }
  ];
  for (const mutate of changes) { const row = field(); mutate(row); assert.throws(() => draft([scalar(), row], "S-test")); }
  const forgedMatch = fieldMismatch(); forgedMatch.record.comparison.declared_field_checks[2].matched = true;
  assert.throws(() => draft([forgedMatch], "S-test"));
  const mixed = scalar(); mixed.record.comparison.source_field = field().record.comparison.source_field;
  assert.throws(() => draft([mixed], "S-test"));
  const wrongMagnitude = field("C-magnitude", "MAGNITUDE"); wrongMagnitude.record.comparison.source_field.value_origin = "NATIVE_COMPONENT";
  assert.throws(() => draft([wrongMagnitude], "S-test"));
});

test("optional human research context includes general question/hypothesis/objective and leaves two-argument legacy output unchanged", () => {
  const rows = [scalar()], before = draft(rows, "S-test").question;
  const context = freeze({ question: "측정 위치의 부호 있는 변위가 하중 가설을 구별하는가?", hypothesis: "동일 형상에서 재료 강성 또는 하중 성분이 응답을 바꾼다",
    objective: "정확 위치·성분의 응답과 잔차를 비교하고 다음 관측을 정한다" });
  const result = draft([field()], "S-test", context);
  for (const value of Object.values(context)) assert.equal(result.question.includes(value), true);
  assert.equal(draft(rows, "S-test", undefined).question, before); assert.equal(draft(rows, "S-test").question, before);
  for (const value of [null, { ...context, extra: "unsupported" }, { ...context, question: 10 }, { ...context, objective: "x".repeat(2001) }]) {
    assert.throws(() => draft([field()], "S-test", value), /context/);
  }
  let reads = 0; const active = { ...context }; Object.defineProperty(active, "question", { enumerable: true, get() { reads++; return "question"; } });
  assert.throws(() => draft([field()], "S-test", active), /context/); assert.equal(reads, 0);
});

test("browser/CommonJS field draft and human context preserve the same exact source semantics", () => {
  const rows = [field(), field("C-magnitude", "MAGNITUDE")], human = { question: "General research question", hypothesis: "Compare response hypotheses", objective: "Compare signed components with derived magnitude" };
  const context = vm.createContext({ window: {}, TextEncoder, rowsJson: JSON.stringify(rows), contextJson: JSON.stringify(human) });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../apps/lab/static/comparison-research.js"), "utf8"), context);
  const result = vm.runInContext("window.comparisonResearch.draft(JSON.parse(rowsJson), 'S-test', JSON.parse(contextJson))", context);
  assert.deepEqual(JSON.parse(JSON.stringify(result)), draft(rows, "S-test", human));
});
