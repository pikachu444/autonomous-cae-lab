"use strict";

// Synthetic source/DOM proof only. No retained mesh, native solver or browser is run.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const vm = require("node:vm");
const common = require("../apps/lab/static/analysis-conditions-controls.js");
const controls = require("../apps/lab/static/assembly-conditions-controls.js");
const copy = value => JSON.parse(JSON.stringify(value));
const active = ["base_plate", "left_support", "right_support", "workpiece", "pressure_block", "left_clamp", "right_clamp"];
const backend = "fixture.assembly_mechanics.code_aster";
const faceId = (component, ordinal = 1) => `S-${component}-${ordinal}`;
function catalog({ mesh = true } = {}) {
  const components = [...active, "inactive_bolt"];
  const selections = components.flatMap((component, index) => {
    const geometry = { component_id: component, coordinate_system: "global", native_coordinate_system: "global_assembly_cartesian_mm",
      center_mm: [index, -2, 5], bounds_mm: { min_mm: [index - 1, -4, 0], max_mm: [index + 1, 0, 10], size_mm: [2, 4, 10] }, native_geometry_sha256: "1".repeat(64) };
    return [{ ...copy(geometry), id: `B-${component}`, label: `${component} <TEST_ONLY>`, kind: "native_assembly_body", roles: ["material"], volume_mm3: 80 },
      ...[1, 2].map(ordinal => ({ ...copy(geometry), id: faceId(component, ordinal), label: `${component} 면 ${ordinal} <TEST_ONLY>`, kind: "native_assembly_face",
        roles: ["boundary", "load", "contact"], catalog_face_id: `${component}:face:${ordinal}:${"2".repeat(64)}`,
        native_ordinal: ordinal, local_ordinal: ordinal, area_mm2: 8, geom_type: "Plane", orientation: "Forward" }))];
  });
  return { source: { experiment_id: "E-assembly", study_id: "S-assembly", cad_revision: "a".repeat(64), backend: "fixture.assembly",
    result_sha256: "b".repeat(64), proposal_sha256: "c".repeat(64), thread_sha256: "d".repeat(64) }, catalog_revision: "e".repeat(64),
    catalog: { schema_version: "1.0", selections,
      coordinate_systems: [{ id: "global", label: "원 조립체 전역", type: "cartesian", unit: "mm", basis: [[1, 0, 0], [0, 1, 0], [0, 0, 1]], origin: [0, 0, 0] }],
      limitations: ["SOURCE_TEST_ONLY · 실물 접촉·물성·강도 자격 UNKNOWN"],
      ...(mesh ? { retained_mesh: { profile: "coarse3", mesh_revision: "3".repeat(64), cad_revision: "a".repeat(64), active_components: [...active], inactive_components: ["inactive_bolt"] } } : {}) },
    backends: [{ backend, label: "Code_Aster 조립체 · TEST_ONLY", scope: "서버 입력 지원 목록 · runtime NOT_CHECKED" }] };
}
function fields(changes = {}) {
  return { conditionsId: "C-assembly", backend, analysisType: "nonlinear_static", coordinateSystem: "global", lengthUnit: "mm", forceUnit: "N", stressUnit: "MPa",
    materialRows: active.map((component, index) => ({ id: `M${index + 1}`, selectionId: `B-${component}`, youngModulus: index === 3 ? "70000" : "210000", poissonRatio: index === 3 ? "0.33" : "0.3", category: "ASSUMED", source: `ASSUMED: ${component} 미측정 재료` })),
    boundaryRows: [
      { id: "BC1", selectionId: faceId("base_plate"), ux: "0", uy: "", uz: "", uxEnabled: true, uyEnabled: false, uzEnabled: false, source: "ASSUMED: X 대칭" },
      { id: "BC2", selectionId: faceId("left_support"), ux: "", uy: "-0.125", uz: "", uxEnabled: false, uyEnabled: true, uzEnabled: false, source: "ASSUMED: Y 변위" },
      { id: "BC3", selectionId: faceId("right_support", 2), ux: "", uy: "", uz: "0", uxEnabled: false, uyEnabled: false, uzEnabled: true, source: "ASSUMED: Z 구속" }],
    loadRows: [{ id: "L1", selectionId: faceId("pressure_block"), fx: "12.5", fy: "-2e1", fz: "-150", source: "ASSUMED: 전역 합력" }],
    contactRows: [{ id: "CP1", selectionA: faceId("base_plate", 2), selectionB: faceId("left_support", 2), law: "bonded", master: "b", distanceMaxMm: "0.125", source: "ASSUMED: bonded idealization" },
      { id: "CP2", selectionA: faceId("workpiece"), selectionB: faceId("pressure_block", 2), law: "frictionless", master: "a", source: "ASSUMED: 무마찰 접촉" }],
    contactSource: "ASSUMED: 사용자가 지정한 결합·무마찰 쌍, 실물 검증 없음", ...changes };
}
function interiorCatalog() {
  const data = catalog();
  for (const component of ["left_support", "right_support"]) {
    const full = data.catalog.selections.find(item => item.id === faceId(component, 2));
    data.catalog.selections.push({ ...copy(full), id: `I-${component}-2`, kind: "assembly_face_interior_nodes", roles: ["boundary", "load"],
      node_scope: "FACE_INTERIOR_EXCLUDING_OTHER_FACE_BOUNDARIES", geometry_metadata_scope: "ORIGINAL_SOURCE_FACE_NOT_SUBSET" });
  }
  return data;
}
function record(data, input = fields(), status = "SUPPORTED_DECLARED_INPUTS") {
  return { schema_version: "1.0", id: input.conditionsId, created_utc: "2026-10-06T12:00:00Z", source: copy(data.source),
    catalog: copy(data.catalog), catalog_revision: data.catalog_revision, request: controls.buildSave(data, input), conditions_revision: "f".repeat(64),
    support: { status, reasons: status === "SUPPORTED_DECLARED_INPUTS" ? [] : ["TEST_ONLY: 실제 서버 Domain 판정을 흉내낸 source fixture"], native_runtime: "NOT_CHECKED" },
    adapter_binding: status === "SUPPORTED_DECLARED_INPUTS" ? { backend: input.backend, version: "TEST_ONLY", settings: { source_only: true } } : null,
    engineering: "UNKNOWN", decision: "NOT_RELEASED" };
}

test("displacement control preserves an empty force declaration and explicit nonzero driven component on reopen", () => {
  const data = catalog(), input = fields({ loadRows: [] }), before = copy(input);
  const saved = record(data, input), reopened = controls.fromRecord(saved, data);
  assert.deepEqual(saved.request.declaration.loads, []);
  assert.deepEqual(controls.buildSave(data, reopened), saved.request);
  assert.deepEqual(input, before);
  for (const row of input.boundaryRows) for (const axis of ["x", "y", "z"]) if (row[`u${axis}Enabled`]) row[`u${axis}`] = "0";
  assert.throws(() => controls.buildSave(data, input), /지정 변위/);
});

test("assembly geometry/options preserve raw face IDs and restrict roles to retained active components", () => {
  const data = catalog(), before = copy(data), options = controls.rowsFromCatalog(data);
  assert.equal(controls.isAssembly(data), true); assert.equal(common.catalog(data), data);
  assert.equal(options.materials.length, 7); assert.equal(options.boundaries.length, 14); assert.equal(options.loads.length, 14); assert.equal(options.contacts.length, 14);
  assert.deepEqual(options.activeComponents, active); assert.equal(options.retainedMesh.mesh_revision, "3".repeat(64));
  assert.equal(options.contacts[0].catalog_face_id, `base_plate:face:1:${"2".repeat(64)}`);
  assert.equal(options.contacts[0].native_ordinal, 1); assert.equal(options.contacts[0].native_geometry_sha256, "1".repeat(64));
  assert.match(options.contacts[0].displayLabel, /원 면 base_plate:face:1:/); assert.match(options.contacts[0].displayLabel, /8 mm² · 중심 \(0, -2, 5\) mm/);
  assert.doesNotMatch(options.contacts[0].displayLabel, /Face1|triangle/);
  assert.equal(options.materials.some(item => Object.hasOwn(item, "youngModulus") || Object.hasOwn(item, "force")), false);
  options.materials[0].center_mm[0] = 99; assert.deepEqual(data, before);
});

test("catalog without retained mesh remains readable but cannot guess active bodies or save", () => {
  const data = catalog({ mesh: false }), options = controls.rowsFromCatalog(data);
  assert.equal(controls.isAssembly(data), true); assert.equal(options.retainedMesh, null);
  assert.deepEqual(options.materials, []); assert.deepEqual(options.contacts, []); assert.deepEqual(options.activeComponents, []);
  assert.throws(() => controls.buildSave(data, fields()), /보존 메시가 없습니다/);
  const altered = catalog(); altered.catalog.retained_mesh.cad_revision = "0".repeat(64);
  assert.throws(() => controls.rowsFromCatalog(altered), /보존 메시의 개정/);
});

test("interior-node guides are offered explicitly for BC/load, preserve full-face geometry and never become contact targets", () => {
  const data = interiorCatalog(), options = controls.rowsFromCatalog(data), input = fields();
  assert.equal(controls.isAssembly(data), true);
  assert.equal(options.boundaries.length, 16); assert.equal(options.loads.length, 16); assert.equal(options.contacts.length, 14);
  assert.equal(options.contacts.some(item => item.kind === "assembly_face_interior_nodes"), false);
  const guide = options.boundaries.find(item => item.id === "I-left_support-2");
  assert.match(guide.displayLabel, /면 내부 절점·모서리 제외/); assert.equal(guide.catalog_face_id, `left_support:face:2:${"2".repeat(64)}`);
  assert.match(guide.displayLabel, /원 면적 8 mm² · 원 중심/);
  input.boundaryRows[1].selectionId = guide.id; input.loadRows[0].selectionId = "I-right_support-2";
  const value = record(data, input), restored = controls.fromRecord(value, data);
  assert.deepEqual(controls.buildSave(data, restored), value.request);
  assert.equal(value.request.declaration.boundary_conditions[1].selection_id, "I-left_support-2");
  assert.equal(value.request.declaration.loads[0].selection_id, "I-right_support-2");
  const contactInput = copy(input); contactInput.contactRows[0].selectionA = guide.id;
  assert.throws(() => controls.buildSave(data, contactInput), /접촉 면/);
  const container = form(); controls.renderForm(container, data, {}); click(addButton(container, "boundaryRows"));
  assert.equal(controls.readForm(container).boundaryRows[0].selectionId, "");
  assert(walk(container).some(node => node.tagName === "OPTION" && node.value === guide.id));
});

test("interior-node catalog refuses contact/material roles, absent retained topology and mismatched same-catalog full face", () => {
  for (const mutate of [data => { data.catalog.selections.at(-1).roles.push("contact"); }, data => { data.catalog.selections.at(-1).roles = ["material"]; },
      data => { data.catalog.selections.at(-1).node_scope = "ALL_FACE_NODES"; }, data => { delete data.catalog.retained_mesh; },
      data => { data.catalog.retained_mesh.active_components = active.filter(component => component !== "right_support"); },
      data => { data.catalog.selections = data.catalog.selections.filter(item => item.id !== faceId("right_support", 2)); },
      data => { data.catalog.selections.at(-1).native_geometry_sha256 = "4".repeat(64); }, data => { data.catalog.selections.at(-1).center_mm[1] = 3; },
      data => { data.catalog.selections.at(-1).orientation = "Reversed"; }, data => { data.catalog.selections.at(-1).geometry_metadata_scope = "SUBSET_GEOMETRY"; },
      data => { data.catalog.selections.at(-1).cad_revision = "0".repeat(64); },
      data => { data.catalog.selections.find(item => item.id === faceId("right_support", 2)).cad_revision = "0".repeat(64); }]) {
    const data = interiorCatalog(); mutate(data); assert.equal(controls.isAssembly(data), false); assert.throws(() => common.catalog(data));
  }
});

test("seven material assignments, partial DOFs, signed loads and mixed contacts produce typed retained-mesh declaration", () => {
  const data = catalog(), input = fields(), before = copy(input), request = controls.buildSave(data, input);
  assert.equal(request.experiment_id, "E-assembly"); assert.equal(request.cad_revision, data.source.cad_revision); assert.equal(request.catalog_revision, data.catalog_revision);
  assert.equal(request.declaration.analysis_type, "nonlinear_static"); assert.equal(request.declaration.materials.length, 7);
  assert.equal(request.declaration.materials[3].young_modulus_MPa, 70000); assert.equal(request.declaration.materials[3].poisson_ratio, 0.33);
  assert.deepEqual(request.declaration.boundary_conditions.map(row => row.components), [{ UX: 0 }, { UY: -0.125 }, { UZ: 0 }]);
  assert.deepEqual(request.declaration.loads[0].components, { FX: 12.5, FY: -20, FZ: -150 });
  assert.deepEqual(request.declaration.contact.pairs, [
    { selection_a: faceId("base_plate", 2), selection_b: faceId("left_support", 2), law: "bonded", master: "b", source: input.contactRows[0].source, distance_max_mm: 0.125 },
    { selection_a: faceId("workpiece"), selection_b: faceId("pressure_block", 2), law: "frictionless", master: "a", source: input.contactRows[1].source }]);
  assert.deepEqual(request.declaration.mesh, { mode: "retained", mesh_revision: "3".repeat(64) });
  assert.deepEqual(input, before); assert.equal(Object.hasOwn(request, "settings"), false); assert.equal(Object.hasOwn(request, "adapter_binding"), false);
});

test("zero contact rows means explicit contact-none with source and no hidden pairs", () => {
  const data = catalog(), input = fields({ contactRows: [], contactSource: "ASSUMED: 접촉 없음" }), value = record(data, input);
  assert.deepEqual(value.request.declaration.contact, { mode: "none", source: "ASSUMED: 접촉 없음" });
  const reopened = controls.fromRecord(value, data); assert.deepEqual(reopened.contactRows, []);
  assert.deepEqual(controls.buildSave(data, reopened), value.request);
});

test("explicit initial contact state roundtrips while a legacy omission is preserved", () => {
  const data = catalog();
  for (const state of ["OPEN", "GEOMETRIC", "CLOSED_ASSUMED"]) {
    const input = fields({ initialContactState: state }), saved = record(data, input);
    assert.equal(saved.request.declaration.contact.initial_state, state);
    assert.deepEqual(controls.buildSave(data, controls.fromRecord(saved, data)), saved.request);
  }
  assert.equal(Object.hasOwn(controls.buildSave(data, fields()).declaration.contact, "initial_state"), false);
  assert.throws(() => controls.buildSave(data, fields({ initialContactState: "AUTO" })), /초기 접촉/);
});

test("initial contact control preserves legacy omission until the human changes it", () => {
  const data = catalog(), input = fields(), container = form();
  controls.renderForm(container, data, input);
  assert.deepEqual(controls.buildSave(data, controls.readForm(container)), controls.buildSave(data, input));
  const control = fieldNode(container, "initialContactState");
  control.value = "CLOSED_ASSUMED"; change(control);
  assert.equal(controls.buildSave(data, controls.readForm(container)).declaration.contact.initial_state, "CLOSED_ASSUMED");
  assert.match(container.textContent, /초기 힘/);
});

test("master union is an explicit typed opt-in and absent/unchecked declarations retain the original wire", () => {
  const data = catalog(), original = controls.buildSave(data, fields());
  assert.equal(Object.hasOwn(original.declaration.contact, "master_union_same_slave"), false);
  assert.deepEqual(controls.buildSave(data, fields({ masterUnionSameSlave: false })), original);
  const input = fields({ masterUnionSameSlave: true, contactRows: [
    { id: "CP1", selectionA: faceId("left_support", 2), selectionB: faceId("workpiece"), law: "frictionless", master: "a", source: "ASSUMED: left master / specimen slave" },
    { id: "CP2", selectionA: faceId("right_support", 2), selectionB: faceId("workpiece"), law: "frictionless", master: "a", source: "ASSUMED: right master / same specimen slave" }] });
  const value = record(data, input), restored = controls.fromRecord(value, data);
  assert.equal(value.request.declaration.contact.master_union_same_slave, true);
  assert.deepEqual(controls.buildSave(data, restored), value.request);
  assert.deepEqual(value.request.declaration.contact.pairs.map(pair => [pair.selection_a, pair.selection_b, pair.master]), [
    [faceId("left_support", 2), faceId("workpiece"), "a"], [faceId("right_support", 2), faceId("workpiece"), "a"]]);
  for (const invalid of ["true", 1, null, []]) assert.throws(() => controls.buildSave(data, fields({ masterUnionSameSlave: invalid })), /체크 여부|명시적 조립체 입력/);
  assert.throws(() => controls.buildSave(data, fields({ masterUnionSameSlavePresent: true })), /체크 여부/);
});

test("saved explicit false master union roundtrips without being dropped or checked", () => {
  const data = catalog(), value = record(data); value.request.declaration.contact.master_union_same_slave = false;
  const restored = controls.fromRecord(value, data), container = form();
  assert.equal(restored.masterUnionSameSlave, false); assert.equal(restored.masterUnionSameSlavePresent, true);
  assert.deepEqual(controls.buildSave(data, restored), value.request);
  controls.renderForm(container, data, restored); assert.equal(fieldNode(container, "masterUnionSameSlave").checked, false);
  assert.deepEqual(controls.buildSave(data, controls.readForm(container)), value.request);
  assert.equal(controls.buildRun(value, data, controls.readForm(container), "E-new-solve").conditions_id, value.id);
});

test("exact supported save/reopen/run preserves native selections and emits only existing conditions run contract", () => {
  const data = catalog(), value = record(data), before = copy(value), reopened = controls.fromRecord(value, data);
  assert.deepEqual(controls.buildSave(data, reopened), value.request);
  assert.equal(reopened.boundaryRows[1].uxEnabled, false); assert.equal(reopened.boundaryRows[1].ux, "");
  assert.equal(reopened.contactRows[0].master, "b"); assert.equal(Object.hasOwn(reopened.contactRows[1], "distanceMaxMm"), false);
  assert.deepEqual(controls.buildRun(value, data, reopened, "E-new-solve"), { parent_experiment_id: "E-assembly", experiment_id: "E-new-solve", backend, conditions_id: "C-assembly" });
  assert.equal(value.support.native_runtime, "NOT_CHECKED"); assert.equal(value.engineering, "UNKNOWN"); assert.equal(value.decision, "NOT_RELEASED"); assert.deepEqual(value, before);
});

test("supported state cannot be borrowed for dirty input or another study/CAD/mesh/source", () => {
  const data = catalog(), value = record(data), input = controls.fromRecord(value, data);
  const changed = copy(input); changed.loadRows[0].fz = "-151";
  assert.throws(() => controls.buildRun(value, data, changed, "E-new-solve"), /저장 후 조립체 입력/);
  assert.throws(() => controls.buildRun(value, data, input, "E-assembly"), /다른 새 해석/);
  assert.throws(() => controls.buildRun(value, data, input, "../other"));
  for (const mutate of [next => { next.source.study_id = "S-other"; }, next => { next.source.cad_revision = "0".repeat(64); },
      next => { next.source.result_sha256 = "0".repeat(64); }, next => { next.catalog.retained_mesh.mesh_revision = "0".repeat(64); },
      next => { next.catalog_revision = "0".repeat(64); }]) {
    const next = copy(data); mutate(next); assert.throws(() => controls.fromRecord(value, next)); assert.throws(() => controls.buildRun(value, next, input, "E-new-solve"));
  }
});

test("unsupported or unavailable declarations reopen intact while actual support remains server-owned", () => {
  const data = catalog(), input = fields(); input.materialRows.pop();
  for (const status of ["UNSUPPORTED_FOR_MODEL", "UNSUPPORTED_FOR_CONDITIONS", "UNAVAILABLE"]) {
    const value = record(data, input, status), before = copy(value), restored = controls.fromRecord(value, data);
    assert.equal(restored.materialRows.length, 6); assert.deepEqual(controls.buildSave(data, restored), value.request);
    assert.throws(() => controls.buildRun(value, data, restored, "E-new-solve"), /서버가/); assert.deepEqual(value, before);
  }
});

test("inactive topology, non-face contacts and display indices do not become mechanical targets", () => {
  for (const mutate of [input => { input.materialRows[0].selectionId = "B-inactive_bolt"; }, input => { input.boundaryRows[0].selectionId = faceId("inactive_bolt"); },
      input => { input.loadRows[0].selectionId = "display-triangle-1"; }, input => { input.contactRows[0].selectionA = "B-base_plate"; },
      input => { input.contactRows[0].selectionB = input.contactRows[0].selectionA; }, input => { input.materialRows[1].selectionId = input.materialRows[0].selectionId; }]) {
    const input = fields(); mutate(input); assert.throws(() => controls.buildSave(catalog(), input));
  }
});

test("explicit frame, units, partial-DOF choices, law/master/source and finite engineering values are required", () => {
  for (const mutate of [input => { input.forceUnit = "kN"; }, input => { input.coordinateSystem = "world"; }, input => { input.analysisType = "linear_static"; },
      input => { input.backend = "structure.calculix.native"; }, input => { delete input.boundaryRows[0].uxEnabled; }, input => { input.boundaryRows[0].uxEnabled = false; },
      input => { input.loadRows[0].fx = ""; }, input => { input.materialRows[0].youngModulus = "Infinity"; }, input => { input.materialRows[0].poissonRatio = "0.5"; },
      input => { input.contactRows[0].master = ""; }, input => { input.contactRows[0].distanceMaxMm = "0"; }, input => { input.contactRows[1].distanceMaxMm = ""; },
      input => { input.contactRows[0].source = ""; }, input => { input.contactSource = ""; }]) {
    const input = fields(); mutate(input); assert.throws(() => controls.buildSave(catalog(), input));
  }
  const input = fields(); input.boundaryRows[0].uy = "unparsed inactive draft";
  assert.deepEqual(controls.buildSave(catalog(), input).declaration.boundary_conditions[0].components, { UX: 0 });
});

test("native assembly catalog metadata is independently checked without widening old native-face roles", () => {
  for (const mutate of [face => { face.native_ordinal = 100; }, face => { face.catalog_face_id = "triangle-1"; }, face => { face.native_geometry_sha256 = "UNKNOWN"; },
      face => { face.bounds_mm.min_mm[0] = 10; }, face => { face.native_coordinate_system = "cad_document_global"; }, face => { face.roles.push("material"); }]) {
    const data = catalog(); mutate(data.catalog.selections[1]); assert.equal(controls.isAssembly(data), false); assert.throws(() => common.catalog(data));
  }
  const data = catalog(); data.catalog.selections[1].kind = "native_face";
  assert.throws(() => common.catalog(data));
  const badBody = catalog(); badBody.catalog.selections[0].volume_mm3 = 0; assert.throws(() => common.catalog(badBody));
});

test("reopening cannot silently lose a law, moment, contact data or a foreign mesh definition", () => {
  for (const mutate of [value => { value.request.declaration.materials[0].law = "anisotropic"; }, value => { value.request.declaration.boundary_conditions[0].components.URX = 0; },
      value => { value.request.declaration.loads[0].components.MX = 1; }, value => { value.request.declaration.contact.pairs[0].id = "RetainMe"; },
      value => { value.request.declaration.contact.pairs[1].distance_max_mm = 1; }, value => { value.request.declaration.mesh.extra = "retain"; },
      value => { value.request.declaration.extension = "retain"; }]) {
    const data = catalog(), value = record(data); mutate(value); const before = copy(value);
    assert.throws(() => controls.fromRecord(value, data)); assert.deepEqual(value, before);
  }
});

test("input JSON refuses getters and unsafe keys without evaluating active values", () => {
  let reads = 0; const input = fields(); Object.defineProperty(input.materialRows[0], "youngModulus", { enumerable: true, get: () => { reads++; return "210000"; } });
  assert.throws(() => controls.buildSave(catalog(), input)); assert.equal(reads, 0);
  const unsafe = fields(); unsafe.contactRows[0] = JSON.parse('{"id":"CP1","__proto__":{"master":"a"}}');
  assert.throws(() => controls.buildSave(catalog(), unsafe));
});

class Node {
  constructor(tag, document) { this.tagName = tag.toUpperCase(); this.ownerDocument = document; this.children = []; this.dataset = {}; this.value = ""; this.checked = false; this.disabled = false; this.hidden = false; this._text = ""; this.listeners = new Map(); }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
  set textContent(value) { this._text = String(value ?? ""); this.children.forEach(child => { child.parentNode = null; }); this.children = []; }
  get value() { return this.tagName !== "SELECT" || this.children.some(child => child.tagName === "OPTION" && child.value === this._value) ? this._value : ""; }
  set value(value) { const text = String(value); this._value = this.tagName !== "SELECT" || this.children.some(child => child.tagName === "OPTION" && child.value === text) ? text : ""; }
  set innerHTML(_value) { throw new Error("No arbitrary HTML in human declarations"); }
  append(...nodes) { nodes.forEach(node => { node.remove(); node.parentNode = this; this.children.push(node); }); }
  replaceChildren(...nodes) { this.textContent = ""; this.append(...nodes); }
  remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter(child => child !== this); this.parentNode = null; }
  addEventListener(type, fn) { if (!this.listeners.has(type)) this.listeners.set(type, []); this.listeners.get(type).push(fn); }
  dispatchEvent(event) { (this.listeners.get(event.type) ?? []).forEach(fn => fn(event)); if (event.bubbles) this.parentNode?.dispatchEvent(event); return true; }
}
const walk = node => [node, ...node.children.flatMap(walk)];
function form() {
  const document = { defaultView: { Event: class { constructor(type, options = {}) { this.type = type; Object.assign(this, options); } } } };
  document.createElement = tag => {
    const node = new Node(tag, document);
    if (tag === "textarea") Object.defineProperty(node, "type", { get: () => "textarea" });
    return node;
  };
  return document.createElement("div");
}
const rowNodes = (container, key) => walk(container).filter(node => node.dataset.assemblyRow === key);
const fieldNode = (container, key) => walk(container).find(node => node.dataset.assemblyField === key);
const addButton = (container, key) => walk(container).find(node => node.dataset.assemblyAdd === key);
const click = node => node.dispatchEvent({ type: "click" });
const change = node => node.dispatchEvent({ type: "change", bubbles: true });

test("human row form starts without engineering guesses and reports actual CAD/mesh/missing assignments as text", () => {
  const container = form(), data = catalog(); data.catalog.selections[0].label = '<img src=x onerror="BAD">';
  controls.renderForm(container, data, {});
  assert.deepEqual(controls.readForm(container).materialRows, []); assert.equal(fieldNode(container, "backend").value, "");
  assert.equal(fieldNode(container, "backend").type, "hidden");
  assert.equal(fieldNode(container, "masterUnionSameSlave").checked, false);
  assert.match(container.textContent, /CAD E-assembly/); assert.match(container.textContent, /보존 메시 coarse3 · 활성 7부품/); assert.match(container.textContent, /재료 0\/7 배정/);
  click(addButton(container, "materialRows")); click(addButton(container, "boundaryRows")); click(addButton(container, "loadRows")); click(addButton(container, "contactRows"));
  const input = controls.readForm(container);
  assert.equal(input.materialRows[0].selectionId, ""); assert.equal(input.materialRows[0].youngModulus, ""); assert.equal(input.materialRows[0].category, "");
  assert.equal(input.boundaryRows[0].uxEnabled, false); assert.equal(input.boundaryRows[0].ux, ""); assert.equal(input.loadRows[0].fz, "");
  assert.equal(input.contactRows[0].law, ""); assert.equal(input.contactRows[0].master, ""); assert.equal(Object.hasOwn(input.contactRows[0], "distanceMaxMm"), false);
  assert(container.textContent.includes('<img src=x onerror="BAD">')); assert.throws(() => controls.buildSave(data, input));
});

test("shared slave rows never opt into master union until the user explicitly checks it", () => {
  const data = catalog(), input = fields(); input.contactRows[0] = { ...input.contactRows[1], id: "CP1", selectionA: faceId("left_support", 2), selectionB: faceId("workpiece"), master: "a" };
  input.contactRows[1] = { ...input.contactRows[0], id: "CP2", selectionA: faceId("right_support", 2) };
  const container = form(); controls.renderForm(container, data, input);
  assert.equal(controls.readForm(container).masterUnionSameSlave, false);
  assert.equal(Object.hasOwn(controls.buildSave(data, controls.readForm(container)).declaration.contact, "master_union_same_slave"), false);
  assert.match(container.textContent, /같은 slave 면의 여러 frictionless master 면을 하나의 접촉 영역으로 묶기\(명시적 선언\)/);
  assert.match(container.textContent, /원래 master\/slave 면 그룹을 보존/);
  let changes = 0; container.addEventListener("input", () => { changes++; });
  const checkbox = fieldNode(container, "masterUnionSameSlave"); checkbox.checked = true; checkbox.dispatchEvent({ type: "input", bubbles: true });
  assert.equal(changes, 1); assert.equal(controls.buildSave(data, controls.readForm(container)).declaration.contact.master_union_same_slave, true);
  checkbox.checked = false;
  assert.equal(Object.hasOwn(controls.buildSave(data, controls.readForm(container)).declaration.contact, "master_union_same_slave"), false);
});

test("rendered saved workflow supports explicit additional partial BC, changed contact law/master and row removal", () => {
  const container = form(), data = catalog(), value = record(data), restored = controls.fromRecord(value, data);
  let notifications = 0; container.addEventListener("input", () => { notifications++; });
  controls.renderForm(container, data, restored);
  assert.deepEqual(controls.buildSave(data, controls.readForm(container)), value.request); assert.match(container.textContent, /재료 7\/7 배정/);
  click(addButton(container, "boundaryRows"));
  const added = rowNodes(container, "boundaryRows")[3];
  fieldNode(added, "selectionId").value = faceId("workpiece", 2); change(fieldNode(added, "selectionId"));
  fieldNode(added, "uxEnabled").checked = true; change(fieldNode(added, "uxEnabled"));
  assert.equal(fieldNode(added, "ux").disabled, false); fieldNode(added, "ux").value = "0.01"; fieldNode(added, "source").value = "ASSUMED: explicit X only";
  const firstContact = rowNodes(container, "contactRows")[0];
  fieldNode(firstContact, "law").value = "frictionless"; change(fieldNode(firstContact, "law")); fieldNode(firstContact, "master").value = "a";
  assert.equal(fieldNode(firstContact, "distanceMaxMm").disabled, true);
  const changed = controls.buildSave(data, controls.readForm(container));
  assert.deepEqual(changed.declaration.boundary_conditions[3].components, { UX: 0.01 });
  assert.equal(changed.declaration.contact.pairs[0].master, "a"); assert.equal(Object.hasOwn(changed.declaration.contact.pairs[0], "distance_max_mm"), false);
  assert.throws(() => controls.buildRun(value, data, controls.readForm(container), "E-new-solve"), /저장 후/);
  click(walk(added).find(node => node.dataset.assemblyRemove === "boundaryRows"));
  assert.equal(controls.readForm(container).boundaryRows.length, 3); assert(notifications >= 2);
  container.replaceChildren(); assert.throws(() => controls.readForm(container), /이전 DOM/);
});

test("catalog withdrawal or changed targets retain exact typed row drafts as unavailable options and refuse save", () => {
  const input = fields(); input.materialRows[0].youngModulus = " 2.1e5 "; input.materialRows[0].source = " \nASSUMED: 원 출처 보존\n ";
  input.boundaryRows[1].selectionId = "I-left_support-2"; input.boundaryRows[0].uy = "unchecked raw draft"; input.loadRows[0].fx = "-0";
  input.contactRows[0].distanceMaxMm = " 1.25e-1 ";
  const missingMesh = catalog({ mesh: false }), changed = catalog();
  changed.source.cad_revision = "5".repeat(64); changed.catalog.retained_mesh.cad_revision = changed.source.cad_revision;
  changed.catalog.selections = changed.catalog.selections.filter(item => ![faceId("base_plate"), faceId("pressure_block"), faceId("workpiece")].includes(item.id));
  for (const data of [missingMesh, changed]) {
    const container = form(); controls.renderForm(container, interiorCatalog(), input);
    const original = controls.readForm(container); controls.renderForm(container, data, original);
    const restored = controls.readForm(container);
    for (const key of ["materialRows", "boundaryRows", "loadRows", "contactRows"]) assert.deepEqual(restored[key], input[key]);
    assert.equal(restored.contactSource, input.contactSource);
    const oldBoundary = rowNodes(container, "boundaryRows")[1], selection = fieldNode(oldBoundary, "selectionId");
    assert.equal(selection.value, "I-left_support-2");
    const unavailable = selection.children.find(option => option.value === selection.value);
    assert.equal(unavailable.dataset.assemblyUnavailable, "true"); assert.match(unavailable.textContent, /현재 CAD catalog에서 사용할 수 없는 대상/);
    assert.match(container.textContent, /사용할 수 없는 대상 · I-left_support-2/);
    assert.throws(() => controls.buildSave(data, restored), /보존 메시|catalog ID/);
  }
});

test("missing retained mesh disables additions and an outer disabled form does not add rows", () => {
  const container = form(); controls.renderForm(container, catalog({ mesh: false }), {});
  assert.equal(addButton(container, "materialRows").disabled, true); click(addButton(container, "materialRows")); assert.equal(controls.readForm(container).materialRows.length, 0);
  controls.renderForm(container, catalog(), fields());
  walk(container).find(node => node.dataset.assemblyConditionsForm).disabled = true;
  click(addButton(container, "contactRows")); assert.equal(controls.readForm(container).contactRows.length, 2);
  click(walk(rowNodes(container, "contactRows")[0]).find(node => node.dataset.assemblyRemove)); assert.equal(controls.readForm(container).contactRows.length, 2);
});

test("browser/CommonJS share additive module contract and missing common validator never fabricates context", () => {
  const browser = { window: {} };
  vm.runInNewContext(readFileSync(require.resolve("../apps/lab/static/analysis-conditions-controls.js"), "utf8"), browser);
  vm.runInNewContext(readFileSync(require.resolve("../apps/lab/static/assembly-conditions-controls.js"), "utf8"), browser);
  assert.deepEqual(Object.keys(browser.window.assemblyConditionsControls), ["isAssembly", "rowsFromCatalog", "buildSave", "fromRecord", "buildRun", "renderForm", "readForm"]);
  assert.equal(JSON.stringify(browser.window.assemblyConditionsControls.buildSave(catalog(), fields())), JSON.stringify(controls.buildSave(catalog(), fields())));
  const unavailable = { window: {} }; vm.runInNewContext(readFileSync(require.resolve("../apps/lab/static/assembly-conditions-controls.js"), "utf8"), unavailable);
  assert.equal(unavailable.window.assemblyConditionsControls.isAssembly(catalog()), false);
  assert.throws(() => unavailable.window.assemblyConditionsControls.rowsFromCatalog(catalog()), /공통 CAD 조건 검증기가 없습니다/);
});
