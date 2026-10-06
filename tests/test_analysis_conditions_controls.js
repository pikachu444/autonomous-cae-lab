"use strict";

// Source controls only: all hashes, records and solver replies below are synthetic.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const vm = require("node:vm");
const controls = require("../apps/lab/static/analysis-conditions-controls.js");
const copy = value => JSON.parse(JSON.stringify(value));
function catalog(backend = "fixture.cadquery") {
  return { source: { experiment_id: "E-cad", study_id: "S-study", cad_revision: "a".repeat(64), backend,
    result_sha256: "b".repeat(64), proposal_sha256: "c".repeat(64), thread_sha256: "d".repeat(64) },
    catalog_revision: "e".repeat(64),
    catalog: { schema_version: "1.0", selections: [
      { id: "B-final", label: "최종 솔리드", kind: "whole_final_solid", roles: ["material", "boundary", "load"] },
      { id: "S-base", label: "선언된 바닥", kind: "adapter_region", roles: ["boundary"] },
      { id: "S-saddle", label: "선언된 안장 중앙 24 mm", kind: "adapter_region", roles: ["load"] }],
      coordinate_systems: [{ id: "global", label: "CAD 전역", type: "cartesian", unit: "mm", basis: [[1, 0, 0], [0, 1, 0], [0, 0, 1]], origin: [0, 0, 0] }],
      limitations: ["일반 면과 접촉 연결은 미완료."] },
    backends: [{ backend: "fixture.calculix", label: "CalculiX", scope: "선언 입력 지원 · runtime 미확인" }] };
}
function fields(changes = {}) {
  return { conditionsId: "C-conditions", backend: "fixture.calculix", materialSelection: "B-final", materialLaw: "isotropic_linear_elastic",
    youngModulus: "210000", poissonRatio: "0.3", materialCategory: "ASSUMED", materialSource: "ASSUMED: 미측정 가정 재료",
    coordinateSystem: "global", lengthUnit: "mm", forceUnit: "N", stressUnit: "MPa", boundarySelection: "S-base",
    ux: "0", uy: "0", uz: "0", boundarySource: "ASSUMED: 바닥 변위 이상화", loadSelection: "S-saddle",
    fx: "0", fy: "0", fz: "-150", loadSource: "ASSUMED: 합력", contactMode: "none", contactSource: "ASSUMED: 접촉 없음", meshSize: "4", ...changes };
}
function record(data = catalog()) {
  const declaration = { analysis_type: "linear_static", units: { length: "mm", force: "N", stress: "MPa" }, coordinate_system: "global",
    materials: [{ id: "M1", selection_id: "B-final", law: "isotropic_linear_elastic", young_modulus_MPa: 210000, poisson_ratio: 0.3,
      source: { category: "ASSUMED", description: "ASSUMED: 미측정 가정 재료" } }],
    boundary_conditions: [{ id: "BC1", selection_id: "S-base", type: "displacement", components: { UX: 0, UY: 0, UZ: 0 }, unit: "mm", coordinate_system: "global", source: "ASSUMED: 바닥 변위 이상화" }],
    loads: [{ id: "L1", selection_id: "S-saddle", type: "resultant_force", components: { FX: 0, FY: 0, FZ: -150 }, unit: "N", coordinate_system: "global", source: "ASSUMED: 합력" }],
    contact: { mode: "none", source: "ASSUMED: 접촉 없음" }, mesh: { mode: "selected", max_size_mm: 4 } };
  return { schema_version: "1.0", id: "C-conditions", created_utc: "2026-10-06T00:00:00Z", source: copy(data.source),
    request: { conditions_id: "C-conditions", experiment_id: "E-cad", cad_revision: data.source.cad_revision, catalog_revision: data.catalog_revision,
      backend: "fixture.calculix", declaration }, catalog: copy(data.catalog), catalog_revision: data.catalog_revision, conditions_revision: "f".repeat(64),
    support: { status: "SUPPORTED_DECLARED_INPUTS", reasons: [], native_runtime: "NOT_CHECKED" },
    adapter_binding: { backend: "fixture.calculix", version: "TEST_ONLY", settings: { opaque: "server_owned" } },
    engineering: "UNKNOWN", decision: "NOT_RELEASED", provenance: { scope: "TEST_ONLY" } };
}
const envelope = value => ({ record: value, integrity: "VERIFIED" });

test("completed CAD choices include imported and assembly backends without guessing structural eligibility", () => {
  const base = { id: "E-cad", study_id: "S-study", status: "COMPLETED_REVIEW_REQUIRED", solver_status: "NOT_RUN", cad_revision: "a".repeat(64) };
  const records = ["fixture.cadquery", "fixture.freecad", "fixture.assembly"].map((backend, index) => ({ ...base, id: `E-cad${index}`, backend }));
  records.push({ ...base, id: "E-other", backend: "fixture.cadquery", study_id: "S-other" },
    { ...base, id: "E-solve", backend: "fixture.calculix", solver_status: "COMPLETED" },
    { ...base, id: "E-rejected", backend: "fixture.freecad", status: "REJECTED" });
  assert.deepEqual(controls.parents(records, "S-study").map(item => item.backend), ["fixture.cadquery", "fixture.freecad", "fixture.assembly"]);
  assert.deepEqual(controls.parents(records, "../study"), []);
});

test("explicit signed force and displacement vectors survive unchanged, including adapter-unsupported values", () => {
  const data = catalog(), before = copy(data), input = fields({ fx: "12.5", fy: "-2e1", fz: "75", ux: "0.125", uy: "-3", uz: "2" });
  const request = controls.buildSave(data, input);
  assert.deepEqual(request.declaration.loads[0].components, { FX: 12.5, FY: -20, FZ: 75 });
  assert.deepEqual(request.declaration.boundary_conditions[0].components, { UX: 0.125, UY: -3, UZ: 2 });
  assert.deepEqual(request.declaration.mesh, { mode: "selected", max_size_mm: 4 });
  assert.equal(request.declaration.materials[0].source.category, "ASSUMED");
  assert.deepEqual(data, before); assert.equal(input.fy, "-2e1");
  assert.equal(Object.hasOwn(request, "settings"), false);
  assert.equal(Object.hasOwn(request, "adapter_binding"), false);
});

test("catalog source, selection roles and exact declared axis/units block missing or substituted bindings", () => {
  const data = catalog();
  for (const changes of [{ materialSelection: "S-saddle" }, { boundarySelection: "S-saddle" }, { loadSelection: "S-base" },
      { loadSelection: "display-triangle-12" }, { materialSelection: "" }, { coordinateSystem: "local" }, { lengthUnit: "m" },
      { forceUnit: "kN" }, { stressUnit: "Pa" }, { backend: "elasticity.codeaster" }, { contactMode: "bonded" }]) {
    assert.throws(() => controls.buildSave(data, fields(changes)));
  }
  for (const expected of [{ experimentId: "E-other" }, { studyId: "S-other" }, { cadRevision: "0".repeat(64) }, { backend: "fixture.freecad" }]) {
    assert.throws(() => controls.catalog(data, expected));
  }
  for (const mutate of [value => { value.source.thread_sha256 = "unknown"; }, value => { value.catalog_revision = "unknown"; },
      value => { value.catalog.selections[1].id = "B-final"; }, value => { value.catalog.coordinate_systems[0].unit = "m"; },
      value => { value.catalog.coordinate_systems[0].basis = [[1, 0, 0], [0, 0, 1], [0, 1, 0]]; },
      value => { delete value.catalog.coordinate_systems[0].origin; }, value => { value.catalog.coordinate_systems.push(copy(value.catalog.coordinate_systems[0])); },
      value => { value.catalog.selections[0].roles.push("face"); }, value => { value.backends[0].backend = "../solver"; }]) {
    const invalid = copy(data); mutate(invalid); assert.throws(() => controls.catalog(invalid));
  }
});

test("finite decimal declarations and explicit sources refuse blanks, Infinity, numeric coercion and active properties", () => {
  for (const key of ["youngModulus", "poissonRatio", "ux", "uy", "uz", "fx", "fy", "fz", "meshSize"]) {
    for (const value of ["", " ", "Infinity", "NaN", "1e999", "0x20", "2 mm", null, 4, true]) assert.throws(() => controls.buildSave(catalog(), fields({ [key]: value })));
  }
  for (const key of ["materialSource", "boundarySource", "loadSource", "contactSource"]) {
    for (const value of ["", " ", "x".repeat(2001)]) assert.throws(() => controls.buildSave(catalog(), fields({ [key]: value })));
  }
  for (const value of ["QUALIFIED", "USER_REPORTED", "", null]) assert.throws(() => controls.buildSave(catalog(), fields({ materialCategory: value })));
  for (const category of ["ASSUMED", "MEASURED_REPORTED", "PUBLISHED_REFERENCE"]) assert.equal(controls.buildSave(catalog(), fields({ materialCategory: category })).declaration.materials[0].source.category, category);
  let reads = 0; const active = fields(); Object.defineProperty(active, "youngModulus", { enumerable: true, get: () => { reads++; return "210000"; } });
  assert.throws(() => controls.buildSave(catalog(), active)); assert.equal(reads, 0);
  assert.throws(() => controls.buildSave(catalog(), JSON.parse('{"conditionsId":"C-new","__proto__":{"source":"foreign"}}')));
});

test("supported save/reopen/run uses the exact record and emits conditions_id without competing settings", () => {
  const data = catalog(), value = record(data), original = copy(value);
  assert.equal(controls.saved(envelope(value), data, controls.buildSave(data, fields())), value);
  assert.deepEqual(controls.fromRecord(value, data), fields());
  assert.deepEqual(controls.buildRun(value, data, fields(), "E-child"), {
    parent_experiment_id: "E-cad", experiment_id: "E-child", backend: "fixture.calculix", conditions_id: "C-conditions" });
  assert.deepEqual(value, original);
  assert.throws(() => controls.buildRun(value, data, fields({ fz: "-151" }), "E-child"), /저장 후 입력/);
  assert.throws(() => controls.buildRun(value, data, fields(), "../new"));
});

test("server support stays authoritative for imported bodies, unsupported vectors and unavailable adapters", () => {
  const data = catalog("fixture.freecad"); data.catalog.selections = data.catalog.selections.slice(0, 1);
  const bodyFields = fields({ boundarySelection: "B-final", loadSelection: "B-final", fx: "15", uz: "1" });
  const request = controls.buildSave(data, bodyFields);
  for (const status of ["UNSUPPORTED_FOR_MODEL", "UNSUPPORTED_FOR_CONDITIONS", "UNAVAILABLE"]) {
    const value = record(data); value.request = copy(request); value.adapter_binding = null;
    value.support = { status, reasons: ["일반 imported CAD의 native 분포는 미지원"], native_runtime: "NOT_CHECKED" };
    assert.equal(controls.saved(envelope(value), data), value);
    assert.deepEqual(controls.fromRecord(value, data), bodyFields);
    assert.throws(() => controls.buildRun(value, data, bodyFields, "E-child"), /서버가/);
    assert.equal(value.request.declaration.loads[0].components.FX, 15);
    assert.equal(value.request.declaration.boundary_conditions[0].components.UZ, 1);
  }
});

test("each source pin and record/catalog/request mismatch refuses reopen rather than borrowing another revision", () => {
  const data = catalog();
  for (const key of ["experiment_id", "study_id", "backend", "cad_revision", "result_sha256", "proposal_sha256", "thread_sha256"]) {
    const value = record(data); value.source[key] = key.endsWith("sha256") || key === "cad_revision" ? "0".repeat(64) : "Other";
    assert.throws(() => controls.saved(envelope(value), data), key);
  }
  for (const mutate of [value => { value.id = "C-other"; }, value => { value.catalog_revision = "0".repeat(64); },
      value => { value.catalog.selections[0].label = "different body"; }, value => { value.request.experiment_id = "E-other"; },
      value => { value.request.cad_revision = "0".repeat(64); }, value => { value.request.catalog_revision = "0".repeat(64); },
      value => { value.support.native_runtime = "AVAILABLE"; }, value => { value.support.status = "APPROVED"; },
      value => { value.engineering = "PASS"; }, value => { value.decision = "RELEASED"; }, value => { value.adapter_binding.backend = "other.solver"; },
      value => { value.support.status = "UNAVAILABLE"; }]) {
    const value = record(data); mutate(value); assert.throws(() => controls.saved(envelope(value), data));
  }
  assert.throws(() => controls.saved({ record: record(data), integrity: "UNKNOWN" }, data));
  assert.throws(() => controls.saved(envelope(record(data)), data, controls.buildSave(data, fields({ fz: "-100" }))));
});

test("reopen cannot silently drop additional targets, contact pairs, components or declaration fields", () => {
  for (const mutate of [value => { value.request.declaration.materials.push(copy(value.request.declaration.materials[0])); },
      value => { value.request.declaration.contact.pairs = []; }, value => { value.request.declaration.loads[0].components.MX = 0; },
      value => { value.request.declaration.boundary_conditions[0].coordinate_system = "local"; },
      value => { value.request.declaration.units.force = "kN"; }, value => { value.request.declaration.extension = "retain me"; }]) {
    const data = catalog(), value = record(data), before = copy(value); mutate(value); const after = copy(value);
    assert.throws(() => controls.fromRecord(value, data)); assert.deepEqual(value, after); assert.notDeepEqual(after, before);
  }
});

test("browser and CommonJS contracts agree without deriving an engineering or runtime verdict", () => {
  const browser = { window: {} };
  vm.runInNewContext(readFileSync(require.resolve("../apps/lab/static/analysis-conditions-controls.js"), "utf8"), browser);
  assert.deepEqual(Object.keys(browser.window.analysisConditionsControls), Object.keys(controls));
  assert.equal(JSON.stringify(browser.window.analysisConditionsControls.buildSave(catalog(), fields())), JSON.stringify(controls.buildSave(catalog(), fields())));
  const value = record(); assert.equal(controls.saved(envelope(value), catalog()).support.native_runtime, "NOT_CHECKED");
  assert.equal(value.engineering, "UNKNOWN"); assert.equal(value.decision, "NOT_RELEASED");
});

function nativeCatalog() {
  const data = catalog("fixture.freecad");
  data.catalog.selections = [{ id: "B-final", label: "Final solid", kind: "whole_final_solid", roles: ["material"] },
    ...[1, 2, 3, 4].map((index) => ({ id: `F-${"1".repeat(64)}-Face${index}`, label: `조건 면 ${index} <TEST_ONLY>`, kind: "native_face", roles: ["boundary", "load"],
      native_object: "FinalPad", native_name: `Face${index}`, body_id: "B-final", area_mm2: 80 + index, center_mm: [index, -2.5, 4],
      bounds_mm: { min: [0, -5, 0], max: [10, 5, 8] }, surface_type: "Plane", unit: "mm", coordinate_system: "global", native_coordinate_system: "cad_document_global",
      geometry_sha256: "2".repeat(64), planar_normal_global: [1, 0, 0] }))];
  data.backends = [{ backend: "structure.calculix.native", label: "Native CalculiX", scope: "Server-declared native syntax; not a runtime proof" }];
  return data;
}
function nativeFields(data) {
  return fields({ backend: "structure.calculix.native", boundarySelection: data.catalog.selections[1].id, loadSelection: data.catalog.selections[4].id,
    uxEnabled: true, uyEnabled: false, uzEnabled: false, uy: "", uz: "",
    additionalBoundaries: [
      { id: "BC2", selectionId: data.catalog.selections[2].id, uxEnabled: false, uyEnabled: true, uzEnabled: false, ux: "", uy: "-0.125", uz: "", source: "ASSUMED: Y symmetry" },
      { id: "BC3", selectionId: data.catalog.selections[3].id, uxEnabled: false, uyEnabled: false, uzEnabled: true, ux: "", uy: "", uz: "0", source: "ASSUMED: Z symmetry" } ] });
}

test("native catalog exposes actual FaceN geometry and independent roles without deriving targets from display triangles", () => {
  const data = nativeCatalog(), before = copy(data); controls.catalog(data);
  assert.deepEqual(controls.choices(data, "material").map(item => item.id), ["B-final"]);
  assert.equal(controls.choices(data, "boundary").length, 4);
  const label = controls.selectionLabel(data.catalog.selections[1]);
  assert.match(label, /FinalPad\/Face1/); assert.match(label, /81 mm²/); assert.match(label, /중심 \(1, -2.5, 4\) mm/);
  assert.equal(controls.buildSave(data, nativeFields(data)).declaration.boundary_conditions[0].selection_id, data.catalog.selections[1].id);
  assert.throws(() => controls.buildSave(data, { ...nativeFields(data), boundarySelection: "display-triangle-0" }));
  assert.throws(() => controls.buildSave(data, { ...nativeFields(data), boundarySelection: "B-final" }));
  assert.deepEqual(data, before);
});

test("unverified native frame, incomplete geometry and wrong face/body role are refused before form admission", () => {
  for (const mutate of [face => { delete face.geometry_sha256; }, face => { face.area_mm2 = 0; }, face => { face.center_mm = [1, 2]; },
      face => { face.bounds_mm.min[0] = 20; }, face => { face.native_name = "triangle-12"; }, face => { face.body_id = "B-other"; },
      face => { face.unit = "m"; }, face => { face.coordinate_system = "world"; }, face => { face.native_coordinate_system = "unknown"; },
      face => { face.roles.push("material"); }, face => { face.planar_normal_global = [0, 1]; }]) {
    const data = nativeCatalog(); mutate(data.catalog.selections[1]); assert.throws(() => controls.catalog(data));
  }
});

test("multiple native symmetry boundaries save/reopen exactly with omitted DOFs, signed loads and original face IDs", () => {
  const data = nativeCatalog(), input = nativeFields(data), request = controls.buildSave(data, input), value = record(data);
  value.request = copy(request); value.adapter_binding.backend = request.backend;
  assert.deepEqual(request.declaration.boundary_conditions.map(item => item.components), [{ UX: 0 }, { UY: -0.125 }, { UZ: 0 }]);
  const before = copy(value); controls.saved(envelope(value), data);
  const restored = controls.fromRecord(value, data);
  assert.deepEqual(controls.buildSave(data, restored), request);
  assert.equal(restored.additionalBoundaries[0].uxEnabled, false); assert.equal(restored.additionalBoundaries[0].ux, "");
  assert.deepEqual(controls.buildRun(value, data, restored, "E-native-child"), { parent_experiment_id: "E-cad", experiment_id: "E-native-child", backend: "structure.calculix.native", conditions_id: value.id });
  assert.deepEqual(value, before); assert.equal(value.engineering, "UNKNOWN"); assert.equal(value.support.native_runtime, "NOT_CHECKED");
});

test("empty, duplicated, unknown or changed-revision native DOFs/targets cannot be simplified into runnable conditions", () => {
  const data = nativeCatalog(), input = nativeFields(data);
  for (const patch of [{ uxEnabled: false }, { uxEnabled: "true" }, { additionalBoundaries: [{ ...input.additionalBoundaries[0], id: "BC1" }] },
      { additionalBoundaries: [input.additionalBoundaries[0], copy(input.additionalBoundaries[0])] },
      { additionalBoundaries: [{ ...input.additionalBoundaries[0], uyEnabled: false }] },
      { additionalBoundaries: [{ ...input.additionalBoundaries[0], uy: "Infinity" }] }]) assert.throws(() => controls.buildSave(data, { ...input, ...patch }));
  const value = record(data); value.request = controls.buildSave(data, input); value.adapter_binding.backend = value.request.backend;
  const altered = copy(value); altered.request.declaration.boundary_conditions[1].components.URX = 0;
  assert.throws(() => controls.fromRecord(altered, data)); assert.equal(altered.request.declaration.boundary_conditions[1].components.URX, 0);
  const next = copy(data); next.source.cad_revision = "3".repeat(64); next.catalog_revision = "4".repeat(64);
  next.catalog.selections.slice(1).forEach(face => { face.id = face.id.replace("1".repeat(64), "5".repeat(64)); });
  assert.throws(() => controls.buildSave(next, input)); assert.throws(() => controls.saved(envelope(value), next));
});
