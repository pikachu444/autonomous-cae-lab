"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const controls = require("../apps/lab/static/observation-controls.js");
const presentation = require("../apps/lab/static/result-presentation.js");
const key = (metric, component = null) => JSON.stringify([metric, component]);

// Small TEST_ONLY response shapes; no actual observation, solver result or qualification.
function record() {
  return { integrity: "VERIFIED", record_id: "E-test",
    result: { experiment_id: "E-test", study: { id: "S-test" }, decision: "NOT_RELEASED",
      validations: [{ type: "physical", status: "UNKNOWN", blocking: true }],
      metrics: {
        max_displacement: { value: 0.0019, unit: "mm", valid: true },
        loaded_saddle_min_global_uz: { value: [-0.0019, -0.0021], unit: "mm", valid: true },
        reaction_force: { value: [-0, 2.5, -100], unit: "N", valid: true },
        peak_stress: { value: 999, unit: "MPa", valid: false, reason: "TEST_ONLY invalid diagnostic" }
      },
      provenance: { adapter: "fixture.calculix", adapter_details: { per_mesh_displacement: { response_metric: "loaded_saddle_min_global_uz" } } }
    }, proposal: { id: "E-test", study_id: "S-test" }, study: { id: "S-test" } };
}
function fields() {
  return { comparisonId: "C-test", purpose: "DEFECT_REPRODUCTION", hypothesis: " TEST_ONLY downward response hypothesis ",
    responseKey: key("loaded_saddle_min_global_uz", 0), name: " TEST_ONLY reported saddle displacement ", value: "-2.2e-3",
    sourceKind: "MEASURED_REPORTED", source: " TEST_ONLY user report, no measured file ", quantity: "displacement",
    component: "user-declared Z", location: "user-declared loaded saddle", coordinateFrame: "user-declared global Cartesian",
    condition: "TEST_ONLY reported 100 N case", tolerance: "0.0004" };
}
function freeze(value) {
  if (value && typeof value === "object") { Object.values(value).forEach(freeze); Object.freeze(value); }
  return value;
}

test("choices expose original finite scalars and explicit signed flat-array items without norm, abs or unit conversion", () => {
  const choices = controls.choices(record());
  assert.equal(choices.length, 6);
  assert.deepEqual(choices.map((item) => [item.key, item.metric, item.component ?? null, item.value, item.unit]), [
    [key("max_displacement"), "max_displacement", null, 0.0019, "mm"],
    [key("loaded_saddle_min_global_uz", 0), "loaded_saddle_min_global_uz", 0, -0.0019, "mm"],
    [key("loaded_saddle_min_global_uz", 1), "loaded_saddle_min_global_uz", 1, -0.0021, "mm"],
    [key("reaction_force", 0), "reaction_force", 0, -0, "N"],
    [key("reaction_force", 1), "reaction_force", 1, 2.5, "N"],
    [key("reaction_force", 2), "reaction_force", 2, -100, "N"]
  ]);
  assert.equal(Object.hasOwn(choices[0], "component"), false);
  assert.equal(Object.is(choices[3].value, -0), true);
  assert.match(choices[1].label, /사용자 지정 배열 항목 1 \(물리 성분 미확인\)/);
  assert.match(choices[5].label, /사용자 지정 배열 항목 3 \(물리 성분 미확인\)/);
});
test("invalid metrics and malformed vectors remain unavailable without removing other valid responses", () => {
  const data = record();
  for (const [name, metric] of Object.entries({
    false_valid: { value: 1, unit: "N", valid: false }, missing_valid: { value: 1, unit: "N" },
    truthy_valid: { value: 1, unit: "N", valid: "true" }, boolean: { value: true, unit: "N", valid: true },
    numeric_string: { value: "1", unit: "N", valid: true }, infinite: { value: Infinity, unit: "N", valid: true },
    nan: { value: NaN, unit: "N", valid: true }, unitless: { value: 1, unit: "", valid: true },
    blank_unit: { value: 1, unit: "  ", valid: true }, missing_unit: { value: 1, valid: true },
    nested: { value: [[1, 2]], unit: "N", valid: true }, mixed: { value: [1, "2"], unit: "N", valid: true },
    boolean_vector: { value: [true, 2], unit: "N", valid: true }, bad_vector: { value: [1, NaN], unit: "N", valid: true },
    empty_vector: { value: [], unit: "N", valid: true }, sparse: { value: new Array(2), unit: "N", valid: true }
  })) data.result.metrics[name] = metric;
  const choices = controls.choices(data);
  assert.equal(choices.length, 6); assert.deepEqual(choices.map((item) => item.key), controls.choices(record()).map((item) => item.key));
  assert.throws(() => controls.build(data, { ...fields(), responseKey: key("peak_stress") }), /명시적으로 선택/);
  assert.throws(() => controls.build(data, { ...fields(), responseKey: key("nested", 0) }), /명시적으로 선택/);
});
test("unknown integrity and mismatched or unsafe experiment/study identities refuse choices and build", () => {
  for (const mutate of [
    (r) => { r.integrity = "NOT_CHECKED"; }, (r) => { delete r.integrity; },
    (r) => { r.record_id = "E-other"; }, (r) => { r.proposal.id = "E-other"; },
    (r) => { r.proposal.study_id = "S-other"; }, (r) => { r.study.id = "S-other"; },
    (r) => { delete r.study; }, (r) => { delete r.proposal; },
    (r) => { r.result.experiment_id = "E-test\n"; }, (r) => { r.result.experiment_id = "../escape"; },
    (r) => { r.result.study.id = "1-invalid"; }, (r) => { r.result.study.id = "S".repeat(81); }
  ]) {
    const data = record(); mutate(data); assert.deepEqual(controls.choices(data), []);
    assert.throws(() => controls.build(data, fields()), /VERIFIED/);
  }
  assert.deepEqual(controls.choices(null), []); assert.deepEqual(controls.choices({}), []);
});
test("saved units and metric keys remain exact and JSON tuple keys avoid ambiguous array selections", () => {
  const data = record(); data.result.metrics['response"[,0]'] = { value: [-1, 1], unit: " Pa ", valid: true };
  const available = controls.choices(data).filter((item) => item.metric === 'response"[,0]');
  assert.deepEqual(available.map((item) => JSON.parse(item.key)), [['response"[,0]', 0], ['response"[,0]', 1]]);
  const request = controls.build(data, { ...fields(), responseKey: available[1].key, unit: "MPa", value: "1" });
  assert.deepEqual(request.response, { metric: 'response"[,0]', component: 1 }); assert.equal(request.observation.unit, " Pa ");
  assert.equal(request.observation.value, 1);
});
test("max_displacement is relabeled as loaded |UZ| only for the actual fixture provenance marker", () => {
  const data = record(), choice = controls.choices(data)[0];
  assert.match(choice.label, /하중 안장.*\|UZ\|/); assert.match(choice.label, /전체 절점 \|U\| 최대값 아님/);
  assert.equal(choice.value, data.result.metrics.max_displacement.value);
  for (const mutate of [
    (r) => { r.result.provenance.adapter = "structural.code_aster"; },
    (r) => { r.result.provenance.adapter_details.per_mesh_displacement.response_metric = "maximum_displacement"; },
    (r) => { delete r.result.provenance.adapter_details; }, (r) => { delete r.result.provenance; }
  ]) { const unmarked = record(); mutate(unmarked); assert.equal(controls.choices(unmarked)[0].label, presentation.metricName("max_displacement")); }
});
test("build returns exactly the declared scalar comparison input and preserves signed explicit array selection", () => {
  const request = controls.build(record(), fields());
  assert.deepEqual(request, {
    comparison_id: "C-test", experiment_id: "E-test", purpose: "DEFECT_REPRODUCTION", hypothesis: "TEST_ONLY downward response hypothesis",
    observation: { name: "TEST_ONLY reported saddle displacement", value: -0.0022, unit: "mm", source_kind: "MEASURED_REPORTED",
      source: "TEST_ONLY user report, no measured file", quantity: "displacement", component: "user-declared Z",
      location: "user-declared loaded saddle", coordinate_frame: "user-declared global Cartesian",
      condition: "TEST_ONLY reported 100 N case", tolerance: 0.0004, conditions: [] },
    response: { metric: "loaded_saddle_min_global_uz", component: 0 }
  });
  const scalar = controls.build(record(), { ...fields(), responseKey: key("max_displacement") });
  assert.deepEqual(scalar.response, { metric: "max_displacement" });
  assert.equal(Object.hasOwn(scalar, "decision"), false); assert.equal(Object.hasOwn(scalar, "validation"), false);
});
test("array response selection is explicit with no default item, physical component or response substitution", () => {
  for (const responseKey of [undefined, "", "reaction_force", key("reaction_force"), key("reaction_force", -1), key("reaction_force", 3), key("reaction_force", "0")]) {
    const input = fields(); if (responseKey === undefined) delete input.responseKey; else input.responseKey = responseKey;
    assert.throws(() => controls.build(record(), input), /명시적으로 선택/);
  }
  const input = { ...fields(), responseKey: key("reaction_force", 2), component: "TEST_ONLY user declared sample", coordinateFrame: "unverified frame" };
  const request = controls.build(record(), input);
  assert.deepEqual(request.response, { metric: "reaction_force", component: 2 });
  assert.equal(request.observation.component, "TEST_ONLY user declared sample"); assert.equal(request.observation.coordinate_frame, "unverified frame");
});
test("source kind and research purpose are preserved exactly without fabricating defaults", () => {
  for (const sourceKind of ["MEASURED_REPORTED", "SPECIFICATION", "SYNTHETIC"]) {
    for (const purpose of ["DEFECT_REPRODUCTION", "JIG_FEASIBILITY"]) {
      const request = controls.build(record(), { ...fields(), sourceKind, purpose });
      assert.equal(request.observation.source_kind, sourceKind); assert.equal(request.purpose, purpose);
    }
  }
  for (const changes of [{ sourceKind: "measured" }, { sourceKind: " SYNTHETIC " }, { purpose: "validation" }]) {
    assert.throws(() => controls.build(record(), { ...fields(), ...changes }));
  }
  for (const key of ["sourceKind", "purpose", "source", "tolerance"]) {
    const input = fields(); delete input[key]; assert.throws(() => controls.build(record(), input));
  }
});
test("numeric inputs require complete finite decimal strings and preserve sign, zero and exponent values", () => {
  for (const [value, expected] of [[" -.25 ", -0.25], ["+1.25e2", 125], ["-0", -0], ["0", 0], [".5", 0.5]]) {
    const request = controls.build(record(), { ...fields(), value, tolerance: "0" });
    assert.equal(Object.is(request.observation.value, expected), true); assert.equal(request.observation.tolerance, 0);
  }
  for (const value of ["", "  ", "NaN", "Infinity", "-Infinity", "1e309", "1x", "0x10", 0, false, null]) {
    assert.throws(() => controls.build(record(), { ...fields(), value }), /관측값/);
    assert.throws(() => controls.build(record(), { ...fields(), tolerance: value }), /허용 차이/);
  }
  assert.throws(() => controls.build(record(), { ...fields(), tolerance: "-0.1" }), /0 이상/);
});
test("all observation semantics and the hypothesis need explicit bounded text", () => {
  for (const [key, limit] of [["hypothesis", 2000], ["name", 256], ["source", 2000], ["quantity", 128], ["component", 128],
    ["location", 512], ["coordinateFrame", 128], ["condition", 2000]]) {
    for (const value of ["", " \n ", "x".repeat(limit + 1)]) assert.throws(() => controls.build(record(), { ...fields(), [key]: value }));
    assert.doesNotThrow(() => controls.build(record(), { ...fields(), [key]: "x".repeat(limit) }));
    const missing = fields(); delete missing[key]; assert.throws(() => controls.build(record(), missing));
  }
  for (const comparisonId of ["", "C-test\n", "../comparison", "1-invalid", "C".repeat(81)]) {
    assert.throws(() => controls.build(record(), { ...fields(), comparisonId }), /식별자/);
  }
});
test("declared condition syntax preserves exact scalar values, paths and units without validating backend alignment", () => {
  const conditions = [
    { source: "execution", path: ["load", "vector", "2"], value: -100, unit: "N" },
    { source: "input_parameters", path: ["support_width_mm"], value: 32, unit: "mm" },
    { source: "execution", path: ["unverified declaration"], value: "", unit: "1" },
    { source: "execution", path: ["enabled"], value: false, unit: "1" }
  ];
  const input = freeze({ ...fields(), conditions }), request = controls.build(freeze(record()), input);
  assert.deepEqual(request.observation.conditions, conditions);
  request.observation.conditions[0].path[0] = "edited"; request.observation.conditions[0].value = 200;
  assert.equal(conditions[0].path[0], "load"); assert.equal(conditions[0].value, -100);
});
test("condition bindings reject malformed sources, paths, shapes, values and the 16 item/segment envelope", () => {
  const valid = { source: "execution", path: ["load"], value: 100, unit: "N" };
  for (const conditions of [null, {}, Array.from({ length: 17 }, () => valid), [{ ...valid, source: "provenance" }],
    [{ ...valid, path: [] }], [{ ...valid, path: Array(17).fill("part") }], [{ ...valid, path: [""] }],
    [{ ...valid, path: ["x".repeat(129)] }], [{ ...valid, path: [0] }], [{ ...valid, path: ["constructor"] }],
    [{ ...valid, unit: " " }], [{ ...valid, value: null }], [{ ...valid, value: [1] }],
    [{ ...valid, extra: true }], [{ source: "execution", path: ["load"], value: 100 }]]) {
    assert.throws(() => controls.build(record(), { ...fields(), conditions }), /조건 연결/);
  }
  assert.doesNotThrow(() => controls.build(record(), { ...fields(), conditions: Array.from({ length: 16 }, () => ({ ...valid, path: Array(16).fill("part") })) }));
});
test("records and fields remain immutable and every returned condition path is independent", () => {
  const data = record(), input = { ...fields(), conditions: [{ source: "execution", path: ["material", "name"], value: "TEST_ONLY", unit: "1" }] };
  const originalRecord = structuredClone(data), originalFields = structuredClone(input);
  freeze(data); freeze(input);
  const available = controls.choices(data), request = controls.build(data, input);
  available[1].value = 99; request.observation.conditions[0].path.push("edited"); request.observation.source = "edited";
  assert.deepEqual(data, originalRecord); assert.deepEqual(input, originalFields);
  assert.equal(data.result.metrics.peak_stress.valid, false); assert.equal(data.result.validations[0].status, "UNKNOWN");
  assert.equal(data.result.decision, "NOT_RELEASED");
});
test("inherited, dangerous or executable data cannot supply choices or observation arguments", () => {
  const inherited = Object.create({ ...fields() }); assert.throws(() => controls.build(record(), inherited), /JSON/);
  let reads = 0; const data = record();
  Object.defineProperty(data.result.metrics, "getter_metric", { enumerable: true, get() { reads += 1; return { value: 1, unit: "N", valid: true }; } });
  assert.equal(controls.choices(data).length, 6); assert.equal(reads, 0);
  const metric = Object.create({ value: 1, unit: "N", valid: true }); data.result.metrics.inherited_metric = metric;
  assert.equal(controls.choices(data).length, 6);
  for (const property of ["__proto__", "prototype", "constructor"]) {
    const input = fields(); Object.defineProperty(input, property, { value: { polluted: true }, enumerable: true });
    assert.throws(() => controls.build(record(), input), /JSON/); assert.equal({}.polluted, undefined);
  }
  const getter = fields(); Object.defineProperty(getter, "value", { enumerable: true, get() { reads += 1; return "1"; } });
  assert.throws(() => controls.build(record(), getter), /JSON/); assert.equal(reads, 0);
  const cycle = fields(); cycle.conditions = [cycle]; assert.throws(() => controls.build(record(), cycle), /JSON/);
  const nonfinite = fields(); nonfinite.conditions = [{ source: "execution", path: ["load"], value: NaN, unit: "N" }];
  assert.throws(() => controls.build(record(), nonfinite), /JSON/);
});
test("browser and CommonJS APIs use existing presentation names without a DOM, provider or HTTP", () => {
  const context = vm.createContext({ window: {}, recordJson: JSON.stringify(record()), fieldsJson: JSON.stringify(fields()) });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../apps/lab/static/result-presentation.js"), "utf8"), context);
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../apps/lab/static/observation-controls.js"), "utf8"), context);
  assert.equal(typeof context.window.observationControls.choices, "function"); assert.equal(typeof context.window.observationControls.build, "function");
  const available = vm.runInContext("window.observationControls.choices(JSON.parse(recordJson))", context);
  assert.equal(available[3].label.split(" · ")[0], presentation.metricName("reaction_force"));
  const request = vm.runInContext("window.observationControls.build(JSON.parse(recordJson), JSON.parse(fieldsJson))", context);
  assert.deepEqual(JSON.parse(JSON.stringify(request)), controls.build(record(), fields()));
});
