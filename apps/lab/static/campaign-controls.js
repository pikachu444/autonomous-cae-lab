"use strict";

// Prepare existing campaign inputs/defaults; Core and the numerical engine own execution.
(function (root) {
  const inputId = /^[A-Za-z][A-Za-z0-9_-]{0,63}$/;
  const storeId = /^[A-Za-z][A-Za-z0-9_-]{0,79}$/;
  const sha256 = /^[0-9a-fA-F]{64}$/;
  const nativeKeys = ["backend", "document", "object", "path", "alias"];
  const candidateKeys = ["native", "label", "unit", "value", "lower", "upper", "source_sha256"];
  const planKeys = ["study_id", "campaign_id", "parameter_ids", "seed", "objective", "constraints",
    "max_generations", "population_size", "initial_values", "required_validations", "engine"];
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  const mapping = (value) => value !== null && typeof value === "object" &&
    (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null);
  const exactKeys = (value, names) => mapping(value) && Object.keys(value).length === names.length && names.every((name) => own(value, name));
  const finite = (value) => typeof value === "number" && Number.isFinite(value);
  const nonempty = (value) => typeof value === "string" && value.trim().length > 0;
  const digest = (value) => typeof value === "string" && sha256.test(value);
  function jsonValue(value, ancestors = new Set()) {
    if (value === null || typeof value === "string" || typeof value === "boolean") return true;
    if (typeof value === "number") return Number.isFinite(value);
    if ((!Array.isArray(value) && !mapping(value)) || ancestors.has(value)) return false;
    const keys = Reflect.ownKeys(value).filter((key) => !(Array.isArray(value) && key === "length"));
    if (keys.some((key) => typeof key !== "string" || !Object.getOwnPropertyDescriptor(value, key).enumerable ||
        !own(Object.getOwnPropertyDescriptor(value, key), "value")) ||
        (Array.isArray(value) && (keys.length !== value.length || keys.some((key, index) => key !== String(index))))) return false;
    ancestors.add(value);
    const valid = keys.every((key) => jsonValue(value[key], ancestors));
    ancestors.delete(value);
    return valid;
  }
  function cloneJson(value) {
    if (Array.isArray(value)) return value.map(cloneJson);
    if (mapping(value)) return Object.fromEntries(Object.keys(value).map((key) => [key, cloneJson(value[key])]));
    return value;
  }
  function validNative(native, backend) {
    return exactKeys(native, nativeKeys) && native.backend === backend && digest(native.document) &&
      native.object === "declared_inputs" && typeof native.path === "string" && inputId.test(native.path) && native.alias === "";
  }
  function validateDiscovery(candidates, backend) {
    if (!nonempty(backend) || !Array.isArray(candidates) || candidates.length < 1 || candidates.length > 32 || !jsonValue(candidates)) {
      throw new Error("선택한 모델의 실제 입력 후보 1~32개가 필요합니다.");
    }
    const paths = new Set();
    let revision, source;
    candidates.forEach((candidate) => {
      if (!exactKeys(candidate, candidateKeys) || !validNative(candidate.native, backend) ||
          !digest(candidate.source_sha256) || !nonempty(candidate.label) || !nonempty(candidate.unit) ||
          !finite(candidate.value) || !finite(candidate.lower) || !finite(candidate.upper) ||
          !(candidate.lower <= candidate.value && candidate.value <= candidate.upper && candidate.lower < candidate.upper) ||
          paths.has(candidate.native.path)) throw new Error("모델 입력 후보의 식별자·단위·범위가 불완전합니다.");
      revision ??= candidate.native.document; source ??= candidate.source_sha256;
      if (candidate.native.document !== revision || candidate.source_sha256 !== source) {
        throw new Error("서로 다른 모델 개정이나 소스의 입력 후보를 섞을 수 없습니다.");
      }
      paths.add(candidate.native.path);
    });
    return candidates;
  }
  function validEntry(entry, backend) {
    return mapping(entry) && jsonValue(entry) && entry.target === "model_analysis" && entry.mode === "free" &&
      entry.kind === "continuous" && mapping(entry.input_effect) && entry.input_effect.status === "PASS" &&
      typeof entry.parameter_id === "string" && inputId.test(entry.parameter_id) && validNative(entry.native, backend) &&
      nonempty(entry.unit) && digest(entry.source_sha256) && entry.model_template_revision === entry.native.document &&
      finite(entry.current_value) && finite(entry.lower_bound) && finite(entry.upper_bound) &&
      entry.lower_bound < entry.upper_bound && entry.lower_bound <= entry.current_value && entry.current_value <= entry.upper_bound &&
      finite(entry.upper_bound - entry.lower_bound) && finite(entry.upper_bound + entry.lower_bound);
  }
  function eligibleModelEntries(entries, candidates, backend) {
    validateDiscovery(candidates, backend);
    if (!Array.isArray(entries)) throw new Error("연구 변수 레지스트리가 필요합니다.");
    const byPath = new Map(candidates.map((candidate) => [candidate.native.path, candidate]));
    return entries.filter((entry) => {
      if (!validEntry(entry, backend)) return false;
      const candidate = byPath.get(entry.native.path);
      return candidate !== undefined && nativeKeys.every((key) => entry.native[key] === candidate.native[key]) &&
        entry.unit === candidate.unit && entry.source_sha256 === candidate.source_sha256 &&
        entry.current_value === candidate.value && entry.model_template_revision === candidate.native.document &&
        entry.lower_bound >= candidate.lower && entry.upper_bound <= candidate.upper;
    });
  }
  function modelPlanArguments(fields, context) {
    if (!exactKeys(fields, planKeys) || !exactKeys(context, ["backend", "settings", "entries"]) ||
        !nonempty(context.backend) || !mapping(context.settings) || !jsonValue(fields) || !jsonValue(context)) {
      throw new Error("모델 최적화 계획에는 기존 API의 입력과 유한한 JSON 데이터만 사용할 수 있습니다.");
    }
    if (typeof fields.study_id !== "string" || !storeId.test(fields.study_id) ||
        typeof fields.campaign_id !== "string" || !storeId.test(fields.campaign_id) || fields.campaign_id.length > 58 ||
        fields.engine !== "scipy.differential_evolution" || !Number.isSafeInteger(fields.seed) || fields.seed < 0 || fields.seed > 2 ** 32 - 1 ||
        !Number.isSafeInteger(fields.max_generations) || fields.max_generations < 1 || fields.max_generations > 100 ||
        !Number.isSafeInteger(fields.population_size) || fields.population_size < 5 || fields.population_size > 64 ||
        fields.population_size * (fields.max_generations + 1) > 512) {
      throw new Error("연구·캠페인 ID, SciPy 엔진, 시드와 기존 실행 예산 범위를 확인하세요.");
    }
    const entries = context.entries;
    if (!Array.isArray(entries) || !entries.length || entries.length > 32 || entries.some((entry) => !validEntry(entry, context.backend)) ||
        new Set(entries.map((entry) => entry.parameter_id)).size !== entries.length ||
        new Set(entries.map((entry) => entry.native.path)).size !== entries.length ||
        entries.some((entry) => entry.native.document !== entries[0].native.document || entry.source_sha256 !== entries[0].source_sha256)) {
      throw new Error("같은 최신 모델에 등록된 연속 자유 변수만 선택할 수 있습니다.");
    }
    const selected = fields.parameter_ids, available = new Map(entries.map((entry) => [entry.parameter_id, entry]));
    if (!Array.isArray(selected) || !selected.length || new Set(selected).size !== selected.length ||
        selected.some((name) => typeof name !== "string" || !available.has(name))) {
      throw new Error("발견·등록된 서로 다른 모델 연구 변수 ID를 선택하세요.");
    }
    const objective = fields.objective;
    validateObjective(objective, ["model"]);
    if (!Array.isArray(fields.constraints) || fields.constraints.length > 16 || fields.constraints.some((constraint) =>
      !exactKeys(constraint, ["source", "metric", "unit", "operator", "limit", "scale"]) || constraint.source !== "model" ||
      !nonempty(constraint.metric) || !nonempty(constraint.unit) || !["<=", ">="].includes(constraint.operator) ||
      !finite(constraint.limit) || !finite(constraint.scale) || constraint.scale <= 0)) {
      throw new Error("제약은 model 지표·단위·비교 연산·유한한 한계와 양수인 정규화 값을 명시해야 합니다.");
    }
    const requirements = fields.required_validations;
    if (!exactKeys(requirements, ["model"]) || !Array.isArray(requirements.model) ||
        requirements.model.some((name) => !nonempty(name)) || new Set(requirements.model).size !== requirements.model.length) {
      throw new Error("필수 수치 검증은 model 배열의 서로 다른 검사 이름으로 지정하세요.");
    }
    const initial = fields.initial_values;
    if (initial !== null && (!exactKeys(initial, selected) || selected.some((name) => !finite(initial[name]) ||
        initial[name] < available.get(name).lower_bound || initial[name] > available.get(name).upper_bound))) {
      throw new Error("초기값은 선택한 모든 변수의 등록 범위 안에 있어야 합니다.");
    }
    return { ...cloneJson(fields), backend: context.backend, settings: cloneJson(context.settings) };
  }
  function validateObjective(objective, sources = ["cad", "analysis", "model"]) {
    if (!mapping(objective) || !jsonValue(objective)) throw new Error("목표에는 유한한 JSON 값만 사용할 수 있습니다.");
    const match = mapping(objective) && objective.direction === "match";
    const keys = ["source", "metric", "unit", "direction", ...(match ? ["target", "scale", "origin", "reference"] : [])];
    if (!exactKeys(objective, keys) || !jsonValue(objective) || !sources.includes(objective.source) ||
        !nonempty(objective.metric) || !nonempty(objective.unit) || !["minimize", "maximize", "match"].includes(objective.direction) ||
        (match && (!finite(objective.target) || !finite(objective.scale) || objective.scale <= 0 ||
          !["DESIGN_TARGET", "MEASURED_REPORTED", "PUBLISHED_REFERENCE", "SYNTHETIC"].includes(objective.origin) ||
          !nonempty(objective.reference) || objective.reference.length > 2048))) {
      throw new Error("응답 출처·지표·정확한 단위를 확인하세요. 목표값 맞추기에는 유한한 목표값, 양수인 정규화 크기와 출처 설명이 필요합니다.");
    }
    return cloneJson(objective);
  }
  function objectiveFromFields(fields) {
    if (!exactKeys(fields, ["source", "metric", "unit", "direction", "target", "scale", "origin", "reference"]) || !jsonValue(fields) ||
        ["source", "metric", "unit", "direction", "reference"].some(key => typeof fields[key] !== "string")) throw new Error("목표 입력 필드를 확인하세요.");
    const objective = { source: fields.source, metric: fields.metric.trim(), unit: fields.unit.trim(), direction: fields.direction };
    if (fields.direction === "match") {
      for (const key of ["target", "scale"]) {
        if (typeof fields[key] !== "string" || !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(fields[key].trim())) throw new Error("목표값과 정규화 크기를 숫자로 입력하세요.");
        objective[key] = Number(fields[key]);
      }
      objective.origin = fields.origin;
      objective.reference = fields.reference.trim();
    }
    return validateObjective(objective);
  }
  function constraintFromFields(fields) {
    if (!exactKeys(fields, ["source", "metric", "unit", "operator", "limit", "scale"]) || !jsonValue(fields) ||
        ["source", "metric", "unit", "operator"].some(key => typeof fields[key] !== "string")) throw new Error("제약 입력 필드를 확인하세요.");
    const value = { source: fields.source, metric: fields.metric.trim(), unit: fields.unit.trim(), operator: fields.operator };
    for (const key of ["limit", "scale"]) {
      if (typeof fields[key] !== "string" || !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(fields[key].trim())) throw new Error("제약의 한계값과 정규화 크기를 숫자로 입력하세요.");
      value[key] = Number(fields[key]);
    }
    if (!["cad", "analysis", "model"].includes(value.source) || !value.metric || !value.unit ||
        !["<=", ">="].includes(value.operator) || !finite(value.limit) || !finite(value.scale) || value.scale <= 0) {
      throw new Error("제약의 응답·단위·한계값과 양수인 정규화 크기를 확인하세요.");
    }
    return value;
  }
  function fixtureOptimizationDefaults(analysisSettings) {
    if (!mapping(analysisSettings) || !jsonValue(analysisSettings) || !own(analysisSettings, "mesh")) {
      throw new Error("기존 지그 해석 설정의 유한한 JSON 메시 선언이 필요합니다.");
    }
    const mesh = analysisSettings.mesh;
    if (!mapping(mesh)) throw new Error("지그 메시 설정을 명시하세요.");
    // The adapter admits only explicit selected; an absent mode retains legacy refinement.
    const selected = own(mesh, "mode");
    if (!exactKeys(mesh, selected ? ["mode", "max_sizes_mm"] : ["max_sizes_mm"]) ||
        (selected && mesh.mode !== "selected")) {
      throw new Error("메시 모드는 selected만 명시할 수 있습니다. 기존 복수 메시 설정에는 mode가 없습니다.");
    }
    const sizes = mesh.max_sizes_mm;
    if (!Array.isArray(sizes) || (selected ? sizes.length !== 1 : sizes.length < 2 || sizes.length > 8) ||
        sizes.some((size) => !finite(size) || size <= 0) ||
        sizes.some((size, index) => index > 0 && sizes[index - 1] <= size)) {
      throw new Error("selected에는 양수 메시 크기 하나, 기존 복수 메시에는 큰 값부터 서로 다른 양수 2~8개가 필요합니다.");
    }
    return {
      meshMode: selected ? "selected" : "refinement",
      objective: { source: "analysis", metric: "max_displacement", unit: "mm", direction: "minimize" },
      objectiveLabel: "하중 안장 절점 최대 |UZ|",
      constraints: selected ? [] : [
        { source: "analysis", metric: "max_displacement", unit: "mm", operator: "<=", limit: 0.0065, scale: 0.0065 },
      ],
      required_validations: { cad: [], analysis: [
        ...(selected ? [] : ["displacement_mesh_trend"]),
        ...sizes.map((_size, index) => `mesh_${index}_reaction_balance`),
      ] },
      note: selected ?
        "선택한 단일 메시의 관측 응답입니다. 메시 민감도는 미평가이며 물리적 허용 변위는 자동으로 설정하지 않습니다." :
        "0.0065 mm는 과거 가상 비교용 기준이며 실제 지그의 허용 변위나 제작 승인이 아닙니다. 기존 메시 추세·반력 검사는 유지합니다.",
    };
  }
  function requireValue(condition, message) { if (!condition) throw new Error(message); }
  function savedCondition(record) {
    requireValue(mapping(record) && jsonValue(record) && typeof record.id === "string" && storeId.test(record.id) &&
      mapping(record.source) && mapping(record.request) && record.request.conditions_id === record.id &&
      record.request.experiment_id === record.source.experiment_id && record.request.cad_revision === record.source.cad_revision &&
      record.request.catalog_revision === record.catalog_revision &&
      [record.source.cad_revision, record.source.result_sha256, record.source.proposal_sha256, record.source.thread_sha256,
        record.conditions_revision, record.catalog_revision].every(digest) &&
      typeof record.source.experiment_id === "string" && storeId.test(record.source.experiment_id) &&
      typeof record.source.study_id === "string" && storeId.test(record.source.study_id) && nonempty(record.source.backend) &&
      mapping(record.request.declaration) && mapping(record.catalog) && record.engineering === "UNKNOWN" && record.decision === "NOT_RELEASED",
    "저장 조건의 CAD·연구·개정·원본 해시와 미승인 상태를 확인할 수 없습니다.");
    requireValue(record.support?.status === "SUPPORTED_DECLARED_INPUTS" && record.support.native_runtime === "NOT_CHECKED" &&
      mapping(record.adapter_binding) && record.adapter_binding.backend === record.request.backend &&
      mapping(record.adapter_binding.settings) && nonempty(record.request.backend),
    "이 모델·조건의 서버 지원 판정이 필요합니다. 다른 설정이나 해석 경로로 대체하지 않습니다.");
    return record;
  }
  function nativeAnchor(entry) {
    return mapping(entry) && mapping(entry.native) && nonempty(entry.native.backend) && nonempty(entry.native.document) &&
      nonempty(entry.native.object) && nonempty(entry.native.path) && digest(entry.source_sha256) && nonempty(entry.unit) &&
      typeof entry.parameter_id === "string" && inputId.test(entry.parameter_id) &&
      entry.mode === "free" && entry.kind === "continuous" && entry.geometry_effect?.status === "PASS";
  }
  function sameAnchor(entry, original) {
    return nativeAnchor(entry) && nativeAnchor(original) && entry.parameter_id === original.parameter_id &&
      entry.source_sha256 === original.source_sha256 && entry.unit === original.unit &&
      JSON.stringify(Object.entries(entry.native).sort()) === JSON.stringify(Object.entries(original.native).sort());
  }
  function conditionContext(selection, context) {
    requireValue(mapping(context) && jsonValue(context) && nonempty(context.store) && Array.isArray(context.entries) &&
      selection.store === context.store && selection.studyId === context.studyId && selection.backend === context.backend &&
      selection.model === context.model && context.studyId === selection.record.source.study_id,
    "저장 조건의 저장소·연구·CAD 모델이 현재 탐색 대상과 다릅니다. 같은 원본 조건을 다시 연결하세요.");
    const eligible = context.entries.filter(entry => selection.sourceEntries.some(original => sameAnchor(entry, original)));
    requireValue(eligible.length > 0, "조건의 원 CAD와 같은 네이티브 문서·소스에 등록된 자유 변수가 필요합니다.");
    return eligible;
  }
  function conditionSelection(record, inspection, context) {
    savedCondition(record);
    requireValue(mapping(inspection) && jsonValue(inspection) && inspection.integrity === "VERIFIED" &&
      mapping(inspection.result) && mapping(inspection.proposal) && mapping(inspection.hashes) &&
      inspection.result.experiment_id === record.source.experiment_id && inspection.result.study?.id === record.source.study_id &&
      inspection.result.cad_revision === record.source.cad_revision && inspection.result.provenance?.adapter === record.source.backend &&
      inspection.result.solver_status === "NOT_RUN" && inspection.result.status === "COMPLETED_REVIEW_REQUIRED" &&
      ["result_sha256", "proposal_sha256", "thread_sha256"].every(key => inspection.hashes[key] === record.source[key]) &&
      inspection.proposal.id === record.source.experiment_id && inspection.proposal.study_id === record.source.study_id &&
      inspection.proposal.model?.geometry?.backend === context?.backend && inspection.proposal.model.geometry.source === context?.model &&
      context?.backend === record.source.backend && context?.studyId === record.source.study_id,
    "조건이 가리키는 VERIFIED 원 CAD의 모델·개정·저장 문서 해시가 현재 선택과 일치해야 합니다.");
    const sourceEntries = listEntries(inspection.registry_snapshot?.entries).filter(entry => nativeAnchor(entry) && entry.native.backend === record.source.backend &&
      mapping(inspection.proposal.parameters) && own(inspection.proposal.parameters, entry.parameter_id));
    requireValue(sourceEntries.length > 0 && new Set(sourceEntries.map(entry => entry.native.document)).size === 1,
      "원 CAD의 등록부에서 하나의 네이티브 모델 문서와 형상 효과를 확인할 수 없습니다.");
    const selection = { store: context.store, studyId: record.source.study_id, backend: context.backend, model: context.model,
      record: cloneJson(record), sourceEntries: cloneJson(sourceEntries) };
    conditionContext(selection, context);
    return selection;
  }
  function listEntries(value) { return Array.isArray(value) ? value : []; }
  function equalJson(left, right) {
    if (Object.is(left, right)) return true;
    if (Array.isArray(left) || Array.isArray(right)) return Array.isArray(left) && Array.isArray(right) &&
      left.length === right.length && left.every((value, index) => equalJson(value, right[index]));
    return mapping(left) && mapping(right) && Object.keys(left).length === Object.keys(right).length &&
      Object.keys(left).every(key => own(right, key) && equalJson(left[key], right[key]));
  }
  function conditionPlanArguments(selection, context, parameterIds) {
    requireValue(mapping(selection) && jsonValue(selection) && Array.isArray(selection.sourceEntries), "현재 검증한 저장 조건을 먼저 연결하세요.");
    const record = savedCondition(selection.record), entries = conditionContext(selection, context);
    requireValue(Array.isArray(parameterIds) && parameterIds.length > 0 && new Set(parameterIds).size === parameterIds.length &&
      parameterIds.every(name => entries.some(entry => entry.parameter_id === name)),
    "원 CAD와 같은 네이티브 문서·소스에서 등록된 자유 변수만 선택할 수 있습니다.");
    // Core performs Domain admission and exact selection rebinding for each new revision.
    return { conditions_id: record.id, analysis_backend: record.request.backend };
  }
  function conditionTemplate(plan) {
    if (mapping(plan) && jsonValue(plan) && plan.route === "fixed_cad_analysis") {
      if (typeof root.fixedCadCampaignControls?.frozenPlan !== "function") {
        throw new Error("고정 CAD 조건 계획을 읽을 입력 검증 도구가 로드되지 않았습니다.");
      }
      return root.fixedCadCampaignControls.frozenPlan(plan);
    }
    requireValue(mapping(plan) && jsonValue(plan) && mapping(plan.analysis) && mapping(plan.analysis.conditions_template),
      "이 계획에는 고정한 저장 CAD 조건이 없습니다.");
    const template = plan.analysis.conditions_template, reference = template.reference, record = savedCondition(template.record);
    requireValue(template.rebind_policy === "REVISION_REBIND_EXACT_SELECTIONS" && mapping(reference) && reference.id === record.id &&
      reference.revision === record.conditions_revision && reference.catalog_revision === record.catalog_revision &&
      digest(reference.record_sha256) && digest(template.record_canonical_sha256) && reference.scope === "USER_DECLARED_UNVERIFIED" &&
      plan.study_id === record.source.study_id && plan.backend === record.source.backend &&
      plan.analysis.backend === record.request.backend && equalJson(plan.analysis.settings, record.adapter_binding.settings),
    "고정한 조건 참조·연구·CAD 경로와 정확한 선택 재연결 정책이 일치하지 않습니다.");
    return template;
  }
  const api = { validateObjective, objectiveFromFields, constraintFromFields, validateDiscovery, eligibleModelEntries, modelPlanArguments, fixtureOptimizationDefaults,
    conditionSelection, conditionPlanArguments, conditionTemplate };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.campaignControls = api;
})(typeof window !== "undefined" ? window : globalThis);
