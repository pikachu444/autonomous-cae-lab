"use strict";

// Typed source controls only. No material measurement, native FE or browser is run.
const test = require("node:test"), assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const vm = require("node:vm");
const controls = require("../apps/lab/static/plasticity-controls.js");
const copy = value => structuredClone(value);
function settings() {
  return { mode: "selected_mesh", case: "uniaxial_j2_isotropic_hardening", dimensions_mm: [20, 4, 2],
    material: { youngs_modulus_mpa: 210000, poisson_ratio: 0.3, yield_stress_mpa: 250, plastic_modulus_mpa: 1000 },
    history: { times_s: [0, 0.125, 1, 2, 3, 4.5, 5, 6], axial_strain: [-0, 0.003, 0.003, 0.001, 0, -0.006, -0.006, 0.004] },
    mesh_sizes_mm: [2], limits: { displacement_relative: 1e-7, displacement_absolute_mm: 1e-10, stress_relative: 1e-7,
      stress_absolute_mpa: 1e-8, plastic_strain_absolute: 1e-9, reaction_relative: 1e-7, reaction_absolute_n: 1e-8,
      mesh_agreement_relative: 1e-7, plastic_dissipation_relative: 1e-6, plastic_dissipation_absolute_mpa: 1e-8 },
    input_provenance: { origin: "SYNTHETIC", reference: "  SOURCE_TEST_ONLY · 가정 J2 입력\n원문 공백 보존  " } };
}
function freeze(value) { if (value && typeof value === "object") { Object.values(value).forEach(freeze); Object.freeze(value); } return value; }

test("validate returns an independent selected-mode clone without changing frozen inputs or limits", () => {
  const baseline = freeze(settings()), before = copy(baseline), result = controls.validate(baseline);
  assert.deepEqual(result, before); assert.notEqual(result, baseline); assert.notEqual(result.limits, baseline.limits);
  result.material.plastic_modulus_mpa = 2500; result.history.axial_strain[1] = 0.009; result.limits.stress_relative = 1;
  assert.deepEqual(baseline, before); assert.equal(baseline.material.plastic_modulus_mpa, 1000);
});

test("loading, hold, unloading and signed reversal roundtrip with original H and source text", () => {
  const baseline = settings(), before = copy(baseline), fields = controls.toFields(baseline), restored = controls.fromFields(fields, baseline);
  assert.equal(fields.plastic_modulus, "1000"); assert.equal(restored.material.plastic_modulus_mpa, 1000);
  assert.match(fields.history, /^time_s,axial_strain\n0,-0\n/);
  assert.deepEqual(restored.history, baseline.history); assert(Object.is(restored.history.axial_strain[0], -0));
  assert.equal(fields.reference, baseline.input_provenance.reference); assert.equal(restored.input_provenance.reference, fields.reference);
  assert.deepEqual(restored, baseline); assert.deepEqual(baseline, before);
  assert.equal(Object.hasOwn(restored, "reference"), false); assert.equal(Object.hasOwn(restored, "validation"), false);
});

test("editing declared values clones the baseline and preserves its exact ten current limits", () => {
  const baseline = settings(), before = copy(baseline), fields = controls.toFields(baseline);
  Object.assign(fields, { length_x: "3.2e1", length_y: "5", length_z: "2.5", youngs_modulus: "175000", poisson_ratio: "-.2",
    yield_stress: "225", plastic_modulus: "2500", mesh_size: "1.25", origin: "MEASURED_REPORTED",
    reference: " \n사용자가 보고한 값 · 자격 미확인\n ", history: "0 0\n.5 +2.5e-3\n1 +2.5e-3\n2 -1e-3\n3 0" });
  const result = controls.fromFields(fields, baseline);
  assert.deepEqual(result.dimensions_mm, [32, 5, 2.5]); assert.deepEqual(result.mesh_sizes_mm, [1.25]);
  assert.deepEqual(result.material, { youngs_modulus_mpa: 175000, poisson_ratio: -0.2, yield_stress_mpa: 225, plastic_modulus_mpa: 2500 });
  assert.deepEqual(result.history, { times_s: [0, 0.5, 1, 2, 3], axial_strain: [0, 0.0025, 0.0025, -0.001, 0] });
  assert.equal(result.input_provenance.origin, "MEASURED_REPORTED"); assert.equal(result.input_provenance.reference, fields.reference);
  assert.deepEqual(result.limits, baseline.limits); assert.notEqual(result.limits, baseline.limits); assert.deepEqual(baseline, before);
  assert.throws(() => controls.fromFields({ ...fields, limits: { ...baseline.limits, stress_relative: 1 } }, baseline), /11개 입력/);
  assert.deepEqual(baseline, before);
});

test("history accepts exact optional header, CRLF, decimal/exponent columns and 32 declared instants", () => {
  const baseline = settings(), fields = controls.toFields(baseline);
  fields.history = "time_s,axial_strain\r\n0,0\r\n1e-2, .01\r\n.5,-.01\r\n1,+.01\r\n";
  assert.deepEqual(controls.fromFields(fields, baseline).history, { times_s: [0, 0.01, 0.5, 1], axial_strain: [0, 0.01, -0.01, 0.01] });
  fields.history = Array.from({ length: 32 }, (_, index) => `${index},${index === 0 ? 0 : index % 2 ? -0.001 : 0.001}`).join("\n");
  assert.equal(controls.fromFields(fields, baseline).history.times_s.length, 32);
  fields.history += "\n32,0"; assert.throws(() => controls.fromFields(fields, baseline), /2–32행/);
});

test("malformed history cannot drop columns, skip empty rows, execute text or silently reuse a valid history", () => {
  const baseline = settings(), before = copy(baseline), original = controls.toFields(baseline);
  for (const history of ["time_s, axial_strain\n0,0\n1,.001", "time_s,axial_strain\n0,0\ntime_s,axial_strain\n1,.001",
      "0,\n1,.001", "0\n1 .001", "0,0,0\n1,.001", "0,0\n\n1,.001", "0,0\n1,process.exit()",
      "0,0\n1,Infinity", "0,0\n1,NaN", "0,0\n1,0x10", "0,0\n1,1e999", "time_s,axial_strain", ""]) {
    assert.throws(() => controls.fromFields({ ...original, history }, baseline)); assert.deepEqual(baseline, before);
  }
});

test("history association, initial zero state, strictly increasing time and small signed strain remain mandatory", () => {
  const baseline = settings(), original = controls.toFields(baseline);
  for (const history of ["1,0\n2,.001", "0,.001\n1,.001", "0,0\n0,.001", "0,0\n1,.001\n.5,0", "0,0\n1,-.010001"]) {
    assert.throws(() => controls.fromFields({ ...original, history }, baseline));
  }
  const mismatched = settings(); mismatched.history.axial_strain.pop(); assert.throws(() => controls.validate(mismatched), /대응하는/);
});

test("benchmark, sweep, wrong typed case IDs and extra settings cannot acquire selected-mode meaning", () => {
  for (const change of [value => { delete value.mode; delete value.input_provenance; value.mesh_sizes_mm = [2, 1]; },
      value => { value.mode = "benchmark"; }, value => { value.case = ["uniaxial_j2_isotropic_hardening"]; },
      value => { value.case = new String(value.case); }, value => { value.case = "uniaxial_j2_isotropic_hardening_other"; },
      value => { value.reference_agreement = "PASS"; }, value => { value.mesh_sizes_mm = [2, 1]; },
      value => { value.limits.unvalidated_extra = 1; }]) {
    const input = settings(); change(input); assert.throws(() => controls.toFields(input));
  }
});

test("finite typed material, positive geometry/mesh and retained positive limits reject coercion and impossible bounds", () => {
  for (const change of [value => { value.material.youngs_modulus_mpa = true; }, value => { value.material.youngs_modulus_mpa = 0; },
      value => { value.material.poisson_ratio = -1; }, value => { value.material.poisson_ratio = 0.5; },
      value => { value.material.yield_stress_mpa = Infinity; }, value => { value.material.plastic_modulus_mpa = -1; },
      value => { value.dimensions_mm[1] = "4"; }, value => { value.dimensions_mm[2] = 0; },
      value => { value.mesh_sizes_mm[0] = 2.01; }, value => { value.limits.stress_relative = 0; },
      value => { value.limits.plastic_dissipation_relative = NaN; }]) {
    const input = settings(); change(input); assert.throws(() => controls.validate(input));
  }
  const baseline = settings(), fields = controls.toFields(baseline);
  for (const [key, value] of [["youngs_modulus", ""], ["length_x", "0x20"], ["plastic_modulus", "1e999"], ["mesh_size", 1], ["yield_stress", true]]) {
    assert.throws(() => controls.fromFields({ ...fields, [key]: value }, baseline));
  }
});

test("declared origins preserve reference text and do not manufacture measured qualification", () => {
  for (const origin of ["ASSUMED", "MEASURED_REPORTED", "PUBLISHED_REFERENCE", "SYNTHETIC"]) {
    const input = settings(); input.input_provenance = { origin, reference: " x" + "文".repeat(1996) + " \n" };
    const restored = controls.fromFields(controls.toFields(input), input);
    assert.deepEqual(restored.input_provenance, input.input_provenance); assert.equal(Object.hasOwn(restored, "qualification"), false);
  }
  const unicode = settings(); unicode.input_provenance.reference = "🧪".repeat(2000);
  assert.equal(controls.toFields(unicode).reference, unicode.input_provenance.reference);
  unicode.input_provenance.reference += "🧪"; assert.throws(() => controls.validate(unicode));
  for (const source of [{ origin: "QUALIFIED", reference: "test" }, { origin: "ASSUMED", reference: " " }, { origin: "ASSUMED", reference: "x".repeat(2001) },
      { origin: "ASSUMED", reference: 123 }, { origin: "SYNTHETIC", reference: "test", measured: true }]) {
    const input = settings(); input.input_provenance = source; assert.throws(() => controls.validate(input));
  }
});

test("inherited objects, arrays with active prototypes, sparse arrays and getters are rejected before active property reads", () => {
  let reads = 0;
  const getter = settings(); Object.defineProperty(getter.material, "youngs_modulus_mpa", { enumerable: true, get() { reads++; return 210000; } });
  assert.throws(() => controls.validate(getter)); assert.equal(reads, 0);
  assert.throws(() => controls.validate(Object.create(settings())));
  const array = settings(); Object.setPrototypeOf(array.history.times_s, Object.create(Array.prototype, { every: { get() { reads++; return () => true; } } }));
  assert.throws(() => controls.validate(array)); assert.equal(reads, 0);
  const sparse = settings(); delete sparse.history.axial_strain[1]; assert.throws(() => controls.validate(sparse));
  const unsafe = settings(); unsafe.material = JSON.parse('{"__proto__":{"youngs_modulus_mpa":210000}}'); assert.throws(() => controls.validate(unsafe));
  const fields = controls.toFields(settings()); Object.defineProperty(fields, "history", { enumerable: true, get() { reads++; return "0,0\n1,.001"; } });
  assert.throws(() => controls.fromFields(fields, settings())); assert.equal(reads, 0);
});

test("browser and CommonJS expose exactly three pure operations with the same typed request meaning", () => {
  const browser = { window: {} };
  vm.runInNewContext(readFileSync(require.resolve("../apps/lab/static/plasticity-controls.js"), "utf8"), browser);
  const api = browser.window.plasticityControls, baseline = settings();
  assert.deepEqual(Object.keys(api), ["validate", "toFields", "fromFields"]); assert.deepEqual(Object.keys(controls), Object.keys(api));
  assert.equal(Object.isFrozen(api), true); assert.equal(Object.isFrozen(controls), true);
  assert.equal(JSON.stringify(api.toFields(baseline)), JSON.stringify(controls.toFields(baseline)));
  const restored = api.fromFields(controls.toFields(baseline), baseline);
  assert.equal(JSON.stringify(restored), JSON.stringify(baseline)); assert(Object.is(restored.history.axial_strain[0], -0));
});
