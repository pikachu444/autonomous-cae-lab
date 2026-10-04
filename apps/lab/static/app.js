"use strict";

// Human controls over the allowlisted Core API. All record text is untrusted.
const $ = (id) => document.getElementById(id);
const state = {
  overview: null, presets: {}, studyId: "", study: null, registry: { entries: [] },
  discovery: [], job: null, submitting: false, pollTimer: null, handlers: new Map(),
  selectedExperiment: null, selectedCampaign: null, comparison: new Set(), studyRequest: 0,
  experimentRequest: 0, campaignRequest: 0, viewer: null, fixtureConditionError: null,
  modelDiscovery: [], modelContext: "", modelRequest: 0,
  importedLevels: [], importedMeshError: null, importedRequest: 0, importedLoading: false,
  campaignSelections: new Map(), campaignSelectionKey: "", campaignDrafts: {}, campaignTarget: "cad", cadCampaignType: "doe",
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
};
const readOperations = new Set(["parameter_discover", "native_inspect", "model_parameters_discover"]);
const labels = {
  PASS: "PASS · 통과", FAIL: "FAIL · 실패", UNKNOWN: "UNKNOWN · 미검증", WARNING: "WARNING · 검토",
  NOT_RELEASED: "NOT_RELEASED · 승인 없음", RELEASED: "RELEASED", VERIFIED: "VERIFIED · 해시 확인",
  NOT_CHECKED: "NOT_CHECKED · 미확인", IMPLEMENTED: "구현됨", EXPERIMENTAL: "실험 범위", PLANNED: "계획됨",
  RUNNING: "실행 중", CANCEL_REQUESTED: "취소 처리 중", CANCELLED: "취소 완료",
  CLEANUP_PENDING: "종료 확인 중",
  COMPLETED: "실행 완료", FAILED: "작업 실패", REJECTED: "검증 거절",
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
  return el("span", override ?? labels[code] ?? code, `badge ${kind}`);
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
function busy() { return state.submitting || activeJob(state.job); }
function available(operation) {
  const matching = list(state.overview?.capabilities).filter((item) => item.operation === operation);
  return !matching.length || matching.some((item) => item.callable === true);
}
function option(select, value, label) { const item = el("option", label); item.value = value; select.append(item); }
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
  $("storeSelect").disabled = busy() || !state.overview;
  $("studySelect").disabled = busy() || !state.overview;
  $("useLocalBtn").disabled = busy();
  const needStudy = ["discoverBtn", "registryRefreshBtn", "simulationRunBtn", "campaignPlanBtn"];
  needStudy.forEach((id) => { if (!state.studyId) $(id).disabled = true; });
  if (!selectedEntries().length) {
    document.querySelector('[data-operation="cad_run"]').disabled = true;
    $("registryRefreshBtn").disabled = true;
  }
  if (!$("nativePath").value || !state.studyId) document.querySelector('[data-operation="parameter_register"]').disabled = true;
  if (!$("nativeFinal").value || !$("nativeModelId").value.trim()) document.querySelector('[data-operation="native_final"]').disabled = true;
  if (!state.presets[$("simulationPreset").value] || ($("simulationPreset").value === "structural_linear" && !$("analysisParent").value)) $("simulationRunBtn").disabled = true;
  if (!$("fixtureConditionFields").hidden && state.fixtureConditionError) $("simulationRunBtn").disabled = true;
  if (!$("importedMeshFields").hidden && (state.importedMeshError || state.importedLoading)) $("simulationRunBtn").disabled = true;
  $("fixtureUseInCampaign").disabled = !writable() || busy() || Boolean(state.fixtureConditionError);
  if (!document.querySelector("[data-campaign-variable]:checked")) $("campaignPlanBtn").disabled = true;
  $("modelDiscoverBtn").disabled = busy() || !state.overview || !state.presets[$("modelCampaignPreset").value]?.declared_inputs || !available("model_parameters_discover");
  if (!state.studyId || !currentModelDiscovery() || !$("modelInputId").value) $("modelRegisterBtn").disabled = true;
  if (isModelCampaign() && !currentModelDiscovery()) $("campaignPlanBtn").disabled = true;
  $("compareBtn").disabled = state.comparison.size < 2;
  $("compareCount").textContent = `${state.comparison.size}개 선택 · 최대 12개`;
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
    ["탐색 계획", list(overview.campaigns).length, "DOE · 수치 최적화"], ["실행 중", list(overview.jobs).filter(activeJob).length, "동시에 한 작업"]].forEach(([label, value, caption]) => {
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
  const oldParent = $("analysisParent").value;
  const parents = clear("analysisParent"); option(parents, "", "완료한 CAD 실험을 선택하세요");
  list(overview.experiments).filter((record) => record.status === "COMPLETED_REVIEW_REQUIRED" && record.cad_revision && /^fixture\./.test(record.backend ?? "") && record.solver_status === "NOT_RUN")
    .forEach((record) => option(parents, record.id, `${record.id} · ${record.study_id}`));
  parents.value = [...parents.options].some((item) => item.value === oldParent) ? oldParent : "";
  renderExperimentList(); renderCampaignList(); updateControls();
}
async function loadOverview({ followJobs = true } = {}) {
  try {
    state.overview = await api("/api/overview");
    $("connectionState").textContent = "로컬 서버 연결됨 · 목록은 미확인 상태이며 기록을 열 때 해시를 검증합니다.";
    $("connectionState").classList.remove("offline");
    renderOverview();
    if (state.studyId) await loadStudy(state.studyId); else renderStudy();
    if (followJobs) {
      const running = list(state.overview.jobs).find(activeJob);
      if (running) { state.job = running; renderJob(); schedulePoll(); }
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
    $("studySelect").value = identifier; renderStudy(); renderRegistry();
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
  renderCampaignVariables(); updateControls();
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
  $("campaignAnalysis").options[1].disabled = !structural;
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
  updateControls();
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
  container.append(table(["비교", "실험 / 연구", "Backend", "실행 상태", "출시 판정", "기록 검사", ""], records.map((row) => {
    const select = el("input"); select.type = "checkbox"; select.checked = state.comparison.has(row.id); select.setAttribute("aria-label", `${row.id} 비교 선택`);
    select.addEventListener("change", () => {
      if (select.checked && state.comparison.size >= 12) { select.checked = false; notify("한 번에 최대 12개 실험을 비교할 수 있습니다."); return; }
      if (select.checked) state.comparison.add(row.id); else state.comparison.delete(row.id); updateControls();
    });
    const identifier = el("div"); identifier.append(experimentButton(row.id), el("small", row.study_id));
    if (row.error) identifier.append(el("small", text(row.error), "metric-reason"));
    return [select, identifier, el("span", row.backend ?? "—", "mono"), badge(row.status), badge(row.decision ?? "UNKNOWN"), badge(row.integrity ?? "NOT_CHECKED"), action("열기", () => inspectExperiment(row.id))];
  })));
  updateControls();
}
async function inspectExperiment(identifier) {
  location.hash = "results"; const request = ++state.experimentRequest, store = activeStore();
  state.selectedExperiment = null;
  const loading = panel("기록과 산출물을 확인하고 있습니다.", "VERIFYING INTEGRITY"); loading.append(el("p", identifier, "mono separated")); clear("experimentDetail").append(loading);
  $("selectedSource").textContent = "소스 버전: 검증 중";
  try {
    const data = await api(`/api/experiments/${idPath(identifier)}`);
    if (request !== state.experimentRequest || store !== activeStore()) return;
    if (data.integrity !== "VERIFIED") throw new Error("서버가 이 기록의 검증 완료를 확인하지 않았습니다.");
    state.selectedExperiment = data; renderExperimentDetail(data);
  } catch (error) {
    if (request !== state.experimentRequest) return;
    const card = panel("기록을 검증할 수 없습니다.", "INTEGRITY CHECK FAILED"); card.classList.add("detail-error"); card.append(el("p", error.message), el("p", "확인되지 않은 수치와 원본 파일을 신뢰한 결과로 표시하지 않습니다."));
    clear("experimentDetail").append(card); $("selectedSource").textContent = "소스 버전: 확인 불가"; throw error;
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
function renderExperimentDetail(data) {
  const result = data.result, summary = data.summary, identifier = result.experiment_id;
  const container = clear("experimentDetail");
  const header = panel(identifier, "VERIFIED EXPERIMENT"); header.classList.add("result-header");
  const verdicts = el("div", undefined, "status-title separated"); verdicts.append(badge(result.status), badge(data.integrity), badge(result.decision)); header.append(verdicts);
  const meta = el("div", undefined, "result-meta");
  [ ["연구", result.study?.id ?? result.study?.study_id], ["솔버", result.solver_status], ["수치 수렴", result.converged === null ? "미해당" : result.converged === true ? "확인됨" : "미확인 / 미수렴"], ["부모", result.parent_experiment_id] ].forEach(([title, value]) => { if (value !== undefined) { const item = el("span", `${title}: `); item.append(el("strong", value)); meta.append(item); } });
  header.append(meta);
  const explanation = el("div", undefined, "result-explanation"); explanation.append(badge(result.decision), el("p", result.decision === "NOT_RELEASED" ? `미검증 요구사항 ${list(summary?.unknown).length}개와 독립 검증 상태를 확인하세요. 실행 완료와 솔버 종료 코드는 강도·물리·출시 승인이 아닙니다.` : "출시 판정의 근거와 모든 독립 검증을 함께 확인하세요.")); header.append(explanation);
  const downloads = el("div", undefined, "button-row separated");
  downloads.append(link("검증된 HTML 보고서", `/api/report/${idPath(identifier)}.html`, "button secondary compact"), link("보고서 JSON", `/api/report/${idPath(identifier)}.json`, "button subtle compact", true), link("근거 묶음 ZIP", `/api/report/${idPath(identifier)}.zip`, "button primary compact", true)); header.append(downloads);
  header.append(el("p", "ZIP은 원본과 부모 연결을 보존하는 로컬 내보내기입니다. 원격 보관·서명·물리 검증을 대신하지 않습니다.", "hint separated")); container.append(header);
  const detailGrid = el("div", undefined, "detail-grid");
  const metrics = panel("단위와 유효성", "NUMERICAL METRICS"); metrics.append(table(["Metric", "값 / 단위", "유효성"], Object.entries(result.metrics ?? {}).map(([name, metric]) => [el("span", name, "mono"), metricCell(metric), badge(metric.valid === true ? "PASS" : "FAIL", metric.valid === true ? "수치 응답 유효" : "INVALID")])));
  if (!Object.keys(result.metrics ?? {}).length) metrics.append(el("p", "이 실험은 사용할 수 있는 수치 metric을 제공하지 않았습니다.", "empty-state"));
  const inputs = panel("같은 개정의 입력", "INPUTS & MODEL"); inputs.append(rawDetail("연구 변수 입력", result.input_parameters), rawDetail("명시한 모델·하중·검증 설정", data.proposal));
  if (result.parent_experiment_id) inputs.append(experimentButton(result.parent_experiment_id, "부모 CAD 실험 열기 →"));
  detailGrid.append(metrics, inputs); container.append(detailGrid);
  const validation = panel("독립 검증 상태", "VALIDATIONS"); validation.classList.add("detail-wide");
  validation.append(table(["검증", "상태", "범위", "관찰 / 한계 / 근거"], list(result.validations).map((item) => {
    const label = el("div", item.type, "validation-type"); label.append(el("small", item.validator));
    const detail = el("div"); detail.append(el("span", text(item.notes ?? item.observed ?? item.expected ?? item.threshold), "hint"), rawDetail("검증 레코드", item));
    return [label, badge(item.status), item.blocking ? "승인을 차단하는 검증" : "보조 검증", detail];
  }))); container.append(validation);
  const evidenceGrid = el("div", undefined, "detail-grid");
  const evidence = panel("판정의 바탕이 된 관찰", "EVIDENCE");
  list(result.evidence).forEach((item) => {
    const card = el("div", undefined, "evidence-card"); card.append(el("h3", item.id), el("p", `${item.type} · ${text(item.method)}`), el("pre", pretty(item.observation)), el("p", `출처: ${text(item.source)}`, "hint"));
    if (typeof item.artifact === "string" && list(result.artifacts).some((artifact) => artifact.path === item.artifact)) card.append(link(item.artifact, artifactUrl(identifier, item.artifact), "text-link artifact-path", true));
    else card.append(el("p", `원본 참조: ${text(item.artifact)}`, "hint"));
    evidence.append(card);
  });
  if (!list(result.evidence).length) evidence.append(el("p", "이 기록에 제공된 evidence가 없습니다.", "empty-state"));
  const visual = panel("같은 실험의 형상", "VERIFIED ARTIFACT PREVIEW");
  const image = list(result.artifacts).find((item) => /\.(png|jpe?g|webp)$/i.test(item.path));
  if (image) {
    const picture = el("img"); picture.className = "preview-image"; picture.src = artifactUrl(identifier, image.path); picture.alt = `${identifier}의 검증된 CAD 미리보기`; picture.loading = "lazy";
    picture.addEventListener("error", () => { picture.hidden = true; visual.append(el("p", "미리보기 파일을 다시 검증해 불러올 수 없습니다. 원본 산출물 목록을 확인하세요.", "metric-reason")); });
    visual.append(picture, el("p", image.path, "preview-caption"));
  } else visual.append(el("p", "이 실험에 manifest로 등록된 이미지가 없습니다. 아래의 원본 CAD·메시·field 파일을 내려받아 확인하세요.", "empty-state"));
  const surface = list(result.artifacts).find((item) => /(?:^|\/)surface\.json$/.test(item.path));
  if (surface) visual.append(action("원본 FreeCAD surface viewer 열기", () => openSurface(visual, identifier, surface.path)));
  visual.append(el("p", "네이티브 3D surface는 같은 실험의 검증된 파일로 엽니다. 치구의 진단용 응력 성분은 아래 원본 연결 표에서 확인합니다.", "hint separated"));
  evidenceGrid.append(evidence, visual); container.append(evidenceGrid);
  renderFixtureStressFields(container, result);
  renderContactFields(container, data);
  renderPdeFields(container, data);
  const artifacts = panel("원본과 처리한 산출물", "ARTIFACTS · VERIFIED BY HASH"); artifacts.classList.add("detail-wide");
  artifacts.append(table(["파일", "크기", "SHA-256", "개정"], list(result.artifacts).map((item) => {
    const digest = el("div", item.sha256, "mono"); return [link(item.path, artifactUrl(identifier, item.path), "artifact-path", true), `${number(item.size_bytes)} bytes`, digest, el("span", item.revision, "mono")];
  }))); container.append(artifacts);
  const provenance = panel("소스와 실행 개정", "PROVENANCE");
  const source = result.provenance ?? {}; const sourceGrid = el("div", undefined, "source-grid separated");
  [["Core commit", source.core_commit], ["Core 변경 상태", source.core_dirty === true ? "기록 시 로컬 변경 있음" : source.core_dirty === false ? "기록 시 clean" : "미기록 / 미확인"], ["Source commit", source.source_commit], ["Core source SHA", source.core_source_sha256], ["CAD revision", result.cad_revision], ["Model revision", result.model_revision ?? result.extensions?.pde?.model_revision], ["Adapter / version", `${text(source.adapter)} / ${text(source.adapter_version)}`]].forEach(([label, value]) => sourceGrid.append(el("span", label), el("div", text(value), "mono")));
  provenance.append(sourceGrid, rawDetail("전체 provenance · thread · result", { provenance: source, thread: data.thread, result })); container.append(provenance);
  const commit = source.core_commit ?? source.source_commit;
  $("selectedSource").textContent = commit ? `소스 ${String(commit).slice(0, 12)}${source.core_dirty ? " · 로컬 변경 있음" : ""}` : "소스 버전: 이 기록에 미제공";
  $("selectedSource").title = text(commit);
  if (result.status === "COMPLETED_REVIEW_REQUIRED" && result.cad_revision && result.solver_status === "NOT_RUN") $("analysisParent").value = identifier;
  updateControls();
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
let viewerScript;
async function openSurface(container, identifier, path) {
  const surface = await api(artifactUrl(identifier, path));
  if (!Array.isArray(surface.bounds) || surface.bounds.length !== 2 || !Array.isArray(surface.faces)) throw new Error("원본 viewer가 읽을 수 있는 surface artifact가 아닙니다.");
  if (!window.createFaceViewer) {
    viewerScript ??= new Promise((resolve, reject) => { const script = document.createElement("script"); script.src = "/upstream/surface_viewer.js"; script.addEventListener("load", resolve); script.addEventListener("error", () => reject(new Error("원본 surface viewer를 불러올 수 없습니다."))); document.head.append(script); });
    await viewerScript;
  }
  const canvas = el("canvas"); canvas.className = "preview-canvas"; canvas.setAttribute("aria-label", "원본 FreeCAD 표면 · 드래그 회전, 휠 확대, 클릭 면 확인");
  const selection = el("p", "드래그로 회전 · 휠로 확대 · 면을 클릭해 원본 face ID 확인", "preview-caption"); container.append(canvas, selection);
  const viewer = window.createFaceViewer(canvas, (face) => { selection.textContent = face ? `원본 face ${face.id} · ${text(face.type ?? face.surface)}` : "선택된 면 없음"; }); viewer.setData(surface); state.viewer = viewer;
}
async function compareExperiments() {
  if (state.comparison.size < 2) return;
  const data = await api(`/api/compare?${new URLSearchParams({ ids: [...state.comparison].join(",") })}`);
  const records = list(data.comparison ?? data.results ?? data); const container = clear("comparisonDetail"); container.hidden = false;
  const card = panel("검증된 기록 비교", "COMPARE · VALIDITY RETAINED"); card.classList.add("compare-card");
  card.append(el("p", "단위와 유효성을 함께 읽으세요. INVALID 값은 성능 우열이나 최적 후보의 근거로 사용할 수 없습니다.", "hint separated"));
  const names = new Set(records.flatMap((record) => Object.keys(record.metrics ?? {})));
  const rows = [["실행 상태", ...records.map((record) => badge(record.status))], ["출시 판정", ...records.map((record) => badge(record.decision))], ["연구 변수", ...records.map((record) => el("span", text(record.parameters), "mono"))], ["UNKNOWN", ...records.map((record) => el("span", list(record.unknown).join(", "), "hint"))]];
  names.forEach((name) => rows.push([el("span", name, "mono"), ...records.map((record) => metricCell(record.metrics?.[name]))]));
  card.append(table(["응답", ...records.map((record) => record.experiment_id)], rows), action("비교 닫기", () => { container.hidden = true; })); container.append(card);
}

function renderJob() {
  const job = state.job; if (!job) { $("jobPanel").hidden = true; return; }
  $("jobPanel").hidden = false; $("jobPanel").classList.toggle("finished", job.status === "COMPLETED"); $("jobPanel").classList.toggle("failed", job.status === "FAILED");
  $("jobTitle").textContent = operationNames[job.operation] ?? job.operation;
  const marker = badge(job.status); $("jobStatus").className = marker.className; $("jobStatus").textContent = marker.textContent;
  $("jobMessage").textContent = job.status === "RUNNING" ? "서버에서 실행 중입니다. 하나의 작업만 실행하며, 완료 또는 실패 상태를 계속 확인합니다."
    : job.status === "CANCEL_REQUESTED" ? "취소를 요청했습니다. 실행 중인 단계가 중단 요청을 처리하는 동안 상태를 계속 확인합니다."
    : job.status === "CLEANUP_PENDING" ? "솔버 종료가 확인되지 않았습니다. 다음 작업은 차단됩니다. 취소 버튼으로 같은 작업의 종료를 다시 요청할 수 있습니다."
    : job.status === "CANCELLED" ? "작업이 중단 요청을 처리했습니다. 부분 로그와 실험 기록은 결과 목록에 보존됩니다. 수치 검증은 결과 기록에서 확인하세요."
    : job.status === "FAILED" ? `실행 실패: ${text(job.error)} · 부분 기록이 있으면 결과 목록에서 확인하세요.` : "작업이 끝났습니다. 실제 결과의 수치·CAD 검증과 미검증 항목은 기록에서 확인하세요.";
  $("jobCancelBtn").hidden = !activeJob(job);
  $("jobCancelBtn").disabled = job.status === "CANCEL_REQUESTED";
  $("jobCancelBtn").textContent = job.status === "CLEANUP_PENDING" ? "종료 재시도" : "작업 취소";
  $("jobJson").textContent = pretty(job); updateControls();
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
    const handler = state.handlers.get(identifier); state.handlers.delete(identifier);
    if (job.status === "COMPLETED" && handler) await handler(job.result);
    if (job.status === "FAILED") notify(`작업이 실패했습니다: ${text(job.error)}`);
    if (job.status === "CANCELLED") notify("작업 취소가 완료됐습니다. 부분 기록은 보존됩니다.", true);
  } catch (error) {
    if (activeJob(state.job)) {
      $("jobMessage").textContent = `상태 연결을 확인할 수 없습니다: ${error.message} · 실행 실패로 단정하지 않고 다시 확인합니다.`; schedulePoll(4000);
    } else notify(`작업 상태는 ${labels[state.job?.status] ?? state.job?.status}입니다. 후속 기록 읽기 실패: ${error.message}`);
  }
}
async function runJob(operation, arguments_, handler) {
  if (!writable() && !readOperations.has(operation)) throw new Error("읽기 전용 라이브러리에서는 새 작업을 실행할 수 없습니다. 작업 저장소로 전환하세요.");
  if (busy()) throw new Error("이미 실행 중인 작업이 있습니다. 종료 상태를 확인한 뒤 다음 작업을 시작하세요.");
  if (!available(operation)) throw new Error("이 작업은 현재 실행 가능한 capability로 제공되지 않습니다.");
  state.submitting = true; updateControls();
  try {
    const body = operation === "pde_run" && arguments_.backend === "pde.fenicsx.imported"
      ? window.importedMeshControls.requestBody(operation, arguments_) : JSON.stringify({ operation, arguments: arguments_ });
    const job = await api("/api/jobs", { method: "POST", body });
    state.job = job; if (handler) state.handlers.set(job.id, handler); renderJob();
    if (activeJob(job)) schedulePoll();
    else {
      await loadOverview({ followJobs: false });
      if (job.status === "COMPLETED" && handler) { state.handlers.delete(job.id); await handler(job.result); }
      else if (job.status === "FAILED") notify(text(job.error));
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
    else await loadOverview({ followJobs: false });
  } catch (error) {
    notify(`취소 요청을 확인할 수 없습니다: ${error.message}`);
    renderJob(); schedulePoll();
  }
});
function bindForm(id, operation, build, handler) {
  $(id).addEventListener("submit", async (event) => {
    event.preventDefault(); if (!event.currentTarget.reportValidity()) return;
    try { const args = build(); await runJob(typeof operation === "function" ? operation() : operation, args, (result) => handler?.(result, args)); }
    catch (error) { notify(error.message); }
  });
}
async function switchStore(identifier) {
  if (busy()) throw new Error("작업 실행 중에는 저장소를 바꿀 수 없습니다.");
  const overview = await api("/api/store", { method: "POST", body: JSON.stringify({ id: identifier }) });
  state.overview = overview; state.studyId = ""; state.study = null; state.registry = { entries: [] }; state.discovery = [];
  invalidateModelDiscovery(); state.campaignSelections.clear(); state.campaignSelectionKey = "";
  state.selectedExperiment = null; state.selectedCampaign = null; state.comparison.clear(); state.studyRequest++; state.experimentRequest++; state.campaignRequest++;
  clear("campaignDetail"); clear("comparisonDetail").hidden = true;
  const card = panel("저장소가 바뀌었습니다.", "RESULTS"); card.append(el("p", "목록에서 열 기록을 선택하세요.", "empty-state")); clear("experimentDetail").append(card);
  $("selectedSource").textContent = "소스 버전: 기록 선택 후 확인"; renderDiscovery([]); renderOverview();
  if (state.studyId) await loadStudy(state.studyId); else { renderStudy(); renderRegistry(); }
}

// Exact Core keyword arguments are assembled here; no commands or file paths.
bindForm("studyForm", "study_create", () => ({ study_id: $("studyId").value.trim(), name: $("studyName").value.trim(), research_question: $("studyQuestion").value.trim(), hypothesis: $("studyHypothesis").value.trim(), objective: $("studyObjective").value.trim() }), async (_result, args) => {
  await loadStudy(args.study_id); $("studyId").value = makeId("S"); notify("연구가 기록되었습니다. 설계에서 실제 변수를 연결하세요.", true);
});
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
bindForm("simulationForm", simulationOperation, () => {
  const preset = state.presets[$("simulationPreset").value], operation = simulationOperation();
  const args = { experiment_id: $("simulationId").value.trim(), backend: preset.backend, settings: fixtureSimulationSettings() };
  if (operation === "analysis_run") args.parent_experiment_id = $("analysisParent").value;
  else args.study_id = state.studyId;
  return args;
}, async (result, args) => { $("simulationId").value = makeId("E-solve"); await inspectExperiment(result.experiment_id ?? args.experiment_id); });
bindForm("campaignForm", campaignOperation, () => {
  const model = isModelCampaign();
  const args = { study_id: state.studyId, campaign_id: $("campaignId").value.trim(), parameter_ids: [...document.querySelectorAll("[data-campaign-variable]:checked")].map((input) => input.value), seed: numeric("campaignSeed") };
  if (!model) { args.backend = $("cadBackend").value; args.model = $("cadModel").value.trim(); }
  if (!args.parameter_ids.length) throw new Error("등록된 자유 변수를 하나 이상 선택하세요.");
  if (!model && $("campaignAnalysis").value) { args.analysis_backend = state.presets.structural_linear.backend; args.analysis_settings = parseField("campaignAnalysisSettings", "object"); }
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
$("cadBackend").addEventListener("change", () => { state.discovery = []; renderDiscovery([]); if ($("cadBackend").value === "fixture.cadquery") $("cadModel").value = "roller_support"; else { $("cadModel").value = $("nativeModelId").value; $("nativeArea").open = true; } renderRegistry(); });
$("cadModel").addEventListener("change", () => { renderDiscovery([]); renderRegistry(); });
$("studySelect").addEventListener("change", () => {
  state.studyId = $("studySelect").value; state.study = null; state.registry = { entries: [] };
  renderDiscovery([]); invalidateModelDiscovery(); renderRegistry(); loadStudy(state.studyId).catch((error) => notify(error.message));
});
$("storeSelect").addEventListener("change", () => switchStore($("storeSelect").value).catch((error) => { $("storeSelect").value = activeStore(); notify(error.message); }));
$("useLocalBtn").addEventListener("click", () => switchStore("local").catch((error) => notify(error.message)));
$("refreshBtn").addEventListener("click", () => loadOverview().catch((error) => notify(error.message)));
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
Promise.allSettled([loadOverview(), api("/api/presets").then(renderPresets)]).then((results) => {
  results.forEach((result) => { if (result.status === "rejected") notify(result.reason.message); }); updateControls();
});
