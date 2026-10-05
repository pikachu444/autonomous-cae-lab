"use strict";

// Draft an interpretation question from verified saved comparisons only.
// Core summaries remain authoritative; no provider, session or execution here.
(function (root) {
  const safeId = /^[A-Za-z][A-Za-z0-9_-]{0,79}$/;
  const sha256 = /^[0-9a-f]{64}$/;
  const dangerous = new Set(["__proto__", "prototype", "constructor"]);
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  const mapping = (value) => value !== null && typeof value === "object" &&
    (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null);
  const has = (value, keys) => mapping(value) && keys.every((key) => own(value, key));
  const exact = (value, keys) => has(value, keys) && Object.keys(value).length === keys.length;
  const finite = (value) => typeof value === "number" && Number.isFinite(value);
  const text = (value, maximum = Infinity) => typeof value === "string" && value.trim().length > 0 && value.length <= maximum;
  const id = (value) => typeof value === "string" && safeId.exec(value)?.[0] === value;
  const digest = (value) => typeof value === "string" && value.length === 64 && sha256.test(value);
  const ordinal = (value) => Number.isSafeInteger(value) && value >= 0;
  function requireValue(condition, message) { if (!condition) throw new Error(message); }
  function jsonValue(value, ancestors = new Set()) {
    if (value === null || typeof value === "string" || typeof value === "boolean") return true;
    if (typeof value === "number") return Number.isFinite(value);
    if ((!Array.isArray(value) && !mapping(value)) || ancestors.has(value)) return false;
    const keys = Reflect.ownKeys(value).filter((key) => !(Array.isArray(value) && key === "length"));
    if (keys.some((key) => {
      const descriptor = Object.getOwnPropertyDescriptor(value, key);
      return typeof key !== "string" || dangerous.has(key) || !descriptor.enumerable || !own(descriptor, "value");
    }) || (Array.isArray(value) && (keys.length !== value.length || keys.some((key, index) => key !== String(index))))) return false;
    ancestors.add(value);
    const valid = keys.every((key) => jsonValue(value[key], ancestors));
    ancestors.delete(value);
    return valid;
  }
  function equalJson(left, right) {
    if (Object.is(left, right)) return true;
    if (Array.isArray(left) || Array.isArray(right)) return Array.isArray(left) && Array.isArray(right) &&
      left.length === right.length && left.every((value, index) => equalJson(value, right[index]));
    if (!mapping(left) || !mapping(right)) return false;
    const keys = Object.keys(left);
    return keys.length === Object.keys(right).length && keys.every((key) => own(right, key) && equalJson(left[key], right[key]));
  }
  function condition(value) {
    return has(value, ["source", "path", "value", "unit"]) && Object.keys(value).length === 4 &&
      ["execution", "input_parameters"].includes(value.source) && Array.isArray(value.path) && value.path.length >= 1 && value.path.length <= 16 &&
      value.path.every((segment) => text(segment, 128) && !dangerous.has(segment)) &&
      (finite(value.value) || typeof value.value === "string" || typeof value.value === "boolean") && text(value.unit, 64);
  }
  function axis(value) { return exact(value, ["quantity", "value", "unit"]) && value.quantity === "time" && value.unit === "s" && finite(value.value); }
  function observation(value) {
    const limits = { name: 256, unit: 64, source: 2000, quantity: 128, component: 128, location: 512, coordinate_frame: 128, condition: 2000 };
    return exact(value, [...Object.keys(limits), "value", "source_kind", "tolerance", "conditions", ...(mapping(value) && own(value, "axis") ? ["axis"] : [])]) &&
      Object.keys(limits).every((key) => text(value[key], limits[key])) && finite(value.value) && finite(value.tolerance) && value.tolerance >= 0 &&
      ["MEASURED_REPORTED", "SPECIFICATION", "SYNTHETIC"].includes(value.source_kind) &&
      Array.isArray(value.conditions) && value.conditions.length <= 16 && value.conditions.every(condition);
  }
  function selection(record) {
    const { request, comparison } = record, response = request.response, metric = comparison.source_metric;
    requireValue(has(metric, ["value", "unit", "valid"]) && metric.valid === true && metric.unit === comparison.unit,
      "비교에 연결된 원 수치 응답의 유효 상태와 단위를 확인할 수 없습니다.");
    if (record.schema_version === "1.0") {
      requireValue(exact(response, ["metric", ...(mapping(response) && own(response, "component") ? ["component"] : [])]) && text(response.metric, 128) &&
        !own(request.observation, "axis") && !own(comparison, "source_channel") && !own(comparison, "response_axis") && !own(comparison, "declared_axis_check"),
      "일반 수치 비교에 다른 이력이나 시간축이 섞여 있습니다.");
      const array = Array.isArray(metric.value);
      requireValue(array ? own(response, "component") && ordinal(response.component) && response.component < metric.value.length && metric.value.every(finite) &&
        comparison.selection_kind === "USER_SELECTED_ARRAY_ITEM" && comparison.response_value === metric.value[response.component]
        : !own(response, "component") && finite(metric.value) && comparison.selection_kind === "SCALAR_METRIC" && comparison.response_value === metric.value,
      "원 scalar 또는 사용자가 지정한 배열 항목의 선택 연결이 일치하지 않습니다.");
      return null;
    }
    const channel = comparison.source_channel;
    requireValue(exact(response, ["history_channel", "sample_index"]) && id(response.history_channel) && ordinal(response.sample_index) &&
      comparison.selection_kind === "EXACT_RECORDED_HISTORY_SAMPLE" &&
      has(channel, ["id", "label", "metric", "quantity", "component", "measure", "coordinate_frame", "location", "unit", "axis", "values", "origin"]) &&
      channel.id === response.history_channel && ["label", "metric", "quantity", "component", "measure", "coordinate_frame", "location", "unit"].every((key) => text(channel[key])) &&
      channel.unit === comparison.unit && has(channel.axis, ["quantity", "unit", "values"]) && channel.axis.quantity === "time" && channel.axis.unit === "s" &&
      Array.isArray(channel.values) && channel.values.length > response.sample_index && channel.values.every(finite) && Array.isArray(channel.axis.values) &&
      channel.axis.values.length === channel.values.length && channel.axis.values.every((value, index, values) => finite(value) && (index === 0 || value > values[index - 1])) &&
      comparison.response_value === channel.values[response.sample_index] &&
      has(channel.origin, ["kind", "driver", "artifact", "sha256", "native_field", "mapping"]) && channel.origin.kind === "NATIVE" &&
      text(channel.origin.driver) && text(channel.origin.artifact) && digest(channel.origin.sha256) && text(channel.origin.native_field) && text(channel.origin.mapping),
    "저장된 원본 이력 채널·표본·측정 의미·출처 연결이 불완전합니다.");
    const check = comparison.declared_axis_check;
    requireValue(axis(request.observation.axis) && axis(comparison.response_axis) &&
      comparison.response_axis.value === channel.axis.values[response.sample_index] && has(check, ["declared", "actual", "matched"]) &&
      typeof check.matched === "boolean" && equalJson(check.declared, request.observation.axis) && equalJson(check.actual, comparison.response_axis) &&
      check.matched === (check.declared.value === check.actual.value),
    "보존된 관측 시간과 원본 표본 시간의 확인 기록이 일치하지 않습니다.");
    return check;
  }
  function verify(row, studyId) {
    requireValue(has(row, ["integrity", "record"]) && row.integrity === "VERIFIED", "모든 비교 기록의 원본 검증이 VERIFIED여야 합니다. 미확인 행을 제외해 진행하지 않습니다.");
    const record = row.record;
    requireValue(has(record, ["schema_version", "id", "request", "source", "comparison"]) && ["1.0", "1.1"].includes(record.schema_version),
      "지원되는 저장 비교 기록 1.0 또는 1.1이 필요합니다.");
    const { request, source, comparison } = record;
    requireValue(exact(request, ["comparison_id", "experiment_id", "purpose", "hypothesis", "observation", "response"]) &&
      has(source, ["experiment_id", "study_id", "result_sha256", "proposal_sha256", "thread_sha256"]) &&
      id(record.id) && request.comparison_id === record.id && id(request.experiment_id) && request.experiment_id === source.experiment_id &&
      source.study_id === studyId && [source.result_sha256, source.proposal_sha256, source.thread_sha256].every(digest),
    "비교 기록과 원 실험·선택한 연구의 식별자 또는 저장 문서 해시가 일치하지 않습니다.");
    requireValue(["DEFECT_REPRODUCTION", "JIG_FEASIBILITY"].includes(request.purpose) && text(request.hypothesis, 2000) &&
      observation(request.observation) && mapping(request.response), "저장된 연구 목적·가설·관측 입력이 불완전합니다.");
    requireValue(has(comparison, ["status", "response_value", "observed_value", "unit", "difference", "absolute_difference", "declared_absolute_tolerance",
      "within_declared_tolerance", "declared_condition_checks", "condition_bindings_supplied", "scope_alignment", "selection_kind", "source_metric", "physical_validation", "decision", "causal_verdict"]) &&
      ["NUMERIC_DIFFERENCE_ONLY", "DECLARED_CONDITION_MISMATCH", "DECLARED_AXIS_MISMATCH"].includes(comparison.status) &&
      finite(comparison.response_value) && finite(comparison.observed_value) && comparison.observed_value === request.observation.value &&
      text(comparison.unit, 64) && comparison.unit === request.observation.unit && finite(comparison.declared_absolute_tolerance) &&
      comparison.declared_absolute_tolerance === request.observation.tolerance && comparison.scope_alignment === "USER_DECLARED_UNVERIFIED" &&
      comparison.physical_validation === "UNKNOWN" && comparison.decision === "NOT_RELEASED" && comparison.causal_verdict === "NOT_EVALUATED",
    "유한한 비교값과 사용자 선언 범위·물리 검증 UNKNOWN·NOT_RELEASED 상태가 보존되어야 합니다.");
    const checks = comparison.declared_condition_checks;
    requireValue(Array.isArray(checks) && checks.length === request.observation.conditions.length && checks.every((check, index) =>
      has(check, ["declared", "actual", "matched"]) && typeof check.matched === "boolean" && equalJson(check.declared, request.observation.conditions[index])) &&
      comparison.condition_bindings_supplied === (checks.length > 0), "선언한 조건과 보존된 조건 확인 기록이 일치하지 않습니다.");
    const axisCheck = selection(record), conditionMismatch = checks.some((check) => !check.matched);
    const expectedStatus = conditionMismatch ? "DECLARED_CONDITION_MISMATCH" : axisCheck && !axisCheck.matched ? "DECLARED_AXIS_MISMATCH" : "NUMERIC_DIFFERENCE_ONLY";
    requireValue(comparison.status === expectedStatus && (expectedStatus === "NUMERIC_DIFFERENCE_ONLY"
      ? finite(comparison.difference) && finite(comparison.absolute_difference) && comparison.absolute_difference >= 0 && typeof comparison.within_declared_tolerance === "boolean"
      : comparison.difference === null && comparison.absolute_difference === null && comparison.within_declared_tolerance === null),
    "조건·시간 불일치의 null 차이·판정 또는 유한한 수치 비교 상태가 일치하지 않습니다.");
    return { comparisonId: record.id, experimentId: source.experiment_id };
  }
  function draft(rows, studyId) {
    requireValue(id(studyId) && Array.isArray(rows) && rows.length >= 1 && rows.length <= 12, "같은 연구의 저장 비교 기록 1~12개와 안전한 연구 식별자가 필요합니다.");
    requireValue(jsonValue(rows), "비교 행은 위험 키·순환 참조·실행 가능한 속성 없이 유한한 JSON 데이터여야 합니다.");
    const references = rows.map((row) => verify(row, studyId));
    const comparisonIds = references.map((item) => item.comparisonId);
    requireValue(new Set(comparisonIds).size === comparisonIds.length, "같은 비교 기록을 중복 선택할 수 없습니다.");
    const experimentIds = [...new Set(references.map((item) => item.experimentId))];
    const question = [
      `연구 ${studyId}에 저장된 비교 근거를 해석해 주세요.`,
      `비교 기록: ${comparisonIds.join(", ")}`,
      `원 실험: ${experimentIds.join(", ")}`,
      "각 원 실험의 저장된 결과 요약과 함께 제공된 comparison_context(비교 기록)를 먼저 읽고, 위 기록만을 근거로 가설별 응답을 비교해 주세요. 사용자가 선언한 조건·위치·성분·좌표계·시간축·단위가 어떤 비교를 허용하는지 설명해 주세요.",
      "SYNTHETIC(가상값), MEASURED_REPORTED(자격이 확인되지 않은 사용자 측정 보고), SPECIFICATION(규격)을 구분해 주세요. 조건이나 시각 불일치로 차이와 허용 차이 판정이 null이면 비교 불가로 유지하고, 0이나 통과로 바꾸지 마세요. 원 단위와 부호를 보존해 주세요.",
      "이력이 있으면 원본 driver와 응력·가지 응력·참조 체적당 에너지의 의미를 구분해 주세요. t=0의 준비되지 않은 수치 초기 상태를 재료 적분 증거로 해석하지 마세요. 표본 사이 값을 보간하거나 없는 수치를 만들지 마세요.",
      "물리 검증 UNKNOWN, 사용자 선언 범위 USER_DECLARED_UNVERIFIED, 사용 미승인 NOT_RELEASED, 원인 판정 NOT_EVALUATED를 유지해 주세요. 수치가 맞는다는 이유로 원인을 하나로 확정하거나 지그 제작·사용 적합성을 승인하지 마세요.",
      "새 계산이나 최적화 없이 저장된 근거를 해석해 주세요. 가설을 구별할 다음 실험과 필요한 측정·입력 자료를 제안하고, 어떤 관측이 각 가설을 구별할 수 있는지 설명해 주세요. 제작 전 지그 판단에 남은 요건도 밝혀 주세요."
    ].join("\n\n");
    requireValue(new TextEncoder().encode(question).length <= 16384, "연구 질문이 기존 16 KiB 입력 범위를 넘었습니다.");
    return { question, studyId, comparisonIds, experimentIds };
  }
  const api = { draft };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.comparisonResearch = api;
})(typeof window !== "undefined" ? window : globalThis);
