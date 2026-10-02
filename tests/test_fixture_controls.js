"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { validate, toFields, fromFields, verifyStressField } = require("../apps/lab/static/fixture-controls.js");
const material = JSON.parse(readFileSync(require.resolve("../plugins/fixture_design/upstream/examples/printed_material_ASSUMED.json"), "utf8"));
const settings = () => ({ load: { force_per_support_N: 100, source: "Illustrative, not measured" }, material: { ...material }, mesh: { max_sizes_mm: [4, 3, 2] } });
test("pinned material, exact provenance and existing settings survive a form round trip", () => {
  const original = settings(); original.material.note = "keep original input metadata";
  assert.deepEqual(fromFields(toFields(original), original), original);
});
test("condition edits preserve provenance and numerical settings without inventing a verdict", () => {
  const original = settings(), fields = toFields(original);
  fields.force_N = "125"; fields.E_3_MPa = "1200"; fields.mesh_sizes = "4, 3 2, 1.5";
  const changed = fromFields(fields, original);
  assert.equal(changed.load.force_per_support_N, 125);
  assert.equal(changed.material.E_3_MPa, 1200);
  assert.equal(changed.material.qualification, "ASSUMED_NOT_MEASURED");
  assert.deepEqual(changed.mesh.max_sizes_mm, [4, 3, 2, 1.5]);
  assert.equal(original.load.force_per_support_N, 100);
});
test("switching to an explicitly entered isotropic material drops incompatible constants", () => {
  const original = settings(), fields = { ...toFields(original), model: "isotropic", elastic_modulus_MPa: "210000", poisson_ratio: "0.3" };
  const changed = fromFields(fields, original);
  assert.equal(changed.material.elastic_modulus_MPa, 210000);
  assert.equal(changed.material.poisson_ratio, 0.3);
  assert.equal("E_1_MPa" in changed.material, false);
  assert.equal("axes" in changed.material, false);
  assert.equal(changed.material.provenance, original.material.provenance);
});
test("blank, boolean, nonfinite and reversed or insufficient meshes are refused", () => {
  for (const force of ["", " ", "0", "-1", "Infinity", "1e999"]) assert.throws(() => fromFields({ ...toFields(settings()), force_N: force }, settings()));
  for (const sizes of ["4", "2, 3", "4, 4, 2", "4, NaN", "4, 0", "4, 3,"]) assert.throws(() => fromFields({ ...toFields(settings()), mesh_sizes: sizes }, settings()));
  assert.throws(() => validate({ ...settings(), load: { force_per_support_N: true, source: "x" } }));
});
test("missing sources and unsupported setting keys fail without silently discarding data", () => {
  assert.throws(() => fromFields({ ...toFields(settings()), provenance: "" }, settings()));
  assert.throws(() => fromFields({ ...toFields(settings()), source: "" }, settings()));
  const original = { ...settings(), support: { bolted: true } };
  assert.throws(() => fromFields(toFields(settings()), original));
});
test("unsupported nested JSON settings survive a refused form edit", () => {
  const load = settings(), mesh = settings();
  load.load.direction = "X"; mesh.mesh.element_type = "C3D4";
  for (const original of [load, mesh]) {
    const before = JSON.stringify(original);
    assert.throws(() => fromFields({ ...toFields(settings()), force_N: "125" }, original));
    assert.equal(JSON.stringify(original), before);
  }
});
test("invalid raw JSON cannot be repaired with stale form values that change another condition", () => {
  const original = settings(); original.load.force_per_support_N = 150; original.material.G_13_MPa = -1;
  const before = JSON.stringify(original), stale = toFields(settings()); stale.G_13_MPa = "400";
  assert.throws(() => toFields(original));
  assert.throws(() => fromFields(stale, original));
  assert.equal(JSON.stringify(original), before);
});
const digest = "a".repeat(64), path = "simulation/support_0/stress_field.json";
const artifacts = [{ path: "simulation/support_0/support_0.frd", sha256: digest }];
const field = () => ({ schema_version: "1.0", field: "stress", representation: "AVERAGED_NODAL", unit: "MPa", coordinate_frame: "SOLVER_GLOBAL_CARTESIAN", tensor_shear_components: true,
  engineering_valid: false, qualification: "UNKNOWN", component_order: ["SXX", "SYY", "SZZ", "SXY", "SYZ", "SZX"], source_frd: { path: "support_0.frd", sha256: digest }, node_count: 1,
  nodes: [{ node_id: 1, position_mm: [0, 0, 0], stress_MPa: [10, 0, 0, 0, 0, 0], von_mises_MPa: 10 }] });
test("stress display admits only diagnostic tensors linked to the exact manifested FRD", () => {
  assert.equal(verifyStressField(field(), artifacts, path).engineering_valid, false);
  assert.throws(() => verifyStressField(field(), [{ ...artifacts[0], sha256: "b".repeat(64) }], path));
  assert.throws(() => verifyStressField(field(), [], path));
});
test("stress display refuses misleading units, component order or engineering validity", () => {
  for (const changes of [{ unit: "Pa" }, { engineering_valid: true }, { qualification: "PASS" }, { tensor_shear_components: false }, { component_order: ["SXX", "SYY", "SZZ", "SXY", "SZX", "SYZ"] }]) {
    assert.throws(() => verifyStressField({ ...field(), ...changes }, artifacts, path));
  }
});
test("stress display refuses duplicate or incomplete nodes and nonfinite tensor components", () => {
  const duplicate = field(); duplicate.nodes.push(duplicate.nodes[0]); duplicate.node_count = 2;
  assert.throws(() => verifyStressField(duplicate, artifacts, path));
  for (const changes of [{ stress_MPa: [1, 2] }, { stress_MPa: [1, 2, 3, 4, NaN, 6] }, { position_mm: [0, Infinity, 0] }, { von_mises_MPa: -1 }]) {
    const invalid = field(); Object.assign(invalid.nodes[0], changes);
    assert.throws(() => verifyStressField(invalid, artifacts, path));
  }
});
