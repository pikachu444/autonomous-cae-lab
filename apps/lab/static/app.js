"use strict";

// Human controls over the allowlisted Core API. All record text is untrusted.
const $ = (id) => document.getElementById(id);
const state = {
  overview: null, presets: {}, studyId: "", study: null, registry: { entries: [] },
  discovery: [], job: null, submitting: false, pollTimer: null, handlers: new Map(), handlerGuards: new Map(),
  selectedExperiment: null, selectedHistories: null, selectedCampaign: null, comparison: new Set(), studyRequest: 0,
  experimentRequest: 0, campaignRequest: 0, viewer: null, fixtureViewer: null, fixtureConditionError: null, storeSwitching: false,
  modelDiscovery: [], modelContext: "", modelRequest: 0,
  importedLevels: [], importedMeshError: null, importedRequest: 0, importedLoading: false,
  campaignSelections: new Map(), campaignSelectionKey: "", campaignDrafts: {}, campaignTarget: "cad", cadCampaignType: "doe",
  fixtureCampaignDefaults: null,
  fixtureCampaignEdited: { constraints: false, requirements: false },
  researchStatus: null, researchStatusError: null, researchStatusRequest: 0, researchLoading: false,
  researchHistory: new Map(), researchContexts: new Map(), researchSession: null,
  simulationDraft: null,
  researchPurposeDraft: {},
  comparisonResearchDraft: "",
  comparisonResearchPrefix: "",
  campaignConditions: { selection: null, request: 0, loading: false, error: "" },
  fixedCad: { selection: null, discovery: null, request: 0, loading: false },
  campaignResearchSelection: { key: "", indexes: new Set() },
  campaignResearchDraft: "", campaignResearchPrefix: "",
  observationRequest: 0,
  observationId: "",
  selectedFieldObservation: null,
  nativeImportRequest: 0, nativeFileSelection: 0,
  analysisConditions: { request: 0, catalog: null, context: "", record: null, recordDraft: "", records: [], additionalBoundaries: [], loading: false, error: "" },
};
const operationNames = {
  study_create: "연구 만들기", parameter_discover: "CAD 변수 발견", parameter_register: "연구 변수 등록",
  registry_refresh: "원본 CAD 등록부 갱신", cad_run: "CAD 실험", native_create: "네이티브 모델 만들기",
  native_import: "내 CAD 가져오기", native_inspect: "네이티브 모델 확인", native_final: "최종 솔리드 선택", analysis_run: "CAD 구조 해석",
  pde_run: "선언한 weak form 실행", model_analysis_run: "선언한 모델·재료·동해석",
  doe_plan: "DOE 계획 저장", doe_run: "DOE 실행", optimization_plan: "최적화 계획 저장",
  optimization_run: "수치 최적화 실행",
  model_parameters_discover: "모델 입력 발견·환경 확인", model_parameters_register: "모델 연구 변수 등록",
  model_optimization_plan: "해석 모델 최적화 계획 저장",
  condition_parameters_discover: "고정 CAD의 조건 입력 발견", condition_parameters_register: "조건 연구 변수 등록",
  condition_optimization_plan: "고정 CAD 조건 탐색 계획 저장",
  research_run: "AI 연구 질문",
  response_comparison_save: "관측·시험 기준 비교 저장",
  analysis_conditions_save: "같은 CAD 개정의 해석 조건 저장",
};
const readOperations = new Set(["parameter_discover", "native_inspect", "model_parameters_discover", "condition_parameters_discover"]);
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
  if (purpose === "general") return {
    name: "CAE 조건·응답 연구",
    question: "연구 대상과 해결할 문제: [입력]\nCAD/해석 모델과 입력 데이터의 출처: [입력]\n비교할 조건과 관측 근거: [입력]\n질문: 어떤 입력이 목적 응답에 영향을 주며, 대안 또는 가설을 어떻게 구별할 수 있는가?",
    hypothesis: "가설/대안 A: [모델에서 바꿀 입력과 예상 응답]\n가설/대안 B: [경쟁 설명 또는 대안]\n구별할 위치·성분·시간/하중 조건: [입력]",
    objective: "목적 응답과 참조를 같은 위치·성분·좌표계·단위·조건에서 비교한다. 수치 탐색 범위와 목적별 허용값의 출처는 [입력]. 설명하지 못한 응답과 다음 비교를 남긴다.",
  };
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
function isFixedCadCampaign() { return $("campaignTarget").value === "analysis_conditions"; }
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
    headers["Content-Type"] = path === "/api/native-import" ? "application/octet-stream" : "application/json";
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
      const value = part.text;
      const item = el(part.type === "strong" ? "strong" : part.type === "em" ? "em" : part.type === "code" ? "code" : "span", value);
      if (part.type === "math") {
        item.className = part.display ? "research-math research-math-display" : "research-math";
        if (typeof window.katex?.render === "function" && value.length <= 8192) {
          try {
            // Self-hosted KaTeX emits MathML; URLs, HTML extensions and macro
            // state sharing are disabled. The raw answer stays unchanged.
            window.katex.render(value, item, { output: "mathml", displayMode: part.display,
              trust: false, strict: "error", throwOnError: true, maxExpand: 500, maxSize: 12, macros: {} });
          } catch { item.textContent = value; item.classList.add("research-math-fallback"); }
        }
      }
      if (part.parts) inline(item, part.parts); target.append(item);
    });
  }
  if (answer && /\\(?:\(|\[)/.test(answer)) body.append(el("p", "수식은 저장된 원문을 조판해 표시합니다. 정확한 답변과 수식 원문은 ‘AI 답변 원문’에서 확인할 수 있습니다.", "hint research-equation-note"));
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
  state.activeArea = selected;
  document.querySelectorAll("[data-panel]").forEach((item) => { item.hidden = item.dataset.panel !== selected; });
  document.querySelectorAll("[data-nav]").forEach((item) => {
    const active = item.dataset.nav === selected;
    item.classList.toggle("active", active);
    if (active) item.setAttribute("aria-current", "page"); else item.removeAttribute("aria-current");
  });
  document.title = `${{ research: "연구", design: "설계", simulation: "해석", explore: "탐색", results: "결과·근거" }[selected]} · Autonomous CAE Lab`;
  mountExperimentInspector(selected);
}
function updateControls() {
  for (const identifier of ["cadBackend", "cadModel", "nativeModelId"]) $(identifier).disabled = busy();
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
  if ($("nativeImportFile").files?.length !== 1) $("nativeImportBtn").disabled = true;
  document.querySelectorAll("[data-native-import]").forEach(item => { item.disabled = busy() || !available("native_inspect"); });
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
  updateAnalysisConditionsControls();
  updateCampaignConditionsControls();
  updateFixedCadControls();
  updateResearchControls();
  updateEngineeringWorkspace();
}

// One actual inspector follows the active engineering pane. Its source leases,
// artifact hashes and viewer remain the same; no duplicate model is constructed.
function engineeringWorkspaceEnabled() { return Boolean(window.analysisConditionsControls && $("designModelViewport")?.dataset.engineeringViewport === "design"); }
function mountExperimentInspector(area) {
  if (!engineeringWorkspaceEnabled()) return;
  const selected = ["design", "simulation"].includes(area) ? area : "results";
  const inspector = $("experimentDetail"), host = $(`${selected}ModelViewport`);
  if (inspector && host && inspector.parentNode !== host) host.append(inspector);
  for (const pane of ["design", "simulation"]) $(`${pane}ViewportEmpty`).hidden = inspector?.parentNode === $(`${pane}ModelViewport`);
  if (state.experimentProperties && state.experimentOverview) {
    const propertyHost = selected === "results" ? state.experimentOverview : $(`${selected}ResultPropertiesBody`);
    if (state.experimentProperties.parentNode !== propertyHost) propertyHost.append(state.experimentProperties);
    for (const pane of ["design", "simulation"]) $(`${pane}ResultProperties`).hidden = selected !== pane;
  }
}
function initializeEngineeringWorkspace() {
  if (!engineeringWorkspaceEnabled()) return;
  $("designOutlinePane").append($("designSourceCard"), $("designImportCard"), $("designNativeCard"));
  $("designPropertiesPane").append($("designRunCard"), $("designRegistryCard"), $("designDiscoveryCard"));
  $("designLegacyColumns").hidden = true;
  $("simulationPropertiesPane").append($("analysisConditionsArea"));
  $("analysisConditionsArea").classList.remove("separated");
  $("simulationExecutionToolbar").append($("analysisConditionsRunForm"));
  $("simulationSourceControls").append($("conditionsSourceControls"), $("analysisConditionsCatalog"));
  $("designCadRecord").addEventListener("change", updateControls);
  $("designOpenRecordBtn").addEventListener("click", () => openEngineeringRecord("design").catch(error => notify(error.message)));
  $("simulationOpenRecordBtn").addEventListener("click", () => openEngineeringRecord("simulation").catch(error => notify(error.message)));
  $("designConditionsBtn").addEventListener("click", () => {
    if (viewBusy()) return;
    const data = state.selectedExperiment, parent = window.analysisConditionsControls.parents(list(state.overview?.experiments), state.studyId)
      .find(item => item.id === data?.result?.experiment_id && item.cad_revision === data.result.cad_revision);
    if (parent && $("conditionsParent").value !== parent.id) { $("conditionsParent").value = parent.id; invalidateAnalysisConditions(); }
    location.hash = "simulation"; showArea("simulation"); updateControls();
  });
}
function updateEngineeringWorkspace() {
  if (!engineeringWorkspaceEnabled()) return;
  const parents = window.analysisConditionsControls.parents(list(state.overview?.experiments), state.studyId), select = $("designCadRecord");
  const old = select.value; clear(select); option(select, "", "보존한 CAD 개정 선택");
  parents.forEach(item => option(select, item.id, `${item.id} · ${item.cad_revision.slice(0, 10)}`));
  select.value = [...select.options].some(item => item.value === old) ? old : "";
  $("designOpenRecordBtn").disabled = viewBusy() || !parents.some(item => item.id === select.value);
  $("simulationOpenRecordBtn").disabled = viewBusy() || state.analysisConditions.loading || !analysisConditionsParent();
  $("designConditionsBtn").disabled = viewBusy() || !state.studyId;
  const data = state.selectedExperiment, result = data?.result;
  if (!result || !state.overview) resetEngineeringProperties();
  for (const pane of ["design", "simulation"]) {
    const outline = clear(`${pane}ModelOutline`);
    if (!result || data.integrity !== "VERIFIED") {
      outline.append(el("p", "보존한 CAD 또는 해석 기록을 열면 실제 모델과 개정이 표시됩니다.", "empty-state"));
      continue;
    }
    const facts = el("dl", undefined, "workspace-facts");
    [["표시 기록", result.experiment_id], ["연구", result.study?.id ?? result.study?.study_id],
      ["CAD 개정", result.cad_revision ? result.cad_revision.slice(0, 16) : "없음"],
      ["경로", result.provenance?.adapter], ["원 CAD", result.parent_experiment_id ?? result.experiment_id],
      ["저장 조건", result.provenance?.analysis_conditions?.id ?? "없음"]]
      .forEach(([label, value]) => facts.append(el("dt", label), el("dd", text(value))));
    outline.append(facts, badge(data.integrity), badge(result.solver_status ?? "NOT_RUN"), badge(result.decision ?? "NOT_RELEASED"));
    if (window.resultPresentation.safeExperimentId(result.experiment_id)) {
      const exports = el("div", undefined, "button-row");
      exports.append(link("보고서", `/api/report/${idPath(result.experiment_id)}.html`, "button secondary compact"),
        link("원본 묶음", `/api/report/${idPath(result.experiment_id)}.zip`, "button subtle compact", true));
      outline.append(exports);
    }
    if ((result.study?.id ?? result.study?.study_id) !== state.studyId) outline.append(el("p", "다른 연구의 보존 기록을 표시 중입니다.", "hint"));
    if (pane === "simulation" && $("conditionsParent").value && (result.parent_experiment_id ?? result.experiment_id) !== $("conditionsParent").value)
      outline.append(el("p", "표시 기록과 작성 중인 조건의 CAD 부모가 다릅니다.", "metric-reason"));
  }
  renderConditionSelectionDetails();
}
function resetEngineeringProperties() {
  if (!engineeringWorkspaceEnabled()) return;
  state.experimentProperties?.remove(); state.experimentProperties = null; state.experimentOverview = null;
  for (const pane of ["design", "simulation"]) $(`${pane}ResultProperties`).hidden = true;
}
async function openEngineeringRecord(area) {
  if (!engineeringWorkspaceEnabled() || viewBusy() || (area === "simulation" && state.analysisConditions.loading)) return;
  const parent = area === "simulation" ? analysisConditionsParent()
    : window.analysisConditionsControls.parents(list(state.overview?.experiments), state.studyId).find(item => item.id === $("designCadRecord").value);
  if (!parent) throw new Error("같은 연구의 보존한 CAD 개정을 선택하세요.");
  const source = JSON.stringify([activeStore(), state.studyId, nativeCadSelection(), area === "simulation" ? $("conditionsParent").value : $("designCadRecord").value]);
  const current = () => !state.storeSwitching && source === JSON.stringify([activeStore(), state.studyId, nativeCadSelection(), area === "simulation" ? $("conditionsParent").value : $("designCadRecord").value]);
  const catalog = area === "simulation" && currentAnalysisConditionsCatalog() ? state.analysisConditions.catalog : null;
  await inspectExperiment(parent.id, current, { studyId: parent.study_id, cadRevision: parent.cad_revision,
    backend: parent.backend, ...(catalog ? { resultSha256: catalog.source.result_sha256 } : {}) }, area);
}
function displacementCaption(components) {
  return ["UX", "UY", "UZ"].map(axis => `${axis} ${Object.hasOwn(components ?? {}, axis) ? number(components[axis]) : "미지정"}`).join(" / ");
}

function analysisConditionsEnabled() { return Boolean(window.analysisConditionsControls && $("analysisConditionsForm")); }
function analysisConditionFieldIds() {
  return { conditionsId: "conditionsId", backend: "conditionsBackend", materialSelection: "conditionsMaterialSelection",
    materialLaw: "conditionsMaterialLaw", youngModulus: "conditionsYoungModulus", poissonRatio: "conditionsPoissonRatio",
    materialCategory: "conditionsMaterialCategory", materialSource: "conditionsMaterialSource",
    coordinateSystem: "conditionsCoordinateSystem", lengthUnit: "conditionsLengthUnit", forceUnit: "conditionsForceUnit", stressUnit: "conditionsStressUnit",
    boundarySelection: "conditionsBoundarySelection", ux: "conditionsUx", uy: "conditionsUy", uz: "conditionsUz",
    uxEnabled: "conditionsUxEnabled", uyEnabled: "conditionsUyEnabled", uzEnabled: "conditionsUzEnabled", boundarySource: "conditionsBoundarySource",
    loadSelection: "conditionsLoadSelection", fx: "conditionsFx", fy: "conditionsFy", fz: "conditionsFz", loadSource: "conditionsLoadSource",
    contactMode: "conditionsContactMode", contactSource: "conditionsContactSource", meshSize: "conditionsMeshSize" };
}
function analysisConditionsFields() {
  const fields = Object.fromEntries(Object.entries(analysisConditionFieldIds()).map(([name, id]) =>
    [name, name.endsWith("Enabled") ? ($(id)?.type === "checkbox" ? $(id).checked : true) : $(id).value]));
  if (state.analysisConditions.additionalBoundaries?.length) fields.additionalBoundaries = state.analysisConditions.additionalBoundaries.map(row => ({ ...row }));
  if (assemblyConditionsActive() && $("conditionsAssemblyFields")?.querySelector("[data-assembly-conditions-form]")) {
    const rows = window.assemblyConditionsControls.readForm($("conditionsAssemblyFields"));
    return { ...rows, ...Object.fromEntries(["conditionsId", "backend", "coordinateSystem", "lengthUnit", "forceUnit", "stressUnit"].map(key => [key, fields[key]])) };
  }
  return fields;
}
function assemblyConditionsActive() {
  return Boolean(window.assemblyConditionsControls && state.analysisConditions.catalog &&
    window.assemblyConditionsControls.isAssembly(state.analysisConditions.catalog));
}
function analysisConditionsBuilder() {
  return assemblyConditionsActive() ? window.assemblyConditionsControls : window.analysisConditionsControls;
}
function rememberAssemblyConditionsDraft() {
  if (!assemblyConditionsActive() || !$("conditionsAssemblyFields")?.querySelector("[data-assembly-conditions-form]")) return;
  state.analysisConditions.assemblyDraft = window.assemblyConditionsControls.readForm($("conditionsAssemblyFields"));
}
function analysisConditionsContext() {
  return JSON.stringify([activeStore(), state.studyId, $("conditionsParent").value,
    $("cadBackend").value, $("cadModel").value, $("nativeModelId").value]);
}
function analysisConditionsParent() {
  return window.analysisConditionsControls.parents(list(state.overview?.experiments), state.studyId).find(item => item.id === $("conditionsParent").value);
}
function currentAnalysisConditionsCatalog() {
  if (!analysisConditionsEnabled()) return false;
  const conditions = state.analysisConditions, parent = analysisConditionsParent();
  return Boolean(!state.storeSwitching && conditions.catalog && conditions.context === analysisConditionsContext() && parent &&
    parent.cad_revision === conditions.catalog.source.cad_revision && parent.backend === conditions.catalog.source.backend);
}
function analysisConditionsCapture(draft = false, experiment = false) {
  return { key: analysisConditionsContext(), request: state.analysisConditions.request,
    ...(draft ? { draft: JSON.stringify(analysisConditionsFields()) } : {}),
    ...(experiment ? { experimentId: $("conditionsExperimentId").value } : {}) };
}
function analysisConditionsCurrent(context) {
  return Boolean(analysisConditionsEnabled() && !state.storeSwitching && context && context.key === analysisConditionsContext() &&
    context.request === state.analysisConditions.request && (!Object.hasOwn(context, "draft") || context.draft === JSON.stringify(analysisConditionsFields())) &&
    (!Object.hasOwn(context, "experimentId") || context.experimentId === $("conditionsExperimentId").value));
}
function analysisConditionsError(message = "") {
  if (!analysisConditionsEnabled()) return;
  state.analysisConditions.error = message;
  $("analysisConditionsError").textContent = message; $("analysisConditionsError").hidden = !message;
}
function invalidateAnalysisConditions() {
  if (!analysisConditionsEnabled()) return;
  const conditions = state.analysisConditions;
  rememberAssemblyConditionsDraft();
  conditions.request++; conditions.catalog = null; conditions.context = ""; conditions.record = null; conditions.recordDraft = "";
  conditions.records = []; conditions.loading = false; analysisConditionsError();
  if ($("conditionsAssemblyFields")) { clear("conditionsAssemblyFields"); $("conditionsAssemblyFields").hidden = true; }
  if ($("conditionsSingleSolidFields")) { $("conditionsSingleSolidFields").hidden = false; $("conditionsSingleSolidFields").disabled = false; }
  clear("analysisConditionsCatalog").append(el("p", "CAD·연구·저장소 선택이 바뀌었습니다. 같은 개정의 대상·지원 범위를 다시 확인하세요. 작성한 수치·출처는 유지했습니다.", "hint"));
  clear("analysisConditionsRecord").append(el("p", "현재 선택에 연결된 저장 조건을 다시 열거나 새 조건으로 저장하세요.", "empty-state"));
  clear("analysisConditionsList").append(el("p", "현재 CAD의 목록을 불러오기 전입니다.", "empty-state"));
  for (const id of ["conditionsBackend", "conditionsMaterialSelection", "conditionsBoundarySelection", "conditionsLoadSelection"]) {
    const select = clear(id); option(select, "", "같은 개정의 catalog를 확인하세요");
  }
  renderAdditionalBoundaries();
}
function renderAnalysisConditionsParents() {
  if (!analysisConditionsEnabled()) return;
  const oldParent = $("conditionsParent").value, select = clear("conditionsParent");
  option(select, "", "현재 연구의 CAD 실험을 선택하세요");
  window.analysisConditionsControls.parents(list(state.overview?.experiments), state.studyId)
    .forEach(item => option(select, item.id, `${item.id} · ${item.backend} · 개정 ${item.cad_revision.slice(0, 12)}`));
  select.value = [...select.options].some(item => item.value === oldParent) ? oldParent : "";
  if (state.analysisConditions.catalog && !currentAnalysisConditionsCatalog()) invalidateAnalysisConditions();
}
function updateAnalysisConditionsControls() {
  if (!analysisConditionsEnabled()) return;
  const conditions = state.analysisConditions;
  if ((conditions.loading && conditions.context !== analysisConditionsContext()) || (conditions.catalog && !currentAnalysisConditionsCatalog())) invalidateAnalysisConditions();
  const current = currentAnalysisConditionsCatalog(), blocked = !writable() || busy() || conditions.loading;
  $("conditionsParent").disabled = viewBusy() || conditions.loading || !state.overview;
  $("analysisConditionsLoadBtn").disabled = viewBusy() || conditions.loading || !analysisConditionsParent();
  $("analysisConditionsRefreshBtn").disabled = viewBusy() || conditions.loading || !current;
  $("analysisConditionsNewIdBtn").disabled = blocked;
  let saveReady = false, runReady = false;
  if (current) {
    try {
      const fields = analysisConditionsFields();
      analysisConditionsBuilder().buildSave(conditions.catalog, fields);
      saveReady = fields.conditionsId !== conditions.record?.id;
      if (conditions.record && conditions.recordDraft === JSON.stringify(fields)) {
        analysisConditionsBuilder().buildRun(conditions.record, conditions.catalog, fields, $("conditionsExperimentId").value.trim()); runReady = true;
      }
    } catch { /* Keep the explicit draft; submission displays its refusal. */ }
  }
  $("analysisConditionsSaveBtn").disabled = blocked || !saveReady || !available("analysis_conditions_save");
  $("analysisConditionsRunBtn").disabled = blocked || !runReady || !available("analysis_run");
  if ($("conditionsSingleSolidFields")) $("conditionsSingleSolidFields").disabled = blocked || assemblyConditionsActive();
  if (assemblyConditionsActive()) {
    const form = $("conditionsAssemblyFields").querySelector("[data-assembly-conditions-form]");
    if (form) form.disabled = blocked;
  }
  for (const axis of ["x", "y", "z"]) {
    const input = $(`conditionsU${axis}`), enabled = $(`conditionsU${axis}Enabled`);
    if (enabled?.type === "checkbox") { input.disabled = blocked || !enabled.checked; input.required = enabled.checked; }
  }
  updateAdditionalBoundaryControls();
  document.querySelectorAll("[data-analysis-conditions-open]").forEach(item => { item.disabled = viewBusy() || conditions.loading || !current; });
}
function renderAnalysisConditionsCatalog() {
  if (!currentAnalysisConditionsCatalog()) return;
  const data = state.analysisConditions.catalog, card = clear("analysisConditionsCatalog");
  card.append(el("h3", `대상 · ${data.source.experiment_id}`), el("p", `개정 ${data.source.cad_revision.slice(0, 16)} · global X/Y/Z · mm / N / MPa`, "hint"));
  const details = el("details", undefined, "advanced"); details.append(el("summary", "해석 경로·원본·지원 한계"));
  data.backends.forEach(item => details.append(el("p", `${item.label} · ${item.backend}: ${item.scope}`, "hint")));
  details.append(el("p", "네이티브 runtime NOT_CHECKED · 물리·강도 자격 UNKNOWN. 일반 면은 서버가 이 개정에 제공한 native_face만 사용합니다.", "hint"));
  const selections = data.catalog.selections.slice(0, 64);
  for (const item of selections) {
    const row = el("div", undefined, "selection-outline");
    row.append(el("strong", item.label), el("p", window.analysisConditionsControls.selectionLabel(item), "hint"));
    if (item.kind === "native_face") row.append(el("p", `${item.surface_type} · global · ${item.roles.includes("boundary") ? "구속" : ""}${item.roles.includes("load") ? " / 합력" : ""}`, "hint"));
    const actions = el("div", undefined, "button-row");
    for (const [role, target, label] of [["material", "conditionsMaterialSelection", "재료 대상"], ["boundary", "conditionsBoundarySelection", "구속 대상"], ["load", "conditionsLoadSelection", "하중 대상"]]) {
      if (!item.roles.includes(role)) continue;
      const context = state.analysisConditions.context;
      const button = action(label, () => {
        if (!currentAnalysisConditionsCatalog() || context !== state.analysisConditions.context || !writable() || busy() || state.analysisConditions.loading) return;
        $(target).value = item.id; changeAnalysisConditionsDraft(); $(target).focus?.();
      }, "button subtle compact");
      button.dataset.conditionsSelection = ""; actions.append(button);
    }
    row.append(actions); card.append(row);
  }
  if (data.catalog.selections.length > selections.length) card.append(el("p", "첫 64개 대상만 요약했습니다. 실제 선택 목록과 catalog 원본에서 나머지 대상을 확인하세요.", "hint"));
  data.catalog.limitations.forEach(item => details.append(el("p", item, "hint")));
  details.append(rawDetail("catalog와 원본 해시 확인", data)); card.append(details);
}
function renderConditionSelectionDetails() {
  if (!engineeringWorkspaceEnabled()) return;
  const data = currentAnalysisConditionsCatalog() ? state.analysisConditions.catalog : null;
  for (const [role, selectId] of [["Material", "conditionsMaterialSelection"], ["Boundary", "conditionsBoundarySelection"], ["Load", "conditionsLoadSelection"]]) {
    const target = clear(`conditions${role}Detail`), item = data?.catalog.selections.find(value => value.id === $(selectId).value);
    if (!item) { target.append(el("p", "같은 CAD 개정의 대상을 선택하세요.", "hint")); continue; }
    target.append(el("p", window.analysisConditionsControls.selectionLabel(item), "selection-geometry"));
    if (item.kind === "native_face") target.append(el("p", `${item.surface_type} · global X/Y/Z · ${item.unit}`, "hint"));
  }
  document.querySelectorAll("[data-conditions-selection]").forEach(item => { item.disabled = !writable() || busy() || state.analysisConditions.loading || !data; });
}
function additionalBoundariesEnabled() { return Boolean($("conditionsAdditionalBoundaries")?.dataset.boundaryRows === "native"); }
function renderAdditionalBoundaries() {
  if (!additionalBoundariesEnabled()) return;
  const container = clear("conditionsAdditionalBoundaries"), data = currentAnalysisConditionsCatalog() ? state.analysisConditions.catalog : null;
  for (const row of state.analysisConditions.additionalBoundaries) {
    const card = el("div", undefined, "boundary-row"), heading = el("div", undefined, "card-heading");
    const remove = action("구속 삭제", () => {
      if (!writable() || busy()) return;
      state.analysisConditions.additionalBoundaries = state.analysisConditions.additionalBoundaries.filter(item => item !== row);
      renderAdditionalBoundaries(); changeAnalysisConditionsDraft();
    }, "button subtle compact"); remove.dataset.boundaryRemove = "";
    heading.append(el("h3", `변위 구속 ${row.id}`), remove); card.append(heading);
    const label = el("label", "같은 개정의 구속 면"), select = el("select"); select.required = true; select.setAttribute("aria-label", `${row.id} 구속 대상`);
    option(select, "", "구속 대상을 선택하세요");
    const choices = data ? window.analysisConditionsControls.choices(data, "boundary") : [];
    choices.forEach(item => option(select, item.id, window.analysisConditionsControls.selectionLabel(item)));
    if (row.selectionId && !choices.some(item => item.id === row.selectionId)) option(select, row.selectionId, `현재 catalog에 없는 대상 · ${row.selectionId}`);
    select.value = row.selectionId;
    select.addEventListener("change", () => { row.selectionId = select.value; geometry(); changeAnalysisConditionsDraft(); });
    label.append(select); card.append(label);
    const detail = el("p", undefined, "selection-geometry"); card.append(detail);
    function geometry() {
      const selection = choices.find(item => item.id === row.selectionId);
      detail.textContent = selection ? window.analysisConditionsControls.selectionLabel(selection) : "이 개정의 catalog에서 대상을 다시 선택하세요.";
    }
    geometry(); const components = el("div", undefined, "component-grid");
    for (const axis of ["x", "y", "z"]) {
      const group = el("div"), enabledLabel = el("label", undefined, "check-line"), enabled = el("input"), value = el("input");
      enabled.type = "checkbox"; enabled.checked = row[`u${axis}Enabled`] !== false;
      enabled.setAttribute("aria-label", `${row.id} U${axis.toUpperCase()} 지정`);
      value.type = "number"; value.step = "any"; value.value = row[`u${axis}`]; value.required = enabled.checked;
      value.setAttribute("aria-label", `${row.id} U${axis.toUpperCase()} mm`); value.dataset.boundaryComponent = "";
      value.dataset.boundaryEnabled = `u${axis}Enabled`; value.dataset.boundaryId = row.id;
      enabled.addEventListener("change", () => { row[`u${axis}Enabled`] = enabled.checked; changeAnalysisConditionsDraft(); });
      value.addEventListener("input", () => { row[`u${axis}`] = value.value; changeAnalysisConditionsDraft(); });
      enabledLabel.append(enabled, el("span", `U${axis.toUpperCase()} 지정`)); group.append(enabledLabel, value); components.append(group);
    }
    card.append(components);
    const sourceLabel = el("label", "구속의 출처·가정"), source = el("textarea"); source.rows = 2; source.required = true; source.maxLength = 2000; source.value = row.source;
    source.setAttribute("aria-label", `${row.id} 구속 출처`); source.addEventListener("input", () => { row.source = source.value; changeAnalysisConditionsDraft(); });
    sourceLabel.append(source); card.append(sourceLabel); container.append(card);
  }
  updateAdditionalBoundaryControls();
}
function updateAdditionalBoundaryControls() {
  if (!additionalBoundariesEnabled()) return;
  const blocked = !writable() || busy() || state.analysisConditions.loading;
  const native = currentAnalysisConditionsCatalog() && $("conditionsBackend").value === "structure.calculix.native" &&
    state.analysisConditions.catalog.backends.some(item => item.backend === "structure.calculix.native");
  $("conditionsAdditionalBoundaryArea").hidden = !native && !state.analysisConditions.additionalBoundaries.length;
  $("conditionsAddBoundaryBtn").disabled = blocked || !native || state.analysisConditions.additionalBoundaries.length >= 127;
  document.querySelectorAll("[data-boundary-remove]").forEach(item => { item.disabled = blocked; });
  document.querySelectorAll("[data-boundary-component]").forEach(input => {
    const row = state.analysisConditions.additionalBoundaries.find(item => item.id === input.dataset.boundaryId);
    const enabled = row?.[input.dataset.boundaryEnabled] !== false; input.disabled = blocked || !enabled; input.required = enabled;
  });
}
function addAnalysisBoundary() {
  if (!additionalBoundariesEnabled() || !currentAnalysisConditionsCatalog() || $("conditionsBackend").value !== "structure.calculix.native" || !writable() || busy() || state.analysisConditions.loading || state.analysisConditions.additionalBoundaries.length >= 127) return;
  let index = 2; while (state.analysisConditions.additionalBoundaries.some(row => row.id === `BC${index}`)) index++;
  state.analysisConditions.additionalBoundaries.push({ id: `BC${index}`, selectionId: "", ux: "0", uy: "0", uz: "0",
    uxEnabled: false, uyEnabled: false, uzEnabled: false, source: "ASSUMED: 선택한 면의 지정 성분 변위로 구속하는 이상화. 실제 체결은 미확인." });
  renderAdditionalBoundaries(); changeAnalysisConditionsDraft();
}
function fillAnalysisConditionsChoices() {
  const data = state.analysisConditions.catalog;
  for (const [id, role] of [["conditionsMaterialSelection", "material"], ["conditionsBoundarySelection", "boundary"], ["conditionsLoadSelection", "load"]]) {
    const old = $(id).value, select = clear(id); option(select, "", "같은 개정의 대상을 명시적으로 선택하세요");
    window.analysisConditionsControls.choices(data, role).forEach(item => option(select, item.id, window.analysisConditionsControls.selectionLabel(item)));
    select.value = [...select.options].some(item => item.value === old) ? old : "";
  }
  const old = $("conditionsBackend").value, select = clear("conditionsBackend"); option(select, "", "서버가 제공한 해석 경로를 선택하세요");
  data.backends.forEach(item => option(select, item.backend, item.backend === "structure.calculix.native" ? "CalculiX · 사용자 CAD의 선형 구조해석" : item.backend === "fixture.assembly_mechanics.code_aster" ? "Code_Aster · 보존 조립체의 재료·구속·하중·접촉" : `${item.label} · ${item.backend}`));
  select.value = [...select.options].some(item => item.value === old) ? old : "";
  const assembly = assemblyConditionsActive();
  if ($("conditionsSingleSolidFields")) { $("conditionsSingleSolidFields").hidden = assembly; $("conditionsSingleSolidFields").disabled = assembly; }
  if ($("conditionsAssemblyFields")) {
    $("conditionsAssemblyFields").hidden = !assembly;
    if (assembly) window.assemblyConditionsControls.renderForm($("conditionsAssemblyFields"), data, {
      materialRows: [], boundaryRows: [], loadRows: [], contactRows: [], contactSource: "",
      ...state.analysisConditions.assemblyDraft,
      conditionsId: $("conditionsId").value, backend: $("conditionsBackend").value, analysisType: "nonlinear_static",
      coordinateSystem: $("conditionsCoordinateSystem").value, lengthUnit: $("conditionsLengthUnit").value,
      forceUnit: $("conditionsForceUnit").value, stressUnit: $("conditionsStressUnit").value });
  }
  renderAdditionalBoundaries();
}
function renderAnalysisConditionsRecord() {
  if (!analysisConditionsEnabled()) return;
  const conditions = state.analysisConditions, record = conditions.record, card = clear("analysisConditionsRecord");
  if (!record) { card.append(el("p", "현재 CAD에 연결된 조건을 저장하거나 보존 기록을 다시 여세요.", "empty-state")); return; }
  const supported = record.support.status === "SUPPORTED_DECLARED_INPUTS";
  card.append(el("h3", `저장 조건 ${record.id}`), badge("VERIFIED"), badge("UNKNOWN", "공학 자격 UNKNOWN"), badge("NOT_RELEASED"));
  card.append(el("p", `원 CAD ${record.source.experiment_id} · 연구 ${record.source.study_id} · ${record.request.backend}`),
    el("p", `개정 ${record.source.cad_revision.slice(0, 16)} · ${supported ? "선언 입력 지원" : "현재 실행 불가"} · ${record.support.status}`, "hint"));
  record.support.reasons.forEach(reason => card.append(el("p", reason, "hint")));
  card.append(el("p", "네이티브 runtime NOT_CHECKED · 실제 실행은 새 해석 기록에서 확인", "hint"));
  if (conditions.recordDraft !== JSON.stringify(analysisConditionsFields())) card.append(el("p", "저장 후 작성 입력이 변경됐습니다. 새 조건 ID로 저장하거나 이 보존 조건을 다시 연 뒤 실행하세요.", "metric-reason"));
  const declaration = record.request.declaration;
  card.append(table(["보존 조건", "입력·출처"], conditionReadoutRows(record)));
  card.append(rawDetail("보존한 재료·구속·부호 하중·좌표계·단위·접촉·메시", declaration), rawDetail("같은 CAD 원본 해시·요청·서버 판정", record),
    link("조건 원본 JSON 저장", `/api/analysis-conditions/${idPath(record.id)}`, "text-link", true));
}
function conditionReadoutRows(record) {
  const declaration = record.request.declaration;
  const selectionName = id => {
    const target = list(record.catalog?.selections).find(item => item.id === id);
    return target?.native_name ? `${target.native_object} / ${target.native_name}` : target?.label ?? id;
  };
  const rows = [["선언 해석", declaration.analysis_type], ["좌표계·단위", `${declaration.coordinate_system} · ${declaration.units?.length} / ${declaration.units?.force} / ${declaration.units?.stress}`]];
  list(declaration.materials).slice(0, 64).forEach(item => rows.push([`재료 · ${selectionName(item.selection_id)}`, `등방성 선형 탄성 · E ${number(item.young_modulus_MPa)} MPa · ν ${number(item.poisson_ratio)} · ${item.source?.category}: ${item.source?.description}`]));
  list(declaration.boundary_conditions).slice(0, 64).forEach(item => rows.push([`변위 구속 · ${selectionName(item.selection_id)}`, `${displacementCaption(item.components)} ${item.unit} · ${item.coordinate_system} · ${item.source}`]));
  list(declaration.loads).slice(0, 64).forEach(item => rows.push([`합력 · ${selectionName(item.selection_id)}`, `FX ${number(item.components?.FX)} / FY ${number(item.components?.FY)} / FZ ${number(item.components?.FZ)} ${item.unit} · ${item.coordinate_system} · ${item.source}`]));
  rows.push(["접촉 모델", `${declaration.contact?.mode} · ${declaration.contact?.source}`],
    ["메시", declaration.mesh?.mode === "retained" ? `보존 메시 ${declaration.mesh.mesh_revision} · 재메시 없음` : `${number(declaration.mesh?.max_size_mm)} mm · ${declaration.mesh?.mode}`]);
  list(declaration.contact?.pairs).forEach((pair, i) => rows.push([`연결 ${i + 1}`, `${selectionName(pair.selection_a)} ↔ ${selectionName(pair.selection_b)} · ${pair.law ?? declaration.contact.mode} · master ${pair.master ?? "미지정"} · ${pair.source ?? declaration.contact.source}${pair.distance_max_mm === undefined ? "" : ` · 거리 ${number(pair.distance_max_mm)} mm`}`]));
  return rows;
}
function renderAnalysisConditionsList() {
  if (!analysisConditionsEnabled()) return;
  const card = clear("analysisConditionsList"), records = state.analysisConditions.records;
  if (!records.length) { card.append(el("p", "이 CAD 실험에 저장된 조건이 없습니다. 새 조건은 원 결과와 별도로 보존됩니다.", "empty-state")); return; }
  records.slice(0, 100).forEach(value => {
    try {
      const record = window.analysisConditionsControls.saved(value, state.analysisConditions.catalog);
      const button = action(`조건 ${record.id} 다시 열기`, () => openAnalysisConditionsRecord(record.id)); button.dataset.analysisConditionsOpen = "";
      card.append(el("p", `${record.id} · ${record.request.backend} · ${record.support.status}`, "hint"), button);
    } catch (error) {
      card.append(el("p", `${value?.id ?? value?.record?.id ?? "식별자 미확인"} · 보존 기록 UNKNOWN · ${value?.error ?? error.message}`, "metric-reason"));
    }
  });
  if (records.length > 100) card.append(el("p", "첫 100개 조건을 표시합니다. 모든 원 기록은 저장소에 보존되어 있습니다.", "hint"));
}
async function readAnalysisConditionsList(context) {
  const data = await api(`/api/analysis-conditions?${new URLSearchParams({ experiment_id: $("conditionsParent").value })}`);
  if (!analysisConditionsCurrent(context)) return;
  if (!Array.isArray(data.records) || data.records.length > 4096) throw new Error("보존 조건 목록의 응답 범위를 확인할 수 없습니다.");
  state.analysisConditions.records = data.records; renderAnalysisConditionsList();
}
async function loadAnalysisConditionsCatalog() {
  if (!analysisConditionsEnabled() || viewBusy() || state.analysisConditions.loading) return;
  const parent = analysisConditionsParent();
  if (!parent) { analysisConditionsError("현재 연구의 완료한 CAD 실험을 선택하세요."); return; }
  const conditions = state.analysisConditions;
  rememberAssemblyConditionsDraft();
  conditions.request++; conditions.loading = true; conditions.context = analysisConditionsContext(); conditions.catalog = null; conditions.record = null; conditions.recordDraft = ""; conditions.records = [];
  analysisConditionsError(); let context = analysisConditionsCapture(true); updateControls();
  clear("analysisConditionsCatalog").append(el("p", "선택한 CAD 개정·원본 해시와 대상 catalog를 확인하고 있습니다…", "hint"));
  renderAnalysisConditionsRecord(); clear("analysisConditionsList").append(el("p", "같은 CAD의 보존 조건을 확인하고 있습니다…", "hint"));
  try {
    const data = await api(`/api/analysis-conditions/catalog?${new URLSearchParams({ experiment_id: parent.id })}`);
    if (!analysisConditionsCurrent(context)) return;
    conditions.catalog = window.analysisConditionsControls.catalog(data, { experimentId: parent.id, studyId: state.studyId, cadRevision: parent.cad_revision, backend: parent.backend });
    conditions.context = analysisConditionsContext(); fillAnalysisConditionsChoices(); renderAnalysisConditionsCatalog();
    // Populating advertised options changes the draft intentionally; later list
    // replies remain tied to these exact populated inputs and the same CAD.
    context = analysisConditionsCapture(true); await readAnalysisConditionsList(context);
    if (engineeringWorkspaceEnabled() && analysisConditionsCurrent(context)) {
      await inspectExperiment(parent.id, () => analysisConditionsCurrent(context), { resultSha256: data.source.result_sha256,
        studyId: data.source.study_id, cadRevision: data.source.cad_revision, backend: data.source.backend }, "simulation");
    }
  } catch (error) {
    if (!analysisConditionsCurrent(context)) return;
    analysisConditionsError(error.message);
  } finally {
    if (context.request === conditions.request && context.key === analysisConditionsContext() && !state.storeSwitching) { conditions.loading = false; updateControls(); }
  }
}
async function refreshAnalysisConditionsList() {
  if (!analysisConditionsEnabled() || !currentAnalysisConditionsCatalog() || viewBusy() || state.analysisConditions.loading) return;
  const conditions = state.analysisConditions; conditions.request++; conditions.loading = true; analysisConditionsError();
  const context = analysisConditionsCapture(true); updateControls();
  try { await readAnalysisConditionsList(context); }
  catch (error) { if (analysisConditionsCurrent(context)) analysisConditionsError(error.message); }
  finally { if (analysisConditionsCurrent(context)) { conditions.loading = false; updateControls(); } }
}
async function openAnalysisConditionsRecord(identifier) {
  if (!analysisConditionsEnabled() || !currentAnalysisConditionsCatalog() || viewBusy() || state.analysisConditions.loading) return;
  const conditions = state.analysisConditions; conditions.request++; conditions.loading = true; analysisConditionsError();
  const context = analysisConditionsCapture(true); updateControls();
  try {
    const payload = await api(`/api/analysis-conditions/${idPath(identifier)}`);
    if (!analysisConditionsCurrent(context)) return;
    const record = window.analysisConditionsControls.saved(payload, conditions.catalog);
    if (record.id !== identifier) throw new Error("요청한 조건 ID와 원 기록이 다릅니다.");
    conditions.record = record; conditions.recordDraft = "";
    try {
      const fields = analysisConditionsBuilder().fromRecord(record, conditions.catalog);
      Object.entries(analysisConditionFieldIds()).forEach(([name, id]) => {
        if (assemblyConditionsActive() && !["conditionsId", "backend", "coordinateSystem", "lengthUnit", "forceUnit", "stressUnit"].includes(name)) return;
        if (name.endsWith("Enabled")) $(id).checked = fields[name] !== false;
        else $(id).value = fields[name];
      });
      conditions.additionalBoundaries = (fields.additionalBoundaries ?? []).map(row => ({ ...row })); renderAdditionalBoundaries();
      if (assemblyConditionsActive()) window.assemblyConditionsControls.renderForm($("conditionsAssemblyFields"), conditions.catalog, fields);
      conditions.recordDraft = JSON.stringify(analysisConditionsFields());
    } catch (error) { analysisConditionsError(error.message); }
    renderAnalysisConditionsRecord();
  } catch (error) { if (analysisConditionsCurrent(context)) analysisConditionsError(error.message); }
  finally {
    if (context.request === conditions.request && context.key === analysisConditionsContext() && !state.storeSwitching) { conditions.loading = false; updateControls(); }
  }
}
function changeAnalysisConditionsDraft() {
  if (!analysisConditionsEnabled()) return;
  state.analysisConditions.request++; state.analysisConditions.loading = false; analysisConditionsError();
  renderAnalysisConditionsRecord(); updateControls();
}
async function saveAnalysisConditions() {
  if (!analysisConditionsEnabled()) return;
  const conditions = state.analysisConditions, context = analysisConditionsCapture(true);
  try {
    if (!currentAnalysisConditionsCatalog() || conditions.loading) throw new Error("현재 CAD 개정의 catalog를 먼저 확인하세요.");
    const args = analysisConditionsBuilder().buildSave(conditions.catalog, analysisConditionsFields());
    if (args.conditions_id === conditions.record?.id) throw new Error("보존 조건 ID는 다시 저장할 수 없습니다. 새 조건 ID를 준비하세요.");
    await runJob("analysis_conditions_save", args, result => {
      if (!analysisConditionsCurrent(context)) return;
      try {
        const record = window.analysisConditionsControls.saved({ record: result, integrity: "VERIFIED" }, conditions.catalog, args);
        conditions.record = record; conditions.recordDraft = context.draft; analysisConditionsError();
        conditions.records = [{ record, integrity: "VERIFIED" }, ...conditions.records.filter(value => value.record?.id !== record.id)];
        renderAnalysisConditionsRecord(); renderAnalysisConditionsList(); updateControls();
        notify("같은 CAD 개정의 조건을 새 기록으로 보존했습니다. 서버 지원 판정과 미확인 runtime·공학 자격을 확인하세요.", true);
      } catch (error) { if (analysisConditionsCurrent(context)) analysisConditionsError(error.message); }
    }, () => analysisConditionsCurrent(context));
  } catch (error) { if (analysisConditionsCurrent(context)) analysisConditionsError(error.message); }
}
async function runAnalysisConditions() {
  if (!analysisConditionsEnabled()) return;
  const conditions = state.analysisConditions, context = analysisConditionsCapture(true, true);
  try {
    if (!currentAnalysisConditionsCatalog() || conditions.loading || conditions.recordDraft !== context.draft) throw new Error("현재 CAD 개정과 작성 입력에 일치하는 조건을 새로 저장하거나 다시 여세요.");
    const args = analysisConditionsBuilder().buildRun(conditions.record, conditions.catalog, analysisConditionsFields(), $("conditionsExperimentId").value.trim());
    await runJob("analysis_run", args, async result => {
      if (!analysisConditionsCurrent(context)) return;
      if (result?.experiment_id !== args.experiment_id || result?.cad_revision !== conditions.record.source.cad_revision || result?.study?.id !== state.studyId || result?.provenance?.adapter !== args.backend) {
        analysisConditionsError("새 해석의 실험·연구·CAD 개정 연결을 확인할 수 없습니다. 원 결과를 확인하세요."); return;
      }
      await inspectExperiment(args.experiment_id, () => analysisConditionsCurrent(context), null, engineeringWorkspaceEnabled() ? "simulation" : "results");
      if (analysisConditionsCurrent(context)) $("conditionsExperimentId").value = makeId("E-conditions");
    }, () => analysisConditionsCurrent(context));
  } catch (error) { if (analysisConditionsCurrent(context)) analysisConditionsError(error.message); }
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
  renderAnalysisConditionsParents();
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
    await loadNativeImports();
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
    $("studySelect").value = identifier; renderStudy(); renderRegistry(); renderAnalysisParents(); renderAnalysisConditionsParents(); updateControls();
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
  const model = isModelCampaign(), fixed = isFixedCadCampaign();
  const key = fixed ? JSON.stringify(["fixed", state.fixedCad.selection?.sourceKey]) : model ? state.modelContext : JSON.stringify([activeStore(), state.studyId, $("cadBackend").value, $("cadModel").value.trim()]);
  const selected = state.campaignSelections.get(key);
  const free = fixed ? fixedCadEntries() : model ? modelCampaignEntries() : campaignCadEntries();
  const variables = clear("campaignVariables");
  state.campaignSelectionKey = key;
  variables.classList.toggle("empty-state", !free.length);
  if (!free.length) variables.append(el("p", fixed ? "보존한 CAD 조건을 연결하고 변경 가능한 재료·하중을 연구 변수로 등록하세요." : model ? "현재 설정으로 변수를 발견하고, 연속·자유·입력 변경 PASS인 연구 변수를 등록하세요." : "이 모델에 연속·자유·형상 효과 PASS로 등록된 변수가 필요합니다."));
  free.forEach((entry, index) => {
    const label = el("label", undefined, "variable-option"); const input = el("input"); input.type = "checkbox"; input.value = entry.parameter_id; input.dataset.campaignVariable = "";
    input.checked = selected ? selected.has(entry.parameter_id) : index === 0;
    input.addEventListener("change", updateControls);
    label.append(input, el("strong", `${entry.display_name} · ${entry.parameter_id}`), el("small", `${number(entry.lower_bound)}–${number(entry.upper_bound)} ${entry.unit}`)); variables.append(label);
  });
  if (fixed) {
    const selected = state.fixedCad.selection;
    $("campaignModel").textContent = selected ? `${state.studyId} · 원 CAD ${selected.record.source.experiment_id}\n같은 CAD 개정과 면을 유지하며 선언한 수치 입력만 변경합니다. 물리적 자격 UNKNOWN.` : "해석 화면에서 같은 native CAD의 저장 조건을 먼저 연결하세요.";
  } else if (model) {
    const preset = state.presets[$("modelCampaignPreset").value];
    $("campaignModel").textContent = `${state.studyId || "연구 미선택"} · ${preset?.backend ?? "모델 미선택"}\n${state.modelDiscovery[0]?.native.document ?? "설정 확인·변수 발견 필요"}\n모델 설정·등록부·실행 환경을 고정합니다. 물리적 자격 UNKNOWN, NOT_RELEASED.`;
  } else $("campaignModel").textContent = `${state.studyId || "연구 미선택"} · ${$("cadBackend").value} · ${$("cadModel").value.trim()}\n설계 화면의 작업 모델과 등록부를 고정해 사용합니다.`;
  updateControls();
}
function renderDiscovery(candidates, { queried = true } = {}) {
  state.discovery = list(candidates);
  $("discoveryCount").textContent = queried ? `${state.discovery.length}개 후보` : "발견 전";
  const select = clear("nativePath"); option(select, "", "발견한 후보를 선택하세요");
  state.discovery.forEach((candidate) => option(select, candidate.native?.path, `${candidate.label} · ${candidate.native?.path}`));
  const container = clear("discoveryList");
  if (!queried) container.append(el("p", "선택한 모델의 ‘변수 발견’으로 실제 후보를 조회하세요. 이전 모델의 후보는 사용하지 않습니다.", "empty-state"));
  else if (!state.discovery.length) container.append(el("p", "지원되는 실제 후보가 발견되지 않았습니다. 모델과 최종 솔리드를 확인하세요.", "empty-state"));
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
  if (identifier) {
    const changed = $("cadModel").value !== identifier || $("cadBackend").value !== "fixture.freecad";
    $("nativeModelId").value = identifier; $("cadModel").value = identifier; $("cadBackend").value = "fixture.freecad";
    if (changed) { state.discovery = []; renderDiscovery([], { queried: false }); }
    renderRegistry();
  }
  const finals = clear("nativeFinal"); option(finals, "", "최종 솔리드를 선택하세요");
  list(info.final_candidates).forEach((item) => option(finals, item.name, `${item.label ?? item.name} · ${item.name}`));
  finals.value = info.final ?? "";
  const detail = clear("nativeDetail"); detail.append(el("h3", info.document ?? "네이티브 CAD"), el("p", identifier, "mono"));
  detail.append(el("p", `최종 솔리드: ${info.final ?? "선택 필요"}`, "hint"), el("p", `실제 후보 ${list(info.candidates).length}개 · 네이티브 등록 ${list(info.parameters).length}개`, "hint"));
  detail.append(el("p", "새 CAD 실험을 만들면 편집 가능한 원본과 내보낸 형상을 같은 실험 개정에서 확인할 수 있습니다.", "hint separated"));
  if (info.native_import?.original_integrity === "VERIFIED") detail.append(el("p", "선택한 원본 FCStd를 별도로 보존하고 가져온 개정을 확인했습니다. 연구 변수를 발견해 새 CAD 개정을 만들 수 있습니다.", "hint"));
  detail.append(rawDetail("네이티브 모델의 실제 응답", info)); $("nativeArea").open = true; updateControls();
}

async function loadNativeImports() {
  const request = ++state.nativeImportRequest, store = activeStore();
  try {
    const data = await api("/api/native-imports");
    if (request !== state.nativeImportRequest || store !== activeStore() || state.storeSwitching) return;
    const container = clear("nativeImportList"), records = list(data.imports);
    if (!records.length) container.append(el("p", "이 저장소에 가져온 모델이 없습니다. 파일을 선택해 시작하세요.", "empty-state"));
    else container.append(table(["가져온 모델", "원본", "다음 작업"], records.map(record => {
      if (!record.model || record.error) {
        const partial = el("div");
        partial.append(el("p", "부분 기록이 남아 있습니다. 완료한 모델로 선택할 수 없습니다."), rawDetail("부분 기록·오류 상세", record));
        return ["가져오기 완료 확인 필요", "원본 확인 전", partial];
      }
      const button = action("모델 확인·변수 연결", () => openImportedModel(record.id));
      button.dataset.nativeImport = record.id;
      return [record.document || record.model, `${number(record.input?.size_bytes)}바이트 보존 · 선택 시 원본 재검사`, button];
    })));
    if (data.omitted) container.append(el("p", `최근 ${records.length}개를 표시합니다. 이전 ${data.omitted}개 기록도 저장소에 보존되어 있습니다.`, "hint"));
    updateControls();
  } catch (error) {
    if (request === state.nativeImportRequest && store === activeStore() && !state.storeSwitching)
      clear("nativeImportList").append(el("p", `가져온 모델 목록을 읽지 못했습니다: ${error.message}`, "hint"));
  }
}

function nativeCadSelection() {
  return JSON.stringify([$("cadBackend").value, $("cadModel").value, $("nativeModelId").value]);
}

async function openImportedModel(identifier) {
  if (busy() || !available("native_inspect")) throw new Error("진행 중인 작업과 모델 확인 기능을 먼저 확인하세요.");
  const store = activeStore(), request = ++state.nativeImportRequest, selection = nativeCadSelection();
  state.submitting = true; updateControls();
  let record;
  try {
    record = await api(`/api/native-imports/${idPath(identifier)}`);
    if (request !== state.nativeImportRequest || store !== activeStore() || state.storeSwitching || selection !== nativeCadSelection()) return;
    if (record.original_integrity !== "VERIFIED") throw new Error("가져온 원본의 무결성을 확인하지 못했습니다.");
    $("nativeModelId").value = record.model;
  } finally { state.submitting = false; updateControls(); }
  if (!record || request !== state.nativeImportRequest || store !== activeStore()) return;
  const inspectionSelection = nativeCadSelection();
  await runJob("native_inspect", { model: record.model }, info => {
    if (store === activeStore() && inspectionSelection === nativeCadSelection() && $("nativeModelId").value === record.model) renderNative(info);
  });
}

async function submitNativeImport() {
  if (!writable() || busy() || !available("native_import")) throw new Error("실행 가능한 작업 저장소에서 CAD 파일을 가져오세요.");
  const input = $("nativeImportFile"), selected = state.nativeFileSelection, store = activeStore(), selection = nativeCadSelection();
  if (input.files?.length !== 1) throw new Error("FCStd 파일 하나를 선택하세요.");
  const file = input.files[0]; state.submitting = true; updateControls();
  try {
    const upload = await window.nativeUploadControls.readFile(file);
    if (selected !== state.nativeFileSelection || input.files?.length !== 1 || input.files[0] !== file || store !== activeStore() || state.storeSwitching || selection !== nativeCadSelection())
      throw new Error("읽는 동안 파일 선택이나 저장소가 바뀌었습니다. 다시 선택하세요.");
    $("nativeImportFileState").textContent = `${upload.label} · ${number(upload.bytes)}바이트 · 원본을 보존하고 실제 모델을 검사합니다.`;
    const job = await api("/api/native-import", { method: "POST", body: upload.body });
    if (job.store_id !== store) throw new Error("가져오기 작업의 저장소를 확인해야 합니다. 원 작업은 작업 기록에서 확인하세요.");
    state.job = job;
    const handler = info => { if (store === activeStore() && selection === nativeCadSelection()) { renderNative(info); input.value = ""; state.nativeFileSelection++; $("nativeImportFileState").textContent = "원본을 보존하고 모델을 가져왔습니다. 연구를 선택한 뒤 변수를 발견하세요."; } };
    state.handlers.set(job.id, handler); renderJob();
    if (activeJob(job)) schedulePoll();
    else {
      await loadOverview({ followJobs: false });
      state.handlers.delete(job.id);
      if (job.status === "COMPLETED") handler(job.result);
      else if (job.status === "FAILED") notify(text(job.error));
    }
  } finally { state.submitting = false; updateControls(); }
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
  if ($("simulationCadWorkspace")) $("simulationCadWorkspace").hidden =
    preset?.operation === "pde_run" || preset?.operation === "model_analysis_run";
  if (preset) {
    description.append(badge(preset.status), el("p", preset.scope), el("p", `Backend: ${preset.backend}`, "mono"));
    $("simulationSettings").value = pretty(preset.settings);
  } else description.append(el("p", "서버가 제공하는 기존 검증 예제가 필요합니다."));
  const operation = simulationOperation(); $("parentField").hidden = operation !== "analysis_run";
  $("simulationRunBtn").dataset.operation = operation;
  $("simulationId").value = makeId(operation === "pde_run" ? "E-pde" : operation === "model_analysis_run" ? "E-model" : "E-solve");
  $("fixtureConditionFields").hidden = preset?.backend !== "fixture.calculix";
  if (window.pdeControls && $("pdeConditionFields")) {
    $("pdeConditionFields").hidden = preset?.backend !== "pde.fenicsx.rectangle" || preset?.settings?.mode !== "selected_mesh";
    loadPdeConditions();
  }
  if (window.plasticityControls && $("plasticityConditionFields")) {
    $("plasticityConditionFields").hidden = preset?.backend !== "structural.code_aster.plasticity" || preset?.settings?.mode !== "selected_mesh";
    loadPlasticityConditions();
  }
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
  if (window.pdeControls) loadPdeConditions();
  if (window.plasticityControls) loadPlasticityConditions();
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
  if (window.pdeControls && !$("pdeConditionFields").hidden && state.pdeConditionError) throw new Error(state.pdeConditionError);
  if (window.plasticityControls && !$("plasticityConditionFields").hidden && state.plasticityConditionError) throw new Error(state.plasticityConditionError);
  const settings = parseField("simulationSettings", "object");
  if (window.pdeControls && !$("pdeConditionFields").hidden) return window.pdeControls.validate(settings);
  if (window.plasticityControls && !$("plasticityConditionFields").hidden) return window.plasticityControls.validate(settings);
  if (!$("importedMeshFields").hidden) {
    if (state.importedMeshError || state.importedLoading) throw new Error(state.importedMeshError ?? "파일을 읽는 중입니다.");
    return window.importedMeshControls.settingsWithLevels(settings, state.importedLevels);
  }
  return $("fixtureConditionFields").hidden ? settings : window.fixtureControls.validate(settings);
}
function pdeConditionError(message) {
  state.pdeConditionError = message;
  $("pdeConditionError").textContent = message ?? "";
  $("pdeConditionError").hidden = !message;
}
function loadPdeConditions() {
  if (!$("pdeConditionFields") || $("pdeConditionFields").hidden) return;
  try {
    const fields = window.pdeControls.toFields(parseField("simulationSettings", "object"));
    document.querySelectorAll("[data-pde-field]").forEach(input => { input.value = fields[input.dataset.pdeField]; input.disabled = false; });
    pdeConditionError(null);
  } catch (error) {
    document.querySelectorAll("[data-pde-field]").forEach(input => { input.disabled = true; });
    pdeConditionError(`해석 설정 JSON을 확인하세요. ${error.message}`);
  }
}
function changePdeConditions() {
  const fields = {};
  document.querySelectorAll("[data-pde-field]").forEach(input => { fields[input.dataset.pdeField] = input.value; });
  try {
    $("simulationSettings").value = pretty(window.pdeControls.fromFields(fields, parseField("simulationSettings", "object")));
    pdeConditionError(null);
  } catch (error) { pdeConditionError(error.message); }
  updateControls();
}
function plasticityConditionError(message) {
  state.plasticityConditionError = message;
  $("plasticityConditionError").textContent = message ?? "";
  $("plasticityConditionError").hidden = !message;
}
function loadPlasticityConditions() {
  if (!$("plasticityConditionFields") || $("plasticityConditionFields").hidden) return;
  try {
    const fields = window.plasticityControls.toFields(parseField("simulationSettings", "object"));
    document.querySelectorAll("[data-plasticity-field]").forEach(input => { input.value = fields[input.dataset.plasticityField]; input.disabled = false; });
    plasticityConditionError(null);
  } catch (error) {
    document.querySelectorAll("[data-plasticity-field]").forEach(input => { input.disabled = true; });
    plasticityConditionError(`해석 설정 JSON을 확인하세요. ${error.message}`);
  }
}
function changePlasticityConditions() {
  const fields = {};
  document.querySelectorAll("[data-plasticity-field]").forEach(input => { fields[input.dataset.plasticityField] = input.value; });
  try {
    $("simulationSettings").value = pretty(window.plasticityControls.fromFields(fields, parseField("simulationSettings", "object")));
    plasticityConditionError(null);
  } catch (error) { plasticityConditionError(error.message); }
  updateControls();
}
function campaignConditionsEnabled() { return Boolean(window.campaignControls?.conditionSelection && $("campaignAnalysisSource")); }
function usesSavedCampaignConditions() { return campaignConditionsEnabled() && !isModelCampaign() && !isFixedCadCampaign() && $("campaignAnalysisSource").value === "saved"; }
function campaignCadEntries() {
  if (!usesSavedCampaignConditions()) return selectedEntries().filter(entry => entry.mode === "free" && entry.kind === "continuous" && entry.geometry_effect?.status === "PASS");
  if (!campaignConditionsCurrent()) return [];
  return list(state.registry?.entries).filter(entry => {
    try { window.campaignControls.conditionPlanArguments(state.campaignConditions.selection, campaignConditionContext(), [entry.parameter_id]); return true; }
    catch { return false; }
  });
}
function campaignConditionContext() {
  return { store: activeStore(), studyId: state.studyId, backend: $("cadBackend").value, model: $("cadModel").value.trim(), entries: list(state.registry?.entries) };
}
function campaignConditionSource() {
  if (!analysisConditionsEnabled() || !currentAnalysisConditionsCatalog() || state.analysisConditions.loading ||
      !state.analysisConditions.record || state.analysisConditions.recordDraft !== JSON.stringify(analysisConditionsFields()))
    throw new Error("해석 화면에서 현재 CAD의 보존 조건을 다시 여세요. 편집한 조건은 새 ID로 먼저 저장하세요.");
  const record = window.analysisConditionsControls.saved({ integrity: "VERIFIED", record: state.analysisConditions.record }, state.analysisConditions.catalog);
  if (record.support.status !== "SUPPORTED_DECLARED_INPUTS") throw new Error("이 모델·조건은 서버 지원 판정이 없어 탐색 해석에 연결할 수 없습니다.");
  return record;
}
function campaignConditionSignature() {
  return JSON.stringify([analysisConditionsEnabled() ? analysisConditionsCapture(true) : null,
    state.analysisConditions.record?.id, state.analysisConditions.record?.conditions_revision, campaignConditionContext()]);
}
function campaignConditionsCurrent() {
  const selection = state.campaignConditions.selection;
  if (!selection || state.storeSwitching || isModelCampaign()) return false;
  try {
    const source = campaignConditionSource();
    if (source.id !== selection.record.id || source.conditions_revision !== selection.record.conditions_revision ||
        selection.sourceKey !== campaignConditionSignature()) return false;
    window.campaignControls.conditionPlanArguments(selection, campaignConditionContext(), [selection.sourceEntries[0].parameter_id]);
    return true;
  } catch { return false; }
}
function campaignConditionsMessage(message = "") {
  state.campaignConditions.error = message;
  if (!campaignConditionsEnabled()) return;
  $("campaignConditionsError").textContent = message; $("campaignConditionsError").hidden = !message;
}
function withdrawCampaignConditions(message = "CAD·연구·저장소 또는 보존 조건이 바뀌었습니다. 같은 원 CAD를 확인해 다시 연결하세요.") {
  state.campaignConditions.request++; state.campaignConditions.loading = false; state.campaignConditions.selection = null;
  if (!campaignConditionsEnabled()) return;
  campaignConditionsMessage(message); renderCampaignConditionsSummary();
}
function renderCampaignConditionsSummary() {
  if (!campaignConditionsEnabled()) return;
  const target = clear("campaignConditionsSummary"), selection = state.campaignConditions.selection;
  if (!selection) { target.append(el("p", "같은 원 CAD의 지원되는 저장 조건을 연결하세요. 저장 조건 모드에서는 연결 전 계획을 저장할 수 없습니다.", "hint")); return; }
  const record = selection.record;
  target.append(el("strong", `저장 조건 ${record.id}`), el("p", `원 CAD ${record.source.experiment_id} · ${selection.backend} / ${selection.model}`),
    el("p", `CAD 개정 ${record.source.cad_revision}`, "mono"), badge("VERIFIED"), badge("UNKNOWN", "공학 자격 UNKNOWN"), badge("NOT_RELEASED"));
  window.comparisonResearch.declarationLines(record.request.declaration).forEach(line => target.append(el("p", line, "hint")));
  target.append(el("p", `${record.request.backend} · 서버 판정 ${record.support.status} · native runtime NOT_CHECKED`, "hint"),
    el("p", "같은 대상 선택을 새 CAD 개정에 다시 확인합니다. 재료·하중·구속의 선언은 USER_DECLARED_UNVERIFIED입니다.", "hint"));
}
function updateCampaignConditionsControls() {
  if (!campaignConditionsEnabled()) return;
  const conditions = state.campaignConditions, saved = usesSavedCampaignConditions();
  if (conditions.selection && !campaignConditionsCurrent()) withdrawCampaignConditions();
  $("campaignSavedConditions").hidden = !saved; $("campaignLegacyAnalysis").hidden = saved;
  if (saved) $("fixtureCampaignNote").hidden = true;
  let sourceReady = false;
  try { campaignConditionSource(); sourceReady = true; } catch { /* Explicit action explains the missing source. */ }
  const blocked = !writable() || busy() || conditions.loading || !state.studyId;
  $("campaignUseConditionsBtn").disabled = blocked || !sourceReady || isModelCampaign();
  if ($("analysisConditionsExploreBtn")) $("analysisConditionsExploreBtn").disabled = blocked || !sourceReady;
  if (saved && (blocked || !campaignConditionsCurrent())) $("campaignPlanBtn").disabled = true;
  document.querySelectorAll("[data-campaign-research]").forEach(item => {
    item.disabled = busy() || !writable() || activeStore() !== "local" || !campaignViewCurrent(state.selectedCampaign) || item.dataset.ready !== "true";
  });
  document.querySelectorAll("[data-campaign-candidate]").forEach(item => { item.disabled = viewBusy() || !campaignViewCurrent(state.selectedCampaign); });
  document.querySelectorAll("[data-campaign-run]").forEach(item => { item.disabled ||= !campaignViewCurrent(state.selectedCampaign); });
  document.querySelectorAll("[data-campaign-result]").forEach(item => { item.disabled = viewBusy() || !campaignViewCurrent(state.selectedCampaign); });
}
async function prepareCampaignConditions(navigate = false) {
  if (!campaignConditionsEnabled() || busy() || !writable() || state.campaignConditions.loading) return;
  const conditions = state.campaignConditions;
  let record, sourceKey;
  try { record = campaignConditionSource(); sourceKey = campaignConditionSignature(); }
  catch (error) { campaignConditionsMessage(error.message); if (navigate) notify(error.message); return; }
  if (isModelCampaign()) { $("campaignTarget").value = "cad"; campaignTargetChanged(); }
  const draft = campaignFormSignature(), request = ++conditions.request;
  const current = () => !state.storeSwitching && request === conditions.request && sourceKey === campaignConditionSignature() && !isModelCampaign() && draft === campaignFormSignature();
  conditions.loading = true; conditions.selection = null; campaignConditionsMessage(); updateControls();
  try {
    const inspection = await api(`/api/experiments/${idPath(record.source.experiment_id)}`);
    if (!current()) return;
    const selection = window.campaignControls.conditionSelection(record, inspection, campaignConditionContext());
    conditions.selection = { ...selection, sourceKey }; $("campaignAnalysisSource").value = "saved";
    renderCampaignConditionsSummary(); renderCampaignVariables();
    if (navigate) { location.hash = "explore"; showArea("explore"); }
    notify("원 CAD·등록 변수와 저장 조건을 탐색 계획에 연결했습니다. 계획을 저장한 뒤 실행하세요.", true);
  } catch (error) { if (current()) { campaignConditionsMessage(error.message); if (navigate) notify(error.message); } }
  finally { if (request === conditions.request) { conditions.loading = false; updateControls(); } }
}
function campaignFormSignature() {
  const ids = ["campaignTarget", "campaignType", "campaignId", "campaignSeed", "campaignSamples", "objectiveSource", "objectiveMetric", "objectiveUnit", "objectiveDirection", "objectiveTarget", "objectiveScale", "objectiveOrigin", "objectiveReference",
    "optimizationConstraints", "optimizationInitial", "optimizationRequired", "optimizationGenerations", "optimizationPopulation", "campaignAnalysisSource", "campaignAnalysis", "campaignAnalysisSettings", "modelCampaignPreset", "modelCampaignSettings"];
  return JSON.stringify([activeStore(), state.studyId, state.storeSwitching, $("cadBackend").value, $("cadModel").value, $("nativeModelId").value,
    ids.map(id => $(id)?.value ?? ""), [...document.querySelectorAll("[data-campaign-variable]:checked")].map(input => input.value),
    state.registry, usesSavedCampaignConditions() ? campaignConditionSignature() : null]);
}
function fixedCadElements() {
  return { input: $("fixedCadInputId"), parameterId: $("fixedCadParameterId"), displayName: $("fixedCadParameterName"),
    lower: $("fixedCadParameterLower"), upper: $("fixedCadParameterUpper"), summary: $("fixedCadInputSummary") };
}
function fixedCadSignature() {
  return JSON.stringify([activeStore(), state.studyId, $("cadBackend").value, $("cadModel").value.trim(),
    analysisConditionsEnabled() ? analysisConditionsCapture(true) : null, state.analysisConditions.record?.id,
    state.analysisConditions.record?.conditions_revision]);
}
function fixedCadCurrent() {
  const selected = state.fixedCad.selection;
  if (!selected || state.storeSwitching || selected.sourceKey !== fixedCadSignature()) return false;
  try {
    const record = campaignConditionSource();
    return window.fixedCadCampaignControls.sameContext(selected, { store: activeStore(), studyId: state.studyId,
      backend: $("cadBackend").value, model: $("cadModel").value.trim(), conditionsId: record.id,
      conditionsRevision: record.conditions_revision, cadRevision: record.source.cad_revision, catalogRevision: record.catalog_revision });
  } catch { return false; }
}
function fixedCadEntries() {
  if (!fixedCadCurrent() || !state.fixedCad.discovery) return [];
  try { return window.fixedCadCampaignControls.eligibleEntries(list(state.registry.entries), state.fixedCad.discovery, state.fixedCad.selection); }
  catch { return []; }
}
function fixedCadError(message = "") {
  $("fixedCadConditionsError").textContent = message; $("fixedCadConditionsError").hidden = !message;
}
function withdrawFixedCad(message = "CAD·저장 조건 또는 작성 내용이 바뀌었습니다. 같은 원본 조건을 다시 연결하세요.") {
  state.fixedCad.request++; state.fixedCad.loading = false; state.fixedCad.selection = null; state.fixedCad.discovery = null;
  fixedCadError(message); clear("fixedCadInputId"); option($("fixedCadInputId"), "", "고정 CAD 조건을 다시 연결하세요");
  $("fixedCadConditionsSummary").textContent = "현재 CAD·조건에 연결된 입력을 다시 확인하세요. 등록 입력 초안은 보존했습니다.";
}
function updateFixedCadControls() {
  if (!window.fixedCadCampaignControls || !$("fixedCadConditionsArea")) return;
  const fixed = state.fixedCad;
  if (fixed.selection && !fixedCadCurrent()) withdrawFixedCad();
  let sourceReady = false;
  try { sourceReady = campaignConditionSource().request.backend === "structure.calculix.native"; } catch { /* Action reports missing conditions. */ }
  const blocked = busy() || !writable() || fixed.loading || !state.studyId;
  $("fixedCadUseConditionsBtn").disabled = blocked || !sourceReady;
  $("fixedCadDiscoverBtn").disabled ||= blocked || !fixedCadCurrent();
  $("fixedCadInputId").disabled = blocked || !fixed.discovery || !fixedCadCurrent();
  $("fixedCadRegisterBtn").disabled ||= blocked || !fixed.discovery || !$("fixedCadInputId").value || !fixedCadCurrent();
  if (isFixedCadCampaign() && (blocked || !fixedCadCurrent() || !fixed.discovery || !fixedCadEntries().length)) $("campaignPlanBtn").disabled = true;
}
async function prepareFixedCad(navigate = false) {
  if (busy() || !writable() || state.fixedCad.loading) return;
  const fixed = state.fixedCad;
  const reportError = error => {
    fixedCadError(error.message);
    if (navigate) { analysisConditionsError(error.message); notify(error.message); }
  };
  let record;
  try { record = campaignConditionSource(); } catch (error) { reportError(error); return; }
  if (!isFixedCadCampaign()) { $("campaignTarget").value = "analysis_conditions"; campaignTargetChanged(); }
  const sourceKey = fixedCadSignature(), request = ++fixed.request;
  const current = () => !state.storeSwitching && request === fixed.request && sourceKey === fixedCadSignature() && isFixedCadCampaign();
  fixed.loading = true; fixed.selection = null; fixed.discovery = null; fixedCadError(); updateControls();
  try {
    const inspection = await api(`/api/experiments/${idPath(record.source.experiment_id)}`);
    if (!current()) return;
    const selected = window.fixedCadCampaignControls.selection(record, inspection, { store: activeStore(), studyId: state.studyId,
      backend: $("cadBackend").value, model: $("cadModel").value.trim() });
    fixed.selection = { ...selected, sourceKey };
    const summary = clear("fixedCadConditionsSummary");
    summary.append(el("strong", `원 CAD ${record.source.experiment_id} · 저장 조건 ${record.id}`), el("p", `CAD 개정 ${record.source.cad_revision.slice(0,16)}`, "mono"));
    summary.append(table(["보존 조건", "입력·출처"], conditionReadoutRows(record)), rawDetail("원 CAD·조건 식별자·전체 해시", record));
    summary.append(el("p", "같은 CAD와 native 면을 유지합니다. 재료·하중 성분만 변경하며, 변동 값은 가정 시나리오로 저장됩니다.", "hint"));
    renderCampaignVariables();
    if (navigate) { location.hash = "explore"; showArea("explore"); }
  } catch (error) { if (current()) reportError(error); }
  finally { if (request === fixed.request) { fixed.loading = false; updateControls(); } }
}
async function discoverFixedCadInputs() {
  if (!fixedCadCurrent() || busy() || !writable()) return;
  const fixed = state.fixedCad, selected = fixed.selection, request = ++fixed.request;
  const current = () => request === fixed.request && selected === fixed.selection && fixedCadCurrent();
  try {
    await runJob("condition_parameters_discover", { conditions_id: selected.record.id }, reply => {
      if (!current()) return;
      window.fixedCadCampaignControls.validateDiscovery(reply, selected); fixed.discovery = reply;
      window.fixedCadCampaignControls.populateInputs(reply, selected, fixedCadElements());
      renderCampaignVariables(); fixedCadError();
    }, current);
  } catch (error) { if (current()) fixedCadError(error.message); }
}
async function registerFixedCadInput(event) {
  event.preventDefault();
  if (!fixedCadCurrent() || !state.fixedCad.discovery || busy() || !writable()) return;
  const fixed = state.fixedCad, selected = fixed.selection, discovered = fixed.discovery;
  const current = () => selected === fixed.selection && discovered === fixed.discovery && fixedCadCurrent();
  try {
    const fields = window.fixedCadCampaignControls.readRegistration(fixedCadElements());
    const args = window.fixedCadCampaignControls.registerArguments(fields, discovered, selected);
    await runJob("condition_parameters_register", args, () => { if (current()) { renderCampaignVariables(); fixedCadError(); } }, current);
  } catch (error) { if (current()) fixedCadError(error.message); }
}
function campaignArguments() {
  const model = isModelCampaign(), fixed = isFixedCadCampaign();
  const args = { study_id: state.studyId, campaign_id: $("campaignId").value.trim(), parameter_ids: [...document.querySelectorAll("[data-campaign-variable]:checked")].map(input => input.value), seed: numeric("campaignSeed") };
  if (!model && !fixed) { args.backend = $("cadBackend").value; args.model = $("cadModel").value.trim(); }
  if (!args.parameter_ids.length) throw new Error("등록된 자유 변수를 하나 이상 선택하세요.");
  if (usesSavedCampaignConditions()) {
    if (!campaignConditionsCurrent()) throw new Error("원 CAD·현재 등록 변수와 검증한 저장 조건을 다시 연결하세요. 직접 설정으로 대체하지 않습니다.");
    Object.assign(args, window.campaignControls.conditionPlanArguments(state.campaignConditions.selection, campaignConditionContext(), args.parameter_ids));
  } else if (!model && !fixed && $("campaignAnalysis").value) {
    if (!window.cadControls.supportsBackend(state.presets.structural_linear, args.backend)) throw new Error("현재 CAD 모델에 연결된 후속 구조 해석이 없습니다. CAD만 실행할 수 있습니다.");
    args.analysis_backend = state.presets.structural_linear.backend; args.analysis_settings = parseField("campaignAnalysisSettings", "object");
  }
  if ($("campaignType").value === "optimization") {
    args.objective = window.campaignControls.objectiveFromFields({ source: $("objectiveSource").value,
      metric: $("objectiveMetric").value, unit: $("objectiveUnit").value, direction: $("objectiveDirection").value,
      target: $("objectiveTarget").value, scale: $("objectiveScale").value, origin: $("objectiveOrigin").value,
      reference: $("objectiveReference").value });
    args.constraints = parseField("optimizationConstraints", "array"); args.initial_values = parseField("optimizationInitial", "nullable-object"); args.required_validations = parseField("optimizationRequired", "object");
    args.max_generations = numeric("optimizationGenerations"); args.population_size = numeric("optimizationPopulation"); args.engine = "scipy.differential_evolution";
  } else { args.sample_count = numeric("campaignSamples"); args.engine = "scipy.latin_hypercube"; }
  if (fixed) {
    if (!fixedCadCurrent() || !state.fixedCad.discovery) throw new Error("같은 CAD의 보존 조건과 입력 변수를 다시 확인하세요.");
    args.conditions_id = state.fixedCad.selection.record.id;
    return window.fixedCadCampaignControls.planArguments(args, { selection: state.fixedCad.selection, discovery: state.fixedCad.discovery, entries: list(state.registry.entries) });
  } else if (model) {
    if (!currentModelDiscovery() || $("campaignType").value !== "optimization") throw new Error("선언한 모델 입력은 현재 설정의 변수 발견을 거친 최적화 계획으로 실행합니다.");
    const context = modelContext();
    return window.campaignControls.modelPlanArguments(args, { backend: context.backend, settings: context.settings, entries: modelCampaignEntries() });
  }
  return args;
}
async function submitCampaignPlan() {
  if (!writable() || busy() || state.campaignConditions.loading) return;
  const signature = campaignFormSignature(), current = () => !state.storeSwitching && campaignFormSignature() === signature;
  try {
    const args = campaignArguments(), operation = campaignOperation();
    await runJob(operation, args, async () => {
      if (!current()) return;
      await inspectCampaign(args.campaign_id, current);
      if (!current()) return;
      $("campaignId").value = makeId($("campaignType").value === "optimization" ? "C-opt" : "C-doe");
      notify("고정한 탐색 계획을 저장했습니다. 원 조건과 후보 범위를 확인한 뒤 실행하거나 연구 질문에 연결하세요.", true);
    }, current);
  } catch (error) { if (current()) notify(error.message); }
}
function campaignOperation() { return isFixedCadCampaign() ? "condition_optimization_plan" : isModelCampaign() ? "model_optimization_plan" : $("campaignType").value === "optimization" ? "optimization_plan" : "doe_plan"; }
function applyFixtureCampaignDefaults() {
  const note = $("fixtureCampaignNote"), previous = state.fixtureCampaignDefaults;
  if (isModelCampaign() || isFixedCadCampaign()) { note.hidden = true; return; }
  if (usesSavedCampaignConditions()) { note.hidden = true; return; }
  const enabled = Boolean($("campaignAnalysis").value);
  $("campaignAnalysisDetails").hidden = !enabled;
  note.hidden = !enabled;
  if (!enabled) {
    if (!state.fixtureCampaignEdited.constraints && previous && $("optimizationConstraints").value === previous.constraints) $("optimizationConstraints").value = "[]";
    if (!state.fixtureCampaignEdited.requirements && previous && $("optimizationRequired").value === previous.requirements) $("optimizationRequired").value = pretty({ cad: previous.cad, analysis: [] });
    state.fixtureCampaignDefaults = null;
    return;
  }
  // Use the current declared settings, never a preset fallback or a hidden physical limit.
  const defaults = window.campaignControls.fixtureOptimizationDefaults(parseField("campaignAnalysisSettings", "object"));
  let requirements;
  try { requirements = parseField("optimizationRequired", "object"); } catch { /* Preserve the editable user input. */ }
  const managedRequirements = previous && $("optimizationRequired").value === previous.requirements;
  const emptyAnalysis = requirements && Object.keys(requirements).length === 2 && Array.isArray(requirements.cad) &&
    Array.isArray(requirements.analysis) && requirements.analysis.length === 0;
  const cad = managedRequirements ? previous.cad : emptyAnalysis ? requirements.cad : [];
  const next = { constraints: pretty(defaults.constraints), requirements: pretty({ cad, analysis: defaults.required_validations.analysis }), cad };
  if (!state.fixtureCampaignEdited.constraints && ($("optimizationConstraints").value.trim() === "[]" || (previous && $("optimizationConstraints").value === previous.constraints))) $("optimizationConstraints").value = next.constraints;
  if (!state.fixtureCampaignEdited.requirements && (managedRequirements || emptyAnalysis)) $("optimizationRequired").value = next.requirements;
  note.textContent = `${defaults.objectiveLabel} · ${defaults.note} 사용자 제약과 필수 검사는 직접 편집할 수 있습니다.`;
  state.fixtureCampaignDefaults = next;
  renderConstraintEditor();
}
function objectiveTargetMode() {
  const enabled = $("campaignType").value === "optimization" && $("objectiveDirection").value === "match";
  $("objectiveTargetFields").hidden = !enabled;
  for (const id of ["objectiveTarget", "objectiveScale", "objectiveOrigin", "objectiveReference"]) {
    $(id).disabled = !enabled; $(id).required = enabled;
  }
}
function renderConstraintEditor() {
  const container = clear("optimizationConstraintRows"), error = $("optimizationConstraintError");
  error.hidden = true;
  let constraints;
  try {
    constraints = parseField("optimizationConstraints", "array");
    if (constraints.length > 16 || constraints.some(value => !value || typeof value !== "object" || Array.isArray(value))) throw new Error("제약은 최대 16개의 응답 조건으로 입력하세요.");
  } catch (cause) { error.textContent = cause.message; error.hidden = false; return; }
  if (!constraints.length) { container.append(el("p", "추가 제약 없음 · 필요한 응답의 상한 또는 하한을 추가하세요.", "hint")); return; }
  constraints.forEach((constraint, index) => {
    const row = el("div", undefined, "context-readout separated"); row.dataset.constraintRow = "";
    row.append(el("strong", `제약 ${index + 1}`));
    const grid = el("div", undefined, "form-grid");
    for (const [key, label, choices] of [
      ["source", "응답 출처", [["cad", "CAD"], ["analysis", "해석"], ["model", "선언 모델"]]],
      ["metric", "응답 지표"], ["unit", "단위"], ["operator", "조건", [["<=", "이하"], [">=", "이상"]]],
      ["limit", "한계값"], ["scale", "정규화 크기"]]) {
      const field = el("label", label), input = el(choices ? "select" : "input");
      input.dataset.constraintField = key; input.setAttribute("aria-label", `제약 ${index + 1} ${label}`);
      if (choices) {
        const values = choices.some(([value]) => value === constraint[key]) ? choices : [...choices, [String(constraint[key] ?? ""), "미지원 값 · 수정 필요"]];
        values.forEach(([value, caption]) => { const option = el("option", caption); option.value = value; input.append(option); });
      } else if (["limit", "scale"].includes(key)) { input.type = "number"; input.step = "any"; }
      input.value = constraint[key] ?? "";
      input.addEventListener("input", syncConstraintEditor); field.append(input); grid.append(field);
    }
    row.append(grid, action("제약 삭제", () => { row.remove(); syncConstraintEditor(); if (!container.children.length) renderConstraintEditor(); }, "button secondary compact"));
    container.append(row);
  });
}
function syncConstraintEditor() {
  const fields = [...$("optimizationConstraintRows").querySelectorAll("[data-constraint-row]")].map(row =>
    Object.fromEntries([...row.querySelectorAll("[data-constraint-field]")].map(input => [input.dataset.constraintField, input.value])));
  const error = $("optimizationConstraintError");
  try {
    $("optimizationConstraints").value = pretty(fields.map(window.campaignControls.constraintFromFields)); error.hidden = true;
  } catch (cause) {
    $("optimizationConstraints").value = pretty(fields.map(value => ({ ...value,
      limit: value.limit.trim() ? Number(value.limit) : null, scale: value.scale.trim() ? Number(value.scale) : null })));
    error.textContent = cause.message; error.hidden = false;
  }
  if (!isModelCampaign() && !isFixedCadCampaign()) state.fixtureCampaignEdited.constraints = true;
}
function campaignTargetChanged() {
  const previous = state.campaignTarget;
  state.campaignDrafts[previous] = Object.fromEntries(["objectiveSource", "objectiveDirection", "objectiveMetric", "objectiveUnit", "objectiveTarget", "objectiveScale", "objectiveOrigin", "objectiveReference", "optimizationConstraints", "optimizationInitial", "optimizationRequired"].map((id) => [id, $(id).value]));
  if (previous === "cad") state.cadCampaignType = $("campaignType").value;
  state.campaignTarget = $("campaignTarget").value;
  const model = isModelCampaign(), fixed = isFixedCadCampaign();
  const draft = state.campaignDrafts[state.campaignTarget] ?? { objectiveSource: fixed ? "analysis" : model ? "model" : "cad", objectiveDirection: "minimize", objectiveMetric: fixed ? "max_displacement" : model ? "" : "cad_volume", objectiveUnit: fixed ? "mm" : model ? "" : "mm^3", objectiveTarget: "", objectiveScale: "1", objectiveOrigin: "DESIGN_TARGET", objectiveReference: "", optimizationConstraints: "[]", optimizationInitial: "null", optimizationRequired: model ? '{"model": []}' : '{"cad": [], "analysis": []}' };
  Object.entries(draft).forEach(([id, value]) => { $(id).value = value; });
  $("campaignType").value = model || fixed ? "optimization" : state.cadCampaignType;
  $("campaignType").querySelector('[value="doe"]').disabled = model || fixed;
  $("declaredModelArea").hidden = !model; $("campaignCadAnalysis").hidden = model || fixed;
  $("fixedCadConditionsArea").hidden = !fixed;
  $("objectiveSource").querySelectorAll("option").forEach((item) => { item.disabled = fixed ? item.value !== "analysis" : model ? item.value !== "model" : item.value === "model"; });
  campaignMode(); renderCampaignVariables();
  try { applyFixtureCampaignDefaults(); } catch (error) { notify(error.message); }
  renderConstraintEditor();
}
function campaignMode() {
  const optimization = $("campaignType").value === "optimization";
  $("optimizationFields").hidden = !optimization; $("sampleCountField").hidden = optimization;
  $("campaignPlanBtn").dataset.operation = campaignOperation();
  $("campaignId").value = makeId(optimization ? "C-opt" : "C-doe"); updateControls();
  objectiveTargetMode(); renderConstraintEditor();
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
async function inspectCampaign(identifier, stillCurrent = () => true) {
  if (!stillCurrent() || state.storeSwitching) return;
  const request = ++state.campaignRequest, store = activeStore(), studyId = state.studyId;
  const current = () => request === state.campaignRequest && store === activeStore() && studyId === state.studyId && !state.storeSwitching && stillCurrent();
  state.selectedCampaign = null; const container = clear("campaignDetail");
  container.append(el("p", "계획과 journal을 검사하고 있습니다…", "hint"));
  try {
    const data = await api(`/api/campaigns/${idPath(identifier)}`);
    if (!current()) return;
    const plan = data.plan ?? data.record?.plan ?? data.record;
    if (!data.record || !plan || plan.campaign_id !== identifier || !["optimization", "doe"].includes(data.type)) throw new Error("서버가 요청한 고정 계획의 식별자를 확인하지 않았습니다.");
    state.selectedCampaign = { ...data, id: identifier, plan, viewStore: store, viewStudy: studyId, viewRequest: request }; renderCampaignDetail();
  } catch (error) { if (!current()) return; clear(container).append(el("p", `기록 확인 실패: ${error.message}`, "metric-reason")); throw error; }
}
function experimentButton(identifier, label = identifier) {
  if (!identifier) return el("span", "—", "hint");
  return action(label, async () => { location.hash = "results"; await inspectExperiment(identifier); }, "record-id");
}
function campaignViewCurrent(data) {
  return Boolean(data && state.selectedCampaign === data && data.viewStore === activeStore() && !state.storeSwitching &&
    data.viewStudy === state.studyId && data.viewRequest === state.campaignRequest && data.plan?.study_id === state.studyId && data.conditionsVerified !== false);
}
function campaignResultButton(data, row, kind) {
  const key = kind === "cad" ? "cad" : kind === "model" ? "model" : "analysis", identifier = row[`${key}_experiment_id`], digest = row[`${key}_result_sha256`];
  if (!identifier || !/^[0-9a-f]{64}$/.test(digest ?? "")) return el("span", identifier ? `${identifier} · 실제 결과 확인 전` : "—", "hint");
  const current = () => campaignViewCurrent(data);
  const button = action(identifier, () => {
    if (!current() || viewBusy()) return;
    return inspectExperiment(identifier, current, { resultSha256: digest, studyId: data.plan.study_id,
      ...(key === "analysis" ? { parentId: row.cad_experiment_id } : {}) });
  }, "record-id");
  button.dataset.campaignResult = ""; button.disabled = !current() || viewBusy(); return button;
}
function campaignResearchRows(data) {
  const plan = data.plan, record = data.record, model = (record.route ?? plan.route) === "model_analysis";
  return list(record.evaluations ?? record.samples).filter(row => row.decision === "NOT_RELEASED" && Number.isSafeInteger(row.index) && row.index >= 0 &&
    (model ? row.model_experiment_id && /^[0-9a-f]{64}$/.test(row.model_result_sha256 ?? "") : row.cad_experiment_id && /^[0-9a-f]{64}$/.test(row.cad_result_sha256 ?? "") &&
      (!plan.analysis || row.analysis_experiment_id && /^[0-9a-f]{64}$/.test(row.analysis_result_sha256 ?? ""))));
}
function prepareCampaignResearch(data, indexes = [...state.campaignResearchSelection.indexes]) {
  if (!campaignViewCurrent(data) || busy() || activeStore() !== "local" || !writable()) throw new Error("같은 작업 저장소·연구의 캠페인을 다시 연 뒤 질문에 연결하세요.");
  if (data.plan.analysis?.conditions_template) window.campaignControls.conditionTemplate(data.plan);
  const draft = window.comparisonResearch.campaignDraft(data, state.studyId, indexes);
  const previous = $("researchQuestion").value, prefix = previous === state.campaignResearchDraft ? state.campaignResearchPrefix : previous;
  const question = prefix.trim() ? `${prefix}\n\n${draft.question}` : draft.question;
  window.researchControls.request(question);
  $("researchQuestion").value = question; state.campaignResearchDraft = question; state.campaignResearchPrefix = prefix;
  state.researchSession = null; $("researchContinue").checked = false;
  location.hash = "research"; showArea("research"); updateResearchControls(); $("researchQuestion").focus?.();
  notify(draft.intent === "RUN_SAVED_OPTIMIZATION" ? "저장한 계획 하나의 실행을 요청하는 질문을 준비했습니다. 연결 범위를 확인하고 직접 질문을 보내세요." : "선택한 실제 후보와 고정 조건을 해석할 질문을 준비했습니다. 편집 후 직접 질문을 보내세요.", true);
  return draft;
}
function renderCampaignDetail() {
  const data = state.selectedCampaign; if (!data) return;
  const container = clear("campaignDetail"), record = data.record, plan = data.plan;
  data.conditionsVerified = true;
  if (plan.analysis?.conditions_template || plan.route === 'fixed_cad_analysis') {
    try { window.campaignControls.conditionTemplate(plan); }
    catch { data.conditionsVerified = false; }
  }
  container.append(el("h3", data.id, "mono"));
  const summary = el("div", undefined, "campaign-summary"); summary.append(badge(record.status), badge(record.decision ?? "NOT_RELEASED"));
  if (record.termination) summary.append(el("p", `종료: ${labels[record.termination.termination_reason] ?? record.termination.termination_reason} · ${record.termination.generations}세대 · ${record.termination.evaluation_count}개 평가`));
  summary.append(el("p", "계획/작업 완료는 출시 승인이나 전역 최적해를 의미하지 않습니다."));
  const algorithm = record.algorithm ?? plan.algorithm;
  if (algorithm) summary.append(el("p", `${algorithm.engine} ${algorithm.version} · seed ${algorithm.seed}`, "mono"));
  container.append(summary);
  if (plan.objective) {
    const objective = plan.objective, target = objective.direction === "match";
    const goal = el("section", undefined, "context-readout separated");
    goal.append(el("h3", "고정한 연구 목표"), el("p", `${objective.source} · ${objective.metric} · ${objective.unit}`),
      el("p", target ? `목표값 ${number(objective.target)} ${objective.unit} · 정규화 크기 ${number(objective.scale)} ${objective.unit}` : objective.direction === "maximize" ? "응답 최대화" : "응답 최소화"));
    if (target) goal.append(el("p", `${objective.origin} · ${objective.reference}`), el("p", "정규화한 차이의 제곱으로 후보를 비교합니다. 목표의 물리적 자격은 UNKNOWN입니다.", "hint"));
    container.append(goal);
  }
  if (!campaignViewCurrent(data)) container.append(el("p", "이 기록의 연구를 선택한 뒤 실행·결과·질문 연결을 사용하세요.", "hint"));
  if (plan.analysis?.conditions_template || plan.route === 'fixed_cad_analysis') {
    try {
      const template = window.campaignControls.conditionTemplate(plan), source = template.record.source;
      const frozen = el("section", undefined, "context-readout separated");
      frozen.append(el("h3", `고정 조건 ${template.reference.id}`), el("p", `원 CAD ${source.experiment_id} · CAD 개정 ${source.cad_revision}`, "mono"));
      frozen.append(table(["보존 조건", "입력·출처"], conditionReadoutRows(template.record)));
      frozen.append(el("p", "서버 지원 선언 · native runtime NOT_CHECKED · USER_DECLARED_UNVERIFIED · 공학 자격 UNKNOWN · NOT_RELEASED", "hint"),
        el("p", plan.route === 'fixed_cad_analysis' ? "같은 CAD 개정·native 면·메시 크기를 유지합니다. 선택한 재료·하중 성분과 가정 출처만 새 조건으로 보존하며 후보마다 실제 해석을 수행합니다." : "후보 개정마다 동일한 선택·좌표계 의미를 다시 확인하고 새 조건을 보존합니다. 실제 자식 결과에서 해당 개정의 동결 조건을 확인하세요.", "hint"), rawDetail("고정한 원 조건·선택 재연결 정책·참조 해시", template));
      container.append(frozen);
    } catch (error) { container.append(el("p", `고정 조건 확인 실패: ${error.message}`, "metric-reason")); }
  }
  const operation = data.type === "optimization" ? "optimization_run" : "doe_run";
  const current = () => campaignViewCurrent(data);
  const button = action("계획 실행 / 이어가기", async () => {
    if (!current() || busy() || !writable()) return;
    try { await runJob(operation, { campaign_id: data.id }, () => current() ? inspectCampaign(data.id, () => data.viewStore === activeStore() && data.viewStudy === state.studyId && !state.storeSwitching) : undefined, current); }
    catch (error) { if (current()) throw error; }
  }, "button primary compact");
  button.dataset.operation = operation; button.dataset.campaignRun = ""; container.append(button);
  const rows = list(record.evaluations ?? record.samples ?? plan.samples);
  const model = (record.route ?? plan.route) === "model_analysis";
  if (model) container.append(el("p", `${typeof plan.backend === "string" ? plan.backend : "선언한 모델 입력의 수치 탐색"} · 물리적 자격 UNKNOWN`, "hint"));
  const actual = campaignResearchRows(data), selectionKey = JSON.stringify([data.viewStore, plan.study_id, data.id]);
  if (state.campaignResearchSelection.key !== selectionKey) state.campaignResearchSelection = { key: selectionKey, indexes: new Set(actual.length <= 12 ? actual.map(row => row.index) : []) };
  else state.campaignResearchSelection.indexes = new Set([...state.campaignResearchSelection.indexes].filter(index => actual.some(row => row.index === index)));
  const handoff = action(record.status === "PLANNED" && data.type === "optimization" ? "이 저장 계획 실행을 AI 질문에 준비" : "선택한 실제 후보를 연구 질문에 연결", () => prepareCampaignResearch(data), "button secondary compact");
  handoff.dataset.campaignResearch = "";
  const ready = () => {
    try { window.comparisonResearch.campaignDraft(data, plan.study_id, [...state.campaignResearchSelection.indexes]); return true; } catch { return false; }
  };
  handoff.dataset.ready = String(ready());
  const researchNote = el("p", "실제 결과가 있는 후보 최대 12개를 질문에 연결합니다. 실패·미확인 기록과 기존 질문은 보존합니다. 질문은 편집 후 직접 보내며 승인된 연결 범위에서 실행됩니다.", "hint separated");
  if (data.type === "doe") researchNote.append(el("span", " DOE 실행은 위의 사람이 조작하는 실행 버튼을 사용하세요. 현재 승인 AI 범위에 DOE 실행을 추가하지 않습니다."));
  container.append(handoff, researchNote);
  if (rows.length) container.append(table(model ? ["질문", "후보 / 연구 변수", "모델 해석", "판정"] : ["질문", "후보 / 연구 변수", "CAD", "해석", "판정"], rows.slice(0, 512).map((row) => {
    const choose = el("div");
    if (actual.some(candidate => candidate.index === row.index)) {
      const input = el("input"); input.type = "checkbox"; input.checked = state.campaignResearchSelection.indexes.has(row.index);
      input.dataset.campaignCandidate = ""; input.setAttribute("aria-label", `후보 ${row.index} 실제 결과를 연구 질문에 포함`);
      input.addEventListener("change", () => {
        if (!current()) return;
        if (input.checked && state.campaignResearchSelection.indexes.size >= 12) { input.checked = false; notify("연구 질문에는 최대 12개 실제 후보를 선택하세요."); return; }
        if (input.checked) state.campaignResearchSelection.indexes.add(row.index); else state.campaignResearchSelection.indexes.delete(row.index);
        handoff.dataset.ready = String(ready()); updateControls();
      }); choose.append(input);
    } else choose.append(el("small", "실제 해석 확인 전"));
    const values = el("div", row.index ?? row.id ?? "후보");
    Object.entries(row.values ?? {}).forEach(([id, value]) => { const variable = plan.variables?.find(item => item.parameter_id === id); values.append(el("small", `${variable?.display_name ?? id}: ${number(value)} ${variable?.unit ?? ''}`)); });
    if (row.objective?.valid) values.append(el("strong", `${row.objective.metric} = ${number(row.objective.value)} ${row.objective.unit}`));
    if (row.objective?.target_comparison) {
      const target = row.objective.target_comparison;
      values.append(el("small", target.valid ? `목표와 차이 ${number(target.difference)} ${target.unit} · 비교 점수 ${number(target.score)}` : target.reason, target.valid ? "" : "metric-reason"));
    }
    for (const constraint of row.constraints ?? []) values.append(el("small", `${constraint.metric}: ${constraint.valid ? number(constraint.value) : "유효 응답 없음"} ${constraint.unit} ${constraint.operator} ${number(constraint.limit)} · ${constraint.satisfied === true ? "충족" : constraint.satisfied === false ? "미충족" : "판정 없음"}`));
    if (row.condition_input_rejection) values.append(el("small", row.condition_input_rejection, "metric-reason"));
    const cad = el("div"); cad.append(campaignResultButton(data, row, "cad"), el("small", row.cad_status ?? "계획됨"));
    const analysis = el("div"); analysis.append(campaignResultButton(data, row, "analysis"), el("small", row.analysis_status ?? "미실행"));
    const verdict = el("div"); if (typeof row.numerically_feasible === "boolean") verdict.append(badge(row.numerically_feasible ? "PASS" : "FAIL", row.numerically_feasible ? "수치 조건 충족" : "수치 조건 미충족"));
    verdict.append(el("small", `UNKNOWN ${list(row.unknown).length}개`));
    if (model) { const result = el("div"); result.append(campaignResultButton(data, row, "model"), el("small", row.model_status ?? "미실행")); return [choose, values, result, verdict]; }
    return [choose, values, cad, analysis, verdict];
  })));
  if (record.incumbent) container.append(rawDetail("현재 최선의 유효 후보 · optimum 승인 아님", record.incumbent));
  container.append(rawDetail("고정 계획 · 원 조건·algorithm·변수·예산", plan), rawDetail("실제 평가 · 실패·미확인·journal 기록", record)); updateControls();
  button.disabled ||= !current();
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
async function inspectExperiment(identifier, stillCurrent = () => true, expected = null, area = "results") {
  if (!stillCurrent()) return;
  if (state.storeSwitching) throw new Error("저장소를 바꾸고 있습니다. 전환 후 기록을 열어 주세요.");
  if (!window.resultPresentation.safeExperimentId(identifier)) throw new Error("실험 식별자를 확인할 수 없습니다.");
  const pane = engineeringWorkspaceEnabled() && ["design", "simulation"].includes(area) ? area : "results";
  location.hash = pane; if (engineeringWorkspaceEnabled()) showArea(pane);
  const request = ++state.experimentRequest, store = activeStore();
  state.fixtureViewer?.destroy(); state.fixtureViewer = null;
  state.selectedExperiment = null;
  state.selectedFieldObservation = null;
  resetEngineeringProperties();
  state.selectedHistories = null; $("historyPanel").hidden = true;
  $("observationPanel").hidden = true; state.observationRequest++;
  const loading = panel("실험을 불러오고 있습니다."); loading.append(el("p", "저장된 기록과 원본 파일의 일치를 확인하고 있습니다.", "hint separated")); clear("experimentDetail").append(loading);
  $("selectedSource").textContent = "기록 확인 중";
  try {
    const data = await api(`/api/experiments/${idPath(identifier)}`);
    if (request !== state.experimentRequest || store !== activeStore() || !stillCurrent()) return;
    if (data.integrity !== "VERIFIED" || data.result?.experiment_id !== identifier) throw new Error("서버가 요청한 기록의 식별자와 검증 완료를 확인하지 않았습니다.");
    if (expected && (expected.resultSha256 && data.hashes?.result_sha256 !== expected.resultSha256 || data.result.study?.id !== expected.studyId ||
        expected.parentId && data.result.parent_experiment_id !== expected.parentId ||
        expected.cadRevision && data.result.cad_revision !== expected.cadRevision || expected.backend && data.result.provenance?.adapter !== expected.backend))
      throw new Error("보존 결과 해시·연구·CAD 개정·경로가 선택한 원 기록과 다릅니다.");
    state.selectedExperiment = data; renderExperimentDetail(data); renderObservation(data);
    loadResponseHistories(data).catch(error => {
      if (state.selectedExperiment === data && store === activeStore() && stillCurrent()) notify(error.message);
    });
  } catch (error) {
    if (request !== state.experimentRequest || store !== activeStore() || !stillCurrent()) return;
    const card = panel("이 실험의 기록을 확인할 수 없습니다."); card.classList.add("detail-error"); card.append(el("p", error.message), el("p", "파일과 기록의 일치를 확인한 후 결과를 표시합니다."));
    clear("experimentDetail").append(card); $("selectedSource").textContent = "기록 확인 실패"; throw error;
  } finally {
    if (request === state.experimentRequest && store === activeStore() && stillCurrent()) updateEngineeringWorkspace();
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
    && record.result.study?.id === state.studyId && (window.observationControls?.choices(record).length
      || window.historyControls?.channels(record, state.selectedHistories).length || fieldObservationSelection()));
}
function fieldObservationSelection() {
  const selected = state.selectedFieldObservation;
  return selected && selected.inspection === state.selectedExperiment && selected.store === activeStore()
    && selected.request === state.experimentRequest && !state.storeSwitching && selected.current()
    && $("observationResponse").value === selected.key ? selected : null;
}
function prepareFieldObservation(inspection, model, selection, current) {
  if (!current() || state.selectedExperiment !== inspection || inspection.result.study.id !== state.studyId)
    throw new Error("같은 연구의 현재 해석 기록과 절점을 선택하세요.");
  const key = JSON.stringify(["field", selection.artifact, selection.node_id, selection.component]);
  const response = $("observationResponse");
  [...response.options].filter(item => item.dataset.fieldObservation).forEach(item => item.remove());
  option(response, key, `절점 ${selection.node_id} · ${selection.component === "MAGNITUDE" ? "|U|" : selection.component} · mm · ${model.artifact.path}`);
  response.options[response.options.length - 1].dataset.fieldObservation = "true";
  response.value = key;
  state.selectedFieldObservation = { inspection, model, selection, current, key, store: activeStore(), request: state.experimentRequest };
  $("observationPanel").hidden = false; $("observationEditor").open = true;
  if (!$("observationPurpose").value) $("observationPurpose").value = "GENERAL_CAE_RESEARCH";
  if (!$("observationUnit").value) $("observationUnit").value = "mm";
  for (const [id, value] of Object.entries({ observationQuantity: "DISPLACEMENT", observationComponent: selection.component,
    observationFrame: model.field.coordinate_frame })) if (!$(id).value) $(id).value = value;
  changeObservationResponse(); updateControls();
  location.hash = "results"; showArea("results"); $("observationEditor").scrollIntoView({ block: "start", behavior: "smooth" });
  notify("원 절점과 성분을 선택했습니다. 관측값·출처·위치·좌표계를 입력해 비교하세요. 센서의 물리적 정렬은 확인 전입니다.", true);
}
function preparePdeFieldObservation(inspection, field, nodeId, component, current) {
  if (!current() || state.selectedExperiment !== inspection || inspection.result.study.id !== state.studyId)
    throw new Error("같은 연구의 현재 PDE 기록과 절점을 선택하세요.");
  const selection = window.pdeFieldInspector.observationSelection(field, nodeId, component);
  const key = JSON.stringify(["pde_field",selection.artifact,selection.node_id,selection.component]);
  const response = $("observationResponse");
  [...response.options].filter(item=>item.dataset.fieldObservation).forEach(item=>item.remove());
  option(response,key,`PDE 절점 ${nodeId} · ${component} · 단위 1 · ${selection.artifact}`);
  response.options[response.options.length-1].dataset.fieldObservation="true"; response.value=key;
  state.selectedFieldObservation={family:"pde",inspection,field,selection,current,key,store:activeStore(),request:state.experimentRequest};
  $("observationPanel").hidden=false; $("observationEditor").open=true;
  if (!$("observationPurpose").value) $("observationPurpose").value="GENERAL_CAE_RESEARCH";
  if (!$("observationUnit").value) $("observationUnit").value="1";
  for (const [id,value] of Object.entries({observationQuantity:field.components.length === 1 ? "PDE_SCALAR_FIELD" : "PDE_VECTOR_FIELD",
    observationComponent:component,observationFrame:"PDE_MODEL_CARTESIAN"})) if (!$(id).value) $(id).value=value;
  changeObservationResponse(); updateControls(); location.hash="results"; showArea("results");
  $("observationEditor").scrollIntoView({block:"start",behavior:"smooth"});
  notify("원 PDE 절점·성분을 연결했습니다. 관측값·출처와 정확한 단위·축을 입력하세요.",true);
}
function observationSubmissionContext() {
  if (!observationReady()) throw new Error("현재 연구에 속한 검증된 실험과 유효한 응답을 먼저 선택하세요.");
  return { store: activeStore(), studyId: state.studyId, record: state.selectedExperiment };
}
function prepareFeFieldObservation(inspection, field, choice, current) {
  if (!current() || state.selectedExperiment !== inspection || inspection.result.study.id !== state.studyId)
    throw new Error("같은 연구의 현재 FE 기록과 원 절점·적분점을 선택하세요.");
  const selection = choice.selector, key = JSON.stringify(["fe_field", selection]);
  const response = $("observationResponse");
  [...response.options].filter(item=>item.dataset.fieldObservation).forEach(item=>item.remove());
  const pointName = selection.kind === "fe_nodal" ? `절점 ${selection.node_id}` : `요소 ${selection.element_id} · 적분점 ${selection.point}/${selection.subpoint}`;
  option(response,key,`${pointName} · ${selection.component} · t=${number(choice.row.time_s)} s`);
  response.options[response.options.length-1].dataset.fieldObservation="true"; response.value=key;
  state.selectedFieldObservation={family:"fe",inspection,field,choice,selection,current,key,store:activeStore(),request:state.experimentRequest};
  $("observationPanel").hidden=false; $("observationEditor").open=true;
  if (!$("observationPurpose").value) $("observationPurpose").value="GENERAL_CAE_RESEARCH";
  for (const [id,value] of Object.entries({observationUnit:choice.row.unit,observationQuantity:choice.row.quantity,
    observationComponent:selection.component,observationFrame:field.coordinate_frame})) if (!$(id).value) $(id).value=value;
  changeObservationResponse(); updateControls(); location.hash="results"; showArea("results");
  $("observationEditor").scrollIntoView({block:"start",behavior:"smooth"});
  notify("원 FE 위치·성분·시각을 연결했습니다. 관측값·출처·관측 시각을 명시하세요. 측정 위치 정렬은 미확인입니다.",true);
}
function observationArguments() {
  observationSubmissionContext();
  const fields = {
    comparisonId: state.observationId, purpose: $("observationPurpose").value,
    hypothesis: $("observationHypothesis").value, responseKey: $("observationResponse").value,
    name: $("observationName").value, value: $("observationValue").value,
    sourceKind: $("observationSourceKind").value, source: $("observationSource").value,
    quantity: $("observationQuantity").value, component: $("observationComponent").value,
    location: $("observationLocation").value, coordinateFrame: $("observationFrame").value,
    condition: $("observationCondition").value, tolerance: $("observationTolerance").value,
    conditions: parseField("observationConditions", "array"),
    unit: $("observationUnit").value,
  };
  const field = fieldObservationSelection();
  if (field?.family === "pde") return window.observationControls.buildPdeField(state.selectedExperiment,
    {...fields,axisValue:$("observationAxisValue").value},field.selection);
  if (field?.family === "fe") return window.observationControls.buildFeField(state.selectedExperiment,
    {...fields,axisQuantity:"time",axisUnit:"s",axisValue:$("observationAxisValue").value},field.selection);
  if (field) return window.observationControls.buildField(state.selectedExperiment, fields, field.selection);
  if ($("observationResponse").selectedOptions?.[0]?.dataset.fieldObservation)
    throw new Error("선택한 필드가 바뀌었습니다. 현재 메시에서 절점을 다시 연결하세요.");
  const selected = historyObservationChannel();
  return selected ? window.historyControls.build(state.selectedExperiment, state.selectedHistories, {
    ...fields, channelId: selected.id, sampleIndex: $("observationHistorySample").value,
    axisQuantity: selected.axis.quantity, axisUnit: selected.axis.unit, axisValue: $("observationAxisValue").value,
  }) : window.observationControls.build(state.selectedExperiment, fields);
}
function historyObservationChannel() {
  const value = $("observationResponse").value;
  return window.historyControls?.channels(state.selectedExperiment, state.selectedHistories)
    .find(item => value === JSON.stringify(["history", item.id]));
}
function historyChannelCaption(channel) {
  const measure = {"infinitesimal Cauchy stress": "미소변형 응력", "internal branch stress": "점탄성 분기의 내부 응력",
    "reference-volume energy density": "기준 체적당 에너지"}[channel.measure] ?? channel.measure;
  if (channel.origin?.driver === "openradioss") return `${measure} · ${channel.location} · 전역 SI 좌표 · ${channel.axis.semantics === "NATIVE_HALF_STEP_VELOCITY_TIME" ? "반 증분 속도 시각" : "원 해석 시각"} (센서 정렬 미확인)`;
  if (channel.origin?.driver === "code_aster") return `${channel.origin.kind === "DERIVED" ? "전체 적분점의 산술평균 · 가중 없음 · 체적 평균 아님" : "경계 그룹의 부호 있는 원 반력"} · 선택 메시 ${channel.origin.mesh_index} · 전역 모델 좌표 (센서 정렬 미확인)`;
  if (channel.origin?.driver === "mgis") return `${measure} · 균질 재료점 1개 · 모델 성분 기준 (센서·세계 좌표 정렬 미확인)`;
  return `${measure ?? channel.label ?? "보존한 응답"} · ${channel.location ?? "위치 미확인"} · 좌표 정렬 미확인`;
}
function historyAxisLabel(channel) { return channel.axis.quantity === "time" ? "시간 (s)" : "하중 계수 (무차원)"; }
function historyAxisValue(channel, value) { return `${number(value)}${channel.axis.quantity === "time" ? " s" : " · 하중 계수"}`; }
function observationResponseNote() {
  const history = historyObservationChannel();
  const field = fieldObservationSelection();
  $("observationFieldFields").hidden = !field;
  $("observationUnit").required = Boolean(field);
  const pdeTime = field?.family === "pde" && field.selection.step_index !== null, feTime = field?.family === "fe";
  $("observationHistoryFields").hidden = !history && !pdeTime && !feTime;
  $("observationHistorySample").required = Boolean(history);
  $("observationHistorySample").parentElement.hidden = Boolean(pdeTime || feTime);
  $("observationAxisValue").required = Boolean(history || pdeTime || feTime);
  if (field?.family === "fe") {
    const row = field.choice.row;
    $("observationResponseNote").textContent=`${row.kind === "fe_nodal" ? `원 절점 ${row.native}` : `원 요소 ${row.native.element_id} · 적분점 ${row.native.point}/${row.native.subpoint}`} · XYZ [${row.coordinates_mm.join(" / ")}] mm · ${row.component} ${number(row.value)} ${row.unit} · t=${number(row.time_s)} s / order ${row.actual_result_order}. ${row.initial_state ? "초기 상태이며 새 Newton 증분이 아닙니다." : "같은 native 기록의 부호 있는 성분입니다."} 다른 메시·시각·성분의 값으로 대체하지 않습니다.`;
    $("observationAxisLabel").textContent="관측 시각 (s)";
    return;
  }
  if (field?.family === "pde") {
    const raw = field.field, node = raw.nodes.find(value=>value.id === field.selection.node_id), axis = raw.components.indexOf(field.selection.component);
    $("observationResponseNote").textContent=`PDE 원 절점 ${node.id} · XY [${node.coordinates.join(" / ")}] (1) · ${field.selection.component} ${number(node.values[axis])} (1) · PDE 모델 좌표. ${pdeTime ? `기록 축 t=${number(raw.selection.time)} (1) · ${raw.selection.solverStatus === "NOT_RUN" ? "미적분 초기조건" : "계산 단계"}. 시간 단위는 초로 변환하지 않습니다.` : "정적 필드입니다."} 참조·물리 자격은 원래 판정을 유지합니다.`;
    return;
  }
  if (field) {
    const raw = field.model.field, selected = field.selection, node = raw.nodes.find(value => value.node_id === selected.node_id);
    const value = window.fixtureFieldControls.scalar(node, selected.component);
    $("observationResponseNote").textContent = `절점 ${node.node_id} · 원본 XYZ [${node.position_mm.join(" / ")}] mm · ${selected.component} ${number(value)} mm · ${raw.coordinate_frame}. 선언 물리량 DISPLACEMENT·성분 ${selected.component}·좌표계 ${raw.coordinate_frame}가 정확히 일치할 때만 차이를 계산합니다. 정적 load parameter ${raw.static.load_parameter}는 시간이 아닙니다.`;
    return;
  }
  if (history) {
    const sample = Number($("observationHistorySample").value), found = $("observationHistorySample").value !== "" && Number.isInteger(sample) && sample < history.values.length;
    $("observationResponseNote").textContent = `${history.label} · ${historyChannelCaption(history)}${found ? ` · 기록값 ${number(history.values[sample])} ${history.unit}, ${historyAxisValue(history, history.axis.values[sample])}` : " · 기록 표본을 선택하세요."} 선언한 축 좌표·물리량·성분이 정확히 일치할 때만 차이를 계산합니다.`;
    return;
  }
  const choice = window.observationControls?.choices(state.selectedExperiment).find(item => item.key === $("observationResponse").value);
  $("observationResponseNote").textContent = choice
    ? `기록된 응답: ${number(choice.value)} ${choice.unit} · 관측값과 허용 차이도 ${choice.unit}로 입력하세요.${choice.component !== undefined ? " 배열 항목의 물리적 성분은 사용자가 확인해야 합니다." : ""}`
    : "선택한 응답의 값과 단위가 여기에 나타납니다.";
}
function changeObservationResponse() {
  const history = historyObservationChannel(), samples = clear("observationHistorySample");
  $("observationAxisValue").value = "";
  if (history) {
    $("observationAxisLabel").textContent = `관측 ${historyAxisLabel(history)}`;
    option(samples, "", "기록된 표본을 선택하세요");
    history.axis.values.forEach((time, index) => option(samples, String(index), `${historyAxisValue(history, time)}${history.initial_state?.index === index ? " · 초기 상태" : ""}`));
  }
  const field = fieldObservationSelection();
  if (field?.family === "pde" && field.selection.step_index !== null) {
    $("observationAxisLabel").textContent="관측 시간축 (1 · 무차원)";
    option(samples,String(field.selection.step_index),`선택 단계 ${field.selection.step_index} · t=${number(field.field.selection.time)} (1)`);
  }
  observationResponseNote();
}
async function loadResponseHistories(inspection) {
  const store = activeStore();
  if (inspection.result.status !== "COMPLETED_REVIEW_REQUIRED") return;
  const value = await api(`/api/response-histories/${idPath(inspection.result.experiment_id)}`);
  if (state.storeSwitching || store !== activeStore() || state.selectedExperiment !== inspection) return;
  const channels = window.historyControls?.channels(inspection, value) ?? [];
  state.selectedHistories = value;
  $("historyPanel").hidden = !channels.length;
  if (!channels.length) return;
  $("observationPanel").hidden = false;
  const select = clear("historyChannel");
  channels.forEach(item => {
    option(select, item.id, `${item.label} · ${item.unit}`);
    option($("observationResponse"), JSON.stringify(["history", item.id]), `${item.label} · 응답 이력 · ${item.unit}`);
  });
  select.value = channels[0].id; renderHistoryChannel(); updateControls();
}
function renderHistoryChannel() {
  const channel = window.historyControls?.channels(state.selectedExperiment, state.selectedHistories)
    .find(item => item.id === $("historyChannel").value);
  if (!channel) { $("historyPanel").hidden = true; return; }
  $("historyContext").textContent = `${channel.label} · ${historyChannelCaption(channel)}${channel.measure === "reference-volume energy density" ? " · MPa = MJ/m³ (기준 체적)" : ""}`;
  $("historyHint").textContent = "기록된 표본·축·부호를 유지합니다. 선은 표본 순서이며 중간값을 계산하지 않습니다. " + (channel.origin.driver === "openradioss"
    ? "속도는 반 증분 시각, 위치·에너지는 원 시각입니다. 스프링 일은 부호를 유지하며 벽의 FNZ는 누적 충격량입니다."
    : channel.origin.driver === "code_aster" ? "0초는 새 Newton 증분이 없는 선언 초기 상태입니다. 준정적 이력의 시각과 원 native order를 유지하며 가중 없는 적분점 평균은 체적 평균이 아닙니다."
    : "0초는 재료 적분 전의 수치 초기 상태입니다.");
  const select = clear("historySample");
  channel.axis.values.forEach((time, index) => option(select, String(index), `${historyAxisValue(channel, time)}${channel.initial_state?.index === index ? " · 초기 상태" : ""}`));
  select.value = String(channel.values.length - 1);
  const target = clear("historyPlot"), width = 720, height = 250, left = 85, right = 25, top = 30, bottom = 45;
  const xs = channel.axis.values, ys = channel.values, min = Math.min(...ys), max = Math.max(...ys);
  const range = max - min, span = xs.at(-1) - xs[0];
  if (Number.isFinite(range) && Number.isFinite(span) && span > 0) {
    const svgNode = (name, attrs = {}, label) => {
      const node = document.createElementNS("http://www.w3.org/2000/svg", name);
      Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
      if (label !== undefined) node.textContent = label;
      return node;
    };
    const svg = svgNode("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": `${channel.label}, ${historyAxisLabel(channel)}에 따른 ${channel.unit}`, style: "display:block;width:100%;max-height:300px;background:var(--surface,#fff)" });
    const x = value => left + (value - xs[0]) / span * (width - left - right);
    const y = value => range > 0 ? top + (1 - (value - min) / range) * (height - top - bottom) : (height - bottom + top) / 2;
    svg.append(svgNode("path", { d: `M${left} ${top}V${height-bottom}H${width-right}`, stroke: "#9ca9b6", fill: "none" }),
      svgNode("polyline", { points: xs.map((value,index) => `${x(value)},${y(ys[index])}`).join(" "), fill: "none", stroke: "#376a83", "stroke-width": 2 }));
    [[left, height-18, historyAxisValue(channel, xs[0])], [width-right-25,height-18,historyAxisValue(channel, xs.at(-1))],
      [7,top+4,`${number(max)} ${channel.unit}`], [7,height-bottom,`${number(min)} ${channel.unit}`]].forEach(([a,b,label]) => svg.append(svgNode("text", {x:a,y:b,fill:"#526171","font-size":11},label)));
    xs.forEach((time,index) => {
      const point = svgNode("circle", {cx:x(time),cy:y(ys[index]),r:5,fill:"#376a83",role:"button",tabindex:0,"aria-label":`${historyAxisValue(channel, time)} · ${number(ys[index])} ${channel.unit}`});
      point.append(svgNode("title", {}, `${historyAxisValue(channel, time)} · ${number(ys[index])} ${channel.unit}`));
      const choose = () => { select.value = String(index); renderHistorySample(); };
      point.addEventListener("click", choose); point.addEventListener("keydown", event => { if (["Enter"," "].includes(event.key)) { event.preventDefault(); choose(); } }); svg.append(point);
    });
    target.append(svg);
  } else target.append(el("p", "축 범위가 표시 한계를 초과합니다. 시점별 원래 값에서 확인하세요.", "hint"));
  clear("historyTable").append(table([historyAxisLabel(channel), `${channel.label} (${channel.unit})`], xs.map((value,index) => [number(value),number(ys[index])])));
  clear("historyOrigin").append(rawDetail("채널·native 출처·원본 해시", channel));
  renderHistorySample();
}
function renderHistorySample() {
  const choice = window.historyControls?.sampleChoice(state.selectedExperiment, state.selectedHistories, $("historyChannel").value, Number($("historySample").value));
  $("historyValue").textContent = choice ? `${choice.label} · ${number(choice.value)} ${choice.unit}` : "";
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
function responseFieldCaption(field) {
  if (["fe_nodal", "fe_gauss"].includes(field.kind)) return `${field.kind === "fe_nodal" ? `절점 ${field.node_id}` : `요소/적분점/하위점 ${field.element_id}/${field.point}/${field.subpoint}`} · ${field.component} · 원 XYZ [${field.coordinates_mm.join(" / ")}] mm · ${field.coordinate_frame} · 부호 있는 원 native 성분`;
  if (field.model_revision) return `PDE 절점 ${field.node_id} · ${field.component} · 원 XY [${field.coordinates.join(" / ")}] (${field.coordinates_unit}) · ${field.coordinate_frame} · 부호 있는 원 성분`;
  return `절점 ${field.node_id} · ${field.component} · ${field.coordinate_frame} · 원 XYZ [${field.position_mm.join(" / ")}] ${field.position_unit} · ${field.value_origin === "DERIVED_MAGNITUDE" ? "저장 UX·UY·UZ의 벡터 크기" : "원본의 부호 있는 성분"}`;
}
function prepareComparisonResearch(rows, context) {
  if (busy() || state.storeSwitching || !context || context.store !== activeStore()
      || context.inspection !== state.selectedExperiment || context.studyId !== context.inspection.result.study.id
      || activeStore() !== "local" || !writable())
    throw new Error("같은 작업 저장소의 결과와 비교 기록을 선택한 뒤 연구 질문에 연결하세요.");
  const study = state.study?.record ?? state.study;
  const original = study?.id === context.studyId ? { question: study.research_question, hypothesis: study.hypothesis, objective: study.objective } : null;
  const draft = window.comparisonResearch.draft(rows, context.studyId,
    original && Object.values(original).every(value => typeof value === "string" && value.length <= 2000) ? original : undefined);
  const previous = $("researchQuestion").value;
  const prefix = previous === state.comparisonResearchDraft ? state.comparisonResearchPrefix : previous;
  const question = prefix.trim() ? `${prefix}\n\n${draft.question}` : draft.question;
  window.researchControls.request(question); // Validate before changing an edited question.
  $("researchQuestion").value = question; state.comparisonResearchDraft = question;
  state.comparisonResearchPrefix = prefix;
  state.researchSession = null; $("researchContinue").checked = false;
  location.hash = "research"; showArea("research"); updateResearchControls();
  $("researchQuestion").focus?.();
  notify("저장된 비교를 확인할 연구 질문을 준비했습니다. 질문 보내기를 누르면 연결된 AI가 원기록을 읽습니다.", true);
  return draft;
}
function renderObservation(data) {
  const choices = window.observationControls?.choices(data) ?? [];
  const panel = $("observationPanel"); panel.hidden = !choices.length || data.result.status !== "COMPLETED_REVIEW_REQUIRED";
  state.observationRequest++; clear("observationRecords");
  state.selectedFieldObservation = null;
  if (data.result.status !== "COMPLETED_REVIEW_REQUIRED") return;
  state.observationId = makeId("O");
  $("observationContext").textContent = `선택한 ${observationSourceCaption({ backend: data.result.provenance.adapter, execution: data.proposal.execution })} 결과에 관측을 연결합니다. 원래 모델과 응답은 그대로 보존합니다.`;
  $("observationEditor").open = false;
  const response = clear("observationResponse"); option(response, "", "유효한 응답을 선택하세요");
  choices.forEach(choice => option(response, choice.key, `${choice.label} · ${choice.unit}`));
  for (const id of ["observationPurpose", "observationHypothesis", "observationName", "observationSourceKind", "observationSource",
    "observationValue", "observationTolerance", "observationQuantity", "observationComponent", "observationLocation", "observationFrame", "observationCondition", "observationUnit"]) $(id).value = "";
  $("observationPurpose").value = "GENERAL_CAE_RESEARCH";
  $("observationConditions").value = "[]"; response.value = ""; clear("observationHistorySample"); $("observationAxisValue").value = ""; observationResponseNote(); updateControls();
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
    const researchContext = {store, studyId, inspection};
    if (rows.length) target.append(action("이 연구의 관측 비교를 AI 질문에 연결", () => prepareComparisonResearch(rows, researchContext)));
    rows.forEach(value => {
      const record = value.record, comparison = record?.comparison;
      if (value.integrity !== "VERIFIED" || record?.source?.study_id !== studyId || !comparison) {
        const error = el("p", `확인할 수 없는 비교 기록: ${value.id ?? "미제공"} · ${value.error ?? "원본 일치 미확인"}`, "metric-reason"); target.append(error); return;
      }
      const observation = record.request.observation, details = el("details", undefined, "advanced separated");
      const kind = { MEASURED_REPORTED: "사용자 보고 측정값", SPECIFICATION: "규격·목표값", SYNTHETIC: "가상 데이터" }[observation.source_kind];
      const mismatch = comparison.status !== "NUMERIC_DIFFERENCE_ONLY";
      const mismatchCaption = record.request.response.field ? "조건·성분·좌표계 불일치 · 차이 계산 보류" : "조건·시각 불일치 · 차이 계산 보류";
      details.append(el("summary", `${observation.name} · ${kind} · ${mismatch ? mismatchCaption : "수치 차이 기록됨"}`));
      details.append(el("p", record.request.hypothesis, "separated"), el("p", `해석 조건: ${observationSourceCaption(record.source)}`),
        el("p", `출처: ${observation.source}`), el("p", `관측 범위: ${observation.quantity} · ${observation.component} · ${observation.location} · ${observation.coordinate_frame}`),
        el("p", `관측 조건: ${observation.condition}`));
      const selected = record.request.response;
      const sourceChoice = !selected.history_channel && !selected.field && record.source.experiment_id === inspection.result.experiment_id
        ? window.observationControls?.choices(inspection).find(choice => choice.metric === selected.metric && choice.component === selected.component) : null;
      const channel = comparison.source_channel;
      const field = comparison.source_field;
      details.append(el("p", `원 응답: ${field ? responseFieldCaption(field) : channel ? `${channel.label} · ${historyChannelCaption(channel)} · 기록 시각 ${number(comparison.response_axis.value)} ${comparison.response_axis.unit}` : sourceChoice?.label ?? window.resultPresentation.metricName(selected.metric)}${selected.component !== undefined && !sourceChoice ? ` · 사용자 지정 배열 항목 ${selected.component + 1} (물리 성분 미확인)` : ""}`));
      if (["fe_nodal", "fe_gauss"].includes(field?.kind)) details.append(el("p", `FE 메시 ${field.mesh_index} · 원 시간 ${field.time_s} s / order ${field.actual_result_order} · ${field.measure} · ${field.time_index === 0 ? "선언한 초기 상태 (새 Newton 증분 아님)" : "기록된 native 계산 상태"}; 센서 위치 정렬·물리 자격은 미확인입니다.`, "hint"));
      else if (field?.model_revision) details.append(el("p", `PDE 메시 ${field.study_index} · ${field.step_index === null ? "정적 필드" : `원 단계 ${field.step_index}`} · 참조·물리 자격은 원 기록을 유지합니다.`, "hint"));
      else if (field) details.append(el("p", `정적 step ${field.static.step} / increment ${field.static.increment} · load parameter ${field.static.load_parameter} (시간 아님) · 전체 필드의 원 절점 선택이며 센서 위치와의 정렬은 미검증입니다.`, "hint"));
      if (comparison.declared_field_checks) details.append(table(["선언 항목", "관측 선언", "원 응답", "일치"], comparison.declared_field_checks.map(check => [check.property, check.declared, check.actual, check.matched ? "일치" : "불일치"])));
      if (comparison.declared_history_checks) details.append(table(["이력 선언", "관측 선언", "원 채널", "일치"], comparison.declared_history_checks.map(check => [check.property, check.declared, check.actual, check.matched ? "일치" : "불일치"])));
      if (channel?.initial_state && channel.initial_state.index === selected.sample_index && channel.initial_state.kind === "UNPREPARED_INITIAL_CONDITION")
        details.append(el("p", "선택한 표본은 재료 적분 전의 수치 초기 상태이며 적분된 재료 응답의 근거가 아닙니다.", "hint"));
      if (comparison.declared_axis_check) details.append(el("p", `관측 시각: ${number(comparison.declared_axis_check.declared.value)} ${comparison.declared_axis_check.declared.unit} · ${comparison.declared_axis_check.matched ? "기록 시각과 정확히 일치" : "기록 시각과 불일치 · 보간하지 않음"}`));
      details.append(table(["관측·기준", "해석 응답", "해석 − 관측", "절대 허용 차이"], [[
        `${number(comparison.observed_value)} ${comparison.unit}`, `${number(comparison.response_value)} ${comparison.unit}`,
        comparison.difference === null ? mismatchCaption : `${number(comparison.difference)} ${comparison.unit}`,
        `${number(comparison.declared_absolute_tolerance)} ${comparison.unit}`]]));
      details.append(el("p", comparison.within_declared_tolerance === null ? field ? "명시적으로 연결한 입력 조건·성분·좌표계가 일치하지 않습니다." : "명시적으로 연결한 입력 조건 또는 관측 시각이 일치하지 않습니다."
        : comparison.within_declared_tolerance ? "입력한 허용 차이 이내입니다." : "입력한 허용 차이를 초과합니다."));
      details.append(el("p", "위치·성분·좌표계·조건의 물리적 일치는 사용자 선언이며 독립 확인 전입니다. 수치가 맞아도 원인 확정·물리 검증·사용 승인으로 판정하지 않습니다.", "hint"));
      if (!comparison.condition_bindings_supplied) details.append(el("p", "저장된 입력과의 명시적 조건 연결은 제공되지 않았습니다.", "hint"));
      details.append(experimentButton(record.source.experiment_id, "이 비교의 원 해석 결과 보기 →"),
        action("이 비교를 AI 질문에 연결", () => prepareComparisonResearch([value], researchContext)),
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
  const context = result.solver_status === "NOT_RUN" ? "이 기록에는 해석 실행 결과가 없습니다."
    : `해석 실행: ${labels[result.solver_status] ?? "상세 기록에서 확인"} · ${presentation.numericalCaption(result)}`;
  const stage = el("details", undefined, "result-stage-details");
  stage.append(el("summary", "실행 상태·다음 확인"), el("p", workflow.next, "hint"), el("p", context, "result-context"));
  header.append(stage);
  const downloads = el("div", undefined, "button-row");
  downloads.append(link("보고서 열기", `/api/report/${idPath(identifier)}.html`, "button secondary compact"), link("원본 묶음 저장", `/api/report/${idPath(identifier)}.zip`, "button subtle compact", true)); header.append(downloads); container.append(header);

  renderFixtureFields(container, data);
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
  if (data.integrity === "VERIFIED" && result.provenance?.analysis_conditions) {
    const reference = result.provenance.analysis_conditions, declaration = data.proposal;
    const frozen = el("details", undefined, "advanced separated");
    frozen.append(el("summary", "이 결과에 보존된 영역·재료·구속·하중"));
    list(declaration.boundary_conditions).forEach(item => frozen.append(el("p",
      `${item.selection_id}: ${displacementCaption(item.components)} ${item.unit} · ${item.coordinate_system}`, "hint")));
    list(declaration.loads).forEach(item => frozen.append(el("p",
      `${item.selection_id}: FX ${number(item.components?.FX)} / FY ${number(item.components?.FY)} / FZ ${number(item.components?.FZ)} ${item.unit} · ${item.coordinate_system}`, "hint")));
    frozen.append(el("p", `조건 ${reference.id} · 물성·적용 자격 미확인`, "hint"),
      rawDetail("보존한 공통 조건과 출처", { materials: declaration.model?.materials,
        coordinate_systems: declaration.model?.coordinate_systems,
        boundary_conditions: declaration.boundary_conditions, loads: declaration.loads,
        contact: declaration.model?.contact_declaration, conditions_reference: reference }),
      link("실행 시 보존한 조건 원본 저장", artifactUrl(identifier, "analysis_conditions.json"), "text-link", true));
    inputs.append(frozen);
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

  const metrics = panel("결과값"); metrics.classList.add("detail-wide");
  const metricRows = Object.entries(result.metrics ?? {}), metricGrid = el("div", undefined, "result-metrics");
  const selectedMaterial = result.provenance?.adapter === "structural.code_aster.plasticity" && data.proposal?.execution?.mode === "selected_mesh";
  const inactiveMetrics = el("details", undefined, "advanced separated"), inactiveGrid = el("div", undefined, "result-metrics");
  if (selectedMaterial) inactiveMetrics.append(el("summary", `이 실행에서 평가하지 않은 참조 응답 ${metricRows.filter(([,metric])=>metric.valid !== true).length}개`),
    el("p", "선택 메시와 일반 이력으로 실행했습니다. 참조·메시 비교·에너지 판정은 미평가이며 원래 값과 사유를 보존합니다.", "hint"), inactiveGrid);
  metricRows.forEach(([name, metric], index) => {
    const metricLabel = name === "max_displacement" && result.provenance?.adapter === "fixture.calculix"
      && result.provenance?.adapter_details?.per_mesh_displacement?.response_metric === "loaded_saddle_min_global_uz"
      ? "하중 안장 최대 |UZ| (전체 |U| 최대 아님)" : presentation.metricName(name, index);
    const card = el("div", undefined, "result-metric"), label = el("span", metricLabel, "stat-label"); label.title = name;
    const unit = metric.unit === "1" ? (name === "cad_component_count" ? "개" : "") : metric.unit === "mm^3" ? "mm³" : metric.unit ?? "";
    const displayNumber = value => typeof value === "number" && Number.isFinite(value)
      ? new Intl.NumberFormat("ko-KR", { maximumSignificantDigits: 6 }).format(value) : text(value);
    const value = Array.isArray(metric.value) ? (name.endsWith("_history") ? "시점별 배열 · 이력 또는 원본 기록에서 확인" : name === "cad_bounds" ? metric.value.map(displayNumber).join(" × ") : text(metric.value)) : displayNumber(metric.value);
    card.append(label, el("strong", `${value} ${unit}`.trim(), `result-metric-value${metric.valid === true ? "" : " invalid-value"}`), badge(metric.valid === true ? "PASS" : "FAIL", metric.valid === true ? "수치 응답 유효" : "판단에 사용할 수 없는 값"));
    if (metric.reason) card.append(el("p", metric.reason, "metric-reason"));
    (selectedMaterial && metric.valid !== true ? inactiveGrid : metricGrid).append(card);
  });
  if (metricRows.length) metrics.append(metricGrid, el("p", "표시값은 읽기 쉽게 반올림했습니다. 원래 수치·단위·판정은 상세 기록에 보존됩니다.", "hint separated")); else metrics.append(el("p", "이 실험은 사용할 수 있는 수치 결과를 제공하지 않았습니다.", "empty-state"));
  if (selectedMaterial && inactiveGrid.childElementCount) metrics.append(inactiveMetrics);
  container.append(metrics);

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
  if (engineeringWorkspaceEnabled()) { state.experimentProperties = side; state.experimentOverview = overview; mountExperimentInspector(state.activeArea); }
  if (window.cadControls.eligibleParent(state.presets[$("simulationPreset").value], { ...result, backend: result.provenance?.adapter })) $("analysisParent").value = identifier;
  updateControls();
}
function renderFixtureFields(container, inspection) {
  const result = inspection.result;
  if (result.provenance?.adapter === "structural.code_aster.plasticity") return renderNativeFeFields(container, inspection);
  if (result.provenance?.adapter === 'fixture.assembly_mechanics.code_aster') return renderAssemblyFields(container, inspection);
  const native = result.provenance?.adapter === "structure.calculix.native";
  if (!native && result.provenance?.adapter !== "fixture.calculix") return Promise.resolve(false);
  const card = panel(native ? "네이티브 구조해석 · 전체 절점 변위" : "같은 해석의 메시와 절점 변위", "NATIVE FEA FIELD · SAME RECORD"); card.classList.add("detail-wide", "fixture-field-card");
  const choices = el("div", undefined, "button-row fixture-field-choices"), detail = el("div", undefined, "fixture-field-detail"); card.append(choices, detail); container.append(card);
  const request = state.experimentRequest, store = activeStore(); let sequence = 0, mounted = null;
  const current = () => card.isConnected && detail.isConnected && request === state.experimentRequest && store === activeStore()
    && !state.storeSwitching && state.selectedExperiment === inspection;
  let record;
  try {
    if (!window.fixtureFieldControls || !window.fixtureFieldViewer) throw new Error("FEA 필드 표시 모듈을 불러올 수 없습니다.");
    record = window.fixtureFieldControls.catalog(inspection);
    if (!record.entries.length) { detail.append(el("p", record.reason, "empty-state")); return Promise.resolve(false); }
  } catch (error) { if (current()) detail.append(el("p", error.message, "metric-reason")); return Promise.resolve(false); }
  const label = el("label", native ? "선택한 해석 메시" : "해석 메시 레벨"), select = el("select"); label.append(select); choices.append(label);
  record.entries.forEach((entry, i) => option(select, String(i), `${entry.size_mm} mm · 원본 레벨 ${entry.index}`)); select.value = String(record.entries.length - 1);
  async function selectField() {
    if (!current()) return false; const epoch = ++sequence, entry = record.entries[Number(select.value)];
    const selected = () => current() && epoch === sequence;
    mounted?.destroy(); if (state.fixtureViewer === mounted) state.fixtureViewer = null; mounted = null;
    if (state.selectedFieldObservation?.inspection === inspection) { state.selectedFieldObservation = null; observationResponseNote(); updateControls(); }
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
      if (!selected()) return false;
      if (native && model.metadata.family !== "native") throw new Error("네이티브 구조해석 전체장 계약을 확인할 수 없습니다.");
      if (!selected()) return false; mounted = window.fixtureFieldViewer.mount(detail, model, selected,
        selection => prepareFieldObservation(inspection, model, selection, selected)); if (!mounted || !selected()) { mounted?.destroy(); return false; }
      state.fixtureViewer = mounted;
      const downloads = el("div", undefined, "button-row separated"); downloads.append(link("전체 절점 U JSON", artifactUrl(result.experiment_id, entry.path), "text-link", true));
      mounted.refs.provenance.append(el("p", native ? "CAD 문서 전역 좌표계 · 저장된 전체 U · 지정 성분 구속과 합력. 실제 사용 승인은 결과 판정을 따릅니다."
        : "해석에 사용한 실제 메시·고정·하중과 저장된 전체 U를 확인합니다. 이 관측은 정확도·강도·실물 사용 승인이 아닙니다.", "hint"));
      if (native) {
        const prescribed = model.rawNative.prescribed_dofs, loads = model.rawNative.loads;
        const dofs = el("details", undefined, "advanced"), forces = el("details", undefined, "advanced");
        dofs.append(el("summary", `실제 지정 변위 · ${prescribed.length}개 DOF`), table(["절점", "지정 성분", "변위 (mm)"],
          prescribed.slice(0, 50).map(row => [row.node_id, [null, "UX", "UY", "UZ"][row.component], number(row.value_mm)])));
        forces.append(el("summary", `실제 절점 하중 · ${loads.length}개 성분`), table(["절점", "하중 성분", "하중 (N)"],
          loads.slice(0, 50).map(row => [row.node_id, [null, "FX", "FY", "FZ"][row.component], number(row.force_N)])));
        if (prescribed.length > 50 || loads.length > 50) forces.append(el("p", "각 목록의 첫 50개를 표시합니다. 전체 성분·값은 원본 U JSON에 보존되어 있습니다.", "hint"));
        mounted.refs.provenance.append(dofs, forces);
      }
      const prefix = entry.path.slice(0, entry.path.lastIndexOf("/") + 1);
      Object.values(model.field.sources).forEach(source => downloads.append(link(source.path, artifactUrl(result.experiment_id, prefix + source.path), "text-link artifact-path", true))); mounted.refs.provenance.append(downloads);
      return true;
    } catch (error) { if (selected()) clear(detail).append(el("p", error.message, "metric-reason")); return false; }
  }
  select.addEventListener("change", () => { void selectField(); }); choices.append(action("필드 다시 불러오기", selectField, "button secondary compact"));
  return selectField();
}

function renderAssemblyFields(container, inspection) {
  const result = inspection.result, card = el('section', undefined, 'result-card fixture-field-card');
  const detail = el('div'), controls = el('div', undefined, 'button-row');
  card.append(el('h2','조립체 전체 결과장'), el('p','원본 7부품의 절점·요소·XYZ와 실제 변위·반력을 연결합니다. Gauss 응력을 절점 응력으로 바꾸지 않습니다.','hint'),controls,detail);
  container.append(card);
  const request = state.experimentRequest, store = activeStore(); let mounted = null, sequence = 0;
  const current = () => request === state.experimentRequest && store === activeStore() && !state.storeSwitching &&
    state.selectedExperiment === inspection && card.isConnected && detail.isConnected;
  async function read() {
    const epoch = ++sequence, selected = () => current() && sequence === epoch;
    mounted?.destroy(); if (state.fixtureViewer === mounted) state.fixtureViewer = null; mounted = null;
    if (state.selectedFieldObservation?.inspection === inspection) { state.selectedFieldObservation = null; observationResponseNote(); updateControls(); }
    clear(detail).append(el('p','동일 기록의 전체 필드·원본 메시와 native ID 연결을 확인하고 있습니다…','hint'));
    try {
      const envelope = await api(`/api/response-fields/${idPath(result.experiment_id)}`);
      if (!selected()) return false;
      const model = window.fixtureFieldControls.verifyAssemblyField(inspection, envelope);
      if (!selected()) return false;
      mounted = window.fixtureFieldViewer.mount(detail, model, selected,
        selection => prepareFieldObservation(inspection, model, selection, selected));
      if (!mounted || !selected()) { mounted?.destroy(); return false; }
      state.fixtureViewer = mounted;
      const fields = model.field;
      mounted.refs.provenance.append(el('p',`보존 메시 ${fields.mesh_revision} · ${fields.initial_state === 'NOT_STORED' ? '초기 하중 0 상태는 native에 저장되지 않았습니다.' : 'native에 저장한 초기 상태를 보존합니다.'}`,'hint'));
      mounted.refs.provenance.append(el('p','표시는 원 TRIA6에서 유도한 4개 선형 삼각형입니다. 다른 부품의 같은 좌표 절점을 합치지 않으며 원 TETRA10 연결과 전체 native Gauss tensors는 원본 파일에 남습니다.','hint'));
      mounted.refs.provenance.append(table(['부품','전체 절점','체적 요소','원 표면','Gauss 위치','native 에너지 상태'],
        fields.bodies.map(body=>[body.component_id,body.node_count,body.element_count,body.boundary_face_count,body.gauss_count,body.native_energy?.status ?? 'UNKNOWN'])));
      const downloads = el('div',undefined,'button-row separated');
      downloads.append(link('전체 U/RF·Gauss 원본',artifactUrl(result.experiment_id,model.artifact.path),'text-link',true),
        link('native MED 결과',artifactUrl(result.experiment_id,'simulation/native/fields.med'),'text-link',true));
      mounted.refs.provenance.append(downloads);
      return true;
    } catch(error) { if (selected()) clear(detail).append(el('p',error.message,'metric-reason')); return false; }
  }
  controls.append(action('전체 결과 필드 불러오기',read,'button secondary compact'));
  detail.append(el('p','버튼으로 이 기록의 전체 변위장을 엽니다. 실패·미수렴 기록의 원자료와 실행 기록은 상세 기록에 보존됩니다.','hint'));
  return Promise.resolve(true);
}
function renderNativeFeFields(container, inspection) {
  const result = inspection.result, card = el("section",undefined,"result-card fixture-field-card");
  const controls = el("div",undefined,"button-row"), detail = el("div");
  card.append(el("p","NATIVE FE · SAME RECORD","eyebrow"),el("h2","시각별 전체 절점·적분점 결과"),
    el("p","변위·반력은 원 절점, 응력·소성변형률은 원 적분점에 표시합니다. 메시·시각·원 성분을 선택하고 같은 위치의 관측과 비교할 수 있습니다.","hint"),controls,detail);
  container.append(card);
  const request = state.experimentRequest, store = activeStore(); let loadSequence=0, renderSequence=0;
  const current = ()=>request === state.experimentRequest && store === activeStore() && state.selectedExperiment === inspection && card.isConnected && !state.storeSwitching;
  const names={"DEPL.DX":"변위 X (mm)","DEPL.DY":"변위 Y (mm)","DEPL.DZ":"변위 Z (mm)",
    "REAC_NODA.DX":"절점 반력 X (N)","REAC_NODA.DY":"절점 반력 Y (N)","REAC_NODA.DZ":"절점 반력 Z (N)",
    "SIEF_ELGA.SIXX":"적분점 응력 XX (MPa)","SIEF_ELGA.SIYY":"적분점 응력 YY (MPa)","SIEF_ELGA.SIZZ":"적분점 응력 ZZ (MPa)",
    "SIEF_ELGA.SIXY":"적분점 응력 XY (MPa)","SIEF_ELGA.SIXZ":"적분점 응력 XZ (MPa)","SIEF_ELGA.SIYZ":"적분점 응력 YZ (MPa)","VARI_ELGA.V1":"적분점 등가 소성변형률 (1)"};
  const resetSelection=()=> {
    if (state.selectedFieldObservation?.family !== "fe" || state.selectedFieldObservation.inspection !== inspection) return;
    state.selectedFieldObservation=null;
    [...$("observationResponse").options].filter(o=>o.dataset.fieldObservation).forEach(o=>o.remove());
    observationResponseNote(); updateControls();
  };
  async function read() {
    const epoch=++loadSequence, active=()=>current()&&epoch===loadSequence;
    resetSelection(); clear(detail).append(el("p","같은 결과의 FE 원본과 전체 이력을 확인하고 있습니다…","hint"));
    try {
      const envelope=await api(`/api/response-fields/${idPath(result.experiment_id)}`);
      if (!active()) return;
      const catalog=window.nativeFeFieldInspector.catalog(inspection,envelope);
      clear(controls); const meshLabel=el("label","메시"), mesh=el("select"); meshLabel.append(mesh); controls.append(meshLabel);
      catalog.meshes.forEach(entry=>option(mesh,String(entry.mesh_index),`${entry.mesh_size_mm} mm · ${entry.times_s.length}개 원 시각`));
      mesh.value=String(catalog.meshes[catalog.meshes.length-1].mesh_index);
      async function chooseMesh() {
        const fieldEpoch=++loadSequence, selected=()=>current()&&fieldEpoch===loadSequence;
        resetSelection(); clear(detail).append(el("p","선택한 원본 필드의 크기·해시·전체 point 연결을 확인하고 있습니다…","hint"));
        try {
          const entry=catalog.meshes.find(m=>m.mesh_index===Number(mesh.value));
          const fetchBytes=async(relative,expectedBytes)=> {
            if (!selected()) throw new Error("선택한 실험 또는 메시가 바뀌었습니다.");
            const response=await fetch(artifactUrl(result.experiment_id,relative),{cache:"no-store",headers:{Accept:"application/octet-stream"}});
            if (!selected() || !response.ok) throw new Error("원 FE 파일을 읽을 수 없습니다.");
            const length=response.headers.get("Content-Length");
            if (length!==null && Number(length)!==expectedBytes) throw new Error("원 FE 파일 크기가 다릅니다.");
            return new Uint8Array(await response.arrayBuffer());
          };
          const field=await window.nativeFeFieldInspector.loadField(inspection,envelope,entry,fetchBytes,selected);
          if (!selected()) return;
          clear(detail); const toolbar=el("div",undefined,"button-row"), timeLabel=el("label","원 해석 시각"), time=el("select"), componentLabel=el("label","결과 성분"),component=el("select");
          field.raw.states.forEach((s,i)=>option(time,String(i),`${number(s.time_s)} s · order ${s.actual_result_order}${i===0 ? " · 초기 상태" : ""}`));
          time.value=String(field.raw.states.length-1); timeLabel.append(time);
          field.components.forEach(c=>option(component,c,names[c]??c)); component.value="SIEF_ELGA.SIXX"; componentLabel.append(component);
          toolbar.append(timeLabel,componentLabel); detail.append(toolbar);
          const pointLabel=el("label","원 절점 ID 또는 요소/적분점/하위점"),point=el("input"), pointRow=el("div",undefined,"button-row"), context=el("p",undefined,"hint"), valuesHost=el("div",undefined,"table-scroll");
          point.placeholder="절점: 1 / 적분점: 1/1/0"; pointLabel.append(point); pointRow.append(pointLabel); detail.append(pointRow,context,valuesHost);
          let page=0;
          function show() {
            if (!selected()) return; resetSelection(); const drawEpoch=++renderSequence, live=()=>selected()&&drawEpoch===renderSequence;
            const timeIndex=Number(time.value), rows=window.nativeFeFieldInspector.rows(field,timeIndex,component.value),start=page*50;
            clear(valuesHost); context.textContent=`${rows.length}개 원 ${rows[0].kind === "fe_nodal" ? "절점" : "적분점"} · ${names[component.value]} · 모델 전역 XYZ (mm) · ${timeIndex===0 ? "초기 상태 / 새 Newton 증분 아님" : "native 계산 시각"} · 측정 위치·실물 자격 미확인`;
            valuesHost.append(table(["절점 / 요소·적분점","XYZ (mm)",`원 값 (${rows[0].unit})`,"관측 연결"],rows.slice(start,start+50).map((r,i)=>[
              r.kind === "fe_nodal" ? r.native : `${r.native.element_id}/${r.native.point}/${r.native.subpoint}`,
              r.coordinates_mm.map(number).join(" / "),number(r.value),action("이 위치·시각에 관측 연결",()=>prepareFeFieldObservation(inspection,field,
                window.nativeFeFieldInspector.selection(field,timeIndex,component.value,start+i),live),"button secondary compact")])));
            const pages=el("div",undefined,"button-row separated"), prev=action("이전 50개",()=>{page--;show();}),next=action("다음 50개",()=>{page++;show();});
            prev.disabled=page===0; next.disabled=start+50>=rows.length; pages.append(prev,el("span",`${start+1}–${Math.min(start+50,rows.length)} / ${rows.length}`),next); valuesHost.append(pages);
          }
          pointRow.append(action("원 ID로 찾기",()=> {
            const rows=window.nativeFeFieldInspector.rows(field,Number(time.value),component.value),needle=point.value.trim();
            const found=rows.findIndex(r=>needle===(r.kind === "fe_nodal" ? String(r.native) : `${r.native.element_id}/${r.native.point}/${r.native.subpoint}`));
            if (found<0) {notify("현재 메시·성분의 정확한 원 ID를 입력하세요.");return;} page=Math.floor(found/50);show();
          },"button secondary compact"));
          time.addEventListener("change",()=>{page=0;show();});component.addEventListener("change",()=>{page=0;show();});show();
          detail.append(link("선택 메시의 전체 이력 원본",artifactUrl(result.experiment_id,entry.artifact),"text-link",true));
        } catch(error) { if(selected())clear(detail).append(el("p",error.message,"metric-reason")); }
      }
      mesh.addEventListener("change",()=>void chooseMesh()); await chooseMesh();
    } catch(error) { if(current())clear(detail).append(el("p",error.message,"metric-reason")); }
  }
  controls.append(action("원 FE 필드 열기",read,"button secondary"));
  return read();
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
        renderPdeNodes(detail, field, result.experiment_id, inspection, selected);
      } catch (error) { if (selected()) clear(detail).append(el("p", error.message, "metric-reason")); }
    }
    select.addEventListener("change", () => { void selectField(); });
    await selectField();
  }).catch(error => { if (current()) clear(detail).append(el("p", error.message, "metric-reason")); });
}
function renderPdeNodes(container, field, identifier, inspection, current) {
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
  if (inspection && current && writable() && inspection.result.status === "COMPLETED_REVIEW_REQUIRED") {
    container.append(action("이 절점·성분에 관측값 연결", () => {
      const nodeId = Number(input.value);
      if (!input.value.trim() || !Number.isSafeInteger(nodeId) || nodeId < 0 || !field.nodes.some(node=>node.id === nodeId))
        throw new Error("원본 native 절점 ID를 입력하세요. 0도 유효한 절점입니다.");
      preparePdeFieldObservation(inspection,field,nodeId,field.components[Number(component.value)],current);
    },"button secondary compact"));
  }
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
  const current = state.handlerGuards.get(identifier) ?? (() => true);
  try {
    const job = await api(`/api/jobs/${idPath(identifier)}`);
    if (identifier !== state.job?.id) return;
    state.job = job; renderJob();
    if (activeJob(job)) { schedulePoll(); return; }
    await loadOverview({ followJobs: false });
    if (job.operation === "research_run") await loadResearchStatus();
    const handler = state.handlers.get(identifier); state.handlers.delete(identifier); state.handlerGuards.delete(identifier);
    if (job.status === "COMPLETED" && handler) await handler(job.result);
    if (job.status === "FAILED" && current()) { if (job.operation === "research_run") researchError(new Error(text(job.error))); else notify(`작업이 실패했습니다: ${text(job.error)}`); }
    if (job.status === "CANCELLED" && current()) notify("작업 취소가 완료됐습니다. 부분 기록은 보존됩니다.", true);
  } catch (error) {
    if (activeJob(state.job)) {
      $("jobMessage").textContent = state.job?.operation === "research_run" ? "작업 상태 연결을 확인할 수 없습니다. 종료를 단정하지 않고 다시 확인합니다."
        : `상태 연결을 확인할 수 없습니다: ${error.message} · 실행 실패로 단정하지 않고 다시 확인합니다.`; schedulePoll(4000);
    } else if (current() && state.job?.operation === "research_run") researchError(error);
    else if (current()) notify(`작업 상태는 ${labels[state.job?.status] ?? state.job?.status}입니다. 후속 기록 읽기 실패: ${error.message}`);
  }
}
async function runJob(operation, arguments_, handler, current = () => true) {
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
    state.job = job; if (handler) { state.handlers.set(job.id, handler); state.handlerGuards.set(job.id, current); } renderJob();
    if (activeJob(job)) schedulePoll();
    else {
      await loadOverview({ followJobs: false });
      if (operation === "research_run") await loadResearchStatus();
      state.handlers.delete(job.id); state.handlerGuards.delete(job.id);
      if (job.status === "COMPLETED" && handler) await handler(job.result);
      else if (job.status === "FAILED" && current()) { if (operation === "research_run") researchError(new Error(text(job.error))); else notify(text(job.error)); }
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
  invalidateAnalysisConditions();
  withdrawFixedCad();
  withdrawCampaignConditions(); state.campaignRequest++;
  let overview;
  try { overview = await api("/api/store", { method: "POST", body: JSON.stringify({ id: identifier }) }); }
  catch (error) {
    state.overview = null; state.studyId = ""; state.study = null; state.registry = { entries: [] }; clearSimulationDraft();
    throw error;
  }
  finally { state.storeSwitching = false; updateControls(); }
  state.overview = overview; state.studyId = ""; state.study = null; state.registry = { entries: [] }; state.discovery = []; clearSimulationDraft();
  state.nativeImportRequest++; state.nativeFileSelection++; $("nativeImportFile").value = "";
  $("nativeImportFileState").textContent = "FCStd 파일 하나를 선택하세요. 원본은 별도로 보존합니다.";
  $("nativeModelId").value = ""; clear("nativeDetail"); clear("nativeFinal");
  state.researchSession = null; $("researchContinue").checked = false; renderResearchAnswers();
  invalidateModelDiscovery(); state.campaignSelections.clear(); state.campaignSelectionKey = "";
  state.selectedExperiment = null; state.selectedFieldObservation = null; state.selectedHistories = null; $("historyPanel").hidden = true; state.selectedCampaign = null; state.comparison.clear(); state.studyRequest++; state.experimentRequest++; state.campaignRequest++;
  $("observationPanel").hidden = true; state.observationRequest++;
  clear("campaignDetail"); clear("comparisonDetail").hidden = true;
  const card = panel("저장소가 바뀌었습니다.", "RESULTS"); card.append(el("p", "목록에서 열 기록을 선택하세요.", "empty-state")); clear("experimentDetail").append(card);
  $("selectedSource").textContent = "소스 버전: 기록 선택 후 확인"; renderDiscovery([], { queried: false }); renderOverview();
  await loadNativeImports();
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
}, async (result, args) => { $("cadExperimentId").value = makeId("E-cad"); await inspectExperiment(result.experiment_id ?? args.experiment_id, () => true, null, engineeringWorkspaceEnabled() ? "design" : "results"); });
bindForm("nativeCreateForm", "native_create", () => ({ template: $("nativeTemplate").value }), renderNative);
$("nativeImportForm").addEventListener("submit", event => { event.preventDefault(); submitNativeImport().catch(error => notify(error.message)); });
$("nativeImportFile").addEventListener("change", () => { state.nativeFileSelection++; $("nativeImportFileState").textContent = $("nativeImportFile").files?.length === 1 ? $("nativeImportFile").files[0].name : "FCStd 파일 하나를 선택하세요."; updateControls(); });
bindForm("nativeInspectForm", "native_inspect", () => ({ model: $("nativeModelId").value.trim() }), renderNative);
bindForm("nativeFinalForm", "native_final", () => ({ model: $("nativeModelId").value.trim(), final: $("nativeFinal").value }), renderNative);
bindForm("simulationForm", simulationOperation, simulationArguments, completeSimulation, simulationSubmissionContext);
if (analysisConditionsEnabled()) {
  $("conditionsId").value = makeId("C-conditions"); $("conditionsExperimentId").value = makeId("E-conditions");
  $("conditionsParent").addEventListener("change", () => { invalidateAnalysisConditions(); updateControls(); });
  $("analysisConditionsLoadBtn").addEventListener("click", loadAnalysisConditionsCatalog);
  $("analysisConditionsRefreshBtn").addEventListener("click", refreshAnalysisConditionsList);
  if (additionalBoundariesEnabled()) $("conditionsAddBoundaryBtn").addEventListener("click", addAnalysisBoundary);
  $("analysisConditionsForm").addEventListener("submit", event => { event.preventDefault(); if (event.currentTarget.reportValidity()) saveAnalysisConditions(); });
  $("analysisConditionsRunForm").addEventListener("submit", event => { event.preventDefault(); if (event.currentTarget.reportValidity()) runAnalysisConditions(); });
  document.querySelectorAll("[data-analysis-condition]").forEach(input => input.addEventListener(input.tagName === "SELECT" ? "change" : "input", changeAnalysisConditionsDraft));
  $("conditionsAssemblyFields")?.addEventListener("input", changeAnalysisConditionsDraft);
  $("conditionsExperimentId").addEventListener("input", updateControls);
  $("analysisConditionsNewIdBtn").addEventListener("click", () => {
    if (!writable() || busy()) return;
    $("conditionsId").value = makeId("C-conditions"); changeAnalysisConditionsDraft();
  });
  for (const id of ["cadBackend", "cadModel", "nativeModelId"]) {
    $(id).addEventListener(id === "cadBackend" ? "change" : "input", () => { invalidateAnalysisConditions(); updateControls(); });
  }
}
if (campaignConditionsEnabled()) {
  $("campaignAnalysisSource").addEventListener("change", () => {
    renderCampaignVariables();
    try { applyFixtureCampaignDefaults(); } catch (error) { notify(error.message); }
    updateControls();
  });
  $("campaignUseConditionsBtn").addEventListener("click", () => prepareCampaignConditions(false));
  $("analysisConditionsExploreBtn").addEventListener("click", () => state.analysisConditions.record?.request?.backend === "structure.calculix.native" ? prepareFixedCad(true) : prepareCampaignConditions(true));
}
bindForm("observationForm", "response_comparison_save", observationArguments, completeObservation, observationSubmissionContext);
$("observationResponse").addEventListener("change", changeObservationResponse);
$("observationHistorySample").addEventListener("change", observationResponseNote);
$("historyChannel").addEventListener("change", renderHistoryChannel);
$("historySample").addEventListener("change", renderHistorySample);
$("campaignForm").addEventListener("submit", event => { event.preventDefault(); if (event.currentTarget.reportValidity()) submitCampaignPlan(); });

$("discoverBtn").addEventListener("click", () => runJob("parameter_discover", { backend: $("cadBackend").value, model: $("cadModel").value.trim() }, renderDiscovery).catch((error) => notify(error.message)));
$("registryRefreshBtn").addEventListener("click", () => runJob("registry_refresh", { study_id: state.studyId, backend: $("cadBackend").value, model: $("cadModel").value.trim() }, () => loadStudy(state.studyId)).catch((error) => notify(error.message)));
$("nativePath").addEventListener("change", () => chooseCandidate($("nativePath").value));
$("nativeFinal").addEventListener("change", updateControls); $("nativeModelId").addEventListener("input", updateControls);
$("cadBackend").addEventListener("change", () => { state.discovery = []; renderDiscovery([], { queried: false }); if ($("cadBackend").value === "fixture.cadquery") $("cadModel").value = "roller_support"; else if ($("cadBackend").value === "fixture.assembly") $("cadModel").value = "bending_assembly"; else { $("cadModel").value = $("nativeModelId").value; $("nativeArea").open = true; } renderRegistry(); });
$("cadModel").addEventListener("change", () => { renderDiscovery([], { queried: false }); renderRegistry(); });
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
document.querySelectorAll("[data-pde-field]").forEach(input => { input.addEventListener(input.tagName === "SELECT" ? "change" : "input", changePdeConditions); });
document.querySelectorAll("[data-plasticity-field]").forEach(input => { input.addEventListener(input.tagName === "SELECT" ? "change" : "input", changePlasticityConditions); });
$("simulationSettings").addEventListener("input", () => { loadFixtureConditions(); if (window.pdeControls) loadPdeConditions(); if (window.plasticityControls) loadPlasticityConditions(); updateControls(); });
$("fixtureUseInCampaign").addEventListener("click", () => {
  try {
    const settings = fixtureSimulationSettings();
    if (isModelCampaign()) { $("campaignTarget").value = "cad"; campaignTargetChanged(); }
    if (campaignConditionsEnabled()) $("campaignAnalysisSource").value = "legacy";
    $("campaignAnalysisSettings").value = pretty(settings); $("campaignAnalysis").value = "structural_linear";
    $("campaignAnalysis").dispatchEvent(new Event("change"));
    notify("같은 재료·하중·메시를 새 탐색 계획의 후속 해석 설정에 넣었습니다. 계획을 검토한 뒤 저장하세요.", true);
  } catch (error) { notify(error.message); }
});
$("campaignType").addEventListener("change", campaignMode);
$("campaignTarget").addEventListener("change", campaignTargetChanged);
$("fixedCadUseConditionsBtn").addEventListener("click", () => prepareFixedCad());
$("fixedCadDiscoverBtn").addEventListener("click", discoverFixedCadInputs);
$("fixedCadRegisterForm").addEventListener("submit", registerFixedCadInput);
$("fixedCadInputId").addEventListener("change", () => {
  if (!fixedCadCurrent() || !state.fixedCad.discovery || !$("fixedCadInputId").value) return;
  try { window.fixedCadCampaignControls.selectInput($("fixedCadInputId").value, state.fixedCad.discovery, state.fixedCad.selection, fixedCadElements()); fixedCadError(); }
  catch (error) { fixedCadError(error.message); }
  updateControls();
});
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
$("campaignAnalysis").addEventListener("change", () => { try { applyFixtureCampaignDefaults(); } catch (error) { notify(error.message); } });
$("campaignAnalysisSettings").addEventListener("change", () => { try { applyFixtureCampaignDefaults(); } catch (error) { notify(error.message); } });
$("optimizationConstraints").addEventListener("input", () => { if (!isModelCampaign() && !isFixedCadCampaign()) state.fixtureCampaignEdited.constraints = true; });
$("optimizationConstraints").addEventListener("change", renderConstraintEditor);
$("objectiveDirection").addEventListener("change", objectiveTargetMode);
$("optimizationAddConstraint").addEventListener("click", () => {
  if (!writable() || busy()) return;
  try {
    const constraints = parseField("optimizationConstraints", "array");
    if (constraints.length >= 16) throw new Error("응답 제약은 최대 16개입니다.");
    constraints.push({ source: $("objectiveSource").value, metric: $("objectiveMetric").value.trim(),
      unit: $("objectiveUnit").value.trim(), operator: "<=", limit: null, scale: 1 });
    $("optimizationConstraints").value = pretty(constraints);
    if (!isModelCampaign() && !isFixedCadCampaign()) state.fixtureCampaignEdited.constraints = true;
    renderConstraintEditor();
    $("optimizationConstraintRows").lastElementChild?.querySelector('[data-constraint-field="limit"]')?.focus();
  } catch (error) { notify(error.message); }
});
$("optimizationRequired").addEventListener("input", () => { if (!isModelCampaign() && !isFixedCadCampaign()) state.fixtureCampaignEdited.requirements = true; });
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
initializeEngineeringWorkspace(); showArea(location.hash.slice(1)); updateControls();
Promise.allSettled([loadOverview(), api("/api/presets").then(renderPresets), loadResearchStatus()]).then((results) => {
  results.forEach((result) => { if (result.status === "rejected") notify(result.reason.message); }); updateControls();
});
