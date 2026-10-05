"use strict";

// Human controls over the allowlisted Core API. All record text is untrusted.
const $ = (id) => document.getElementById(id);
const state = {
  overview: null, presets: {}, studyId: "", study: null, registry: { entries: [] },
  discovery: [], job: null, submitting: false, pollTimer: null, handlers: new Map(),
  selectedExperiment: null, selectedCampaign: null, comparison: new Set(), studyRequest: 0,
  experimentRequest: 0, campaignRequest: 0, viewer: null, fixtureViewer: null, fixtureConditionError: null, storeSwitching: false,
  modelDiscovery: [], modelContext: "", modelRequest: 0,
  importedLevels: [], importedMeshError: null, importedRequest: 0, importedLoading: false,
  campaignSelections: new Map(), campaignSelectionKey: "", campaignDrafts: {}, campaignTarget: "cad", cadCampaignType: "doe",
  researchStatus: null, researchStatusError: null, researchStatusRequest: 0, researchLoading: false,
  researchHistory: new Map(), researchContexts: new Map(), researchSession: null,
  simulationDraft: null,
  researchPurposeDraft: {},
  observationRequest: 0,
  observationId: "",
};
const operationNames = {
  study_create: "연구 만들기", parameter_discover: "CAD 변수 발견", parameter_register: "연구 변수 등록",
  registry_refresh: "원본 CAD 등록부 갱신", cad_run: "CAD 실험", native_create: "네이티브 모델 만들기",
  native_inspect: "네이티브 모델 확인", native_final: "최종 솔리드 선택", analysis_run: "CAD 구조 해석",
  pde_run: "선언한 weak form 실행", model_analysis_run: "선언한 모델·재료·동해석",
  doe_plan: "DOE 계획 저장", doe_run: "DOE 실행", optimization_plan: "최적화 계획 저장",
  optimization_run: "수치 최적화 실행",
  model_parameters_discover: "모델 입력 발견·환경 확인", model_parameters_register: "모델 연구 변수 등록",
  model_optimization_plan: "해석 모델 최적화 계획 저장",
  research_run: "AI 연구 질문",
  response_comparison_save: "관측·시험 기준 비교 저장",
};
const readOperations = new Set(["parameter_discover", "native_inspect", "model_parameters_discover"]);
const labels = {
  PASS: "통과", FAIL: "조건 미충족", UNKNOWN: "미확인", WARNING: "검토 필요",
  NOT_RELEASED: "공학적 사용 미승인", RELEASED: "공학적 사용 승인", VERIFIED: "기록·원본 일치",
  NOT_CHECKED: "기록 확인 전", IMPLEMENTED: "구현됨", EXPERIMENTAL: "실험 범위", PLANNED: "계획됨",
  RUNNING: "실행 중", CANCEL_REQUESTED: "취소 처리 중", CANCELLED: "취소 완료",
  CLEANUP_PENDING: "종료 확인 중", RECOVERY_REQUIRED: "실행 상태 확인 필요",
  COMPLETED: "실행 완료", FAILED: "작업 실패", REJECTED: "조건 미충족",
  FAILED_EXECUTION: "실행 실패", COMPLETED_REVIEW_REQUIRED: "완료 · 검토 필요", NO_FEASIBLE_DESIGN: "유효한 후보 없음",
  CONVERGED: "수치 수렴", MAX_GENERATIONS: "세대 예산 종료", NOT_RUN: "실행 안 함",
};

function el(tag, text, className) {
  const item = document.createElement(tag);
  if (text !== undefined && text !== null) item.textContent = String(text);
  if (className) item.className = className;
  return item;
}
function clear(target) {
  const item = typeof target === "string" ? $(target) : target;
  item.replaceChildren();
  return item;
}
function list(value) { return Array.isArray(value) ? value : (value && typeof value === "object" ? Object.values(value) : []); }
function text(value) {
  if (value === null || value === undefined) return "—";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}
function pretty(value) { return JSON.stringify(value, null, 2) ?? "—"; }
function number(value) {
  if (typeof value !== "number") return text(value);
  if (!Number.isFinite(value)) return "유효한 유한값 아님";
  if (value === 0) return "0";
  if (Math.abs(value) < 0.0001 || Math.abs(value) >= 1e7) return value.toExponential(7).replace(/0+e/, "e").replace(/\.e/, "e");
  return new Intl.NumberFormat("ko-KR", { maximumSignificantDigits: 10 }).format(value);
}
function badge(status, override) {
  const code = String(status ?? "UNKNOWN");
  const kind = ["PASS", "VERIFIED", "RELEASED"].includes(code) ? "pass"
    : ["FAIL", "FAILED", "REJECTED", "FAILED_EXECUTION", "NO_FEASIBLE_DESIGN"].includes(code) ? "fail"
      : ["UNKNOWN", "WARNING", "NOT_RELEASED"].includes(code) ? "unknown"
        : ["RUNNING", "CANCEL_REQUESTED", "CLEANUP_PENDING", "PLANNED"].includes(code) ? "pending" : code === "EXPERIMENTAL" ? "experimental" : "neutral";
  const item = el("span", override ?? labels[code] ?? code, `badge ${kind}`);
  item.dataset.status = code; item.title = code;
  return item;
}
function action(label, handler, className = "button subtle compact") {
  const button = el("button", label, className);
  button.type = "button";
  button.addEventListener("click", () => Promise.resolve().then(handler).catch((error) => notify(error.message)));
  return button;
}
function link(label, path, className = "text-link", download = false) {
  const item = el("a", label, className);
  item.href = path;
  if (download) item.setAttribute("download", "");
  else { item.target = "_blank"; item.rel = "noopener"; }
  return item;
}
function table(headers, rows) {
  const wrapper = el("div", undefined, "table-scroll");
  const item = el("table");
  const head = el("thead");
  const heading = el("tr");
  headers.forEach((title) => { const th = el("th", title); th.scope = "col"; heading.append(th); });
  head.append(heading);
  const body = el("tbody");
  rows.forEach((cells) => {
    const row = el("tr");
    cells.forEach((content) => {
      const cell = el("td");
      if (content instanceof Node) cell.append(content);
      else cell.textContent = text(content);
      row.append(cell);
    });
    body.append(row);
  });
  item.append(head, body); wrapper.append(item); return wrapper;
}
function rawDetail(label, value) {
  const detail = el("details", undefined, "raw-detail");
  detail.append(el("summary", label), el("pre", pretty(value)));
  return detail;
}
function panel(title, eyebrow) {
  const card = el("article", undefined, "card");
  if (eyebrow) card.append(el("p", eyebrow, "eyebrow"));
  card.append(el("h2", title));
  return card;
}
function notify(message, success = false) {
  $("notice").hidden = false; $("notice").classList.toggle("success", success);
  $("noticeText").textContent = message;
}
function makeId(prefix) { return `${prefix}-lab-${Date.now().toString(36)}`; }
function idPath(identifier) { return encodeURIComponent(identifier); }
function artifactUrl(identifier, path) { return `/api/artifacts/${idPath(identifier)}?${new URLSearchParams({ path })}`; }
function writable() {
  if (!state.overview) return false;
  const active = typeof state.overview.active_store === "object" ? state.overview.active_store.id : state.overview.active_store;
  return list(state.overview.stores).find((store) => store.id === active)?.writable === true;
}
function activeStore() { return typeof state.overview?.active_store === "object" ? state.overview.active_store.id : state.overview?.active_store; }
function activeJob(job) { return ["RUNNING", "CANCEL_REQUESTED", "CLEANUP_PENDING"].includes(job?.status); }
function recoveryRequired() { return state.overview?.execution?.state === "RECOVERY_REQUIRED" || state.job?.status === "RECOVERY_REQUIRED"; }
function busy() { return state.submitting || state.storeSwitching || activeJob(state.job) || recoveryRequired() || state.overview?.execution?.accepting_jobs === false; }
function viewBusy() { return state.submitting || activeJob(state.job) || state.storeSwitching; }
function available(operation) {
  const matching = list(state.overview?.capabilities).filter((item) => item.operation === operation);
  return !matching.length || matching.some((item) => item.callable === true);
}
function workflowContext(value, kind = "experiment", integrity = "NOT_CHECKED") {
  const result = kind === "job" ? value?.result : value;
  const backend = result?.provenance?.adapter ?? result?.backend;
  const preset = state.presets[$("simulationPreset").value];
  return { kind, integrity, writable: writable(), busy: busy(), analysisAvailable: available("analysis_run"),
    eligibleParent: window.cadControls.eligibleParent(preset, { ...result, backend }) };
}
function option(select, value, label) { const item = el("option", label); item.value = value; select.append(item); }
function researchPurpose(purpose) {
  if (purpose === "defect") return {
    name: "제품 불량 재현 연구",
    question: "관찰한 불량의 위치·형태: [입력]\n발생 조건과 정상 조건의 차이: [입력]\n측정/사진/시험의 출처와 단위: [입력]\n질문: 어떤 조건과 메커니즘이 이 현상을 재현하고 다른 원인 가설과 구별되는가?",
    hypothesis: "H1: [원인 가설과 모델에서 바꿀 조건]\nH2: [경쟁 원인 가설과 모델에서 바꿀 조건]\n가설을 구별할 관찰량/조건: [입력]",
    objective: "불량 위치·변형 모양·발생 시점/하중·응답 이력을 관찰과 비교한다. 비교 위치/방향/단위·허용 오차와 다른 조건에서 확인할 응답은 [입력]. 설명하지 못한 현상과 다음 구별 시험을 남긴다.",
  };
  if (purpose === "jig") return {
    name: "제작 전 시험 지그 검토",
    question: "시험 목적과 시험체: [입력]\n지그 CAD/체결/접촉·장착 조건: [입력]\n장비의 하중/스트로크 범위와 출처: [입력]\n질문: 제작 전에 원하는 하중·구속을 전달하고 시험체 응답을 측정할 수 있는가?",
    hypothesis: "설계안 A: [하중 경로·접촉/체결·지그 강성]\n설계안 B: [바꿀 조건 또는 설계]\n시험체 응답을 왜곡할 수 있는 지그 변형/미끄럼: [입력]",
    objective: "간섭·장착, 하중 전달/반력, 접촉·미끄럼, 지그와 시험체의 변형, 장비 하중/스트로크 요구량을 비교한다. 시험 목적별 허용값과 출처는 [입력]. 미확인 항목과 제작 전 필요한 확인을 남긴다.",
  };
  throw new Error("연구 목적을 선택하세요.");
}
function prepareResearchPurpose(purpose) {
  const draft = researchPurpose(purpose);
  const fields = { studyName: draft.name, studyQuestion: draft.question, studyHypothesis: draft.hypothesis, studyObjective: draft.objective,
    researchQuestion: `${draft.question}\n\n비교할 가설:\n${draft.hypothesis}\n\n연구 목적:\n${draft.objective}\n\n입력하지 않은 조건은 미확인으로 두고, 지원되는 모델·도구 범위와 필요한 정보를 먼저 확인해 주세요.` };
  let filled = 0;
  for (const [id, value] of Object.entries(fields)) {
    if (!$(id).value.trim() || $(id).value === state.researchPurposeDraft[id]) { $(id).value = value; filled++; }
  }
  state.researchPurposeDraft = fields;
  location.hash = "research";
  notify(filled ? "빈 질문에 연구 작성 틀을 넣었습니다. 관찰·조건을 입력해 주세요. 실행은 시작하지 않았습니다." : "작성 중인 질문을 유지했습니다. 새 질문을 준비하려면 해당 입력을 비운 뒤 목적을 선택하세요.", true);
}
function selectedEntries() {
  const backend = $("cadBackend").value, model = $("cadModel").value.trim();
  return list(state.registry?.entries).filter((item) => item.native?.backend === backend &&
    (item.native.document === model || item.native.document === `${model}.py`));
}
function isModelCampaign() { return $("campaignTarget").value === "model"; }
function modelContext() {
  const preset = state.presets[$("modelCampaignPreset").value];
  if (!preset?.declared_inputs) throw new Error("선언된 입력 변수를 지원하는 모델을 선택하세요.");
  const settings = parseField("modelCampaignSettings", "object");
  return { backend: preset.backend, settings, key: JSON.stringify([activeStore(), state.studyId, $("modelCampaignPreset").value, preset.backend, settings]) };
}
function currentModelDiscovery() {
  try { return state.modelDiscovery.length > 0 && state.modelContext === modelContext().key; }
  catch { return false; }
}
function modelCampaignEntries() {
  if (!currentModelDiscovery()) return [];
  return window.campaignControls.eligibleModelEntries(list(state.registry.entries), state.modelDiscovery, modelContext().backend);
}
function invalidateModelDiscovery() {
  state.modelDiscovery = []; state.modelContext = ""; state.modelRequest++;
  renderModelDiscovery(); renderCampaignVariables();
}

async function api(path, options = {}) {
  const headers = { Accept: "application/json", ...(options.headers ?? {}) };
  if (options.method === "POST") {
    headers["Content-Type"] = "application/json";
    headers["X-CAE-Token"] = state.overview?.token ?? "";
  }
  const response = await fetch(path, { cache: "no-store", ...options, headers });
  let data;
  try { data = await response.json(); } catch { throw new Error(`서버 응답을 읽을 수 없습니다 (${response.status}).`); }
  if (!response.ok) throw new Error(text(data.error ?? data.message ?? `요청 실패 (${response.status})`));
  return data;
}
function parseField(id, kind) {
  let value;
  try { value = JSON.parse($(id).value); } catch { throw new Error(`${$(id).closest("label")?.firstChild?.textContent?.trim() || "설정"}: JSON 형식을 확인하세요.`); }
  function finite(item) {
    if (typeof item === "number" && !Number.isFinite(item)) throw new Error("설정에는 유한한 숫자만 입력할 수 있습니다.");
    if (item && typeof item === "object") Object.values(item).forEach(finite);
  }
  finite(value);
  if (kind === "object" && (!value || typeof value !== "object" || Array.isArray(value))) throw new Error("설정은 JSON 객체여야 합니다.");
  if (kind === "array" && !Array.isArray(value)) throw new Error("제약은 JSON 배열이어야 합니다.");
  if (kind === "nullable-object" && value !== null && (!value || typeof value !== "object" || Array.isArray(value))) throw new Error("초기 후보는 JSON 객체 또는 null이어야 합니다.");
  return value;
}
function numeric(id) { const value = Number($(id).value); if (!$(id).value.trim() || !Number.isFinite(value)) throw new Error("유한한 숫자를 입력하세요."); return value; }

function researchContext() { return { local: activeStore() === "local", writable: writable(), busy: busy() }; }
function confirmedResearchSession() {
  if (activeJob(state.job)) return null;
  const session = state.researchSession;
  return session?.jobStatus === "COMPLETED" && window.researchControls.canContinue(session.result, state.researchStatus,
    { ...researchContext(), resultStore: session.store, activeStore: activeStore() }) ? session.result.session_id : null;
}
function updateResearchControls() {
  if (!$('researchRunBtn')) return;
  const sessionId = confirmedResearchSession(), checked = $("researchContinue").checked;
  $("researchContinue").disabled = busy() || !sessionId;
  if (!sessionId) $("researchContinue").checked = false;
  $("researchResetBtn").disabled = busy(); $("researchQuestion").disabled = busy();
  let inputError = null;
  try { window.researchControls.request($("researchQuestion").value, checked && sessionId ? sessionId : undefined); }
  catch (error) { inputError = error.message; }
  const runnable = !state.researchLoading && window.researchControls.canRun(state.researchStatus, researchContext());
  $("researchRunBtn").disabled = !runnable || Boolean(inputError);
  $("researchSessionState").textContent = sessionId
    ? ($("researchContinue").checked ? "확인된 대화의 맥락을 이어 질문합니다." : "새 대화로 질문합니다. 이전 답변은 아래에 보존됩니다.")
    : "새 대화로 질문합니다. 확인되지 않은 대화는 이어서 실행하지 않습니다.";
  $("researchInputState").textContent = recoveryRequired() ? "이전 작업의 완료·중단 여부를 확인해야 합니다. 보존된 답변과 결과를 먼저 확인하세요."
    : busy() ? "현재 작업의 종료를 확인한 뒤 질문할 수 있습니다."
    : !writable() || activeStore() !== "local" ? "질문을 실행하려면 작업 저장소로 전환하세요."
      : state.researchLoading ? "AI 연구 연결을 확인하고 있습니다."
        : !runnable ? window.researchControls.statusView(state.researchStatus).reason : inputError ?? "질문만 입력하면 됩니다. 연구 ID·가설·목적을 먼저 작성할 필요는 없습니다.";
}
function renderResearchConnection() {
  const view = window.researchControls.statusView(recoveryRequired() ? { state: "RECOVERY_REQUIRED" } : state.researchStatus), target = clear("researchConnection");
  target.append(el("strong", view.ready || view.recovery ? view.modelLabel : "AI 연구 연결 대기"), el("p", view.reason));
  if (view.workspaceUrl) target.append(link("연결된 OpenScience 열기 →", view.workspaceUrl));
  const scope = clear("researchScope");
  if (view.ready && view.scopes.length) {
    scope.append(el("strong", "이 연결에서 지원하는 범위")); const items = el("ul");
    view.scopes.forEach(item => items.append(el("li", `${item.label}: ${item.operations.join(" · ") || "지원 작업 확인 필요"}`)));
    scope.append(items);
  } else scope.append(el("p", "연결을 확인하면 실제 지원 범위가 나타납니다.", "hint"));
  $("researchConnectionJson").textContent = pretty(state.researchStatusError ? { status: state.researchStatus, error: state.researchStatusError } : state.researchStatus);
  updateResearchControls();
}
async function loadResearchStatus() {
  const request = ++state.researchStatusRequest; state.researchLoading = true; updateResearchControls();
  try {
    const status = await api("/api/research");
    if (request !== state.researchStatusRequest) return;
    state.researchStatus = status; state.researchStatusError = null;
  } catch (error) {
    if (request !== state.researchStatusRequest) return;
    state.researchStatus = { configured: false, available: false, state: "UNAVAILABLE", reason: "AI 연구 연결을 확인할 수 없습니다. 새로고침한 뒤 다시 확인하세요." };
    state.researchStatusError = error.message;
  } finally {
    if (request === state.researchStatusRequest) { state.researchLoading = false; renderResearchConnection(); }
  }
}
function retainResearchJob(job) {
  if (job?.operation !== "research_run" || !job.result) return;
  const context = state.researchContexts.get(job.id);
  const store = typeof job.store_id === "string" ? job.store_id : null;
  const view = window.researchControls.responseView(job.result, context ?? {});
  state.researchHistory.set(job.id, { job, store, view, bound: Boolean(store && (!context || context.store === store)) });
  if (context && job.id === state.job?.id) state.researchSession = { result: view.valid ? job.result : null, store, jobStatus: job.status };
  renderResearchAnswers();
}
function renderResearchAnswers() {
  const target = clear("researchAnswers"), records = [...state.researchHistory.values()].reverse();
  const current = state.job;
  const hasProgress = current?.operation === "research_run" && activeJob(current) && current.progress;
  if (hasProgress) {
    const view = window.researchControls.progressView(current.progress), workflow = window.researchControls.jobWorkflow(current);
    const card = el("section", undefined, "research-answer"), heading = el("div", undefined, "research-answer-heading");
    heading.append(badge(current.status, workflow.stage), badge(current.progress?.decision)); card.append(heading);
    if (view.valid) {
      const context = state.researchContexts.get(current.id);
      if (typeof context?.question === "string") card.append(el("h3", "보낸 질문"), el("p", context.question, "research-question-text"));
      card.append(el("h3", "수신 중인 실제 AI 답변"));
      appendResearchAnswer(card, view.answer, "아직 받은 답변이 없습니다. 반환된 도구 상태를 아래에서 확인하세요.");
      appendResearchTools(card, view.tools, current.store_id, Boolean(typeof current.store_id === "string" && (!context || context.store === current.store_id)), "아직 반환된 도구 기록이 없습니다.");
      card.append(el("small", "실행 중인 부분 기록입니다. 최종 응답이 확인되기 전에는 대화를 이어 실행하지 않습니다. 각 실험의 미확인·실패 판정은 그대로 유지됩니다."));
    } else card.append(el("p", view.reason, "metric-reason"));
    card.append(rawDetail("현재 진행·작업 원본 기록", current)); target.append(card);
  }
  if (!records.length && !hasProgress) {
    target.append(el("p", activeJob(state.job) && state.job?.operation === "research_run"
      ? "AI 연구가 실행 중입니다. 실제 답변과 도구 기록이 반환되면 표시합니다."
      : "질문을 보내면 실제 답변, 도구 상태와 연결된 실험이 여기에 나타납니다.", "empty-state")); return;
  }
  records.forEach(({ job, store, view, bound }) => {
    const card = el("section", undefined, "research-answer"), workflow = window.researchControls.jobWorkflow(job);
    const heading = el("div", undefined, "research-answer-heading"); heading.append(badge(job.status, workflow.stage), badge(job.result?.decision)); card.append(heading);
    if (view.valid) {
      card.append(el("h3", "보낸 질문"), el("p", view.question, "research-question-text"), el("h3", "실제 AI 답변"));
      appendResearchAnswer(card, view.answer, "받은 답변이 없습니다. 아래의 작업 기록에서 실패·취소 근거를 확인하세요.");
      if (view.reason) card.append(el("p", view.reason, "metric-reason"));
      appendResearchTools(card, view.tools, store, bound, "반환된 도구 실행 기록이 없습니다.");
    } else card.append(el("p", view.reason, "metric-reason"));
    card.append(el("small", "AI 응답은 수치 검증이나 공학적 사용 승인을 뜻하지 않습니다. 각 실험의 미확인·실패 판정은 그대로 유지됩니다."));
    card.append(rawDetail("답변·도구·작업 원본 기록", job)); target.append(card);
  });
}
function researchAnswerBlocks(answer) {
  const blocks = [], lines = answer.split(/\r\n|\n|\r/), starts = [0]; let start = 0, fence = null;
  for (const ending of answer.matchAll(/\r\n|\n|\r/g)) starts.push(ending.index + ending[0].length);
  const flush = end => { if (end > start) blocks.push(...window.researchControls.answerBlocks(answer.slice(start, end)).blocks); };
  lines.forEach((line, index) => {
    if (fence) { if (line.trim() === fence) fence = null; return; }
    const technical = /^\s*(`{3,}|~{3,})([^`]*)$/.exec(line);
    if (technical) { fence = technical[1]; return; }
    const heading = /^ {0,3}(#{1,6})[ \t]+(.+)$/.exec(line);
    if (!heading) return;
    flush(starts[index]);
    const parsed = window.researchControls.answerBlocks(heading[2]).blocks[0];
    blocks.push({ type: "heading", level: Math.min(6, Math.max(3, heading[1].length + 1)),
      parts: parsed?.parts ?? [{ type: "text", text: heading[2] }] });
    start = starts[index + 1] ?? answer.length;
  });
  flush(answer.length); return blocks;
}
function appendResearchAnswer(card, answer, emptyMessage) {
  const body = el("div", undefined, "research-answer-text research-answer-formatted");
  function inline(target, parts) {
    parts.forEach(part => {
      // Remove only paired math delimiters in prose. Keep expression text,
      // signs, units and code unchanged; there is no equation evaluator.
      const value = part.type !== "code" && typeof part.text === "string"
        ? part.text.replace(/\\\(([\s\S]*?)\\\)/g, "$1").replace(/\\\[([\s\S]*?)\\\]/g, "$1") : part.text;
      const item = el(part.type === "strong" ? "strong" : part.type === "em" ? "em" : part.type === "code" ? "code" : "span", value);
      if (part.parts) inline(item, part.parts); target.append(item);
    });
  }
  if (answer && /\\(?:\(|\[)/.test(answer)) body.append(el("p", "수식은 원문 식을 텍스트로 표시합니다. 첨자·지수 표기와 정확한 원문은 ‘AI 답변 원문’에서 확인할 수 있습니다.", "hint research-equation-note"));
  if (!answer) body.append(el("p", emptyMessage));
  else researchAnswerBlocks(answer).forEach(block => {
    if (block.type === "paragraph") { const paragraph = el("p"); inline(paragraph, block.parts); body.append(paragraph); }
    else if (block.type === "heading") { const heading = el(`h${block.level}`); inline(heading, block.parts); body.append(heading); }
    else if (block.type === "list") {
      const items = el(block.ordered ? "ol" : "ul", undefined, "research-answer-list");
      block.items.forEach(entry => {
        const item = el("li"), marker = el("span", entry.marker, "research-list-marker"), content = el("span");
        inline(content, entry.parts); item.append(marker, content); items.append(item);
      }); body.append(items);
    } else if (block.type === "table") {
      const wrapper = el("div", undefined, "table-scroll"), values = el("table"), header = el("thead"), row = el("tr"), rows = el("tbody");
      block.header.forEach(parts => { const cell = el("th"); cell.scope = "col"; inline(cell, parts); row.append(cell); }); header.append(row);
      block.rows.forEach(parts => { const record = el("tr"); parts.forEach(value => { const cell = el("td"); inline(cell, value); record.append(cell); }); rows.append(record); });
      values.append(header, rows); wrapper.append(values); body.append(wrapper);
    } else if (block.type === "technical") {
      const detail = el("details", undefined, "raw-detail"); detail.append(el("summary", "코드·기술 출력 원문"), el("pre", block.text)); body.append(detail);
    }
  });
  card.append(body);
  if (answer) { const original = el("details", undefined, "raw-detail research-answer-original"); original.append(el("summary", "AI 답변 원문"), el("pre", answer)); card.append(original); }
}
function appendResearchTools(card, tools, store, bound, emptyMessage) {
  if (!tools.length) { card.append(el("p", emptyMessage, "hint")); return; }
  card.append(table(["실행한 도구", "실제 상태", "연결된 실험"], tools.map(item => {
    if (!item) return ["도구 기록 확인 필요", badge("UNKNOWN"), "원본 기록에서 확인하세요."];
    const name = el("span", item.label); name.title = item.raw.tool;
    const resultLink = item.experimentId && bound && store === activeStore()
      ? action("실험 결과 보기 →", async () => { await inspectExperiment(item.experimentId); showArea("results"); location.hash = "results"; })
      : el("span", item.experimentId ? "원래 실험 저장소에서 확인하세요." : "연결된 실험 없음");
    if (item.experimentId) { resultLink.dataset.experimentId = item.experimentId; resultLink.title = item.experimentId; }
    return [name, badge(item.status, item.statusLabel), resultLink];
  })));
}
async function submitResearchQuestion() {
  if (state.researchLoading || !window.researchControls.canRun(state.researchStatus, researchContext())) throw new Error("AI 연구 연결과 작업 저장소 상태를 확인한 뒤 질문하세요.");
  const session = confirmedResearchSession();
  if ($("researchContinue").checked && !session) throw new Error("확인된 대화가 없습니다. 새 대화로 질문하세요.");
  const args = window.researchControls.request($("researchQuestion").value, $("researchContinue").checked ? session : undefined);
  await runJob("research_run", args, () => renderResearchAnswers());
}
function researchError(error) {
  state.researchStatusError = error.message; $("researchConnectionJson").textContent = pretty({ status: state.researchStatus, error: error.message });
  notify(window.researchControls.safeMessage(error.message, "AI 연구 요청을 완료하지 못했습니다. 연결 상태와 작업 기록을 확인하세요."));
}

function showArea(name) {
  const selected = ["research", "design", "simulation", "explore", "results"].includes(name) ? name : "research";
  document.querySelectorAll("[data-panel]").forEach((item) => { item.hidden = item.dataset.panel !== selected; });
  document.querySelectorAll("[data-nav]").forEach((item) => {
    const active = item.dataset.nav === selected;
    item.classList.toggle("active", active);
    if (active) item.setAttribute("aria-current", "page"); else item.removeAttribute("aria-current");
  });
  document.title = `${{ research: "연구", design: "설계", simulation: "해석", explore: "탐색", results: "결과·근거" }[selected]} · Autonomous CAE Lab`;
}
function updateControls() {
  const blocked = !writable() || busy();
  document.querySelectorAll("fieldset[data-write]").forEach((item) => { item.disabled = blocked; });
  document.querySelectorAll("fieldset[data-read-job]").forEach((item) => { item.disabled = busy() || !state.overview; });
  document.querySelectorAll("[data-operation]").forEach((item) => { item.disabled = !state.overview || busy() || (!writable() && !readOperations.has(item.dataset.operation)) || !available(item.dataset.operation); });
  $("storeSelect").disabled = viewBusy() || !state.overview;
  $("studySelect").disabled = viewBusy() || !state.overview;
  $("useLocalBtn").disabled = viewBusy();
  const needStudy = ["discoverBtn", "registryRefreshBtn", "simulationRunBtn", "campaignPlanBtn"];
  needStudy.forEach((id) => { if (!state.studyId) $(id).disabled = true; });
  if (!selectedEntries().length) {
    document.querySelector('[data-operation="cad_run"]').disabled = true;
    $("registryRefreshBtn").disabled = true;
  }
  if (!$("nativePath").value || !state.studyId) document.querySelector('[data-operation="parameter_register"]').disabled = true;
  if (!$("nativeFinal").value || !$("nativeModelId").value.trim()) document.querySelector('[data-operation="native_final"]').disabled = true;
  if (!state.presets[$("simulationPreset").value] || (simulationOperation() === "analysis_run" && !$("analysisParent").value)) $("simulationRunBtn").disabled = true;
  if (state.simulationDraft && (state.simulationDraft.store !== activeStore() || state.simulationDraft.source.studyId !== state.studyId)) $("simulationRunBtn").disabled = true;
  if (!$("fixtureConditionFields").hidden && state.fixtureConditionError) $("simulationRunBtn").disabled = true;
  if (!$("importedMeshFields").hidden && (state.importedMeshError || state.importedLoading)) $("simulationRunBtn").disabled = true;
  $("fixtureUseInCampaign").disabled = !writable() || busy() || Boolean(state.fixtureConditionError) || !window.cadControls.supportsBackend(state.presets.structural_linear, $("cadBackend").value);
  if (!document.querySelector("[data-campaign-variable]:checked")) $("campaignPlanBtn").disabled = true;
  $("modelDiscoverBtn").disabled = busy() || !state.overview || !state.presets[$("modelCampaignPreset").value]?.declared_inputs || !available("model_parameters_discover");
  if (!state.studyId || !currentModelDiscovery() || !$("modelInputId").value) $("modelRegisterBtn").disabled = true;
  if (isModelCampaign() && !currentModelDiscovery()) $("campaignPlanBtn").disabled = true;
  $("compareBtn").disabled = state.comparison.size < 2;
  $("compareCount").textContent = `${state.comparison.size}개 선택 · 최대 12개`;
  document.querySelectorAll("[data-experiment-draft]").forEach((item) => { item.disabled = blocked || !available(item.dataset.experimentDraft); });
  if (!observationReady()) $("observationSaveBtn").disabled = true;
  updateResearchControls();
}

function renderAnalysisParents() {
  const preset = state.presets[$("simulationPreset").value];
  const oldParent = $("analysisParent").value;
  const parents = clear("analysisParent"); option(parents, "", "이 해석에 연결된 CAD 실험을 선택하세요");
  list(state.overview?.experiments).filter((record) => record.study_id === state.studyId && window.cadControls.eligibleParent(preset, record))
    .forEach((record) => option(parents, record.id, `${record.id} · ${record.study_id}`));
  parents.value = [...parents.options].some((item) => item.value === oldParent) ? oldParent : "";
}
function refreshCadAnalysis() {
  const compatible = window.cadControls.supportsBackend(state.presets.structural_linear, $("cadBackend").value);
  $("campaignAnalysis").options[1].disabled = !compatible;
  if (!compatible && $("campaignAnalysis").value) {
    $("campaignAnalysis").value = "";
    $("campaignAnalysis").dispatchEvent(new Event("change"));
  }
}
function renderOverview() {
  const overview = state.overview;
  if (!overview) return;
  const stores = clear("storeSelect");
  list(overview.stores).forEach((store) => option(stores, store.id, store.label ?? store.id));
  stores.value = activeStore();
  const mode = badge(writable() ? "IMPLEMENTED" : "NOT_CHECKED", writable() ? "작업 저장소" : "읽기 전용");
  $("storeMode").className = mode.className; $("storeMode").textContent = mode.textContent;
  $("readOnlyBanner").hidden = writable();
  $("footerStore").textContent = `${activeStore()} · ${writable() ? "새 기록을 보존하는 작업 저장소" : "읽기 전용 기록 라이브러리"}`;
  const studies = list(overview.studies);
  if (!studies.some((study) => study.id === state.studyId)) {
    state.studyId = studies.find((study) => !study.error)?.id ?? "";
    invalidateModelDiscovery();
  }
  const select = clear("studySelect");
  if (!studies.length) option(select, "", "새 연구를 만들어 주세요");
  studies.forEach((study) => option(select, study.id, `${study.name || study.id} · ${study.id}${study.error ? " · 기록 오류" : ""}`));
  select.value = state.studyId;
  const stats = clear("overviewStats");
  [["연구", studies.length, "기록한 질문과 가설"], ["실험", list(overview.experiments).length, "CAD · 구조 · PDE"],
    ["탐색 계획", list(overview.campaigns).length, "DOE · 수치 최적화"],
    recoveryRequired() ? ["실행 상태 확인 필요", list(overview.jobs).filter(job => job.status === "RECOVERY_REQUIRED").length || "미확인", "새 작업 차단 · 보존 기록 조회 가능"]
      : ["실행 중", list(overview.jobs).filter(activeJob).length, "동시에 한 작업"]].forEach(([label, value, caption]) => {
    const card = el("div", undefined, "stat-card"); card.append(el("span", label, "stat-label"), el("span", value, "stat-value"), el("span", caption, "stat-caption")); stats.append(card);
  });
  const capabilities = clear("capabilities");
  list(overview.capabilities).forEach((capability) => {
    const card = el("div", undefined, "capability-item");
    card.append(badge(capability.status), el("h3", capability.label ?? capability.operation), el("p", text(capability.scope)));
    card.append(el("div", `${capability.backend ?? capability.operation} · ${capability.callable ? "API 제공" : "실행 API 없음"}`, "mono"));
    capabilities.append(card);
  });
  if (!capabilities.children.length) capabilities.append(el("p", "서버에서 capability 정보를 제공하지 않았습니다.", "empty-state"));
  renderAnalysisParents();
  renderExperimentList(); renderCampaignList(); updateControls();
}
async function loadOverview({ followJobs = true } = {}) {
  try {
    state.overview = await api("/api/overview");
    $("connectionState").textContent = state.overview.execution?.state === "RECOVERY_REQUIRED"
      ? "로컬 서버 연결됨 · 실행 상태 확인 필요 · 새 작업은 차단되며 보존된 기록은 볼 수 있습니다."
      : "로컬 서버 연결됨 · 목록은 미확인 상태이며 기록을 열 때 해시를 검증합니다.";
    $("connectionState").classList.remove("offline");
    renderOverview();
    list(state.overview.jobs).filter(job => job.operation === "research_run").forEach(retainResearchJob);
    renderResearchAnswers();
    if (state.studyId) await loadStudy(state.studyId); else renderStudy();
    if (followJobs) {
      const observed = list(state.overview.jobs).find(job => job.status === "RECOVERY_REQUIRED") ?? list(state.overview.jobs).find(activeJob)
        ?? list(state.overview.jobs).find(job => job.id === state.job?.id);
      if (observed) { state.job = observed; renderJob(); schedulePoll(); }
    }
  } catch (error) {
    $("connectionState").textContent = `연결을 확인할 수 없습니다 · ${error.message}`;
    $("connectionState").classList.add("offline"); updateControls(); throw error;
  }
}
async function loadStudy(identifier) {
  const request = ++state.studyRequest;
  const store = activeStore();
  try {
    const data = await api(`/api/studies/${idPath(identifier)}`);
    if (request !== state.studyRequest || store !== activeStore()) return;
    state.studyId = identifier; state.study = data.study; state.registry = data.registry ?? { entries: [] };
    $("studySelect").value = identifier; renderStudy(); renderRegistry(); renderAnalysisParents(); updateControls();
  } catch (error) {
    if (request !== state.studyRequest) return;
    state.study = null; state.registry = { entries: [] }; renderStudy(); renderRegistry(); throw error;
  }
}
function renderStudy() {
  const card = clear("studyDetail"); card.append(el("p", "CURRENT STUDY", "eyebrow"), el("h2", state.study?.name ?? "현재 연구"));
  if (!state.study) { card.append(el("p", "연구를 만들거나 상단에서 선택하면 질문·가설·등록 상태가 나타납니다.", "empty-state")); return; }
  const dl = el("dl", undefined, "definition-list separated");
  [["질문", state.study.research_question], ["가설", state.study.hypothesis], ["목적", state.study.objective]].forEach(([label, value]) => dl.append(el("dt", label), el("dd", value)));
  const meta = el("div", undefined, "card-meta"); meta.append(el("span", state.study.id, "mono"), el("span", `등록 변수 ${list(state.registry.entries).length}개`));
  card.append(dl, meta); const go = el("a", "설계에서 변수 등록하기 →", "text-link"); go.href = "#design"; card.append(go);
}
function renderRegistry() {
  const entries = selectedEntries();
  $("registryRevision").textContent = state.studyId ? `등록부 revision ${state.registry.revision ?? "미확인"}` : "등록부 미선택";
  const container = clear("registryList");
  if (!entries.length) container.append(el("p", "현재 연구·모델에 등록된 변수가 없습니다. 실제 후보를 발견하고 등록해 주세요.", "empty-state"));
  else container.append(table(["연구 변수", "현재 값 / 범위", "형상 효과"], entries.map((entry) => {
    const name = el("div", entry.display_name); name.append(el("small", entry.parameter_id, "mono"));
    const value = el("div", `${number(entry.current_value)} ${entry.unit}`); value.append(el("small", `${number(entry.lower_bound)} – ${number(entry.upper_bound)} · ${entry.kind} / ${entry.mode}`));
    return [name, value, badge(entry.geometry_effect?.status)];
  })));
  const values = clear("cadValues");
  values.classList.toggle("empty-state", !entries.length);
  if (!entries.length) values.append(el("p", "이 모델에 등록된 연구 변수가 나타납니다."));
  entries.forEach((entry) => {
    const label = el("label", `${entry.display_name} · ${entry.parameter_id} (${entry.unit})`);
    const input = el("input"); input.type = "number"; input.step = entry.kind === "integer" ? "1" : "any"; input.required = true;
    input.min = entry.lower_bound; input.max = entry.upper_bound; input.value = entry.current_value;
    input.dataset.cadParameter = entry.parameter_id; input.readOnly = entry.mode === "fixed";
    label.append(input, el("small", `범위 ${number(entry.lower_bound)}–${number(entry.upper_bound)} · ${entry.mode === "fixed" ? "고정값" : "자유 변수"}`, "hint")); values.append(label);
  });
  refreshCadAnalysis(); renderCampaignVariables(); updateControls();
}
function renderCampaignVariables() {
  if (state.campaignSelectionKey) state.campaignSelections.set(state.campaignSelectionKey,
    new Set([...document.querySelectorAll("[data-campaign-variable]:checked")].map((item) => item.value)));
  const model = isModelCampaign();
  const key = model ? state.modelContext : JSON.stringify([activeStore(), state.studyId, $("cadBackend").value, $("cadModel").value.trim()]);
  const selected = state.campaignSelections.get(key);
  const free = model ? modelCampaignEntries() : selectedEntries().filter((entry) => entry.mode === "free" && entry.kind === "continuous" && entry.geometry_effect?.status === "PASS");
  const variables = clear("campaignVariables");
  state.campaignSelectionKey = key;
  variables.classList.toggle("empty-state", !free.length);
  if (!free.length) variables.append(el("p", model ? "현재 설정으로 변수를 발견하고, 연속·자유·입력 변경 PASS인 연구 변수를 등록하세요." : "이 모델에 연속·자유·형상 효과 PASS로 등록된 변수가 필요합니다."));
  free.forEach((entry, index) => {
    const label = el("label", undefined, "variable-option"); const input = el("input"); input.type = "checkbox"; input.value = entry.parameter_id; input.dataset.campaignVariable = "";
    input.checked = selected ? selected.has(entry.parameter_id) : index === 0;
    input.addEventListener("change", updateControls);
    label.append(input, el("strong", `${entry.display_name} · ${entry.parameter_id}`), el("small", `${number(entry.lower_bound)}–${number(entry.upper_bound)} ${entry.unit}`)); variables.append(label);
  });
  if (model) {
    const preset = state.presets[$("modelCampaignPreset").value];
    $("campaignModel").textContent = `${state.studyId || "연구 미선택"} · ${preset?.backend ?? "모델 미선택"}\n${state.modelDiscovery[0]?.native.document ?? "설정 확인·변수 발견 필요"}\n모델 설정·등록부·실행 환경을 고정합니다. 물리적 자격 UNKNOWN, NOT_RELEASED.`;
  } else $("campaignModel").textContent = `${state.studyId || "연구 미선택"} · ${$("cadBackend").value} · ${$("cadModel").value.trim()}\n설계 화면의 작업 모델과 등록부를 고정해 사용합니다.`;
  updateControls();
}
function renderDiscovery(candidates) {
  state.discovery = list(candidates);
  $("discoveryCount").textContent = `${state.discovery.length}개 후보`;
  const select = clear("nativePath"); option(select, "", "발견한 후보를 선택하세요");
  state.discovery.forEach((candidate) => option(select, candidate.native?.path, `${candidate.label} · ${candidate.native?.path}`));
  const container = clear("discoveryList");
  if (!state.discovery.length) container.append(el("p", "지원되는 실제 후보가 발견되지 않았습니다. 모델과 최종 솔리드를 확인하세요.", "empty-state"));
  else container.append(table(["후보", "현재 값", "선택"], state.discovery.map((candidate) => {
    const name = el("div", candidate.label); name.append(el("small", candidate.native?.path, "mono"));
    return [name, `${number(candidate.value)} ${candidate.unit}`, action("등록 후보", () => chooseCandidate(candidate.native.path))];
  })));
  const preferred = state.discovery.find((item) => item.native?.path === "support_width_mm") ?? state.discovery[0];
  if (preferred) chooseCandidate(preferred.native.path);
  updateControls();
}
function chooseCandidate(path) {
  const candidate = state.discovery.find((item) => item.native?.path === path);
  if (!candidate) return;
  $("nativePath").value = path;
  $("parameterId").value = path === "support_width_mm" ? "support_width" : path.replace(/[^A-Za-z0-9_-]/g, "_").replace(/_mm$/, "").slice(0, 60);
  if (!/^[A-Za-z]/.test($("parameterId").value)) $("parameterId").value = `p_${$("parameterId").value}`;
  $("parameterName").value = candidate.label ?? $("parameterId").value;
  const distance = Math.max(Math.abs(candidate.value) * 0.25, 0.5);
  $("parameterLower").value = candidate.lower ?? candidate.value - distance;
  $("parameterUpper").value = candidate.upper ?? candidate.value + distance;
  updateControls();
}
function renderNative(info) {
  const identifier = info.design ?? info.model ?? $("nativeModelId").value;
  if (identifier) { $("nativeModelId").value = identifier; $("cadModel").value = identifier; $("cadBackend").value = "fixture.freecad"; renderRegistry(); }
  const finals = clear("nativeFinal"); option(finals, "", "최종 솔리드를 선택하세요");
  list(info.final_candidates).forEach((item) => option(finals, item.name, `${item.label ?? item.name} · ${item.name}`));
  finals.value = info.final ?? "";
  const detail = clear("nativeDetail"); detail.append(el("h3", info.document ?? "네이티브 CAD"), el("p", identifier, "mono"));
  detail.append(el("p", `최종 솔리드: ${info.final ?? "선택 필요"}`, "hint"), el("p", `실제 후보 ${list(info.candidates).length}개 · 네이티브 등록 ${list(info.parameters).length}개`, "hint"));
  detail.append(el("p", "새 CAD 실험을 만들면 편집 가능한 원본과 내보낸 형상을 같은 실험 개정에서 확인할 수 있습니다.", "hint separated"));
  detail.append(rawDetail("네이티브 모델의 실제 응답", info)); $("nativeArea").open = true; updateControls();
}

function renderPresets(data) {
  const presets = data.presets ?? data;
  state.presets = Array.isArray(presets) ? Object.fromEntries(presets.map((item) => [item.id ?? item.key, item])) : presets;
  const select = clear("simulationPreset");
  Object.entries(state.presets).forEach(([id, preset]) => option(select, id, preset.label ?? id));
  if (!select.options.length) option(select, "", "사용 가능한 예제 없음");
  selectPreset();
  const structural = state.presets.structural_linear;
  refreshCadAnalysis();
  if (structural) $("campaignAnalysisSettings").value = pretty(structural.settings);
  const models = clear("modelCampaignPreset");
  Object.entries(state.presets).filter(([, preset]) => preset.declared_inputs === true)
    .forEach(([id, preset]) => option(models, id, preset.label ?? id));
  if (!models.options.length) option(models, "", "광고된 모델 입력이 없습니다");
  selectModelCampaignPreset();
}
function selectModelCampaignPreset() {
  const preset = state.presets[$("modelCampaignPreset").value];
  const description = clear("modelCampaignDescription");
  if (preset) {
    description.append(el("p", preset.scope), el("p", preset.backend, "mono"));
    $("modelCampaignSettings").value = pretty(preset.settings);
  } else { description.append(el("p", "현재 adapter에 선언된 입력 연결이 필요합니다.")); $("modelCampaignSettings").value = "{}"; }
  invalidateModelDiscovery();
}
function renderModelDiscovery() {
  const select = clear("modelInputId"); option(select, "", "발견한 입력을 선택하세요");
  state.modelDiscovery.forEach((candidate) => option(select, candidate.native.path, `${candidate.label} · ${candidate.unit}`));
  const container = clear("modelDiscoveryList");
  if (!state.modelDiscovery.length) container.append(el("p", "현재 모델 설정으로 입력 변수를 다시 발견하세요. 오래된 등록 매핑으로 계획을 만들지 않습니다.", "hint"));
  else container.append(table(["입력", "현재 값", "광고된 범위"], state.modelDiscovery.map((candidate) =>
    [candidate.label, `${number(candidate.value)} ${candidate.unit}`, `${number(candidate.lower)}–${number(candidate.upper)} ${candidate.unit}`])));
  if (state.modelDiscovery[0]) chooseModelCandidate(state.modelDiscovery[0].native.path);
  updateControls();
}
function chooseModelCandidate(path) {
  const candidate = state.modelDiscovery.find((item) => item.native.path === path); if (!candidate) return;
  $("modelInputId").value = path;
  $("modelParameterId").value = `model_${path}`.slice(0, 64); $("modelParameterName").value = candidate.label;
  for (const id of ["modelParameterLower", "modelParameterUpper"]) { $(id).min = candidate.lower; $(id).max = candidate.upper; }
  $("modelParameterLower").value = candidate.lower; $("modelParameterUpper").value = candidate.upper;
  updateControls();
}
function simulationOperation() {
  const preset = state.presets[$("simulationPreset").value];
  if (["analysis_run", "pde_run", "model_analysis_run"].includes(preset?.operation)) return preset.operation;
  if (preset?.backend === "pde.fenicsx") return "pde_run";
  if (preset?.backend === "structural.code_aster") return "model_analysis_run";
  return "analysis_run";
}
function selectPreset() {
  clearSimulationDraft();
  const preset = state.presets[$("simulationPreset").value]; const description = clear("presetDescription");
  if (preset) {
    description.append(badge(preset.status), el("p", preset.scope), el("p", `Backend: ${preset.backend}`, "mono"));
    $("simulationSettings").value = pretty(preset.settings);
  } else description.append(el("p", "서버가 제공하는 기존 검증 예제가 필요합니다."));
  const operation = simulationOperation(); $("parentField").hidden = operation !== "analysis_run";
  $("simulationRunBtn").dataset.operation = operation;
  $("simulationId").value = makeId(operation === "pde_run" ? "E-pde" : operation === "model_analysis_run" ? "E-model" : "E-solve");
  $("fixtureConditionFields").hidden = preset?.backend !== "fixture.calculix";
  $("importedMeshFields").hidden = preset?.backend !== "pde.fenicsx.imported";
  state.importedRequest++; state.importedLoading = false; state.importedLevels = [];
  $("importedMeshFiles").value = ""; importedMeshError(null);
  if (!$("importedMeshFields").hidden) {
    try {
      const selected = window.importedMeshControls.splitSettings(preset.settings);
      state.importedLevels = selected.levels;
      $("simulationSettings").value = pretty(selected.draft);
    } catch (error) { importedMeshError(error.message); }
  }
  renderImportedMeshes();
  if (!$("fixtureConditionFields").hidden) loadFixtureConditions();
  else fixtureConditionError(null);
  renderAnalysisParents(); updateControls();
}
function clearSimulationDraft() {
  state.simulationDraft = null;
  clear("simulationDraftContext").hidden = true;
}
async function prepareExperimentDraft(record) {
  if (!writable() || busy() || state.storeSwitching) throw new Error("실행 가능한 작업 저장소에서 이전 작업의 종료 상태를 확인하세요.");
  const store = activeStore(), request = state.experimentRequest;
  const draft = window.experimentDraft.fromRecord(record, state.presets);
  if (!draft.available) throw new Error(draft.reason);
  if (!available(draft.operation)) throw new Error("이 조건을 실행할 기능이 현재 연결되지 않았습니다.");
  if (draft.arguments.parent_experiment_id) {
    const parent = list(state.overview?.experiments).find(item => item.id === draft.arguments.parent_experiment_id);
    if (!window.cadControls.eligibleParent(state.presets[draft.presetId], parent)) throw new Error("원본 CAD 부모를 같은 저장소에서 선택할 수 없습니다.");
  }
  await loadStudy(draft.source.studyId);
  if (store !== activeStore() || request !== state.experimentRequest || state.studyId !== draft.source.studyId
      || busy() || state.storeSwitching) throw new Error("연구 또는 저장소가 바뀌었습니다. 원 실험을 다시 열어 조건을 불러오세요.");
  $("simulationPreset").value = draft.presetId; selectPreset();
  clear("presetDescription").append(el("strong", "저장된 해석 조건을 사용합니다."),
    el("p", "아래 조건은 원 실험에서 가져왔습니다. 해석 예제의 초기 설정으로 바꾸지 않았습니다.", "hint"));
  $("simulationSettings").value = pretty(draft.arguments.settings);
  if (!$("importedMeshFields").hidden) {
    const imported = window.importedMeshControls.splitSettings(draft.arguments.settings);
    state.importedLevels = imported.levels; $("simulationSettings").value = pretty(imported.draft); renderImportedMeshes();
  }
  if (draft.arguments.parent_experiment_id) {
    $("analysisParent").value = draft.arguments.parent_experiment_id;
    if ($("analysisParent").value !== draft.arguments.parent_experiment_id) throw new Error("원본 CAD 부모를 같은 저장소에서 선택할 수 없습니다.");
  }
  loadFixtureConditions();
  state.simulationDraft = { ...draft, store };
  const context = clear("simulationDraftContext"); context.hidden = false;
  context.append(el("strong", "원래 조건에서 새 가상 실험 준비"), el("p", `${draft.source.experimentId} · ${draft.source.studyId}`),
    el("p", "원래 재료·하중·메시와 모델 연결을 불러왔습니다. 바꿀 조건을 검토한 뒤 새 실험으로 실행하세요. 원 결과는 보존됩니다.", "hint"));
  location.hash = "simulation"; updateControls();
  notify("원래 조건을 새 실험 초안으로 불러왔습니다. 아직 해석은 실행하지 않았습니다.", true);
}
function simulationArguments() {
  if (state.storeSwitching) throw new Error("저장소 전환이 끝난 뒤 조건을 확인하세요.");
  const preset = state.presets[$("simulationPreset").value], operation = simulationOperation(), draft = state.simulationDraft;
  if (!preset) throw new Error("해석할 모델을 선택하세요.");
  if (draft && (draft.store !== activeStore() || draft.source.studyId !== state.studyId
      || draft.source.backend !== preset.backend || draft.operation !== operation)) throw new Error("원 실험과 현재 연구·모델 연결이 달라졌습니다. 조건을 다시 불러오세요.");
  const args = { experiment_id: $("simulationId").value.trim(), backend: preset.backend, settings: fixtureSimulationSettings() };
  if (draft && args.experiment_id === draft.source.experimentId) throw new Error("원 결과를 보존하도록 새 실험 ID를 사용하세요.");
  if (operation === "analysis_run") {
    const parent = list(state.overview?.experiments).find((record) => record.id === $("analysisParent").value);
    if (!window.cadControls.eligibleParent(preset, parent) || parent.study_id !== state.studyId) throw new Error("현재 연구에 연결된 CAD 부모 실험을 선택하세요.");
    if (draft && $("analysisParent").value !== draft.source.parentExperimentId) throw new Error("불러온 조건은 원래 CAD 부모와 연결되어 있습니다. 다른 모델은 모델 선택부터 새로 준비하세요.");
    args.parent_experiment_id = $("analysisParent").value;
  } else {
    args.study_id = state.studyId;
    if (draft?.arguments.hypothesis_id) args.hypothesis_id = draft.arguments.hypothesis_id;
  }
  return args;
}
function simulationSubmissionContext() {
  return { store: activeStore(), studyId: state.studyId, source: state.simulationDraft?.source.experimentId };
}
async function completeSimulation(result, args, context) {
  if (context.store !== activeStore() || context.studyId !== state.studyId) return;
  const source = context.source;
  if (source) state.comparison = new Set([source, result.experiment_id ?? args.experiment_id]);
  $("simulationId").value = makeId("E-solve"); await inspectExperiment(result.experiment_id ?? args.experiment_id);
}
function importedMeshError(message) {
  state.importedMeshError = message;
  $("importedMeshError").textContent = message ?? "";
  $("importedMeshError").hidden = !message;
}
function renderImportedMeshes() {
  const container = clear("importedMeshSummary");
  if (!state.importedLevels.length) return;
  const summaries = window.importedMeshControls.summaries(state.importedLevels);
  container.append(table(["순서 · 파일", "크기", "SHA-256", "순서 변경"], summaries.map((row, index) => {
    const actions = el("div"); actions.className = "button-row";
    for (const [label, delta] of [["위로", -1], ["아래로", 1]]) {
      const button = action(label, () => {
        const other = index + delta;
        [state.importedLevels[index], state.importedLevels[other]] = [state.importedLevels[other], state.importedLevels[index]];
        renderImportedMeshes();
      }, "button secondary compact");
      button.disabled = index + delta < 0 || index + delta >= summaries.length;
      actions.append(button);
    }
    return [`${index + 1}. ${row.source}`, `${row.size_bytes} bytes`, el("span", row.sha256, "mono"), actions];
  })));
}
async function selectImportedFiles() {
  const request = ++state.importedRequest;
  state.importedLoading = true; state.importedLevels = []; clear("importedMeshSummary"); importedMeshError(null); updateControls();
  try {
    const levels = await window.importedMeshControls.fromFiles($("importedMeshFiles").files);
    if (request !== state.importedRequest) return;
    state.importedLevels = levels; renderImportedMeshes();
  } catch (error) {
    if (request === state.importedRequest) importedMeshError(error.message);
  } finally {
    if (request === state.importedRequest) { state.importedLoading = false; updateControls(); }
  }
}
function fixtureConditionError(message) {
  state.fixtureConditionError = message;
  $("fixtureConditionError").textContent = message ?? "";
  $("fixtureConditionError").hidden = !message;
}
function fixtureMaterialFields() {
  const isotropic = $("fixtureMaterialModel").value === "isotropic";
  $("fixtureIsotropicFields").hidden = !isotropic;
  $("fixtureOrthotropicFields").hidden = isotropic;
}
function loadFixtureConditions() {
  if ($("fixtureConditionFields").hidden) return;
  try {
    const fields = window.fixtureControls.toFields(parseField("simulationSettings", "object"));
    document.querySelectorAll("[data-fixture-field]").forEach((input) => { input.value = fields[input.dataset.fixtureField] ?? ""; input.disabled = false; });
    fixtureMaterialFields(); fixtureConditionError(null);
  } catch (error) {
    document.querySelectorAll("[data-fixture-field]").forEach((input) => { input.disabled = true; });
    fixtureConditionError(`해석 설정 JSON을 먼저 수정하세요. ${error.message}`);
  }
}
function changeFixtureConditions() {
  const fields = {};
  document.querySelectorAll("[data-fixture-field]").forEach((input) => { fields[input.dataset.fixtureField] = input.value; });
  fixtureMaterialFields();
  try {
    const settings = window.fixtureControls.fromFields(fields, parseField("simulationSettings", "object"));
    $("simulationSettings").value = pretty(settings); fixtureConditionError(null);
  } catch (error) { fixtureConditionError(error.message); }
  updateControls();
}
function fixtureSimulationSettings() {
  if (!$("fixtureConditionFields").hidden && state.fixtureConditionError) throw new Error(state.fixtureConditionError);
  const settings = parseField("simulationSettings", "object");
  if (!$("importedMeshFields").hidden) {
    if (state.importedMeshError || state.importedLoading) throw new Error(state.importedMeshError ?? "파일을 읽는 중입니다.");
    return window.importedMeshControls.settingsWithLevels(settings, state.importedLevels);
  }
  return $("fixtureConditionFields").hidden ? settings : window.fixtureControls.validate(settings);
}
function campaignOperation() { return isModelCampaign() ? "model_optimization_plan" : $("campaignType").value === "optimization" ? "optimization_plan" : "doe_plan"; }
function campaignTargetChanged() {
  const previous = state.campaignTarget;
  state.campaignDrafts[previous] = Object.fromEntries(["objectiveSource", "objectiveDirection", "objectiveMetric", "objectiveUnit", "optimizationConstraints", "optimizationInitial", "optimizationRequired"].map((id) => [id, $(id).value]));
  if (previous === "cad") state.cadCampaignType = $("campaignType").value;
  state.campaignTarget = $("campaignTarget").value;
  const model = isModelCampaign();
  const draft = state.campaignDrafts[state.campaignTarget] ?? { objectiveSource: model ? "model" : "cad", objectiveDirection: "minimize", objectiveMetric: model ? "" : "cad_volume", objectiveUnit: model ? "" : "mm^3", optimizationConstraints: "[]", optimizationInitial: "null", optimizationRequired: model ? '{"model": []}' : '{"cad": [], "analysis": []}' };
  Object.entries(draft).forEach(([id, value]) => { $(id).value = value; });
  $("campaignType").value = model ? "optimization" : state.cadCampaignType;
  $("campaignType").querySelector('[value="doe"]').disabled = model;
  $("declaredModelArea").hidden = !model; $("campaignCadAnalysis").hidden = model;
  $("objectiveSource").querySelectorAll("option").forEach((item) => { item.disabled = model ? item.value !== "model" : item.value === "model"; });
  campaignMode(); renderCampaignVariables();
}
function campaignMode() {
  const optimization = $("campaignType").value === "optimization";
  $("optimizationFields").hidden = !optimization; $("sampleCountField").hidden = optimization;
  $("campaignPlanBtn").dataset.operation = campaignOperation();
  $("campaignId").value = makeId(optimization ? "C-opt" : "C-doe"); updateControls();
}
function renderCampaignList() {
  const rows = list(state.overview?.campaigns); $("campaignCount").textContent = rows.length;
  const container = clear("campaignList");
  if (!rows.length) { container.append(el("p", "저장한 계획이 나타납니다. 현재 라이브러리에 캠페인이 없을 수도 있습니다.", "empty-state")); return; }
  rows.forEach((row) => {
    const card = el("div", undefined, "campaign-row"); const textBlock = el("div");
    textBlock.append(el("strong", row.type === "optimization" ? "수치 최적화" : "DOE"), el("div", row.id, "mono"), el("p", row.study_id));
    card.append(textBlock, action("계획·기록 열기", () => inspectCampaign(row.id))); container.append(card);
  });
}
async function inspectCampaign(identifier) {
  const request = ++state.campaignRequest, store = activeStore(); const container = clear("campaignDetail");
  container.append(el("p", "계획과 journal을 검사하고 있습니다…", "hint"));
  try {
    const data = await api(`/api/campaigns/${idPath(identifier)}`);
    if (request !== state.campaignRequest || store !== activeStore()) return;
    state.selectedCampaign = { id: identifier, ...data }; renderCampaignDetail();
  } catch (error) { if (request === state.campaignRequest) { clear(container).append(el("p", `기록 확인 실패: ${error.message}`, "metric-reason")); } throw error; }
}
function experimentButton(identifier, label = identifier) {
  if (!identifier) return el("span", "—", "hint");
  return action(label, async () => { location.hash = "results"; await inspectExperiment(identifier); }, "record-id");
}
function renderCampaignDetail() {
  const data = state.selectedCampaign; if (!data) return;
  const container = clear("campaignDetail"), record = data.record, plan = record.plan ?? record;
  container.append(el("h3", data.id, "mono"));
  const summary = el("div", undefined, "campaign-summary"); summary.append(badge(record.status), badge(record.decision ?? "NOT_RELEASED"));
  if (record.termination) summary.append(el("p", `종료: ${labels[record.termination.termination_reason] ?? record.termination.termination_reason} · ${record.termination.generations}세대 · ${record.termination.evaluation_count}개 평가`));
  summary.append(el("p", "계획/작업 완료는 출시 승인이나 전역 최적해를 의미하지 않습니다."));
  const algorithm = record.algorithm ?? plan.algorithm;
  if (algorithm) summary.append(el("p", `${algorithm.engine} ${algorithm.version} · seed ${algorithm.seed}`, "mono"));
  container.append(summary);
  const operation = data.type === "optimization" ? "optimization_run" : "doe_run";
  const button = action("계획 실행 / 이어가기", () => runJob(operation, { campaign_id: data.id }, () => inspectCampaign(data.id)), "button primary compact");
  button.dataset.operation = operation; container.append(button);
  const rows = list(record.evaluations ?? record.samples ?? plan.samples);
  const model = (record.route ?? plan.route) === "model_analysis";
  if (model) container.append(el("p", `${typeof plan.backend === "string" ? plan.backend : "선언한 모델 입력의 수치 탐색"} · 물리적 자격 UNKNOWN`, "hint"));
  if (rows.length) container.append(table(model ? ["후보 / 연구 변수", "모델 해석", "판정"] : ["후보 / 연구 변수", "CAD", "해석", "판정"], rows.map((row) => {
    const values = el("div", row.index ?? row.id ?? "후보"); values.append(el("small", text(row.values), "mono"));
    const cad = el("div"); cad.append(experimentButton(row.cad_experiment_id, row.cad_experiment_id ?? "—"), el("small", row.cad_status ?? "계획됨"));
    const analysis = el("div"); analysis.append(experimentButton(row.analysis_experiment_id), el("small", row.analysis_status ?? "미실행"));
    const verdict = el("div"); if (typeof row.numerically_feasible === "boolean") verdict.append(badge(row.numerically_feasible ? "PASS" : "FAIL", row.numerically_feasible ? "수치 조건 충족" : "수치 조건 미충족"));
    verdict.append(el("small", `UNKNOWN ${list(row.unknown).length}개`));
    if (model) { const result = el("div"); result.append(experimentButton(row.model_experiment_id), el("small", row.model_status ?? "미실행")); return [values, result, verdict]; }
    return [values, cad, analysis, verdict];
  })));
  if (record.incumbent) container.append(rawDetail("현재 최선의 유효 후보 · optimum 승인 아님", record.incumbent));
  container.append(rawDetail("고정한 계획·algorithm·journal 기록", record)); updateControls();
}

function renderExperimentList() {
  const query = $("experimentSearch").value.toLowerCase().trim(), filter = $("experimentFilter").value;
  const records = list(state.overview?.experiments).filter((row) => (!filter || row.status === filter) &&
    (!query || `${row.id} ${row.study_id} ${row.backend}`.toLowerCase().includes(query)));
  const container = clear("experimentList");
  if (!records.length) { container.append(el("p", "이 조건에 맞는 실험이 없습니다. 실험을 실행하거나 다른 저장소를 선택하세요.", "empty-state")); updateControls(); return; }
  container.append(table(["비교", "실험 / 연구", "작업", "현재 단계 / 다음 할 일", "사용 승인", "기록 확인", ""], records.map((row) => {
    const select = el("input"); select.type = "checkbox"; select.checked = state.comparison.has(row.id); select.setAttribute("aria-label", `${row.id} 비교 선택`);
    select.addEventListener("change", () => {
      if (select.checked && state.comparison.size >= 12) { select.checked = false; notify("한 번에 최대 12개 실험을 비교할 수 있습니다."); return; }
      if (select.checked) state.comparison.add(row.id); else state.comparison.delete(row.id); updateControls();
    });
    const identifier = el("div"); identifier.append(experimentButton(row.id), el("small", row.study_id));
    if (row.error) identifier.append(el("small", text(row.error), "metric-reason"));
    const workflow = window.resultPresentation.workflow(row, workflowContext(row, "experiment", row.integrity));
    const progress = el("div"); progress.append(badge(row.status, workflow.stage), el("small", workflow.next));
    return [select, identifier, el("span", window.resultPresentation.title(row.backend)), progress, badge(row.decision ?? "UNKNOWN"), badge(row.integrity ?? "NOT_CHECKED"), action("열기", () => inspectExperiment(row.id))];
  })));
  updateControls();
}
async function inspectExperiment(identifier) {
  if (state.storeSwitching) throw new Error("저장소를 바꾸고 있습니다. 전환 후 기록을 열어 주세요.");
  if (!window.resultPresentation.safeExperimentId(identifier)) throw new Error("실험 식별자를 확인할 수 없습니다.");
  location.hash = "results"; const request = ++state.experimentRequest, store = activeStore();
  state.fixtureViewer?.destroy(); state.fixtureViewer = null;
  state.selectedExperiment = null;
  $("observationPanel").hidden = true; state.observationRequest++;
  const loading = panel("실험을 불러오고 있습니다."); loading.append(el("p", "저장된 기록과 원본 파일의 일치를 확인하고 있습니다.", "hint separated")); clear("experimentDetail").append(loading);
  $("selectedSource").textContent = "기록 확인 중";
  try {
    const data = await api(`/api/experiments/${idPath(identifier)}`);
    if (request !== state.experimentRequest || store !== activeStore()) return;
    if (data.integrity !== "VERIFIED" || data.result?.experiment_id !== identifier) throw new Error("서버가 요청한 기록의 식별자와 검증 완료를 확인하지 않았습니다.");
    state.selectedExperiment = data; renderExperimentDetail(data); renderObservation(data);
  } catch (error) {
    if (request !== state.experimentRequest) return;
    const card = panel("이 실험의 기록을 확인할 수 없습니다."); card.classList.add("detail-error"); card.append(el("p", error.message), el("p", "파일과 기록의 일치를 확인한 후 결과를 표시합니다."));
    clear("experimentDetail").append(card); $("selectedSource").textContent = "기록 확인 실패"; throw error;
  }
}
function metricCell(metric) {
  const cell = el("div");
  if (!metric) { cell.append(el("span", "미제공", "hint")); return cell; }
  cell.append(el("span", `${number(metric.value)} ${metric.unit ?? ""}`, `metric-value${metric.valid === true ? "" : " invalid-value"}`));
  cell.append(el("small", metric.valid === true ? "유효한 수치 응답" : "INVALID · 판단에 사용할 수 없음"));
  if (metric.reason) cell.append(el("small", metric.reason, "metric-reason"));
  return cell;
}
function observationReady() {
  const record = state.selectedExperiment;
  return Boolean(!state.storeSwitching && record?.result?.status === "COMPLETED_REVIEW_REQUIRED"
    && record.result.study?.id === state.studyId && window.observationControls?.choices(record).length);
}
function observationSubmissionContext() {
  if (!observationReady()) throw new Error("현재 연구에 속한 검증된 실험과 유효한 응답을 먼저 선택하세요.");
  return { store: activeStore(), studyId: state.studyId, record: state.selectedExperiment };
}
function observationArguments() {
  observationSubmissionContext();
  return window.observationControls.build(state.selectedExperiment, {
    comparisonId: state.observationId, purpose: $("observationPurpose").value,
    hypothesis: $("observationHypothesis").value, responseKey: $("observationResponse").value,
    name: $("observationName").value, value: $("observationValue").value,
    sourceKind: $("observationSourceKind").value, source: $("observationSource").value,
    quantity: $("observationQuantity").value, component: $("observationComponent").value,
    location: $("observationLocation").value, coordinateFrame: $("observationFrame").value,
    condition: $("observationCondition").value, tolerance: $("observationTolerance").value,
    conditions: parseField("observationConditions", "array"),
  });
}
function observationResponseNote() {
  const choice = window.observationControls?.choices(state.selectedExperiment).find(item => item.key === $("observationResponse").value);
  $("observationResponseNote").textContent = choice
    ? `기록된 응답: ${number(choice.value)} ${choice.unit} · 관측값과 허용 차이도 ${choice.unit}로 입력하세요.${choice.component !== undefined ? " 배열 항목의 물리적 성분은 사용자가 확인해야 합니다." : ""}`
    : "선택한 응답의 값과 단위가 여기에 나타납니다.";
}
function observationSourceCaption(source) {
  let caption = window.resultPresentation.title(source.backend);
  if (source.backend === "fixture.calculix") {
    try {
      const fields = window.fixtureControls.toFields(source.execution);
      caption += ` · 지지부당 ${fields.force_N} N · 메시 ${fields.mesh_sizes} mm`;
    } catch { /* Preserve the exact source in the expandable record. */ }
  }
  return caption;
}
function renderObservation(data) {
  const choices = window.observationControls?.choices(data) ?? [];
  const panel = $("observationPanel"); panel.hidden = !choices.length || data.result.status !== "COMPLETED_REVIEW_REQUIRED";
  state.observationRequest++; clear("observationRecords");
  if (panel.hidden) return;
  state.observationId = makeId("O");
  $("observationContext").textContent = `선택한 ${observationSourceCaption({ backend: data.result.provenance.adapter, execution: data.proposal.execution })} 결과에 관측을 연결합니다. 원래 모델과 응답은 그대로 보존합니다.`;
  $("observationEditor").open = false;
  const response = clear("observationResponse"); option(response, "", "유효한 응답을 선택하세요");
  choices.forEach(choice => option(response, choice.key, `${choice.label} · ${choice.unit}`));
  for (const id of ["observationPurpose", "observationHypothesis", "observationName", "observationSourceKind", "observationSource",
    "observationValue", "observationTolerance", "observationQuantity", "observationComponent", "observationLocation", "observationFrame", "observationCondition"]) $(id).value = "";
  $("observationConditions").value = "[]"; response.value = ""; observationResponseNote(); updateControls();
  loadResponseComparisons(data).catch(error => notify(error.message));
}
async function loadResponseComparisons(inspection = state.selectedExperiment) {
  if (!inspection) return;
  const request = ++state.observationRequest, store = activeStore(), studyId = inspection.result.study.id;
  const current = () => request === state.observationRequest && !state.storeSwitching && store === activeStore() && state.selectedExperiment === inspection;
  clear("observationRecords").append(el("p", "이 연구의 저장된 관측 비교를 확인하고 있습니다…", "hint"));
  try {
    const rows = await api(`/api/response-comparisons?study_id=${idPath(studyId)}`);
    if (!current()) return;
    if (!Array.isArray(rows)) throw new Error("관측 비교 목록의 형식을 확인할 수 없습니다.");
    const target = clear("observationRecords");
    if (!rows.length) target.append(el("p", "저장된 관측 비교가 없습니다. 관측값과 조건을 입력해 새 비교를 남길 수 있습니다.", "hint"));
    rows.forEach(value => {
      const record = value.record, comparison = record?.comparison;
      if (value.integrity !== "VERIFIED" || record?.source?.study_id !== studyId || !comparison) {
        const error = el("p", `확인할 수 없는 비교 기록: ${value.id ?? "미제공"} · ${value.error ?? "원본 일치 미확인"}`, "metric-reason"); target.append(error); return;
      }
      const observation = record.request.observation, details = el("details", undefined, "advanced separated");
      const kind = { MEASURED_REPORTED: "사용자 보고 측정값", SPECIFICATION: "규격·목표값", SYNTHETIC: "가상 데이터" }[observation.source_kind];
      details.append(el("summary", `${observation.name} · ${kind} · ${comparison.status === "DECLARED_CONDITION_MISMATCH" ? "조건 불일치 · 차이 계산 보류" : "수치 차이 기록됨"}`));
      details.append(el("p", record.request.hypothesis, "separated"), el("p", `해석 조건: ${observationSourceCaption(record.source)}`),
        el("p", `출처: ${observation.source}`), el("p", `관측 범위: ${observation.quantity} · ${observation.component} · ${observation.location} · ${observation.coordinate_frame}`),
        el("p", `관측 조건: ${observation.condition}`));
      const selected = record.request.response;
      const sourceChoice = record.source.experiment_id === inspection.result.experiment_id
        ? window.observationControls?.choices(inspection).find(choice => choice.metric === selected.metric && choice.component === selected.component) : null;
      details.append(el("p", `원 응답: ${sourceChoice?.label ?? window.resultPresentation.metricName(selected.metric)}${selected.component !== undefined && !sourceChoice ? ` · 사용자 지정 배열 항목 ${selected.component + 1} (물리 성분 미확인)` : ""}`));
      details.append(table(["관측·기준", "해석 응답", "해석 − 관측", "절대 허용 차이"], [[
        `${number(comparison.observed_value)} ${comparison.unit}`, `${number(comparison.response_value)} ${comparison.unit}`,
        comparison.difference === null ? "조건 불일치 · 계산 보류" : `${number(comparison.difference)} ${comparison.unit}`,
        `${number(comparison.declared_absolute_tolerance)} ${comparison.unit}`]]));
      details.append(el("p", comparison.within_declared_tolerance === null ? "명시적으로 연결한 입력 조건이 일치하지 않습니다."
        : comparison.within_declared_tolerance ? "입력한 허용 차이 이내입니다." : "입력한 허용 차이를 초과합니다."));
      details.append(el("p", "위치·성분·좌표계·조건의 물리적 일치는 사용자 선언이며 독립 확인 전입니다. 수치가 맞아도 원인 확정·물리 검증·사용 승인으로 판정하지 않습니다.", "hint"));
      if (!comparison.condition_bindings_supplied) details.append(el("p", "저장된 입력과의 명시적 조건 연결은 제공되지 않았습니다.", "hint"));
      details.append(experimentButton(record.source.experiment_id, "이 비교의 원 해석 결과 보기 →"),
        link("비교 원본 저장", `/api/response-comparisons/${idPath(record.id)}`, "text-link", true), rawDetail("입력·선택 응답·원본 해시·조건 검사", record));
      target.append(details);
    });
  } catch (error) {
    if (!current()) return;
    clear("observationRecords").append(el("p", `관측 비교를 확인하지 못했습니다: ${error.message}`, "metric-reason")); throw error;
  }
}
async function completeObservation(result, args, context) {
  if (result?.id !== args.comparison_id || result?.source?.experiment_id !== args.experiment_id) throw new Error("저장된 관측 비교의 연결을 확인할 수 없습니다.");
  if (!context || state.storeSwitching || context.store !== activeStore() || context.studyId !== state.studyId || context.record !== state.selectedExperiment) return;
  state.observationId = makeId("O");
  await loadResponseComparisons(context.record);
  notify("관측·조건·수치 차이를 새 기록으로 저장했습니다. 물리적 일치와 원인은 확인 전입니다.", true);
}
function renderExperimentDetail(data) {
  state.fixtureViewer?.destroy(); state.fixtureViewer = null;
  const result = data.result, identifier = result.experiment_id;
  const presentation = window.resultPresentation, check = presentation.checks(result);
  const container = clear("experimentDetail"), backend = result.provenance?.adapter;
  const header = panel(presentation.title(backend), "실험 결과"); header.classList.add("result-header");
  const workflow = presentation.workflow(result, workflowContext(result, "experiment", data.integrity));
  const verdicts = el("div", undefined, "status-title"); verdicts.append(badge(result.status, workflow.stage), badge(data.integrity), badge(result.decision)); header.append(verdicts);
  header.append(el("p", workflow.next, "hint"));
  const context = result.solver_status === "NOT_RUN" ? "이 기록에는 해석 실행 결과가 없습니다."
    : `해석 실행: ${labels[result.solver_status] ?? "상세 기록에서 확인"} · ${presentation.numericalCaption(result)}`;
  header.append(el("p", context, "result-context"));
  const downloads = el("div", undefined, "button-row");
  downloads.append(link("보고서 열기", `/api/report/${idPath(identifier)}.html`, "button secondary compact"), link("원본 묶음 저장", `/api/report/${idPath(identifier)}.zip`, "button subtle compact", true)); header.append(downloads); container.append(header);

  const overview = el("div", undefined, "result-overview");
  const visual = panel("모델 형상"); visual.classList.add("result-visual");
  const artifactsList = list(result.artifacts);
  renderCadPreview(visual, data);
  const side = el("div", undefined, "result-side");
  const inputs = panel("입력 조건"), values = presentation.inputs(data);
  const inputList = el("dl", undefined, "result-facts");
  values.forEach(item => { inputList.append(el("dt", item.name), el("dd", `${number(item.value)}${item.unit && item.unit !== "1" ? ` ${item.unit}` : ""}`)); });
  if (values.length) inputs.append(inputList); else inputs.append(el("p", "등록된 연구 변수 입력이 없습니다. 모델·하중 설정은 상세 기록에서 확인하세요.", "empty-state"));
  if (data.integrity === "VERIFIED" && backend === "fixture.calculix") {
    try {
      const fields = window.fixtureControls.toFields(data.proposal.execution), facts = el("dl", undefined, "result-facts separated");
      const rows = [["지지부당 하중", `${fields.force_N} N`], ["하중 출처", fields.source],
        ["재료 모델", fields.model === "isotropic" ? "등방성" : "직교 이방성"],
        ["재료 데이터", fields.qualification === "ASSUMED_NOT_MEASURED" ? "측정되지 않은 가정값" : fields.qualification],
        ["재료 출처", fields.provenance], ["메시", `${fields.mesh_sizes} mm · ${fields.mesh_mode === "selected" ? "선택한 메시 하나" : "기존 메시 비교"}`]];
      if (fields.model === "isotropic") rows.splice(3, 0, ["탄성계수 E", `${fields.elastic_modulus_MPa} MPa`], ["푸아송비 ν", fields.poisson_ratio]);
      rows.forEach(([label, value]) => facts.append(el("dt", label), el("dd", value))); inputs.append(facts);
    } catch (_error) { inputs.append(el("p", "간단한 양식으로 표시할 수 없는 조건입니다. 원래 전체 조건을 확인하세요.", "hint")); }
  }
  if (presentation.safeExperimentId(result.parent_experiment_id) && result.parent_experiment_id !== identifier)
    inputs.append(experimentButton(result.parent_experiment_id, "기록이 참조한 CAD 실험 보기 →"));
  if (data.integrity === "VERIFIED" && data.proposal?.execution && result.solver_status !== "NOT_RUN") {
    const original = el("details", undefined, "advanced separated");
    original.append(el("summary", "원래 해석의 전체 조건"), el("pre", pretty(data.proposal.execution))); inputs.append(original);
  }
  const draft = window.experimentDraft?.fromRecord(data, state.presets);
  if (draft?.available) {
    const reuse = action("이 조건에서 새 실험 준비", () => prepareExperimentDraft(data), "button secondary compact");
    reuse.dataset.experimentDraft = draft.operation; reuse.disabled = !writable() || busy() || !available(draft.operation);
    inputs.append(reuse, el("p", writable() ? "조건을 불러온 뒤 수정·실행합니다. 기존 결과는 바뀌지 않습니다." : "읽기 전용 기록입니다. 다른 저장소로 모델을 옮기는 기능은 아직 제공하지 않습니다.", "hint"));
  }
  side.append(inputs);
  const checks = panel("확인 상태");
  const checkCounts = el("div", undefined, "check-counts");
  for (const [code, count] of Object.entries(check.counts)) if (count) checkCounts.append(badge(code === "other" ? "NOT_CHECKED" : code, `${code === "other" ? "기타" : labels[code]} ${count}개`));
  checks.append(checkCounts, el("p", `이 실험 기록에 포함된 검사 ${check.total}개 기준입니다.`, "hint"));
  checks.append(el("p", result.decision === "NOT_RELEASED" ? "강도·실물 사용 승인에 필요한 확인이 남아 있습니다." : "사용 승인 여부는 기록의 판정과 근거를 따릅니다.", "check-note")); side.append(checks);
  overview.append(visual, side); container.append(overview);
  renderFixtureFields(container, data);

  const metrics = panel("결과값"); metrics.classList.add("detail-wide");
  const metricRows = Object.entries(result.metrics ?? {}), metricGrid = el("div", undefined, "result-metrics");
  metricRows.forEach(([name, metric], index) => {
    const metricLabel = name === "max_displacement" && result.provenance?.adapter === "fixture.calculix"
      && result.provenance?.adapter_details?.per_mesh_displacement?.response_metric === "loaded_saddle_min_global_uz"
      ? "하중 안장 최대 |UZ| (전체 |U| 최대 아님)" : presentation.metricName(name, index);
    const card = el("div", undefined, "result-metric"), label = el("span", metricLabel, "stat-label"); label.title = name;
    const unit = metric.unit === "1" ? (name === "cad_component_count" ? "개" : "") : metric.unit === "mm^3" ? "mm³" : metric.unit ?? "";
    const displayNumber = value => typeof value === "number" && Number.isFinite(value)
      ? new Intl.NumberFormat("ko-KR", { maximumSignificantDigits: 6 }).format(value) : text(value);
    const value = Array.isArray(metric.value) ? (name === "cad_bounds" ? metric.value.map(displayNumber).join(" × ") : text(metric.value)) : displayNumber(metric.value);
    card.append(label, el("strong", `${value} ${unit}`.trim(), `result-metric-value${metric.valid === true ? "" : " invalid-value"}`), badge(metric.valid === true ? "PASS" : "FAIL", metric.valid === true ? "수치 응답 유효" : "판단에 사용할 수 없는 값"));
    if (metric.reason) card.append(el("p", metric.reason, "metric-reason")); metricGrid.append(card);
  });
  if (metricRows.length) metrics.append(metricGrid, el("p", "표시값은 읽기 쉽게 반올림했습니다. 원래 수치·단위·판정은 상세 기록에 보존됩니다.", "hint separated")); else metrics.append(el("p", "이 실험은 사용할 수 있는 수치 결과를 제공하지 않았습니다.", "empty-state")); container.append(metrics);

  if (check.unresolved.length) {
    const pending = panel("남은 확인 사항"); pending.classList.add("detail-wide", "result-pending");
    const rows = el("ul", undefined, "pending-checks");
    check.unresolved.forEach((item, index) => {
      const row = el("li"), name = el("span", presentation.validationName(item.type, index)); name.title = item.type;
      row.append(name, badge(item.status)); if (item.blocking) row.append(el("small", "사용 승인에 필요")); rows.append(row);
    }); pending.append(rows); container.append(pending);
  }
  renderFixtureStressFields(container, result);
  renderContactFields(container, data);
  renderPdeFields(container, data);

  const records = el("details", undefined, "card result-records detail-wide"); records.append(el("summary", "상세 검사·원본 파일·실행 기록"));
  records.append(el("p", `실험 ${identifier} · 연구 ${result.study?.id ?? result.study?.study_id ?? "미제공"}`, "hint separated"));
  const validation = panel("기록에 포함된 검사");
  validation.append(table(["검사", "상태", "범위", "원본 기록"], list(result.validations).map((item, index) => {
    const label = el("div", presentation.validationName(item.type, index), "validation-type"); label.append(el("small", `${item.type} · ${item.validator}`));
    const detail = el("div"); detail.append(el("span", text(item.notes ?? item.observed ?? item.expected ?? item.threshold), "hint"), rawDetail("검사 기록 펼치기", item));
    return [label, badge(item.status), item.blocking ? "사용 승인에 필요" : "보조 검사", detail];
  }))); records.append(validation);
  const evidence = panel("검사 근거");
  list(result.evidence).forEach(item => {
    const card = el("div", undefined, "evidence-card"); card.append(el("h3", item.id), el("p", `${item.type} · ${text(item.method)}`), rawDetail("관찰 원본 펼치기", item));
    if (typeof item.artifact === "string" && artifactsList.some(artifact => artifact.path === item.artifact)) card.append(link(item.artifact, artifactUrl(identifier, item.artifact), "text-link artifact-path", true));
    evidence.append(card);
  });
  if (!list(result.evidence).length) evidence.append(el("p", "이 기록에 제공된 검사 근거가 없습니다.", "empty-state")); records.append(evidence);
  const artifacts = panel("원본 파일");
  artifacts.append(table(["파일", "크기", "SHA-256", "개정"], list(result.artifacts).map((item) => {
    const digest = el("div", item.sha256, "mono"); return [link(item.path, artifactUrl(identifier, item.path), "artifact-path", true), `${number(item.size_bytes)} bytes`, digest, el("span", item.revision, "mono")];
  }))); records.append(artifacts);
  const provenance = panel("실행 버전과 원본 식별 정보");
  const source = result.provenance ?? {}; const sourceGrid = el("div", undefined, "source-grid separated");
  [["Core commit", source.core_commit], ["Core 변경 상태", source.core_dirty === true ? "기록 시 로컬 변경 있음" : source.core_dirty === false ? "기록 시 clean" : "미기록 / 미확인"], ["Source commit", source.source_commit], ["Core source SHA", source.core_source_sha256], ["CAD revision", result.cad_revision], ["Model revision", result.model_revision ?? result.extensions?.pde?.model_revision], ["Adapter / version", `${text(source.adapter)} / ${text(source.adapter_version)}`]].forEach(([label, value]) => sourceGrid.append(el("span", label), el("div", text(value), "mono")));
  provenance.append(sourceGrid, rawDetail("연구 변수·모델·하중 설정", { registry: data.registry_snapshot, proposal: data.proposal }), rawDetail("전체 provenance · thread · result", { provenance: source, thread: data.thread, result }), link("보고서 JSON 저장", `/api/report/${idPath(identifier)}.json`, "button subtle compact", true)); records.append(provenance);
  records.append(el("p", "원본 묶음은 이 기록과 부모 실험을 함께 저장합니다. 원격 보관과 서명은 별도 확인이 필요합니다.", "hint separated")); container.append(records);
  const commit = source.core_commit ?? source.source_commit;
  $("selectedSource").textContent = "기록·원본 확인됨";
  $("selectedSource").title = text(commit);
  $("resultBrowser").open = false;
  if (window.cadControls.eligibleParent(state.presets[$("simulationPreset").value], { ...result, backend: result.provenance?.adapter })) $("analysisParent").value = identifier;
  updateControls();
}
function renderFixtureFields(container, inspection) {
  const result = inspection.result;
  if (result.provenance?.adapter !== "fixture.calculix") return Promise.resolve(false);
  const card = panel("같은 해석의 메시와 절점 변위", "NATIVE FEA FIELD · SAME RECORD"); card.classList.add("detail-wide", "fixture-field-card");
  card.append(el("p", "해석에 사용한 실제 메시·고정·하중과 저장된 전체 U를 확인합니다. 이 관측은 정확도·강도·실물 사용 승인이 아닙니다.", "hint separated"));
  const choices = el("div", undefined, "button-row separated"), detail = el("div", undefined, "fixture-field-detail separated"); card.append(choices, detail); container.append(card);
  const request = state.experimentRequest, store = activeStore(); let sequence = 0, mounted = null;
  const current = () => card.isConnected && detail.isConnected && request === state.experimentRequest && store === activeStore()
    && !state.storeSwitching && state.selectedExperiment === inspection;
  let record;
  try {
    if (!window.fixtureFieldControls || !window.fixtureFieldViewer) throw new Error("FEA 필드 표시 모듈을 불러올 수 없습니다.");
    record = window.fixtureFieldControls.catalog(inspection);
    if (!record.entries.length) { detail.append(el("p", record.reason, "empty-state")); return Promise.resolve(false); }
  } catch (error) { if (current()) detail.append(el("p", error.message, "metric-reason")); return Promise.resolve(false); }
  const label = el("label", "해석 메시 레벨"), select = el("select"); label.append(select); choices.append(label);
  record.entries.forEach((entry, i) => option(select, String(i), `${entry.size_mm} mm · 원본 레벨 ${entry.index}`)); select.value = String(record.entries.length - 1);
  async function selectField() {
    if (!current()) return false; const epoch = ++sequence, entry = record.entries[Number(select.value)];
    const selected = () => current() && epoch === sequence;
    mounted?.destroy(); if (state.fixtureViewer === mounted) state.fixtureViewer = null; mounted = null;
    clear(detail).append(el("p", "같은 기록의 필드 바이트·원본 연결·전체 절점과 외곽면을 확인하고 있습니다…", "hint"));
    try {
      if (!entry) throw new Error("이 기록의 메시 레벨을 선택하세요.");
      async function fetchFieldBytes(relative, expectedBytes) {
        if (!selected()) throw new Error("필드 선택이 바뀌었습니다.");
        const response = await fetch(artifactUrl(result.experiment_id, relative), { cache: "no-store", headers: { Accept: "application/octet-stream" } });
        if (!selected()) throw new Error("필드 선택이 바뀌었습니다.");
        if (!response.ok) throw new Error(`원본 필드를 검증해 읽을 수 없습니다 (${response.status}).`);
        const length = response.headers.get("Content-Length");
        if (length !== null && (!/^\d+$/.test(length) || Number(length) !== expectedBytes)) throw new Error("응답 바이트 크기가 같은 기록의 manifest와 다릅니다.");
        const reader = response.body?.getReader?.();
        if (!reader) {
          if (length === null) throw new Error("읽기 범위를 확인할 수 없는 응답입니다.");
          const bytes = new Uint8Array(await response.arrayBuffer()); if (!selected()) throw new Error("필드 선택이 바뀌었습니다."); return bytes;
        }
        const chunks = []; let size = 0;
        try {
          while (true) {
            const chunk = await reader.read(); if (!selected()) throw new Error("필드 선택이 바뀌었습니다."); if (chunk.done) break;
            size += chunk.value.byteLength;
            if (size > expectedBytes || size > window.fixtureFieldControls.LIMITS.bytes) throw new Error("원본 필드가 화면 읽기 바이트 범위를 넘습니다."); chunks.push(chunk.value);
          }
        } catch (error) { await reader.cancel().catch(() => {}); throw error; } finally { reader.releaseLock(); }
        if (size !== expectedBytes) throw new Error("필드 응답의 일부 바이트가 빠져 있습니다.");
        const bytes = new Uint8Array(size); let offset = 0; chunks.forEach(chunk => { bytes.set(chunk, offset); offset += chunk.byteLength; }); return bytes;
      }
      const model = await window.fixtureFieldControls.loadField(record, entry, fetchFieldBytes, selected);
      if (!selected()) return false; mounted = window.fixtureFieldViewer.mount(detail, model, selected); if (!mounted || !selected()) { mounted?.destroy(); return false; }
      state.fixtureViewer = mounted;
      const downloads = el("div", undefined, "button-row separated"); downloads.append(link("전체 절점 U JSON", artifactUrl(result.experiment_id, entry.path), "text-link", true));
      const prefix = entry.path.slice(0, entry.path.lastIndexOf("/") + 1);
      Object.values(model.field.sources).forEach(source => downloads.append(link(source.path, artifactUrl(result.experiment_id, prefix + source.path), "text-link artifact-path", true))); mounted.refs.provenance.append(downloads);
      return true;
    } catch (error) { if (selected()) clear(detail).append(el("p", error.message, "metric-reason")); return false; }
  }
  select.addEventListener("change", () => { void selectField(); }); choices.append(action("필드 다시 불러오기", selectField, "button secondary compact"));
  return selectField();
}
function renderContactFields(container, inspection) {
  const result = inspection.result;
  if (result.provenance?.adapter !== "structural.code_aster.contact_patch") return;
  const card = panel("같은 실험의 접촉 필드", "NATIVE CONTACT FIELD · SAME RECORD");
  card.classList.add("detail-wide", "contact-field-card");
  card.append(badge(result.status), badge(result.decision),
    el("p", "원본 메시의 절점·접촉 절점·적분점 값을 확인합니다. 원래 수치 판정과 미검증 요구사항은 위 결과를 따릅니다. 전체 필드 표시는 강도·물리·출시 승인이 아닙니다.", "hint separated"));
  const detail = el("div", undefined, "separated"); card.append(detail); container.append(card);
  const request = state.experimentRequest, store = activeStore();
  const current = () => request === state.experimentRequest && store === activeStore() && state.selectedExperiment === inspection;
  async function fetchBytes(relative) {
    if (!current()) throw new Error("선택한 실험이 바뀌었습니다.");
    const response = await fetch(artifactUrl(result.experiment_id, relative), { cache: "no-store", headers: { Accept: "application/octet-stream" } });
    if (!current()) throw new Error("선택한 실험이 바뀌었습니다.");
    if (!response.ok) throw new Error(`원본 산출물을 검증해 읽을 수 없습니다 (${response.status}).`);
    const size = Number(response.headers.get("Content-Length"));
    if (Number.isFinite(size) && size > 32 * 1024 * 1024) throw new Error("화면에서 읽을 수 있는 파일 크기를 넘습니다. 원본을 내려받아 확인하세요.");
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (!current()) throw new Error("선택한 실험이 바뀌었습니다.");
    return bytes;
  }
  detail.append(el("p", "같은 기록의 입력·메시·소스·전체 필드 해시를 확인하고 있습니다…", "hint"));
  Promise.resolve().then(async () => {
    if (!window.contactFieldInspector) throw new Error("접촉 필드 검사를 불러올 수 없습니다. 원본 산출물 목록을 확인하세요.");
    const field = await window.contactFieldInspector.loadContactField(inspection, fetchBytes, current);
    if (!current()) return;
    clear(detail);
    if (field.status !== "available") {
      detail.append(el("p", field.reason ?? "신뢰할 수 있는 접촉 필드를 읽지 못했습니다. 원본 산출물을 확인하세요.", "metric-reason"));
      return;
    }
    renderContactNativeValues(detail, field, result.experiment_id, current);
  }).catch(error => { if (current()) clear(detail).append(el("p", error.message, "metric-reason")); });
}

function renderContactNativeValues(container, field, identifier, isCurrent) {
  const meta = field.metadata, exact = value => typeof value === "number" ? (Object.is(value, -0) ? "-0" : String(value)) : text(value);
  // Keep IEEE signed zero in the point inspector as a JSON number, too.
  function nativeText(value) {
    if (typeof value === "number") return exact(value);
    if (Array.isArray(value)) return `[${value.map(nativeText).join(", ")}]`;
    if (value && typeof value === "object") return `{\n${Object.entries(value).map(([key, child]) => `${JSON.stringify(key)}: ${nativeText(child)}`).join(",\n")}\n}`;
    return JSON.stringify(value);
  }
  const coords = values => values.map(exact).join(" / ");
  const alias = id => Object.entries(meta.aliases ?? {}).filter(([, nodeId]) => String(nodeId) === String(id)).map(([name]) => name).join(" / ");
  const positions = new Map(field.nodes.map(node => [node.id, node]));
  const solids = field.cells.filter(cell => cell.type === "QUAD4"), edges = field.cells.filter(cell => cell.type === "SEG2");
  container.append(el("p", `${field.nodes.length}개 절점 · ${solids.length}개 QUAD4 · ${edges.length}개 SEG2 · ${field.slave.length}개 접촉 절점 · ${field.gauss.length}개 적분점 · 원본 단계 ${exact(meta.order)} / INST ${exact(meta.inst)}`, "hint"));
  container.append(el("p", `원본 소스 ${text(meta.sourceCommit)} · 모델 ${text(meta.modelRevision)} · 제안 ${text(meta.proposalRevision)}`, "mono separated"));
  const unknown = list(meta.validations).filter(item => item.blocking === true && item.status === "UNKNOWN");
  container.append(badge(meta.decision), el("p", `원래 미검증 요구사항 ${unknown.length}개를 유지합니다. native 접촉 간극은 UNAVAILABLE입니다. 응력 적분점의 W는 면적 가중치(m²)이며 기하 Z 좌표가 아닙니다.`, "hint separated"));
  const downloads = el("div", undefined, "button-row separated");
  field.downloads.forEach(item => downloads.append(link(item.path, artifactUrl(identifier, item.path), "text-link artifact-path", true)));
  container.append(downloads, rawDetail("표시 파일의 SHA·크기·개정과 캡처된 소스", { files: field.downloads, sourceHashes: meta.sourceHashes }));
  const controls = el("div", undefined, "button-row separated"), label = el("label", "원본 필드 / 성분"), component = el("select");
  component.setAttribute("aria-label", "접촉 원본 필드 성분");
  const options = [
    ["ux", "절점 변위 Ux (m)", "nodes", "m", row => row.u.dx],
    ["uy", "절점 변위 Uy (m)", "nodes", "m", row => row.u.dy],
    ["rfx", "절점 반력 RFx (N/m)", "nodes", "N/m", row => row.rf_n_per_m.dx],
    ["rfy", "절점 반력 RFy (N/m)", "nodes", "N/m", row => row.rf_n_per_m.dy],
    ["pressure", "접촉 절점 signed LAGS_C (Pa)", "slave", "Pa", row => row.normalTractionPa],
    ...[["xx", "SIXX"], ["yy", "SIYY"], ["zz", "SIZZ"], ["xy", "SIXY"]].map(([key, name]) => [key, `적분점 ${name} (Pa)`, "gauss", "Pa", row => row.stress_pa[key]]),
  ];
  options.forEach(([key, name]) => option(component, key, name)); component.value = "uy";
  label.append(component); controls.append(label); container.append(controls);
  const canvas = el("canvas"); canvas.width = 900; canvas.height = 520; canvas.className = "contact-field-canvas";
  canvas.setAttribute("role", "img"); canvas.setAttribute("aria-label", `${identifier}의 원본 QUAD4·SEG2 메시와 실제 필드 점`);
  const legend = el("p", undefined, "hint contact-field-legend"), description = el("p", undefined, "hint");
  const scatter = el("canvas"); scatter.width = 900; scatter.height = 280; scatter.className = "contact-field-canvas"; scatter.hidden = true;
  scatter.setAttribute("role", "img"); scatter.setAttribute("aria-label", `${identifier}의 실제 접촉 절점 X와 부호 있는 LAGS_C`);
  const picked = rawDetail("선택한 실제 원본 점", null);
  container.append(canvas, legend, description, scatter, picked);
  const filter = el("label", "원본 절점 ID / raw ID 또는 셀 ID로 찾기 (정확히)"), input = el("input");
  input.type = "text"; input.placeholder = "빈칸이면 전체 필드"; input.setAttribute("aria-label", "접촉 원본 필드 ID 필터"); filter.append(input); container.append(filter);
  const rows = el("div"), caption = el("p", undefined, "hint"), pagination = el("div", undefined, "button-row separated");
  let page = 0, filtered = [], plotted = [];
  const previous = action("이전 필드 50개", () => { if (isCurrent()) { page--; drawRows(); } });
  const next = action("다음 필드 50개", () => { if (isCurrent()) { page++; drawRows(); } });
  const last = action("마지막 필드 50개", () => { if (isCurrent()) { page = Math.max(0, Math.ceil(filtered.length / 50) - 1); drawRows(); } });
  pagination.append(previous, next, last); container.append(rows, caption, pagination);
  const selected = () => options.find(item => item[0] === component.value);
  function rowId(row, kind) { return kind === "gauss" ? `${row.cellId}:${row.order}:${row.point}:${row.subpoint}` : String(row.id); }
  function drawRows() {
    if (!isCurrent()) return;
    const kind = selected()[2], start = page * 50, visible = filtered.slice(start, start + 50);
    let headings, values;
    if (kind === "nodes") {
      headings = ["절점 / alias", "DEPL raw ID", "RF raw ID", "X / Y / Z (m)", "Ux (m)", "Uy (m)", "RFx (N/m)", "RFy (N/m)"];
      values = visible.map(row => [`${row.id}${alias(row.id) ? ` (${alias(row.id)})` : ""}`, row.rawDeplId, row.rawReactionId, coords(row.xyz_m), exact(row.u.dx), exact(row.u.dy), exact(row.rf_n_per_m.dx), exact(row.rf_n_per_m.dy)]);
    } else if (kind === "slave") {
      headings = ["접촉 절점 / alias", "DEPL.LAGS_C raw ID", "X / Y / Z (m)", "signed LAGS_C (Pa)"];
      values = visible.map(row => [`${row.id}${alias(row.id) ? ` (${alias(row.id)})` : ""}`, row.rawId, coords(row.xyz_m), exact(row.normalTractionPa)]);
    } else {
      headings = ["셀 ID", "raw MAILLE", "순서", "POINT", "SOUS_POINT", "X / Y (m)", "W (m²)", "SIXX (Pa)", "SIYY (Pa)", "SIZZ (Pa)", "SIXY (Pa)"];
      values = visible.map(row => [String(row.cellId), row.rawElementId, String(row.order), String(row.point), String(row.subpoint), coords(row.xy_m), exact(row.weight_m2), ...["xx", "yy", "zz", "xy"].map(name => exact(row.stress_pa[name]))]);
    }
    clear(rows).append(table(headings, values));
    caption.textContent = filtered.length ? `${start + 1}–${start + visible.length} / ${filtered.length}개 원본 행 표시` : "해당 원본 ID가 없습니다.";
    previous.disabled = page === 0; next.disabled = start + 50 >= filtered.length; last.disabled = next.disabled;
  }
  function drawScatter(points, valueOf) {
    const ctx = scatter.getContext("2d"); if (!ctx) return;
    ctx.clearRect(0, 0, scatter.width, scatter.height);
    const xs = points.map(row => row.xyz_m[0]), ys = points.map(valueOf), xmin = Math.min(...xs), xmax = Math.max(...xs), ymin = Math.min(...ys), ymax = Math.max(...ys);
    const dx = xmax - xmin, dy = ymax - ymin;
    if (![xmin, xmax, ymin, ymax, dx, dy].every(Number.isFinite) || !(dx > 0)) return;
    const px = x => 65 + (x - xmin) / dx * (scatter.width - 110), py = y => dy === 0 ? scatter.height / 2 : 30 + (ymax - y) / dy * (scatter.height - 75);
    ctx.strokeStyle = "#6d7d86"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(65, 25); ctx.lineTo(65, scatter.height - 45); ctx.lineTo(scatter.width - 45, scatter.height - 45); ctx.stroke();
    ctx.fillStyle = "#172b37"; ctx.font = "12px sans-serif";
    ctx.fillText(`X (m): ${exact(xmin)} → ${exact(xmax)}`, 70, scatter.height - 12);
    ctx.fillText(`signed LAGS_C (Pa): ${exact(ymin)} → ${exact(ymax)}`, 75, 18);
    points.forEach(row => { ctx.fillStyle = alias(row.id) ? "#a83836" : "#19746e"; ctx.beginPath(); ctx.arc(px(row.xyz_m[0]), py(valueOf(row)), 4, 0, Math.PI * 2); ctx.fill(); });
  }
  function drawMesh() {
    if (!isCurrent()) return;
    const ctx = canvas.getContext("2d"), [key, name, kind, unit, valueOf] = selected(), points = field[kind];
    scatter.hidden = kind !== "slave";
    description.textContent = kind === "slave" ? "도트와 아래 X–LAGS_C 산점도는 실제 slave 접촉 절점의 부호 있는 값입니다. master·비접촉 절점의 가상 0이나 반력/면적 대체값을 만들지 않습니다."
      : kind === "gauss" ? "도트는 실제 적분점 XY의 원본 응력입니다. 보간·절점 평균·외삽·요소 전체 색칠을 하지 않습니다. 적분점 기하 Z는 UNAVAILABLE입니다."
        : "도트는 원본 절점 값입니다. 변형 배율이나 연속장 보간을 적용하지 않았으며, 메시 선은 캡처된 원래 좌표와 연결을 따릅니다.";
    if (!ctx) { legend.textContent = "브라우저가 캔버스를 표시하지 못합니다. 전체 원본 표와 다운로드를 확인하세요."; return; }
    let xmin = Infinity, xmax = -Infinity, ymin = Infinity, ymax = -Infinity, minimum = Infinity, maximum = -Infinity;
    field.nodes.forEach(row => { xmin = Math.min(xmin, row.xyz_m[0]); xmax = Math.max(xmax, row.xyz_m[0]); ymin = Math.min(ymin, row.xyz_m[1]); ymax = Math.max(ymax, row.xyz_m[1]); });
    points.forEach(row => { minimum = Math.min(minimum, valueOf(row)); maximum = Math.max(maximum, valueOf(row)); });
    const dx = xmax - xmin, dy = ymax - ymin, span = maximum - minimum;
    ctx.clearRect(0, 0, canvas.width, canvas.height); plotted = [];
    if (![dx, dy, minimum, maximum, span].every(Number.isFinite) || !(dx > 0 && dy > 0)) { legend.textContent = "화면 좌표·색상 범위를 표시할 수 없습니다. 원본 표를 확인하세요."; return; }
    const scale = Math.min((canvas.width - 70) / dx, (canvas.height - 70) / dy), left = (canvas.width - dx * scale) / 2, top = (canvas.height - dy * scale) / 2;
    const xy = coords => [left + (coords[0] - xmin) * scale, top + (ymax - coords[1]) * scale];
    field.cells.forEach(cell => {
      ctx.strokeStyle = cell.type === "SEG2" ? "#172b37a0" : "#66798550"; ctx.lineWidth = cell.type === "SEG2" ? 1 : .5; ctx.beginPath();
      cell.nodeIds.forEach((id, index) => { const [x, y] = xy(positions.get(id).xyz_m); if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); });
      if (cell.type === "QUAD4") ctx.closePath(); ctx.stroke();
    });
    points.forEach(row => {
      const [x, y] = xy(kind === "gauss" ? row.xy_m : row.xyz_m), value = valueOf(row), fraction = span === 0 ? .5 : Math.max(0, Math.min(1, (value - minimum) / span));
      ctx.fillStyle = `hsl(${230 * (1 - fraction)} 65% 48%)`; ctx.beginPath(); ctx.arc(x, y, kind === "slave" ? 4 : kind === "gauss" ? 1.8 : 2.2, 0, Math.PI * 2); ctx.fill();
      plotted.push({ x, y, row, kind });
      if (kind !== "gauss" && alias(row.id)) { ctx.strokeStyle = "#172b37"; ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(x, y, 6, 0, Math.PI * 2); ctx.stroke(); ctx.fillStyle = "#172b37"; ctx.font = "12px sans-serif"; ctx.fillText(alias(row.id), x + 7, y - 5); }
    });
    canvas.setAttribute("aria-label", `${identifier} · ${name} · 원본 ${points.length}개 점과 ${solids.length} QUAD4 / ${edges.length} SEG2`);
    legend.textContent = `${name} · 실제 점 ${points.length}개 · 최솟값 ${exact(minimum)} / 최댓값 ${exact(maximum)} ${unit} · 파랑 → 빨강 · 클릭하면 실제 행 표시`;
    if (kind === "slave") drawScatter(points, valueOf);
  }
  function changeFilter() {
    if (!isCurrent()) return;
    const kind = selected()[2], query = input.value.trim();
    filtered = !query ? field[kind] : field[kind].filter(row => kind === "gauss" ? String(row.cellId) === query || row.rawElementId === query || rowId(row, kind) === query : String(row.id) === query || row.rawId === query || row.rawDeplId === query || row.rawReactionId === query || alias(row.id).split(" / ").includes(query));
    page = 0; drawRows();
  }
  canvas.addEventListener("click", event => {
    if (!isCurrent()) return;
    const bounds = canvas.getBoundingClientRect(); if (!(bounds.width > 0 && bounds.height > 0)) return;
    const x = (event.clientX - bounds.left) * canvas.width / bounds.width, y = (event.clientY - bounds.top) * canvas.height / bounds.height;
    let near = null, distance = 100;
    plotted.forEach(point => { const d = (point.x - x) ** 2 + (point.y - y) ** 2; if (d < distance) { near = point; distance = d; } });
    picked.querySelector("pre").textContent = nativeText(near ? { location: near.kind, id: rowId(near.row, near.kind), captured_native_row: near.row } : null); picked.open = true;
  });
  input.addEventListener("input", changeFilter);
  component.addEventListener("change", () => { if (!isCurrent()) return; input.value = ""; picked.querySelector("pre").textContent = pretty(null); changeFilter(); drawMesh(); });
  changeFilter(); drawMesh();
  container.append(rawDetail("전체 원본 메시 연결·그룹·alias와 표시 한계", { cells: field.cells, nodeGroups: field.nodeGroups, cellGroups: field.cellGroups, aliases: meta.aliases, limitations: field.limitations }));
}

function renderPdeFields(container, inspection) {
  const result = inspection.result;
  if (!String(result.provenance?.adapter ?? "").startsWith("pde.")) return;
  const card = panel("같은 실험의 PDE 필드", "NATIVE FIELD · SAME RECORD");
  card.classList.add("detail-wide", "pde-field-card");
  card.append(badge(result.status), badge(result.decision),
    el("p", "원본 절점 값과 2D 메시를 확인합니다. 좌표와 필드의 단위는 1(무차원)입니다. 수치 검증 상태와 물리·모델 미검증 항목은 위의 원래 판정을 따릅니다.", "hint separated"));
  const controls = el("div", undefined, "button-row separated"), detail = el("div", undefined, "separated");
  card.append(controls, detail); container.append(card);
  const request = state.experimentRequest, store = activeStore();
  const current = () => request === state.experimentRequest && store === activeStore() && state.selectedExperiment === inspection;
  let fieldRequest = 0;
  async function fetchBytes(relative) {
    if (!current()) throw new Error("선택한 실험이 바뀌었습니다.");
    const response = await fetch(artifactUrl(result.experiment_id, relative), { cache: "no-store", headers: { Accept: "application/octet-stream" } });
    if (!current()) throw new Error("선택한 실험이 바뀌었습니다.");
    if (!response.ok) throw new Error(`원본 산출물을 검증해 읽을 수 없습니다 (${response.status}).`);
    const size = Number(response.headers.get("Content-Length"));
    if (Number.isFinite(size) && size > 32 * 1024 * 1024) throw new Error("화면에서 읽을 수 있는 파일 크기를 넘습니다. 원본을 내려받아 확인하세요.");
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (!current()) throw new Error("선택한 실험이 바뀌었습니다.");
    return bytes;
  }
  clear(detail).append(el("p", "같은 기록의 입력·소스·필드 해시를 확인하고 있습니다…", "hint"));
  Promise.resolve().then(async () => {
    if (!window.pdeFieldInspector) throw new Error("PDE 필드 검사를 불러올 수 없습니다. 원본 산출물 목록을 확인하세요.");
    const catalog = await window.pdeFieldInspector.loadCatalog(inspection, fetchBytes, current);
    if (!current()) return;
    clear(detail);
    if (!["available", "partial"].includes(catalog.status) || !catalog.entries.length) {
      detail.append(el("p", catalog.reason ?? "이 기록은 원본 다운로드로 확인할 수 있습니다.", "empty-state"));
      return;
    }
    if (catalog.reason) controls.append(el("p", catalog.reason, "hint"));
    const label = el("label", "메시 / 시간 단계"), select = el("select"); label.append(select); controls.append(label);
    catalog.entries.forEach((entry, index) => {
      const mesh = entry.cellsPerAxis === null ? `메시 레벨 ${entry.level}` : `축당 ${entry.cellsPerAxis}개`;
      const time = entry.stepIndex === null ? "" : ` · 단계 ${entry.stepIndex} · t=${number(entry.time)}${entry.solverStatus === "NOT_RUN" ? " · 초기조건" : ""}`;
      option(select, String(index), `${mesh}${time}`);
    });
    select.value = String(catalog.entries.length - 1);
    async function selectField() {
      const sequence = ++fieldRequest;
      const entry = catalog.entries[Number(select.value)];
      const selected = () => current() && sequence === fieldRequest;
      clear(detail).append(el("p", "선택한 원본 필드와 연결 파일을 검증하고 있습니다…", "hint"));
      try {
        const field = await window.pdeFieldInspector.loadField(catalog, entry, fetchBytes, selected);
        if (!selected()) return;
        clear(detail);
        if (field.status !== "available") {
          detail.append(el("p", field.reason ?? "이 단계의 신뢰할 수 있는 필드가 없습니다. 원본 산출물을 확인하세요.", "metric-reason"));
          return;
        }
        renderPdeNodes(detail, field, result.experiment_id);
      } catch (error) { if (selected()) clear(detail).append(el("p", error.message, "metric-reason")); }
    }
    select.addEventListener("change", () => { void selectField(); });
    await selectField();
  }).catch(error => { if (current()) clear(detail).append(el("p", error.message, "metric-reason")); });
}
function renderPdeNodes(container, field, identifier) {
  const selection = field.selection;
  container.append(el("p", `${number(field.nodes.length)}개 절점 · ${number(field.cells.length)}개 삼각형 · ${selection.solverStatus}${selection.time === null ? "" : ` · t=${number(selection.time)}`} · 원본 모델 ${text(field.metadata.modelRevision)}`, "hint"));
  const links = el("div", undefined, "button-row separated");
  field.downloads.forEach(item => links.append(link(item.path, artifactUrl(identifier, item.path), "text-link artifact-path", true)));
  container.append(links);
  const label = el("label", "필드 성분"), component = el("select");
  field.components.forEach((name, index) => option(component, String(index), name));
  label.append(component); container.append(label);
  const canvas = el("canvas"); canvas.width = 900; canvas.height = 520; canvas.className = "pde-field-canvas";
  canvas.setAttribute("role", "img"); canvas.setAttribute("aria-label", `${identifier}의 원본 PDE 메시와 선택한 성분의 셀 평균 색상`);
  const legend = el("p", undefined, "hint pde-field-legend");
  container.append(canvas, legend, el("p", "색상은 삼각형의 세 원본 절점 값 평균입니다. 보간한 연속장이나 수치 오차 판정을 대신하지 않습니다. 아래 표는 원본 절점 값입니다.", "hint"));
  const filter = el("label", "원본 native 절점 ID로 찾기"), input = el("input");
  input.type = "number"; input.min = "0"; input.step = "1"; input.placeholder = "빈칸이면 전체 절점"; filter.append(input); container.append(filter);
  const rows = el("div"), caption = el("p", undefined, "hint"), pagination = el("div", undefined, "button-row separated");
  let page = 0, nodes = field.nodes;
  const previous = action("이전 50개", () => { page--; drawRows(); }), next = action("다음 50개", () => { page++; drawRows(); });
  pagination.append(previous, next); container.append(rows, caption, pagination);
  function drawRows() {
    const start = page * 50, visible = nodes.slice(start, start + 50);
    clear(rows).append(table(["Native 절점", "원본 MSH 절점", "X / Y (1)", ...field.components.map(name => `${name} (1)`)], visible.map(node => [String(node.id), node.sourceId, node.coordinates.map(number).join(" / "), ...node.values.map(number)])));
    caption.textContent = nodes.length ? `${start + 1}–${start + visible.length} / ${number(nodes.length)}개 표시` : "해당 절점이 없습니다.";
    previous.disabled = page === 0; next.disabled = start + 50 >= nodes.length;
  }
  function drawMesh() {
    const ctx = canvas.getContext("2d");
    if (!ctx) { legend.textContent = "브라우저가 2D 표면을 표시하지 못합니다. 원본 절점 표와 다운로드를 확인하세요."; return; }
    const axis = Number(component.value), positions = new Map(field.nodes.map(node => [node.id, node]));
    let xmin = Infinity, xmax = -Infinity, ymin = Infinity, ymax = -Infinity, minimum = Infinity, maximum = -Infinity;
    field.nodes.forEach(node => { xmin = Math.min(xmin, node.coordinates[0]); xmax = Math.max(xmax, node.coordinates[0]); ymin = Math.min(ymin, node.coordinates[1]); ymax = Math.max(ymax, node.coordinates[1]); minimum = Math.min(minimum, node.values[axis]); maximum = Math.max(maximum, node.values[axis]); });
    const spanx = xmax - xmin, spany = ymax - ymin, span = maximum - minimum;
    if (!(spanx > 0 && spany > 0) || ![spanx, spany, minimum, maximum, span].every(Number.isFinite)) { ctx.clearRect(0, 0, canvas.width, canvas.height); legend.textContent = "화면 좌표 범위를 표시할 수 없습니다. 원본 절점 표를 확인하세요."; return; }
    const scale = Math.min((canvas.width - 60) / spanx, (canvas.height - 60) / spany);
    const left = (canvas.width - scale * spanx) / 2, top = (canvas.height - scale * spany) / 2;
    ctx.clearRect(0, 0, canvas.width, canvas.height); ctx.lineWidth = .35; ctx.strokeStyle = "#354a5960";
    field.cells.forEach(cell => {
      const triangle = cell.nodeIds.map(id => positions.get(id));
      const value = triangle.reduce((sum, node) => sum + node.values[axis] / 3, 0);
      const fraction = span === 0 ? .5 : Math.max(0, Math.min(1, (value - minimum) / span));
      ctx.fillStyle = `hsl(${230 * (1 - fraction)} 65% 54%)`; ctx.beginPath();
      triangle.forEach((node, index) => { const x = left + (node.coordinates[0] - xmin) * scale, y = top + (ymax - node.coordinates[1]) * scale; if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); });
      ctx.closePath(); ctx.fill(); ctx.stroke();
    });
    legend.textContent = `${field.components[axis]} · 원본 절점 최솟값 ${number(minimum)} / 최댓값 ${number(maximum)} (1) · 파랑 → 빨강`;
  }
  input.addEventListener("input", () => { nodes = input.value.trim() ? field.nodes.filter(node => node.id === Number(input.value)) : field.nodes; page = 0; drawRows(); });
  component.addEventListener("change", drawMesh); drawRows(); drawMesh();
  container.append(rawDetail("원본 경계 · 연성 영역/인터페이스 · 메시 매핑", { boundaries: field.boundaries, interface: field.interface, mapping: field.mapping, binding: field.binding, cells: field.cells }));
}
function renderFixtureStressFields(container, result) {
  const artifacts = list(result.artifacts);
  const fields = artifacts.filter((item) => /(?:^|\/)stress_field\.json$/.test(item.path));
  if (!fields.length) return;
  const card = panel("원본과 연결한 응력 성분", "DIAGNOSTIC STRESS · MPa");
  card.classList.add("detail-wide");
  card.append(badge("UNKNOWN", "강도·응력 수렴 미검증"), el("p", "평균 절점 응력의 6개 성분과 von Mises 값을 확인합니다. 좌표는 mm, 성분은 전체 CAD 축 기준 MPa입니다. 전단 성분은 응력 텐서 성분입니다. 이 표로 강도나 사용을 승인하지 않습니다.", "hint separated"));
  const choices = el("div", undefined, "button-row separated");
  const detail = el("div", undefined, "separated");
  let request = 0;
  fields.forEach((artifact) => choices.append(action(artifact.path.replace(/^simulation\//, ""), async () => {
    const sequence = ++request, store = activeStore();
    clear(detail).append(el("p", "산출물과 원본 FRD 해시를 확인하고 있습니다…", "hint"));
    try {
      const raw = await api(artifactUrl(result.experiment_id, artifact.path));
      if (sequence !== request || store !== activeStore() || state.selectedExperiment?.result?.experiment_id !== result.experiment_id) return;
      const field = window.fixtureControls.verifyStressField(raw, artifacts, artifact.path);
      renderStressNodes(detail, field, result.experiment_id, artifact.path);
    } catch (error) {
      if (sequence === request && store === activeStore()) clear(detail).append(el("p", error.message, "metric-reason"));
    }
  }, "button secondary compact")));
  card.append(choices, detail); container.append(card);
}
function renderStressNodes(container, field, identifier, path) {
  clear(container);
  const sourcePath = path.slice(0, path.lastIndexOf("/") + 1) + field.source_frd.path;
  const sources = el("div", undefined, "button-row");
  sources.append(link("검증된 원본 FRD", artifactUrl(identifier, sourcePath), "text-link", true), link("6성분 전체 JSON", artifactUrl(identifier, path), "text-link", true));
  container.append(el("p", `${number(field.node_count)}개 절점 · AVERAGED_NODAL · engineering_valid=false`, "hint"), sources);
  const filter = el("label", "절점 ID로 찾기");
  const input = el("input"); input.type = "number"; input.min = "1"; input.step = "1"; input.placeholder = "빈칸이면 전체 절점";
  filter.append(input); container.append(filter);
  const rows = el("div"), controls = el("div", undefined, "button-row separated"), caption = el("p", undefined, "hint");
  let page = 0, selected = field.nodes;
  const previous = action("이전 50개", () => { page--; draw(); }, "button subtle compact");
  const next = action("다음 50개", () => { page++; draw(); }, "button subtle compact");
  controls.append(previous, next); container.append(rows, caption, controls);
  function draw() {
    clear(rows);
    const start = page * 50, visible = selected.slice(start, start + 50);
    rows.append(table(["절점", "X / Y / Z (mm)", ...field.component_order, "von Mises"], visible.map((node) => [String(node.node_id), node.position_mm.map(number).join(" / "), ...node.stress_MPa.map(number), number(node.von_mises_MPa)])));
    caption.textContent = selected.length ? `${start + 1}–${start + visible.length} / ${number(selected.length)}개 표시` : "해당 절점이 없습니다.";
    previous.disabled = page === 0; next.disabled = start + 50 >= selected.length;
  }
  input.addEventListener("input", () => { selected = input.value.trim() ? field.nodes.filter((node) => node.node_id === Number(input.value)) : field.nodes; page = 0; draw(); });
  draw();
}
function renderCadPreview(container, inspection) {
  const presentation = window.resultPresentation, result = inspection.result;
  const request = state.experimentRequest, store = activeStore();
  const current = () => container.isConnected && request === state.experimentRequest && store === activeStore()
    && !state.storeSwitching && state.selectedExperiment === inspection;
  const ownPreview = presentation.cadPreview(inspection); let parentLink = null;
  if (!ownPreview && (result.parent_experiment_id === null || result.parent_experiment_id === undefined)) {
    container.append(el("p", "이 실험에 등록된 형상 미리보기가 없습니다. 제공된 수치 결과와 원본 파일을 확인하세요.", "empty-state"));
    return Promise.resolve(false);
  }
  const loading = el("p", "같은 CAD 개정의 원본 형상을 확인하고 있습니다…", "empty-state surface-loading");
  const note = el("p", "이 미리보기는 CAD 형상입니다. 해석 메시, 변형장, 구속·하중 오버레이와 절점 변위는 제공하지 않습니다.", "visual-note");
  const retry = action("형상 다시 불러오기", loadPreview, "button secondary compact"); retry.hidden = true;
  container.append(loading, retry, note);
  async function loadPreview() {
    if (!current()) return false;
    retry.disabled = true;
    try {
      let preview = ownPreview;
      if (!preview) {
        const parentId = presentation.parentCadId(inspection);
        const parent = await api(`/api/experiments/${idPath(parentId)}`);
        if (!current()) return false;
        preview = presentation.parentCadPreview(inspection, parent);
      }
      if (!current()) return false;
      if (preview.parent) {
        container.querySelector("h2").textContent = "사용한 부모 CAD 형상(해석 메시/변형장 아님)";
        note.textContent = "같은 CAD 개정의 부모 실험에서 저장한 원본 형상입니다. 해석 메시, 변형장, 구속·하중 오버레이와 절점 변위는 이 미리보기에서 제공하지 않습니다.";
        parentLink ??= experimentButton(preview.experimentId, "이 형상의 부모 CAD 실험 보기 →"); note.append(el("br"), parentLink);
      } else note.textContent = "같은 실험에서 저장한 원본 CAD 형상입니다. 해석 메시, 변형장, 구속·하중 오버레이와 절점 변위는 이 미리보기에서 제공하지 않습니다.";
      const opened = preview.kind === "surface" ? await openSurface(container, preview, current)
        : await openCadImage(container, preview, current);
      if (!current() || !opened) return false;
      loading.remove(); retry.hidden = true; return true;
    } catch (error) {
      if (current()) { loading.textContent = `형상을 불러오지 못했습니다. ${error.message}`; retry.hidden = false; }
      return false;
    } finally { if (current()) retry.disabled = false; }
  }
  return Promise.resolve().then(loadPreview);
}
function openCadImage(container, preview, current) {
  if (!current()) return Promise.resolve(false);
  return new Promise((resolve, reject) => {
    const picture = el("img", undefined, "preview-image"); picture.hidden = true;
    picture.alt = preview.parent ? "사용한 부모 CAD 형상(해석 메시/변형장 아님)" : "같은 실험의 원본 CAD 형상";
    picture.addEventListener("load", () => { if (!current()) { picture.remove(); resolve(false); return; } picture.hidden = false; resolve(true); });
    picture.addEventListener("error", () => { picture.remove(); if (!current()) resolve(false); else reject(new Error("등록된 원본 CAD 이미지를 불러올 수 없습니다.")); });
    container.insertBefore(picture, container.querySelector(".visual-note"));
    picture.src = artifactUrl(preview.experimentId, preview.path);
  });
}
let viewerScript;
async function openSurface(container, preview, current) {
  if (!current()) return false;
  const surface = await api(artifactUrl(preview.experimentId, preview.path));
  if (!current()) return false;
  if (!Array.isArray(surface.bounds) || surface.bounds.length !== 2 || !Array.isArray(surface.faces)) throw new Error("원본 viewer가 읽을 수 있는 surface artifact가 아닙니다.");
  if (!window.createFaceViewer) {
    viewerScript ??= new Promise((resolve, reject) => { const script = document.createElement("script"); script.src = "/upstream/surface_viewer.js"; script.addEventListener("load", resolve); script.addEventListener("error", () => { script.remove(); reject(new Error("원본 surface viewer를 불러올 수 없습니다.")); }); document.head.append(script); }).catch(error => { viewerScript = undefined; throw error; });
    await viewerScript;
  }
  if (!current()) return false;
  const canvas = el("canvas"); canvas.className = "preview-canvas";
  canvas.setAttribute("aria-label", `${preview.parent ? "사용한 부모 CAD 형상(해석 메시/변형장 아님)" : "같은 실험의 원본 CAD 표면"} · 드래그 회전, 휠 확대, 클릭 면 확인`);
  const stage = el("div", undefined, "surface-stage"), controls = el("div", undefined, "surface-controls");
  const selection = el("p", window.resultPresentation.faceDescription(null), "surface-selection");
  const selectedRecord = rawDetail("선택한 면의 원본 정보", null); selectedRecord.hidden = true;
  stage.append(canvas); container.insertBefore(stage, container.querySelector(".visual-note"));
  const viewer = window.createFaceViewer(canvas, face => {
    if (!current()) return;
    selection.textContent = window.resultPresentation.faceDescription(face); selectedRecord.hidden = !face;
    selectedRecord.querySelector("pre").textContent = pretty(face ? { component_id: face.component_id,
      catalog_face_id: face.catalog_face_id, display_face_id: face.id, type: face.type ?? face.surface } : null);
  }); viewer.setData(surface); state.viewer = viewer;
  controls.append(el("span", "드래그 회전 · 휠 확대 · 클릭 면 선택", "hint"), action("기본 보기", () => {
    if (!current()) return;
    viewer.setData(surface); selection.textContent = window.resultPresentation.faceDescription(null); selectedRecord.hidden = true;
  }, "button subtle compact"));
  stage.append(controls, selection, selectedRecord);
  return true;
}
async function compareExperiments() {
  if (state.comparison.size < 2) return;
  const store = activeStore(), ids = [...state.comparison];
  const data = await api(`/api/compare?${new URLSearchParams({ ids: ids.join(",") })}`);
  if (state.storeSwitching || store !== activeStore() || ids.join("\n") !== [...state.comparison].join("\n")) return;
  renderComparison(data);
}
function renderComparison(data) {
  const records = list(data.comparison ?? data.results ?? data); const container = clear("comparisonDetail"); container.hidden = false;
  const card = panel("검증된 기록 비교", "COMPARE · VALIDITY RETAINED"); card.classList.add("compare-card");
  card.append(el("p", "단위와 유효성을 함께 읽으세요. INVALID 값은 성능 우열이나 최적 후보의 근거로 사용할 수 없습니다.", "hint separated"));
  const names = new Set(records.flatMap((record) => Object.keys(record.metrics ?? {})));
  const rows = [["실행 상태", ...records.map((record) => badge(record.status))], ["출시 판정", ...records.map((record) => badge(record.decision))], ["연구 변수", ...records.map((record) => el("span", text(record.parameters), "mono"))], ["미확인 항목", ...records.map((record) => el("span", list(record.unknown).map((name, index) => window.resultPresentation.validationName(name, index)).join(" · "), "hint"))]];
  [...names].forEach((name, index) => {
    const label = el("span", name === "max_displacement" ? "저장된 최대 변위 응답" : window.resultPresentation.metricName(name, index)); label.title = name;
    rows.push([label, ...records.map((record) => metricCell(record.metrics?.[name]))]);
  });
  if (names.has("max_displacement")) card.append(el("p", "전체 변위장 최대 |U|와 하중부 |UZ|는 다른 응답입니다. 아래 값의 위치·성분은 원 실험의 결과 정의와 전체 필드에서 확인하세요.", "hint"));
  card.append(table(["응답", ...records.map((record) => record.experiment_id)], rows), action("비교 닫기", () => { container.hidden = true; })); container.append(card);
}

function renderJob() {
  const job = state.job; if (!job) { $("jobPanel").hidden = true; return; }
  const workflow = job.operation === "research_run" ? window.researchControls.jobWorkflow(job)
    : window.resultPresentation.workflow(job, workflowContext(job, "job"));
  $("jobPanel").hidden = false; $("jobPanel").classList.toggle("finished", workflow.tone === "recorded"); $("jobPanel").classList.toggle("failed", workflow.tone === "failed");
  const indicator = $("jobPanel").querySelector(".job-indicator"); if (indicator) indicator.style.animation = activeJob(job) ? "" : "none";
  $("jobTitle").textContent = Object.hasOwn(operationNames, job.operation) ? operationNames[job.operation] : "작업 상태";
  const marker = badge(job.status, workflow.stage); $("jobStatus").className = workflow.tone === "failed" ? "badge fail" : marker.className; $("jobStatus").textContent = marker.textContent;
  $("jobStatus").dataset.status = marker.dataset.status; $("jobStatus").title = marker.title;
  $("jobMessage").textContent = workflow.next;
  if (job.operation === "research_run" && activeJob(job)) {
    const phase = window.researchControls.phaseLabel(job.progress?.phase, job.progress);
    if (phase) $("jobMessage").append(el("small", phase, "research-phase"));
  }
  $("jobCancelBtn").hidden = !activeJob(job);
  $("jobCancelBtn").disabled = job.status === "CANCEL_REQUESTED";
  $("jobCancelBtn").textContent = job.status === "CLEANUP_PENDING" ? "종료 재시도" : "작업 취소";
  $("jobJson").textContent = pretty(job);
  if (job.operation === "research_run") { retainResearchJob(job); renderResearchAnswers(); }
  updateControls();
}
function schedulePoll(delay = 1200) {
  clearTimeout(state.pollTimer);
  if (activeJob(state.job)) state.pollTimer = setTimeout(pollJob, delay);
}
async function pollJob() {
  const identifier = state.job?.id; if (!identifier || !activeJob(state.job)) return;
  try {
    const job = await api(`/api/jobs/${idPath(identifier)}`);
    if (identifier !== state.job?.id) return;
    state.job = job; renderJob();
    if (activeJob(job)) { schedulePoll(); return; }
    await loadOverview({ followJobs: false });
    if (job.operation === "research_run") await loadResearchStatus();
    const handler = state.handlers.get(identifier); state.handlers.delete(identifier);
    if (job.status === "COMPLETED" && handler) await handler(job.result);
    if (job.status === "FAILED") { if (job.operation === "research_run") researchError(new Error(text(job.error))); else notify(`작업이 실패했습니다: ${text(job.error)}`); }
    if (job.status === "CANCELLED") notify("작업 취소가 완료됐습니다. 부분 기록은 보존됩니다.", true);
  } catch (error) {
    if (activeJob(state.job)) {
      $("jobMessage").textContent = state.job?.operation === "research_run" ? "작업 상태 연결을 확인할 수 없습니다. 종료를 단정하지 않고 다시 확인합니다."
        : `상태 연결을 확인할 수 없습니다: ${error.message} · 실행 실패로 단정하지 않고 다시 확인합니다.`; schedulePoll(4000);
    } else if (state.job?.operation === "research_run") researchError(error);
    else notify(`작업 상태는 ${labels[state.job?.status] ?? state.job?.status}입니다. 후속 기록 읽기 실패: ${error.message}`);
  }
}
async function runJob(operation, arguments_, handler) {
  if (!writable() && !readOperations.has(operation)) throw new Error("읽기 전용 라이브러리에서는 새 작업을 실행할 수 없습니다. 작업 저장소로 전환하세요.");
  if (busy()) throw new Error("이미 실행 중인 작업이 있습니다. 종료 상태를 확인한 뒤 다음 작업을 시작하세요.");
  if (!available(operation)) throw new Error("이 작업은 현재 실행 가능한 capability로 제공되지 않습니다.");
  const researchRequest = operation === "research_run" ? { ...arguments_, store: activeStore() } : null;
  if (researchRequest && (state.researchLoading || !window.researchControls.canRun(state.researchStatus, researchContext()))) throw new Error("AI 연구 연결과 작업 저장소 상태를 확인하세요.");
  state.submitting = true; updateControls();
  try {
    const body = operation === "pde_run" && arguments_.backend === "pde.fenicsx.imported"
      ? window.importedMeshControls.requestBody(operation, arguments_) : JSON.stringify({ operation, arguments: arguments_ });
    const job = await api("/api/jobs", { method: "POST", body });
    if (researchRequest) state.researchContexts.set(job.id, researchRequest);
    state.job = job; if (handler) state.handlers.set(job.id, handler); renderJob();
    if (activeJob(job)) schedulePoll();
    else {
      await loadOverview({ followJobs: false });
      if (operation === "research_run") await loadResearchStatus();
      if (job.status === "COMPLETED" && handler) { state.handlers.delete(job.id); await handler(job.result); }
      else if (job.status === "FAILED") { if (operation === "research_run") researchError(new Error(text(job.error))); else notify(text(job.error)); }
    }
  } finally { state.submitting = false; updateControls(); }
}
$("jobCancelBtn").addEventListener("click", async () => {
  const identifier = state.job?.id;
  if (!identifier || !activeJob(state.job) || state.job.status === "CANCEL_REQUESTED") return;
  $("jobCancelBtn").disabled = true;
  try {
    const job = await api(`/api/jobs/${idPath(identifier)}/cancel`, { method: "POST", body: "{}" });
    if (identifier !== state.job?.id) return;
    state.job = job; renderJob();
    if (activeJob(job)) schedulePoll();
    else { await loadOverview({ followJobs: false }); if (job.operation === "research_run") await loadResearchStatus(); }
  } catch (error) {
    if (state.job?.operation === "research_run") researchError(error); else notify(`취소 요청을 확인할 수 없습니다: ${error.message}`);
    renderJob(); schedulePoll();
  }
});
function bindForm(id, operation, build, handler, capture) {
  $(id).addEventListener("submit", async (event) => {
    event.preventDefault(); if (!event.currentTarget.reportValidity()) return;
    try {
      const args = build(), context = capture?.();
      await runJob(typeof operation === "function" ? operation() : operation, args, (result) => handler?.(result, args, context));
    }
    catch (error) { notify(error.message); }
  });
}
async function switchStore(identifier) {
  if (viewBusy()) throw new Error("작업 실행 중에는 저장소를 바꿀 수 없습니다.");
  if (state.storeSwitching) throw new Error("저장소 전환을 확인하고 있습니다.");
  // Invalidate pending parent/artifact reads before the server changes stores.
  state.storeSwitching = true; state.experimentRequest++; state.fixtureViewer?.destroy(); state.fixtureViewer = null; updateControls();
  let overview;
  try { overview = await api("/api/store", { method: "POST", body: JSON.stringify({ id: identifier }) }); }
  catch (error) {
    state.overview = null; state.studyId = ""; state.study = null; state.registry = { entries: [] }; clearSimulationDraft();
    throw error;
  }
  finally { state.storeSwitching = false; updateControls(); }
  state.overview = overview; state.studyId = ""; state.study = null; state.registry = { entries: [] }; state.discovery = []; clearSimulationDraft();
  state.researchSession = null; $("researchContinue").checked = false; renderResearchAnswers();
  invalidateModelDiscovery(); state.campaignSelections.clear(); state.campaignSelectionKey = "";
  state.selectedExperiment = null; state.selectedCampaign = null; state.comparison.clear(); state.studyRequest++; state.experimentRequest++; state.campaignRequest++;
  $("observationPanel").hidden = true; state.observationRequest++;
  clear("campaignDetail"); clear("comparisonDetail").hidden = true;
  const card = panel("저장소가 바뀌었습니다.", "RESULTS"); card.append(el("p", "목록에서 열 기록을 선택하세요.", "empty-state")); clear("experimentDetail").append(card);
  $("selectedSource").textContent = "소스 버전: 기록 선택 후 확인"; renderDiscovery([]); renderOverview();
  if (state.studyId) await loadStudy(state.studyId); else { renderStudy(); renderRegistry(); }
}

// Exact Core keyword arguments are assembled here; no commands or file paths.
bindForm("studyForm", "study_create", () => ({ study_id: $("studyId").value.trim(), name: $("studyName").value.trim(), research_question: $("studyQuestion").value.trim(), hypothesis: $("studyHypothesis").value.trim(), objective: $("studyObjective").value.trim() }), async (_result, args) => {
  await loadStudy(args.study_id); $("studyId").value = makeId("S"); notify("연구 기록만 저장했습니다. AI 질문이나 해석을 실행한 것은 아닙니다.", true);
});
$("researchQuestionForm").addEventListener("submit", (event) => { event.preventDefault(); submitResearchQuestion().catch(researchError); });
$("researchQuestion").addEventListener("input", updateResearchControls); $("researchContinue").addEventListener("change", updateResearchControls);
$("researchResetBtn").addEventListener("click", () => { if (busy()) return; state.researchSession = null; $("researchContinue").checked = false; updateResearchControls(); $("researchQuestion").focus(); });
bindForm("registerForm", "parameter_register", () => ({ study_id: state.studyId, backend: $("cadBackend").value, model: $("cadModel").value.trim(), native_path: $("nativePath").value, parameter_id: $("parameterId").value.trim(), display_name: $("parameterName").value.trim(), lower: numeric("parameterLower"), upper: numeric("parameterUpper"), mode: $("parameterMode").value, kind: $("parameterKind").value }), async () => { await loadStudy(state.studyId); notify("형상 효과가 확인된 연구 변수를 등록했습니다.", true); });
bindForm("modelRegisterForm", "model_parameters_register", () => {
  if (!currentModelDiscovery() || !state.modelDiscovery.some((item) => item.native.path === $("modelInputId").value)) throw new Error("현재 모델 설정으로 입력 변수를 먼저 발견하세요.");
  const context = modelContext();
  return { study_id: state.studyId, backend: context.backend, settings: context.settings, input_id: $("modelInputId").value,
    parameter_id: $("modelParameterId").value.trim(), display_name: $("modelParameterName").value.trim(),
    lower: numeric("modelParameterLower"), upper: numeric("modelParameterUpper"), mode: $("modelParameterMode").value };
}, async (_result, args) => { await loadStudy(args.study_id); notify("선언된 입력의 변경을 검증하고 등록했습니다. 물리적 자격은 UNKNOWN입니다.", true); });
bindForm("cadForm", "cad_run", () => {
  const values = {};
  document.querySelectorAll("[data-cad-parameter]").forEach((input) => { const value = Number(input.value); if (!input.value || !Number.isFinite(value)) throw new Error("연구 변수의 유한한 값을 입력하세요."); values[input.dataset.cadParameter] = value; });
  return { study_id: state.studyId, experiment_id: $("cadExperimentId").value.trim(), backend: $("cadBackend").value, model: $("cadModel").value.trim(), values };
}, async (result, args) => { $("cadExperimentId").value = makeId("E-cad"); await inspectExperiment(result.experiment_id ?? args.experiment_id); });
bindForm("nativeCreateForm", "native_create", () => ({ template: $("nativeTemplate").value }), renderNative);
bindForm("nativeInspectForm", "native_inspect", () => ({ model: $("nativeModelId").value.trim() }), renderNative);
bindForm("nativeFinalForm", "native_final", () => ({ model: $("nativeModelId").value.trim(), final: $("nativeFinal").value }), renderNative);
bindForm("simulationForm", simulationOperation, simulationArguments, completeSimulation, simulationSubmissionContext);
bindForm("observationForm", "response_comparison_save", observationArguments, completeObservation, observationSubmissionContext);
$("observationResponse").addEventListener("change", observationResponseNote);
bindForm("campaignForm", campaignOperation, () => {
  const model = isModelCampaign();
  const args = { study_id: state.studyId, campaign_id: $("campaignId").value.trim(), parameter_ids: [...document.querySelectorAll("[data-campaign-variable]:checked")].map((input) => input.value), seed: numeric("campaignSeed") };
  if (!model) { args.backend = $("cadBackend").value; args.model = $("cadModel").value.trim(); }
  if (!args.parameter_ids.length) throw new Error("등록된 자유 변수를 하나 이상 선택하세요.");
  if (!model && $("campaignAnalysis").value) {
    if (!window.cadControls.supportsBackend(state.presets.structural_linear, args.backend)) throw new Error("현재 CAD 모델에 연결된 후속 구조 해석이 없습니다. CAD만 실행할 수 있습니다.");
    args.analysis_backend = state.presets.structural_linear.backend; args.analysis_settings = parseField("campaignAnalysisSettings", "object");
  }
  if ($("campaignType").value === "optimization") {
    args.objective = { source: $("objectiveSource").value, metric: $("objectiveMetric").value.trim(), unit: $("objectiveUnit").value.trim(), direction: $("objectiveDirection").value };
    args.constraints = parseField("optimizationConstraints", "array"); args.initial_values = parseField("optimizationInitial", "nullable-object"); args.required_validations = parseField("optimizationRequired", "object");
    args.max_generations = numeric("optimizationGenerations"); args.population_size = numeric("optimizationPopulation"); args.engine = "scipy.differential_evolution";
  } else { args.sample_count = numeric("campaignSamples"); args.engine = "scipy.latin_hypercube"; }
  if (model) {
    if (!currentModelDiscovery() || $("campaignType").value !== "optimization") throw new Error("선언한 모델 입력은 현재 설정의 변수 발견을 거친 최적화 계획으로 실행합니다.");
    const context = modelContext();
    return window.campaignControls.modelPlanArguments(args, { backend: context.backend, settings: context.settings, entries: modelCampaignEntries() });
  }
  return args;
}, async (_result, args) => { $("campaignId").value = makeId($("campaignType").value === "optimization" ? "C-opt" : "C-doe"); await inspectCampaign(args.campaign_id); notify("수치 후보의 계획을 저장했습니다. 계획을 검토한 뒤 실행하거나 이어가세요.", true); });

$("discoverBtn").addEventListener("click", () => runJob("parameter_discover", { backend: $("cadBackend").value, model: $("cadModel").value.trim() }, renderDiscovery).catch((error) => notify(error.message)));
$("registryRefreshBtn").addEventListener("click", () => runJob("registry_refresh", { study_id: state.studyId, backend: $("cadBackend").value, model: $("cadModel").value.trim() }, () => loadStudy(state.studyId)).catch((error) => notify(error.message)));
$("nativePath").addEventListener("change", () => chooseCandidate($("nativePath").value));
$("nativeFinal").addEventListener("change", updateControls); $("nativeModelId").addEventListener("input", updateControls);
$("cadBackend").addEventListener("change", () => { state.discovery = []; renderDiscovery([]); if ($("cadBackend").value === "fixture.cadquery") $("cadModel").value = "roller_support"; else if ($("cadBackend").value === "fixture.assembly") $("cadModel").value = "bending_assembly"; else { $("cadModel").value = $("nativeModelId").value; $("nativeArea").open = true; } renderRegistry(); });
$("cadModel").addEventListener("change", () => { renderDiscovery([]); renderRegistry(); });
$("studySelect").addEventListener("change", () => {
  state.studyId = $("studySelect").value; state.study = null; state.registry = { entries: [] };
  $("analysisParent").value = "";
  renderDiscovery([]); invalidateModelDiscovery(); renderRegistry(); loadStudy(state.studyId).catch((error) => notify(error.message));
});
document.querySelectorAll("[data-research-purpose]").forEach((button) => button.addEventListener("click", () => prepareResearchPurpose(button.dataset.researchPurpose)));
$("storeSelect").addEventListener("change", () => switchStore($("storeSelect").value).catch((error) => { $("storeSelect").value = activeStore(); notify(error.message); }));
$("useLocalBtn").addEventListener("click", () => switchStore("local").catch((error) => notify(error.message)));
$("refreshBtn").addEventListener("click", () => Promise.allSettled([loadOverview(), loadResearchStatus()]).then(results => results.forEach(result => { if (result.status === "rejected") notify(result.reason.message); })));
$("dismissNotice").addEventListener("click", () => { $("notice").hidden = true; });
$("simulationPreset").addEventListener("change", selectPreset); $("analysisParent").addEventListener("change", updateControls);
$("importedMeshFiles").addEventListener("change", () => selectImportedFiles());
document.querySelectorAll("[data-fixture-field]").forEach((input) => { input.addEventListener(input.tagName === "SELECT" ? "change" : "input", changeFixtureConditions); });
$("simulationSettings").addEventListener("input", () => { loadFixtureConditions(); updateControls(); });
$("fixtureUseInCampaign").addEventListener("click", () => {
  try {
    const settings = fixtureSimulationSettings();
    if (isModelCampaign()) { $("campaignTarget").value = "cad"; campaignTargetChanged(); }
    $("campaignAnalysisSettings").value = pretty(settings); $("campaignAnalysis").value = "structural_linear";
    $("campaignAnalysis").dispatchEvent(new Event("change"));
    notify("같은 재료·하중·메시를 새 탐색 계획의 후속 해석 설정에 넣었습니다. 계획을 검토한 뒤 저장하세요.", true);
  } catch (error) { notify(error.message); }
});
$("campaignType").addEventListener("change", campaignMode);
$("campaignTarget").addEventListener("change", campaignTargetChanged);
$("modelCampaignPreset").addEventListener("change", selectModelCampaignPreset);
$("modelCampaignSettings").addEventListener("input", invalidateModelDiscovery);
$("modelInputId").addEventListener("change", () => chooseModelCandidate($("modelInputId").value));
$("modelDiscoverBtn").addEventListener("click", async () => {
  try {
    const context = modelContext(), request = ++state.modelRequest;
    await runJob("model_parameters_discover", { backend: context.backend, settings: context.settings }, (candidates) => {
      if (request !== state.modelRequest || context.key !== modelContext().key) return;
      state.modelDiscovery = window.campaignControls.validateDiscovery(candidates, context.backend); state.modelContext = context.key;
      renderModelDiscovery(); renderCampaignVariables(); notify("현재 설정의 입력 변수를 발견했습니다. 범위를 확인해 연구 변수로 등록하세요.", true);
    });
  } catch (error) { notify(error.message); }
});
$("campaignAnalysis").addEventListener("change", () => {
  const analysis = Boolean($("campaignAnalysis").value); $("campaignAnalysisDetails").hidden = !analysis;
  const defaultConstraints = pretty([{ source: "analysis", metric: "max_displacement", unit: "mm", operator: "<=", limit: 0.0065, scale: 0.0065 }]);
  let sizes = state.presets.structural_linear?.settings?.mesh?.max_sizes_mm ?? [];
  try { sizes = parseField("campaignAnalysisSettings", "object").mesh?.max_sizes_mm ?? sizes; } catch { /* Submission reports malformed JSON. */ }
  const defaultRequirements = pretty({ cad: [], analysis: ["displacement_mesh_trend", ...sizes.map((_size, index) => `mesh_${index}_reaction_balance`)] });
  if (analysis && $("optimizationConstraints").value.trim() === "[]") $("optimizationConstraints").value = defaultConstraints;
  if (analysis && $("optimizationRequired").value.includes('"analysis": []')) $("optimizationRequired").value = defaultRequirements;
  if (!analysis && $("optimizationConstraints").value === defaultConstraints) $("optimizationConstraints").value = "[]";
  if (!analysis && $("optimizationRequired").value === defaultRequirements) $("optimizationRequired").value = '{"cad": [], "analysis": []}';
});
$("objectiveSource").addEventListener("change", () => {
  if (isModelCampaign()) return;
  $("objectiveMetric").value = $("objectiveSource").value === "analysis" ? "max_displacement" : "cad_volume";
  $("objectiveUnit").value = $("objectiveSource").value === "analysis" ? "mm" : "mm^3";
});
$("experimentSearch").addEventListener("input", renderExperimentList); $("experimentFilter").addEventListener("change", renderExperimentList);
$("compareBtn").addEventListener("click", () => compareExperiments().catch((error) => notify(error.message)));
$("jobDetailsBtn").addEventListener("click", () => { $("jobDetails").hidden = !$("jobDetails").hidden; $("jobDetails").open = true; });
window.addEventListener("hashchange", () => showArea(location.hash.slice(1)));
$("studyId").value = makeId("S"); $("cadExperimentId").value = makeId("E-cad"); $("campaignId").value = makeId("C-doe");
showArea(location.hash.slice(1)); updateControls();
Promise.allSettled([loadOverview(), api("/api/presets").then(renderPresets), loadResearchStatus()]).then((results) => {
  results.forEach((result) => { if (result.status === "rejected") notify(result.reason.message); }); updateControls();
});
