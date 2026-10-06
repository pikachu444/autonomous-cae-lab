"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { fromRecord } = require("../apps/lab/static/experiment-draft.js");

// Small TEST_ONLY verified-response shapes, not real solver outputs or qualification.
const hash = (character) => character.repeat(64);
const presets = {
  model: { operation: "model_analysis_run", backend: "structural.code_aster", settings: { example: "DO NOT COPY" } },
  pde: { operation: "pde_run", backend: "pde.fenicsx.transient", settings: { example: "DO NOT COPY" } },
  fixture: { operation: "analysis_run", backend: "fixture.calculix", parent_backends: ["fixture.cadquery"], settings: { load: { force_per_support_N: 999 } } }
};
function saved(namespace = "model_analysis", backend = "structural.code_aster") {
  const settings = {
    load: { vector: [-100, -0, 3.25], unit: "N", source: "TEST_ONLY assumed load" },
    material: { elastic_modulus_MPa: 210000, poisson_ratio: 0.3, qualification: "HYPOTHETICAL_UNQUALIFIED" },
    mesh: { mode: "selected", max_sizes_mm: [4] },
    samples: [{ time: 0, value: -1e-12 }, { time: 0.5, value: 7.125 }],
    reference: { path: "mesh/INPUT.msh", source: "TEST_ONLY exact reference", expression: "-2*x + sin(y)" }
  };
  const record = {
    integrity: "VERIFIED", record_id: "E-original",
    result: {
      schema_version: "1.0", experiment_id: "E-original", study: { id: "S-test", hypothesis_id: "H-test" },
      status: "COMPLETED_REVIEW_REQUIRED", decision: "NOT_RELEASED", solver_status: "SUCCESS", converged: true,
      cad_revision: null, model_revision: hash("f"), proposal_revision: hash("a"), input_parameters: {},
      metrics: { displacement: { value: -1e-12, unit: "mm", valid: false, reason: "TEST_ONLY invalid response" } },
      validations: [{ type: "physical", status: "UNKNOWN", blocking: true }], evidence: [], artifacts: [],
      extensions: { [namespace]: { model_revision: hash("f") } },
      provenance: { adapter: backend, proposal_sha256: hash("a"), solver: { backend }, execution_settings: structuredClone(settings) }
    },
    proposal: {
      schema_version: "1.0", id: "E-original", study_id: "S-test", hypothesis_id: "H-test",
      physics: { backend, analysis_type: "TEST_ONLY_declared_model" }, model: { geometry: null },
      model_revision: hash("f"), execution: settings, parameters: {}, objectives: [], constraints: [],
      extensions: { [namespace]: { model_revision: hash("f") } }
    },
    thread: { experiment: "E-original", run: "E-original", study: "S-test", hypothesis: "H-test", cad_revision: null, model_revision: hash("f") },
    study: { id: "S-test" },
    ledger: { experiment_id: "E-original", result_sha256: hash("b"), thread_sha256: hash("c") },
    hashes: { result_sha256: hash("b"), thread_sha256: hash("c"), proposal_sha256: hash("d"), ledger_sha256: hash("e"), study_sha256: hash("9") },
    parent_chain: []
  };
  return record;
}
function fixture() {
  const child = saved("model_analysis", "fixture.calculix"), parent = saved("model_analysis", "fixture.cadquery");
  for (const record of [child, parent]) {
    delete record.result.extensions; delete record.proposal.extensions;
    delete record.result.model_revision; delete record.proposal.model_revision; delete record.thread.model_revision;
    record.result.cad_revision = hash("8"); record.thread.cad_revision = hash("8");
  }
  parent.record_id = parent.result.experiment_id = parent.proposal.id = parent.thread.experiment = parent.ledger.experiment_id = "E-cad";
  parent.proposal.physics = { backend: null, analysis_type: "cad_preflight" };
  parent.proposal.model.geometry = { backend: "fixture.cadquery", source: "TEST_ONLY editable CAD" };
  parent.result.solver_status = "NOT_RUN"; parent.result.provenance.solver = null; parent.thread.run = null;
  // CAD's initial proposal revision can differ from its final canonical proposal hash.
  parent.result.proposal_revision = hash("7");
  child.result.parent_experiment_id = child.proposal.parent_experiment_id = child.result.provenance.parent_experiment_id = child.thread.parent_experiment = "E-cad";
  child.proposal.model.geometry = { source_experiment_id: "E-cad", cad_revision: hash("8") };
  child.result.provenance.parent_result_sha256 = child.thread.parent_result_sha256 = parent.hashes.result_sha256;
  child.proposal.parameters = { support_width_mm: 32 }; child.result.input_parameters = { support_width_mm: 32 };
  child.parent_chain = [parent];
  return child;
}
function freeze(value) {
  if (value && typeof value === "object") { Object.values(value).forEach(freeze); Object.freeze(value); }
  return value;
}
function refused(record, code, context = presets) {
  const result = fromRecord(record, context);
  assert.equal(result.available, false); assert.equal(result.code, code); assert.match(result.reason, /\S/);
  assert.equal(Object.hasOwn(result, "arguments"), false);
  return result;
}

test("saved conditions retain raw loads, units, signs, material, mesh, samples and references without aliases", () => {
  const record = saved(), original = structuredClone(record);
  freeze(record); freeze(presets);
  const draft = fromRecord(record, presets);
  assert.equal(draft.available, true); assert.equal(draft.operation, "model_analysis_run"); assert.equal(draft.presetId, "model");
  assert.deepEqual(draft.arguments, { backend: "structural.code_aster", settings: record.proposal.execution, study_id: "S-test", hypothesis_id: "H-test" });
  assert.equal(Object.is(draft.arguments.settings.load.vector[1], -0), true);
  draft.arguments.settings.load.vector[0] = 200;
  draft.arguments.settings.material.qualification = "edited";
  draft.arguments.settings.mesh.max_sizes_mm.push(2);
  draft.arguments.settings.samples[0].value = 99;
  draft.arguments.settings.reference.path = "edited";
  assert.deepEqual(record, original);
  assert.equal(draft.source.experimentId, "E-original"); assert.equal(Object.hasOwn(draft.arguments, "experiment_id"), false);
  assert.equal(Object.hasOwn(draft.arguments, "parent_experiment_id"), false);
});
test("PDE uses its explicit operation and preserves a free-form hypothesis string without inventing a CAD parent", () => {
  const record = saved("pde", "pde.fenicsx.transient"), hypothesis = "원래 가설: 하중 부호와 이력 비교";
  record.proposal.hypothesis_id = record.result.study.hypothesis_id = record.thread.hypothesis = hypothesis;
  record.proposal.model.geometry = { type: "rectangle", size: [1, 2], unit: "1" };
  const draft = fromRecord(record, presets);
  assert.equal(draft.available, true); assert.equal(draft.operation, "pde_run");
  assert.equal(draft.arguments.hypothesis_id, hypothesis); assert.deepEqual(draft.arguments.settings, record.proposal.execution);
  assert.equal(draft.source.modelRevision, hash("f")); assert.equal(draft.source.cadRevision, null);
  assert.equal(Object.hasOwn(draft.arguments, "parent_experiment_id"), false);
});
test("fixture drafts keep the verified original CAD parent and never submit the source child ID", () => {
  const record = freeze(fixture()), draft = fromRecord(record, presets);
  assert.equal(draft.available, true); assert.equal(draft.operation, "analysis_run");
  assert.deepEqual(draft.arguments, { backend: "fixture.calculix", settings: record.proposal.execution, parent_experiment_id: "E-cad" });
  assert.equal(draft.source.cadRevision, hash("8")); assert.equal(draft.source.parentExperimentId, "E-cad");
  assert.equal(Object.hasOwn(draft.arguments, "experiment_id"), false);
  assert.equal(Object.hasOwn(draft.arguments, "study_id"), false); assert.equal(Object.hasOwn(draft.arguments, "hypothesis_id"), false);
});
test("complete rejected and failed records provide editable conditions without changing invalid metrics or verdicts", () => {
  for (const status of ["REJECTED", "FAILED_EXECUTION"]) {
    const record = saved(); record.result.status = status; record.result.solver_status = status === "REJECTED" ? "NOT_RUN" : "FAILED_EXECUTION";
    const original = structuredClone(record), draft = fromRecord(freeze(record), presets);
    assert.equal(draft.available, true); assert.deepEqual(draft.arguments.settings, record.proposal.execution);
    assert.deepEqual(record, original); assert.equal(record.result.decision, "NOT_RELEASED");
    assert.equal(record.result.metrics.displacement.valid, false); assert.equal(record.result.validations[0].status, "UNKNOWN");
    assert.equal(Object.hasOwn(draft, "eligible"), false); assert.equal(Object.hasOwn(draft, "decision"), false);
  }
});
test("only VERIFIED complete saved responses can supply drafts", () => {
  for (const integrity of ["NOT_CHECKED", "FAILED", undefined]) {
    const record = saved(); if (integrity === undefined) delete record.integrity; else record.integrity = integrity;
    refused(record, "INTEGRITY_REQUIRED");
  }
  for (const key of ["proposal", "thread", "study", "ledger", "hashes"]) {
    const record = saved(); delete record[key]; refused(record, "INCOMPLETE_RECORD");
  }
  const pending = saved(); pending.result.status = "RUNNING"; refused(pending, "INCOMPLETE_RECORD");
  const absent = saved(); delete absent.proposal.execution; refused(absent, "INCOMPLETE_RECORD");
});
test("experiment, record, study, hypothesis and ledger identities must agree exactly", () => {
  for (const mutate of [
    (r) => { r.record_id = "E-other"; }, (r) => { r.experiment_id = "E-other"; },
    (r) => { r.proposal.id = "E-other"; }, (r) => { r.thread.experiment = "E-other"; },
    (r) => { r.ledger.experiment_id = "E-other"; }, (r) => { r.thread.run = "E-other"; },
    (r) => { r.proposal.study_id = "S-other"; }, (r) => { r.study.id = "S-other"; },
    (r) => { r.thread.study = "S-other"; }, (r) => { r.result.study.hypothesis_id = "H-other"; },
    (r) => { r.thread.hypothesis = "H-other"; }
  ]) { const record = saved(); mutate(record); refused(record, "IDENTITY_MISMATCH"); }
  for (const invalid of ["E-original\n", "../E-original", "E-original/child", "", "1-invalid", "E".repeat(81)]) {
    const record = saved(); record.result.experiment_id = invalid; refused(record, "IDENTITY_MISMATCH");
  }
});
test("backend matching is exact and cannot fall back to a similar adapter or operation", () => {
  for (const backend of ["structural.code_aster ", "structural.code_aster.plasticity", null]) {
    const record = saved(); record.proposal.physics.backend = backend; refused(record, "BACKEND_MISMATCH");
  }
  const wrongSolver = saved(); wrongSolver.result.provenance.solver.backend = "fixture.calculix"; refused(wrongSolver, "BACKEND_MISMATCH");
  refused(saved(), "PRESET_UNAVAILABLE", { wrong: { backend: "structural.code_aster", operation: "pde_run" } });
  refused(saved(), "PRESET_UNAVAILABLE", { missing: { backend: "structural.code_aster" } });
  refused(saved(), "PRESET_UNAVAILABLE", {});
});
test("duplicate backend presets supply only deterministic screen context and never read example settings", () => {
  let reads = 0;
  const first = { backend: "structural.code_aster", operation: "model_analysis_run" };
  Object.defineProperty(first, "settings", { enumerable: true, get() { reads += 1; throw new Error("preset settings read"); } });
  const record = saved(), draft = fromRecord(record, { first, second: presets.model });
  assert.equal(draft.available, true); assert.equal(draft.presetId, "first"); assert.equal(reads, 0);
  assert.deepEqual(draft.arguments.settings, record.proposal.execution);
});
test("stored execution and proposal/ledger hash links cannot disagree", () => {
  const settings = saved(); settings.result.provenance.execution_settings.load.vector[0] = 100; refused(settings, "SETTINGS_MISMATCH");
  const revision = saved(); revision.result.proposal_revision = hash("e"); refused(revision, "SETTINGS_MISMATCH");
  const run = saved(); run.thread.run = null; refused(run, "SETTINGS_MISMATCH");
  const ledger = saved(); ledger.ledger.result_sha256 = hash("9"); refused(ledger, "INCOMPLETE_RECORD");
  const missing = saved(); delete missing.hashes.proposal_sha256; refused(missing, "INCOMPLETE_RECORD");
  const trailing = saved(); trailing.hashes.study_sha256 += "\n"; refused(trailing, "INCOMPLETE_RECORD");
});
test("fixture parent IDs, verification, native declaration and recorded raw result hash are joined", () => {
  for (const mutate of [
    (r) => { r.result.parent_experiment_id = "E-original"; },
    (r) => { r.proposal.parent_experiment_id = "E-other"; },
    (r) => { r.result.provenance.parent_experiment_id = "E-other"; },
    (r) => { r.thread.parent_experiment = "E-other"; },
    (r) => { r.proposal.model.geometry.source_experiment_id = "E-other"; },
    (r) => { r.parent_chain = []; }, (r) => { r.parent_chain.push(structuredClone(r.parent_chain[0])); },
    (r) => { r.result.provenance.parent_result_sha256 = hash("9"); },
    (r) => { r.thread.parent_result_sha256 = hash("9"); },
    (r) => { r.parent_chain[0].proposal.physics.analysis_type = "linear_static"; },
    (r) => { r.parent_chain[0].result.parent_experiment_id = "E-original"; },
    (r) => { r.parent_chain[0].proposal.model.geometry.backend = "fixture.freecad"; }
  ]) { const record = fixture(); mutate(record); refused(record, "PARENT_MISMATCH"); }
  const unverified = fixture(); unverified.parent_chain[0].integrity = "NOT_CHECKED"; refused(unverified, "INTEGRITY_REQUIRED");
  const wrongStudy = fixture(); const parent = wrongStudy.parent_chain[0];
  parent.result.study.id = parent.proposal.study_id = parent.thread.study = parent.study.id = "S-other";
  refused(wrongStudy, "PARENT_MISMATCH");
});
test("fixture and declared model revisions must agree across the saved documents", () => {
  for (const mutate of [
    (r) => { r.proposal.model.geometry.cad_revision = hash("9"); },
    (r) => { r.thread.cad_revision = hash("9"); },
    (r) => { r.parent_chain[0].result.cad_revision = hash("9"); },
    (r) => { r.parent_chain[0].thread.cad_revision = hash("9"); }
  ]) { const record = fixture(); mutate(record); refused(record, "REVISION_MISMATCH"); }
  for (const mutate of [
    (r) => { r.proposal.model_revision = hash("9"); }, (r) => { r.thread.model_revision = hash("9"); },
    (r) => { r.proposal.extensions.model_analysis.model_revision = hash("9"); },
    (r) => { r.result.extensions.model_analysis.model_revision = hash("9"); }
  ]) { const record = saved(); mutate(record); refused(record, "REVISION_MISMATCH"); }
});
test("model/PDE routes refuse fake CAD parents and inconsistent or absent route declarations", () => {
  for (const mutate of [
    (r) => { r.result.parent_experiment_id = "E-cad"; }, (r) => { r.proposal.parent_experiment_id = "E-cad"; },
    (r) => { r.result.cad_revision = hash("8"); }, (r) => { r.thread.cad_revision = hash("8"); },
    (r) => { r.proposal.model.geometry = { source_experiment_id: "E-cad" }; },
    (r) => { r.parent_chain = [fixture().parent_chain[0]]; }
  ]) { const record = saved(); mutate(record); refused(record, "PARENT_MISMATCH"); }
  const absent = saved(); delete absent.proposal.extensions; delete absent.result.extensions; refused(absent, "UNSUPPORTED_OPERATION");
  const mixed = saved(); mixed.result.extensions.pde = { model_revision: hash("f") }; refused(mixed, "UNSUPPORTED_OPERATION");
  const half = saved(); delete half.result.extensions; refused(half, "INCOMPLETE_RECORD");
});
test("CAD registration and model campaign/binding/registered assignments are explicit out-of-scope refusals", () => {
  refused(fixture().parent_chain[0], "UNSUPPORTED_OPERATION");
  for (const mutate of [
    (r) => { r.result.campaign_id = "C-test"; }, (r) => { r.proposal.campaign_id = "C-test"; },
    (r) => { r.thread.campaign = "C-test"; },
    (r) => { r.proposal.extensions.model_analysis.parameter_binding = { input_ids: {} }; },
    (r) => { r.result.extensions.model_analysis.parameter_binding = { input_ids: {} }; },
    (r) => { r.proposal.parameters = { p1: 2 }; }, (r) => { r.result.input_parameters = { p1: 2 }; },
    (r) => { r.proposal.objectives = [{ metric: "energy" }]; }
  ]) { const record = saved(); mutate(record); const result = refused(record, "UNSUPPORTED_BINDING"); assert.match(result.reason, /範囲|범위/); }
});
test("finite JSON validation blocks unsafe keys, cycles, sparse arrays and executable attributes without invoking them", () => {
  for (const value of [NaN, Infinity, -Infinity, undefined, () => 1, new Date(), 1n]) {
    const record = saved(); record.proposal.execution.invalid = value; refused(record, "INVALID_JSON");
  }
  for (const key of ["__proto__", "prototype", "constructor"]) {
    const record = saved(); Object.defineProperty(record.proposal.execution, key, { value: { polluted: true }, enumerable: true });
    refused(record, "INVALID_JSON"); assert.equal({}.polluted, undefined);
  }
  const cyclic = saved(); cyclic.proposal.execution.self = cyclic.proposal.execution; refused(cyclic, "INVALID_JSON");
  const sparse = saved(); sparse.proposal.execution.samples = new Array(2); refused(sparse, "INVALID_JSON");
  const extra = saved(); extra.proposal.execution.samples.extra = 1; refused(extra, "INVALID_JSON");
  const hidden = saved(); Object.defineProperty(hidden.proposal.execution, "hidden", { value: 1 }); refused(hidden, "INVALID_JSON");
  let reads = 0; const getter = saved(); Object.defineProperty(getter.proposal.execution, "getter", { enumerable: true, get() { reads += 1; return 1; } });
  refused(getter, "INVALID_JSON"); assert.equal(reads, 0);
});
test("object key order is irrelevant while exact signed numeric values remain authoritative", () => {
  const reordered = saved(); reordered.result.provenance.execution_settings = Object.fromEntries(Object.entries(reordered.proposal.execution).reverse());
  assert.equal(fromRecord(reordered, presets).available, true);
  const changedSign = saved(); changedSign.result.provenance.execution_settings.load.vector[1] = 0;
  refused(changedSign, "SETTINGS_MISMATCH");
});
test("browser and CommonJS exports expose the same pure helper without requiring a runtime or DOM", () => {
  const source = fs.readFileSync(path.join(__dirname, "../apps/lab/static/experiment-draft.js"), "utf8");
  const context = vm.createContext({ window: {}, recordJson: JSON.stringify(saved()), presetsJson: JSON.stringify(presets) });
  vm.runInContext(source, context);
  assert.equal(typeof context.window.experimentDraft.fromRecord, "function");
  const draft = vm.runInContext("window.experimentDraft.fromRecord(JSON.parse(recordJson), JSON.parse(presetsJson))", context);
  assert.equal(draft.available, true); assert.equal(draft.operation, "model_analysis_run");
  assert.deepEqual(JSON.parse(JSON.stringify(draft)), JSON.parse(JSON.stringify(fromRecord(JSON.parse(context.recordJson), presets))));
});

test("cancelled declared inputs can prepare a new experiment without copying partial responses", () => {
  const record = saved();
  record.result.status = "CANCELLED";
  record.result.solver_status = "CANCELLED";
  record.result.converged = null;
  record.result.metrics = {};
  const before = JSON.stringify(record);
  const draft = fromRecord(record, presets);
  assert.equal(draft.available, true);
  assert.deepEqual(draft.arguments.settings, record.proposal.execution);
  assert.equal(Object.hasOwn(draft.arguments, "metrics"), false);
  assert.equal(JSON.stringify(record), before);
});
