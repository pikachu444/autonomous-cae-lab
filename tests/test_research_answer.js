"use strict";

// Display-only: retained first-answer text and controlled DOM fixtures.
// Ordinary clone paths after promotion; no ignored evidence/HTTP/native needed.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const vm = require("node:vm");
const controls = require("../apps/lab/static/research-controls.js");
const appSource = readFileSync(require.resolve("../apps/lab/static/app.js"), "utf8");
const styleSource = readFileSync(require.resolve("../apps/lab/static/style.css"), "utf8");
// Verbatim job.result.answer from human-02/question-ended-01.json. Formatting
// this text does not verify any AI statement about CAD or engineering.
const FIRST_ANSWER = "다음 순서로 실제 실행하겠습니다.\n\n1. `roller_support` CAD에서 폭과 롤러 지름의 네이티브 치수를 확인하고 연구 변수로 등록  \n2. 나머지 형상은 CAD 기본값으로 둔 채 폭 32/38 mm, 롤러 지름 8.3 mm인 두 CAD 실험 생성 및 형상 검증  \n3. 각 검증된 CAD에 같은 가상 직교이방성 재료, CAD 축 기준 재료축, 아래 방향 100 N 하중과 동일 경계조건을 적용  \n4. 메시 크기 4/3/2 mm에서 해석해 처짐 수렴성과 반력 평형을 확인  \n5. 검증 영수증과 화면에서 열 수 있는 실험 ID를 연결해 비교\n\n응력은 진단값으로만 보고 강도 합격으로 판정하지 않으며, 모든 미확인 상태와 `NOT_RELEASED`를 그대로 유지하겠습니다.\nCAD 두 설계는 생성·검증됐지만, 구조해석 실행 전에 **경계조건과 하중 적용 면**이 확정되어야 합니다.\n\n권장 조건으로 진행해도 될까요?\n\n- **구속:** 4개 볼트 구멍의 원통면을 완전 고정\n- **하중:** 롤러가 닿는 상부 원통형 받침면에 CAD **−Z 방향 총 100 N**을 분포하중으로 적용\n- **해석:** 선형 정적, 메시 4/3/2 mm\n- **재료축:** CAD X/Y/Z와 일치\n\n이 조건은 실제 볼트 체결 및 롤러 접촉을 단순화하므로 국부 응력에는 특히 부정확할 수 있습니다.\n\n현재 화면에서 확인 가능한 CAD 실험은 다음과 같습니다.\n\n- 폭 32 mm: `cad-width32-d8p3-v1`\n- 폭 38 mm: `cad-width38-d8p3-v1`\n\n두 CAD 모두 롤러 지름 8.3 mm이며 BREP, STEP 왕복, watertight 검사에 통과했습니다. 다만 기계 인터페이스·강도·실하중 시험·피로는 모두 `UNKNOWN`, 판정은 `NOT_RELEASED`입니다.";
const boundary = appSource.indexOf('$("jobCancelBtn").addEventListener("click", async () => {');
assert(boundary > 0);
function partsText(parts) { return parts.map(part => part.parts ? partsText(part.parts) : part.text).join(""); }
function blockText(block) {
  if (block.type === "paragraph") return partsText(block.parts);
  if (block.type === "list") return block.items.map(item => `${item.marker} ${partsText(item.parts)}`).join("\n");
  if (block.type === "table") return [block.header, ...block.rows].map(row => row.map(partsText).join("|")).join("\n");
  return block.text;
}
class TinyNode {
  constructor(tag = "div") {
    this.tagName = tag.toUpperCase(); this.children = []; this.dataset = {}; this.attributes = {}; this.style = {};
    this.className = ""; this.value = ""; this.hidden = false; this.disabled = false; this.checked = false; this._text = "";
    this.classList = { contains: name => this.className.split(/\s+/).includes(name),
      add: (...names) => { this.className = [...new Set([...this.className.split(/\s+/).filter(Boolean), ...names])].join(" "); },
      toggle: (name, enabled) => { this.className = this.className.split(/\s+/).filter(value => value && value !== name).join(" "); if (enabled) this.classList.add(name); } };
  }
  set textContent(value) { this._text = String(value ?? ""); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
  set innerHTML(_value) { throw new Error("Answer markup must never be evaluated as HTML"); }
  append(...items) { for (const item of items) { const child = item instanceof TinyNode ? item : new TinyNode("#text"); if (!(item instanceof TinyNode)) child.textContent = item; this.children.push(child); } }
  replaceChildren(...items) { this._text = ""; this.children = []; this.append(...items); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  addEventListener(name, callback) { (this.listeners ??= new Map()).set(name, callback); }
  querySelector(selector) { return walk(this).slice(1).find(node => selector.startsWith(".") ? node.classList.contains(selector.slice(1)) : node.tagName === selector.toUpperCase()) ?? null; }
}
function walk(node) { return [node, ...node.children.flatMap(walk)]; }
function shape(node) { return { tag: node.tagName, text: node._text, children: node.children.map(shape) }; }
function payload(answer = FIRST_ANSWER) {
  return { kind: "openscience_research", status: "COMPLETED", session_id: "ses_Confirmed123", source_commit: "a".repeat(40),
    model: controls.MODEL, profile: "FixtureScalar", workspace_url: "http://127.0.0.1:4100/owned-project/session",
    question: "synthetic UI input", answer, tools: [{ tool: "caelab_experiment_run", status: "COMPLETED_REVIEW_REQUIRED", experiment_id: "E-cad" }],
    completion_is_engineering_approval: false, decision: "NOT_RELEASED" };
}
function harness({ writable = true, store = "local" } = {}) {
  const ids = new Map(), operations = [], counters = { http: 0, timers: 0 };
  const $ = id => { if (!ids.has(id)) ids.set(id, new TinyNode()); return ids.get(id); };
  for (const [operation, id] of [["research_run", "researchRunBtn"], ["cad_run", "cadRun"], ["parameter_register", "register"], ["native_final", "nativeFinalButton"]]) {
    const button = $(id); button.dataset.operation = operation; operations.push(button);
  }
  $("cadBackend").value = "fixture.cadquery"; $("cadModel").value = "roller_support"; $("simulationPreset").value = "linear";
  $("campaignTarget").value = "cad"; $("researchQuestion").value = "질문";
  $("fixtureConditionFields").hidden = true; $("importedMeshFields").hidden = true;
  const indicator = new TinyNode("span"); indicator.className = "job-indicator"; $("jobPanel").append(indicator);
  const document = { getElementById: $, createElement: tag => new TinyNode(tag), querySelectorAll: selector => selector === "[data-operation]" ? operations : [],
    querySelector: selector => operations.find(node => selector === `[data-operation="${node.dataset.operation}"]`) ?? null };
  const sandbox = { document, Node: TinyNode, window: { researchControls: controls, cadControls: { eligibleParent: () => false, supportsBackend: () => true } },
    location: { hash: "research" }, URL, URLSearchParams, TextEncoder, Intl, console,
    fetch: () => { counters.http++; throw new Error("No HTTP/provider calls in presentation tests"); },
    setTimeout: () => { counters.timers++; throw new Error("No job execution in presentation tests"); }, clearTimeout: () => {} };
  vm.createContext(sandbox); vm.runInContext(appSource.slice(0, boundary) + "\nglobalThis.ui = {state,appendResearchAnswer,renderResearchAnswers,retainResearchJob,renderResearchConnection,renderJob,updateControls,confirmedResearchSession};", sandbox);
  const ui = sandbox.ui; ui.state.overview = { active_store: store, stores: [{ id: store, writable }], capabilities: [] };
  ui.state.presets = { linear: { operation: "analysis_run", backend: "fixture.calculix" } };
  ui.state.researchStatus = { configured: true, available: true, state: "READY", model: controls.MODEL, profile: "FixtureScalar",
    workspace_url: payload().workspace_url, capabilities: [{ backend: "fixture.cadquery", operations: ["cad_run"] }] };
  return { ui, $, counters };
}

test("retained first answer becomes paragraphs/lists/emphasis while keeping numeric/unit/verdict strings and exact original", () => {
  assert.equal(typeof FIRST_ANSWER, "string"); const model = controls.answerBlocks(FIRST_ANSWER), text = model.blocks.map(blockText).join("\n");
  assert.equal(model.raw, FIRST_ANSWER); assert.deepEqual(model.blocks.filter(block => block.type === "list").map(block => block.items.length), [5, 4, 2]);
  assert.deepEqual(model.blocks.find(block => block.type === "list").items.map(item => item.marker), ["1.", "2.", "3.", "4.", "5."]);
  for (const literal of ["32/38 mm", "8.3 mm", "100 N", "4/3/2 mm", "−Z 방향 총 100 N", "UNKNOWN", "NOT_RELEASED", "cad-width32-d8p3-v1", "cad-width38-d8p3-v1", "부정확할 수 있습니다"]) assert(text.includes(literal), literal);
  const numbers = value => value.match(/\d+(?:\.\d+)?/g); assert.deepEqual(numbers(text), numbers(FIRST_ANSWER));
  const h = harness(), card = new TinyNode(); h.ui.appendResearchAnswer(card, FIRST_ANSWER, "empty");
  const body = card.children[0]; assert(walk(body).some(node => node.tagName === "STRONG" && node.textContent === "경계조건과 하중 적용 면"));
  assert(walk(body).some(node => node.tagName === "CODE" && node.textContent === "NOT_RELEASED"));
  assert.equal(walk(card).find(node => node.tagName === "PRE").textContent, FIRST_ANSWER);
  assert.doesNotMatch(body.textContent, /\*\*경계조건|`NOT_RELEASED`/); assert.deepEqual(h.counters, { http: 0, timers: 0 });
});
test("formatter leaves numbers/maths/identifiers as text; partial delimiters remain visible until closed", () => {
  const raw = "**수치 `1.5000` mm** · *강조* · −0 · 2.98023223876953e-08 m · 2*3*4 · 2**3**4 · NOT_RELEASED\n\n**아직 닫히지 않음";
  const parsed = controls.answerBlocks(raw), text = parsed.blocks.map(blockText).join("\n\n");
  assert.equal(parsed.raw, raw); for (const literal of ["1.5000", "−0", "2.98023223876953e-08 m", "2*3*4", "2**3**4", "NOT_RELEASED", "**아직 닫히지 않음"]) assert(text.includes(literal), literal);
  assert(parsed.blocks[0].parts.some(part => part.type === "em")); assert(parsed.blocks[0].parts.some(part => part.type === "strong" && part.parts.some(value => value.type === "code")));
  assert.equal(controls.answerBlocks("01. 1.0000 mm\n03) UNKNOWN").blocks[0].items[0].marker, "01.");
});
test("tables preserve each original scalar/unit/signed value; ragged/ambiguous tables never invent cells", () => {
  const raw = "| 설계 | 처짐 (mm) | 판정 | 한계 |\n|---|---:|:---|---|\n|32 mm|−0.0012300|UNKNOWN|**`NOT_RELEASED`**|\n|38 mm|2.0e-08|FAIL|가상 재료|";
  const parsed = controls.answerBlocks(raw), table = parsed.blocks[0]; assert.equal(table.type, "table"); assert.equal(parsed.raw, raw);
  assert.deepEqual(table.rows.map(row => row.map(partsText)), [["32 mm", "−0.0012300", "UNKNOWN", "NOT_RELEASED"], ["38 mm", "2.0e-08", "FAIL", "가상 재료"]]);
  const h = harness(), card = new TinyNode(); h.ui.appendResearchAnswer(card, raw, "empty");
  const values = walk(card.children[0]).filter(node => node.tagName === "TD"); assert.deepEqual(values.map(node => node.textContent), table.rows.flat().map(partsText));
  assert(walk(values[3]).some(node => node.tagName === "CODE" && node.textContent === "NOT_RELEASED"));
  for (const partial of ["|a|b|\n|---|---|\n|1.000|", "|a|b|\n|---|---|\n|`1|2`|UNKNOWN|"]) {
    const unknown = controls.answerBlocks(partial); assert.equal(unknown.raw, partial); assert.equal(unknown.blocks[0].type, "paragraph"); assert(blockText(unknown.blocks[0]).includes("UNKNOWN") || blockText(unknown.blocks[0]).includes("1.000"));
  }
});
test("technical fences keep exact CRLF/JSON/numbers in collapsed text only, including incomplete output", () => {
  const technical = '```json\r\n{"value":-0.000123456789,"status":"NOT_RELEASED","unsafe":"<script>run()</script>"}\r\n```\r\n';
  const parsed = controls.answerBlocks(technical); assert.equal(parsed.raw, technical); assert.equal(parsed.blocks[0].type, "technical"); assert.equal(parsed.blocks[0].text, technical);
  const h = harness(), card = new TinyNode(); h.ui.appendResearchAnswer(card, technical, "empty");
  const detail = card.children[0].children[0]; assert.equal(detail.tagName, "DETAILS"); assert.equal(detail.open, undefined);
  assert.equal(walk(detail).find(node => node.tagName === "PRE").textContent, technical);
  const incomplete = "```json\n{\"value\":1.234567890123"; assert.equal(controls.answerBlocks(incomplete).blocks[0].text, incomplete);
});
test("untrusted HTML/scripts/unsafe Markdown links stay inert text; actual experiment route remains metadata-bound", () => {
  const raw = '<img src=x onerror=alert(1)> <script>throw 1</script>\n\n[실험](javascript:alert(1)) [data](data:text/html,unsafe) **UNKNOWN**';
  const h = harness(), record = { id: "J-fixture", operation: "research_run", store_id: "local", status: "COMPLETED", result: payload(raw) };
  h.ui.retainResearchJob(record); const body = walk(h.$("researchAnswers")).find(node => node.classList.contains("research-answer-text"));
  const nodes = walk(body); assert.equal(nodes.filter(node => ["A", "IMG", "SCRIPT", "IFRAME", "OBJECT"].includes(node.tagName)).length, 0);
  assert.match(body.textContent, /javascript:alert\(1\)/); assert.match(body.textContent, /<script>/);
  assert.equal(nodes.some(node => Object.keys(node.attributes).some(key => /^on|href|src/.test(key))), false);
  const actualLink = walk(h.$("researchAnswers")).find(node => node.tagName === "BUTTON" && node.dataset.experimentId === "E-cad"); assert(actualLink); assert.equal(actualLink.title, "E-cad");
  assert(walk(h.$("researchAnswers")).some(node => node.dataset.status === "NOT_RELEASED")); assert.deepEqual(h.counters, { http: 0, timers: 0 });
});
test("partial and final answers share exact formatter/DOM path; original result/failed tool/UNKNOWN are retained", () => {
  const raw = "**미확인** `UNKNOWN` · `NOT_RELEASED`\n\n1. 실제 부분 답변\n2. 1.5000 mm";
  const h = harness(), progress = { session_id: "ses_Partial123", model: controls.MODEL, answer: raw,
    tools: [{ tool: "caelab_analysis_run", status: "FAILED_EXECUTION", experiment_id: "E-failed" }], cleanup_pending: false, completion_is_engineering_approval: false, decision: "NOT_RELEASED" };
  h.ui.state.job = { id: "J-fixture", operation: "research_run", store_id: "local", status: "RUNNING", progress }; h.ui.renderJob();
  const partialBody = walk(h.$("researchAnswers")).find(node => node.classList.contains("research-answer-text")); const before = JSON.stringify(progress);
  assert.equal(h.ui.confirmedResearchSession(), null); assert.equal(h.$("researchContinue").disabled, true);
  const result = payload(raw); result.tools = progress.tools;
  h.ui.state.job = { ...h.ui.state.job, status: "FAILED", result: { ...result, status: "FAILED" } }; h.ui.renderJob();
  const finalBody = walk(h.$("researchAnswers")).find(node => node.classList.contains("research-answer-text")); assert.deepEqual(shape(finalBody), shape(partialBody));
  assert.equal(JSON.stringify(progress), before); assert.equal(h.ui.state.job.result.answer, raw); assert.equal(h.$("jobStatus").dataset.status, "FAILED");
  assert.equal(h.$("jobPanel").classList.contains("finished"), false); assert(walk(h.$("researchAnswers")).some(node => node.dataset.status === "FAILED_EXECUTION"));
});
test("formatting preserves actual busy/read-only/cancel/cleanup gates and never admits a completed progress session", () => {
  const h = harness(); h.ui.updateControls(); assert.equal(h.$("researchRunBtn").disabled, false);
  for (const code of ["RUNNING", "CANCEL_REQUESTED", "CLEANUP_PENDING"]) {
    h.ui.state.job = { id: "J-fixture", operation: "research_run", store_id: "local", status: code, progress: { session_id: "ses_Partial123", model: controls.MODEL,
      answer: FIRST_ANSWER, tools: [], cleanup_pending: true, completion_is_engineering_approval: false, decision: "NOT_RELEASED" } }; h.ui.renderJob();
    assert.equal(h.$("researchRunBtn").disabled, true); assert.equal(h.$("researchContinue").disabled, true); assert.equal(h.$("jobCancelBtn").hidden, false);
    assert.equal(h.$("jobCancelBtn").disabled, code === "CANCEL_REQUESTED"); assert.equal(h.$("jobStatus").dataset.status, code);
  }
  assert.equal(h.$("jobCancelBtn").textContent, "종료 재시도");
  const library = harness({ store: "library", writable: false }); library.ui.updateControls(); assert.equal(library.$("researchRunBtn").disabled, true);
  assert.deepEqual(h.counters, { http: 0, timers: 0 }); assert.deepEqual(library.counters, { http: 0, timers: 0 });
});
test("browser/CommonJS formatter agree and scoped styles keep wrapping/spacing without an HTML engine", () => {
  const browser = { window: {}, URL, TextEncoder }; vm.runInNewContext(readFileSync(require.resolve("../apps/lab/static/research-controls.js"), "utf8"), browser);
  assert.equal(JSON.stringify(browser.window.researchControls.answerBlocks(FIRST_ANSWER)), JSON.stringify(controls.answerBlocks(FIRST_ANSWER)));
  assert.match(styleSource, /\.research-answer-formatted\{white-space:normal\}/); assert.match(styleSource, /\.research-answer-formatted>p\{white-space:pre-wrap/);
  assert.match(styleSource, /\.research-answer-list>li\{display:grid/);
  assert.doesNotMatch(appSource.slice(appSource.indexOf("function appendResearchAnswer("), appSource.indexOf("function appendResearchTools(")), /innerHTML|eval\(|href\s*=/);
});

test("actual completed response error is visible while raw completion/confirmed continuation and failure/cancel precedence stay intact", () => {
  const h = harness(), result = payload("도구 실행을 완료하지 못했습니다. **UNKNOWN**, `NOT_RELEASED` 유지");
  result.error = Array(6).fill("CAE native guard denied this operation.").join("\n");
  result.tools = Array(6).fill(null).map(() => ({ tool: "caelab_analysis_run", status: "error" }));
  const before = JSON.stringify(result); h.ui.state.researchContexts.set("J-fixture", { question: result.question, store: "local" });
  h.ui.state.job = { id: "J-fixture", operation: "research_run", status: "COMPLETED", store_id: "local", result }; h.ui.renderJob();
  assert.equal(h.$("jobStatus").textContent, "AI 연구 중 오류 발생"); assert.equal(h.$("jobStatus").dataset.status, "COMPLETED");
  assert.equal(h.$("jobPanel").classList.contains("finished"), false); assert.equal(h.$("jobPanel").classList.contains("failed"), true);
  assert.match(h.$("researchAnswers").textContent, /AI 연구 중 오류가 발생했습니다/);
  assert.equal(h.ui.confirmedResearchSession(), result.session_id); assert.equal(h.$("researchContinue").disabled, false);
  assert.equal(JSON.stringify(result), before); assert.equal(h.ui.state.job.result.status, "COMPLETED"); assert.equal(h.ui.state.job.result.decision, "NOT_RELEASED");
  for (const code of ["FAILED", "CANCELLED"]) {
    h.ui.state.job = { ...h.ui.state.job, status: code }; h.ui.renderJob();
    assert.equal(h.$("jobStatus").textContent, code === "FAILED" ? "AI 연구 실패" : "AI 연구 취소 완료"); assert.equal(h.$("researchContinue").disabled, true);
  }
  for (const error of [undefined, "", "  "]) assert.equal(controls.jobWorkflow({ status: "COMPLETED", result: { ...payload(), error } }).stage, "AI 응답 받음 · 결과 검토 필요");
});
test("only supplied known phase metadata adds secondary Korean wording with zero status/gate effect", () => {
  const h = harness(), base = { id: "J-phase", operation: "research_run", store_id: "local", status: "RUNNING", progress: {
    session_id: null, model: controls.MODEL, answer: "", tools: [], cleanup_pending: false, completion_is_engineering_approval: false, decision: "NOT_RELEASED" } };
  for (const phase of ["RUNTIME_VERIFY", "RESIDENT_VERIFY", "CLI_PREFLIGHT", "END_VERIFY"]) {
    h.ui.state.job = { ...base, progress: { ...base.progress, phase } }; h.ui.renderJob();
    assert.equal(h.$("jobMessage").children.at(-1).className, "research-phase"); assert.equal(h.$("jobMessage").children.at(-1).textContent, controls.phaseLabel(phase));
    assert.equal(h.$("jobStatus").dataset.status, "RUNNING"); assert.equal(h.$("jobStatus").textContent, "AI 연구 실행 중");
    assert.equal(h.$("researchRunBtn").disabled, true); assert.equal(h.$("jobCancelBtn").disabled, false);
  }
  for (const phase of [undefined, null, "FUTURE_PHASE", "constructor", "toString", {}, true]) {
    h.ui.state.job = { ...base, progress: { ...base.progress, phase } }; h.ui.renderJob();
    assert.equal(h.$("jobMessage").children.some(node => node.className === "research-phase"), false); assert.equal(controls.phaseLabel(phase), null);
  }
  h.ui.state.job = { ...base, status: "COMPLETED", result: payload(), progress: { ...base.progress, phase: "END_VERIFY" } }; h.ui.renderJob();
  assert.equal(h.$("jobMessage").children.some(node => node.className === "research-phase"), false); assert.deepEqual(h.counters, { http: 0, timers: 0 });
});

test("observed capability wire aliases share tool labels without inventing operations or altering availability", () => {
  const h = harness(), operations = ["parameters_discover", "parameters_register", "experiment_run"];
  h.ui.state.researchStatus.capabilities = [{ backend: "fixture.cadquery", operations }];
  const before = JSON.stringify(h.ui.state.researchStatus), view = controls.statusView(h.ui.state.researchStatus);
  assert.equal(view.ready, true); assert.deepEqual(view.scopes[0].operations, ["CAD 변수 확인", "연구 변수 등록", "CAD 생성·검사"]);
  operations.forEach((operation, i) => assert.equal(controls.toolView({ tool: "caelab_" + operation, status: "completed" }).label, view.scopes[0].operations[i]));
  h.ui.renderResearchConnection(); assert.match(h.$("researchScope").textContent, /CAD 변수 확인 · 연구 변수 등록 · CAD 생성·검사/);
  assert.doesNotMatch(h.$("researchScope").textContent, /등록된 도구/); assert.equal(JSON.stringify(h.ui.state.researchStatus), before);
  const unknown = controls.statusView({ ...h.ui.state.researchStatus, capabilities: [{ backend: "fixture.cadquery", operations: ["not_a_tool", "constructor"] }] });
  assert.deepEqual(unknown.scopes[0].operations, ["등록된 도구", "등록된 도구"]);
  assert.equal(controls.statusView({ ...h.ui.state.researchStatus, available: false }).ready, false); assert.deepEqual(h.counters, { http: 0, timers: 0 });
});

test("received human-05 answer or valid tool status hides stale preparation wording, preserving END_VERIFY and active/cleanup gates", () => {
  // Exact retained human-05/progress-03.json job.progress, SHA256
  // 50197ee339efdffa376ae250f5e0a5aecb4b529875d09cc47b5a6a66abf39c73.
  // Its tools array is empty; tool-only controls below are distinct fixtures.
  const observed = { session_id: null,
    answer: "계획은 다음과 같습니다.\n\n1. 새 연구 기록을 만들고 `roller_support`의 실제 CAD 파라미터 경로·현재값·허용범위를 먼저 조회합니다.\n2. 요청된 변수인 지지대 폭만 등록합니다. 롤러 지름 8.3 mm와 나머지 치수는 등록하지 않고 CAD 기본값을 유지합니다.\n3. 폭 32 mm CAD와 38 mm CAD를 각각 새 불변 실험으로 생성하고 검증 결과를 확인합니다.\n4. 각 검증된 CAD를 부모로 삼아 **순서대로** CalculiX 해석을 실행합니다. 해석은 4→3→2 mm 메시, 지지대당 100 N의 총 하향(-Z) 하중, 제시된 가상 직교이방성 물성을 그대로 사용합니다.\n5. 동일 기록에서 처짐, 최종 두 메시의 처짐 변화(허용 기준 ≤5%), X/Y/Z 각 축의 **부호 있는** 반력 평형(허용 기준 ≤1%)을 읽어 비교합니다.\n\n지원되는 경계 이상화는 요청하신 그대로, 한 개 지지대의 아래면 X/Y/Z 완전 고정과 안장 중앙 24 mm 구간의 테셀레이션 면적 비례 총 -Z 100 N 분포입니다. 이는 볼트 체결·접촉·회전을 재현하지 않습니다. 직교이방성 축은 전역 CAD X/Y/Z이며, Z를 가상 적층 방향으로 선언하되 별도 재료 회전은 적용하지 않습니다. 피크 응력은 유효한 강도 지표가 아니며, 세 메시만으로 점근 수렴을 입증하지 않습니다.",
    tools: [], cleanup_pending: true, model: "openai-codex/gpt-5.6-sol", completion_is_engineering_approval: false,
    decision: "NOT_RELEASED", phase: "CLI_PREFLIGHT", phase_started_utc: "2026-10-04T15:01:42.5045545Z" };
  assert.equal(observed.answer.length, 661); assert.equal(controls.progressView(observed).valid, true);
  assert.match(controls.phaseLabel(observed.phase), /질문을 보내기 전에/); // One-argument compatibility.
  const h = harness(), base = { id: "J-phase-observed", operation: "research_run", store_id: "local", status: "RUNNING" };
  const hasPhase = () => h.$("jobMessage").children.some(node => node.className === "research-phase");
  const signals = [observed, { ...observed, answer: " \n", tools: [{ tool: "caelab_study_create", status: "completed" }] }];
  for (const signal of signals) {
    for (const phase of ["RUNTIME_VERIFY", "RESIDENT_VERIFY", "CLI_PREFLIGHT"]) {
      const progress = { ...signal, phase }, before = JSON.stringify(progress);
      h.ui.state.job = { ...base, progress }; h.ui.renderJob();
      assert.equal(controls.phaseLabel(phase, progress), null); assert.equal(hasPhase(), false);
      assert.equal(h.$("jobStatus").textContent, "AI 연구 실행 중"); assert.equal(h.$("jobStatus").dataset.status, "RUNNING");
      assert.equal(h.$("researchRunBtn").disabled, true); assert.equal(h.$("researchContinue").disabled, true);
      assert.equal(h.$("jobCancelBtn").hidden, false); assert.equal(h.$("jobCancelBtn").disabled, false);
      assert.equal(h.ui.confirmedResearchSession(), null); assert.equal(JSON.stringify(progress), before);
      if (signal === observed) assert(walk(h.$("researchAnswers")).some(node => node.tagName === "PRE" && node.textContent === observed.answer));
    }
  }
  for (const progress of [
    { ...observed, answer: " \n", tools: [] },
    { ...observed, answer: " \n", tools: [{ tool: "caelab_study_create", status: 1 }, null, { tool: "caelab_study_create", status: " " }] },
    { ...observed, model: "unverified-model" }, { ...observed, tools: null },
  ]) {
    h.ui.state.job = { ...base, progress }; h.ui.renderJob();
    assert.equal(controls.phaseLabel("CLI_PREFLIGHT", progress), controls.phaseLabel("CLI_PREFLIGHT")); assert.equal(hasPhase(), true);
  }
  for (const status of ["RUNNING", "CANCEL_REQUESTED", "CLEANUP_PENDING"]) {
    h.ui.state.job = { ...base, status, progress: { ...observed, phase: "END_VERIFY" } }; h.ui.renderJob();
    assert.equal(hasPhase(), true); assert.equal(h.$("jobMessage").children.at(-1).textContent, controls.phaseLabel("END_VERIFY"));
    assert.equal(h.$("jobStatus").dataset.status, status); assert.equal(h.$("jobStatus").textContent, status === "RUNNING" ? "AI 연구 실행 중" : "AI 연구 종료 확인 중");
    assert.equal(h.$("researchRunBtn").disabled, true); assert.equal(h.$("researchContinue").disabled, true);
    assert.equal(h.$("jobCancelBtn").disabled, status === "CANCEL_REQUESTED"); assert.equal(h.ui.confirmedResearchSession(), null);
  }
  for (const phase of ["FUTURE_PHASE", "constructor", null, {}, true]) assert.equal(controls.phaseLabel(phase, observed), null);
  assert.deepEqual(h.counters, { http: 0, timers: 0 });
});
