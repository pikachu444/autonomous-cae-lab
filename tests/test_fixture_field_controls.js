"use strict";

// TEST_ONLY TET10/FRD-looking vectors. No native execution or retained data copied.
const { test } = require("node:test"), assert = require("node:assert/strict"), crypto = require("node:crypto");
const controls = require("../apps/lab/static/fixture-field-controls.js");
const clone = value => JSON.parse(JSON.stringify(value));
const digest = bytes => crypto.createHash("sha256").update(bytes).digest("hex");
const token = value => value.toExponential(5).replace(/e([+-])(\d+)$/, (_, sign, exponent) => `E${sign}${exponent.padStart(2, "0")}`);
function fixture({ legacy = false } = {}) {
  const revision = "a".repeat(64), parent = "E-TEST_ONLY-cad", id = "E-TEST_ONLY-field", ids = [7, 11, 21, 43, 54, 67, 81, 102, 145, 209];
  const xyz = [[0, 0, 0], [2, 0, 0], [0, 2, 0], [0, 0, 2], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [0, 1, 1]];
  const observed = { 43: [-.01, .02, -.03], 102: [.002, .003, -.004], 145: [.001, -.002, -.05], 209: [.001, .01, -.09] };
  const sizes = legacy ? [4, 3] : [4], version = legacy ? "5" : "6", entries = [], artifacts = [], byPath = new Map();
  sizes.forEach((size, index) => {
    const prefix = `simulation/support_${index}/`, sources = {};
    for (const [key, name] of Object.entries({ mesh: "gmsh.inp", deck: `support_${index}.inp`, saddle: "saddle_load.json", frd: `support_${index}.frd`, dat: `support_${index}.dat` })) {
      const raw = Buffer.from(`TEST_ONLY ${index} ${key} metadata pin; not native input/output`);
      sources[key] = { path: name, sha256: digest(raw), bytes: raw.length };
      artifacts.push({ path: prefix + name, sha256: digest(raw), size_bytes: raw.length, revision, mime_type: "application/octet-stream" });
    }
    const field = { schema_version: "1.0", kind: "fixture_calculix_nodal_displacement", backend: "fixture.calculix", adapter_version: version,
      parent_experiment_id: parent, cad_revision: revision, mesh_index: index, mesh_size_max_mm: size,
      coordinate_frame: "SOLVER_GLOBAL_CARTESIAN", position_unit: "mm", displacement_unit: "mm", force_unit: "N",
      static: { step: 1, increment: 1, load_parameter: 1 }, coverage: "ALL_MESH_NODES", qualification: "UNKNOWN", engineering_valid: false,
      nodes: ids.map((node, i) => { const u = observed[node] ?? [0, 0, 0]; return { node_id: node, position_mm: xyz[i], displacement_mm: u, displacement_tokens: u.map(token) }; }),
      elements: [{ element_id: 31, type: "C3D10", node_ids: ids }], boundary_faces: [
        { element_id: 2, group: "BOTTOM", type: "CPS6", node_ids: [7, 11, 21, 54, 67, 81] },
        { element_id: 3, group: "SADDLE_SIDE", type: "CPS6", node_ids: [7, 43, 11, 102, 145, 54] },
        { element_id: 5, group: "WALL_A", type: "CPS6", node_ids: [11, 43, 21, 145, 209, 67] },
        { element_id: 17, group: "WALL_B", type: "CPS6", node_ids: [21, 43, 7, 209, 102, 81] }],
      fixed_node_ids: [7, 11, 21, 54, 67, 81], fixed_dofs: [1, 2, 3], loads: [43, 102, 145].map((node, i) => ({ node_id: node, dof: 3, force_N: [0, 0, -i - 1], force_token: String(-i - 1) })),
      node_count: 10, element_count: 1, boundary_face_count: 4, sources };
    const bytes = Buffer.from(JSON.stringify(field)), path = prefix + "fea_field.json";
    artifacts.push({ path, sha256: digest(bytes), size_bytes: bytes.length, revision, mime_type: "application/json" }); byPath.set(path, bytes); entries.push(field);
  });
  const mesh = legacy ? { max_sizes_mm: sizes } : { mode: "selected", max_sizes_mm: sizes };
  const execution = { load: { force_per_support_N: 6, source: "TEST_ONLY" }, material: { provenance: "TEST_ONLY" }, mesh };
  const inspection = { integrity: "VERIFIED", result: { experiment_id: id, parent_experiment_id: parent, cad_revision: revision, solver_status: "COMPLETED", converged: true,
    decision: "NOT_RELEASED", status: "COMPLETED_REVIEW_REQUIRED", artifacts, validations: ["machine_interface", "static_strength", "physical_load_test", "fatigue_durability", "joint_and_contact", "material_qualification", "stress_convergence"].map(type => ({ type, status: "UNKNOWN", blocking: true })),
    metrics: { max_displacement: { value: .05, unit: "mm", valid: true }, peak_stress: { value: 99, unit: "MPa", valid: false, reason: "TEST_ONLY diagnostic" },
      displacement_mesh_change_ratio: { value: legacy ? .01 : null, unit: "1", valid: legacy } },
    provenance: { adapter: "fixture.calculix", adapter_version: version, parent_experiment_id: parent, core_commit: "b".repeat(40), source_commit: "c".repeat(40), execution_settings: execution,
      adapter_details: { adapter: "fixture.calculix", adapter_version: version, parent_experiment_id: parent, cad_revision: revision, mesh_max_sizes_mm: sizes,
        force_per_support_N: 6, mesh_policy: { mode: legacy ? "refinement" : "selected" }, ...(legacy ? {} : { mesh_sensitivity: { status: "NOT_ASSESSED" } }),
        per_mesh_displacement: { studies: entries.map((field, index) => ({ index, mesh_size_max_mm: sizes[index], loaded_node_count: 3,
          displacement_table: `simulation/support_${index}/support_${index}.dat`, displacement_table_sha256: field.sources.dat.sha256 })) } } } },
    proposal: { id, parent_experiment_id: parent, execution, model: { geometry: { source_experiment_id: parent, cad_revision: revision } }, physics: { backend: "fixture.calculix" } },
    thread: { experiment: id, parent_experiment: parent, cad_revision: revision } };
  return { field: entries[0], fields: entries, inspection, path: "simulation/support_0/fea_field.json", bytes: byPath.get("simulation/support_0/fea_field.json"), byPath };
}
function verify(data) { return controls.verifyField(data.field, data.inspection, data.path); }
function rebind(data, bytes) { const item = data.inspection.result.artifacts.find(item => item.path === data.path); item.sha256 = digest(bytes); item.size_bytes = bytes.length; }
module.exports = { fixture, clone, digest, verify, rebind };

if (require.main === module) {
  test("TEST_ONLY full field retains gapped native IDs, complete topology, three U components, UNKNOWN and original metrics", () => {
    const data = fixture(), before = JSON.stringify(data), model = verify(data);
    assert.equal(model.field.node_count, 10); assert.equal(model.field.boundary_face_count, 4); assert.equal(model.metadata.saddleGroup, "SADDLE_SIDE");
    assert.equal(model.metadata.fieldProducer, "6"); assert.equal(model.metadata.resultProducer, "6"); assert.equal(model.metadata.sensitivity, "NOT_ASSESSED");
    assert.equal(model.metadata.unknownCount, 7); assert.equal(model.metadata.decision, "NOT_RELEASED"); assert.equal(data.inspection.result.metrics.peak_stress.valid, false);
    assert.equal(JSON.stringify(data), before); assert(Object.isFrozen(model.field.nodes[0].displacement_mm));
    data.field.nodes[0].position_mm[0] = 99; assert.equal(model.field.nodes[0].position_mm[0], 0);
  });
  for (const [name, fault] of Object.entries({
    integrity: d => d.inspection.integrity = "NOT_CHECKED", parent: d => d.field.parent_experiment_id = "E-other", revision: d => d.field.cad_revision = "d".repeat(64),
    result_version: d => d.inspection.result.provenance.adapter_version = "7", field_version: d => d.field.adapter_version = "7", proposal_parent: d => d.inspection.proposal.parent_experiment_id = "E-other",
    thread_revision: d => d.inspection.thread.cad_revision = "d".repeat(64), source_digest: d => d.field.sources.frd.sha256 = "d".repeat(64), source_bytes: d => d.field.sources.dat.bytes++,
    source_path: d => d.field.sources.deck.path = "../support_0.inp", source_revision: d => d.inspection.result.artifacts[0].revision = "d".repeat(64), duplicate_manifest: d => d.inspection.result.artifacts.push(d.inspection.result.artifacts[0]),
    unsafe_path: d => d.inspection.result.artifacts[0].path = "../mesh.inp", wrong_field_path: d => d.inspection.result.artifacts.at(-1).path = "cad/fea_field.json", wrong_mime: d => d.inspection.result.artifacts.at(-1).mime_type = "text/html",
    step: d => d.field.static.step = 2, load_parameter: d => d.field.static.load_parameter = .5, fake_time: d => d.field.static.time = 1, units: d => d.field.displacement_unit = "m", frame: d => d.field.coordinate_frame = "CAD_LOCAL",
    partial_coverage: d => d.field.coverage = "ROLLER_NODES", promoted_qualification: d => d.field.qualification = "PASS", promoted_stress: d => d.field.engineering_valid = true,
    missing_node: d => d.field.nodes.pop(), duplicate_node: d => d.field.nodes[1].node_id = 7, unsafe_node_id: d => d.field.nodes[1].node_id = Number.MAX_SAFE_INTEGER + 1,
    nonfinite_X: d => d.field.nodes[3].displacement_mm[0] = Infinity, missing_UY: d => d.field.nodes[3].displacement_mm.splice(1, 1), changed_nonextreme_UX: d => d.field.nodes[3].displacement_mm[0] = .02,
    missing_native_token: d => d.field.nodes[3].displacement_tokens.pop(), foreign_connectivity: d => d.field.elements[0].node_ids[9] = 999, repeated_element_node: d => d.field.elements[0].node_ids[9] = 7,
    incomplete_exterior: d => { d.field.boundary_faces.pop(); d.field.boundary_face_count--; }, swapped_midside: d => [d.field.boundary_faces[0].node_ids[3], d.field.boundary_faces[0].node_ids[4]] = [67, 54],
    duplicate_face_id: d => d.field.boundary_faces[1].element_id = 2, invalid_fixed_set: d => d.field.fixed_node_ids.pop(), wrong_fixed_dofs: d => d.field.fixed_dofs = [3],
    fixed_loaded_overlap: d => d.field.loads[0].node_id = 7, changed_force_token: d => d.field.loads[0].force_token = "-9", wrong_force_direction: d => d.field.loads[0].force_N[0] = 1,
    loaded_DAT_association: d => d.inspection.result.provenance.adapter_details.per_mesh_displacement.studies[0].displacement_table_sha256 = "d".repeat(64),
    selected_fake_trend: d => d.inspection.result.metrics.displacement_mesh_change_ratio.valid = true,
  })) test(`refuses ${name} before a trusted field is available`, () => { const data = fixture(); fault(data); assert.throws(() => verify(data)); });
  test("nonmanifold C3D10 faces are rejected independently of boundary counts", () => {
    const data = fixture(); data.field.elements.push({ ...clone(data.field.elements[0]), element_id: 32 }, { ...clone(data.field.elements[0]), element_id: 33 }); data.field.element_count = 3;
    assert.throws(() => verify(data), /비다양체/);
  });
  test("GUI byte and item budgets are resource bounds, with no native calls", async () => {
    const data = fixture(); data.inspection.result.artifacts.at(-1).size_bytes = controls.LIMITS.bytes + 1; assert.throws(() => controls.catalog(data.inspection), /32 MiB/);
    const oversized = fixture(); oversized.field.nodes = Array(controls.LIMITS.nodes + 1).fill(oversized.field.nodes[0]); oversized.field.node_count = oversized.field.nodes.length;
    assert.throws(() => verify(oversized), /항목 범위/);
  });
  test("legacy v5 preserves declared last-pair statistics; old partial records are unavailable without invented U", () => {
    const legacy = fixture({ legacy: true }), before = JSON.stringify(legacy.inspection); const model = verify(legacy);
    assert.equal(model.metadata.sensitivity, "RECORDED_SCREEN"); assert.equal(JSON.stringify(legacy.inspection), before);
    const old = fixture(); old.inspection.result.artifacts = old.inspection.result.artifacts.filter(item => !item.path.endsWith("fea_field.json")); old.inspection.result.provenance.adapter_version = "4";
    const entry = controls.catalog(old.inspection); assert.equal(entry.status, "unavailable"); assert.deepEqual(entry.entries, []);
  });
  test("raw SHA/bytes loader fetches only the manifested field, freezes bytes across await, and keeps source pins", async () => {
    const data = fixture(), record = controls.catalog(data.inspection), calls = [], bytes = Uint8Array.from(data.bytes);
    const pending = controls.loadField(record, record.entries[0], async (path, expected) => { calls.push([path, expected]); return bytes; }, () => true);
    await Promise.resolve(); bytes.fill(0); const model = await pending;
    assert.deepEqual(calls, [[data.path, data.bytes.length]]); assert.equal(model.field.nodes[3].displacement_mm[0], -.01); assert.equal(Object.keys(model.field.sources).length, 5);
  });
  test("same-length altered bytes and incomplete bytes are refused", async () => {
    for (const truncate of [false, true]) { const data = fixture(), record = controls.catalog(data.inspection), bytes = Uint8Array.from(data.bytes); bytes[20] ^= 1;
      await assert.rejects(controls.loadField(record, record.entries[0], async () => truncate ? bytes.slice(1) : bytes, () => true), truncate ? /크기/ : /SHA-256/); }
  });
  test("duplicate JSON keys and malformed UTF-8 are rejected after matching raw digest", async () => {
    for (const invalidUtf8 of [false, true]) { const data = fixture(); const bytes = invalidUtf8 ? Buffer.from([255, ...data.bytes.slice(1)]) : Buffer.from(data.bytes.toString().replace('"schema_version":', '"schema_version":"0.0","schema_version":'));
      rebind(data, bytes); const record = controls.catalog(data.inspection); await assert.rejects(controls.loadField(record, record.entries[0], async () => Uint8Array.from(bytes), () => true)); }
  });
  test("late field success and late reader failure cannot return a field after selection changes", async () => {
    for (const fail of [false, true]) { const data = fixture(), record = controls.catalog(data.inspection); let current = true, settle;
      const pending = controls.loadField(record, record.entries[0], () => new Promise((resolve, reject) => { settle = fail ? reject : resolve; }), () => current);
      current = false; settle(fail ? new Error("TEST_ONLY late native-file error") : Uint8Array.from(data.bytes)); await assert.rejects(pending); }
  });
}
