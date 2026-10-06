"use strict";

// Source workflow proof with JSON HTTP replies and a controlled DOM only.
// Root separately owns actual browser/native/provider evidence.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const vm = require("node:vm");
const controls = require("../apps/lab/static/campaign-controls.js");
const research = require("../apps/lab/static/comparison-research.js");
const source = readFileSync(require.resolve("../apps/lab/static/app.js"), "utf8");
const html = readFileSync(require.resolve("../apps/lab/static/index.html"), "utf8");
const boundary = source.indexOf('$("jobCancelBtn").addEventListener("click", async () => {');
assert(boundary > 0);
const clone = value => structuredClone(value);
const sha = char => char.repeat(64);
const freeze = value => { if (value && typeof value === "object") { Object.values(value).forEach(freeze); Object.freeze(value); } return value; };
function entry() {
  return { parameter_id: "width", display_name: "등록 폭", native: { backend: "fixture.cadquery", document: "roller_support.py", object: "roller_support", path: "support_width_mm" },
    source_sha256: sha("9"), unit: "mm", mode: "free", kind: "continuous", geometry_effect: { status: "PASS" },
    lower_bound: 28, upper_bound: 60, current_value: 38 };
}
function condition() {
  const source = { experiment_id: "E-original", study_id: "S-study", cad_revision: sha("a"), backend: "fixture.cadquery",
    result_sha256: sha("b"), proposal_sha256: sha("c"), thread_sha256: sha("d") };
  const declaration = { analysis_type: "linear_static", units: { length: "mm", force: "N", stress: "MPa" }, coordinate_system: "global",
    materials: [{ id: "M1", selection_id: "B-final", law: "isotropic_linear_elastic", young_modulus_MPa: 210000, poisson_ratio: 0.3,
      source: { category: "ASSUMED", description: "ASSUMED: source <unqualified>" } }],
    boundary_conditions: [{ id: "BC1", selection_id: "S-base", type: "displacement", components: { UX: 0, UY: 0, UZ: 0 }, unit: "mm", coordinate_system: "global", source: "ASSUMED: ideal fixing" }],
    loads: [{ id: "L1", selection_id: "S-saddle", type: "resultant_force", components: { FX: 0, FY: 0, FZ: -217.25 }, unit: "N", coordinate_system: "global", source: "ASSUMED: signed load <source>" }],
    contact: { mode: "none", source: "ASSUMED: no contact" }, mesh: { mode: "selected", max_size_mm: 4 } };
  const catalog = { schema_version: "1.0", selections: [
    { id: "B-final", label: "최종 솔리드", kind: "body", roles: ["material", "boundary", "load"] },
    { id: "S-base", label: "바닥", kind: "adapter_region", roles: ["boundary"] },
    { id: "S-saddle", label: "안장", kind: "adapter_region", roles: ["load"] }],
    coordinate_systems: [{ id: "global", label: "전역", type: "cartesian", unit: "mm", basis: [[1, 0, 0], [0, 1, 0], [0, 0, 1]], origin: [0, 0, 0] }], limitations: ["No general face mapping"] };
  return { schema_version: "1.0", id: "C-original", created_utc: "2026-10-06T00:00:00Z", source, catalog, catalog_revision: sha("e"), conditions_revision: sha("f"),
    request: { conditions_id: "C-original", experiment_id: "E-original", cad_revision: sha("a"), catalog_revision: sha("e"), backend: "fixture.calculix", declaration },
    support: { status: "SUPPORTED_DECLARED_INPUTS", reasons: [], native_runtime: "NOT_CHECKED" },
    adapter_binding: { backend: "fixture.calculix", version: "TEST_ONLY", conditions_version: "TEST_ONLY", settings: { material: { E_MPa: 210000 }, load: { force_per_support_N: 217.25 }, mesh: { mode: "selected", max_sizes_mm: [4] } }, settings_sha256: sha("8") },
    engineering: "UNKNOWN", decision: "NOT_RELEASED", provenance: { test_only: true } };
}
function inspection(record = condition()) {
  return { integrity: "VERIFIED", result: { experiment_id: record.source.experiment_id, study: { id: "S-study" }, cad_revision: sha("a"),
    provenance: { adapter: "fixture.cadquery" }, solver_status: "NOT_RUN", status: "COMPLETED_REVIEW_REQUIRED", decision: "NOT_RELEASED" },
    hashes: { result_sha256: sha("b"), proposal_sha256: sha("c"), thread_sha256: sha("d") },
    proposal: { id: record.source.experiment_id, study_id: "S-study", model: { geometry: { backend: "fixture.cadquery", source: "roller_support" } }, parameters: { width: 38 } },
    registry_snapshot: { revision: 1, entries: [entry()] } };
}
function context() { return { store: "local", studyId: "S-study", backend: "fixture.cadquery", model: "roller_support", entries: [entry()] }; }
function campaign(type = "optimization", complete = true, count = 2) {
  const saved = condition();
  const plan = { campaign_id: "C-campaign", study_id: "S-study", backend: "fixture.cadquery", model: "roller_support", status: "PLANNED",
    algorithm: { engine: type === "optimization" ? "scipy.differential_evolution" : "scipy.latin_hypercube", version: "TEST_ONLY", seed: 13 },
    variables: [{ parameter_id: "width", lower: 28, upper: 60 }],
    objective: { source: "analysis", metric: "max_displacement", unit: "mm", direction: "minimize" }, constraints: [],
    analysis: { backend: "fixture.calculix", settings: clone(saved.adapter_binding.settings), conditions_template: {
      rebind_policy: "REVISION_REBIND_EXACT_SELECTIONS", reference: { id: saved.id, revision: saved.conditions_revision,
        record_sha256: sha("7"), catalog_revision: saved.catalog_revision, scope: "USER_DECLARED_UNVERIFIED" }, record: saved, record_canonical_sha256: sha("6") } } };
  const rows = Array.from({ length: count }, (_, index) => ({ index, values: { width: 38 + index }, cad_experiment_id: `E-C-campaign-${String(index).padStart(4, "0")}`,
    cad_result_sha256: sha("1"), cad_status: "COMPLETED_REVIEW_REQUIRED", analysis_experiment_id: `A-C-campaign-${String(index).padStart(4, "0")}`,
    analysis_result_sha256: sha("2"), analysis_status: "COMPLETED_REVIEW_REQUIRED", decision: "NOT_RELEASED", unknown: ["material", "strength"],
    objective: { value: index === 0 ? -0.03 : null, unit: "mm", valid: index === 0 }, feedback: { objective: index === 0 ? -0.03 : null }, numerically_feasible: index === 0 }));
  const record = complete ? { campaign_id: plan.campaign_id, study_id: plan.study_id, status: "COMPLETED_REVIEW_REQUIRED", decision: "NOT_RELEASED", plan_sha256: sha("3"),
    [type === "optimization" ? "evaluations" : "samples"]: rows } : { status: "PLANNED", plan, evaluations: [] };
  return { id: plan.campaign_id, type, plan, record };
}

test("saved CAD conditions decorate either numeric campaign with only C-ID and adapter backend; inputs stay immutable", () => {
  const saved = freeze(condition()), original = freeze(inspection(saved)), current = freeze(context());
  const before = JSON.stringify([saved, original, current]);
  const selection = controls.conditionSelection(saved, original, current);
  assert.deepEqual(controls.conditionPlanArguments(selection, current, ["width"]), { conditions_id: "C-original", analysis_backend: "fixture.calculix" });
  assert.equal(Object.hasOwn(controls.conditionPlanArguments(selection, current, ["width"]), "analysis_settings"), false);
  assert.equal(JSON.stringify([saved, original, current]), before);
  selection.record.request.declaration.loads[0].components.FZ = -100;
  assert.equal(saved.request.declaration.loads[0].components.FZ, -217.25);
});

test("wrong source pins, unsupported adapter and native document/source drift refuse without a settings fallback", () => {
  for (const mutate of [
    (s, i) => { i.integrity = "UNKNOWN"; }, (s, i) => { i.hashes.proposal_sha256 = sha("0"); },
    (s, i) => { i.result.cad_revision = sha("0"); }, (s, i) => { i.proposal.model.geometry.source = "other"; },
    (s, i) => { i.registry_snapshot.entries[0].native.document = "other.py"; },
    (s, i) => { i.registry_snapshot.entries[0].source_sha256 = sha("0"); },
    s => { s.support.status = "UNSUPPORTED_FOR_MODEL"; s.adapter_binding = null; },
    s => { s.decision = "RELEASED"; }, s => { s.request.cad_revision = sha("0"); }
  ]) {
    const saved = condition(), original = inspection(saved), current = context(); mutate(saved, original, current);
    assert.throws(() => controls.conditionSelection(saved, original, current));
  }
  const selection = controls.conditionSelection(condition(), inspection(), context());
  for (const change of [{ store: "history" }, { studyId: "S-other" }, { model: "other" }, { backend: "fixture.freecad" },
    { entries: [{ ...entry(), source_sha256: sha("0") }] }, { entries: [{ ...entry(), geometry_effect: { status: "UNKNOWN" } }] }]) {
    assert.throws(() => controls.conditionPlanArguments(selection, { ...context(), ...change }, ["width"]));
  }
  assert.throws(() => controls.conditionPlanArguments(selection, context(), ["invented"]));
  assert.throws(() => controls.conditionPlanArguments(selection, context(), ["width", "width"]));
});

test("frozen template preserves support, exact rebind policy and projected settings on completed reopen", () => {
  const data = freeze(campaign()), template = controls.conditionTemplate(data.plan);
  assert.equal(template.reference.id, "C-original");
  assert.equal(template.record.request.declaration.loads[0].components.FZ, -217.25);
  for (const mutate of [p => { p.analysis.settings.load.force_per_support_N = 150; }, p => { p.analysis.conditions_template.reference.id = "C-other"; },
    p => { p.analysis.conditions_template.rebind_policy = "GUESS"; }, p => { p.analysis.conditions_template.reference.catalog_revision = sha("0"); }]) {
    const plan = clone(data.plan); mutate(plan); assert.throws(() => controls.conditionTemplate(plan));
  }
});

test("completed campaign question cites original condition, signed declarations, real candidates and invalid semantics without mutation", () => {
  for (const type of ["doe", "optimization"]) {
    const data = freeze(campaign(type)), before = JSON.stringify(data), draft = research.campaignDraft(data, "S-study", [1, 0]);
    assert.equal(draft.intent, "INTERPRET_SAVED_RESULTS"); assert.equal(draft.conditionsId, "C-original"); assert.equal(draft.sourceExperimentId, "E-original");
    assert.deepEqual(draft.candidateIndexes, [1, 0]); assert.deepEqual(draft.experimentIds, ["A-C-campaign-0001", "A-C-campaign-0000"]);
    for (const text of ["C-original", "E-original", "C-campaign", "A-C-campaign-0001", "FZ=-217.25 N", "ASSUMED", "global", "analysis_conditions_context", "invalid", "UNKNOWN", "NOT_RELEASED", "|UZ|", "|U|", "USER_DECLARED_UNVERIFIED"]) assert(draft.question.includes(text), text);
    assert.match(draft.question, /새 계산·최적화 실행 없이/); assert.equal(JSON.stringify(data), before);
    assert.equal(data.record[type === "optimization" ? "evaluations" : "samples"][1].feedback.objective, null);
  }
});

test("planned optimization handoff requests inspect and run of the existing ID only; DOE cannot advertise AI execution", () => {
  const draft = research.campaignDraft(campaign("optimization", false), "S-study", []);
  assert.equal(draft.intent, "RUN_SAVED_OPTIMIZATION"); assert.deepEqual(draft.experimentIds, []);
  assert.match(draft.question, /optimization_inspect/); assert.match(draft.question, /optimization_run\(\{campaign_id: "C-campaign"\}\)/);
  assert.match(draft.question, /아직 실제 후보 결과가 없습니다/); assert.match(draft.question, /새 계획·원시 설정·변수·하중·재료를 만들거나 대체하지/);
  assert.throws(() => research.campaignDraft(campaign("doe", false), "S-study", []));
});

test("cross-study, skipped results, malformed pins, overlarge and duplicate candidate questions are refused as a whole", () => {
  assert.throws(() => research.campaignDraft(campaign(), "S-other", [0]));
  assert.throws(() => research.campaignDraft(campaign(), "S-study", [0, 0]));
  assert.throws(() => research.campaignDraft(campaign(), "S-study", [12]));
  assert.throws(() => research.campaignDraft(campaign("optimization", true, 13), "S-study", Array.from({ length: 13 }, (_, i) => i)));
  for (const mutate of [d => { d.record.evaluations[0].analysis_result_sha256 = null; }, d => { d.record.evaluations[0].analysis_experiment_id = null; },
    d => { d.plan.analysis.conditions_template.record.source.cad_revision = sha("0"); },
    d => { d.plan.analysis.conditions_template.record.support.status = "UNSUPPORTED_FOR_MODEL"; },
    d => { d.record.evaluations[0].decision = "RELEASED"; }]) {
    const data = campaign(); mutate(data); assert.throws(() => research.campaignDraft(data, "S-study", [0]));
  }
});

class Node {
  constructor(tag = "div") { this.tagName = tag.toUpperCase(); this.children = []; this.dataset = {}; this.value = ""; this.hidden = false; this.disabled = false; this.checked = false; this._text = ""; this.className = ""; this.isConnected = true; this.listeners = new Map(); this.attributes = {};
    this.classList = { toggle: (name, on) => { if (on) this.className += ` ${name}`; }, add: (...names) => { this.className += ` ${names.join(" ")}`; },
      remove: (...names) => { this.className = this.className.split(/\s+/).filter(name => !names.includes(name)).join(" "); }, contains: name => this.className.split(/\s+/).includes(name) }; }
  get textContent() { return this._text + this.children.map(node => node.textContent).join(""); }
  set textContent(value) { this._text = String(value ?? ""); this.children = []; }
  set innerHTML(value) { throw new Error(`Untrusted content HTML: ${value}`); }
  append(...items) { this.children.push(...items.map(item => item instanceof Node ? item : Object.assign(new Node("#text"), { textContent: item }))); }
  replaceChildren(...items) { this._text = ""; this.children = []; this.append(...items); }
  get options() { return this.children.filter(node => node.tagName === "OPTION"); }
  addEventListener(type, callback) { this.listeners.set(type, callback); }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  querySelector(selector) { return walk(this).find(node => selector === `.${node.className}` || node.tagName === selector.toUpperCase()) ?? null; }
  focus() {}
}
function walk(node) { return [node, ...node.children.flatMap(walk)]; }
function deferred() { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
function harness({ fetchReply, writable = true } = {}) {
  const nodes = new Map(), paths = [], timers = [];
  const $ = id => { if (!nodes.has(id)) nodes.set(id, new Node("div")); return nodes.get(id); };
  const attrNodes = [];
  for (const match of html.matchAll(/<button\b[^>]*\bdata-operation="([^"]+)"[^>]*>/g)) {
    const id = /\bid="([^"]+)"/.exec(match[0])?.[1], node = id ? $(id) : new Node("button"); node.dataset.operation = match[1]; attrNodes.push(node);
  }
  const all = () => [...new Set([...attrNodes, ...[...nodes.values()].flatMap(walk)])];
  const selected = selector => {
    const data = /^\[data-([a-z-]+)\](?::checked)?$/.exec(selector);
    if (!data) return [];
    const key = data[1].replace(/-([a-z])/g, (_, char) => char.toUpperCase());
    return all().filter(node => Object.hasOwn(node.dataset, key) && (!selector.endsWith(":checked") || node.checked));
  };
  const document = { getElementById: $, createElement: tag => new Node(tag), querySelectorAll: selected,
    querySelector: selector => /^\[data-operation=/.test(selector) ? attrNodes.find(node => selector === `[data-operation="${node.dataset.operation}"]`) : selected(selector)[0] ?? null };
  const sandbox = { document, Node, window: {}, Intl, TextEncoder, URL, URLSearchParams, location: { hash: "simulation" },
    setTimeout: (fn, delay) => { timers.push({ fn, delay }); return timers.length; }, clearTimeout: () => {},
    fetch: async (path, options) => { paths.push({ path, options }); assert(fetchReply, `Unexpected HTTP ${path}`); return fetchReply(path, options); } };
  vm.createContext(sandbox);
  for (const file of ["campaign-controls", "comparison-research", "analysis-conditions-controls", "cad-controls", "research-controls", "result-presentation"]) vm.runInContext(readFileSync(require.resolve(`../apps/lab/static/${file}.js`), "utf8"), sandbox);
  const evaluateJson = value => { sandbox.jsonFixture = JSON.stringify(value); return vm.runInContext("JSON.parse(jsonFixture)", sandbox); };
  const reply = (value, status = 200) => ({ ok: status < 400, status, json: async () => evaluateJson(value) });
  vm.runInContext(source.slice(0, boundary) + "\nglobalThis.ui = {state, prepareCampaignConditions, campaignConditionsCurrent, campaignArguments, submitCampaignPlan, inspectCampaign, renderCampaignDetail, prepareCampaignResearch, updateControls, withdrawCampaignConditions, campaignFormSignature, loadOverview, inspectExperiment, runJob, pollJob};", sandbox);
  const ui = sandbox.ui;
  const defaults = { cadBackend: "fixture.cadquery", cadModel: "roller_support", nativeModelId: "", campaignTarget: "cad", campaignType: "optimization", campaignId: "C-campaign", campaignSeed: "13", campaignSamples: "2",
    objectiveSource: "analysis", objectiveMetric: "max_displacement", objectiveUnit: "mm", objectiveDirection: "minimize", optimizationConstraints: "[]", optimizationInitial: "null", optimizationRequired: '{"cad":[],"analysis":[]}', optimizationGenerations: "1", optimizationPopulation: "5",
    campaignAnalysisSource: "legacy", campaignAnalysis: "structural_linear", campaignAnalysisSettings: '{"raw_user_draft":"KEEP THIS"}', conditionsParent: "E-original", conditionsId: "C-original", conditionsBackend: "fixture.calculix",
    conditionsMaterialSelection: "B-final", conditionsMaterialLaw: "isotropic_linear_elastic", conditionsYoungModulus: "210000", conditionsPoissonRatio: "0.3", conditionsMaterialCategory: "ASSUMED", conditionsMaterialSource: "ASSUMED: source <unqualified>",
    conditionsCoordinateSystem: "global", conditionsLengthUnit: "mm", conditionsForceUnit: "N", conditionsStressUnit: "MPa", conditionsBoundarySelection: "S-base", conditionsUx: "0", conditionsUy: "0", conditionsUz: "0", conditionsBoundarySource: "ASSUMED: ideal fixing",
    conditionsLoadSelection: "S-saddle", conditionsFx: "0", conditionsFy: "0", conditionsFz: "-217.25", conditionsLoadSource: "ASSUMED: signed load <source>", conditionsContactMode: "none", conditionsContactSource: "ASSUMED: no contact", conditionsMeshSize: "4", conditionsExperimentId: "E-next", researchQuestion: "작성 중인 가설 질문", simulationPreset: "structural_linear" };
  Object.entries(defaults).forEach(([id, value]) => { $(id).value = value; });
  $("fixtureConditionFields").hidden = true; $("importedMeshFields").hidden = true;
  const variable = new Node("input"); variable.value = "width"; variable.checked = true; variable.dataset.campaignVariable = ""; $("campaignVariables").append(variable);
  const overview = { active_store: "local", token: "TEST_ONLY", stores: [{ id: "local", writable }], capabilities: [], studies: [{ id: "S-study" }], campaigns: [], jobs: [],
    experiments: [{ id: "E-original", study_id: "S-study", cad_revision: sha("a"), backend: "fixture.cadquery", solver_status: "NOT_RUN", status: "COMPLETED_REVIEW_REQUIRED" }] };
  ui.state.overview = evaluateJson(overview); ui.state.studyId = "S-study"; ui.state.registry = evaluateJson({ revision: 1, entries: [entry()] });
  ui.state.presets = evaluateJson({ structural_linear: { backend: "fixture.calculix", operation: "analysis_run", parent_backends: ["fixture.cadquery"] } });
  const saved = evaluateJson(condition());
  ui.state.analysisConditions.record = saved;
  ui.state.analysisConditions.recordDraft = vm.runInContext("JSON.stringify(analysisConditionsFields())", sandbox);
  ui.state.analysisConditions.catalog = evaluateJson({ source: saved.source, catalog: saved.catalog, catalog_revision: saved.catalog_revision,
    backends: [{ backend: "fixture.calculix", label: "CalculiX", scope: "Declared input only" }] });
  ui.state.analysisConditions.context = vm.runInContext("analysisConditionsContext()", sandbox);
  sandbox.renderOverview = () => ui.updateControls(); sandbox.renderResearchAnswers = () => {}; sandbox.renderJob = () => ui.updateControls();
  sandbox.loadNativeImports = async () => {}; sandbox.loadStudy = async () => {}; sandbox.showArea = () => {};
  sandbox.renderExperimentDetail = data => { $("experimentDetail").textContent = `SAME_RESULT ${JSON.stringify(data.result)}`; };
  sandbox.renderObservation = () => {}; sandbox.loadResponseHistories = async () => {};
  return { ui, sandbox, $, paths, timers, overview, reply, evaluateJson, all, variable };
}
function completedChild(row) {
  return { integrity: "VERIFIED", hashes: { result_sha256: row.analysis_result_sha256 },
    result: { experiment_id: row.analysis_experiment_id, parent_experiment_id: row.cad_experiment_id, study: { id: "S-study" }, cad_revision: sha("4"),
      solver_status: "COMPLETED", status: "COMPLETED_REVIEW_REQUIRED", decision: "NOT_RELEASED", provenance: { adapter: "fixture.calculix", analysis_conditions: { id: "C-C-campaign-0000", revision: sha("5") } },
      metrics: { invalid_stress: { valid: false, value: null, unit: "MPa" }, signed_reaction: { valid: true, value: [0, 0, 217.25], unit: "N" } } } };
}
async function click(node) { assert(node?.listeners.get("click")); node.listeners.get("click")(); await new Promise(resolve => setImmediate(resolve)); await new Promise(resolve => setImmediate(resolve)); }

test("explicit saved-condition choice preserves raw settings and both DOE/DE payloads, with no automatic catalogue or provider HTTP", async () => {
  let h;
  h = harness({ fetchReply: path => { assert.equal(path, "/api/experiments/E-original"); return h.reply(inspection()); } });
  const raw = h.$("campaignAnalysisSettings").value;
  await h.ui.prepareCampaignConditions(true);
  assert.equal(h.ui.state.campaignConditions.error, "");
  assert.equal(h.sandbox.location.hash, "explore"); assert.equal(h.ui.campaignConditionsCurrent(), true);
  assert.equal(h.$("campaignAnalysisSource").value, "saved"); assert.equal(h.$("campaignAnalysisSettings").value, raw);
  assert.match(h.$("campaignConditionsSummary").textContent, /FZ=-217.25 N/); assert.match(h.$("campaignConditionsSummary").textContent, /NOT_CHECKED/);
  h.$("campaignAnalysisSettings").value = "USER DRAFT { invalid JSON";
  for (const type of ["doe", "optimization"]) {
    h.$("campaignType").value = type;
    const args = h.ui.campaignArguments(); assert.equal(args.conditions_id, "C-original"); assert.equal(args.analysis_backend, "fixture.calculix");
    assert.equal(Object.hasOwn(args, "analysis_settings"), false); assert.equal(args.engine, type === "doe" ? "scipy.latin_hypercube" : "scipy.differential_evolution");
  }
  assert.deepEqual(h.paths.map(item => item.path), ["/api/experiments/E-original"]);
  h.$("campaignAnalysisSource").value = "legacy"; h.$("campaignAnalysisSettings").value = raw;
  const legacy = h.ui.campaignArguments(); assert.equal(Object.hasOwn(legacy, "conditions_id"), false); assert.equal(legacy.analysis_settings.raw_user_draft, "KEEP THIS");
});

test("actual source workflow saves frozen plan, human-runs same campaign, reopens all children/conditions and prepares editable research without provider execution", async () => {
  let h, savedPlan, completed = false; const final = campaign();
  h = harness({ fetchReply: (path, options) => {
    if (path === "/api/experiments/E-original") return h.reply(inspection());
    if (path === "/api/overview") return h.reply(h.overview);
    if (path === "/api/campaigns/C-campaign") return h.reply(completed ? final : { type: "optimization", record: { status: "PLANNED", plan: savedPlan, evaluations: [] }, plan: savedPlan });
    if (path === "/api/experiments/A-C-campaign-0000") return h.reply(completedChild(final.record.evaluations[0]));
    assert.equal(path, "/api/jobs"); const body = JSON.parse(options.body);
    if (body.operation === "optimization_plan") {
      assert.equal(body.arguments.conditions_id, "C-original"); assert.equal(Object.hasOwn(body.arguments, "analysis_settings"), false);
      savedPlan = final.plan; return h.reply({ id: "J-plan", operation: body.operation, status: "COMPLETED", result: savedPlan });
    }
    assert.equal(body.operation, "optimization_run"); assert.deepEqual(body.arguments, { campaign_id: "C-campaign" });
    completed = true; return h.reply({ id: "J-run", operation: body.operation, status: "COMPLETED", result: final.record });
  } });
  await h.ui.prepareCampaignConditions(); await h.ui.submitCampaignPlan();
  assert(h.ui.state.selectedCampaign, `${h.$("noticeText").textContent}\n${JSON.stringify(h.paths.map(item => item.path))}`);
  assert.equal(h.ui.state.selectedCampaign.plan.analysis.conditions_template.reference.id, "C-original");
  assert.match(h.$("campaignDetail").textContent, /고정 조건 C-original/);
  const planned = h.ui.prepareCampaignResearch(h.ui.state.selectedCampaign, []);
  assert.equal(planned.intent, "RUN_SAVED_OPTIMIZATION"); assert.match(h.$("researchQuestion").value, /^작성 중인 가설 질문/);
  const run = h.all().find(node => Object.hasOwn(node.dataset, "campaignRun")); await click(run);
  assert.equal(completed, true); assert.equal(h.ui.state.selectedCampaign.record.status, "COMPLETED_REVIEW_REQUIRED");
  assert.match(h.$("campaignDetail").textContent, /A-C-campaign-0001/); assert.match(h.$("campaignDetail").textContent, /FX 0 \/ FY 0 \/ FZ -217.25 N/);
  const answerDraft = h.ui.prepareCampaignResearch(h.ui.state.selectedCampaign, [0, 1]);
  assert.equal(answerDraft.intent, "INTERPRET_SAVED_RESULTS"); assert.match(h.$("researchQuestion").value, /새 계산·최적화 실행 없이/);
  assert.equal((h.$("researchQuestion").value.match(/작성 중인 가설 질문/g) ?? []).length, 1);
  assert.equal(h.$("researchQuestion").value.includes("optimization_run({campaign_id"), false, "Replaced generated planned question must not request a rerun");
  const result = h.all().find(node => node.tagName === "BUTTON" && node.textContent === "A-C-campaign-0000"); await click(result);
  assert.equal(h.ui.state.selectedExperiment.result.provenance.analysis_conditions.id, "C-C-campaign-0000");
  assert.match(h.$("experimentDetail").textContent, /invalid_stress/); assert.match(h.$("experimentDetail").textContent, /signed_reaction/);
  assert.equal(h.paths.filter(item => item.options?.method === "POST").length, 2, "Only explicit human plan/run; handoffs issue no POST");
  assert.equal(h.paths.some(item => item.path.startsWith("/api/research") || item.path.includes("catalog")), false);
});

test("source preparation late success and errors cannot replace changed store/study/model/condition drafts", async () => {
  for (const change of [h => { h.ui.state.studyId = "S-other"; }, h => { h.ui.state.overview.active_store = "history"; },
    h => { h.$("cadModel").value = "other"; }, h => { h.$("conditionsFz").value = "-300"; },
    h => { h.$("campaignAnalysisSettings").value = "Changed raw campaign draft"; }, h => { h.$("campaignAnalysisSource").value = "saved"; },
    h => { h.ui.state.registry.entries[0].source_sha256 = sha("0"); }]) {
    for (const fail of [false, true]) {
      const pending = deferred(); const h = harness({ fetchReply: () => pending.promise });
      const prepare = h.ui.prepareCampaignConditions(true); change(h);
      const chosenSource = h.$("campaignAnalysisSource").value;
      assert.equal(h.paths.length, 1, h.$("campaignConditionsError").textContent);
      if (fail) pending.reject(new Error("LATE ERROR SHOULD STAY QUIET")); else pending.resolve(h.reply(inspection()));
      await prepare; assert.equal(h.ui.state.campaignConditions.selection, null); assert.equal(h.$("campaignAnalysisSource").value, chosenSource);
      assert.equal(h.$("campaignConditionsError").textContent.includes("LATE"), false); assert.equal(h.sandbox.location.hash, "simulation");
    }
  }
});

test("saved source withdrawal on unsupported/stale model blocks plan and keeps user raw drafts instead of silently falling back", async () => {
  let h; h = harness({ fetchReply: path => { assert.equal(path, "/api/experiments/E-original"); return h.reply(inspection()); } });
  await h.ui.prepareCampaignConditions();
  h.ui.state.analysisConditions.record.support.status = "UNSUPPORTED_FOR_CONDITIONS"; h.ui.updateControls();
  assert.equal(h.ui.state.campaignConditions.selection, null); assert.equal(h.$("campaignAnalysisSource").value, "saved");
  assert.equal(h.$("campaignPlanBtn").disabled, true); assert.throws(() => h.ui.campaignArguments());
  assert.equal(h.$("campaignAnalysisSettings").value, '{"raw_user_draft":"KEEP THIS"}'); assert.equal(h.paths.length, 1);
});

test("readonly, recovery and existing active job prevent condition connection and plan POST", async () => {
  for (const h of [harness({ writable: false }), harness()]) {
    if (h.ui.state.overview.stores[0].writable) h.ui.state.job = { status: "RUNNING" };
    h.ui.updateControls(); await h.ui.prepareCampaignConditions(); await h.ui.submitCampaignPlan();
    assert.equal(h.paths.length, 0); assert.equal(h.$("analysisConditionsExploreBtn").disabled, true);
  }
  const h = harness(); h.ui.state.overview.execution = { state: "RECOVERY_REQUIRED", accepting_jobs: false };
  h.ui.updateControls(); await h.ui.prepareCampaignConditions(); await h.ui.submitCampaignPlan(); assert.equal(h.paths.length, 0);
});

test("late plan completion and late errors preserve a changed campaign draft and do not inspect a stale campaign", async () => {
  for (const fail of [false, true]) {
    let h; const pending = deferred(); h = harness({ fetchReply: path => {
      if (path === "/api/experiments/E-original") return h.reply(inspection()); if (path === "/api/overview") return h.reply(h.overview);
      assert.equal(path, "/api/jobs"); return pending.promise;
    } });
    await h.ui.prepareCampaignConditions(); const task = h.ui.submitCampaignPlan();
    assert(h.paths.some(item => item.path === "/api/jobs"), h.$("noticeText").textContent);
    h.$("objectiveMetric").value = "edited while in flight";
    if (fail) pending.reject(new Error("LATE PLAN ERROR")); else pending.resolve(h.reply({ id: "J-plan", status: "COMPLETED", result: campaign().plan }));
    await task; assert.equal(h.$("objectiveMetric").value, "edited while in flight");
    assert.equal(h.ui.state.selectedCampaign, null); assert.equal(h.paths.some(item => item.path.startsWith("/api/campaigns/")), false);
    assert.equal(h.$("noticeText").textContent.includes("LATE"), false);
  }
});

test("campaign and candidate reads reject late success/error after store/study/navigation changes and verify result pins", async () => {
  for (const fail of [false, true]) {
    const pending = deferred(); let h; h = harness({ fetchReply: () => pending.promise });
    const task = h.ui.inspectCampaign("C-campaign"); h.ui.state.studyId = "S-other";
    if (fail) pending.reject(new Error("LATE CAMPAIGN ERROR")); else pending.resolve(h.reply(campaign()));
    await task; assert.equal(h.ui.state.selectedCampaign, null); assert.equal(h.$("campaignDetail").textContent.includes("LATE"), false);
  }
  let h; const final = campaign(); h = harness({ fetchReply: path => path.startsWith("/api/campaigns/") ? h.reply(final) : h.reply({ ...completedChild(final.record.evaluations[0]), hashes: { result_sha256: sha("0") } }) });
  await h.ui.inspectCampaign("C-campaign");
  const result = h.all().find(node => node.tagName === "BUTTON" && node.textContent === "A-C-campaign-0000"); await click(result);
  assert.equal(h.ui.state.selectedExperiment, null); assert.match(h.$("experimentDetail").textContent, /보존 결과 해시/);
  assert.match(h.$("noticeText").textContent, /보존 결과 해시/);
});

test("planned DOE has a human runner and no AI execution handoff; unexecuted child IDs are never result links", async () => {
  let h; const data = campaign("doe", false); data.plan.samples = [{ index: 0, values: { width: 38 }, cad_experiment_id: "E-planned", analysis_experiment_id: "A-planned" }];
  h = harness({ fetchReply: () => h.reply(data) }); await h.ui.inspectCampaign("C-campaign");
  assert.equal(h.all().some(node => node.tagName === "BUTTON" && node.textContent === "A-planned"), false);
  assert.match(h.$("campaignDetail").textContent, /DOE 실행은.*사람/);
  const question = h.all().find(node => Object.hasOwn(node.dataset, "campaignResearch")); assert.equal(question.disabled, true);
  assert.throws(() => h.ui.prepareCampaignResearch(h.ui.state.selectedCampaign, []));
});

test("malformed frozen support/settings blocks planned run and research handoff instead of substituting raw settings", async () => {
  for (const mutate of [d => { d.plan.analysis.settings.load.force_per_support_N = 150; },
    d => { d.plan.analysis.conditions_template.record.support.status = "UNSUPPORTED_FOR_CONDITIONS"; }]) {
    const data = campaign("optimization", false); mutate(data);
    let h; h = harness({ fetchReply: path => { assert.equal(path, "/api/campaigns/C-campaign"); return h.reply(data); } });
    await h.ui.inspectCampaign("C-campaign");
    const button = h.all().find(node => Object.hasOwn(node.dataset, "campaignRun")); assert.equal(button.disabled, true); await click(button);
    assert.equal(h.paths.length, 1); assert.match(h.$("campaignDetail").textContent, /고정 조건 확인 실패/);
    assert.throws(() => h.ui.prepareCampaignResearch(h.ui.state.selectedCampaign, []));
    assert.equal(h.$("researchQuestion").value, "작성 중인 가설 질문");
  }
});

test("enabled shared controls refresh overview without any condition/catalogue/provider GET", async () => {
  let h; h = harness({ fetchReply: path => { assert.equal(path, "/api/overview"); return h.reply(h.overview); } });
  h.$("campaignAnalysisSource").value = "saved"; await h.ui.loadOverview();
  assert.deepEqual(h.paths.map(item => item.path), ["/api/overview"]);
  assert.equal(h.$("campaignPlanBtn").disabled, true); assert.equal(h.$("campaignAnalysisSettings").value, '{"raw_user_draft":"KEEP THIS"}');
});

test("owned async plan job uses existing polling and late completion cannot replace an edited human plan", async () => {
  let h; h = harness({ fetchReply: path => {
    if (path === "/api/experiments/E-original") return h.reply(inspection());
    if (path === "/api/jobs") return h.reply({ id: "J-async-plan", operation: "optimization_plan", status: "RUNNING" });
    if (path === "/api/jobs/J-async-plan") return h.reply({ id: "J-async-plan", operation: "optimization_plan", status: "COMPLETED", result: campaign().plan });
    assert.equal(path, "/api/overview"); return h.reply(h.overview);
  } });
  await h.ui.prepareCampaignConditions(); await h.ui.submitCampaignPlan();
  assert.equal(h.ui.state.job.status, "RUNNING"); assert.equal(h.ui.state.handlers.size, 1);
  h.$("optimizationConstraints").value = '[{"source":"analysis","metric":"test","unit":"N","operator":">=","limit":-20,"scale":20}]';
  await h.ui.pollJob(); assert.equal(h.ui.state.job.status, "COMPLETED"); assert.equal(h.ui.state.handlers.size, 0);
  assert.equal(h.ui.state.selectedCampaign, null); assert.equal(h.paths.some(item => item.path.startsWith("/api/campaigns/")), false);
  assert.match(h.$("optimizationConstraints").value, /"limit":-20/);
});

test("late candidate success/error after a new campaign or study cannot render or notify a different record", async () => {
  for (const fail of [false, true]) {
    const pending = deferred(); let h; const data = campaign(); h = harness({ fetchReply: path => path.startsWith("/api/campaigns/") ? h.reply(data) : pending.promise });
    await h.ui.inspectCampaign("C-campaign");
    const button = h.all().find(node => node.tagName === "BUTTON" && node.textContent === "A-C-campaign-0000"); await click(button);
    assert(h.paths.some(item => item.path === "/api/experiments/A-C-campaign-0000"));
    h.ui.state.studyId = "S-other"; h.$("experimentDetail").textContent = "NEW USER RECORD";
    if (fail) pending.reject(new Error("LATE CHILD ERROR")); else pending.resolve(h.reply(completedChild(data.record.evaluations[0])));
    await new Promise(resolve => setImmediate(resolve)); await new Promise(resolve => setImmediate(resolve));
    assert.equal(h.ui.state.selectedExperiment, null); assert.equal(h.$("experimentDetail").textContent, "NEW USER RECORD");
    assert.equal(h.$("noticeText").textContent.includes("LATE CHILD"), false);
  }
});
