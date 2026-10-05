"use strict";

// UNSOLVED display-only fixtures. The VM evaluates actual app renderer/control
// definitions, stops before listener registration/boot, and forbids HTTP/timers.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const vm = require("node:vm");
const presentation = require("../apps/lab/static/result-presentation.js");
const cadControls = require("../apps/lab/static/cad-controls.js");
const researchControls = require("../apps/lab/static/research-controls.js");
const fixtureControls = require("../apps/lab/static/fixture-controls.js");
const appSource = readFileSync(require.resolve("../apps/lab/static/app.js"), "utf8");
const htmlSource = readFileSync(require.resolve("../apps/lab/static/index.html"), "utf8");
const bootBoundary = '$(' + '"jobCancelBtn").addEventListener("click", async () => {';
const split = appSource.indexOf(bootBoundary);
assert(split > 0, "Actual listener/boot boundary must be found, never evaluate application boot");

class TinyNode {
  constructor(tag = "div") {
    this.tagName = tag.toUpperCase(); this.children = []; this.attributes = {}; this.dataset = {};
    this.style = {}; this.className = ""; this.value = ""; this.hidden = false; this.disabled = false;
    this.open = false; this.checked = false; this.listeners = new Map(); this._text = "";
    this.classList = {
      add: (...values) => { this.className = [...new Set([...this.className.split(/\s+/).filter(Boolean), ...values])].join(" "); },
      contains: value => this.className.split(/\s+/).includes(value),
      toggle: (value, enabled) => {
        const active = enabled ?? !this.classList.contains(value);
        this.className = this.className.split(/\s+/).filter(item => item && item !== value).join(" ");
        if (active) this.classList.add(value); return active;
      },
    };
  }
  set textContent(value) { this.children = []; this._text = String(value ?? ""); }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
  set innerHTML(_value) { throw new Error("Untrusted display must use textContent, never HTML"); }
  append(...items) {
    for (const item of items) { const child = item instanceof TinyNode ? item : new TinyNode("#text");
      if (!(item instanceof TinyNode)) child.textContent = String(item); child.parentNode = this; this.children.push(child); }
  }
  replaceChildren(...items) { this._text = ""; this.children = []; this.append(...items); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  addEventListener(name, callback) { this.listeners.set(name, callback); }
  querySelector(selector) { return walk(this).slice(1).find(node => selector.startsWith(".") ? node.classList.contains(selector.slice(1)) : node.tagName === selector.toUpperCase()) ?? null; }
  remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter(child => child !== this); }
}
function walk(node) { return [node, ...node.children.flatMap(walk)]; }
function freeze(value) {
  if (value && typeof value === "object") { Object.values(value).forEach(freeze); Object.freeze(value); }
  return value;
}
function result(backend = "fixture.assembly", changes = {}) {
  return { experiment_id: "E-display-only", status: "COMPLETED_REVIEW_REQUIRED", solver_status: "NOT_RUN",
    cad_revision: "a".repeat(64), decision: "NOT_RELEASED", provenance: { adapter: backend },
    metrics: { diagnostic: { value: -0, valid: false, unit: "mm", reason: "표시 fixture: 검증 안 함" } },
    input_parameters: {}, validations: [{ type: "static_strength", status: "UNKNOWN", blocking: true }],
    evidence: [], artifacts: [], ...changes };
}
function harness({ writable = true, callable = true, selectedPreset = "linear" } = {}) {
  const ids = new Map(), selectors = new Map(), calls = [], prohibited = { http: 0, timers: 0 };
  const $ = id => { if (!ids.has(id)) ids.set(id, new TinyNode()); return ids.get(id); };
  $("simulationPreset").value = selectedPreset; $("cadBackend").value = "fixture.assembly";
  $("cadModel").value = "bending_assembly"; $("campaignTarget").value = "cad";
  const indicator = new TinyNode("span"); indicator.className = "job-indicator"; $("jobPanel").append(indicator);
  // Bind the actual declared buttons to their IDs, including analysis_run.
  // This is a limited DOM model, not a live layout/browser qualification.
  const operationNodes = [];
  for (const tag of htmlSource.matchAll(/<button\b[^>]*>/g)) {
    const operation = /\bdata-operation="([^"]+)"/.exec(tag[0])?.[1]; if (!operation) continue;
    const id = /\bid="([^"]+)"/.exec(tag[0])?.[1], node = id ? $(id) : new TinyNode("button");
    node.dataset.operation = operation; operationNodes.push(node); selectors.set(`[data-operation="${operation}"]`, node);
  }
  assert(operationNodes.includes($("simulationRunBtn")), "The real analysis button must participate in existing operation gates");
  const writeFields = [new TinyNode("fieldset")], readFields = [new TinyNode("fieldset")];
  const document = { getElementById: $, createElement: tag => new TinyNode(tag), querySelectorAll: selector =>
    selector === "[data-operation]" ? operationNodes : selector === "fieldset[data-write]" ? writeFields : selector === "fieldset[data-read-job]" ? readFields : [],
    querySelector: selector => {
      if (!selector.startsWith("[data-operation=")) return null;
      if (!selectors.has(selector)) selectors.set(selector, new TinyNode("button")); return selectors.get(selector);
    } };
  const sandbox = { document, Node: TinyNode, window: { cadControls, researchControls, fixtureControls,
    resultPresentation: { ...presentation, workflow: (value, context) => { calls.push({ value, context }); return presentation.workflow(value, context); } } },
    location: { hash: "#results" }, TextEncoder, URL, URLSearchParams, Intl, console,
    fetch: () => { prohibited.http++; throw new Error("HTTP is forbidden in the display gate"); },
    setTimeout: () => { prohibited.timers++; throw new Error("Application timers are forbidden in the display gate"); }, clearTimeout: () => {} };
  vm.createContext(sandbox);
  vm.runInContext(appSource.slice(0, split) + "\nglobalThis.appUnderTest = {state, workflowContext, renderExperimentList, renderExperimentDetail, renderJob, updateControls, activeJob, researchPurpose, prepareResearchPurpose, simulationArguments, clearSimulationDraft, simulationSubmissionContext, completeSimulation, renderComparison};", sandbox, { filename: require.resolve("../apps/lab/static/app.js") });
  const app = sandbox.appUnderTest;
  app.state.presets = { linear: { operation: "analysis_run", backend: "fixture.calculix", parent_backends: ["fixture.cadquery"] } };
  app.state.overview = { active_store: "display", stores: [{ id: "display", writable }], experiments: [],
    capabilities: [{ operation: "analysis_run", callable }] };
  app.state.studyId = "S-display";
  return { app, $, document, calls, indicator, prohibited };
}

test("research-purpose drafts keep user observations and send no provider or simulation request", () => {
  const h = harness(), observations = "실측 0.21 mm, 출처: 시험 A. H1과 H2는 아직 미확인.";
  h.$("researchQuestion").value = observations; h.$("studyHypothesis").value = "사용자가 작성한 가설";
  h.app.prepareResearchPurpose("defect");
  assert.equal(h.$("researchQuestion").value, observations);
  assert.equal(h.$("studyHypothesis").value, "사용자가 작성한 가설");
  assert.match(h.$("studyQuestion").value, /불량의 위치·형태.*\[입력\]/);
  assert.match(h.$("studyObjective").value, /다음 구별 시험/);
  assert.deepEqual(h.prohibited, { http: 0, timers: 0 });
  const jig = harness(); jig.app.prepareResearchPurpose("jig");
  assert.match(jig.$("researchQuestion").value, /장비의 하중\/스트로크/);
  assert.match(jig.$("studyObjective").value, /지그와 시험체의 변형/);
  assert.deepEqual(jig.prohibited, { http: 0, timers: 0 });
  jig.$("studyObjective").value = "사용자 기준: 지그 처짐 0.05 mm 이내. 아직 측정하지 않음.";
  jig.app.prepareResearchPurpose("defect");
  assert.match(jig.$("researchQuestion").value, /불량의 위치·형태/);
  assert.equal(jig.$("studyObjective").value, "사용자 기준: 지그 처짐 0.05 mm 이내. 아직 측정하지 않음.");
});

test("actual comparison translates response names without changing invalid metrics or conflating loaded UZ with whole-field U", () => {
  const h = harness(), data = freeze([{ experiment_id: "E-100", status: "COMPLETED_REVIEW_REQUIRED", decision: "NOT_RELEASED",
    parameters: {}, unknown: ["static_strength"], metrics: { max_displacement: { value: 0.00002, unit: "mm", valid: true },
      peak_stress: { value: 0.4, unit: "MPa", valid: false, reason: "허용 강도 미확인" } } }]);
  const original = JSON.stringify(data); h.app.renderComparison(data);
  const text = h.$("comparisonDetail").textContent;
  assert.match(text, /저장된 최대 변위 응답/); assert.match(text, /절점 평균 응력/);
  assert.match(text, /전체 변위장 최대 \|U\|와 하중부 \|UZ\|는 다른 응답/);
  assert.match(text, /판단에 사용할 수 없음/); assert.match(text, /허용 강도 미확인/);
  assert.equal(JSON.stringify(data), original); assert.deepEqual(h.prohibited, { http: 0, timers: 0 });
});

test("draft submission keeps the source CAD and single mesh while changing one load", () => {
  const h = harness();
  const settings = { load: { force_per_support_N: 150, source: "Virtual load case, not measured" },
    material: { model: "isotropic", elastic_modulus_MPa: 210000, poisson_ratio: 0.3, provenance: "Illustrative", qualification: "ASSUMED_NOT_MEASURED" },
    mesh: { mode: "selected", max_sizes_mm: [4] } };
  h.app.state.overview.experiments = [{ id: "E-cad-source", study_id: "S-display", backend: "fixture.cadquery", status: "COMPLETED_REVIEW_REQUIRED", solver_status: "NOT_RUN", cad_revision: "a".repeat(64) }];
  h.$("analysisParent").value = "E-cad-source"; h.$("simulationId").value = "E-new-load";
  h.$("simulationSettings").value = JSON.stringify(settings); h.$("importedMeshFields").hidden = true;
  h.app.state.simulationDraft = { store: "display", operation: "analysis_run", arguments: {}, source: {
    experimentId: "E-original", studyId: "S-display", backend: "fixture.calculix", parentExperimentId: "E-cad-source" } };
  const args = h.app.simulationArguments();
  assert.equal(args.parent_experiment_id, "E-cad-source"); assert.equal(args.experiment_id, "E-new-load");
  assert.equal(JSON.stringify(args.settings), JSON.stringify(settings));
  h.$("simulationId").value = "E-original"; assert.throws(() => h.app.simulationArguments(), /새 실험/);
  h.$("simulationId").value = "E-new-load"; h.app.state.studyId = "S-other";
  assert.throws(() => h.app.simulationArguments(), /연결이 달라졌습니다/);
  h.app.clearSimulationDraft();
  assert.throws(() => h.app.simulationArguments(), /현재 연구에 연결된 CAD/);
  h.app.state.studyId = "S-display"; h.app.state.storeSwitching = true;
  assert.throws(() => h.app.simulationArguments(), /저장소 전환/);
  h.app.updateControls(); assert.equal(h.$("simulationRunBtn").disabled, true);
  assert.deepEqual(h.prohibited, { http: 0, timers: 0 });
});

test("simulation completion keeps the submitted source and ignores a changed study or store", async () => {
  const h = harness(); h.app.state.simulationDraft = { source: { experimentId: "E-original" } };
  const submitted = h.app.simulationSubmissionContext();
  h.app.state.simulationDraft.source.experimentId = "E-other-draft";
  assert.equal(submitted.source, "E-original");
  h.app.state.studyId = "S-changed";
  await h.app.completeSimulation({ experiment_id: "E-new" }, { experiment_id: "E-new" }, submitted);
  assert.equal(h.app.state.comparison.size, 0);
  h.app.state.studyId = submitted.studyId; h.app.state.overview.active_store = "other";
  await h.app.completeSimulation({ experiment_id: "E-new" }, { experiment_id: "E-new" }, submitted);
  assert.equal(h.app.state.comparison.size, 0);
  assert.deepEqual(h.prohibited, { http: 0, timers: 0 });
});

test("Node and browser workflow exports agree without a browser service or a test-only admission path", () => {
  const source = readFileSync(require.resolve("../apps/lab/static/result-presentation.js"), "utf8"), browser = { window: {} };
  vm.runInNewContext(source, browser);
  assert.deepEqual(Object.keys(browser.window.resultPresentation).sort(), Object.keys(presentation).sort());
  const record = freeze(result()), before = JSON.stringify(record);
  assert.equal(JSON.stringify(browser.window.resultPresentation.workflow(record)), JSON.stringify(presentation.workflow(record)));
  assert.equal(JSON.stringify(record), before);
});

test("actual experiment list renderer reuses workflow and preserves raw status, release and integrity", () => {
  const h = harness(), assembly = result(), support = result("fixture.cadquery"), failed = result("fixture.cadquery", { status: "REJECTED" });
  const variants = [assembly, support, failed, result("fixture.cadquery", { status: "FAILED" }),
    result("fixture.cadquery", { status: "FAILED_EXECUTION" }), result("fixture.cadquery", { status: "FUTURE_CODE" }), result("fixture.cadquery", { status: undefined })];
  const rows = variants.map((item, i) => ({ id: `E-display-${i}`, study_id: "S-display",
    status: item.status, solver_status: item.solver_status, backend: item.provenance.adapter,
    cad_revision: item.cad_revision, decision: item.decision, integrity: "NOT_CHECKED" }));
  h.app.state.overview.experiments = freeze(rows); const before = JSON.stringify(rows);
  h.app.renderExperimentList();
  assert.equal(h.calls.length, rows.length);
  const bodyRows = walk(h.$("experimentList")).filter(node => node.tagName === "TBODY")[0].children;
  assert.equal(bodyRows[0].children[3].children[0].children[0].textContent, "모델 준비됨 · 해석 안 함");
  assert.match(bodyRows[0].children[3].textContent, /해석 기능은 아직 준비되지 않았습니다/);
  assert.match(bodyRows[1].children[3].textContent, /기록·원본 일치를 먼저/);
  assert.match(bodyRows[2].children[3].textContent, /조건 미충족.*미충족 검사/);
  for (let i = 0; i < rows.length; i++) {
    const progress = bodyRows[i].children[3].children[0], status = progress.children[0];
    const expected = presentation.workflow(rows[i], h.calls[i].context).stage;
    assert.equal(status.classList.contains("badge"), true); assert.equal(status.textContent, expected);
    assert.equal(status.dataset.status, rows[i].status ?? "UNKNOWN"); assert.equal(status.title, rows[i].status ?? "UNKNOWN");
    assert.equal(progress.textContent.split(expected).length - 1, 1, "Exactly one primary stage caption");
    assert.doesNotMatch(progress.textContent, /완료\s*·\s*검토\s*필요/);
    if (["REJECTED", "FAILED", "FAILED_EXECUTION"].includes(rows[i].status)) assert.equal(status.classList.contains("fail"), true);
    if (i >= 5) assert.equal(status.textContent, "현재 단계 미확인");
    const badges = walk(bodyRows[i]).filter(node => node.classList.contains("badge"));
    assert(badges.some(node => node.dataset.status === (rows[i].status ?? "UNKNOWN")));
    assert(badges.some(node => node.dataset.status === "NOT_RELEASED"));
    assert(badges.some(node => node.dataset.status === "NOT_CHECKED"));
  }
  assert.equal(JSON.stringify(rows), before); assert.deepEqual(h.prohibited, { http: 0, timers: 0 });
});

test("actual result header explains CAD-only block and keeps invalid metrics and UNKNOWN raw details", () => {
  const h = harness(), inspection = freeze({ result: result(), integrity: "VERIFIED", registry_snapshot: { entries: [] } });
  const before = JSON.stringify(inspection); h.app.state.selectedExperiment = inspection;
  h.app.renderExperimentDetail(inspection);
  const header = h.$("experimentDetail").children[0];
  assert.match(header.textContent, /모델 준비됨 · 해석 안 함/); assert.match(header.textContent, /해석 기능은 아직 준비되지 않았습니다/);
  const stage = walk(header).find(node => node.classList.contains("badge") && node.dataset.status === "COMPLETED_REVIEW_REQUIRED");
  assert(stage); assert.equal(stage.textContent, "모델 준비됨 · 해석 안 함"); assert.equal(stage.title, "COMPLETED_REVIEW_REQUIRED");
  assert.equal(header.textContent.split(stage.textContent).length - 1, 1, "No duplicate stage paragraph");
  assert.doesNotMatch(header.textContent, /완료\s*·\s*검토\s*필요/);
  assert.equal(h.calls.length, 1); assert.equal(h.calls[0].context.eligibleParent, false);
  assert.equal(h.$("analysisParent").value, ""); assert.equal(h.$("simulationRunBtn").disabled, true);
  const displayed = h.$("experimentDetail").textContent;
  assert.match(displayed, /판단에 사용할 수 없는 값/); assert.match(displayed, /정적 강도/);
  const original = walk(h.$("experimentDetail")).find(node => node.tagName === "PRE" && node.textContent.includes('"solver_status"'));
  assert(original); assert.match(original.textContent, /NOT_RUN/); assert.match(original.textContent, /NOT_RELEASED/); assert.match(original.textContent, /UNKNOWN/);
  assert(Object.is(inspection.result.metrics.diagnostic.value, -0)); assert.equal(JSON.stringify(inspection), before);
  assert.equal(h.$("resultBrowser").open, false); assert.deepEqual(h.prohibited, { http: 0, timers: 0 });
  for (const status of ["REJECTED", "FAILED", "FAILED_EXECUTION", "FUTURE_CODE", undefined]) {
    const varied = freeze({ result: result("fixture.assembly", { status }), integrity: "VERIFIED" }), variedBefore = JSON.stringify(varied);
    h.app.state.selectedExperiment = varied; h.app.renderExperimentDetail(varied);
    const primary = h.$("experimentDetail").children[0], rawCode = status ?? "UNKNOWN";
    const label = walk(primary).find(node => node.classList.contains("badge") && node.dataset.status === rawCode);
    assert(label); assert.equal(label.title, rawCode);
    assert.equal(label.textContent, presentation.workflow(varied.result, h.calls.at(-1).context).stage);
    assert.doesNotMatch(primary.textContent, /완료\s*·\s*검토\s*필요/);
    if (["REJECTED", "FAILED", "FAILED_EXECUTION"].includes(status)) assert.equal(label.classList.contains("fail"), true);
    else assert.equal(label.textContent, "현재 단계 미확인");
    assert.equal(JSON.stringify(varied), variedBefore);
  }
  assert.equal(h.calls.length, 6); assert.deepEqual(h.prohibited, { http: 0, timers: 0 });
});

test("actual header and unchanged controls distinguish eligible support, read-only, busy and unavailable states", () => {
  for (const [options, job, next] of [[{}, null, /재료·하중·메시.*새 실험을 실행/],
    [{ writable: false }, null, /읽기 전용/], [{}, { status: "CLEANUP_PENDING" }, /종료를 먼저 확인/],
    [{ callable: false }, null, /현재 실행할 수 없습니다/], [{ selectedPreset: "missing" }, null, /호환되는 부모 모델/]]) {
    const h = harness(options), inspection = freeze({ result: result("fixture.cadquery"), integrity: "VERIFIED" });
    h.app.state.job = job; h.app.state.selectedExperiment = inspection; h.app.renderExperimentDetail(inspection);
    assert.match(h.$("experimentDetail").children[0].textContent, next);
    if (options.writable === false || job || options.callable === false || options.selectedPreset === "missing") assert.equal(h.$("simulationRunBtn").disabled, true);
    else { assert.equal(h.$("analysisParent").value, inspection.result.experiment_id); assert.equal(h.$("simulationRunBtn").disabled, false); }
    assert.deepEqual(h.prohibited, { http: 0, timers: 0 });
  }
});

test("COMPLETED job with rejected/failed Core result renders failure red while retaining service codes and raw bytes", () => {
  const h = harness();
  for (const status of ["REJECTED", "FAILED", "FAILED_EXECUTION"]) {
    const job = freeze({ id: "J-display", status: "COMPLETED", operation: "analysis_run", result: result("fixture.calculix", { status }) });
    const before = JSON.stringify(job); h.app.state.job = job; h.app.renderJob();
    assert.equal(h.$("jobPanel").classList.contains("failed"), true); assert.equal(h.$("jobPanel").classList.contains("finished"), false);
    assert.equal(h.$("jobStatus").classList.contains("fail"), true);
    assert.match(h.$("jobStatus").textContent, status === "REJECTED" ? /조건 미충족/ : /실행 실패/);
    assert.equal(h.$("jobStatus").dataset.status, "COMPLETED"); assert.equal(h.$("jobStatus").title, "COMPLETED");
    assert.equal(h.$("jobJson").textContent, JSON.stringify(job, null, 2)); assert.equal(JSON.stringify(job), before);
    assert.equal(h.indicator.style.animation, "none"); assert.equal(h.$("jobCancelBtn").hidden, true);
  }
  assert.equal(h.calls.length, 3); assert.deepEqual(h.prohibited, { http: 0, timers: 0 });
});

test("terminal CAD, solver and missing-result jobs stop animation without a blanket completed/released message", () => {
  const h = harness();
  const cases = [[result(), "모델 준비됨 · 해석 안 함"],
    [result("fixture.calculix", { solver_status: "COMPLETED", decision: "UNKNOWN" }), "해석 실행됨 · 결과 검토 필요"],
    [undefined, "현재 단계 미확인"], [{ status: "FUTURE_STATE" }, "현재 단계 미확인"]];
  for (const [payload, caption] of cases) {
    const job = freeze({ status: "COMPLETED", operation: "cad_run", result: payload });
    h.app.state.job = job; h.app.renderJob();
    assert.equal(h.$("jobStatus").textContent, caption); assert.equal(h.$("jobPanel").classList.contains("finished"), false);
    assert.equal(h.$("jobPanel").classList.contains("failed"), false); assert.equal(h.indicator.style.animation, "none");
    assert.doesNotMatch(h.$("jobMessage").textContent, /연구 완료|작업이 끝났습니다/);
    assert.equal(h.$("jobStatus").dataset.status, "COMPLETED");
  }
  assert.deepEqual(h.prohibited, { http: 0, timers: 0 });
});

test("metadata jobs show the named saved/read step and reject missing evidence even after service completion", () => {
  const h = harness({ writable: false });
  for (const [operation, payload, caption] of [["doe_plan", { campaign_id: "C-display", status: "PLANNED" }, "수치 탐색 계획 저장됨"],
    ["parameter_discover", [], "발견된 변수 없음"], ["study_create", {}, "현재 단계 미확인"]]) {
    h.app.state.job = freeze({ status: "COMPLETED", operation, result: payload }); h.app.renderJob();
    assert.equal(h.$("jobStatus").textContent, caption);
    assert.equal(h.$("jobPanel").classList.contains("finished"), caption !== "현재 단계 미확인");
    assert.equal(h.$("jobCancelBtn").hidden, true); assert.equal(h.$("simulationRunBtn").disabled, true);
    assert.doesNotMatch(h.$("jobMessage").textContent, /연구 완료|해석 완료/);
  }
  assert.deepEqual(h.prohibited, { http: 0, timers: 0 });
});

test("actual cancel/cleanup button and busy guards survive stage rendering with positive payload present", () => {
  const h = harness();
  for (const [status, hidden, disabled, label] of [["RUNNING", false, false, "작업 취소"], ["CANCEL_REQUESTED", false, true, "작업 취소"],
    ["CLEANUP_PENDING", false, false, "종료 재시도"], ["CANCELLED", true, false, "작업 취소"], ["FAILED", true, false, "작업 취소"]]) {
    const job = freeze({ status, operation: "cad_run", result: result() }); h.app.state.job = job; h.app.renderJob();
    assert.equal(h.$("jobCancelBtn").hidden, hidden); assert.equal(h.$("jobCancelBtn").disabled, disabled);
    assert.equal(h.$("jobCancelBtn").textContent, label); assert.equal(h.$("jobStatus").dataset.status, status);
    assert.equal(h.indicator.style.animation, hidden ? "none" : "");
    if (!hidden) { assert.equal(h.$("storeSelect").disabled, true); assert.equal(h.$("simulationRunBtn").disabled, true); }
  }
  assert.deepEqual(h.prohibited, { http: 0, timers: 0 });
});

test("untrusted labels/errors stay literal text or raw detail and never become HTML or guessed stage guidance", () => {
  const h = harness(), hostile = '<img src=x onerror="throw new Error()">' + "f".repeat(64);
  h.app.state.job = freeze({ status: "COMPLETED", operation: hostile, result: { status: hostile }, error: hostile });
  h.app.renderJob(); assert.equal(h.$("jobTitle").textContent, "작업 상태"); assert.equal(h.$("jobStatus").textContent, "현재 단계 미확인");
  assert.doesNotMatch(h.$("jobMessage").textContent, /<img|ffff/); assert(h.$("jobJson").textContent.includes(hostile.replaceAll('"', '\\"')));
  const data = freeze({ result: result("fixture.assembly", { metrics: { hostile: { value: -2, unit: "mm", valid: false, reason: hostile } } }), integrity: "VERIFIED" });
  h.app.state.selectedExperiment = data; h.app.renderExperimentDetail(data);
  assert(walk(h.$("experimentDetail")).some(node => node.classList.contains("metric-reason") && node.textContent === hostile));
  assert(!walk(h.$("experimentDetail")).some(node => node.tagName === "IMG" || node.tagName === "SCRIPT"));
  assert.deepEqual(h.prohibited, { http: 0, timers: 0 });
});
