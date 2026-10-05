"use strict";

// Synthetic UI contracts only: no browser, live HTTP, AI, CAD or solver.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const vm = require("node:vm");
const controls = require("../apps/lab/static/research-controls.js");
const presentation = require("../apps/lab/static/result-presentation.js");
const cadControls = require("../apps/lab/static/cad-controls.js");
const appSource = readFileSync(require.resolve("../apps/lab/static/app.js"), "utf8");
const htmlSource = readFileSync(require.resolve("../apps/lab/static/index.html"), "utf8");
const boundary = appSource.indexOf('$("jobCancelBtn").addEventListener("click", async () => {');
assert(boundary > 0, "Stop before actual event listeners and boot");
const QUESTION = "  지지부 조건을 바꾸면 결과가 어떻게 달라져요? 🧪\n";
function status(changes = {}) {
  return { configured: true, available: true, state: "READY", model: controls.MODEL, profile: "FixtureScalar",
    workspace_url: "http://127.0.0.1:4098/owned-project", capabilities: [{ backend: "fixture.cadquery", operations: ["cad_run"] }], ...changes };
}
function result(changes = {}) {
  return { kind: "openscience_research", status: "COMPLETED", session_id: "ses_Actual123", model: controls.MODEL,
    profile: "FixtureScalar", workspace_url: status().workspace_url, question: QUESTION, answer: "실제 반환 텍스트 fixture입니다.",
    tools: [{ tool: "caelab.cad_run", status: "COMPLETED_REVIEW_REQUIRED", experiment_id: "E-synthetic" },
      { tool: "caelab.analysis_run", status: "FAILED_EXECUTION", experiment_id: "E-failed" },
      { tool: "caelab.experiment_inspect", status: "UNKNOWN" }], source_commit: "a".repeat(40),
    completion_is_engineering_approval: false, decision: "NOT_RELEASED", ...changes };
}
function job(changes = {}) { return { id: "J-synthetic", operation: "research_run", store_id: "local", status: "COMPLETED", result: result(), ...changes }; }
class TinyNode {
  constructor(tag = "div") {
    this.tagName = tag.toUpperCase(); this.children = []; this.attributes = {}; this.dataset = {}; this.style = {};
    this.className = ""; this.value = ""; this.hidden = false; this.disabled = false; this.checked = false; this._text = "";
    this.classList = { contains: value => this.className.split(/\s+/).includes(value),
      add: (...values) => { this.className = [...new Set([...this.className.split(/\s+/).filter(Boolean), ...values])].join(" "); },
      remove: (...values) => { this.className = this.className.split(/\s+/).filter(value => !values.includes(value)).join(" "); },
      toggle: (value, enabled) => { const active = enabled ?? !this.classList.contains(value); this.classList.remove(value); if (active) this.classList.add(value); return active; } };
  }
  set textContent(value) { this._text = String(value ?? ""); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
  set innerHTML(_value) { throw new Error("Untrusted prose must never be HTML"); }
  append(...items) { for (const item of items) { const child = item instanceof TinyNode ? item : new TinyNode("#text"); if (!(item instanceof TinyNode)) child.textContent = item; this.children.push(child); } }
  replaceChildren(...items) { this._text = ""; this.children = []; this.append(...items); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  addEventListener(name, callback) { (this.listeners ??= new Map()).set(name, callback); }
  querySelector(selector) { return walk(this).slice(1).find(node => selector.startsWith(".") ? node.classList.contains(selector.slice(1)) : node.tagName === selector.toUpperCase()) ?? null; }
}
function walk(node) { return [node, ...node.children.flatMap(walk)]; }
function harness({ writable = true, store = "local", researchStatus = status(), fetchReply } = {}) {
  const ids = new Map(), operations = [], paths = [], timers = [];
  const $ = id => { if (!ids.has(id)) ids.set(id, new TinyNode()); return ids.get(id); };
  for (const tag of htmlSource.matchAll(/<button\b[^>]*>/g)) {
    const operation = /\bdata-operation="([^"]+)"/.exec(tag[0])?.[1]; if (!operation) continue;
    const id = /\bid="([^"]+)"/.exec(tag[0])?.[1]; const node = id ? $(id) : new TinyNode("button"); node.dataset.operation = operation; operations.push(node);
  }
  $("cadBackend").value = "fixture.cadquery"; $("cadModel").value = "roller_support";
  $("simulationPreset").value = "linear"; $("campaignTarget").value = "cad"; $("researchQuestion").value = QUESTION;
  $("fixtureConditionFields").hidden = true; $("importedMeshFields").hidden = true;
  const indicator = new TinyNode("span"); indicator.className = "job-indicator"; $("jobPanel").append(indicator);
  const document = { getElementById: $, createElement: tag => new TinyNode(tag), querySelectorAll: selector => selector === "[data-operation]" ? operations : [],
    querySelector: selector => operations.find(node => selector === `[data-operation="${node.dataset.operation}"]`) ?? null };
  const sandbox = { document, Node: TinyNode, window: { researchControls: controls, resultPresentation: presentation, cadControls },
    location: { hash: "research" }, TextEncoder, URL, URLSearchParams, Intl, console,
    fetch: async (path, options) => { paths.push({ path, options }); assert(fetchReply, "No uncontrolled HTTP is allowed"); return fetchReply(path, options); },
    setTimeout: (fn, delay) => { timers.push({ fn, delay }); return timers.length; }, clearTimeout: () => {} };
  vm.createContext(sandbox);
  vm.runInContext(appSource.slice(0, boundary) + "\nglobalThis.ui = {state, updateControls, updateResearchControls, confirmedResearchSession, renderResearchConnection, loadResearchStatus, loadOverview, renderResearchAnswers, retainResearchJob, renderJob, submitResearchQuestion, runJob, pollJob, researchError};", sandbox);
  const ui = sandbox.ui;
  ui.state.overview = { active_store: store, stores: [{ id: store, writable }], token: "synthetic-token", capabilities: [], jobs: [] };
  ui.state.presets = { linear: { operation: "analysis_run", backend: "fixture.calculix", parent_backends: ["fixture.cadquery"] } };
  ui.state.researchStatus = researchStatus;
  return { ui, $, paths, timers, sandbox };
}
function reply(value, ok = true) { return { ok, status: ok ? 200 : 503, json: async () => value }; }

test("CommonJS/browser pure exports agree; no model selector or fallback", () => {
  const browser = { window: {}, URL, TextEncoder };
  vm.runInNewContext(readFileSync(require.resolve("../apps/lab/static/research-controls.js"), "utf8"), browser);
  assert.deepEqual(Object.keys(browser.window.researchControls), Object.keys(controls));
  assert.equal(JSON.stringify(browser.window.researchControls.request(QUESTION)), JSON.stringify(controls.request(QUESTION)));
  assert.equal(controls.MODEL, "openai-codex/gpt-5.6-sol");
  assert.doesNotMatch(htmlSource, /<select[^>]*researchModel|gpt-6|gpt-5\.6-luna|<textarea[^>]*id="researchQuestion"[^>]*>[^<]+/);
});
test("request keeps all original whitespace/unicode and only question/session keys", () => {
  assert.deepEqual(controls.request(QUESTION), { question: QUESTION });
  assert.deepEqual(controls.request(QUESTION, "ses_Confirmed42"), { question: QUESTION, session_id: "ses_Confirmed42" });
  assert.deepEqual(controls.request(QUESTION, null), { question: QUESTION });
  assert.equal(controls.request("가".repeat(5461) + "a").question.length, 5462);
});
test("question is bounded by actual UTF8 bytes; malformed text/session refuses", () => {
  assert.equal(new TextEncoder().encode(controls.request("a".repeat(16384)).question).length, 16384);
  for (const invalid of ["a".repeat(16385), "가".repeat(5462), "  \n", "\ud800", "x\udc00", false, null]) assert.throws(() => controls.request(invalid));
  for (const session of ["ses_", "ses_a-b", "../session", "ses_a\n", true, {}, "foreign"]) assert.throws(() => controls.request(QUESTION, session));
});
test("approved model/verified loopback/profile/capability required before asking", () => {
  const context = { local: true, writable: true, busy: false };
  assert.equal(controls.canRun(status(), context), true);
  for (const change of [{ model: "other/model" }, { configured: false }, { available: false }, { state: "UNAVAILABLE" }, { profile: "" },
    { workspace_url: "javascript:alert(1)" }, { workspace_url: "https://example.com/" }, { workspace_url: "http://secret@localhost/" },
    { capabilities: [{ backend: "fixture.cadquery", operations: "cad_run" }] }]) assert.equal(controls.canRun(status(change), context), false);
  for (const change of [{ local: false }, { writable: false }, { busy: true }, { local: undefined }]) assert.equal(controls.canRun(status(), { ...context, ...change }), false);
});
test("actual status reason is Korean safe text; private path/code stays out of primary", () => {
  assert.equal(controls.safeMessage("AI 연구 연결이 준비되지 않았습니다."), "AI 연구 연결이 준비되지 않았습니다.");
  for (const raw of ["C:\\private\\owner.json", "실패 C:\\private", "실패 /home/private", "실패 OWNER_SOURCE_CHANGED", "실패 {\"secret\":1}", "TypeError at bridge"]) assert.doesNotMatch(controls.safeMessage(raw), /private|OWNER_SOURCE|secret|TypeError/);
  const h = harness({ researchStatus: status({ available: false, reason: "실패 C:\\private\\owner.json" }) });
  h.ui.renderResearchConnection(); assert.doesNotMatch(h.$("researchConnection").textContent, /private/);
  assert.match(h.$("researchConnectionJson").textContent, /private/);
});
test("complete actual answer keeps failed/UNKNOWN tool codes and NOT_RELEASED", () => {
  const value = result(), before = JSON.stringify(value), view = controls.responseView(value, { question: QUESTION });
  assert.equal(view.valid, true); assert.equal(view.confirmed, true); assert.equal(view.answer, value.answer);
  assert.deepEqual(view.tools.map(item => item.status), ["COMPLETED_REVIEW_REQUIRED", "FAILED_EXECUTION", "UNKNOWN"]);
  assert.equal(value.decision, "NOT_RELEASED"); assert.equal(JSON.stringify(value), before);
  assert.equal(controls.responseView(value, { question: "another request" }).valid, false);
  assert.equal(controls.responseView(result({ model: "unapproved" })).valid, false);
});
test("failed/cancelled/preflight nullable responses retain partial/empty answer but never continue", () => {
  for (const state of ["FAILED", "CANCELLED"]) {
    const data = result({ status: state, answer: "여기까지 받은 실제 부분 답변", error: "도구 실행을 완료하지 못했습니다." });
    const view = controls.responseView(data); assert.equal(view.valid, true); assert.equal(view.answer, data.answer); assert.equal(view.confirmed, false);
    assert.equal(controls.canContinue(data, status(), { local: true, writable: true, activeStore: "local", resultStore: "local" }), false);
  }
  const preflight = controls.responseView(result({ status: "FAILED", session_id: null, source_commit: null, answer: "", profile: "", workspace_url: "" }));
  assert.equal(preflight.valid, true); assert.equal(preflight.answer, ""); assert.equal(preflight.confirmed, false);
});
test("continuation requires confirmed same model/profile/project/store; no inferred ID", () => {
  const context = { local: true, writable: true, activeStore: "local", resultStore: "local" };
  assert.equal(controls.canContinue(result(), status(), context), true);
  for (const changed of [{ session_id: null }, { source_commit: null }, { source_commit: "bad" }, { profile: "foreign" }, { workspace_url: "http://localhost/foreign" }]) assert.equal(controls.canContinue(result(changed), status(), context), false);
  assert.equal(controls.canContinue(result(), status(), { ...context, resultStore: "library" }), false);
});
test("actual request form precedes secondary metadata and explicit assembly restriction remains", () => {
  assert(htmlSource.indexOf('id="researchQuestionForm"') < htmlSource.indexOf('id="studyForm"'));
  assert.match(htmlSource, /<details class="research-records"><summary[^>]*>연구 기록만 저장/);
  const primary = htmlSource.slice(htmlSource.indexOf('id="researchQuestionForm"'), htmlSource.indexOf('</form>', htmlSource.indexOf('id="researchQuestionForm"')));
  assert.doesNotMatch(primary, /studyId|studyHypothesis|studyObjective/);
  assert.match(primary, /<textarea id="researchQuestion"[^>]*placeholder="[^"]+"><\/textarea>/);
  assert.match(htmlSource, /전체 조립체의 하중·접촉 해석은 아직 준비되지 않았습니다/);
  for (const id of ["studyForm", "studyId", "studyName", "studyQuestion", "studyHypothesis", "studyObjective", "simulationRunBtn", "jobCancelBtn"]) assert.equal([...htmlSource.matchAll(new RegExp(`id="${id}"`, "g"))].length, 1);
});
test("actual controls disable busy/library/unconfigured; continue only known completed session", () => {
  const h = harness(); h.ui.updateControls(); assert.equal(h.$("researchRunBtn").disabled, false); assert.equal(h.$("researchContinue").disabled, true);
  h.ui.state.researchSession = { result: result(), store: "local", jobStatus: "COMPLETED" }; h.ui.updateControls(); assert.equal(h.$("researchContinue").disabled, false);
  for (const change of ["failed", "busy", "library", "unconfigured"]) {
    if (change === "failed") h.ui.state.researchSession.jobStatus = "FAILED";
    if (change === "busy") h.ui.state.job = job({ status: "RUNNING", result: undefined });
    if (change === "library") { h.ui.state.job = null; h.ui.state.overview.active_store = "library"; h.ui.state.overview.stores.push({ id: "library", writable: false }); }
    if (change === "unconfigured") { h.ui.state.overview.active_store = "local"; h.ui.state.researchStatus = { configured: false, available: false }; }
    h.$("researchContinue").checked = true; h.ui.updateControls(); assert.equal(h.$("researchContinue").disabled, true); assert.equal(h.$("researchContinue").checked, false);
    if (change !== "failed") assert.equal(h.$("researchRunBtn").disabled, true);
  }
});
test("actual answer renderer uses text nodes, retains raw tool/status/IDs and same-store links", () => {
  const h = harness(), payload = result({ answer: '<script>alert("answer")</script>\nUNKNOWN stays unknown', question: QUESTION + '<img src=x>' });
  const record = job({ result: payload }); h.ui.retainResearchJob(record);
  const cards = walk(h.$("researchAnswers"));
  assert(cards.some(node => node.classList.contains("research-answer-text") && node.textContent === payload.answer));
  assert.equal(cards.filter(node => ["SCRIPT", "IMG"].includes(node.tagName)).length, 0);
  assert(cards.some(node => node.dataset.status === "FAILED_EXECUTION")); assert(cards.some(node => node.dataset.status === "UNKNOWN")); assert(cards.some(node => node.dataset.status === "NOT_RELEASED"));
  assert.deepEqual(cards.filter(node => node.tagName === "BUTTON" && node.dataset.experimentId).map(node => node.dataset.experimentId), ["E-synthetic", "E-failed"]);
  h.ui.state.overview.active_store = "library"; h.ui.renderResearchAnswers();
  assert.equal(walk(h.$("researchAnswers")).filter(node => node.tagName === "BUTTON" && node.dataset.experimentId).length, 0);
  assert.match(h.$("researchAnswers").textContent, /원래 실험 저장소에서 확인/); assert.match(h.$("researchAnswers").textContent, /<script>/);
});
test("malformed/foreign response IDs never become executable result links", () => {
  const h = harness(), raw = result({ tools: [{ tool: '<script>alert(1)</script>', status: "FUTURE_STATUS", experiment_id: "../foreign" }, null] });
  h.ui.retainResearchJob(job({ result: raw })); const nodes = walk(h.$("researchAnswers"));
  assert.equal(nodes.filter(node => node.tagName === "BUTTON").length, 0); assert.match(h.$("researchAnswers").textContent, /상태 확인 필요/);
  h.ui.state.researchContexts.set("J-synthetic", { question: "foreign", store: "local" }); h.ui.retainResearchJob(job({ result: raw }));
  assert.match(h.$("researchAnswers").textContent, /응답 형식을 확인할 수 없습니다/); assert.equal(walk(h.$("researchAnswers")).filter(node => node.classList.contains("research-answer-text")).length, 0);
});
test("actual failed/cancelled job keeps partial answers and cancellation gates, never green success", () => {
  const h = harness();
  for (const code of ["FAILED", "CANCELLED"]) {
    h.ui.state.job = job({ status: code, result: result({ status: code, answer: "실패 전 실제 부분 답변" }) });
    h.ui.state.researchContexts.set("J-synthetic", { question: QUESTION, store: "local" }); h.ui.renderJob();
    assert.match(h.$("researchAnswers").textContent, /실패 전 실제 부분 답변/); assert.equal(h.$("jobPanel").classList.contains("finished"), false);
    assert.equal(h.$("jobCancelBtn").hidden, true); assert.equal(h.$("researchContinue").disabled, true);
    assert.equal(h.$("jobStatus").dataset.status, code); if (code === "FAILED") assert.equal(h.$("jobPanel").classList.contains("failed"), true);
  }
  for (const code of ["RUNNING", "CANCEL_REQUESTED", "CLEANUP_PENDING"]) {
    h.ui.state.job = job({ status: code, result: undefined }); h.ui.renderJob();
    assert.equal(h.$("jobCancelBtn").hidden, false); assert.equal(h.$("jobCancelBtn").disabled, code === "CANCEL_REQUESTED"); assert.equal(h.$("researchRunBtn").disabled, true);
  }
  assert.equal(h.$("jobCancelBtn").textContent, "종료 재시도"); assert.equal(h.paths.length, 0);
});
test("completed AI job displays response receipt rather than numerical/engineering approval", () => {
  const h = harness(); h.ui.state.job = job(); h.ui.renderJob();
  assert.equal(h.$("jobStatus").textContent, "AI 응답 받음 · 결과 검토 필요"); assert.equal(h.$("jobStatus").dataset.status, "COMPLETED");
  assert.match(h.$("jobMessage").textContent, /각 실험의 판정/); assert.equal(h.ui.confirmedResearchSession(), null, "Reloaded response is not implicitly continued");
});

test("recovered research blocks every new question even with a positive retained answer", async () => {
  const h = harness();
  h.ui.state.job = job({ status: "RECOVERY_REQUIRED", cleanup_pending: true });
  h.ui.state.researchContexts.set("J-synthetic", { question: QUESTION, store: "local" });
  h.ui.renderJob();
  assert.equal(h.$("jobStatus").textContent, "실행 상태 확인 필요 · 새 작업 차단");
  assert.equal(h.$("jobStatus").dataset.status, "RECOVERY_REQUIRED");
  assert.equal(h.$("jobPanel").classList.contains("finished"), false);
  assert.equal(h.$("jobCancelBtn").hidden, true, "No fresh token can cancel an orphan");
  assert.equal(h.$("researchRunBtn").disabled, true);
  assert.equal(h.$("researchContinue").disabled, true);
  assert.equal(h.ui.confirmedResearchSession(), null);
  assert.match(h.$("researchAnswers").textContent, /실제 반환 텍스트 fixture/);
  assert.match(h.$("researchInputState").textContent, /이전 작업.*확인해야/);
  await assert.rejects(h.ui.submitResearchQuestion(), /AI 연구 연결과 작업 저장소 상태/);
  assert.equal(h.paths.length, 0);
  assert.equal(h.timers.length, 0);
});

test("unknown journal admission blocks execution with no recoverable job ID", async () => {
  const h = harness();
  h.ui.state.overview.execution = { state: "RECOVERY_REQUIRED", outcome: "UNKNOWN", idle_confirmed: false, accepting_jobs: false, recovered_job_ids: [] };
  h.ui.state.job = job();
  h.ui.updateControls();
  assert.equal(h.$("researchRunBtn").disabled, true);
  assert.equal(h.$("researchResetBtn").disabled, true);
  assert.equal(h.$("storeSelect").disabled, false, "Recovery preserves library browsing, while server ownership still guards switching");
  assert.equal(h.$("studySelect").disabled, false, "Preserved studies remain selectable");
  h.ui.state.comparison.add("E-one"); h.ui.state.comparison.add("E-two");
  h.ui.updateControls();
  assert.equal(h.$("compareBtn").disabled, false, "Preserved result comparison remains available");
  await assert.rejects(h.ui.submitResearchQuestion(), /AI 연구 연결과 작업 저장소 상태/);
  assert.equal(h.paths.length, 0);
  assert.equal(h.timers.length, 0);
  h.ui.renderResearchConnection();
  assert.match(h.$("researchConnection").textContent, /^실행 상태 확인 필요/);
  assert.doesNotMatch(h.$("researchConnection").textContent, /연결 대기|승인된 모델에 연결됐습니다/);
  assert.match(h.$("researchConnectionJson").textContent, /READY/, "Raw previous connection evidence remains intact");
  const view = controls.statusView(status({ available: false, state: "RECOVERY_REQUIRED", reason: "raw_private_path" }));
  assert.equal(view.ready, false);
  assert.equal(view.modelLabel, "실행 상태 확인 필요");
  assert.match(view.reason, /이전 작업.*보존된 답변과 결과/);
  assert.doesNotMatch(view.reason, /private|raw|인증|로그인/);
});

test("refresh restores the durable job and original answer without polling an unknown worker", async () => {
  const retained = job({ status: "RECOVERY_REQUIRED", cleanup_pending: true });
  const overview = { active_store: "local", stores: [{ id: "local", writable: true }], studies: [], capabilities: [], token: "synthetic-token", jobs: [retained],
    execution: { state: "RECOVERY_REQUIRED", outcome: "UNKNOWN", idle_confirmed: false, accepting_jobs: false, recovered_job_ids: [retained.id] } };
  const before = JSON.stringify(overview);
  const h = harness({ fetchReply: path => { assert.equal(path, "/api/overview"); return reply(overview); } });
  // These unrelated listing renderers have their own controls. Exercise the
  // actual refresh, answer restoration, job rendering and admission controls.
  h.sandbox.renderOverview = () => h.ui.updateControls(); h.sandbox.renderStudy = () => {};
  await h.ui.loadOverview();
  assert.equal(h.ui.state.job.id, retained.id);
  assert.match(h.$("connectionState").textContent, /실행 상태 확인 필요.*보존된 기록/);
  assert.match(h.$("researchAnswers").textContent, /실제 반환 텍스트 fixture/);
  assert.equal(h.$("researchRunBtn").disabled, true);
  assert.equal(h.$("jobCancelBtn").hidden, true);
  assert.equal(h.ui.confirmedResearchSession(), null);
  assert.equal(h.timers.length, 0);
  assert.equal(h.paths.length, 1);
  assert.equal(JSON.stringify(overview), before);
  // Only a later authoritative terminal for that same ID can replace the
  // displayed recovery status; a positive result payload alone did not.
  overview.execution = { state: "IDLE", idle_confirmed: true, accepting_jobs: true };
  overview.jobs = [job()];
  await h.ui.loadOverview();
  assert.equal(h.ui.state.job.status, "COMPLETED");
  assert.equal(h.$("researchRunBtn").disabled, false);
  assert.equal(h.ui.confirmedResearchSession(), null);
  assert.equal(h.timers.length, 0);
});

test("refresh shows recovery and closes admission even when the damaged journal has no job", async () => {
  const h = harness({ fetchReply: path => { assert.equal(path, "/api/overview"); return reply({ active_store: "local", stores: [{ id: "local", writable: true }], jobs: [],
    execution: { state: "RECOVERY_REQUIRED", outcome: "UNKNOWN", idle_confirmed: false, accepting_jobs: false, recovered_job_ids: [] } }); } });
  h.sandbox.renderOverview = () => h.ui.updateControls(); h.sandbox.renderStudy = () => {};
  await h.ui.loadOverview();
  assert.equal(h.ui.state.job, null);
  assert.match(h.$("connectionState").textContent, /새 작업은 차단/);
  assert.equal(h.$("researchRunBtn").disabled, true);
  assert.equal(h.timers.length, 0);
  assert.equal(h.paths.length, 1);
});
test("source-bound request context protects current session from older retained jobs", () => {
  const h = harness(); h.ui.state.job = job(); h.ui.state.researchContexts.set("J-synthetic", { question: QUESTION, store: "local" }); h.ui.retainResearchJob(h.ui.state.job);
  assert.equal(h.ui.confirmedResearchSession(), "ses_Actual123");
  h.ui.state.researchContexts.set("J-older", { question: QUESTION, store: "local" }); h.ui.retainResearchJob(job({ id: "J-older", status: "FAILED", result: result({ status: "FAILED" }) }));
  assert.equal(h.ui.confirmedResearchSession(), "ses_Actual123");
  assert.equal(h.ui.state.researchHistory.size, 2);
});
test("status refresh fail closes and overlapping response cannot restore an older owner", async () => {
  const pending = []; const h = harness({ fetchReply: () => new Promise(resolve => pending.push(resolve)) });
  const first = h.ui.loadResearchStatus(), second = h.ui.loadResearchStatus();
  pending[1](reply(status({ available: false, reason: "AI 연구 연결이 준비되지 않았습니다." }))); await second;
  pending[0](reply(status())); await first; assert.equal(h.ui.state.researchStatus.available, false);
  assert.equal(h.$("researchRunBtn").disabled, true); assert.equal(h.paths.length, 2);
  const failed = harness({ fetchReply: () => { throw new Error("C:\\private\\owner.json"); } }); await failed.ui.loadResearchStatus();
  assert.equal(failed.$("researchRunBtn").disabled, true); assert.doesNotMatch(failed.$("researchConnection").textContent, /private/); assert.match(failed.$("researchConnectionJson").textContent, /private/);
});
test("actual submit uses existing tokenized single-job route with exact preserved request", async () => {
  const h = harness({ fetchReply: (path, options) => { assert.equal(path, "/api/jobs"); assert.equal(options.method, "POST"); return reply(job({ status: "RUNNING", result: undefined })); } });
  h.ui.state.researchSession = { result: result(), store: "local", jobStatus: "COMPLETED" }; h.$("researchContinue").checked = true;
  await h.ui.submitResearchQuestion(); const request = h.paths[0];
  assert.deepEqual(JSON.parse(request.options.body), { operation: "research_run", arguments: { question: QUESTION, session_id: "ses_Actual123" } });
  assert.equal(request.options.headers["X-CAE-Token"], "synthetic-token"); assert.equal(h.paths.length, 1); assert.equal(h.timers[0].delay, 1200);
  assert.equal(h.$("researchRunBtn").disabled, true); assert.equal(h.ui.state.researchContexts.get("J-synthetic").question, QUESTION);
});
test("actual busy/read-only/unconfigured submission refuses before request", async () => {
  for (const setting of [{ writable: false }, { store: "library" }, { researchStatus: { configured: false, available: false } }]) {
    const h = harness(setting); await assert.rejects(h.ui.submitResearchQuestion()); assert.equal(h.paths.length, 0);
  }
  const h = harness(); h.ui.state.job = job({ status: "RUNNING", result: undefined }); await assert.rejects(h.ui.submitResearchQuestion()); assert.equal(h.paths.length, 0);
});
test("running poll never refreshes native health; terminal failed result survives and status refreshes once", async () => {
  const terminal = job({ status: "FAILED", result: result({ status: "FAILED", answer: "실제 부분 답변", error: "실패 C:\\private\\secret" }), error: "실패 C:\\private\\secret" });
  let complete = false; const h = harness({ fetchReply: path => path === "/api/research" ? reply(status()) : reply(complete ? terminal : job({ status: "RUNNING", result: undefined })) });
  vm.runInContext("loadOverview = async () => {};", h.sandbox); // Isolate the existing overview renderer, not the research route.
  h.ui.state.job = job({ status: "RUNNING", result: undefined }); h.ui.state.researchContexts.set("J-synthetic", { question: QUESTION, store: "local" });
  await h.ui.pollJob(); assert.deepEqual(h.paths.map(item => item.path), ["/api/jobs/J-synthetic"]);
  complete = true; await h.ui.pollJob(); assert.deepEqual(h.paths.map(item => item.path), ["/api/jobs/J-synthetic", "/api/jobs/J-synthetic", "/api/research"]);
  assert.match(h.$("researchAnswers").textContent, /실제 부분 답변/); assert.doesNotMatch(h.$("noticeText").textContent, /private|secret/); assert.equal(h.$("researchContinue").disabled, true);
});
test("initial/explicit refresh/terminal only source hooks and existing cancel/raw controls remain", () => {
  const poll = appSource.slice(appSource.indexOf("function schedulePoll("), appSource.indexOf("async function runJob("));
  assert.match(poll, /if \(activeJob\(job\)\) \{ schedulePoll\(\); return; \}/); assert.equal((poll.match(/loadResearchStatus\(\)/g) ?? []).length, 1);
  assert.match(appSource, /Promise\.allSettled\(\[loadOverview\(\), api\("\/api\/presets"\)\.then\(renderPresets\), loadResearchStatus\(\)\]/);
  assert.match(appSource, /"refreshBtn"\)\.addEventListener[^\n]*loadResearchStatus\(\)/);
  assert.match(appSource, /\/cancel`, \{ method: "POST", body: "\{\}" \}/);
  assert.match(appSource, /state\.researchSession = null; \$\("researchContinue"\)\.checked = false; renderResearchAnswers\(\)/);
  assert.doesNotMatch(readFileSync(require.resolve("../apps/lab/static/research-controls.js"), "utf8"), /innerHTML|fetch\(|setTimeout\(/);
});

test("progress uses only actual approved partial bytes and can never confirm a session", () => {
  const data = { session_id: "ses_Progress123", model: controls.MODEL, answer: "실제 부분 답변", tools: result().tools,
    cleanup_pending: false, completion_is_engineering_approval: false, decision: "NOT_RELEASED" };
  const before = JSON.stringify(data), view = controls.progressView(data);
  assert.equal(view.valid, true); assert.equal(view.confirmed, false); assert.equal(view.answer, data.answer);
  assert.deepEqual(view.tools.map(item => item.status), ["COMPLETED_REVIEW_REQUIRED", "FAILED_EXECUTION", "UNKNOWN"]);
  assert.equal(controls.responseView(data).confirmed, false); assert.equal(JSON.stringify(data), before);
  assert.equal(controls.progressView({ ...data, session_id: null, answer: "", tools: [] }).valid, true);
  for (const change of [{ model: "other/model" }, { session_id: "ses_abc\n" }, { cleanup_pending: "true" },
    { answer: null }, { tools: null }, { decision: "RELEASED" }, { completion_is_engineering_approval: true }]) {
    const refused = controls.progressView({ ...data, ...change }); assert.equal(refused.valid, false); assert.equal(refused.answer, ""); assert.equal(refused.confirmed, false);
  }
});
test("running/cancel-requested progress renders escaped actual partials, failed tools and old history without continuation", () => {
  const h = harness(); h.ui.retainResearchJob(job({ id: "J-old", result: result({ answer: "과거 최종 답변 보존" }) }));
  h.ui.state.researchSession = { result: result(), store: "local", jobStatus: "COMPLETED" };
  h.ui.state.researchContexts.set("J-synthetic", { question: QUESTION, store: "local" });
  const progress = { session_id: "ses_Progress123", model: controls.MODEL, answer: '<script>alert("partial")</script>\n실제 진행 답변',
    tools: result().tools, cleanup_pending: false, completion_is_engineering_approval: false, decision: "NOT_RELEASED" };
  for (const code of ["RUNNING", "CANCEL_REQUESTED"]) {
    h.ui.state.job = job({ status: code, result: undefined, progress }); h.ui.renderJob();
    const nodes = walk(h.$("researchAnswers"));
    assert(nodes.some(node => node.classList.contains("research-answer-text") && node.textContent === progress.answer));
    assert.equal(nodes.filter(node => node.tagName === "SCRIPT").length, 0);
    assert.match(h.$("researchAnswers").textContent, /과거 최종 답변 보존/); assert.match(h.$("researchAnswers").textContent, /실행 중인 부분 기록/);
    assert(nodes.some(node => node.dataset.status === "FAILED_EXECUTION")); assert(nodes.some(node => node.dataset.status === "UNKNOWN"));
    assert.equal(h.ui.state.researchHistory.size, 1, "Progress does not overwrite or invent terminal history");
    assert.equal(h.ui.confirmedResearchSession(), null); assert.equal(h.$("researchContinue").disabled, true);
    assert.equal(h.$("researchRunBtn").disabled, true); assert.equal(h.$("jobStatus").dataset.status, code);
    assert.equal(h.paths.length, 0, "Rendering progress must not invoke health/provider/HTTP");
  }
  h.ui.state.overview.active_store = "library"; h.ui.renderResearchAnswers();
  assert.equal(walk(h.$("researchAnswers")).filter(node => node.tagName === "BUTTON" && node.dataset.experimentId).length, 0);
});
test("active ownership remains running until cancellation or cleanup; terminal result remains authoritative", async () => {
  const progress = { session_id: null, model: controls.MODEL, answer: "종료 확인 전 받은 실제 부분 답변", tools: [],
    cleanup_pending: true, completion_is_engineering_approval: false, decision: "NOT_RELEASED" };
  const h = harness({ fetchReply: () => reply(job({ status: "RUNNING", result: undefined, progress })) });
  h.ui.state.job = job({ status: "RUNNING", result: undefined }); await h.ui.pollJob();
  assert.deepEqual(h.paths.map(item => item.path), ["/api/jobs/J-synthetic"], "Progress polling never runs owner health");
  for (const code of ["RUNNING", "CANCEL_REQUESTED"]) {
    h.ui.state.job = job({ status: code, result: undefined, progress }); h.ui.renderJob();
    assert.equal(h.$("jobStatus").textContent, code === "RUNNING" ? "AI 연구 실행 중" : "AI 연구 종료 확인 중"); assert.equal(h.$("jobStatus").dataset.status, code);
    assert.equal(h.$("jobPanel").classList.contains("finished"), false); assert.equal(h.$("jobCancelBtn").hidden, false);
    assert.equal(h.$("researchRunBtn").disabled, true); assert.equal(h.$("researchContinue").disabled, true);
    assert.match(h.$("researchAnswers").textContent, /종료 확인 전 받은 실제 부분 답변/);
  }
  h.ui.state.job = job({ status: "FAILED", progress, result: result({ status: "FAILED", answer: "최종 실패의 원래 부분 답변" }) }); h.ui.renderJob();
  assert.equal(h.$("jobStatus").textContent, "AI 연구 실패"); assert.equal(h.$("jobStatus").dataset.status, "FAILED");
  assert.match(h.$("researchAnswers").textContent, /최종 실패의 원래 부분 답변/);
  assert.equal(walk(h.$("researchAnswers")).some(node => node.classList.contains("research-answer-text") && node.textContent === progress.answer), false);
});

test("retained official caelab_ names and known wire aliases render meaningful labels without changing raw tool/status", () => {
  // Names observed in retained official contact Research JSONL, plus documented
  // MCP aliases. Source test remains portable: no ignored live evidence needed.
  const known = [
    ["caelab_study_create", "연구 기록 저장"], ["caelab_study_inspect", "연구 기록 확인"],
    ["caelab_model_analysis_run", "선언된 모델 해석"], ["caelab_experiment_inspect", "실험 결과 확인"],
    ["caelab_experiment_summary", "실험 결과 요약"], ["caelab_experiment_compare", "실험 결과 비교"],
    ["caelab_analysis_run", "CAD 구조 해석"], ["caelab_parameters_discover", "CAD 변수 확인"],
    ["caelab_parameters_register", "연구 변수 등록"], ["caelab_parameters_list", "등록된 연구 변수 확인"],
    ["caelab_experiment_run", "CAD 생성·검사"], ["caelab_optimization_inspect", "최적화 실행 기록 확인"],
  ];
  const tools = known.map(([tool], i) => ({ tool, status: ["completed", "FAILED_EXECUTION", "UNKNOWN"][i % 3] }));
  const before = JSON.stringify(tools);
  known.forEach(([tool, label], i) => { const view = controls.toolView(tools[i]); assert.equal(view.label, label); assert.equal(view.raw, tools[i]); assert.equal(view.raw.tool, tool); assert.equal(view.status, tools[i].status); });
  for (const tool of ["caelab_future_operation", "another_parameters_discover", "caelab_toString", "caelab_constructor"]) assert.equal(controls.toolView({ tool, status: "constructor" }).label, "도구 실행");
  assert.equal(controls.toolView({ tool: "caelab_future_operation", status: "constructor" }).statusLabel, "상태 확인 필요");
  const h = harness(); h.ui.retainResearchJob(job({ result: result({ tools }) }));
  const rows = walk(h.$("researchAnswers")).find(node => node.tagName === "TBODY").children;
  known.forEach(([tool, label], i) => { assert.equal(rows[i].children[0].children[0].textContent, label); assert.equal(rows[i].children[0].children[0].title, tool); assert.equal(rows[i].children[1].children[0].dataset.status, tools[i].status); });
  assert.equal(JSON.stringify(tools), before); assert.equal(h.paths.length, 0);
});
