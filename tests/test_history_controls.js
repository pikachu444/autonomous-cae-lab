"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const controls = require("../apps/lab/static/history-controls.js");
const digest = (character) => character.repeat(64);

// Small TEST_ONLY native-history envelope shapes. These are not native evidence,
// measured observations, material qualification or a producer implementation.
function fixture() {
  const componentNames = ["xx", "yy", "zz", "xy", "xz", "yz"];
  const stress = [[-0, 0, 0, 0, 0, 0], [-6, 10, 12, -14, -16, -18], [-4, 20, 24, -28, -32, -36]];
  const branch = [[0, 0, 0, 0, 0, 0], [-1, 2, 3, -4, -5, -6], [-2, 4, 6, -8, -10, -12]];
  const energy = [[[0, 0], [2, 3], [3, 4]], [[0, 0], [2.1, 3.1], [3.2, 4.2]]];
  const inspection = { integrity: "VERIFIED", record_id: "E-test", result: {
    experiment_id: "E-test", study: { id: "S-test" }, status: "COMPLETED_REVIEW_REQUIRED", solver_status: "COMPLETED", decision: "NOT_RELEASED",
    provenance: { adapter: "material.mfront.viscoelastic" },
    metrics: { stress_history: { value: stress, unit: "MPa", valid: true }, branch_stress_history: { value: branch, unit: "MPa", valid: true },
      native_energy_history: { value: energy, unit: "MPa", valid: true }, reference_work_history: { value: [0, 4, 5], unit: "MPa", valid: true } },
    validations: [{ type: "physical", status: "UNKNOWN", blocking: true }],
    artifacts: [{ path: "simulation/native_raw.json", sha256: digest("a"), size_bytes: 100, revision: digest("b") }]
  }, proposal: { id: "E-test", study_id: "S-test", physics: { backend: "material.mfront.viscoelastic" } }, study: { id: "S-test" }, hashes: { result_sha256: digest("b") } };
  function channel(id, metric, quantity, component, measure, values, driver, nativeField, mapping) {
    return { id, label: `TEST_ONLY ${driver} ${quantity} ${component}`, metric, quantity, component, measure,
      coordinate_frame: "Tridimensional model component basis; sensor/world alignment UNKNOWN", location: "single homogeneous material point", unit: "MPa",
      axis: { quantity: "time", unit: "s", values: [0, 0.5, 1] }, values,
      origin: { kind: "NATIVE", driver, artifact: "simulation/native_raw.json", sha256: digest("a"), native_field: nativeField, mapping },
      initial_state: { index: 0, kind: "UNPREPARED_INITIAL_CONDITION" } };
  }
  const channels = [];
  for (const [name, rows, metric, quantity, measure, nativeField] of [
    ["stress", stress, "stress_history", "stress", "infinitesimal Cauchy stress", "stress_physical_mpa"],
    ["branch", branch, "branch_stress_history", "branch_stress", "internal branch stress", "branch_stress_physical_mpa"]
  ]) componentNames.forEach((component, index) => channels.push(channel(`mgis-${name}-${component}`, metric, quantity, component, measure,
    rows.map((row) => row[index]), "mgis", nativeField, "RECORDED_PHYSICAL_COMPONENT")));
  for (const [driverIndex, driver] of ["mgis", "mtest"].entries()) {
    for (const [componentIndex, name] of ["stored", "dissipated"].entries()) channels.push(channel(`${driver}-${name}`, "native_energy_history",
      `${name}_energy_density`, "scalar", "reference-volume energy density", energy[driverIndex].map((row) => row[componentIndex]),
      driver, `${name}_energy_mpa`, "NATIVE_SCALAR"));
  }
  return { inspection, envelope: { integrity: "VERIFIED", experiment_id: "E-test", study_id: "S-test", result_sha256: digest("b"), channels } };
}
function fields() {
  return { comparisonId: "C-test", purpose: "DEFECT_REPRODUCTION", hypothesis: " TEST_ONLY stress relaxation hypothesis ",
    name: "TEST_ONLY reported shear", value: "-18.5", sourceKind: "SYNTHETIC", source: "TEST_ONLY illustrative input",
    quantity: "stress", component: "xz", location: "single homogeneous material point", coordinateFrame: "material Cartesian X/Y/Z",
    condition: "TEST_ONLY declared load path", tolerance: "0.25", channelId: "mgis-stress-xz", sampleIndex: "1",
    axisQuantity: "time", axisUnit: "s", axisValue: "0.75", responseKey: '["history","mgis-stress-xz",1]' };
}
function freeze(value) {
  if (value && typeof value === "object") { Object.values(value).forEach(freeze); Object.freeze(value); }
  return value;
}
function refused(data) {
  assert.deepEqual(controls.channels(data.inspection, data.envelope), []);
  assert.throws(() => controls.sampleChoice(data.inspection, data.envelope, "mgis-stress-xz", 1), /VERIFIED/);
  assert.throws(() => controls.build(data.inspection, data.envelope, fields()), /VERIFIED/);
}

test("the supported native channels preserve physical tensor order, signed samples and explicit energy origins", () => {
  const data = fixture(), channels = controls.channels(data.inspection, data.envelope);
  assert.equal(channels.length, 16); assert.deepEqual(channels, data.envelope.channels);
  assert.equal(channels[4].component, "xz"); assert.equal(channels[4].values[1], -16);
  assert.equal(channels[5].component, "yz"); assert.equal(channels[5].values[1], -18);
  assert.equal(Object.is(channels[0].values[0], -0), true);
  assert.equal(channels[14].origin.driver, "mtest"); assert.equal(channels[14].origin.native_field, "stored_energy_mpa");
  channels[0].axis.values[0] = 10; channels[0].origin.sha256 = digest("e");
  assert.equal(data.envelope.channels[0].axis.values[0], 0); assert.equal(data.envelope.channels[0].origin.sha256, digest("a"));
});
test("sample choice returns one exact native sample and retains the initial condition caption without interpolating", () => {
  const data = fixture(), choice = controls.sampleChoice(data.inspection, data.envelope, "mgis-stress-xz", 1);
  assert.equal(choice.key, '["history","mgis-stress-xz",1]'); assert.equal(choice.value, -16); assert.equal(choice.unit, "MPa");
  assert.equal(choice.history_channel, "mgis-stress-xz"); assert.equal(choice.sample_index, 1);
  assert.deepEqual(choice.axis, { quantity: "time", value: 0.5, unit: "s" }); assert.match(choice.label, /t=0\.5s/);
  assert.deepEqual(choice.channel, data.envelope.channels[4]);
  const initial = controls.sampleChoice(data.inspection, data.envelope, "mgis-stress-xx", 0);
  assert.equal(Object.is(initial.value, -0), true); assert.match(initial.label, /수치 초기 상태 \(재료 적분 증거 아님\)/);
  delete data.envelope.channels[4].initial_state;
  assert.equal(controls.sampleChoice(data.inspection, data.envelope, "mgis-stress-xz", 0).sample_index, 0);
});
test("history envelopes need matching verified inspection identities and the exact saved result hash", () => {
  for (const mutate of [
    (d) => { d.inspection.integrity = "NOT_CHECKED"; }, (d) => { d.envelope.integrity = "NOT_CHECKED"; },
    (d) => { d.inspection.record_id = "E-other"; }, (d) => { d.inspection.proposal.id = "E-other"; },
    (d) => { d.inspection.proposal.study_id = "S-other"; }, (d) => { d.inspection.study.id = "S-other"; },
    (d) => { d.envelope.experiment_id = "E-other"; }, (d) => { d.envelope.study_id = "S-other"; },
    (d) => { d.envelope.result_sha256 = digest("c"); }, (d) => { delete d.inspection.hashes; },
    (d) => { d.inspection.hashes.result_sha256 = d.envelope.result_sha256 = digest("B"); },
    (d) => { d.inspection.result.experiment_id = "E-test\n"; }, (d) => { d.inspection.result.study.id = "../study"; }
  ]) { const data = fixture(); mutate(data); refused(data); }
});
test("the first scope is the completed Maxwell backend and valid native source metrics, independent of solver status spelling", () => {
  for (const mutate of [
    (d) => { d.inspection.result.status = "REJECTED"; }, (d) => { d.inspection.result.status = "FAILED_EXECUTION"; },
    (d) => { d.inspection.result.provenance.adapter = "material.mfront.elasticity"; },
    (d) => { d.inspection.proposal.physics.backend = "fixture.calculix"; },
    (d) => { d.inspection.result.metrics.stress_history.valid = false; },
    (d) => { d.inspection.result.metrics.stress_history.valid = "true"; },
    (d) => { delete d.inspection.result.metrics.native_energy_history; }
  ]) { const data = fixture(); mutate(data); refused(data); }
  const data = fixture(); data.inspection.result.solver_status = "TEST_ONLY alternate saved completion spelling";
  assert.equal(controls.channels(data.inspection, data.envelope).length, 16);
});
test("native origin is bound to the one manifested raw artifact and cannot relabel reference work as native", () => {
  for (const mutate of [
    (d) => { d.envelope.channels[0].origin.kind = "REFERENCE"; },
    (d) => { d.envelope.channels[0].origin.driver = "python"; },
    (d) => { d.envelope.channels[0].origin.artifact = "../native_raw.json"; },
    (d) => { d.envelope.channels[0].origin.sha256 = digest("c"); },
    (d) => { d.envelope.channels[0].origin.sha256 = digest("A"); },
    (d) => { d.inspection.result.artifacts = []; },
    (d) => { d.inspection.result.artifacts.push(structuredClone(d.inspection.result.artifacts[0])); },
    (d) => { d.envelope.channels[0].origin.native_field = "reference_work_history"; },
    (d) => { d.envelope.channels[0].origin.mapping = "NATIVE_SCALAR"; },
    (d) => { d.envelope.channels[0].origin.driver = "mtest"; },
    (d) => { d.envelope.channels[0].metric = "reference_work_history"; }
  ]) { const data = fixture(); mutate(data); refused(data); }
});
test("explicit channel metadata is required and cannot claim a different unit, quantity, measure, frame or point", () => {
  for (const mutate of [
    (c) => { c.id = "../history"; }, (c) => { c.id += "\n"; }, (c) => { c.label = " "; },
    (c) => { delete c.metric; }, (c) => { c.component = true; }, (c) => { c.component = "kelvin-xz"; },
    (c) => { c.quantity = "strain"; }, (c) => { c.measure = "engineering shear"; },
    (c) => { c.coordinate_frame = "global"; }, (c) => { c.location = "assembly"; },
    (c) => { c.unit = ""; }, (c) => { c.unit = "Pa"; }
  ]) { const data = fixture(); mutate(data.envelope.channels[0]); refused(data); }
  const duplicate = fixture(); duplicate.envelope.channels[1].id = duplicate.envelope.channels[0].id; refused(duplicate);
});
test("histories need finite dense same-length arrays and strictly increasing explicit time in seconds", () => {
  for (const mutate of [
    (c) => { c.values = []; c.axis.values = []; }, (c) => { c.values = [1, 2]; },
    (c) => { c.values[1] = true; }, (c) => { c.values[1] = "2"; }, (c) => { c.values[1] = NaN; },
    (c) => { c.values[1] = [2]; }, (c) => { c.values = new Array(3); },
    (c) => { c.axis.quantity = "load_parameter"; }, (c) => { c.axis.unit = "ms"; },
    (c) => { c.axis.values = [0, 0, 1]; }, (c) => { c.axis.values = [0, 1, 0.5]; },
    (c) => { c.axis.values[1] = Infinity; }, (c) => { c.axis.values[1] = false; }
  ]) { const data = fixture(); mutate(data.envelope.channels[0]); refused(data); }
  const empty = fixture(); empty.envelope.channels = []; refused(empty);
});
test("sampleChoice refuses missing channels, noninteger indexes, aliases and out-of-range samples", () => {
  const data = fixture();
  for (const index of [-1, 0.5, NaN, Infinity, "1", null, 3, Number.MAX_SAFE_INTEGER + 1]) {
    assert.throws(() => controls.sampleChoice(data.inspection, data.envelope, "mgis-stress-xz", index), /표본 번호/);
  }
  for (const id of ["", "mgis-stress-unknown", "mgis-stress-xz\n", "../channel"]) {
    assert.throws(() => controls.sampleChoice(data.inspection, data.envelope, id, 1), /채널/);
  }
});
test("build reuses observation validation but persists only history identity and the explicitly reported axis", () => {
  const data = fixture(), request = controls.build(data.inspection, data.envelope, fields());
  assert.deepEqual(request.response, { history_channel: "mgis-stress-xz", sample_index: 1 });
  assert.deepEqual(request.observation.axis, { quantity: "time", value: 0.75, unit: "s" });
  assert.equal(request.observation.value, -18.5); assert.equal(request.observation.unit, "MPa");
  assert.equal(request.observation.source_kind, "SYNTHETIC"); assert.equal(request.observation.tolerance, 0.25);
  assert.equal(request.experiment_id, "E-test"); assert.equal(request.comparison_id, "C-test");
  assert.equal(request.hypothesis, "TEST_ONLY stress relaxation hypothesis"); assert.deepEqual(request.observation.conditions, []);
  assert.equal(Object.hasOwn(request.response, "metric"), false); assert.equal(Object.hasOwn(request.response, "component"), false);
  assert.equal(JSON.stringify(request).includes("history_validation_sample"), false);
  assert.equal(Object.hasOwn(request, "decision"), false);
});
test("build requires a canonical explicit sample index and accepts no implicit or interpolated time choice", () => {
  const data = fixture();
  for (const sampleIndex of ["", "01", "+1", "1.0", "1e0", " 1 ", "1\n", "-1", "0.5", "9007199254740992", 1]) {
    assert.throws(() => controls.build(data.inspection, data.envelope, { ...fields(), sampleIndex }), /표본 번호/);
  }
  assert.throws(() => controls.build(data.inspection, data.envelope, { ...fields(), sampleIndex: "3" }), /표본 번호/);
  const initial = controls.build(data.inspection, data.envelope, { ...fields(), sampleIndex: "0", axisValue: "-0" });
  assert.equal(initial.response.sample_index, 0); assert.equal(Object.is(initial.observation.axis.value, -0), true);
});
test("reported axes need explicit time/s and finite decimal strings; the native sample cannot fill missing values", () => {
  const data = fixture();
  for (const changed of [{ axisQuantity: "load" }, { axisUnit: "ms" }, { axisValue: "" }, { axisValue: " " },
    { axisValue: "NaN" }, { axisValue: "Infinity" }, { axisValue: "1e309" }, { axisValue: "1x" }, { axisValue: 1 }, { axisValue: true }]) {
    assert.throws(() => controls.build(data.inspection, data.envelope, { ...fields(), ...changed }), /관측 시간/);
  }
  for (const name of ["channelId", "sampleIndex", "axisQuantity", "axisUnit", "axisValue"]) {
    const input = fields(); delete input[name]; assert.throws(() => controls.build(data.inspection, data.envelope, input), /명시한/);
  }
  const explicit = controls.build(data.inspection, data.envelope, { ...fields(), axisValue: "+1.25e1" });
  assert.equal(explicit.observation.axis.value, 12.5);
});
test("existing observation refusals and declared conditions remain authoritative without native metadata replacing user semantics", () => {
  const data = fixture();
  for (const changed of [{ value: "" }, { tolerance: "-1" }, { sourceKind: "native" }, { component: "" }, { comparisonId: "../comparison" }]) {
    assert.throws(() => controls.build(data.inspection, data.envelope, { ...fields(), ...changed }));
  }
  const input = { ...fields(), component: "TEST_ONLY declared component", coordinateFrame: "TEST_ONLY declared frame",
    conditions: [{ source: "execution", path: ["temperature_k"], value: 293.15, unit: "K" }] };
  const request = controls.build(data.inspection, data.envelope, input);
  assert.equal(request.observation.component, input.component); assert.equal(request.observation.coordinate_frame, input.coordinateFrame);
  assert.deepEqual(request.observation.conditions, input.conditions);
});
test("frozen inspection, envelope and fields remain untouched by choices and the ephemeral projection", () => {
  const data = fixture(), input = fields(), original = structuredClone(data), originalInput = structuredClone(input);
  freeze(data); freeze(input);
  const sample = controls.sampleChoice(data.inspection, data.envelope, "mgis-stress-xz", 1);
  sample.channel.values[1] = 999; sample.channel.initial_state.kind = "edited";
  const request = controls.build(data.inspection, data.envelope, input); request.observation.axis.value = 999;
  assert.deepEqual(data, original); assert.deepEqual(input, originalInput);
  assert.equal(data.inspection.result.decision, "NOT_RELEASED"); assert.equal(data.inspection.result.validations[0].status, "UNKNOWN");
  assert.equal(Object.hasOwn(data.inspection.result.metrics, "history_validation_sample"), false);
});
test("inherited, dangerous, cyclic and executable data refuse without invoking accessors", () => {
  const data = fixture(); assert.throws(() => controls.build(data.inspection, data.envelope, Object.create(fields())), /JSON/);
  let reads = 0; const getter = fields(); Object.defineProperty(getter, "axisValue", { enumerable: true, get() { reads += 1; return "1"; } });
  assert.throws(() => controls.build(data.inspection, data.envelope, getter), /JSON/); assert.equal(reads, 0);
  const sourceGetter = fixture(); Object.defineProperty(sourceGetter.envelope.channels[0], "values", { enumerable: true, get() { reads += 1; return [0, 1, 2]; } });
  refused(sourceGetter); assert.equal(reads, 0);
  const cycle = fields(); cycle.extra = cycle; assert.throws(() => controls.build(data.inspection, data.envelope, cycle), /JSON/);
  for (const key of ["__proto__", "prototype", "constructor"]) {
    const unsafe = fields(); Object.defineProperty(unsafe, key, { value: { polluted: true }, enumerable: true });
    assert.throws(() => controls.build(data.inspection, data.envelope, unsafe), /JSON/); assert.equal({}.polluted, undefined);
  }
});
test("browser and CommonJS exports agree using existing observation controls without DOM or runtime execution", () => {
  const data = fixture(), context = vm.createContext({ window: {}, inspectionJson: JSON.stringify(data.inspection), envelopeJson: JSON.stringify(data.envelope), fieldsJson: JSON.stringify(fields()) });
  for (const filename of ["result-presentation.js", "observation-controls.js", "history-controls.js"]) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, "../apps/lab/static", filename), "utf8"), context);
  }
  assert.equal(typeof context.window.historyControls.channels, "function"); assert.equal(typeof context.window.historyControls.sampleChoice, "function");
  const request = vm.runInContext("window.historyControls.build(JSON.parse(inspectionJson), JSON.parse(envelopeJson), JSON.parse(fieldsJson))", context);
  assert.deepEqual(JSON.parse(JSON.stringify(request)), controls.build(data.inspection, data.envelope, fields()));
});

test("general CAE purpose preserves the exact retained history sample and explicit measured axis contract", () => {
  const data = fixture(), input = { ...fields(), purpose: "GENERAL_CAE_RESEARCH", hypothesis: "Compare signed stress relaxation under alternative constitutive hypotheses" };
  const original = structuredClone(data), request = controls.build(freeze(data.inspection), freeze(data.envelope), freeze(input));
  assert.equal(request.purpose, "GENERAL_CAE_RESEARCH"); assert.equal(request.hypothesis, input.hypothesis);
  assert.deepEqual(request.response, { history_channel: "mgis-stress-xz", sample_index: 1 });
  assert.deepEqual(request.observation.axis, { quantity: "time", value: 0.75, unit: "s" });
  assert.equal(request.observation.unit, "MPa"); assert.equal(request.observation.value, -18.5);
  assert.equal(Object.hasOwn(request.response, "field"), false); assert.equal(Object.hasOwn(request.response, "metric"), false);
  assert.deepEqual(data, original);
});
