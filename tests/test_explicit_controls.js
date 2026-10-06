"use strict";

// TEST_ONLY typed inputs. These are not native results, measured loads or
// qualification of deformable bodies, surface contact or a physical specimen.
const test = require("node:test"), assert = require("node:assert/strict");
const { readFileSync } = require("node:fs"), vm = require("node:vm");
const controls = require("../apps/lab/static/explicit-controls.js");
const copy = value => structuredClone(value);
const flight = "rigid_cube_freefall", compliant = "rigid_cube_compliant_stop";
function settings(caseId = flight) {
  const spring = caseId === compliant, end = spring ? .5 : .2;
  return { mode: "selected_history", case: caseId, edge_m: .1, mass_kg: 1, center_height_m: 1, initial_velocity_m_s: -0,
    end_time_s: end, time_step_s: .0001, history_interval_s: .0001, limits: { mass_relative: 1e-8 },
    acceleration_history: { time_s: [0, end / 4, end / 2, end], acceleration_z_m_s2: [-9.81, -0, -0, 4.905] },
    input_provenance: { origin: "SYNTHETIC", reference: "  SOURCE_TEST_ONLY · 선언 하중\n원문 공백 보존  " },
    ...(spring ? { spring_stiffness_n_m: 10000, spring_mass_kg: .002 } : {}) };
}
function freeze(value) { if (value && typeof value === "object") { Object.values(value).forEach(freeze); Object.freeze(value); } return value; }
function withEnd(value, end) { value.end_time_s = end; value.acceleration_history = { time_s: [0, end], acceleration_z_m_s2: [-9.81, -9.81] }; return value; }

test("validate independently clones frozen selected settings, source, limits and signed loads", () => {
  const baseline = freeze(settings()), original = copy(baseline), accepted = controls.validate(baseline);
  assert.deepEqual(accepted, original); assert.notEqual(accepted, baseline); assert.notEqual(accepted.limits, baseline.limits);
  assert.notEqual(accepted.acceleration_history, baseline.acceleration_history); assert.notEqual(accepted.input_provenance, baseline.input_provenance);
  accepted.acceleration_history.acceleration_z_m_s2[1] = 20; accepted.limits.mass_relative = .1; accepted.input_provenance.reference = "edited";
  assert.deepEqual(baseline, original); assert.equal(Object.hasOwn(accepted, "gravity_m_s2"), false);
});

test("both existing topologies roundtrip exact fixed SI values, signed zero and source text without response substitution", () => {
  for (const caseId of [flight, compliant]) {
    const baseline = settings(caseId), original = copy(baseline), fields = controls.toFields(baseline), restored = controls.fromFields(fields, baseline);
    assert.ok(Object.values(fields).every(value => typeof value === "string")); assert.equal(fields.initial_velocity_m_s, "-0");
    assert.match(fields.history, /^time_s,acceleration_z_m_s2\n0,-9.81\n/); assert.match(fields.history, /,-0\n/);
    assert.deepEqual(restored, baseline); assert.equal(Object.is(restored.initial_velocity_m_s, -0), true);
    assert.equal(Object.is(restored.acceleration_history.acceleration_z_m_s2[1], -0), true);
    assert.equal(fields.reference, baseline.input_provenance.reference); assert.equal(restored.input_provenance.reference, fields.reference);
    assert.deepEqual(baseline, original); assert.equal(Object.hasOwn(fields, "limits"), false); assert.equal(Object.hasOwn(fields, "gravity_m_s2"), false);
    assert.equal(Object.hasOwn(fields, "case"), false); assert.equal(Object.hasOwn(fields, "spring_mass_kg"), false);
    for (const key of ["reference", "response", "validation", "decision", "surface_contact"]) assert.equal(Object.hasOwn(restored, key), false);
    assert.equal(Object.hasOwn(fields, "spring_stiffness_n_m"), caseId === compliant);
  }
});

test("edits keep the baseline topology and limits while preserving the explicit signed piecewise-linear load", () => {
  const baseline = freeze(settings()), original = copy(baseline), fields = controls.toFields(baseline);
  Object.assign(fields, { edge_m: ".25", mass_kg: "2", center_height_m: "1.5", initial_velocity_m_s: "+4.5", end_time_s: ".5",
    time_step_s: "1e-4", history_interval_s: "7e-4", origin: "MEASURED_REPORTED", reference: " \n원 측정 보고 · 정렬 및 물리 자격 미확인\n ",
    history: "0 -2e1\n.1 -2e1\n.2 0\n.3 +2e1\n.5 -0" });
  const result = controls.fromFields(fields, baseline);
  assert.equal(result.edge_m, .25); assert.equal(result.initial_velocity_m_s, 4.5); assert.equal(result.history_interval_s, .0007);
  assert.deepEqual(result.acceleration_history, { time_s: [0, .1, .2, .3, .5], acceleration_z_m_s2: [-20, -20, 0, 20, -0] });
  assert.equal(result.input_provenance.origin, "MEASURED_REPORTED"); assert.equal(result.input_provenance.reference, fields.reference);
  assert.deepEqual(result.limits, baseline.limits); assert.notEqual(result.limits, baseline.limits); assert.equal(result.case, flight);
  assert.equal(Object.hasOwn(result, "gravity_m_s2"), false); assert.deepEqual(baseline, original);
  assert.throws(() => controls.fromFields({ ...fields, limits: { mass_relative: .1 } }, baseline), /폼의 명시한/);
  const stop = settings(compliant), stopFields = controls.toFields(stop); stopFields.spring_stiffness_n_m = "2.5e4";
  const editedStop = controls.fromFields(stopFields, stop);
  assert.equal(editedStop.spring_stiffness_n_m, 25000); assert.equal(editedStop.spring_mass_kg, .002); assert.deepEqual(editedStop.limits, stop.limits);
});

test("history supports exact optional header, CRLF, decimal/exponent columns and sixteen explicit instants", () => {
  const baseline = settings(), fields = controls.toFields(baseline);
  fields.history = "time_s,acceleration_z_m_s2\r\n0,-1e2\r\n.1,+100\r\n2e-1,-0\r\n";
  assert.deepEqual(controls.fromFields(fields, baseline).acceleration_history, { time_s: [0, .1, .2], acceleration_z_m_s2: [-100, 100, -0] });
  const longer = withEnd(settings(), 1), longerFields = controls.toFields(longer);
  longerFields.history = Array.from({ length: 16 }, (_, i) => `${i / 15},${i % 2 ? -100 : 100}`).join("\n");
  assert.equal(controls.fromFields(longerFields, longer).acceleration_history.time_s.length, 16);
  longerFields.history += "\n1,0"; assert.throws(() => controls.fromFields(longerFields, longer), /2–16행/);
});

test("malformed or unit-bearing history cannot execute text, drop rows or silently reuse the baseline load", () => {
  const baseline = settings(), original = copy(baseline), fields = controls.toFields(baseline);
  for (const history of ["", "time_s,acceleration_z_m_s2", "time_s, acceleration_z_m_s2\n0,-9.81\n.2,0",
    "time_s,acceleration_z_m_s2\n0,-9.81\ntime_s,acceleration_z_m_s2\n.2,0", "0,\n.2,0", "0\n.2,0", "0,-9.81,0\n.2,0",
    "0,-9.81\n\n.2,0", "0,-9.81\n.2,globalThis.executed=true", "0,-9.81\n.2,NaN", "0,-9.81\n.2,Infinity",
    "0,-9.81\n.2,1e309", "0,-9.81\n.2,0x10", "0s,-9.81\n.2,0", "0,-9.81m/s2\n.2,0", "time_ms,acceleration_z_m_s2\n0,-9.81\n200,0"]) {
    assert.throws(() => controls.fromFields({ ...fields, history }, baseline)); assert.deepEqual(baseline, original);
  }
  assert.equal(globalThis.executed, undefined);
});

test("acceleration rows bind strictly increasing seconds from zero through the exact declared end", () => {
  const baseline = settings(), fields = controls.toFields(baseline);
  for (const history of [".1,0\n.2,0", "0,-9.81\n0,0", "0,-9.81\n.15,0\n.1,0\n.2,0", "0,-9.81\n.1,0", "0,-9.81\n.20001,0",
    "0,-100.001\n.2,0", "0,-9.81\n.2,100.001"]) assert.throws(() => controls.fromFields({ ...fields, history }, baseline));
  for (const mutate of [s => { s.acceleration_history.acceleration_z_m_s2.pop(); }, s => { s.acceleration_history.time_s = new Array(4); },
    s => { s.acceleration_history.time_s[1] = "0.05"; }, s => { s.acceleration_history.acceleration_z_m_s2[1] = true; },
    s => { s.acceleration_history.acceleration_z_m_s2[1] = NaN; }]) {
    const invalid = settings(); mutate(invalid); assert.throws(() => controls.validate(invalid));
  }
  assert.equal(controls.validate(withEnd(settings(), .001)).acceleration_history.time_s.at(-1), .001);
});

test("fixed SI scalar bounds require finite typed numbers and editable decimal strings rather than inferred units", () => {
  for (const [key, value] of [["edge_m", .000999], ["edge_m", 1.00001], ["mass_kg", .000999], ["mass_kg", 100.1],
    ["center_height_m", .05], ["center_height_m", 10.1], ["initial_velocity_m_s", -10.001], ["initial_velocity_m_s", 10.001],
    ["end_time_s", .000999], ["end_time_s", 2.1], ["time_step_s", .0000009], ["time_step_s", .00101],
    ["history_interval_s", .00009], ["history_interval_s", .01001], ["mass_kg", "1"], ["initial_velocity_m_s", true], ["edge_m", Infinity]]) {
    const invalid = settings(); invalid[key] = value; assert.throws(() => controls.validate(invalid));
  }
  for (const [key, value] of [["edge_m", "100 mm"], ["mass_kg", "1kg"], ["center_height_m", ""], ["initial_velocity_m_s", 0],
    ["time_step_s", "NaN"], ["history_interval_s", "1e309"]]) {
    const baseline = settings(), fields = controls.toFields(baseline); fields[key] = value; assert.throws(() => controls.fromFields(fields, baseline));
  }
  const baseline = settings(), fields = controls.toFields(baseline);
  assert.throws(() => controls.fromFields({ ...fields, unit: "mm" }, baseline), /폼의 명시한/);
  const wrongNames = { ...fields, edge_mm: "100" }; delete wrongNames.edge_m;
  assert.throws(() => controls.fromFields(wrongNames, baseline), /폼의 명시한/);
  const signed = settings(); signed.initial_velocity_m_s = 10; assert.equal(controls.validate(signed).initial_velocity_m_s, 10);
});

test("resource and integer terminal-cycle admission preserve existing budgets without synthesizing native clocks", () => {
  const atBudget = withEnd(settings(), 2); atBudget.time_step_s = .00001; atBudget.history_interval_s = .0002;
  assert.equal(controls.validate(atBudget).end_time_s, 2);
  for (const mutate of [s => { s.time_step_s = 1e-6; }, s => { s.history_interval_s = .0001; }]) {
    const invalid = copy(atBudget); mutate(invalid); assert.throws(() => controls.validate(invalid), /예산/);
  }
  const tooFew = withEnd(settings(), .009); tooFew.history_interval_s = .001;
  assert.throws(() => controls.validate(tooFew), /예산/);
  const incompleteCycle = withEnd(settings(), .02001);
  assert.throws(() => controls.validate(incompleteCycle), /정수 cycle/);
  const nonIntegerHistoryRatio = withEnd(settings(), .5); nonIntegerHistoryRatio.history_interval_s = .0007;
  assert.equal(controls.validate(nonIntegerHistoryRatio).history_interval_s, .0007);
  assert.equal(Object.hasOwn(controls.validate(nonIntegerHistoryRatio), "expected_history_times"), false);
});

test("the compliant topology keeps fixed spring mass, explicit stiffness and history every capped cycle", () => {
  for (const [key, value] of [["spring_mass_kg", .004], ["spring_mass_kg", ".002"], ["spring_stiffness_n_m", 999],
    ["spring_stiffness_n_m", 1000001], ["spring_stiffness_n_m", true], ["history_interval_s", .0002]]) {
    const invalid = settings(compliant); invalid[key] = value; assert.throws(() => controls.validate(invalid));
  }
  for (const stiffness of [1000, 1000000]) {
    const valid = settings(compliant); valid.spring_stiffness_n_m = stiffness; assert.equal(controls.validate(valid).spring_stiffness_n_m, stiffness);
  }
  const baseline = settings(compliant), fields = controls.toFields(baseline); fields.time_step_s = ".00005";
  assert.throws(() => controls.fromFields(fields, baseline), /이력 간격=dt/);
  fields.history_interval_s = ".00005";
  assert.equal(controls.fromFields(fields, baseline).time_step_s, .00005);
  assert.throws(() => controls.fromFields({ ...fields, spring_mass_kg: ".004" }, baseline), /고정 질량/);
});

test("benchmark, gravity, arbitrary cases and reference limits cannot silently acquire selected-history meaning", () => {
  for (const change of [s => { delete s.mode; }, s => { s.mode = "benchmark"; }, s => { s.case = "rigid_cube_ground_stop"; },
    s => { s.case = [flight]; }, s => { s.case = flight + "\n"; }, s => { s.case = "deformable_surface_contact"; },
    s => { s.gravity_m_s2 = 9.81; }, s => { s.limits.energy_abs_j = .01; }, s => { s.limits.mass_relative = 1e-6; },
    s => { s.acceleration_history.unit = "g"; }]) {
    const invalid = settings(); change(invalid); assert.throws(() => controls.validate(invalid));
    assert.throws(() => controls.toFields(invalid)); assert.throws(() => controls.fromFields(controls.toFields(settings()), invalid));
  }
  // Selected flight does not borrow the benchmark's analytical before-contact
  // gate or replace the user's acceleration with constant gravity.
  const afterGroundHeight = withEnd(settings(), .7); afterGroundHeight.initial_velocity_m_s = -1;
  assert.equal(controls.validate(afterGroundHeight).end_time_s, .7);
  const original = settings(), fields = controls.toFields(original);
  assert.throws(() => controls.fromFields({ ...fields, gravity_m_s2: "9.81" }, original), /폼의 명시한/);
});

test("source origins and original references remain explicit unqualified declarations with a codepoint bound", () => {
  for (const origin of ["ASSUMED", "MEASURED_REPORTED", "PUBLISHED_REFERENCE", "SYNTHETIC"]) {
    const baseline = settings(); baseline.input_provenance.origin = origin;
    const fields = controls.toFields(baseline), result = controls.fromFields(fields, baseline);
    assert.equal(result.input_provenance.origin, origin); assert.equal(result.input_provenance.reference, baseline.input_provenance.reference);
    assert.equal(Object.hasOwn(result.input_provenance, "qualification"), false);
  }
  for (const source of [{ origin: "measured", reference: "TEST_ONLY" }, { origin: "MEASURED_REPORTED", reference: " \n " },
    { origin: "SYNTHETIC", reference: "x".repeat(2001) }, { origin: "ASSUMED", reference: 2 },
    { origin: "SYNTHETIC", reference: "TEST_ONLY", qualified: true }]) {
    const invalid = settings(); invalid.input_provenance = source; assert.throws(() => controls.validate(invalid), /출처/);
  }
  const astral = settings(); astral.input_provenance.reference = "🧪".repeat(2000);
  assert.equal(controls.fromFields(controls.toFields(astral), astral).input_provenance.reference, astral.input_provenance.reference);
  astral.input_provenance.reference += "🧪"; assert.throws(() => controls.validate(astral), /2000자/);
});

test("inherited, executable, sparse, cyclic and dangerous typed inputs are rejected without invoking accessors", () => {
  const baseline = settings(), fields = controls.toFields(baseline); let reads = 0;
  const getter = copy(baseline); Object.defineProperty(getter, "case", { enumerable: true, get() { reads += 1; return flight; } });
  assert.throws(() => controls.validate(getter), /JSON/); assert.equal(reads, 0);
  const fieldGetter = copy(fields); Object.defineProperty(fieldGetter, "history", { enumerable: true, get() { reads += 1; return fields.history; } });
  assert.throws(() => controls.fromFields(fieldGetter, baseline), /문자열 입력/); assert.equal(reads, 0);
  assert.throws(() => controls.validate(Object.create(baseline)), /JSON/);
  assert.throws(() => controls.fromFields(Object.create(fields), baseline), /문자열 입력/);
  const custom = Object.assign(new (class Settings {})(), baseline); assert.throws(() => controls.validate(custom), /JSON/);
  const cyclic = copy(baseline); cyclic.acceleration_history.extra = cyclic; assert.throws(() => controls.validate(cyclic), /JSON/);
  for (const key of ["__proto__", "prototype", "constructor"]) {
    const bad = copy(baseline); Object.defineProperty(bad.input_provenance, key, { value: { polluted: true }, enumerable: true });
    assert.throws(() => controls.validate(bad), /JSON/); assert.equal({}.polluted, undefined);
  }
  const sparse = copy(baseline); delete sparse.acceleration_history.time_s[1]; assert.throws(() => controls.validate(sparse), /JSON/);
  const executable = copy(baseline); executable.input_provenance.reference = () => "TEST_ONLY"; assert.throws(() => controls.validate(executable), /JSON/);
  const baselineAfter = copy(baseline); assert.deepEqual(baselineAfter, settings());
});

test("browser and CommonJS expose the same three pure helpers and support explicit condition reuse", () => {
  const context = vm.createContext({ window: {} });
  vm.runInContext(readFileSync(require.resolve("../apps/lab/static/explicit-controls.js"), "utf8"), context);
  const browser = context.window.explicitControls;
  assert.deepEqual(Object.keys(controls), ["validate", "toFields", "fromFields"]); assert.equal(Object.isFrozen(controls), true);
  assert.equal(typeof browser.validate, "function"); assert.equal(typeof browser.toFields, "function"); assert.equal(typeof browser.fromFields, "function");
  for (const caseId of [flight, compliant]) {
    const baseline = freeze(settings(caseId)), fields = browser.toFields(baseline);
    assert.deepEqual(copy(browser.fromFields(fields, baseline)), controls.fromFields(controls.toFields(baseline), baseline));
    fields.reference += "\n독립 새 선언";
    const changed = browser.fromFields(fields, baseline); assert.equal(changed.input_provenance.reference, fields.reference);
    assert.notEqual(changed.input_provenance, baseline.input_provenance); assert.equal(baseline.input_provenance.reference, settings(caseId).input_provenance.reference);
  }
});
