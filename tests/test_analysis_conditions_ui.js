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
  set textContent(value) { this._text = String(value ?? ""); this.children = []; }
  get textContent() { return this._text + this.children.map(node => node.textContent).join(""); }
  set innerHTML(_value) { throw new Error("Untrusted catalog/record text must use textContent"); }
  append(...items) { for (const item of items) { const node = item instanceof Node ? item : new Node("#text"); if (!(item instanceof Node)) node.textContent = item; this.children.push(node); } }
  replaceChildren(...items) { this._text = ""; this.children = []; this.append(...items); }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  addEventListener(name, fn) { (this.listeners ??= new Map()).set(name, fn); }
  querySelector(selector) { return walk(this).slice(1).find(node => selector.startsWith(".") ? node.classList.contains(selector.slice(1)) : node.tagName === selector.toUpperCase()) ?? null; }
}
function walk(node) { return [node, ...node.children.flatMap(walk)]; }
function harness({ backend = "fixture.cadquery", writable = true, moduleAvailable = true, fetchReply } = {}) {
  const nodes = new Map(), operations = [], writes = [], paths = [], timers = [];
  const $ = id => { if (!nodes.has(id)) nodes.set(id, new Node(/Selection$|Backend$|Unit$|Parent$|System$|Law$|Category$|Mode$/.test(id) ? "select" : "div")); return nodes.get(id); };
  for (const match of html.matchAll(/<button\b[^>]*>/g)) {
    const operation = /\bdata-operation="([^"]+)"/.exec(match[0])?.[1]; if (!operation) continue;
    const id = /\bid="([^"]+)"/.exec(match[0])?.[1], node = id ? $(id) : new Node("button"); node.dataset.operation = operation; operations.push(node);
  }
  for (const match of html.matchAll(/<fieldset\b[^>]*data-write[^>]*>/g)) { const id = /\bid="([^"]+)"/.exec(match[0])?.[1]; writes.push(id ? $(id) : new Node("fieldset")); }
  const document = { getElementById: $, createElement: tag => new Node(tag),
    querySelectorAll: selector => selector === "[data-operation]" ? operations : selector === "fieldset[data-write]" ? writes :
      selector === "[data-analysis-conditions-open]" ? walk($("analysisConditionsList")).filter(node => Object.hasOwn(node.dataset, "analysisConditionsOpen")) : [],
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
  const sandbox = { document, Node, window: { ...(moduleAvailable ? { analysisConditionsControls: analysisControls } : {}), cadControls, resultPresentation: presentation, researchControls },
    location: { hash: "simulation" }, Intl, TextEncoder, URL, URLSearchParams, console,
    fetch: async (path, options) => { paths.push({ path, options }); assert(fetchReply, `No uncontrolled HTTP: ${path}`); return fetchReply(path, options); },
    setTimeout: (fn, delay) => { timers.push({ fn, delay }); return timers.length; }, clearTimeout: () => {} };
  vm.createContext(sandbox);
  vm.runInContext(source.slice(0, boundary) + "\nglobalThis.ui = {state, updateControls, renderAnalysisConditionsParents, currentAnalysisConditionsCatalog, analysisConditionsFields, loadAnalysisConditionsCatalog, refreshAnalysisConditionsList, openAnalysisConditionsRecord, saveAnalysisConditions, runAnalysisConditions, changeAnalysisConditionsDraft, invalidateAnalysisConditions, renderAnalysisConditionsRecord, loadOverview, runJob, pollJob, inspectExperiment};", sandbox);
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
