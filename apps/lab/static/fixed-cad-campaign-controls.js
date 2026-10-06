"use strict";

// Human preparation only. Core verifies hashes/admission; the existing engine generates candidates.
(function (root) {
  const common = typeof module !== "undefined" && module.exports ? require("./campaign-controls.js") : null;
  const solver = "structure.calculix.native";
  const id = /^[A-Za-z][A-Za-z0-9_-]{0,63}$/;
  const storeId = /^[A-Za-z][A-Za-z0-9_-]{0,79}$/;
  const sha = /^[0-9a-f]{64}$/;
  const decimal = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
  const nativeKeys = ["backend", "document", "object", "path", "alias"];
  const descriptorKeys = ["id", "label", "unit", "value", "lower", "upper", "declaration_path"];
  const candidateKeys = ["native", "label", "unit", "value", "lower", "upper", "source_sha256"];
  const planKeys = ["study_id", "campaign_id", "conditions_id", "parameter_ids", "objective", "constraints", "seed",
    "max_generations", "population_size", "initial_values", "required_validations", "engine"];
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  const mapping = value => value !== null && typeof value === "object" &&
    (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null);
  const exact = (value, names) => mapping(value) && Object.keys(value).length === names.length && names.every(key => own(value, key));
  const finite = value => typeof value === "number" && Number.isFinite(value);
  const text = value => typeof value === "string" && value.trim().length > 0;
  const digest = value => typeof value === "string" && sha.test(value);
  const identity = (value, pattern = storeId) => typeof value === "string" && pattern.test(value);
  function requireValue(condition, message) { if (!condition) throw new Error(message); }
  function json(value, seen = new Set()) {
    if (value === null || typeof value === "string" || typeof value === "boolean") return true;
    if (typeof value === "number") return Number.isFinite(value);
    if ((!Array.isArray(value) && !mapping(value)) || seen.has(value)) return false;
    const keys = Reflect.ownKeys(value).filter(key => !(Array.isArray(value) && key === "length"));
    if (keys.some(key => typeof key !== "string" || ["__proto__", "prototype", "constructor"].includes(key) ||
        !Object.getOwnPropertyDescriptor(value, key).enumerable || !own(Object.getOwnPropertyDescriptor(value, key), "value")) ||
        (Array.isArray(value) && (keys.length !== value.length || keys.some((key, index) => key !== String(index))))) return false;
    seen.add(value); const valid = keys.every(key => json(value[key], seen)); seen.delete(value); return valid;
  }
  function clone(value) {
    if (Array.isArray(value)) return value.map(clone);
    if (mapping(value)) return Object.fromEntries(Object.keys(value).map(key => [key, clone(value[key])]));
    return value;
  }
  function equal(left, right) {
    if (Object.is(left, right)) return true;
    if (Array.isArray(left) || Array.isArray(right)) return Array.isArray(left) && Array.isArray(right) &&
      left.length === right.length && left.every((value, index) => equal(value, right[index]));
    return mapping(left) && mapping(right) && Object.keys(left).length === Object.keys(right).length &&
      Object.keys(left).every(key => own(right, key) && equal(left[key], right[key]));
  }
  function source(value) {
    return mapping(value) && identity(value.experiment_id) && identity(value.study_id) && value.backend === "fixture.freecad" &&
      [value.cad_revision, value.result_sha256, value.proposal_sha256, value.thread_sha256].every(digest);
  }
  function savedRecord(record) {
    requireValue(mapping(record) && json(record) && identity(record.id) && source(record.source) &&
      mapping(record.request) && record.request.conditions_id === record.id && record.request.experiment_id === record.source.experiment_id &&
      record.request.cad_revision === record.source.cad_revision && record.request.catalog_revision === record.catalog_revision &&
      [record.conditions_revision, record.catalog_revision].every(digest) && record.request.backend === solver &&
      record.support?.status === "SUPPORTED_DECLARED_INPUTS" && record.support.native_runtime === "NOT_CHECKED" &&
      record.engineering === "UNKNOWN" && record.decision === "NOT_RELEASED" && mapping(record.adapter_binding) &&
      record.adapter_binding.backend === solver && text(record.adapter_binding.version) && mapping(record.adapter_binding.settings) &&
      digest(record.adapter_binding.policy_sha256) && mapping(record.catalog),
    "지원되는 native 단일 솔리드의 저장 조건과 원 CAD 개정을 먼저 연결하세요.");
    const declaration = record.request.declaration, regions = record.catalog.selections;
    requireValue(mapping(declaration) && Array.isArray(regions) && new Set(regions.map(item => item?.id)).size === regions.length &&
      declaration.analysis_type === "linear_static" && declaration.coordinate_system === "global" &&
      equal(declaration.units, { length: "mm", force: "N", stress: "MPa" }) &&
      Array.isArray(declaration.materials) && declaration.materials.length === 1 &&
      Array.isArray(declaration.loads) && declaration.loads.length > 0 &&
      Array.isArray(declaration.boundary_conditions) && declaration.boundary_conditions.length > 0 &&
      declaration.contact?.mode === "none" && declaration.mesh?.mode === "selected" &&
      finite(declaration.mesh.max_size_mm) && declaration.mesh.max_size_mm > 0,
    "고정할 재료·native 면·좌표계·하중·변위 경계·단일 메시 선언을 확인할 수 없습니다.");
    const regionFor = (selection, role, kind) => regions.some(item => mapping(item) && item.id === selection && item.kind === kind &&
      Array.isArray(item.roles) && item.roles.includes(role) && (kind !== "native_face" ||
        /^Face[1-9][0-9]*$/.test(item.native_name ?? "") && /^F-[0-9a-f]{64}-Face[1-9][0-9]*$/.test(item.id) &&
        item.body_id === "B-final" && item.coordinate_system === "global" && item.native_coordinate_system === "cad_document_global"));
    const material = declaration.materials[0];
    requireValue(mapping(material) && material.selection_id === "B-final" && regionFor(material.selection_id, "material", "whole_final_solid") &&
      material.law === "isotropic_linear_elastic" && finite(material.young_modulus_MPa) && finite(material.poisson_ratio) &&
      mapping(material.source) && text(material.source.description) &&
      ["ASSUMED", "MEASURED_REPORTED", "PUBLISHED_REFERENCE"].includes(material.source.category) &&
      declaration.boundary_conditions.every(item => mapping(item) && identity(item.id) && item.type === "displacement" &&
        regionFor(item.selection_id, "boundary", "native_face") && item.coordinate_system === "global" && item.unit === "mm" &&
        mapping(item.components) && Object.keys(item.components).length > 0 &&
        Object.keys(item.components).every(key => ["UX", "UY", "UZ"].includes(key) && finite(item.components[key])) && text(item.source)) &&
      declaration.loads.every(item => mapping(item) && identity(item.id) && item.type === "resultant_force" &&
        regionFor(item.selection_id, "load", "native_face") && item.coordinate_system === "global" && item.unit === "N" &&
        exact(item.components, ["FX", "FY", "FZ"]) && Object.values(item.components).every(finite) && text(item.source)),
    "재료의 최종 솔리드와 저장된 native 면·성분이 일치하지 않습니다.");
    return record;
  }
  function selection(record, inspection, context) {
    savedRecord(record);
    requireValue(mapping(context) && json(context) && text(context.store) && context.studyId === record.source.study_id &&
      context.backend === record.source.backend && text(context.model) && mapping(inspection) && json(inspection) &&
      inspection.integrity === "VERIFIED" && mapping(inspection.result) && mapping(inspection.proposal) && mapping(inspection.hashes) &&
      inspection.result.experiment_id === record.source.experiment_id && inspection.result.study?.id === record.source.study_id &&
      inspection.result.cad_revision === record.source.cad_revision && inspection.result.provenance?.adapter === record.source.backend &&
      inspection.result.status === "COMPLETED_REVIEW_REQUIRED" && inspection.result.solver_status === "NOT_RUN" &&
      inspection.result.decision === "NOT_RELEASED" && ["result_sha256", "proposal_sha256", "thread_sha256"].every(key =>
        inspection.hashes[key] === record.source[key]) && inspection.proposal.id === record.source.experiment_id &&
      inspection.proposal.study_id === record.source.study_id && inspection.proposal.model?.geometry?.backend === context.backend &&
      inspection.proposal.model.geometry.source === context.model,
    "저장 조건의 VERIFIED 원 CAD·연구·모델·문서 해시가 현재 선택과 일치해야 합니다.");
    // No CAD design-variable registry is needed: this route retains this exact parent.
    return { store: context.store, studyId: context.studyId, backend: context.backend, model: context.model,
      parentIntegrity: "VERIFIED", record: clone(record) };
  }
  function selected(value) {
    requireValue(mapping(value) && json(value) && text(value.store) && text(value.model) && value.parentIntegrity === "VERIFIED" &&
      value.studyId === value.record?.source?.study_id && value.backend === value.record?.source?.backend,
    "고정 CAD와 조건을 다시 연결하세요.");
    savedRecord(value.record); return value;
  }
  function sameContext(value, context) {
    try {
      const item = selected(value), record = item.record;
      return mapping(context) && json(context) && context.store === item.store && context.studyId === item.studyId &&
        context.backend === item.backend && context.model === item.model && context.conditionsId === record.id &&
        context.conditionsRevision === record.conditions_revision && context.cadRevision === record.source.cad_revision &&
        context.catalogRevision === record.catalog_revision;
    } catch { return false; }
  }
  function contextKey(value) {
    const item = selected(value), record = item.record;
    return JSON.stringify([item.store, item.studyId, item.backend, item.model, record.id, record.conditions_revision,
      record.catalog_revision, record.source.cad_revision, record.source.result_sha256, record.source.proposal_sha256, record.source.thread_sha256]);
  }
  function scalarAt(declaration, path) {
    requireValue(Array.isArray(path) && ((path.length === 3 && path[0] === "materials" &&
      ["young_modulus_MPa", "poisson_ratio"].includes(path[2])) ||
      (path.length === 4 && path[0] === "loads" && path[2] === "components" && ["FX", "FY", "FZ"].includes(path[3]))) &&
      Number.isSafeInteger(path[1]) && path[1] >= 0,
    "서버가 광고한 E·ν·선언 하중 성분만 연구 변수로 등록할 수 있습니다.");
    let value = declaration;
    for (const key of path) {
      requireValue(value !== null && typeof value === "object" && own(value, key), "광고한 입력의 원 선언 위치가 없습니다.");
      value = value[key];
    }
    return value;
  }
  function validateTemplate(payload, record) {
    savedRecord(record);
    requireValue(mapping(payload) && json(payload) && payload.backend === solver && equal(payload.source, record.source) &&
      payload.conditions_id === record.id && payload.conditions_revision === record.conditions_revision &&
      payload.catalog_revision === record.catalog_revision && digest(payload.template_revision) &&
      digest(payload.condition_input_descriptors_sha256) && payload.rebind_policy === "FIXED_CAD_NO_REBIND" &&
      equal(payload.record, record) && mapping(payload.reference) && payload.reference.id === record.id &&
      payload.reference.revision === record.conditions_revision && payload.reference.catalog_revision === record.catalog_revision &&
      payload.reference.scope === "USER_DECLARED_UNVERIFIED" && digest(payload.reference.record_sha256) &&
      mapping(payload.fingerprint) && payload.fingerprint.backend === solver && payload.fingerprint.version === record.adapter_binding.version &&
      payload.fingerprint.projection_policy_sha256 === record.adapter_binding.policy_sha256 && mapping(payload.fingerprint.input_policy) &&
      Object.keys(payload.fingerprint.input_policy).length > 0 && Object.values(payload.fingerprint.input_policy).every(digest),
    "입력 발견의 CAD·C0·catalog·template·소스 핀이 연결한 저장 조건과 다릅니다.");
    const descriptors = payload.descriptors, candidates = payload.candidates;
    requireValue(Array.isArray(descriptors) && descriptors.length >= 1 && descriptors.length <= 32 &&
      Array.isArray(candidates) && candidates.length === descriptors.length,
    "서버가 광고한 서로 다른 조건 입력 1~32개가 필요합니다.");
    const ids = new Set(), paths = new Set();
    descriptors.forEach(descriptor => {
      requireValue(exact(descriptor, descriptorKeys) && identity(descriptor.id, id) && text(descriptor.label) && text(descriptor.unit) &&
        [descriptor.value, descriptor.lower, descriptor.upper].every(finite) && descriptor.lower < descriptor.upper &&
        descriptor.lower <= descriptor.value && descriptor.value <= descriptor.upper && !ids.has(descriptor.id) &&
        Object.is(scalarAt(record.request.declaration, descriptor.declaration_path), descriptor.value),
      "광고한 입력 ID·값·범위와 고정된 원 선언이 일치하지 않습니다.");
      const expectedUnit = descriptor.declaration_path[0] === "loads" ? "N" : descriptor.declaration_path[2] === "poisson_ratio" ? "1" : "MPa";
      const path = JSON.stringify(descriptor.declaration_path);
      requireValue(descriptor.unit === expectedUnit && !paths.has(path), "입력 단위 또는 선언 위치가 중복되거나 다릅니다.");
      ids.add(descriptor.id); paths.add(path);
    });
    const candidateIds = new Set();
    candidates.forEach(candidate => {
      const descriptor = descriptors.find(item => item.id === candidate?.native?.path);
      requireValue(exact(candidate, candidateKeys) && exact(candidate.native, nativeKeys) && descriptor &&
        candidate.native.backend === solver && candidate.native.object === "analysis_conditions" &&
        candidate.native.document === payload.template_revision && candidate.native.alias === "" &&
        candidate.source_sha256 === payload.template_revision && !candidateIds.has(candidate.native.path) &&
        ["label", "unit", "value", "lower", "upper"].every(key => Object.is(candidate[key], descriptor[key])),
      "조건 입력 Candidate의 native ID·template·값·단위·범위가 서버 광고와 다릅니다.");
      candidateIds.add(candidate.native.path);
    });
    return payload;
  }
  function validateDiscovery(payload, value) { return validateTemplate(payload, selected(value).record); }
  function eligibleEntries(entries, discovery, value) {
    validateDiscovery(discovery, value);
    requireValue(Array.isArray(entries), "현재 연구 변수 등록부가 필요합니다.");
    return entries.filter(entry => {
      if (!mapping(entry) || !json(entry) || entry.target !== "analysis_conditions" || entry.mode !== "free" || entry.kind !== "continuous" ||
          entry.input_effect?.status !== "PASS" || !identity(entry.parameter_id, id) || !text(entry.display_name) ||
          entry.conditions_id !== discovery.conditions_id || entry.conditions_template_revision !== discovery.template_revision ||
          entry.condition_input_descriptors_sha256 !== discovery.condition_input_descriptors_sha256 ||
          entry.source_sha256 !== discovery.template_revision || !exact(entry.native, nativeKeys) ||
          entry.native.backend !== solver || entry.native.object !== "analysis_conditions" || entry.native.alias !== "" ||
          entry.native.document !== discovery.template_revision) return false;
      const candidate = discovery.candidates.find(item => item.native.path === entry.native.path);
      return Boolean(candidate && entry.unit === candidate.unit && Object.is(entry.current_value, candidate.value) &&
        [entry.lower_bound, entry.upper_bound].every(finite) && entry.lower_bound < entry.upper_bound &&
        entry.lower_bound >= candidate.lower && entry.upper_bound <= candidate.upper &&
        entry.lower_bound <= entry.current_value && entry.current_value <= entry.upper_bound &&
        finite(entry.upper_bound - entry.lower_bound) && finite(entry.upper_bound + entry.lower_bound));
    });
  }
  function registerArguments(fields, discovery, value) {
    const item = selected(value); validateDiscovery(discovery, item);
    requireValue(exact(fields, ["input_id", "parameter_id", "display_name", "lower", "upper", "mode"]) && json(fields) &&
      identity(fields.parameter_id, id) && text(fields.display_name) && fields.mode === "free", "입력·변수 ID·표시 이름과 자유 변수 범위를 입력하세요.");
    const descriptor = discovery.descriptors.find(entry => entry.id === fields.input_id);
    requireValue(descriptor && finite(fields.lower) && finite(fields.upper) && fields.lower < fields.upper &&
      fields.lower >= descriptor.lower && fields.upper <= descriptor.upper &&
      fields.lower <= descriptor.value && descriptor.value <= fields.upper &&
      finite(fields.upper - fields.lower) && finite(fields.upper + fields.lower),
    "하한·상한은 원 값을 포함하는 서버 광고 범위 안의 유한한 구간이어야 합니다.");
    return { study_id: item.studyId, conditions_id: item.record.id, ...clone(fields), display_name: fields.display_name.trim() };
  }
  function planArguments(fields, context) {
    requireValue(exact(fields, planKeys) && json(fields) && mapping(context) && json(context), "고정 CAD 조건 최적화의 명시적 계획 입력이 필요합니다.");
    const item = selected(context.selection), entries = eligibleEntries(context.entries, context.discovery, item);
    requireValue(fields.study_id === item.studyId && fields.conditions_id === item.record.id && identity(fields.campaign_id) &&
      fields.campaign_id.length <= 58 && fields.engine === "scipy.differential_evolution" &&
      Number.isSafeInteger(fields.seed) && fields.seed >= 0 && fields.seed <= 2 ** 32 - 1 &&
      Number.isSafeInteger(fields.max_generations) && fields.max_generations >= 1 && fields.max_generations <= 100 &&
      Number.isSafeInteger(fields.population_size) && fields.population_size >= 5 && fields.population_size <= 64 &&
      fields.population_size * (fields.max_generations + 1) <= 512,
    "같은 연구·C0, 새 캠페인 ID, SciPy DE 시드와 기존 실행 예산을 확인하세요.");
    requireValue(Array.isArray(fields.parameter_ids) && fields.parameter_ids.length > 0 && fields.parameter_ids.length <= 32 &&
      new Set(fields.parameter_ids).size === fields.parameter_ids.length && fields.parameter_ids.every(name => identity(name, id) &&
        entries.filter(entry => entry.parameter_id === name).length === 1) &&
      new Set(fields.parameter_ids.map(name => entries.find(entry => entry.parameter_id === name).native.path)).size === fields.parameter_ids.length,
    "같은 C0·template에서 등록한 서로 다른 연속 자유 변수를 선택하세요.");
    (common ?? root.campaignControls).validateObjective(fields.objective, ["analysis"]);
    requireValue(fields.objective.metric === "max_displacement" && fields.objective.unit === "mm" &&
      Array.isArray(fields.constraints) && fields.constraints.length <= 16 && fields.constraints.every(constraint =>
        exact(constraint, ["source", "metric", "unit", "operator", "limit", "scale"]) && constraint.source === "analysis" &&
        constraint.metric === "max_displacement" && constraint.unit === "mm" && ["<=", ">="].includes(constraint.operator) &&
        finite(constraint.limit) && finite(constraint.scale) && constraint.scale > 0) && fields.initial_values === null &&
      exact(fields.required_validations, ["cad", "analysis"]) && Array.isArray(fields.required_validations.cad) &&
      Array.isArray(fields.required_validations.analysis) && fields.required_validations.cad.length === 0 && fields.required_validations.analysis.length === 0,
    "이 경로는 전체 솔리드 최대 |U| (mm)의 목표·제약, 빈 필수 검사와 초기값 null을 명시합니다.");
    return clone(fields);
  }
  function frozenPlan(plan) {
    requireValue(mapping(plan) && json(plan) && plan.route === "fixed_cad_analysis" && mapping(plan.fixed_cad), "이 계획에는 고정 CAD 조건 template이 없습니다.");
    const template = plan.fixed_cad; validateTemplate(template, template.record);
    requireValue(plan.study_id === template.source.study_id, "고정 계획의 연구와 원 CAD 조건이 다릅니다.");
    return template;
  }
  function scalarText(value) { return Object.is(value, -0) ? "-0" : String(value); }
  function inputSummary(descriptor) {
    requireValue(exact(descriptor, descriptorKeys) && json(descriptor), "광고된 입력을 선택하세요.");
    return `${descriptor.label} · 현재 ${scalarText(descriptor.value)} ${descriptor.unit} · 등록 가능 ${scalarText(descriptor.lower)} … ${scalarText(descriptor.upper)} ${descriptor.unit}`;
  }
  function populateInputs(discovery, value, elements) {
    validateDiscovery(discovery, value);
    const select = elements.input, document = select?.ownerDocument;
    requireValue(document && typeof document.createElement === "function" && typeof select.replaceChildren === "function", "입력 선택 화면을 찾을 수 없습니다.");
    const previous = select.value, options = [];
    const placeholder = document.createElement("option"); placeholder.value = ""; placeholder.textContent = "변경할 재료값·하중 성분을 선택하세요"; options.push(placeholder);
    discovery.descriptors.forEach(descriptor => {
      const option = document.createElement("option"); option.value = descriptor.id;
      option.textContent = `${descriptor.label} · ${scalarText(descriptor.value)} ${descriptor.unit}`; options.push(option);
    });
    select.replaceChildren(...options);
    select.value = discovery.descriptors.some(item => item.id === previous) ? previous : "";
    // A refresh never overwrites the user's registration draft.
    if (elements.summary) elements.summary.textContent = select.value ? inputSummary(discovery.descriptors.find(item => item.id === select.value)) :
      "입력을 선택하면 원 값·단위·등록 가능한 수치 범위가 나타납니다.";
  }
  function selectInput(inputId, discovery, value, elements) {
    validateDiscovery(discovery, value);
    const descriptor = discovery.descriptors.find(item => item.id === inputId);
    requireValue(descriptor, "광고된 조건 입력을 선택하세요.");
    elements.parameterId.value = descriptor.id; elements.displayName.value = descriptor.label;
    elements.lower.value = scalarText(descriptor.lower); elements.upper.value = scalarText(descriptor.upper);
    if (elements.summary) elements.summary.textContent = inputSummary(descriptor);
    return descriptor;
  }
  function readRegistration(elements) {
    const number = input => {
      const value = input?.value;
      requireValue(typeof value === "string" && decimal.test(value.trim()) && Number.isFinite(Number(value)), "하한·상한은 유한한 십진수로 입력하세요.");
      return Number(value);
    };
    return { input_id: elements.input.value, parameter_id: elements.parameterId.value.trim(), display_name: elements.displayName.value.trim(),
      lower: number(elements.lower), upper: number(elements.upper), mode: "free" };
  }
  const api = { selection, sameContext, contextKey, validateDiscovery, eligibleEntries, registerArguments, planArguments,
    frozenPlan, inputSummary, populateInputs, selectInput, readRegistration };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.fixedCadCampaignControls = api;
})(typeof window !== "undefined" ? window : globalThis);
