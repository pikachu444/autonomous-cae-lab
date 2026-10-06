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

const j2Backend = "structural.code_aster.plasticity";
function j2Fixture(sizes = [2]) {
  const index = sizes.length - 1, selected = sizes.length === 1;
  const times = selected ? [0, .25, .5, 1] : [0, .25, .5, .75, 1, 1.25];
  // Native result orders are identifiers, not synthesized sample indexes or a
  // guaranteed increasing clock. The reader associates them with actual INST.
  const orders = selected ? [0, 7, 3, 12] : [0, 7, 3, 12, 17, 10];
  const prefix = `simulation/level_${index}/`, channels = [];
  function add(id, component, nativeField, group = null) {
    const derived = group === null, strain = component === "V1";
    channels.push({ id, label: `TEST_ONLY J2 ${component}${derived ? " unweighted mean" : " boundary resultant"}`, metric: null,
      quantity: derived ? (strain ? "equivalent_plastic_strain" : "stress") : "force", component,
      measure: derived ? (strain ? "UNWEIGHTED arithmetic mean of native VARI_ELGA.V1; not volume average" :
        "UNWEIGHTED arithmetic mean of small-strain Cauchy Gauss stress; not volume average") : "signed native POST_RELEVE_T boundary resultant",
      coordinate_frame: "global Cartesian model; sensor/world alignment UNKNOWN",
      location: derived ? `all BODY TETRA10 five-point Gauss samples on finest declared mesh ${index}` : `group ${group} on finest declared mesh ${index}`,
      unit: derived ? (strain ? "1" : "MPa") : "N",
      axis: { quantity: "time", unit: "s", values: times.slice(), semantics: "NATIVE_INST_DECLARED_QUASI_STATIC_HISTORY_SECONDS" },
      values: times.map((_, i) => i === 0 ? -0 : (strain ? .0005 * i : -8 * i)),
      initial_state: { index: 0, kind: "INITIAL_STATE_NO_NEWTON_INCREMENT", time_s: 0, actual_result_order: orders[0] },
      origin: { kind: derived ? "DERIVED" : "NATIVE", driver: "code_aster", artifact: `${prefix}parsed_history.json`, sha256: digest("a"),
        native_artifact: `${prefix}worker_result.json`, native_sha256: digest("c"), native_field: nativeField,
        mapping: derived ? "ALL_GAUSS_UNWEIGHTED_ARITHMETIC_MEAN" : "EXACT_NATIVE_POST_RELEVE_T_BOUNDARY_RESULTANT",
        mesh_index: index, mesh_size_mm: sizes[index], actual_result_orders: orders.slice(), mesh_sha256: digest("d"), expected_mesh_sha256: digest("e"),
        ...(derived ? { aggregation: { operation: "arithmetic_mean", weighting: "UNWEIGHTED", point_count: 10,
          coverage: "ALL_BODY_TETRA10_FIVE_RIGI_POINTS", volume_average: false } } : {}) } });
  }
  add("j2-x0-fx", "FX", "BOUNDARY_RESULTANTS.X0.DX", "X0.DX");
  add("j2-y0-fy", "FY", "BOUNDARY_RESULTANTS.Y0.DY", "Y0.DY");
  add("j2-z0-fz", "FZ", "BOUNDARY_RESULTANTS.Z0.DZ", "Z0.DZ");
  add("j2-xl-fx", "FX", "BOUNDARY_RESULTANTS.XL.DX", "XL.DX");
  for (const component of ["SIXX", "SIYY", "SIZZ", "SIXY", "SIXZ", "SIYZ", "V1"]) {
    add(`j2-gauss-mean-${component.toLowerCase()}`, component, component === "V1" ? "VARI_ELGA.V1" : `SIEF_ELGA.${component}`);
  }
  const artifacts = sizes.flatMap((_, level) => [
    ["parsed_history.json", "a"], ["worker_result.json", "c"], ["mesh.msh", "d"], ["expected_mesh.json", "e"]
  ].map(([name, hash]) => ({ path: `simulation/level_${level}/${name}`, sha256: digest(hash), size_bytes: 100, revision: digest("f") })));
  const inspection = { integrity: "VERIFIED", record_id: "E-j2", result: { experiment_id: "E-j2", study: { id: "S-j2" },
    model_revision: digest("d"), proposal_revision: digest("f"), cad_revision: null, status: "COMPLETED_REVIEW_REQUIRED", solver_status: "COMPLETED",
    converged: true, decision: "NOT_RELEASED", provenance: { adapter: j2Backend, adapter_version: selected ? "1.2" : "1", proposal_sha256: digest("f") },
    metrics: { retained_validation_residual: { value: 9, unit: "1", valid: false } }, artifacts,
    validations: [{ type: "physical", status: "UNKNOWN", blocking: true }] },
    proposal: { id: "E-j2", study_id: "S-j2", model_revision: digest("d"), physics: { backend: j2Backend },
      execution: { mesh_sizes_mm: sizes.slice(), history: { times_s: times.slice(), axial_strain: selected ? [0, .003, .003, -.002] : [0, .001, .003, .002, .001, 0] } } },
    study: { id: "S-j2" }, hashes: { result_sha256: digest("b") } };
  return { inspection, envelope: { integrity: "VERIFIED", experiment_id: "E-j2", study_id: "S-j2", result_sha256: digest("b"), channels } };
}
function j2Fields(channelId = "j2-gauss-mean-sixz") {
  return { ...fields(), comparisonId: "C-j2", purpose: "GENERAL_CAE_RESEARCH", channelId, sampleIndex: "2", axisValue: ".55",
    hypothesis: "TEST_ONLY compare declared J2 signed response during hold and reversal", name: "TEST_ONLY reported J2 response",
    quantity: "stress", component: "SIXZ", location: "TEST_ONLY declared gauge location", coordinateFrame: "TEST_ONLY declared gauge frame",
    condition: "TEST_ONLY recorded block history; sensor alignment unverified", responseKey: "unused history source", conditions: [] };
}
function j2Refused(data) {
  assert.deepEqual(controls.channels(data.inspection, data.envelope), []);
  assert.throws(() => controls.sampleChoice(data.inspection, data.envelope, "j2-x0-fx", 0), /VERIFIED/);
  assert.throws(() => controls.build(data.inspection, data.envelope, j2Fields()), /VERIFIED/);
}

test("J2 choices keep four signed native resultants separate from seven all-Gauss unweighted means", () => {
  const data = j2Fixture(), accepted = controls.channels(data.inspection, data.envelope);
  assert.equal(accepted.length, 11); assert.deepEqual(accepted, data.envelope.channels);
  assert.deepEqual(accepted.slice(0, 4).map(c => [c.id, c.component, c.origin.native_field]), [
    ["j2-x0-fx", "FX", "BOUNDARY_RESULTANTS.X0.DX"], ["j2-y0-fy", "FY", "BOUNDARY_RESULTANTS.Y0.DY"],
    ["j2-z0-fz", "FZ", "BOUNDARY_RESULTANTS.Z0.DZ"], ["j2-xl-fx", "FX", "BOUNDARY_RESULTANTS.XL.DX"]
  ]);
  assert.ok(accepted.slice(0, 4).every(c => c.origin.kind === "NATIVE" && !Object.hasOwn(c.origin, "aggregation") && c.unit === "N"));
  assert.ok(accepted.slice(4).every(c => c.origin.kind === "DERIVED" && c.origin.aggregation.volume_average === false));
  const stress = controls.sampleChoice(data.inspection, data.envelope, "j2-gauss-mean-sixz", 2);
  assert.equal(stress.value, -16); assert.equal(stress.unit, "MPa"); assert.equal(stress.channel.origin.actual_result_orders[2], 3);
  const strain = controls.sampleChoice(data.inspection, data.envelope, "j2-gauss-mean-v1", 2);
  assert.equal(strain.unit, "1"); assert.equal(strain.value, .001); assert.equal(strain.channel.origin.native_field, "VARI_ELGA.V1");
  assert.equal(Object.is(accepted[0].values[0], -0), true);
  assert.match(controls.sampleChoice(data.inspection, data.envelope, "j2-x0-fx", 0).label, /새 Newton 증분 없음/);
  assert.doesNotMatch(stress.label, /새 Newton|재료 적분/);
});

test("J2 history uses the declared finest mesh and exact source/model/proposal joins, retaining invalid metrics", () => {
  const historical = j2Fixture([3, 2, 1]), accepted = controls.channels(historical.inspection, historical.envelope);
  assert.equal(accepted.length, 11); assert.ok(accepted.every(c => c.origin.mesh_index === 2 && c.origin.mesh_size_mm === 1));
  // CAD-free declared-model proposals omit cad_revision. Accept an explicitly
  // null optional field too, while never adding one to the saved proposal.
  assert.equal(Object.hasOwn(historical.inspection.proposal, "cad_revision"), false);
  const optionalNull = j2Fixture(); optionalNull.inspection.proposal.cad_revision = null;
  assert.equal(controls.channels(optionalNull.inspection, optionalNull.envelope).length, 11);
  assert.equal(historical.inspection.result.metrics.retained_validation_residual.valid, false);
  for (const mutate of [
    d => { d.inspection.proposal.model_revision = digest("e"); },
    d => { d.inspection.result.provenance.proposal_sha256 = digest("a"); },
    d => { d.inspection.result.cad_revision = digest("d"); },
    d => { d.inspection.proposal.cad_revision = digest("d"); },
    d => { d.inspection.result.solver_status = "NOT_RUN"; },
    d => { d.inspection.result.converged = false; },
    d => { d.inspection.result.artifacts[2].revision = digest("a"); },
    d => { d.inspection.proposal.execution.mesh_sizes_mm = [2, 1]; },
    d => { d.inspection.proposal.execution.mesh_sizes_mm[0] = 1; },
    d => { d.inspection.proposal.execution.history.times_s[2] = .6; },
    d => { d.envelope.result_sha256 = digest("c"); },
    d => { d.envelope.channels.pop(); }
  ]) { const data = j2Fixture(); mutate(data); j2Refused(data); }
  const coarse = j2Fixture([3, 2, 1]);
  for (const channel of coarse.envelope.channels) {
    channel.origin.mesh_index = 0; channel.origin.mesh_size_mm = 3;
    channel.origin.artifact = "simulation/level_0/parsed_history.json"; channel.origin.native_artifact = "simulation/level_0/worker_result.json";
    channel.location = channel.location.replace("mesh 2", "mesh 0");
  }
  // A well-formed native channel is not proof that a coarser result is the
  // history source. Full choices also bind the sealed request's finest level.
  assert.equal(controls.nativeChannelValid(coarse.envelope.channels[0], j2Backend), true); j2Refused(coarse);
});

test("direct J2 comparison metadata validation works without a manifest; retained choices pin parsed/raw/mesh hashes", () => {
  const data = j2Fixture(), channel = data.envelope.channels[4], artifacts = data.inspection.result.artifacts;
  assert.equal(controls.nativeChannelValid(channel, j2Backend), true);
  assert.equal(controls.nativeChannelValid(channel, j2Backend, artifacts), true);
  for (const entryIndex of [0, 1, 2, 3]) {
    const changed = structuredClone(data); changed.inspection.result.artifacts[entryIndex].sha256 = digest("9");
    assert.equal(controls.nativeChannelValid(changed.envelope.channels[4], j2Backend), true);
    assert.equal(controls.nativeChannelValid(changed.envelope.channels[4], j2Backend, changed.inspection.result.artifacts), false);
    j2Refused(changed);
  }
  for (const mutate of [
    d => { d.envelope.channels[0].origin.artifact = "simulation/level_1/parsed_history.json"; },
    d => { d.envelope.channels[0].origin.native_artifact = "simulation/level_0/../worker_result.json"; },
    d => { d.envelope.channels[0].origin.mesh_sha256 = digest("D"); },
    d => { d.inspection.result.artifacts.splice(3, 1); },
    d => { d.inspection.result.artifacts.push({ ...d.inspection.result.artifacts[0], path: "Simulation/level_0/parsed_history.json" }); }
  ]) { const changed = j2Fixture(); mutate(changed); j2Refused(changed); }
  assert.equal(controls.nativeChannelValid(channel, j2Backend, []), false);
});

test("J2 metadata refuses native/derived swaps, alternate components/units/frames and weighted or incomplete Gauss claims", () => {
  for (const [index, mutate] of [
    [0, c => { c.origin.kind = "DERIVED"; }], [0, c => { c.origin.native_field = "REAC_NODA.DX"; }],
    [0, c => { c.origin.aggregation = { operation: "arithmetic_mean" }; }], [0, c => { c.component = "FY"; }],
    [0, c => { c.origin.driver = "python"; }], [0, c => { c.location = "group X0.DY on finest declared mesh 0"; }],
    [4, c => { c.origin.kind = "NATIVE"; }], [4, c => { c.metric = "stress_history"; }],
    [4, c => { c.quantity = "strain"; }], [4, c => { c.unit = "Pa"; }], [4, c => { c.coordinate_frame = "verified sensor Cartesian"; }],
    [4, c => { c.measure = "volume average Cauchy stress"; }], [4, c => { c.origin.mapping = "NATIVE_SCALAR"; }],
    [4, c => { c.origin.aggregation.weighting = "VOLUME_WEIGHTED"; }], [4, c => { c.origin.aggregation.volume_average = true; }],
    [4, c => { c.origin.aggregation.coverage = "ONE_GAUSS_POINT"; }], [4, c => { c.origin.aggregation.point_count = 9; }],
    [4, c => { delete c.origin.aggregation; }], [10, c => { c.unit = "mm/mm"; }], [10, c => { c.origin.native_field = "VARI_ELGA.V2"; }]
  ]) {
    const data = j2Fixture(); mutate(data.envelope.channels[index]);
    assert.equal(controls.nativeChannelValid(data.envelope.channels[index], j2Backend), false); j2Refused(data);
  }
  const inconsistentCoverage = j2Fixture(); inconsistentCoverage.envelope.channels[4].origin.aggregation.point_count = 15;
  assert.equal(controls.nativeChannelValid(inconsistentCoverage.envelope.channels[4], j2Backend), true); j2Refused(inconsistentCoverage);
});

test("J2 seconds, native order identities and no-Newton initial state are exact, without interpolation or order renumbering", () => {
  for (const mutate of [
    c => { c.axis.quantity = "load_parameter"; }, c => { c.axis.unit = "ms"; }, c => { c.axis.semantics = "NATIVE_CURRENT_TIME"; },
    c => { c.axis.values[0] = .1; }, c => { c.axis.values[2] = .25; }, c => { c.values[2] = Infinity; },
    c => { c.values = new Array(4); }, c => { c.origin.actual_result_orders[2] = 7; },
    c => { c.origin.actual_result_orders[2] = "3"; }, c => { c.origin.actual_result_orders.pop(); },
    c => { c.initial_state.kind = "CONVERGED_NEWTON_INCREMENT"; }, c => { c.initial_state.index = 1; },
    c => { c.initial_state.actual_result_order = 1; }, c => { c.initial_state.time_s = .1; }
  ]) { const data = j2Fixture(); mutate(data.envelope.channels[0]); j2Refused(data); }
  const inconsistentOrders = j2Fixture(); inconsistentOrders.envelope.channels[1].origin.actual_result_orders[1] = 8;
  assert.equal(controls.nativeChannelValid(inconsistentOrders.envelope.channels[1], j2Backend), true); j2Refused(inconsistentOrders);
  const data = j2Fixture();
  assert.deepEqual(controls.channels(data.inspection, data.envelope)[0].origin.actual_result_orders, [0, 7, 3, 12]);
  assert.throws(() => controls.sampleChoice(data.inspection, data.envelope, "j2-gauss-mean-sixz", .5), /정수 표본/);
});

test("J2 build reuses declared common observations while retaining exact native/derived channel identity and native units", () => {
  for (const [channelId, unit] of [["j2-x0-fx", "N"], ["j2-gauss-mean-sixz", "MPa"], ["j2-gauss-mean-v1", "1"]]) {
    const data = j2Fixture(), input = j2Fields(channelId), original = structuredClone(data), originalInput = structuredClone(input);
    freeze(data); freeze(input);
    const request = controls.build(data.inspection, data.envelope, input);
    assert.deepEqual(request.response, { history_channel: channelId, sample_index: 2 });
    assert.equal(request.purpose, "GENERAL_CAE_RESEARCH"); assert.equal(request.observation.unit, unit);
    assert.equal(request.observation.value, -18.5); assert.equal(request.observation.component, input.component);
    assert.equal(request.observation.coordinate_frame, input.coordinateFrame); assert.equal(request.observation.location, input.location);
    assert.deepEqual(request.observation.axis, { quantity: "time", value: .55, unit: "s" });
    assert.equal(request.observation.source_kind, "SYNTHETIC"); assert.equal(request.experiment_id, "E-j2");
    assert.equal(JSON.stringify(request).includes("history_validation_sample"), false); assert.equal(Object.hasOwn(request.response, "metric"), false);
    request.observation.axis.value = 9;
    assert.deepEqual(data, original); assert.deepEqual(input, originalInput); assert.equal(data.inspection.result.decision, "NOT_RELEASED");
    assert.equal(data.inspection.result.validations[0].status, "UNKNOWN");
  }
  const data = j2Fixture();
  assert.throws(() => controls.build(data.inspection, data.envelope, { ...j2Fields(), axisValue: "" }), /명시|관측 시간/);
  assert.throws(() => controls.build(data.inspection, data.envelope, { ...j2Fields(), axisUnit: "ms" }), /관측 시간/);
});

test("verified rejected J2 histories remain readable with original invalid metrics but cannot create a comparison", () => {
  const data = j2Fixture(); data.inspection.result.status = "REJECTED";
  const original = structuredClone(data); freeze(data);
  assert.equal(controls.channels(data.inspection, data.envelope).length, 11);
  assert.equal(controls.sampleChoice(data.inspection, data.envelope, "j2-x0-fx", 1).value, -8);
  assert.throws(() => controls.build(data.inspection, data.envelope, j2Fields()), /새 관측 비교 저장은 허용하지/);
  assert.deepEqual(data, original); assert.equal(data.inspection.result.metrics.retained_validation_residual.valid, false);
  for (const status of ["FAILED_EXECUTION", "CANCELLED", "COMPLETED"]) {
    const changed = j2Fixture(); changed.inspection.result.status = status; j2Refused(changed);
  }
});

test("direct J2 metadata refuses accessor/prototype/cyclic data and browser exports keep the same four-operation API", () => {
  const data = j2Fixture(); let reads = 0;
  const getter = structuredClone(data.envelope.channels[0]);
  Object.defineProperty(getter.origin, "mesh_index", { enumerable: true, get() { reads += 1; return 0; } });
  assert.equal(controls.nativeChannelValid(getter, j2Backend), false); assert.equal(reads, 0);
  assert.equal(controls.nativeChannelValid(Object.create(data.envelope.channels[0]), j2Backend), false);
  const cycle = structuredClone(data.envelope.channels[0]); cycle.origin.extra = cycle;
  assert.equal(controls.nativeChannelValid(cycle, j2Backend), false);
  const dangerous = structuredClone(data.envelope.channels[0]); Object.defineProperty(dangerous.origin, "__proto__", { value: {}, enumerable: true });
  assert.equal(controls.nativeChannelValid(dangerous, j2Backend), false);
  const artifactGetter = structuredClone(data.inspection.result.artifacts);
  Object.defineProperty(artifactGetter[0], "sha256", { enumerable: true, get() { reads += 1; return digest("a"); } });
  assert.equal(controls.nativeChannelValid(data.envelope.channels[0], j2Backend, artifactGetter), false); assert.equal(reads, 0);
  const context = vm.createContext({ window: {}, inspectionJson: JSON.stringify(data.inspection), envelopeJson: JSON.stringify(data.envelope), fieldsJson: JSON.stringify(j2Fields()) });
  for (const filename of ["result-presentation.js", "observation-controls.js", "history-controls.js"]) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, "../apps/lab/static", filename), "utf8"), context);
  }
  const request = vm.runInContext("window.historyControls.build(JSON.parse(inspectionJson), JSON.parse(envelopeJson), JSON.parse(fieldsJson))", context);
  assert.deepEqual(JSON.parse(JSON.stringify(request)), controls.build(data.inspection, data.envelope, j2Fields()));
  assert.deepEqual(Object.keys(controls).sort(), ["build", "channels", "nativeChannelValid", "sampleChoice"]);
});

test("OpenRadioss retained half-step velocity, derived force sign and native wall impulse are unchanged by J2 dispatch", () => {
  const native = { id: "radioss-center-vz", label: "TEST_ONLY retained velocity", metric: null, quantity: "velocity", component: "Z",
    measure: "raw leapfrog velocity", coordinate_frame: "global Cartesian SI; sensor/world alignment UNKNOWN", location: "main node 9", unit: "m/s",
    axis: { quantity: "time", unit: "s", values: [0, .00005, .00015], semantics: "NATIVE_HALF_STEP_VELOCITY_TIME" }, values: [0, -.00049, -.00147],
    initial_state: { index: 0, kind: "NATIVE_DECLARED_INITIAL_STATE" }, origin: { kind: "NATIVE", driver: "openradioss", artifact: "simulation/parsed_history.json",
      sha256: digest("a"), native_artifact: "simulation/dropT01", native_sha256: digest("c"), native_field: "velocity_m_s", mapping: "EXACT_RETAINED_TH40_SAMPLE" } };
  const force = { ...structuredClone(native), id: "radioss-ground-fz", quantity: "force", component: "global Z", unit: "N",
    measure: "native spring axial force with explicit sign mapping", location: "spring element 2 / moving body",
    axis: { ...native.axis, semantics: "NATIVE_CURRENT_TIME" }, origin: { ...native.origin, kind: "DERIVED", native_field: "spring_axial_force_n", mapping: "GLOBAL_UPWARD_FORCE_EQUALS_MINUS_LOCAL_FX" } };
  const impulse = { ...structuredClone(native), id: "radioss-wall-fnz", quantity: "impulse", component: "FNZ", unit: "N s",
    measure: "signed native cumulative wall impulse", location: "rigid wall 1", axis: { ...native.axis, semantics: "NATIVE_CURRENT_TIME" },
    origin: { ...native.origin, native_field: "RWALL/FNZ" } };
  const legacy = fixture(), { inspection, envelope } = legacy;
  inspection.result.provenance.adapter = inspection.proposal.physics.backend = "explicit.openradioss";
  inspection.result.metrics = {}; inspection.result.artifacts = [{ path: native.origin.artifact, sha256: digest("a") }, { path: native.origin.native_artifact, sha256: digest("c") }];
  envelope.channels = [native, force, impulse];
  assert.deepEqual(controls.channels(inspection, envelope), envelope.channels);
  assert.equal(controls.nativeChannelValid(native, "explicit.openradioss"), true);
  assert.equal(controls.nativeChannelValid(force, "explicit.openradioss"), true); assert.equal(controls.nativeChannelValid(impulse, "explicit.openradioss"), true);
  assert.deepEqual(controls.sampleChoice(inspection, envelope, native.id, 1).axis, { quantity: "time", value: .00005, unit: "s" });
  assert.doesNotMatch(controls.sampleChoice(inspection, envelope, native.id, 0).label, /Newton|재료 적분/);
  const request = controls.build(inspection, envelope, { ...fields(), channelId: native.id, axisValue: ".00005" });
  assert.equal(request.observation.unit, "m/s"); assert.equal(request.observation.axis.value, .00005);
  assert.deepEqual(request.response, { history_channel: native.id, sample_index: 1 });
  const wrongForce = structuredClone(force); wrongForce.origin.kind = "NATIVE";
  assert.equal(controls.nativeChannelValid(wrongForce, "explicit.openradioss"), false);
  const wrongImpulse = structuredClone(impulse); wrongImpulse.unit = "N";
  assert.equal(controls.nativeChannelValid(wrongImpulse, "explicit.openradioss"), false);
});
