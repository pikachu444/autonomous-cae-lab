"use strict";

// Tiny UNSOLVED layout fixtures. XDMF/H5 placeholders are never native evidence.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { createHash, webcrypto } = require("node:crypto");
const { readFileSync } = require("node:fs");
const vm = require("node:vm");
const reader = require("../apps/lab/static/pde-field-inspector.js");
const hash = (data) => createHash("sha256").update(data).digest("hex");
const copy = (x) => structuredClone(x);
const now = () => true;
const moduleSource = readFileSync(require.resolve("../apps/lab/static/pde-field-inspector.js"), "utf8");
function browser(crypto = webcrypto) {
  const context = { window: { crypto }, TextEncoder, TextDecoder, Uint8Array };
  vm.runInNewContext(moduleSource, context); return context.window.pdeFieldInspector;
}
function nativeField(vector = false) {
  const values = vector ? [[1, -3], [2, 4], [-5, 6], [7, -8]] : [1, 2, 3, 4];
  const pair = (i, ids, measure, normal) => ({ facet_ids: [i], facet_node_ids: [ids], dof_ids: [...ids].sort((a, b) => a - b),
    measure, normal_integral: normal, prescribed_values: vector ? [[1, -2], [3, -4]] : [1, 2], prescribed_integral: vector ? [4, -6] : 3 });
  return { schema_version: "1", coordinates_unit: "1", field_unit: "1", ...(vector ? { field_type: "vector", components: ["u0", "u1"], block_size: 2 } : {}),
    node_ids: [0, 5, 9, 12], coordinates: [[0, 0], [2, 0], [0, 1], [2, 1]], values,
    cell_node_ids: [[0, 5, 12], [0, 12, 9]], dirichlet_node_ids: [0, 5, 9],
    boundaries: { xmin: pair(0, [0, 9], 1, [-1, 0]), xmax: pair(3, [5, 12], 1, [1, 0]),
      ymin: pair(6, [0, 5], 2, [0, -2]), ymax: pair(8, [9, 12], 2, [0, 2]) } };
}
function couplingField() {
  const field = nativeField(true), old = field.boundaries;
  const segment = (facet, endpoints) => ({ facet_ids: [facet], facet_node_ids: [endpoints], dof_ids: [...endpoints].sort((a, b) => a - b), measure: 1,
    normal_integral: [0, -1], prescribed_values: [[1, -2], [3, -4]], prescribed_integral: [4, -6] });
  return { ...field, node_ids: [0, 5, 9, 12, 20, 31], coordinates: [[0, 0], [2, 0], [0, 1], [2, 1], [1, 0], [1, 1]],
    values: [[1, -3], [2, 4], [-5, 6], [7, -8], [9, -10], [-11, 12]], cell_ids: [0, 6, 15, 21],
    cell_node_ids: [[0, 20, 31], [0, 31, 9], [20, 5, 12], [20, 12, 31]], cell_regions: ["left", "left", "right", "right"],
    dirichlet_node_ids: [0, 5, 9, 20], interface: { facet_ids: [40], facet_node_ids: [[20, 31]], node_ids: [20, 31],
      adjacent_cell_ids: [[0, 21]], measure: 1, plus_x_normal: [1, 0] },
    boundaries: { xmin: { left: old.xmin }, xmax: { right: old.xmax },
      ymin: { left: segment(6, [0, 20]), right: segment(7, [20, 5]) },
      ymax: { left: segment(8, [9, 31]), right: segment(9, [31, 12]) } } };
}
function fixture(kind = "rectangle", rejected = false) {
  const buffers = new Map(), refs = [], reads = [], fields = [], bindings = [];
  const put = (path, value) => buffers.set(path, Buffer.from(typeof value === "string" ? value : JSON.stringify(value, null, 2), "utf8"));
  const vector = ["vector", "coupled"].includes(kind), coupled = kind === "coupled", imported = kind === "imported", transient = kind === "transient";
  const source = { schema_version: "1", domain_plugin_version: "1", files: { reader_fixture: {
    repository_path: "tests/synthetic_worker.py", copied_path: "sources/synthetic_worker.py", sha256: hash("UNSOLVED source fixture\n") } } };
  put("pde/sources/synthetic_worker.py", "UNSOLVED source fixture\n"); put("pde/source_manifest.json", source);
  const settings = { problem: { domain: imported ? { type: "imported_mesh", body: "body" } : { type: "rectangle", lengths: [2, 1] },
    weak_form: coupled ? { diffusion: { left: [[2, .5], [.5, 1]], right: [[4, -.5], [-.5, 2]] }, reaction: [[0, 0], [0, 0]] } : { diffusion: 1, reaction: 0, rhs: "0" },
    boundaries: Object.fromEntries(["xmin", "xmax", "ymin", "ymax"].map((side) => [side, { type: ["xmin", "ymin"].includes(side) ? "dirichlet" : "neumann",
      value: coupled ? Object.fromEntries((side === "xmin" ? ["left"] : side === "xmax" ? ["right"] : ["left", "right"]).map((r) => [r, ["1", "2"]])) : vector ? ["1", "2"] : "1" }])),
    reference: { source: "UNSOLVED synthetic reader layout; not numerical qualification", solution: vector ? ["1", "2"] : "1" } },
    mesh: imported ? { degree: 1, levels: [{ format: "gmsh_msh2_ascii", source: "UNSOLVED.msh", data: "UNSOLVED original mesh bytes\r\n", sha256: hash("UNSOLVED original mesh bytes\r\n") }] } : { degree: 1, cell_counts: [coupled ? 2 : 1] }, validation: { untouched_source_only: true } };
  if (transient) { settings.time = { start: 0, end: 1, step_counts: [2], unit: "1", scheme: "backward_euler" }; settings.refinement_axis = "time"; }
  put("pde/input.json", settings);
  const worker = { schema_version: "1", status: "COMPLETED", spec_sha256: hash(buffers.get("pde/input.json")), source_manifest_sha256: hash(buffers.get("pde/source_manifest.json")), mpi_size: 1, scalar_type: "float64", versions: { fixture: "UNSOLVED" } };
  const rows = [];
  for (let j = 0; j < (transient ? 3 : 1); j++) {
    const field = coupled ? couplingField() : nativeField(vector);
    let binding = null, mapping = null;
    const prefix = transient ? `study_0/step_${j}` : imported ? "level_0" : `level_n${settings.mesh.cell_counts[0]}`;
    const files = { field: `${prefix}/field.xdmf`, field_data: `${prefix}/field.h5`, form_source: `${prefix}/forms.ufl.txt`, dofs: `${prefix}/dofs.json` };
    let rawValues = null;
    if (transient) { files.time_binding = `${prefix}/time_binding.json`; rawValues = j === 0 ? "[1.0,-0.0,1e-05,4.5]" : j === 1 ? "[2.0,-0.0,2e-05,5.5]" : "[3.0,-0.0,3e-05,6.5]"; field.values = JSON.parse(rawValues); }
    if (vector || imported) files.binding = `${prefix}/binding.json`;
    if (imported) {
      Object.assign(files, { original: `${prefix}/original.msh`, dense: `${prefix}/dense-import.msh`, mapping: `${prefix}/import_mapping.json` });
      Object.assign(field, { cell_ids: [0, 11], source_node_ids: [101, 107, 201, 505], source_cell_ids: [601, 901] });
      Object.entries(field.boundaries).forEach(([name, b], i) => { b.source_element_ids = [1001 + i]; });
      put(`pde/${files.original}`, settings.mesh.levels[0].data); put(`pde/${files.dense}`, "UNSOLVED dense derived mesh bytes\n");
      mapping = { schema_version: "1", original_sha256: settings.mesh.levels[0].sha256, dense_sha256: hash(buffers.get(`pde/${files.dense}`)),
        dense_node_ids: [1, 2, 3, 4], original_node_ids: [101, 107, 201, 505], geometry_input_indices: [2, 0, 3, 1], geometry_source_node_ids: [201, 101, 505, 107],
        vertex_ids: [0, 3, 7, 9], vertex_geometry_indices: [1, 3, 0, 2], vertex_dof_ids: [0, 5, 9, 12],
        cell_ids: [0, 11], original_cell_index: [1, 0], importer_cell_source_ids: [901, 601], source_cell_ids: [601, 901],
        physical_groups: { body: { dim: 2, tag: 1 }, xmin: { dim: 1, tag: 2 }, xmax: { dim: 1, tag: 3 }, ymin: { dim: 1, tag: 4 }, ymax: { dim: 1, tag: 5 } },
        boundary_source_elements: Object.fromEntries(Object.entries(field.boundaries).map(([name, b]) => [name, b.source_element_ids])), gmsh_initialization: { argv: [], read_config_files: false, finalized: true } };
      binding = { schema_version: "1", node_ids: field.node_ids, source_node_ids: field.source_node_ids, source_sha256: mapping.original_sha256, dense_sha256: mapping.dense_sha256,
        diffusion: 1, reaction: 0, rhs_values: [0, 0, 0, 0], reference_values: [1, 2, 3, 4] };
    } else if (coupled) {
      binding = { schema_version: "1", components: ["u0", "u1"], regions: {} };
      for (const region of ["left", "right"]) {
        const cell_ids = field.cell_ids.filter((id, i) => field.cell_regions[i] === region), node_ids = region === "left" ? [0, 9, 20, 31] : [5, 12, 20, 31];
        binding.regions[region] = { cell_ids, node_ids, diffusion: settings.problem.weak_form.diffusion[region], reaction: settings.problem.weak_form.reaction,
          rhs_values: node_ids.map(() => [3, -4]), reference_values: node_ids.map(() => [1, -2]) };
      }
    } else if (vector || transient) {
      binding = { schema_version: "1", node_ids: field.node_ids, ...(vector ? { components: ["u0", "u1"] } : { time: j / 2 }),
        rhs_values: vector ? field.values : [0, 0, 0, 0], reference_values: field.values };
    }
    put(`pde/${files.field}`, "UNSOLVED XDMF placeholder"); put(`pde/${files.field_data}`, "UNSOLVED H5 placeholder"); put(`pde/${files.form_source}`, "UNSOLVED form source placeholder");
    if (rawValues) put(`pde/${files.dofs}`, JSON.stringify(field, null, 2).replace(/"values": \[[\s\S]*?\]/, `"values": ${rawValues}`));
    else put(`pde/${files.dofs}`, field);
    if (binding) put(`pde/${files.binding || files.time_binding}`, binding); if (mapping) put(`pde/${files.mapping}`, mapping);
    const nodes = field.node_ids.length, prescribed = field.dirichlet_node_ids.length;
    const row = { degree: 1, cell_type: "triangle", cells_per_axis: settings.mesh.cell_counts?.[0], global_cells: field.cell_node_ids.length,
      global_dofs: nodes * (vector ? 2 : 1), dirichlet_dofs: prescribed * (vector ? 2 : 1), files, artifact_sha256: {} };
    if (vector || imported) Object.assign(row, { global_nodes: nodes, dirichlet_nodes: prescribed });
    if (vector) row.block_size = 2;
    if (coupled) Object.assign(row, { region_cell_counts: { left: 2, right: 2 }, region_coefficients: settings.problem.weak_form.diffusion, reaction_matrix: settings.problem.weak_form.reaction });
    if (imported) Object.assign(row, { level: 0, source_sha256: mapping.original_sha256, dense_sha256: mapping.dense_sha256, physical_groups: mapping.physical_groups, coefficients: { diffusion: 1, reaction: 0 } });
    if (transient) Object.assign(row, { index: j, time: j / 2, native_time_value: j / 2, dt: j ? .5 : 0, solver_status: j ? "COMPLETED" : "NOT_RUN",
      previous_values_sha256: j ? rows[j - 1].current_values_sha256 : null, current_values_sha256: hash(`{"node_ids":[0,5,9,12],"values":${rawValues}}`), distinct_state: true,
      linear_residual: j ? { relative: 1e-12 } : null, ksp_convergence_reason: j ? 1 : null, ksp_iterations: j ? 1 : null });
    rows.push(row); refs.push({ row, files }); fields.push(field); bindings.push(binding);
  }
  if (transient) worker.studies = [{ study_index: 0, cells_per_axis: 1, step_count: 2, dt: .5, refinement_axis: "time", steps: rows }];
  else worker.mesh_studies = rows;
  const backend = `pde.fenicsx.${kind}`, revision = "a".repeat(64), model = "b".repeat(64);
  const inspection = { integrity: "VERIFIED", proposal: { id: "E-reader-UNSOLVED", study_id: "S-reader-UNSOLVED", model_revision: model, physics: { backend }, execution: copy(settings) },
    thread: { experiment: "E-reader-UNSOLVED", study: "S-reader-UNSOLVED", model_revision: model }, ledger: { experiment_id: "E-reader-UNSOLVED" },
    result: { experiment_id: "E-reader-UNSOLVED", study: { id: "S-reader-UNSOLVED" }, status: rejected ? "REJECTED" : "COMPLETED_REVIEW_REQUIRED", decision: "NOT_RELEASED", solver_status: "COMPLETED", converged: true,
      model_revision: model, proposal_revision: revision, artifacts: [], metrics: { l2_error: { value: .25, unit: "1", valid: !rejected, reason: rejected ? "Retained numerical rejection" : "UNSOLVED test observation" } },
      validations: [{ type: "physical_validation", status: "UNKNOWN", blocking: true }], evidence: [{ observation: { status: rejected ? "FAIL" : "PASS", fixture: "UNSOLVED" } }],
      provenance: { proposal_sha256: revision, adapter: backend, execution_settings: copy(settings), adapter_details: { adapter: backend, domain_plugin_version: "1", units: "dimensionless",
        spec_sha256: worker.spec_sha256, source_manifest_sha256: worker.source_manifest_sha256, source_manifest: "pde/source_manifest.json", source_sha256: { reader_fixture: source.files.reader_fixture.sha256 } } } } };
  function seal() {
    for (const { row, files } of refs) row.artifact_sha256 = Object.fromEntries(Object.entries(files).map(([key, path]) => [key, hash(buffers.get(`pde/${path}`))]));
    put("pde/worker_result.json", worker);
    inspection.result.artifacts = [...buffers].map(([path, data]) => ({ path, sha256: hash(data), size_bytes: data.byteLength, revision, mime_type: "application/octet-stream" }));
    inspection.hashes = { artifacts: copy(inspection.result.artifacts) }; return inspection;
  }
  seal();
  const fetchBytes = async (path) => { reads.push(path); if (!buffers.has(path)) throw new Error("Missing source fixture"); return Uint8Array.from(buffers.get(path)); };
  return { inspection, worker, settings, source, buffers, refs, fields, bindings, reads, put, seal, fetchBytes };
}
async function opened(f = fixture(), api = reader, index = 0) {
  const catalog = await api.loadCatalog(f.inspection, f.fetchBytes, now);
  assert.equal(catalog.status, "available", catalog.reason);
  const field = await api.loadField(catalog, catalog.entries[index], f.fetchBytes, now);
  return { catalog, field };
}
function cleared(result, status = "error") {
  assert.equal(result.status, status, result.reason); assert.equal(typeof result.reason, "string");
  assert.deepEqual(result.nodes, []); assert.deepEqual(result.cells, []);
}

test("browser/CommonJS expose retained-field reads and exact observation identity", () => {
  assert.deepEqual(Object.keys(reader), ["loadCatalog", "loadField", "observationSelection"]); assert.deepEqual(Object.keys(browser()), Object.keys(reader));
});
test("PDE observation selection binds the original DOF bytes, model/level and native node zero", async () => {
  const {field}=await opened();
  const selected=reader.observationSelection(field,0,"u");
  assert.equal(selected.node_id,0); assert.equal(selected.model_revision,field.metadata.modelRevision);
  assert.equal(selected.artifact,field.source.artifact); assert.equal(selected.sha256,field.source.sha256);
  assert.equal(selected.study_index,field.selection.studyIndex); assert.equal(selected.step_index,field.selection.stepIndex);
  assert.equal(Object.hasOwn(selected,"value"),false);
  assert.throws(()=>reader.observationSelection(field,999,"u"));
  assert.throws(()=>reader.observationSelection(field,0,"UX"));
});
for (const kind of ["rectangle", "vector", "coupled", "imported"]) test(`${kind}: exact native layout, zero/sparse IDs and original UNKNOWN/rejected verdicts`, async () => {
  const f = fixture(kind, true), before = JSON.stringify(f.inspection), { catalog, field } = await opened(f);
  assert.equal(field.status, "available", field.reason); assert.equal(field.nodes[0].id, 0); assert.equal(field.nodes[1].id, 5);
  assert.equal(field.metadata.status, "REJECTED"); assert.equal(field.metadata.assessment.decision, "NOT_RELEASED");
  assert.equal(field.metadata.metrics.l2_error.valid, false); assert.equal(field.metadata.metrics.l2_error.reason, "Retained numerical rejection");
  assert.equal(field.metadata.assessment.validations[0].status, "UNKNOWN");
  assert.deepEqual(field.nodes.map((n) => n.values), f.fields[0].values.map((v) => Array.isArray(v) ? v : [v]));
  assert.equal(field.cells[0].rowIndex, 0); assert.equal(field.cells[0].id, ["coupled", "imported"].includes(kind) ? 0 : null);
  assert.equal(JSON.stringify(f.inspection), before); assert.ok(Object.isFrozen(catalog.entries[0].files)); assert.ok(Object.isFrozen(field.nodes[0].values));
  if (kind === "coupled") { assert.deepEqual(field.interface.adjacent_cell_ids, [[0, 21]]); assert.deepEqual(field.boundaries.ymin, f.fields[0].boundaries.ymin); }
  if (kind === "imported") { assert.equal(field.nodes[0].sourceId, 101); assert.equal(field.cells[0].sourceId, 601); assert.deepEqual(field.mapping.original_cell_index, [1, 0]); }
});

test("transient preserves Python float tokens/negative zero, chain and initial NOT_RUN", async () => {
  const f = fixture("transient"), { catalog, field: initial } = await opened(f);
  assert.equal(initial.status, "available", initial.reason); assert.equal(initial.selection.solverStatus, "NOT_RUN"); assert.equal(initial.selection.time, 0);
  assert.ok(Object.is(initial.nodes[1].values[0], -0)); assert.equal(initial.nodes[2].values[0], 1e-5);
  const final = await reader.loadField(catalog, catalog.entries[2], f.fetchBytes, now);
  assert.equal(final.status, "available", final.reason); assert.equal(final.selection.time, 1); assert.equal(final.binding.time, 1);
  assert.ok(f.reads.includes(catalog.entries[1].files.dofs));
  assert.notEqual(f.worker.studies[0].steps[0].current_values_sha256, hash(JSON.stringify({ node_ids: f.fields[0].node_ids, values: f.fields[0].values })));
});

test("caller inspection changes during an await cannot rewrite the immutable identity", async () => {
  const f = fixture(); let first = true;
  const fetch = async (path) => { if (first) { first = false; f.inspection.result.experiment_id = "E-other"; f.inspection.result.artifacts[0].sha256 = "0".repeat(64); } return f.fetchBytes(path); };
  const catalog = await reader.loadCatalog(f.inspection, fetch, now); assert.equal(catalog.status, "available", catalog.reason);
  assert.equal(catalog.metadata.experimentId, "E-reader-UNSOLVED"); assert.throws(() => { catalog.metadata.status = "PASS"; }, TypeError);
  const field = await reader.loadField(catalog, catalog.entries[0], f.fetchBytes, now); assert.equal(field.status, "available", field.reason);
  cleared(await reader.loadField(catalog, copy(catalog.entries[0]), f.fetchBytes, now));
  const foreign = (await opened(fixture())).catalog; cleared(await reader.loadField(catalog, foreign.entries[0], f.fetchBytes, now));
});

test("unowned catalog refusal does not return or freeze fabricated caller verdict metadata", async () => {
  const f = fixture(), { catalog } = await opened(f);
  const fake = { metadata: { status: "manufactured PASS" }, downloads: [], entries: [copy(catalog.entries[0])] };
  const refused = await reader.loadField(fake, fake.entries[0], f.fetchBytes, now); cleared(refused);
  assert.equal(refused.metadata, null); assert.equal(Object.isFrozen(fake.metadata), false);
});

test("same-record manifest proposal revision differs from model revision and is required", async () => {
  const f = fixture(); f.inspection.result.artifacts[0].revision = f.inspection.result.model_revision;
  const result = await reader.loadCatalog(f.inspection, f.fetchBytes, now); assert.equal(result.status, "error"); assert.match(result.reason, /proposal revision/); assert.equal(f.reads.length, 0);
});

test("unverified/cross-experiment/model/backend/proposal/ledger copies refuse before fetching", async (t) => {
  const mutations = {
    integrity: (x) => { x.integrity = "UNVERIFIED"; }, experiment: (x) => { x.proposal.id = "E-other"; },
    model: (x) => { x.proposal.model_revision = "c".repeat(64); }, backend: (x) => { x.proposal.physics.backend = "pde.fenicsx.vector"; },
    proposal: (x) => { x.result.provenance.proposal_sha256 = "d".repeat(64); }, ledger: (x) => { x.ledger.experiment_id = "E-other"; },
    thread: (x) => { x.thread.model_revision = "d".repeat(64); }, settings: (x) => { x.proposal.execution.mesh.degree = 2; },
  };
  for (const [label, mutate] of Object.entries(mutations)) await t.test(label, async () => {
    const f = fixture(); mutate(f.inspection); const result = await reader.loadCatalog(f.inspection, f.fetchBytes, now); assert.equal(result.status, "error", result.reason); assert.equal(f.reads.length, 0);
  });
});

test("duplicate, traversal and unexpected case-fold artifact aliases are refused", async (t) => {
  for (const path of ["pde/input.json", "PDE/INPUT.JSON", "../input.json", "/pde/input.json", "C:\\input.json", "pde/%2e%2e/input.json"]) await t.test(path, async () => {
    const f = fixture(); f.inspection.result.artifacts.push({ ...f.inspection.result.artifacts[0], path });
    const catalog = await reader.loadCatalog(f.inspection, f.fetchBytes, now); assert.equal(catalog.status, "error", catalog.reason); assert.equal(f.reads.length, 0);
  });
});

test("header byte length and raw SHA tamper never returns trusted fields", async (t) => {
  for (const mode of ["length", "sha"]) await t.test(mode, async () => {
    const f = fixture(), bytes = f.buffers.get("pde/input.json");
    f.buffers.set("pde/input.json", mode === "length" ? Buffer.concat([bytes, Buffer.from(" ")]) : Buffer.from(bytes.toString().replace('"diffusion": 1', '"diffusion": 2')));
    const catalog = await reader.loadCatalog(f.inspection, f.fetchBytes, now); assert.equal(catalog.status, "error", catalog.reason); assert.deepEqual(catalog.entries, []);
  });
});

test("native spec/source/copied bytes/row references do not substitute the Core record", async (t) => {
  for (const mutate of [
    (f) => { f.worker.spec_sha256 = "e".repeat(64); f.seal(); },
    (f) => { f.inspection.result.provenance.adapter_details.source_sha256.reader_fixture = "e".repeat(64); },
    (f) => { f.inspection.result.provenance.adapter_details.mpi_size = 2; },
    (f) => { f.inspection.result.provenance.adapter_details.scalar_type = "float32"; },
    (f) => { f.inspection.result.provenance.adapter_details.versions = { fixture: "foreign producer" }; },
    (f) => { f.source.files.reader_fixture.copied_path = "absent.py"; f.put("pde/source_manifest.json", f.source); f.worker.source_manifest_sha256 = hash(f.buffers.get("pde/source_manifest.json")); f.inspection.result.provenance.adapter_details.source_manifest_sha256 = f.worker.source_manifest_sha256; f.seal(); },
    (f) => { f.worker.mesh_studies[0].files.dofs = "foreign/dofs.json"; f.put("pde/foreign/dofs.json", f.fields[0]); f.seal(); f.inspection.result.artifacts = f.inspection.result.artifacts.filter((a) => a.path !== "pde/foreign/dofs.json"); f.inspection.hashes.artifacts = copy(f.inspection.result.artifacts); },
  ]) await t.test(String(mutate), async () => { const f = fixture(); mutate(f); const result = await reader.loadCatalog(f.inspection, f.fetchBytes, now); assert.equal(result.status, "error", result.reason); });
});

test("native-output-relative copied source paths bind once to experiment-relative Core artifacts", async () => {
  const f = fixture(), bytes = f.buffers.get("pde/sources/synthetic_worker.py");
  // Native workers also use a root-relative worker.py, not only sources/*.py.
  f.buffers.delete("pde/sources/synthetic_worker.py"); f.buffers.set("pde/worker.py", bytes);
  f.source.files.reader_fixture.copied_path = "worker.py"; f.put("pde/source_manifest.json", f.source);
  f.worker.source_manifest_sha256 = hash(f.buffers.get("pde/source_manifest.json"));
  f.inspection.result.provenance.adapter_details.source_manifest_sha256 = f.worker.source_manifest_sha256; f.seal();
  const { catalog, field } = await opened(f); assert.equal(field.status, "available", field.reason);
  const artifact = catalog.downloads.find((d) => d.path === "pde/worker.py");
  assert.equal(artifact.sha256, f.source.files.reader_fixture.sha256);
  assert.equal(artifact.sha256, f.inspection.result.provenance.adapter_details.source_sha256.reader_fixture);
  assert.equal(artifact.revision, f.inspection.result.proposal_revision);
});

test("copied source paths refuse double prefixes, unsafe paths and unprefixed/hash-mismatched Core substitutes", async (t) => {
  for (const nativePath of ["pde/sources/synthetic_worker.py", "PDE/sources/synthetic_worker.py", "../worker.py", "/worker.py", "C:\\worker.py"]) await t.test(nativePath, async () => {
    const f = fixture(); f.source.files.reader_fixture.copied_path = nativePath;
    // Even a manifested double-prefix alias with matching bytes cannot be admitted.
    if (/^pde\//i.test(nativePath)) f.buffers.set(`pde/${nativePath}`, f.buffers.get("pde/sources/synthetic_worker.py"));
    f.put("pde/source_manifest.json", f.source); f.worker.source_manifest_sha256 = hash(f.buffers.get("pde/source_manifest.json"));
    f.inspection.result.provenance.adapter_details.source_manifest_sha256 = f.worker.source_manifest_sha256; f.seal();
    const catalog = await reader.loadCatalog(f.inspection, f.fetchBytes, now); assert.equal(catalog.status, "error", catalog.reason); assert.deepEqual(catalog.entries, []);
  });
  await t.test("Core path is required to be experiment-relative", async () => {
    const f = fixture(), bytes = f.buffers.get("pde/sources/synthetic_worker.py");
    f.buffers.delete("pde/sources/synthetic_worker.py"); f.buffers.set("sources/synthetic_worker.py", bytes); f.seal();
    const catalog = await reader.loadCatalog(f.inspection, f.fetchBytes, now); assert.equal(catalog.status, "error"); assert.match(catalog.reason, /not uniquely manifested/);
  });
  await t.test("Core copied bytes must equal source and adapter hashes", async () => {
    const f = fixture(); f.put("pde/sources/synthetic_worker.py", "Different UNSOLVED copied source\n"); f.seal();
    const catalog = await reader.loadCatalog(f.inspection, f.fetchBytes, now); assert.equal(catalog.status, "error"); assert.match(catalog.reason, /not uniquely manifested/);
  });
});

test("partial/missing/legacy/oversized records are explicit download-only, never solver FAIL", async (t) => {
  for (const [label, mutate, status] of [
    ["missing worker", (f) => { f.inspection.result.artifacts = f.inspection.result.artifacts.filter((a) => a.path !== "pde/worker_result.json"); f.inspection.hashes.artifacts = copy(f.inspection.result.artifacts); }, "partial"],
    ["worker partial", (f) => { f.worker.status = "FAILED"; f.seal(); }, "partial"],
    ["legacy scalar", (f) => { f.inspection.proposal.physics.backend = "pde.fenicsx"; f.inspection.result.provenance.adapter = "pde.fenicsx"; }, "unavailable"],
    ["nonlinear", (f) => { f.inspection.proposal.physics.backend = "pde.fenicsx.nonlinear"; f.inspection.result.provenance.adapter = "pde.fenicsx.nonlinear"; }, "unavailable"],
    ["32MiB cap", (f) => { f.inspection.result.artifacts.find((a) => a.path === "pde/input.json").size_bytes = 32 * 1024 * 1024 + 1; f.inspection.hashes.artifacts = copy(f.inspection.result.artifacts); }, "unavailable"],
  ]) await t.test(label, async () => {
    const f = fixture(); mutate(f); const catalog = await reader.loadCatalog(f.inspection, f.fetchBytes, now);
    assert.equal(catalog.status, status, catalog.reason); assert.deepEqual(catalog.entries, []); assert.ok(catalog.downloads.length); assert.equal(catalog.metadata.assessment.decision, "NOT_RELEASED");
  });
});

test("fetch absence is partial; malformed/duplicate JSON keys and nonfinite field values are errors", async (t) => {
  const f = fixture(), { catalog } = await opened(f);
  cleared(await reader.loadField(catalog, catalog.entries[0], async () => { throw new Error("Unavailable"); }, now), "partial");
  for (const raw of ['{"schema_version":"1","schema_version":"1"}', "{ invalid JSON", JSON.stringify(f.fields[0]).replace('"values":[1,2,3,4]', '"values":[1,2,3,1e999]')]) await t.test(raw.slice(0, 45), async () => {
    const x = fixture(); x.put(`pde/${x.refs[0].files.dofs}`, raw); x.seal(); const { field } = await opened(x); cleared(field);
  });
});

test("field type/units/counts/connectivity/boundary/node errors clear output", async (t) => {
  const changes = {
    unit: (f) => { f.fields[0].field_unit = "MPa"; }, duplicateID: (f) => { f.fields[0].node_ids[1] = 0; },
    negativeID: (f) => { f.fields[0].node_ids[0] = -1; }, unsafeID: (f) => { f.fields[0].node_ids[3] = 2 ** 53; },
    count: (f) => { f.worker.mesh_studies[0].global_dofs++; }, shape: (f) => { f.fields[0].coordinates[0].push(0); },
    foreignNode: (f) => { f.fields[0].cell_node_ids[0][0] = 999; }, duplicateTriangle: (f) => { f.fields[0].cell_node_ids[1] = [...f.fields[0].cell_node_ids[0]]; },
    degenerate: (f) => { f.fields[0].coordinates[3] = [1, 0]; }, inventedCellID: (f) => { f.fields[0].cell_ids = [0, 1]; },
    missingBoundary: (f) => { delete f.fields[0].boundaries.ymax; }, facetIdentity: (f) => { f.fields[0].boundaries.xmax.facet_ids[0] = 0; },
    missingUnion: (f) => { f.fields[0].dirichlet_node_ids = [0]; }, boundaryNode: (f) => { f.fields[0].boundaries.xmax.dof_ids = [0, 5]; },
  };
  for (const [label, mutate] of Object.entries(changes)) await t.test(label, async () => {
    const f = fixture(); mutate(f); f.put(`pde/${f.refs[0].files.dofs}`, f.fields[0]); f.seal(); const { field } = await opened(f); cleared(field);
  });
});

test("directed vector labels/order and binding IDs are retained, never scalarized", async (t) => {
  for (const [label, mutate] of [
    ["component swap", (f) => { f.fields[0].components.reverse(); }], ["one component", (f) => { f.fields[0].values[0] = [1]; }],
    ["binding component", (f) => { f.bindings[0].components.reverse(); }], ["binding node order", (f) => { f.bindings[0].node_ids = [...f.bindings[0].node_ids].reverse(); }],
  ]) await t.test(label, async () => {
    const f = fixture("vector"); mutate(f); f.put(`pde/${f.refs[0].files.dofs}`, f.fields[0]); f.put(`pde/${f.refs[0].files.binding}`, f.bindings[0]); f.seal(); const { field } = await opened(f); cleared(field);
  });
});

test("coupled left/right adjacency, split sides, region sets and two RHS traces are exact", async (t) => {
  for (const [label, mutate] of [
    ["neighbour swap", (f) => { f.fields[0].interface.adjacent_cell_ids[0].reverse(); }], ["foreign region", (f) => { f.fields[0].cell_regions[0] = "elsewhere"; }],
    ["missing split", (f) => { delete f.fields[0].boundaries.ymin.right; }], ["missing RHS trace", (f) => { f.bindings[0].regions.right.rhs_values.pop(); }],
    ["coefficient", (f) => { f.bindings[0].regions.right.diffusion = [[2, 0], [0, 2]]; }],
  ]) await t.test(label, async () => {
    const f = fixture("coupled"); mutate(f); f.put(`pde/${f.refs[0].files.dofs}`, f.fields[0]); f.put(`pde/${f.refs[0].files.binding}`, f.bindings[0]); f.seal(); const { field } = await opened(f); cleared(field);
  });
});

test("imported original/dense/native index spaces and physical names cannot be conflated", async (t) => {
  for (const [label, mutate] of [
    ["dense as source", (m) => { m.original_node_ids = [1, 2, 3, 4]; }], ["geometry permutation", (m) => { m.geometry_input_indices[0] = 0; }],
    ["vertex composition", (m) => { m.vertex_geometry_indices.reverse(); }], ["cell index", (m) => { m.original_cell_index.reverse(); }],
    ["physical name", (m) => { m.physical_groups.elsewhere = m.physical_groups.xmin; delete m.physical_groups.xmin; }],
    ["ambient config", (m) => { m.gmsh_initialization.read_config_files = true; }], ["boundary elements", (m) => { m.boundary_source_elements.xmin = [3000]; }],
  ]) await t.test(label, async () => {
    const f = fixture("imported"), path = `pde/${f.refs[0].files.mapping}`, mapping = JSON.parse(f.buffers.get(path)); mutate(mapping); f.put(path, mapping); f.seal(); const { field } = await opened(f); cleared(field);
  });
});

test("transient time/status/value-chain/cross-step references are refused before preview", async (t) => {
  for (const [label, mutate] of [
    ["time", (f) => { f.worker.studies[0].steps[1].time = .75; }], ["Constant", (f) => { f.worker.studies[0].steps[1].native_time_value = 0; }],
    ["initial solved", (f) => { f.worker.studies[0].steps[0].solver_status = "COMPLETED"; }], ["previous hash", (f) => { f.worker.studies[0].steps[2].previous_values_sha256 = "0".repeat(64); }],
    ["same file reused", (f) => { f.worker.studies[0].steps[2].files.dofs = f.worker.studies[0].steps[0].files.dofs; }],
  ]) await t.test(label, async () => { const f = fixture("transient"); mutate(f); f.seal(); const catalog = await reader.loadCatalog(f.inspection, f.fetchBytes, now); assert.equal(catalog.status, "error", catalog.reason); });
});

test("transient verified raw lexemes, exact binding and fixed geometry are independently checked", async (t) => {
  for (const [label, mutate] of [
    ["JS reserialization", (f) => { f.put(`pde/${f.refs[2].files.dofs}`, f.fields[2]); }],
    ["wrong binding time", (f) => { f.bindings[2].time = .5; f.put(`pde/${f.refs[2].files.time_binding}`, f.bindings[2]); }],
    ["changed geometry", (f) => { const doc = JSON.parse(f.buffers.get(`pde/${f.refs[1].files.dofs}`)); doc.coordinates[0][0] = .1; f.put(`pde/${f.refs[1].files.dofs}`, JSON.stringify(doc).replace(/"values":\[[\s\S]*?\]/, '"values":[2.0,-0.0,2e-05,5.5]')); }],
    ["previous binding", (f) => { f.bindings[1].time = 99; f.put(`pde/${f.refs[1].files.time_binding}`, f.bindings[1]); }],
    ["malformed previous values", (f) => { const path = `pde/${f.refs[1].files.dofs}`, doc = JSON.parse(f.buffers.get(path)); doc.values = [[2.0], -0.0, 2e-05, 5.5]; f.put(path, doc); }],
  ]) await t.test(label, async () => { const f = fixture("transient"); mutate(f); f.seal(); const { field } = await opened(f, reader, 2); cleared(field); });
});

test("stale asynchronous catalog fetch, field fetch and SHA await clear trusted output", async (t) => {
  await t.test("catalog fetch", async () => {
    const f = fixture(); let active = true;
    const catalog = await reader.loadCatalog(f.inspection, async (path) => { const bytes = await f.fetchBytes(path); active = false; return bytes; }, () => active);
    assert.equal(catalog.status, "error"); assert.match(catalog.reason, /Selection changed/); assert.deepEqual(catalog.entries, []);
  });
  await t.test("field fetch", async () => {
    const f = fixture(), { catalog } = await opened(f); let active = true;
    cleared(await reader.loadField(catalog, catalog.entries[0], async (path) => { const bytes = await f.fetchBytes(path); active = false; return bytes; }, () => active));
  });
  await t.test("digest await", async () => {
    const f = fixture(); let active = true, armed = false;
    const api = browser({ subtle: { digest: async (...args) => { const result = await webcrypto.subtle.digest(...args); if (armed) active = false; return result; } } });
    const catalog = await api.loadCatalog(f.inspection, f.fetchBytes, () => active); assert.equal(catalog.status, "available", catalog.reason); armed = true;
    const result = await api.loadField(catalog, catalog.entries[0], f.fetchBytes, () => active); assert.equal(result.status, "error"); assert.equal(result.nodes.length, 0); assert.match(result.reason, /Selection changed/);
  });
});

test("fetched byte buffer mutation during hash cannot alter the verified consumed snapshot", async () => {
  const f = fixture(); let returned, armed = false;
  const api = browser({ subtle: { digest: async (algorithm, bytes) => { if (armed && returned) returned.fill(0); return webcrypto.subtle.digest(algorithm, bytes); } } });
  const catalog = await api.loadCatalog(f.inspection, f.fetchBytes, now); assert.equal(catalog.status, "available", catalog.reason); armed = true;
  const field = await api.loadField(catalog, catalog.entries[0], async (path) => { returned = await f.fetchBytes(path); return returned; }, now);
  assert.equal(field.status, "available", field.reason); assert.equal(field.nodes[0].values[0], 1);
});

test("node and catalog resource caps return download-only instead of a fabricated verdict", async () => {
  const f = fixture(), count = 200001; f.fields[0].node_ids = Array.from({ length: count }, (_, i) => i); f.worker.mesh_studies[0].global_dofs = count;
  f.put(`pde/${f.refs[0].files.dofs}`, f.fields[0]); f.seal(); const { field } = await opened(f); cleared(field, "unavailable"); assert.match(field.reason, /200000/);
  const triangles = fixture(); triangles.fields[0].cell_node_ids = Array(400001).fill([0, 5, 12]); triangles.worker.mesh_studies[0].global_cells = 400001;
  triangles.put(`pde/${triangles.refs[0].files.dofs}`, triangles.fields[0]); triangles.seal(); const bounded = (await opened(triangles)).field;
  cleared(bounded, "unavailable"); assert.match(bounded.reason, /400000/);
  const x = fixture(); x.settings.mesh.cell_counts = Array(2049).fill(1); x.worker.mesh_studies = Array(2049).fill(x.worker.mesh_studies[0]);
  x.put("pde/input.json", x.settings); x.worker.spec_sha256 = hash(x.buffers.get("pde/input.json")); x.inspection.proposal.execution = copy(x.settings);
  x.inspection.result.provenance.execution_settings = copy(x.settings); x.inspection.result.provenance.adapter_details.spec_sha256 = x.worker.spec_sha256; x.seal();
  const catalog = await reader.loadCatalog(x.inspection, x.fetchBytes, now); assert.equal(catalog.status, "unavailable", catalog.reason); assert.match(catalog.reason, /2048/);
});
