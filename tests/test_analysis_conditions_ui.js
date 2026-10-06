"use strict";

// Controlled DOM/HTTP source proof only; no browser, CAD, solver or provider.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const vm = require("node:vm");
const analysisControls = require("../apps/lab/static/analysis-conditions-controls.js");
const cadControls = require("../apps/lab/static/cad-controls.js");
const presentation = require("../apps/lab/static/result-presentation.js");
const researchControls = require("../apps/lab/static/research-controls.js");
const source = readFileSync(require.resolve("../apps/lab/static/app.js"), "utf8");
const html = readFileSync(require.resolve("../apps/lab/static/index.html"), "utf8");
const boundary = source.indexOf('$("jobCancelBtn").addEventListener("click", async () => {');
assert(boundary > 0, "Use the existing controlled seam before startup/listeners");
const clone = value => JSON.parse(JSON.stringify(value));
const reply = (value, ok = true) => ({ ok, status: ok ? 200 : 503, json: async () => value });
const parent = (id = "E-cad", backend = "fixture.cadquery") => ({ id, backend, study_id: "S-study", cad_revision: "a".repeat(64), status: "COMPLETED_REVIEW_REQUIRED", solver_status: "NOT_RUN" });
function catalog(backend = "fixture.cadquery") {
  const selections = [{ id: "B-final", label: "최종 솔리드 <TEST_ONLY>", kind: "whole_final_solid", roles: ["material", "boundary", "load"] }];
  if (backend === "fixture.cadquery") selections.push({ id: "S-base", label: "선언 바닥", kind: "adapter_region", roles: ["boundary"] },
    { id: "S-saddle", label: "중앙 24 mm 안장", kind: "adapter_region", roles: ["load"] });
  return { source: { experiment_id: "E-cad", study_id: "S-study", cad_revision: "a".repeat(64), backend,
    result_sha256: "b".repeat(64), proposal_sha256: "c".repeat(64), thread_sha256: "d".repeat(64) }, catalog_revision: "e".repeat(64),
    catalog: { schema_version: "1.0", selections,
      coordinate_systems: [{ id: "global", label: "전역", type: "cartesian", unit: "mm", basis: [[1, 0, 0], [0, 1, 0], [0, 0, 1]], origin: [0, 0, 0] }],
      limitations: ["일반 면·physical group·접촉 쌍은 미완료."] },
    backends: [{ backend: "fixture.calculix", label: "CalculiX", scope: "선언 입력 경로 · 설치·공학 자격은 미확인" }] };
}
function record(data, request, status = "SUPPORTED_DECLARED_INPUTS") {
  return { schema_version: "1.0", id: request.conditions_id, created_utc: "2026-10-06T00:00:00Z", source: clone(data.source), request: clone(request),
    catalog: clone(data.catalog), catalog_revision: data.catalog_revision, conditions_revision: "f".repeat(64),
    support: { status, reasons: status === "SUPPORTED_DECLARED_INPUTS" ? [] : ["선택한 CAD·하중 분포는 adapter에서 지원되지 않습니다."], native_runtime: "NOT_CHECKED" },
    adapter_binding: status === "SUPPORTED_DECLARED_INPUTS" ? { backend: request.backend, version: "TEST_ONLY", settings: { solver_syntax: "opaque server binding" } } : null,
    engineering: "UNKNOWN", decision: "NOT_RELEASED", provenance: { test_only: true } };
}
function child(id = "E-child") {
  return { experiment_id: id, study: { id: "S-study" }, cad_revision: "a".repeat(64), provenance: { adapter: "fixture.calculix" },
    solver_status: "COMPLETED", status: "COMPLETED_REVIEW_REQUIRED", engineering: "UNKNOWN", decision: "NOT_RELEASED",
    metrics: { signed_reactions: { value: [0, 0, 150], unit: "N", valid: true }, test_displacements: { value: [0.001, -0.002, -0.03], unit: "mm", valid: true } } };
}
class Node {
  constructor(tag = "div") {
    this.tagName = tag.toUpperCase(); this.children = []; this.dataset = {}; this.attributes = {}; this.style = {}; this.value = "";
    this.disabled = false; this.hidden = false; this.checked = false; this.className = ""; this._text = ""; this.isConnected = true;
    this.classList = { contains: value => this.className.split(/\s+/).includes(value),
      add: (...values) => { this.className = [...new Set([...this.className.split(/\s+/).filter(Boolean), ...values])].join(" "); },
      remove: (...values) => { this.className = this.className.split(/\s+/).filter(value => !values.includes(value)).join(" "); },
      toggle: (value, enabled) => { const on = enabled ?? !this.classList.contains(value); this.classList.remove(value); if (on) this.classList.add(value); return on; } };
  }
  get options() { return this.children.filter(node => node.tagName === "OPTION"); }
  set textContent(value) { this._text = String(value ?? ""); this.children.forEach(node => { node.parentNode = null; }); this.children = []; }
  get textContent() { return this._text + this.children.map(node => node.textContent).join(""); }
  set innerHTML(_value) { throw new Error("Untrusted catalog/record text must use textContent"); }
  append(...items) { for (const item of items) { const node = item instanceof Node ? item : new Node("#text"); if (!(item instanceof Node)) node.textContent = item; node.remove(); node.parentNode = this; this.children.push(node); } }
  replaceChildren(...items) { this.textContent = ""; this.append(...items); }
  remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter(node => node !== this); this.parentNode = null; }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  removeAttribute(key) { delete this.attributes[key]; }
  addEventListener(name, fn) { (this.listeners ??= new Map()).set(name, fn); }
  querySelector(selector) { return walk(this).slice(1).find(node => selector.startsWith(".") ? node.classList.contains(selector.slice(1)) : node.tagName === selector.toUpperCase()) ?? null; }
}
function walk(node) { return [node, ...node.children.flatMap(walk)]; }
function harness({ backend = "fixture.cadquery", writable = true, moduleAvailable = true, workspace = false, fetchReply } = {}) {
  const nodes = new Map(), operations = [], writes = [], paths = [], timers = [];
  const $ = id => { if (!nodes.has(id)) nodes.set(id, new Node(/Selection$|Backend$|Unit$|Parent$|System$|Law$|Category$|Mode$/.test(id) ? "select" : "div")); return nodes.get(id); };
  for (const match of html.matchAll(/<button\b[^>]*>/g)) {
    const operation = /\bdata-operation="([^"]+)"/.exec(match[0])?.[1]; if (!operation) continue;
    const id = /\bid="([^"]+)"/.exec(match[0])?.[1], node = id ? $(id) : new Node("button"); node.dataset.operation = operation; operations.push(node);
  }
  for (const match of html.matchAll(/<fieldset\b[^>]*data-write[^>]*>/g)) { const id = /\bid="([^"]+)"/.exec(match[0])?.[1]; writes.push(id ? $(id) : new Node("fieldset")); }
  const document = { getElementById: $, createElement: tag => new Node(tag),
    querySelectorAll: selector => selector === "[data-operation]" ? operations : selector === "fieldset[data-write]" ? writes :
      selector === "[data-analysis-conditions-open]" ? walk($("analysisConditionsList")).filter(node => Object.hasOwn(node.dataset, "analysisConditionsOpen")) :
      ["[data-conditions-selection]", "[data-boundary-remove]", "[data-boundary-component]"].includes(selector) ?
        [...nodes.values()].filter(node => Object.hasOwn(node.dataset, selector.slice(6, -1).replace(/-([a-z])/g, (_, c) => c.toUpperCase())) ||
          walk(node).some(child => Object.hasOwn(child.dataset, selector.slice(6, -1).replace(/-([a-z])/g, (_, c) => c.toUpperCase()))))
          .flatMap(walk).filter((node, index, all) => all.indexOf(node) === index && Object.hasOwn(node.dataset, selector.slice(6, -1).replace(/-([a-z])/g, (_, c) => c.toUpperCase()))) : [],
    querySelector: selector => operations.find(node => selector === `[data-operation="${node.dataset.operation}"]`) ?? null };
  $("cadBackend").value = backend; $("cadModel").value = backend === "fixture.cadquery" ? "roller_support" : "native_TEST_ONLY"; $("nativeModelId").value = "";
  $("simulationPreset").value = "linear"; $("fixtureConditionFields").hidden = true; $("importedMeshFields").hidden = true;
  $("campaignTarget").value = "cad"; $("conditionsParent").value = "E-cad";
  const defaults = { conditionsId: "C-conditions", conditionsBackend: "fixture.calculix", conditionsMaterialSelection: "B-final", conditionsMaterialLaw: "isotropic_linear_elastic",
    conditionsYoungModulus: "210000", conditionsPoissonRatio: "0.3", conditionsMaterialCategory: "ASSUMED", conditionsMaterialSource: "ASSUMED: 未測定 <TEST_ONLY>",
    conditionsCoordinateSystem: "global", conditionsLengthUnit: "mm", conditionsForceUnit: "N", conditionsStressUnit: "MPa",
    conditionsBoundarySelection: backend === "fixture.cadquery" ? "S-base" : "B-final", conditionsUx: "0", conditionsUy: "0", conditionsUz: "0", conditionsBoundarySource: "ASSUMED: 고정 이상화",
    conditionsLoadSelection: backend === "fixture.cadquery" ? "S-saddle" : "B-final", conditionsFx: "0", conditionsFy: "0", conditionsFz: "-150", conditionsLoadSource: "ASSUMED: 합력 <TEST_ONLY>",
    conditionsContactMode: "none", conditionsContactSource: "ASSUMED: 접촉 없음", conditionsMeshSize: "4", conditionsExperimentId: "E-child" };
  Object.entries(defaults).forEach(([id, value]) => { $(id).value = value; });
  if (workspace) {
    $("designModelViewport").dataset.engineeringViewport = "design";
    $("conditionsAdditionalBoundaries").dataset.boundaryRows = "native";
    for (const axis of ["x", "y", "z"]) { $(`conditionsU${axis}Enabled`).type = "checkbox"; $(`conditionsU${axis}Enabled`).checked = true; }
    $("resultsModelViewport").append($("experimentDetail"));
  }
  const sandbox = { document, Node, window: { ...(moduleAvailable ? { analysisConditionsControls: analysisControls } : {}), cadControls, resultPresentation: presentation, researchControls },
    location: { hash: "simulation" }, Intl, TextEncoder, URL, URLSearchParams, console,
    fetch: async (path, options) => { paths.push({ path, options }); assert(fetchReply, `No uncontrolled HTTP: ${path}`); return fetchReply(path, options); },
    setTimeout: (fn, delay) => { timers.push({ fn, delay }); return timers.length; }, clearTimeout: () => {} };
  vm.createContext(sandbox);
  vm.runInContext(source.slice(0, boundary) + "\nglobalThis.ui = {state, updateControls, renderAnalysisConditionsParents, currentAnalysisConditionsCatalog, analysisConditionsFields, loadAnalysisConditionsCatalog, refreshAnalysisConditionsList, openAnalysisConditionsRecord, saveAnalysisConditions, runAnalysisConditions, changeAnalysisConditionsDraft, invalidateAnalysisConditions, renderAnalysisConditionsRecord, loadOverview, runJob, pollJob, inspectExperiment, initializeEngineeringWorkspace, showArea, mountExperimentInspector, openEngineeringRecord, renderAnalysisConditionsCatalog, renderAdditionalBoundaries, addAnalysisBoundary, renderJob, renderFixtureFields};", sandbox);
  const ui = sandbox.ui;
  const overview = { active_store: "local", stores: [{ id: "local", writable }], token: "TEST_ONLY", capabilities: [], jobs: [],
    studies: [{ id: "S-study" }, { id: "S-other" }], experiments: [parent("E-cad", backend), parent("E-import", "fixture.freecad"), parent("E-assembly", "fixture.assembly")] };
  ui.state.overview = overview; ui.state.studyId = "S-study";
  ui.state.presets = { linear: { backend: "fixture.calculix", operation: "analysis_run", parent_backends: ["fixture.cadquery"] } };
  // Unrelated panes have separate source suites. Keep the actual overview,
  // single-job polling and Results inspector request/context flow here.
  sandbox.renderOverview = () => { ui.renderAnalysisConditionsParents(); ui.updateControls(); };
  sandbox.renderResearchAnswers = () => {};
  sandbox.loadStudy = async () => {};
  sandbox.loadNativeImports = async () => {};
  sandbox.renderStudy = () => {};
  sandbox.renderJob = () => { ui.updateControls(); };
  sandbox.renderExperimentDetail = data => { $("experimentDetail").textContent = `ACTUAL_CHILD_TEST_ONLY ${JSON.stringify(data.result)}`; };
  sandbox.renderObservation = () => {};
  sandbox.loadResponseHistories = async () => {};
  return { ui, $, paths, timers, sandbox, overview, defaults };
}
function ready(h, data = catalog()) {
  h.ui.state.analysisConditions.catalog = data;
  h.ui.state.analysisConditions.context = JSON.stringify(["local", "S-study", "E-cad", h.$("cadBackend").value, h.$("cadModel").value, ""]);
  return data;
}
function savedReady(h, data = ready(h), status) {
  const request = analysisControls.buildSave(data, clone(h.ui.analysisConditionsFields()));
  const value = record(data, request, status);
  h.ui.state.analysisConditions.record = value;
  h.ui.state.analysisConditions.recordDraft = JSON.stringify(h.ui.analysisConditionsFields());
  return value;
}

test("distinct Korean same-CAD form precedes retained example controls and marks every default source ASSUMED", () => {
  assert(html.indexOf('id="analysisConditionsForm"') < html.indexOf('id="simulationForm"'));
  assert(html.indexOf('/static/analysis-conditions-controls.js') < html.indexOf('/static/app.js'));
  for (const id of ["conditionsMaterialSource", "conditionsBoundarySource", "conditionsLoadSource", "conditionsContactSource"]) assert.match(html, new RegExp(`id="${id}"[^>]*>ASSUMED:`));
  assert.match(html, /MEASURED_REPORTED · 사용자가 보고한 측정값, 자격 미확인/);
  assert.match(html, /화면 삼각형 번호를 네이티브 면 ID로 사용하지 않습니다/);
  assert(html.indexOf('id="experimentDetail"') < html.indexOf('id="observationPanel"'), "Actual model/results precede the observation editor");
  for (const id of ["simulationSettings", "fixtureConditionFields", "importedMeshFields", "historyPanel", "researchQuestionForm"]) assert(html.includes(`id="${id}"`));
});

test("overview/UI refresh lists all completed same-study CADs without any automatic catalog or record GET", async () => {
  const h = harness({ fetchReply: path => { assert.equal(path, "/api/overview"); return reply(h.overview); } });
  ready(h); h.$("conditionsFz").value = "-217.25"; h.$("conditionsLoadSource").value = "Draft source sentinel";
  await h.ui.loadOverview();
  assert.deepEqual(h.paths.map(item => item.path), ["/api/overview"]);
  assert.deepEqual(h.$("conditionsParent").options.map(item => item.value), ["", "E-cad", "E-import", "E-assembly"]);
  assert.equal(h.$("conditionsFz").value, "-217.25"); assert.equal(h.$("conditionsLoadSource").value, "Draft source sentinel");
  assert.equal(h.ui.currentAnalysisConditionsCatalog(), true);
});

test("explicit catalog action checks exact source and lists revision-owned targets with runtime and scope limits", async () => {
  const data = catalog();
  const h = harness({ fetchReply: path => {
    if (path === "/api/analysis-conditions/catalog?experiment_id=E-cad") return reply(data);
    assert.equal(path, "/api/analysis-conditions?experiment_id=E-cad"); return reply({ records: [] });
  } });
  await h.ui.loadAnalysisConditionsCatalog();
  assert.equal(h.ui.currentAnalysisConditionsCatalog(), true); assert.equal(h.ui.state.analysisConditions.loading, false);
  assert.equal(h.paths.length, 2); assert.match(h.$("analysisConditionsCatalog").textContent, /NOT_CHECKED/);
  assert.match(h.$("analysisConditionsCatalog").textContent, /<TEST_ONLY>/); assert.match(h.$("analysisConditionsCatalog").textContent, /일반 면/);
  assert.deepEqual(h.$("conditionsBoundarySelection").options.map(item => item.value), ["", "B-final", "S-base"]);
  assert.deepEqual(h.$("conditionsLoadSelection").options.map(item => item.value), ["", "B-final", "S-saddle"]);
  assert.equal(h.$("conditionsLoadSelection").value, "S-saddle", "A same-catalog explicit draft choice is retained");
});

test("save keeps signed vectors, typed sources and same CAD; new analysis sends only conditions_id and opens actual child Results", async () => {
  const data = catalog(); let retained, calls = 0;
  const h = harness({ fetchReply: (path, options) => {
    if (path === "/api/overview") return reply(h.overview);
    if (path === "/api/experiments/E-child") return reply({ integrity: "VERIFIED", result: child() });
    assert.equal(path, "/api/jobs"); assert.equal(options.method, "POST"); assert.equal(options.headers["X-CAE-Token"], "TEST_ONLY");
    const body = JSON.parse(options.body); calls++;
    if (body.operation === "analysis_conditions_save") {
      assert.equal(body.arguments.experiment_id, "E-cad"); assert.equal(body.arguments.cad_revision, "a".repeat(64));
      assert.deepEqual(body.arguments.declaration.loads[0].components, { FX: 0, FY: 0, FZ: -150 });
      assert.deepEqual(body.arguments.declaration.boundary_conditions[0].components, { UX: 0, UY: 0, UZ: 0 });
      assert.equal(body.arguments.declaration.materials[0].source.category, "ASSUMED");
      assert.equal(Object.hasOwn(body.arguments, "settings"), false);
      retained = record(data, body.arguments); return reply({ id: "J-save", operation: body.operation, status: "COMPLETED", result: retained });
    }
    assert.equal(body.operation, "analysis_run");
    assert.deepEqual(body.arguments, { parent_experiment_id: "E-cad", experiment_id: "E-child", backend: "fixture.calculix", conditions_id: "C-conditions" });
    return reply({ id: "J-run", operation: body.operation, status: "COMPLETED", result: child() });
  } });
  ready(h, data); const before = JSON.stringify(h.ui.analysisConditionsFields());
  await h.ui.saveAnalysisConditions();
  assert.equal(h.ui.state.analysisConditions.record.id, "C-conditions"); assert.equal(h.ui.state.analysisConditions.recordDraft, before);
  assert.match(h.$("analysisConditionsRecord").textContent, /FX 0 \/ FY 0 \/ FZ -150 N/);
  assert.match(h.$("analysisConditionsRecord").textContent, /UNKNOWN/); assert.match(h.$("analysisConditionsRecord").textContent, /NOT_CHECKED/);
  assert.equal(h.$("analysisConditionsRunBtn").disabled, false); assert.equal(h.$("analysisConditionsSaveBtn").disabled, true, "append-only ID cannot be reused");
  await h.ui.runAnalysisConditions();
  assert.equal(calls, 2); assert.equal(h.ui.state.selectedExperiment.result.experiment_id, "E-child");
  assert.equal(h.sandbox.location.hash, "results"); assert.match(h.$("experimentDetail").textContent, /signed_reactions/);
  assert.match(h.$("experimentDetail").textContent, /test_displacements/); assert.equal(retained.request.declaration.loads[0].components.FZ, -150);
});

test("edits after saving require a new condition record; original record and unrelated refresh preserve the full draft", async () => {
  const h = harness({ fetchReply: path => { assert.equal(path, "/api/overview"); return reply(h.overview); } });
  const value = savedReady(h), before = JSON.stringify(value);
  h.$("conditionsFz").value = "-151"; h.ui.changeAnalysisConditionsDraft();
  assert.equal(h.$("analysisConditionsRunBtn").disabled, true); assert.match(h.$("analysisConditionsRecord").textContent, /保存|저장 후/);
  await h.ui.runAnalysisConditions(); assert.equal(h.paths.length, 0); assert.match(h.$("analysisConditionsError").textContent, /새로 저장|다시 여/);
  await h.ui.saveAnalysisConditions(); assert.equal(h.paths.length, 0); assert.match(h.$("analysisConditionsError").textContent, /새 조건 ID/);
  h.$("conditionsId").value = "C-next"; h.ui.changeAnalysisConditionsDraft(); assert.equal(h.$("analysisConditionsSaveBtn").disabled, false);
  await h.ui.loadOverview(); assert.equal(h.$("conditionsFz").value, "-151"); assert.equal(JSON.stringify(value), before);
});

test("imported whole-final-solid declarations save/reopen but server refusal prevents any forced fixture analysis", async () => {
  const data = catalog("fixture.freecad"); let value;
  const h = harness({ backend: "fixture.freecad", fetchReply: (path, options) => {
    if (path === "/api/overview") return reply(h.overview);
    if (path === "/api/analysis-conditions/C-conditions") return reply({ record: value, integrity: "VERIFIED" });
    assert.equal(path, "/api/jobs"); const body = JSON.parse(options.body); assert.equal(body.operation, "analysis_conditions_save");
    assert.equal(body.arguments.declaration.loads[0].selection_id, "B-final"); assert.equal(body.arguments.declaration.loads[0].components.FX, 12);
    value = record(data, body.arguments, "UNSUPPORTED_FOR_MODEL"); return reply({ id: "J-save", operation: body.operation, status: "COMPLETED", result: value });
  } });
  ready(h, data); h.$("conditionsFx").value = "12";
  await h.ui.saveAnalysisConditions(); assert.equal(h.$("analysisConditionsRunBtn").disabled, true);
  assert.match(h.$("analysisConditionsRecord").textContent, /UNSUPPORTED_FOR_MODEL/); assert.match(h.$("analysisConditionsRecord").textContent, /adapter에서 지원되지/);
  await h.ui.runAnalysisConditions(); assert.equal(h.paths.filter(item => item.path === "/api/jobs").length, 1);
  h.$("conditionsFx").value = "999"; h.ui.changeAnalysisConditionsDraft();
  await h.ui.openAnalysisConditionsRecord("C-conditions");
  assert.equal(h.$("conditionsFx").value, "12"); assert.equal(h.$("conditionsLoadSelection").value, "B-final");
  assert.equal(h.$("analysisConditionsRunBtn").disabled, true); assert.equal(h.$("analysisConditionsSaveBtn").disabled, true);
  assert.equal(value.adapter_binding, null); assert.equal(value.engineering, "UNKNOWN"); assert.equal(value.decision, "NOT_RELEASED");
});

test("readonly, recovery, active-job and explicit capability refusal prevent typed save/run POSTs", async () => {
  for (const mutate of [h => { h.overview.stores[0].writable = false; }, h => { h.overview.execution = { state: "RECOVERY_REQUIRED", accepting_jobs: false }; },
      h => { h.ui.state.job = { id: "J-active", status: "RUNNING" }; }, h => { h.overview.capabilities = ["analysis_conditions_save", "analysis_run"].map(operation => ({ operation, callable: false })); }]) {
    const h = harness(); savedReady(h); h.$("conditionsId").value = "C-next"; h.ui.changeAnalysisConditionsDraft(); mutate(h); h.ui.updateControls();
    assert.equal(h.$("analysisConditionsSaveBtn").disabled, true); await h.ui.saveAnalysisConditions(); assert.equal(h.paths.length, 0);
    h.$("conditionsId").value = "C-conditions"; h.ui.state.analysisConditions.recordDraft = JSON.stringify(h.ui.analysisConditionsFields()); h.ui.updateControls();
    assert.equal(h.$("analysisConditionsRunBtn").disabled, true); await h.ui.runAnalysisConditions(); assert.equal(h.paths.length, 0);
  }
});

test("late catalog success and error cannot attach to changed store, study, CAD model, parent or draft", async () => {
  const changes = [h => { h.overview.active_store = "other"; }, h => { h.ui.state.studyId = "S-other"; },
    h => { h.$("cadModel").value = "different native CAD"; }, h => { h.$("conditionsParent").value = "E-import"; },
    h => { h.$("conditionsFz").value = "-999"; h.ui.changeAnalysisConditionsDraft(); }];
  for (const change of changes) for (const failure of [false, true]) {
    let complete; const h = harness({ fetchReply: () => new Promise(resolve => { complete = resolve; }) });
    const pending = h.ui.loadAnalysisConditionsCatalog(); change(h);
    h.$("analysisConditionsCatalog").textContent = "Current catalog sentinel"; h.$("analysisConditionsError").textContent = "Current error sentinel";
    complete(reply(failure ? { error: "Late foreign catalog error" } : catalog(), !failure)); await pending;
    assert.equal(h.ui.state.analysisConditions.catalog, null); assert.equal(h.$("analysisConditionsCatalog").textContent, "Current catalog sentinel");
    assert.equal(h.$("analysisConditionsError").textContent, "Current error sentinel"); assert.equal(h.paths.length, 1, "No stale condition-list read follows");
  }
});

test("late saved-record success and error cannot replace an edited or newly selected model draft", async () => {
  for (const failure of [false, true]) for (const edit of [h => { h.$("conditionsFz").value = "-201"; h.ui.changeAnalysisConditionsDraft(); },
      h => { h.$("cadModel").value = "new native model"; h.ui.invalidateAnalysisConditions(); }]) {
    let complete; const h = harness({ fetchReply: () => new Promise(resolve => { complete = resolve; }) });
    const data = ready(h), value = savedReady(h, data); h.ui.state.analysisConditions.record = null;
    const pending = h.ui.openAnalysisConditionsRecord("C-conditions"); edit(h);
    h.$("analysisConditionsRecord").textContent = "New record sentinel"; h.$("analysisConditionsError").textContent = "New error sentinel";
    complete(reply(failure ? { error: "Late foreign record error" } : { record: value, integrity: "VERIFIED" }, !failure)); await pending;
    assert.equal(h.ui.state.analysisConditions.record, null); assert.equal(h.$("analysisConditionsRecord").textContent, "New record sentinel");
    assert.equal(h.$("analysisConditionsError").textContent, "New error sentinel");
    if (h.$("conditionsFz").value === "-201") assert.equal(h.$("conditionsFz").value, "-201");
  }
});

test("wrong revision/hash/support on reopen keeps the unsaved human inputs and blocks native execution", async () => {
  for (const mutate of [value => { value.source.cad_revision = "0".repeat(64); }, value => { value.source.result_sha256 = "0".repeat(64); },
      value => { value.support.native_runtime = "AVAILABLE"; }, value => { value.request.declaration.loads[0].selection_id = "triangle-1"; }]) {
    const data = catalog(); let value;
    const h = harness({ fetchReply: () => reply({ record: value, integrity: "VERIFIED" }) });
    ready(h, data); value = record(data, analysisControls.buildSave(data, clone(h.ui.analysisConditionsFields()))); mutate(value);
    h.$("conditionsFz").value = "-211"; await h.ui.openAnalysisConditionsRecord("C-conditions");
    assert.equal(h.$("conditionsFz").value, "-211"); assert.equal(h.$("analysisConditionsRunBtn").disabled, true);
    assert.equal(h.$("analysisConditionsError").hidden, false); assert.equal(h.paths.length, 1);
  }
});

test("new single-job save retains lifecycle but rejects late completion and terminal errors after draft changes", async () => {
  for (const failure of [false, true]) {
    const data = catalog(); let submitted, completeOverview;
    const h = harness({ fetchReply: (path, options) => {
      if (path === "/api/jobs") { submitted = JSON.parse(options.body); return reply({ id: "J-conditions", operation: submitted.operation, status: "RUNNING" }); }
      if (path === "/api/jobs/J-conditions") return reply(failure ? { id: "J-conditions", operation: submitted.operation, status: "FAILED", error: "Late terminal error" } :
        { id: "J-conditions", operation: submitted.operation, status: "COMPLETED", result: record(data, submitted.arguments) });
      assert.equal(path, "/api/overview"); return new Promise(resolve => { completeOverview = resolve; });
    } });
    ready(h, data); await h.ui.saveAnalysisConditions(); assert.equal(h.ui.state.job.id, "J-conditions"); assert.equal(h.timers.length, 1);
    const pending = h.ui.pollJob(); await new Promise(resolve => setImmediate(resolve)); assert(completeOverview);
    h.$("conditionsFz").value = "-222"; h.ui.changeAnalysisConditionsDraft(); h.$("noticeText").textContent = "Current notice sentinel";
    completeOverview(reply(h.overview)); await pending;
    assert.equal(h.ui.state.analysisConditions.record, null); assert.equal(h.$("conditionsFz").value, "-222");
    assert.equal(h.$("noticeText").textContent, "Current notice sentinel"); assert.equal(h.ui.state.job.status, failure ? "FAILED" : "COMPLETED");
    assert.equal(h.ui.state.handlers.has("J-conditions"), false); assert.equal(h.ui.state.handlerGuards.has("J-conditions"), false);
  }
});

test("late new-analysis Results success or error cannot render under an edited condition draft", async () => {
  for (const failure of [false, true]) {
    let completeResult;
    const h = harness({ fetchReply: (path, options) => {
      if (path === "/api/jobs") { const request = JSON.parse(options.body); assert.equal(request.operation, "analysis_run"); return reply({ id: "J-run", operation: "analysis_run", status: "COMPLETED", result: child() }); }
      if (path === "/api/overview") return reply(h.overview);
      assert.equal(path, "/api/experiments/E-child"); return new Promise(resolve => { completeResult = resolve; });
    } });
    savedReady(h); const pending = h.ui.runAnalysisConditions(); await new Promise(resolve => setImmediate(resolve)); assert(completeResult);
    h.$("conditionsFz").value = "-301"; h.ui.changeAnalysisConditionsDraft(); h.$("experimentDetail").textContent = "Current results sentinel";
    h.$("analysisConditionsError").textContent = "Current condition error sentinel";
    completeResult(reply(failure ? { error: "Late results failure" } : { integrity: "VERIFIED", result: child() }, !failure)); await pending;
    assert.equal(h.$("experimentDetail").textContent, "Current results sentinel"); assert.equal(h.ui.state.selectedExperiment, null);
    assert.equal(h.$("analysisConditionsError").textContent, "Current condition error sentinel"); assert.equal(h.$("conditionsFz").value, "-301");
  }
});

test("absent new helper degrades harmlessly in older controlled-DOM harnesses", () => {
  const h = harness({ moduleAvailable: false });
  assert.doesNotThrow(() => { h.ui.renderAnalysisConditionsParents(); h.ui.updateControls(); h.ui.invalidateAnalysisConditions(); });
  assert.equal(h.paths.length, 0); assert.equal(h.ui.state.analysisConditions.catalog, null);
});

function nativeCatalog() {
  const data = catalog("fixture.freecad");
  data.catalog.selections = [{ id: "B-final", label: "최종 솔리드", kind: "whole_final_solid", roles: ["material"] },
    ...[1, 2, 3, 4].map(index => ({ id: `F-${"1".repeat(64)}-Face${index}`, label: `면 ${index} <TEST_ONLY>`, kind: "native_face", roles: ["boundary", "load"],
      native_object: "FinalPad", native_name: `Face${index}`, body_id: "B-final", area_mm2: 80 + index, center_mm: [index, -2.5, 4],
      bounds_mm: { min: [0, -5, 0], max: [10, 5, 8] }, surface_type: "Plane", unit: "mm", coordinate_system: "global", native_coordinate_system: "cad_document_global", geometry_sha256: "2".repeat(64) }))];
  data.backends = [{ backend: "structure.calculix.native", label: "Native CalculiX", scope: "단일 final solid · 선언 입력 · 설치 미확인" }];
  return data;
}
function nativeReady(h) {
  const data = ready(h, nativeCatalog());
  h.$("conditionsBackend").value = "structure.calculix.native"; h.$("conditionsBoundarySelection").value = data.catalog.selections[1].id;
  h.$("conditionsLoadSelection").value = data.catalog.selections[4].id;
  h.$("conditionsUyEnabled").checked = false; h.$("conditionsUzEnabled").checked = false;
  h.ui.renderAnalysisConditionsCatalog(); h.ui.updateControls(); return data;
}
async function event(node, name) { assert(node.listeners?.has(name), `${name} listener is connected`); await node.listeners.get(name)({ target: node, currentTarget: node }); }
function cadInspection(backend = "fixture.freecad") {
  return { integrity: "VERIFIED", hashes: { result_sha256: "b".repeat(64) }, result: { experiment_id: "E-cad", study: { id: "S-study" },
    cad_revision: "a".repeat(64), provenance: { adapter: backend }, solver_status: "NOT_RUN", status: "COMPLETED_REVIEW_REQUIRED", decision: "NOT_RELEASED" } };
}

test("Research starts with question/answer and collapsed technical support while every existing control ID remains unique", () => {
  assert.match(html, /<details\b[^>]*class="[^"]*technical-support"[^>]*><summary>기술·지원 정보<\/summary>/);
  const capabilityStart = html.indexOf('<details class="card capability-card');
  assert(capabilityStart > html.indexOf('id="researchAnswers"'));
  assert.equal(/\bopen\b/.test(html.slice(capabilityStart, html.indexOf(">", capabilityStart))), false);
  for (const id of ["capabilities", "researchScope", "researchQuestionForm", "jobCancelBtn", "historyPanel", "conditionsParent", "analysisConditionsForm", "simulationForm", "experimentDetail"])
    assert.equal([...html.matchAll(new RegExp(`id="${id}"`, "g"))].length, 1, id);
  const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map(match => match[1]); assert.equal(ids.length, new Set(ids).size);
});

test("engineering panes move the original controls, inspector and result properties instead of cloning any model or run form", () => {
  const h = harness({ workspace: true }), inspector = h.$("experimentDetail"), runForm = h.$("analysisConditionsRunForm");
  h.ui.initializeEngineeringWorkspace(); h.ui.showArea("design");
  assert.equal(h.$("designRunCard").parentNode, h.$("designPropertiesPane"));
  assert.equal(h.$("designSourceCard").parentNode, h.$("designOutlinePane"));
  assert.equal(h.$("analysisConditionsArea").parentNode, h.$("simulationPropertiesPane"));
  assert.equal(runForm.parentNode, h.$("simulationExecutionToolbar"));
  assert.equal(h.$("conditionsSourceControls").parentNode, h.$("simulationSourceControls"));
  assert.equal(inspector.parentNode, h.$("designModelViewport"));
  const originalProperties = new Node(), overview = new Node(); originalProperties.textContent = "ORIGINAL SIGNED INPUTS";
  h.ui.state.experimentProperties = originalProperties; h.ui.state.experimentOverview = overview;
  h.ui.showArea("simulation"); assert.equal(inspector.parentNode, h.$("simulationModelViewport")); assert.equal(originalProperties.parentNode, h.$("simulationResultPropertiesBody"));
  h.ui.showArea("results"); assert.equal(inspector.parentNode, h.$("resultsModelViewport")); assert.equal(originalProperties.parentNode, overview);
  assert.equal(originalProperties.textContent, "ORIGINAL SIGNED INPUTS"); assert.equal(runForm, h.$("analysisConditionsRunForm")); assert.equal(h.paths.length, 0);
});

test("explicit engineering parent open checks actual study/revision/backend/result hash and readonly can inspect without a write", async () => {
  const h = harness({ workspace: true, writable: false, backend: "fixture.freecad", fetchReply: path => { assert.equal(path, "/api/experiments/E-cad"); return reply(cadInspection()); } });
  nativeReady(h); h.ui.initializeEngineeringWorkspace(); await h.ui.openEngineeringRecord("simulation");
  assert.equal(h.ui.state.selectedExperiment.result.experiment_id, "E-cad"); assert.equal(h.sandbox.location.hash, "simulation");
  assert.equal(h.$("experimentDetail").parentNode, h.$("simulationModelViewport")); assert.match(h.$("simulationModelOutline").textContent, /E-cad/);
  assert.equal(h.$("analysisConditionsSaveBtn").disabled, true); assert.equal(h.$("conditionsAddBoundaryBtn").disabled, true);
  for (const mutate of [value => { value.hashes.result_sha256 = "3".repeat(64); }, value => { value.result.cad_revision = "3".repeat(64); },
      value => { value.result.provenance.adapter = "fixture.assembly"; }, value => { value.result.study.id = "S-other"; }]) {
    const wrong = cadInspection(); mutate(wrong);
    const other = harness({ workspace: true, backend: "fixture.freecad", fetchReply: () => reply(wrong) }); nativeReady(other);
    await assert.rejects(other.ui.openEngineeringRecord("simulation")); assert.equal(other.ui.state.selectedExperiment, null);
  }
});

test("engineering parent late success/error is discarded after store, study, model or selected revision changes", async () => {
  for (const change of [h => { h.overview.active_store = "other"; }, h => { h.ui.state.studyId = "S-other"; },
      h => { h.$("cadModel").value = "different-native-model"; }, h => { h.$("conditionsParent").value = "E-import"; }]) for (const fail of [false, true]) {
    let complete; const h = harness({ workspace: true, backend: "fixture.freecad", fetchReply: () => new Promise(resolve => { complete = resolve; }) }); nativeReady(h);
    const pending = h.ui.openEngineeringRecord("simulation"); change(h); h.$("experimentDetail").textContent = "CURRENT MODEL SENTINEL";
    complete(reply(fail ? { error: "LATE MODEL ERROR" } : cadInspection(), !fail)); await pending;
    assert.equal(h.ui.state.selectedExperiment, null); assert.equal(h.$("experimentDetail").textContent, "CURRENT MODEL SENTINEL"); assert.equal(h.paths.length, 1);
  }
});

test("explicit native catalog action opens its pinned CAD while overview alone adds no model/catalog/provider reads", async () => {
  const data = nativeCatalog(); const h = harness({ workspace: true, backend: "fixture.freecad", fetchReply: path => {
    if (path === "/api/overview") return reply(h.overview);
    if (path === "/api/analysis-conditions/catalog?experiment_id=E-cad") return reply(data);
    if (path === "/api/analysis-conditions?experiment_id=E-cad") return reply({ records: [] });
    assert.equal(path, "/api/experiments/E-cad"); return reply(cadInspection());
  } });
  h.ui.initializeEngineeringWorkspace(); h.$("conditionsFz").value = "-237.75";
  await h.ui.loadOverview(); assert.deepEqual(h.paths.map(value => value.path), ["/api/overview"]);
  await h.ui.loadAnalysisConditionsCatalog();
  assert.deepEqual(h.paths.slice(1).map(value => value.path), ["/api/analysis-conditions/catalog?experiment_id=E-cad", "/api/analysis-conditions?experiment_id=E-cad", "/api/experiments/E-cad"]);
  assert.equal(h.$("conditionsFz").value, "-237.75"); assert.equal(h.$("experimentDetail").parentNode, h.$("simulationModelViewport"));
  assert.equal(h.$("conditionsBoundarySelection").options[1].value, data.catalog.selections[1].id);
  assert.equal(h.$("conditionsBackend").value, "", "Never substitute the native backend automatically");
});

test("native face row editing saves three independent boundary components, reopens them and runs only the saved C-ID", async () => {
  let savedValue, data;
  const h = harness({ workspace: true, backend: "fixture.freecad", fetchReply: (path, options) => {
    if (path === "/api/overview") return reply(h.overview);
    if (path === "/api/analysis-conditions/C-conditions") return reply({ record: savedValue, integrity: "VERIFIED" });
    if (path === "/api/experiments/E-child") { const result = child(); result.provenance.adapter = "structure.calculix.native"; return reply({ integrity: "VERIFIED", result }); }
    assert.equal(path, "/api/jobs"); assert.equal(options.headers["X-CAE-Token"], "TEST_ONLY");
    const body = JSON.parse(options.body);
    if (body.operation === "analysis_conditions_save") {
      assert.deepEqual(body.arguments.declaration.boundary_conditions.map(item => item.components), [{ UX: 0 }, { UY: -0.125 }, { UZ: 0 }]);
      assert.deepEqual(body.arguments.declaration.boundary_conditions.map(item => item.selection_id), data.catalog.selections.slice(1, 4).map(item => item.id));
      savedValue = record(data, body.arguments); return reply({ id: "J-save", operation: body.operation, status: "COMPLETED", result: savedValue });
    }
    assert.equal(body.operation, "analysis_run"); assert.deepEqual(body.arguments, { parent_experiment_id: "E-cad", experiment_id: "E-child", backend: "structure.calculix.native", conditions_id: "C-conditions" });
    const result = child(); result.provenance.adapter = "structure.calculix.native"; return reply({ id: "J-run", operation: body.operation, status: "COMPLETED", result });
  } });
  data = nativeReady(h); h.ui.initializeEngineeringWorkspace();
  assert.match(h.$("analysisConditionsCatalog").textContent, /FinalPad\/Face1/); assert.match(h.$("analysisConditionsCatalog").textContent, /81 mm²/);
  for (const [faceIndex, axis, value] of [[2, "Y", "-0.125"], [3, "Z", "0"]]) {
    h.ui.addAnalysisBoundary(); const cards = h.$("conditionsAdditionalBoundaries").children, card = cards.at(-1);
    const nodes = walk(card), select = nodes.find(node => node.tagName === "SELECT"); select.value = data.catalog.selections[faceIndex].id; await event(select, "change");
    const enabled = nodes.find(node => node.attributes["aria-label"]?.endsWith(`U${axis} 지정`)); enabled.checked = true; await event(enabled, "change");
    const numeric = nodes.find(node => node.attributes["aria-label"]?.endsWith(`U${axis} mm`)); numeric.value = value; await event(numeric, "input");
  }
  await h.ui.saveAnalysisConditions(); const original = JSON.stringify(savedValue);
  assert.match(h.$("analysisConditionsRecord").textContent, /UX 0 \/ UY 미지정 \/ UZ 미지정/);
  assert.equal(h.$("analysisConditionsRunBtn").disabled, false);
  h.ui.state.analysisConditions.additionalBoundaries[0].uy = "9"; h.ui.changeAnalysisConditionsDraft(); assert.equal(h.$("analysisConditionsRunBtn").disabled, true);
  await h.ui.openAnalysisConditionsRecord("C-conditions"); assert.equal(h.ui.state.analysisConditions.additionalBoundaries[0].uy, "-0.125");
  assert.equal(h.$("conditionsUyEnabled").checked, false); assert.equal(h.$("conditionsUy").disabled, true); assert.equal(h.$("conditionsUy").required, false);
  assert.equal(h.$("conditionsAdditionalBoundaries").children.length, 2);
  await h.ui.runAnalysisConditions(); assert.equal(h.ui.state.selectedExperiment.result.provenance.adapter, "structure.calculix.native");
  assert.equal(h.$("experimentDetail").parentNode, h.$("simulationModelViewport")); assert.equal(JSON.stringify(savedValue), original);
});

test("extra native boundaries retain unsaved sources across catalog withdrawal and cannot edit or POST while readonly or busy", async () => {
  const h = harness({ workspace: true, backend: "fixture.freecad" }); nativeReady(h); h.ui.addAnalysisBoundary();
  const row = h.ui.state.analysisConditions.additionalBoundaries[0]; row.selectionId = nativeCatalog().catalog.selections[2].id; row.source = "USER RAW SOURCE SENTINEL";
  h.$("cadModel").value = "new model"; h.ui.invalidateAnalysisConditions(); h.ui.updateControls();
  assert.equal(h.ui.state.analysisConditions.additionalBoundaries[0].source, "USER RAW SOURCE SENTINEL"); assert.match(h.$("conditionsAdditionalBoundaries").textContent, /현재 catalog에 없는 대상/);
  assert.equal(h.$("analysisConditionsSaveBtn").disabled, true); await h.ui.saveAnalysisConditions(); assert.equal(h.paths.length, 0);
  nativeReady(h); const remove = walk(h.$("conditionsAdditionalBoundaries")).find(node => Object.hasOwn(node.dataset, "boundaryRemove"));
  h.overview.stores[0].writable = false; h.ui.updateControls(); assert.equal(remove.disabled, true); await event(remove, "click"); h.ui.addAnalysisBoundary();
  assert.equal(h.ui.state.analysisConditions.additionalBoundaries.length, 1);
  h.overview.stores[0].writable = true; h.ui.state.job = { id: "J-active", status: "RUNNING", operation: "analysis_run" }; h.ui.updateControls();
  assert.equal(h.$("conditionsAddBoundaryBtn").disabled, true); await event(remove, "click"); h.ui.addAnalysisBoundary(); assert.equal(h.ui.state.analysisConditions.additionalBoundaries.length, 1);
});

test("native field controller passes the same verified-family model through the common byte loader/viewer and retains partial DOF/load rows", async () => {
  // The trusted loader and renderer are composition doubles here; their hash,
  // mesh and native physics admission are covered by their own source suites.
  const payload = new Uint8Array([123, 125]), entry = { path: "simulation/field.json", size_bytes: 2, size_mm: 4, index: 0 }, models = [];
  const h = harness({ workspace: true, fetchReply: path => {
    assert.equal(path, "/api/artifacts/E-native-field?path=simulation%2Ffield.json");
    return { ok: true, headers: { get: () => "2" }, arrayBuffer: async () => payload.buffer };
  } });
  const inspection = { result: { experiment_id: "E-native-field", provenance: { adapter: "structure.calculix.native" } } }, model = {
    metadata: { family: "native" }, field: { sources: {} }, rawNative: {
      prescribed_dofs: [{ node_id: 7, component: 1, value_mm: -0.125 }], loads: [{ node_id: 8, component: 3, force_N: -150 }] } };
  h.ui.state.selectedExperiment = inspection;
  h.sandbox.window.fixtureFieldControls = { LIMITS: { bytes: 32 }, catalog: data => { assert.equal(data, inspection); return { entries: [entry] }; },
    loadField: async (_record, selectedEntry, fetchBytes, isCurrent) => { assert.equal(selectedEntry, entry); assert(isCurrent()); assert.deepEqual(Array.from(await fetchBytes(entry.path, 2)), Array.from(payload)); return model; } };
  const provenance = new Node(); h.sandbox.window.fixtureFieldViewer = { mount: (_detail, value, current) => { assert(current()); models.push(value); return { destroy: () => {}, refs: { provenance } }; } };
  const host = new Node(); assert.equal(await h.ui.renderFixtureFields(host, inspection), true, host.textContent);
  assert.equal(models[0], model); assert.match(host.textContent, /네이티브 구조해석/); assert.match(provenance.textContent, /UX-0.125/); assert.match(provenance.textContent, /FZ-150/);
  assert.equal(provenance.textContent.includes("UY0"), false); assert.equal(provenance.textContent.includes("안장"), false);
  assert.equal(h.paths.length, 1); assert.equal(h.ui.state.fixtureViewer.refs.provenance, provenance);
});

test("native field late load and incorrect family never mount or reuse fixture fallback under another selected record", async () => {
  for (const stale of [false, true]) {
    let complete, mounts = 0; const h = harness({ workspace: true });
    const inspection = { result: { experiment_id: "E-native-field", provenance: { adapter: "structure.calculix.native" } } };
    h.ui.state.selectedExperiment = inspection;
    h.sandbox.window.fixtureFieldControls = { catalog: () => ({ entries: [{ path: "simulation/field.json", size_mm: 4, index: 0 }] }),
      loadField: () => new Promise(resolve => { complete = resolve; }) };
    h.sandbox.window.fixtureFieldViewer = { mount: () => { mounts++; return { destroy: () => {} }; } };
    const host = new Node(), pending = h.ui.renderFixtureFields(host, inspection);
    if (stale) { h.ui.state.experimentRequest++; host.textContent = "CURRENT FIELD SENTINEL"; }
    complete({ metadata: { family: "fixture" } }); assert.equal(await pending, false); assert.equal(mounts, 0);
    if (stale) assert.equal(host.textContent, "CURRENT FIELD SENTINEL"); else assert.match(host.textContent, /전체장 계약을 확인할 수 없습니다/);
  }
});

test("workspace keeps the existing owned-job cancel and cleanup controls while typed native writes stay blocked", () => {
  const h = harness({ workspace: true, backend: "fixture.freecad" }); nativeReady(h);
  for (const [status, disabled, label] of [["RUNNING", false, "작업 취소"], ["CANCEL_REQUESTED", true, "작업 취소"], ["CLEANUP_PENDING", false, "종료 재시도"]]) {
    h.ui.state.job = { id: "J-owned", operation: "analysis_run", status }; h.ui.renderJob();
    assert.equal(h.$("jobCancelBtn").hidden, false); assert.equal(h.$("jobCancelBtn").disabled, disabled); assert.equal(h.$("jobCancelBtn").textContent, label);
    assert.equal(h.$("analysisConditionsSaveBtn").disabled, true); assert.equal(h.$("analysisConditionsRunBtn").disabled, true); assert.equal(h.$("conditionsAddBoundaryBtn").disabled, true);
  }
  assert.equal(h.paths.length, 0);
});
