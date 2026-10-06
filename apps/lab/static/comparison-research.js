"use strict";

// Draft an interpretation question from verified saved comparisons only.
// Core summaries remain authoritative; no provider, session or execution here.
(function (root) {
  const history = typeof module !== "undefined" && module.exports ? require("./history-controls.js") : null;
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
  function relativeArtifact(value) {
    return text(value, 1024) && value === value.trim() && !/[\\:%\u0000-\u001f\u007f]/.test(value) &&
      value.split("/").every(part => text(part) && part === part.trim() && ![".", ".."].includes(part) && !dangerous.has(part));
  }
  function fieldSelection(record) {
    const { request, comparison, source } = record, field = request.response.field, original = comparison.source_field;
    const identityKeys = ["artifact", "sha256", "cad_revision", "node_id", "component"];
    requireValue(exact(request.response, ["field"]) && exact(field, identityKeys) && relativeArtifact(field.artifact) && digest(field.sha256) &&
      digest(field.cad_revision) && field.cad_revision === source.cad_revision && Number.isSafeInteger(field.node_id) && field.node_id > 0 &&
      ["UX", "UY", "UZ", "MAGNITUDE"].includes(field.component) && comparison.selection_kind === "EXACT_RECORDED_FIELD_NODE" &&
      comparison.field_qualification === "UNKNOWN" && comparison.unit === "mm" &&
      exact(original, [...identityKeys, "quantity", "position_mm", "position_unit", "coordinate_frame", "value_origin", "static", "coverage"]) &&
      identityKeys.every(key => original[key] === field[key]) && original.quantity === "DISPLACEMENT" && original.position_unit === "mm" &&
      Array.isArray(original.position_mm) && original.position_mm.length === 3 && original.position_mm.every(finite) &&
      text(original.coordinate_frame, 128) && text(original.coverage, 128) &&
      original.value_origin === (field.component === "MAGNITUDE" ? "DERIVED_MAGNITUDE" : "NATIVE_COMPONENT") &&
      (field.component !== "MAGNITUDE" || comparison.response_value >= 0) &&
      exact(original.static, ["step", "increment", "load_parameter"]) && Number.isSafeInteger(original.static.step) && original.static.step > 0 &&
      Number.isSafeInteger(original.static.increment) && original.static.increment > 0 && finite(original.static.load_parameter) &&
      !own(request.observation, "axis") && !own(comparison, "source_metric") && !own(comparison, "source_channel") &&
      !own(comparison, "response_axis") && !own(comparison, "declared_axis_check"),
    "정확한 원 field·SHA·CAD 개정·절점·좌표·성분·정적 증분과 미확인 자격의 연결을 확인할 수 없습니다.");
    const checks = comparison.declared_field_checks, properties = ["quantity", "component", "coordinate_frame"];
    requireValue(Array.isArray(checks) && checks.length === properties.length && checks.every((check, index) =>
      exact(check, ["property", "declared", "actual", "matched"]) && check.property === properties[index] &&
      check.declared === request.observation[check.property] && check.actual === original[check.property] &&
      typeof check.matched === "boolean" && check.matched === (check.declared === check.actual)),
    "필드의 원 물리량·성분·좌표계와 사용자 선언의 확인 기록이 일치하지 않습니다.");
    return checks;
  }
  function pdeFieldSelection(record) {
    const {request,comparison,source}=record, field=request.response.field, original=comparison.source_field;
    const keys=["kind","artifact","sha256","model_revision","study_index","step_index","node_id","component"];
    requireValue(exact(request.response,["field"]) && exact(field,keys) && field.kind === "pde_nodal" &&
      relativeArtifact(field.artifact) && digest(field.sha256) && digest(field.model_revision) && field.model_revision === source.model_revision &&
      ordinal(field.study_index) && ordinal(field.node_id) && (field.step_index === null || ordinal(field.step_index)) &&
      ["u","u0","u1"].includes(field.component) && comparison.selection_kind === "EXACT_RECORDED_FIELD_NODE" && comparison.unit === "1" &&
      has(original,["artifact","sha256","model_revision","study_index","step_index","node_id","component","quantity","coordinates","coordinates_unit","coordinate_frame"]) &&
      keys.filter(key=>key !== "kind").every(key=>original[key] === field[key]) &&
      ["PDE_SCALAR_FIELD","PDE_VECTOR_FIELD"].includes(original.quantity) && original.coordinates_unit === "1" &&
      Array.isArray(original.coordinates) && original.coordinates.length === 2 && original.coordinates.every(finite) &&
      original.coordinate_frame === "PDE_MODEL_CARTESIAN" && has(comparison.field_qualification,["physical","decision"]) &&
      comparison.field_qualification.physical === "UNKNOWN" && comparison.field_qualification.decision === "NOT_RELEASED" &&
      !own(comparison,"source_metric") && !own(comparison,"source_channel"),
      "원 PDE 모델 개정·메시·단계·절점·성분·단위와 미검증 자격을 확인할 수 없습니다.");
    const checks=comparison.declared_field_checks;
    requireValue(Array.isArray(checks) && checks.length === 3 && ["quantity","component","coordinate_frame"].every((key,index)=>
      exact(checks[index],["property","declared","actual","matched"]) && checks[index].property === key &&
      checks[index].declared === request.observation[key] && checks[index].actual === original[key] &&
      checks[index].matched === (checks[index].declared === checks[index].actual)),"PDE 관측의 선언한 성분·좌표 확인이 일치하지 않습니다.");
    let axisCheck=null;
    if (field.step_index === null) requireValue(!own(request.observation,"axis") && !own(comparison,"response_axis") &&
      !own(comparison,"declared_axis_check"),"정적 PDE 필드에 시간축을 만들 수 없습니다.");
    else {
      const actual=comparison.response_axis, declared=request.observation.axis; axisCheck=comparison.declared_axis_check;
      requireValue(exact(actual,["quantity","unit","value"]) && actual.quantity === "time" && actual.unit === "1" && finite(actual.value) &&
        exact(declared,["quantity","unit","value"]) && declared.quantity === "time" && declared.unit === "1" && finite(declared.value) &&
        exact(axisCheck,["declared","actual","matched"]) && equalJson(axisCheck.actual,actual) && equalJson(axisCheck.declared,declared) &&
        axisCheck.matched === (actual.value === declared.value),"PDE의 정확한 저장 축을 초나 보간값으로 바꾸지 마세요.");
    }
    return {fields:checks,axis:axisCheck};
  }
  function selection(record) {
    if (record.schema_version === "1.2") return fieldSelection(record);
    if (record.schema_version === "1.4") return pdeFieldSelection(record);
    const { request, comparison } = record, response = request.response, metric = comparison.source_metric;
    requireValue(!own(comparison, "source_field") && !own(comparison, "field_qualification") && !own(comparison, "declared_field_checks"),
      "scalar 또는 이력 비교에 다른 field 선택 근거가 섞여 있습니다.");
    const nativeHistory = record.schema_version === "1.3";
    requireValue(nativeHistory ? !own(comparison, "source_metric") : has(metric, ["value", "unit", "valid"]) && metric.valid === true && metric.unit === comparison.unit,
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
      channel.id === response.history_channel && ["label", ...(nativeHistory ? [] : ["metric"]), "quantity", "component", "measure", "coordinate_frame", "location", "unit"].every((key) => text(channel[key])) &&
      channel.unit === comparison.unit && has(channel.axis, ["quantity", "unit", "values"]) && channel.axis.quantity === "time" && channel.axis.unit === "s" &&
      Array.isArray(channel.values) && channel.values.length > response.sample_index && channel.values.every(finite) && Array.isArray(channel.axis.values) &&
      channel.axis.values.length === channel.values.length && channel.axis.values.every((value, index, values) => finite(value) && (index === 0 || value > values[index - 1])) &&
      comparison.response_value === channel.values[response.sample_index] &&
      has(channel.origin, ["kind", "driver", "artifact", "sha256", "native_field", "mapping"]) && (nativeHistory || channel.origin.kind === "NATIVE") &&
      text(channel.origin.driver) && text(channel.origin.artifact) && digest(channel.origin.sha256) && text(channel.origin.native_field) && text(channel.origin.mapping),
    "저장된 원본 이력 채널·표본·측정 의미·출처 연결이 불완전합니다.");
    if (nativeHistory) {
      requireValue((root.historyControls ?? history)?.nativeChannelValid(channel, record.source.backend) === true,
        "지원되는 native 이력의 원래 단위·측정량·시간축·출처가 필요합니다.");
      const checks = comparison.declared_history_checks;
      requireValue(Array.isArray(checks) && checks.length === 3 && ["quantity", "component", "coordinate_frame"].every((key, i) =>
        has(checks[i], ["property", "declared", "actual", "matched"]) && checks[i].property === key &&
        checks[i].declared === request.observation[key] && checks[i].actual === channel[key] &&
        checks[i].matched === (checks[i].declared === checks[i].actual)), "이력 관측의 물리량·성분·좌표계 확인이 일치하지 않습니다.");
    }
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
    requireValue(has(record, ["schema_version", "id", "request", "source", "comparison"]) && ["1.0", "1.1", "1.2", "1.3", "1.4"].includes(record.schema_version),
      "지원되는 저장 비교 기록 1.0, 1.1 또는 1.2가 필요합니다.");
    const { request, source, comparison } = record;
    requireValue(exact(request, ["comparison_id", "experiment_id", "purpose", "hypothesis", "observation", "response"]) &&
      has(source, ["experiment_id", "study_id", "result_sha256", "proposal_sha256", "thread_sha256"]) &&
      id(record.id) && request.comparison_id === record.id && id(request.experiment_id) && request.experiment_id === source.experiment_id &&
      source.study_id === studyId && [source.result_sha256, source.proposal_sha256, source.thread_sha256].every(digest),
    "비교 기록과 원 실험·선택한 연구의 식별자 또는 저장 문서 해시가 일치하지 않습니다.");
    requireValue(["GENERAL_CAE_RESEARCH", "DEFECT_REPRODUCTION", "JIG_FEASIBILITY"].includes(request.purpose) && text(request.hypothesis, 2000) &&
      observation(request.observation) && mapping(request.response), "저장된 연구 목적·가설·관측 입력이 불완전합니다.");
    requireValue(has(comparison, ["status", "response_value", "observed_value", "unit", "difference", "absolute_difference", "declared_absolute_tolerance",
      "within_declared_tolerance", "declared_condition_checks", "condition_bindings_supplied", "scope_alignment", "selection_kind", "physical_validation", "decision", "causal_verdict",
      ...(["1.2","1.4"].includes(record.schema_version) ? ["source_field", "field_qualification", "declared_field_checks"] : record.schema_version === "1.3" ? ["source_channel", "declared_history_checks"] : ["source_metric"])]) &&
      ["NUMERIC_DIFFERENCE_ONLY", "DECLARED_CONDITION_MISMATCH", "DECLARED_AXIS_MISMATCH", "DECLARED_FIELD_MISMATCH"].includes(comparison.status) &&
      finite(comparison.response_value) && finite(comparison.observed_value) && comparison.observed_value === request.observation.value &&
      text(comparison.unit, 64) && comparison.unit === request.observation.unit && finite(comparison.declared_absolute_tolerance) &&
      comparison.declared_absolute_tolerance === request.observation.tolerance && comparison.scope_alignment === "USER_DECLARED_UNVERIFIED" &&
      comparison.physical_validation === "UNKNOWN" && comparison.decision === "NOT_RELEASED" && comparison.causal_verdict === "NOT_EVALUATED",
    "유한한 비교값과 사용자 선언 범위·물리 검증 UNKNOWN·NOT_RELEASED 상태가 보존되어야 합니다.");
    const checks = comparison.declared_condition_checks;
    requireValue(Array.isArray(checks) && checks.length === request.observation.conditions.length && checks.every((check, index) =>
      has(check, ["declared", "actual", "matched"]) && typeof check.matched === "boolean" && equalJson(check.declared, request.observation.conditions[index])) &&
      comparison.condition_bindings_supplied === (checks.length > 0), "선언한 조건과 보존된 조건 확인 기록이 일치하지 않습니다.");
    const selectedCheck = selection(record), conditionMismatch = checks.some((check) => !check.matched);
    const fieldMismatch = record.schema_version === "1.4" ? selectedCheck.fields.some(check=>!check.matched) : record.schema_version === "1.2" ? selectedCheck.some(check => !check.matched)
      : record.schema_version === "1.3" && comparison.declared_history_checks.some(check => !check.matched);
    const axisMismatch = record.schema_version === "1.4" ? selectedCheck.axis && !selectedCheck.axis.matched : ["1.1", "1.3"].includes(record.schema_version) && selectedCheck && !selectedCheck.matched;
    const expectedStatus = conditionMismatch ? "DECLARED_CONDITION_MISMATCH" : fieldMismatch ? "DECLARED_FIELD_MISMATCH" : axisMismatch ? "DECLARED_AXIS_MISMATCH" : "NUMERIC_DIFFERENCE_ONLY";
    requireValue(comparison.status === expectedStatus && (expectedStatus === "NUMERIC_DIFFERENCE_ONLY"
      ? finite(comparison.difference) && finite(comparison.absolute_difference) && comparison.absolute_difference >= 0 && typeof comparison.within_declared_tolerance === "boolean"
      : comparison.difference === null && comparison.absolute_difference === null && comparison.within_declared_tolerance === null),
    "조건·시간·필드 불일치의 null 차이·판정 또는 유한한 수치 비교 상태가 일치하지 않습니다.");
    if (["1.2","1.4"].includes(record.schema_version) && expectedStatus === "NUMERIC_DIFFERENCE_ONLY") requireValue(
      comparison.difference === comparison.response_value - comparison.observed_value &&
      comparison.absolute_difference === Math.abs(comparison.difference) &&
      comparison.within_declared_tolerance === (comparison.absolute_difference <= comparison.declared_absolute_tolerance),
      "보존된 필드 응답의 부호와 차이·허용 차이 판정이 일치하지 않습니다.");
    return { comparisonId: record.id, experimentId: source.experiment_id };
  }
  function fieldLines(rows) {
    const value = item => Object.is(item, -0) ? "-0" : String(item);
    return rows.filter(row => ["1.2","1.4"].includes(row.record.schema_version)).flatMap(row => {
      const { request, comparison } = row.record, original = comparison.source_field;
      if (row.record.schema_version === "1.4") return [
        `비교 ${row.record.id}: 원 PDE 모델 ${original.model_revision} · 메시 ${original.study_index} · 단계 ${original.step_index ?? "정적"} · ${original.artifact}`,
        `원 절점 ${original.node_id} · XY [${original.coordinates.map(value).join(", ")}] (1) · ${original.quantity}/${original.component}=${value(comparison.response_value)} (1) · ${original.coordinate_frame}`,
        `축 ${comparison.response_axis ? `${comparison.response_axis.quantity}=${value(comparison.response_axis.value)} (${comparison.response_axis.unit})` : "정적"}; 원 초기/계산 자격 ${JSON.stringify(comparison.field_qualification)}; 사용자 선언 출처 ${request.observation.source_kind}`,
        `선언한 관측 ${value(request.observation.value)} (${request.observation.unit}) · 상태 ${comparison.status} · 차이 ${value(comparison.difference)}; 참조·물리·원인 확정 UNKNOWN/NOT_EVALUATED/NOT_RELEASED`
      ];
      return [
        `비교 ${row.record.id}: 원 field ${original.artifact} · SHA256 ${original.sha256} · CAD 개정 ${original.cad_revision}`,
        `정확한 원 절점 ${original.node_id} · 좌표 [${original.position_mm.map(value).join(", ")}] ${original.position_unit} · 원 좌표계 ${original.coordinate_frame} · ${original.quantity}/${original.component} = ${value(comparison.response_value)} ${comparison.unit} · ${original.value_origin}`,
        `정적 원 증분 step=${original.static.step}, increment=${original.static.increment}, load_parameter=${value(original.static.load_parameter)} · 원 coverage ${original.coverage} · field 자격 ${comparison.field_qualification}`,
        `사용자 선언: ${request.observation.quantity}/${request.observation.component} · ${request.observation.coordinate_frame}; 비교 상태 ${comparison.status} · 차이 ${value(comparison.difference)} · 절대 차이 ${value(comparison.absolute_difference)} · 허용 차이 판정 ${value(comparison.within_declared_tolerance)}`
      ];
    });
  }
  function historyLines(rows) {
    return rows.filter(row => row.record.schema_version === "1.3").flatMap(row => {
      const { comparison, request } = row.record, channel = comparison.source_channel, origin = channel.origin;
      return [`비교 ${row.record.id}: ${channel.quantity}/${channel.component} · ${channel.measure} · ${channel.location} · ${channel.coordinate_frame}`,
        `원 표본 ${request.response.sample_index}: ${comparison.response_value} ${comparison.unit}; 축 ${comparison.response_axis.quantity}=${comparison.response_axis.value} ${comparison.response_axis.unit} · ${channel.axis.semantics ?? "원 재료 시간"}`,
        `출처 ${origin.kind}/${origin.driver} · ${origin.native_field} · ${origin.mapping}; 초기 상태 ${channel.initial_state?.kind ?? "미기록"} · 비교 상태 ${comparison.status}`];
    });
  }
  function draft(rows, studyId, context) {
    requireValue(id(studyId) && Array.isArray(rows) && rows.length >= 1 && rows.length <= 12, "같은 연구의 저장 비교 기록 1~12개와 안전한 연구 식별자가 필요합니다.");
    requireValue(jsonValue(rows), "비교 행은 위험 키·순환 참조·실행 가능한 속성 없이 유한한 JSON 데이터여야 합니다.");
    const references = rows.map((row) => verify(row, studyId));
    const comparisonIds = references.map((item) => item.comparisonId);
    requireValue(new Set(comparisonIds).size === comparisonIds.length, "같은 비교 기록을 중복 선택할 수 없습니다.");
    const experimentIds = [...new Set(references.map((item) => item.experimentId))];
    const general = rows.some(row => row.record.request.purpose === "GENERAL_CAE_RESEARCH");
    const hasStructuralField = rows.some(row => row.record.schema_version === "1.2"),
      hasPdeField = rows.some(row => row.record.schema_version === "1.4"),
      hasHistory = rows.some(row => ["1.1", "1.3"].includes(row.record.schema_version));
    const humanContext = [];
    if (context !== undefined) {
      requireValue(exact(context, ["question", "hypothesis", "objective"]) && jsonValue(context) &&
        Object.values(context).every(value => text(value, 2000) && !value.includes("\u0000")),
        "연구 context는 질문·가설·목적을 각각 2000자 이내의 자체 JSON 문자열로 명시해야 합니다.");
      humanContext.push(`사용자가 기록한 연구 질문: ${context.question}`, `비교할 가설: ${context.hypothesis}`, `연구 목적·응답: ${context.objective}`);
    }
    const question = [
      `연구 ${studyId}에 저장된 비교 근거를 해석해 주세요.`,
      `비교 기록: ${comparisonIds.join(", ")}`,
      `원 실험: ${experimentIds.join(", ")}`,
      ...humanContext,
      "각 원 실험의 저장된 결과 요약과 함께 제공된 comparison_context(비교 기록)를 먼저 읽고, 위 기록만을 근거로 가설별 응답을 비교해 주세요. 사용자가 선언한 조건·위치·성분·좌표계·시간축·단위가 어떤 비교를 허용하는지 설명해 주세요.",
      "SYNTHETIC(가상값), MEASURED_REPORTED(자격이 확인되지 않은 사용자 측정 보고), SPECIFICATION(규격)을 구분해 주세요. 조건이나 시각 불일치로 차이와 허용 차이 판정이 null이면 비교 불가로 유지하고, 0이나 통과로 바꾸지 마세요. 원 단위와 부호를 보존해 주세요.",
      ...(hasHistory ? ["이력이 있으면 원본 driver와 각 채널의 위치·성분·물리량·단위·축 의미를 구분해 주세요. 응력·가지 응력·참조 체적당 에너지와 동적 모델의 전체 에너지를 혼동하지 마세요. 재료점의 UNPREPARED_INITIAL_CONDITION과 동적 모델의 선언 초기 상태를 구분해 주세요. 원 TH 속도의 반 증분 시각을 위치·에너지 시각으로 바꾸지 말고, 벽의 누적 충격량 FNZ를 순간 힘으로 해석하지 마세요. 부호 있는 native 일과 명시한 파생값을 구분해 주세요. t=0의 준비되지 않은 수치 초기 상태를 재료 적분 증거로 해석하지 마세요. 표본 사이 값을 보간하거나 없는 수치를 만들지 마세요."] : []),
      ...fieldLines(rows),
      ...historyLines(rows),
      ...(hasStructuralField ? [
        "필드는 EXACT_RECORDED_FIELD_NODE에 연결된 원 절점·좌표·원 SHA·CAD 개정을 유지해 주세요. UX/UY/UZ의 NATIVE_COMPONENT는 부호 있는 원 변위이며, MAGNITUDE의 DERIVED_MAGNITUDE는 벡터에서 계산한 크기입니다. 두 의미를 바꾸지 마세요. 정적 step/increment/load_parameter를 시간축으로 쓰지 마세요. 센서/world 정렬과 서로 다른 메시의 같은 절점 ID는 검증된 물리 위치 대응이 아닙니다. DECLARED_FIELD_MISMATCH이면 차이·허용 차이 판정 null을 보존해 주세요."
      ] : []),
      ...(hasPdeField ? ["PDE는 원 model_revision·메시·단계·절점과 u/u0/u1 성분을 유지해 주세요. 좌표·필드·저장된 모델 시간의 단위 1을 mm나 초로 바꾸지 마세요. 정적 필드에는 시간축이 없습니다. UNINTEGRATED_INITIAL_CONDITION/NOT_RUN은 초기 선언값이며 적분 성공이 아닙니다. 다른 메시의 같은 절점 ID를 같은 물리 위치로 추정하지 마세요. DECLARED_FIELD_MISMATCH/DECLARED_AXIS_MISMATCH의 null 판정을 보존하고 보간하거나 없는 참조 오차를 만들지 마세요."] : []),
      general ?
        "물리 검증 UNKNOWN, 사용자 선언 범위 USER_DECLARED_UNVERIFIED, 사용 미승인 NOT_RELEASED, 원인 판정 NOT_EVALUATED를 유지해 주세요. 수치가 맞는다는 이유로 유일한 원인이나 공학적 사용 적합성을 확정하지 마세요." :
        "물리 검증 UNKNOWN, 사용자 선언 범위 USER_DECLARED_UNVERIFIED, 사용 미승인 NOT_RELEASED, 원인 판정 NOT_EVALUATED를 유지해 주세요. 수치가 맞는다는 이유로 원인을 하나로 확정하거나 지그 제작·사용 적합성을 승인하지 마세요.",
      general ?
        "새 계산이나 최적화 없이 저장된 근거를 해석해 주세요. 연구 질문과 가설을 구별할 다음 실험·필요한 측정·입력 자료와 응답·잔차를 제안해 주세요. 모델링 가정과 수치·물리 검증에 남은 확인 사항도 밝혀 주세요." :
        "새 계산이나 최적화 없이 저장된 근거를 해석해 주세요. 가설을 구별할 다음 실험과 필요한 측정·입력 자료를 제안하고, 어떤 관측이 각 가설을 구별할 수 있는지 설명해 주세요. 제작 전 지그 판단에 남은 요건도 밝혀 주세요."
    ].join("\n\n");
    requireValue(new TextEncoder().encode(question).length <= 16384, "연구 질문이 기존 16 KiB 입력 범위를 넘었습니다.");
    return { question, studyId, comparisonIds, experimentIds };
  }
  function declarationLines(declaration) {
    requireValue(mapping(declaration) && jsonValue(declaration), "보존한 선언 조건이 필요합니다.");
    const value = item => typeof item === "number" ? Object.is(item, -0) ? "-0" : String(item) : String(item ?? "미확인");
    const excerpt = item => String(item ?? "미확인").slice(0, 256);
    const lines = [`해석 ${excerpt(declaration.analysis_type)} · 좌표계 ${excerpt(declaration.coordinate_system)} · 길이 ${excerpt(declaration.units?.length)} / 힘 ${excerpt(declaration.units?.force)} / 응력 ${excerpt(declaration.units?.stress)}`];
    for (const material of (declaration.materials ?? []).slice(0, 64)) lines.push(
      `재료 ${excerpt(material.selection_id)}: ${excerpt(material.law)}, E=${value(material.young_modulus_MPa)} MPa, ν=${value(material.poisson_ratio)}, 출처 ${excerpt(material.source?.category)} · ${excerpt(material.source?.description)}`);
    for (const bc of (declaration.boundary_conditions ?? []).slice(0, 64)) lines.push(
      `구속 ${excerpt(bc.selection_id)}: ${Object.entries(bc.components ?? {}).map(([key, item]) => `${key}=${value(item)}`).join(" / ")} ${excerpt(bc.unit)} · ${excerpt(bc.coordinate_system)} · ${excerpt(bc.source)}`);
    for (const load of (declaration.loads ?? []).slice(0, 64)) lines.push(
      `하중 ${excerpt(load.selection_id)}: ${Object.entries(load.components ?? {}).map(([key, item]) => `${key}=${value(item)}`).join(" / ")} ${excerpt(load.unit)} · ${excerpt(load.coordinate_system)} · ${excerpt(load.source)}`);
    lines.push(`접촉 ${excerpt(declaration.contact?.mode)} · ${excerpt(declaration.contact?.source)}; 메시 ${excerpt(declaration.mesh?.mode)} / ${value(declaration.mesh?.max_size_mm)} mm`);
    return lines;
  }
  function campaignDraft(data, studyId, indexes) {
    requireValue(mapping(data) && jsonValue(data) && id(studyId) && id(data.id) && ["optimization", "doe"].includes(data.type) &&
      mapping(data.record), "현재 저장소에서 다시 확인한 캠페인 기록이 필요합니다.");
    const record = data.record, plan = data.plan ?? record.plan ?? record;
    requireValue(mapping(plan) && plan.campaign_id === data.id && plan.study_id === studyId &&
      (!own(record, "campaign_id") || record.campaign_id === data.id) && (!own(record, "study_id") || record.study_id === studyId) &&
      (!own(record, "plan_sha256") || digest(record.plan_sha256)) &&
      (!own(record, "decision") || record.decision === "NOT_RELEASED"), "선택한 연구와 고정 계획·원 실행 기록이 일치하지 않습니다.");
    const rows = record.evaluations ?? record.samples ?? [];
    const planned = data.type === "optimization" && record.status === "PLANNED" && rows.length === 0 && Array.isArray(indexes) && indexes.length === 0;
    requireValue(Array.isArray(rows) && rows.length <= 512 && Array.isArray(indexes) && (planned || indexes.length >= 1 && indexes.length <= 12) &&
      indexes.every(ordinal) && new Set(indexes).size === indexes.length &&
      rows.every(row => mapping(row) && ordinal(row.index)) && new Set(rows.map(row => row.index)).size === rows.length,
    "실제 보존 후보 1~12개를 중복 없이 선택하세요.");
    const model = (record.route ?? plan.route) === "model_analysis";
    const fixedCad = (record.route ?? plan.route) === "fixed_cad_analysis";
    requireValue(!planned || !fixedCad, "현재 AI 실행 범위에는 고정 CAD 조건 탐색이 없습니다. 사람이 계획을 실행한 뒤 실제 후보 해석을 질문에 연결하세요.");
    const selected = indexes.map(index => rows.find(row => row.index === index));
    requireValue(selected.every(row => row && row.decision === "NOT_RELEASED" &&
      (model ? id(row.model_experiment_id) && digest(row.model_result_sha256) : id(row.cad_experiment_id) && digest(row.cad_result_sha256) &&
        (plan.analysis ? id(row.analysis_experiment_id) && digest(row.analysis_result_sha256) : true))),
    "미실행·건너뛴 해석은 연구 근거로 연결할 수 없습니다. 실제 결과와 해시가 있는 후보를 선택하세요.");
    const template = plan.analysis?.conditions_template;
    let conditionsId = null, sourceExperimentId = null, context = [];
    if (template !== undefined) {
      const reference = template?.reference, saved = template?.record, source = saved?.source;
      requireValue(mapping(template) && template.rebind_policy === "REVISION_REBIND_EXACT_SELECTIONS" &&
        mapping(reference) && id(reference.id) && [reference.revision, reference.record_sha256, reference.catalog_revision, template.record_canonical_sha256].every(digest) &&
        reference.scope === "USER_DECLARED_UNVERIFIED" && mapping(saved) && saved.id === reference.id &&
        saved.conditions_revision === reference.revision && saved.catalog_revision === reference.catalog_revision &&
        saved.engineering === "UNKNOWN" && saved.decision === "NOT_RELEASED" &&
        saved.support?.status === "SUPPORTED_DECLARED_INPUTS" && mapping(source) && id(source.experiment_id) && source.study_id === studyId &&
        [source.cad_revision, source.result_sha256, source.proposal_sha256, source.thread_sha256].every(digest) &&
        saved.request?.conditions_id === saved.id && saved.request?.experiment_id === source.experiment_id &&
        saved.request?.cad_revision === source.cad_revision && saved.request?.catalog_revision === saved.catalog_revision &&
        saved.request?.backend === plan.analysis?.backend && source.backend === plan.backend,
      "고정한 원 조건·CAD 개정·해시·사용자 선언 범위가 불완전합니다.");
      conditionsId = reference.id; sourceExperimentId = source.experiment_id;
      context = [`원 저장 조건 ${conditionsId} · 조건 개정 ${reference.revision}`,
        `원 CAD ${sourceExperimentId} · CAD 개정 ${source.cad_revision}`,
        `원 조건 해시 ${reference.record_sha256} · catalog 개정 ${reference.catalog_revision}`,
        ...declarationLines(saved.request.declaration),
        "각 실제 후보 CAD 개정에 정확한 대상 선택을 다시 연결한 정책: REVISION_REBIND_EXACT_SELECTIONS. 실제 자식 요약의 analysis_conditions_context에서 후보별 조건 ID·개정·동결 선언을 확인해 주세요."];
    }
    if (fixedCad) {
      const frozen = plan.fixed_cad, saved = frozen?.record, reference = frozen?.reference, source = frozen?.source;
      requireValue(mapping(frozen) && frozen.rebind_policy === "FIXED_CAD_NO_REBIND" && mapping(saved) && mapping(reference) &&
        mapping(source) && source.study_id === studyId && id(source.experiment_id) && id(saved.id) &&
        saved.id === frozen.conditions_id && saved.id === reference.id && saved.conditions_revision === frozen.conditions_revision &&
        saved.conditions_revision === reference.revision && saved.catalog_revision === frozen.catalog_revision &&
        saved.catalog_revision === reference.catalog_revision && frozen.backend === plan.analysis?.backend &&
        source.backend === plan.backend && saved.source.experiment_id === source.experiment_id &&
        saved.engineering === "UNKNOWN" && saved.decision === "NOT_RELEASED" &&
        [source.cad_revision, source.result_sha256, source.proposal_sha256, source.thread_sha256,
          reference.record_sha256, frozen.template_revision, frozen.condition_input_descriptors_sha256].every(digest) &&
        selected.every(row => row.cad_experiment_id === source.experiment_id && id(row.conditions_id) &&
          digest(row.condition_binding_sha256) && mapping(row.condition_declaration) && row.condition_input_rejection === null),
      "고정 CAD·조건 template과 실제 후보의 새 조건·결과 연결을 확인할 수 없습니다.");
      conditionsId = saved.id; sourceExperimentId = source.experiment_id;
      context = [`원 CAD ${sourceExperimentId} · CAD 개정 ${source.cad_revision} · FIXED_CAD_NO_REBIND`,
        `기준 조건 ${saved.id} · 조건 개정 ${saved.conditions_revision} · template ${frozen.template_revision}`,
        ...declarationLines(saved.request.declaration),
        "CAD·native 면·mesh 크기는 고정했습니다. CAD 형상 변수와 별개로 다음 재료·하중 연구 입력을 수치 엔진이 변경했습니다.",
        ...selected.map(row => `후보 ${row.index}: ${JSON.stringify(row.values)} · 새 조건 ${row.conditions_id} · 바인딩 ${row.condition_binding_sha256}`),
        "각 실제 자식 결과의 analysis_conditions_context에서 후보별 동결 조건·재료/하중의 ASSUMED 시나리오 출처를 확인하세요. 같은 CAD여도 서로 다른 메시의 절점 ID가 같은 위치를 뜻한다고 추정하지 마세요."];
    }
    const references = selected.map(row => ({ index: row.index, cadExperimentId: model ? null : row.cad_experiment_id,
      experimentId: model ? row.model_experiment_id : plan.analysis ? row.analysis_experiment_id : row.cad_experiment_id }));
    const question = [
      planned ? `연구 ${studyId}의 이미 저장된 최적화 캠페인 ${data.id} 실행을 요청합니다.` : `연구 ${studyId}의 저장 캠페인 ${data.id}에서 선택한 실제 후보를 해석해 주세요.`,
      ...(context.length ? [context.join("\n")] : []),
      planned ? "아직 실제 후보 결과가 없습니다. 실행에서 반환된 실제 ID를 근거로 사용해 주세요." : `선택한 후보:\n${references.map(item => `후보 ${item.index}: ${item.cadExperimentId ? `CAD ${item.cadExperimentId} · ` : ""}결과 ${item.experimentId}`).join("\n")}`,
      `고정 목적 함수: ${JSON.stringify(plan.objective ?? null)}\n고정 제약: ${JSON.stringify(plan.constraints ?? [])}`,
      ...(plan.objective?.direction === "match" ? [
        "이 목표는 명시한 단일 scalar 응답의 목표값 맞추기입니다. 정규화 크기는 허용차가 아니며, 위치·성분·축·단위를 바꾸거나 응답 일치로 유일한 원인을 확정하지 마세요.",
        ...selected.map(row => `후보 ${row.index}의 보존된 목표 비교: ${JSON.stringify(row.objective?.target_comparison ?? null)}`)
      ] : []),
      "각 원 실험의 저장 결과 요약과 제공된 analysis_conditions_context를 먼저 읽고, 실제 변수·재료·구속·하중·좌표계·관측 위치·성분·단위와 지표의 의미를 보존해 주세요. 하중 영역의 최대 |UZ|와 전체 필드 최대 |U|는 다른 관측량입니다. signed 값과 시간·하중 축을 바꾸거나 없는 관측을 만들지 마세요.",
      "ASSUMED, MEASURED_REPORTED(자격이 확인되지 않은 사용자 보고), PUBLISHED_REFERENCE와 SYNTHETIC 근거를 구분해 주세요. invalid 지표·null 잔차·실패·UNKNOWN은 원 상태로 유지해 주세요. 수치적으로 유효한 후보와 물리·강도·내구·장비 자격 UNKNOWN, 사용자 선언 USER_DECLARED_UNVERIFIED, 사용 미승인 NOT_RELEASED를 구분해 주세요.",
      planned ?
        `현재 연결에서 optimization_inspect와 optimization_run을 지원하는지 먼저 확인해 주세요. 지원된다면 optimization_inspect로 이미 저장된 캠페인 ${data.id}의 고정 계획을 읽고 optimization_run({campaign_id: "${data.id}"})으로 이 계획 하나를 실행해 주세요. 후보는 기존 수치 엔진이 생성합니다. 새 계획·원시 설정·변수·하중·재료를 만들거나 대체하지 마세요. 지원되지 않으면 실행하지 말고 필요한 연결 범위를 설명해 주세요. 실제 반환한 후보 CAD·해석 ID와 각 analysis_conditions_context를 읽고, 실패·미확인 항목과 가설을 구별할 응답을 설명해 주세요.` :
        "선택하지 않은 후보도 실패·미확인 기록이 남아 있음을 고려하고, 수치 탐색의 완료를 전역 최적해나 유일한 원인 또는 제작 승인으로 해석하지 마세요. 새 계산·최적화 실행 없이 저장된 근거에서 가설을 구별할 응답·잔차와 다음 실험에 필요한 측정·조건을 제안해 주세요.",
      "수치 탐색의 완료를 전역 최적해·유일한 원인·제작 승인으로 바꾸지 마세요."
    ].join("\n\n");
    requireValue(new TextEncoder().encode(question).length <= 16384, "연구 질문이 기존 16 KiB 입력 범위를 넘었습니다. 후보 수와 조건 설명을 줄이세요.");
    return { question, studyId, campaignId: data.id, conditionsId, sourceExperimentId, intent: planned ? "RUN_SAVED_OPTIMIZATION" : "INTERPRET_SAVED_RESULTS",
      candidateIndexes: [...indexes], experimentIds: [...new Set(references.map(item => item.experimentId))] };
  }
  const api = { draft, declarationLines, campaignDraft };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.comparisonResearch = api;
})(typeof window !== "undefined" ? window : globalThis);
