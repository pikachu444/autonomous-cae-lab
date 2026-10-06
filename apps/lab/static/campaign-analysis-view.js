"use strict";

// Display the saved numerical sample analysis, never fit/recompute it here.
// Core owns receipt/cryptographic/source validation. Optional caller pins join
// the response to the context captured before its asynchronous read.
(function (root) {
  const envelopeKeys = ["schema_version", "integrity", "report_id", "campaign_id", "study_id", "report_sha256", "source", "declaration", "analysis", "decision", "engineering_qualification",
    "variables", "samples", "seed", "created_utc", "provenance"];
  const responseKeys = ["metric", "unit", "direction"];
  const pinKeys = ["report_id", "campaign_id", "study_id", "plan_sha256", "result_sha256", "report_sha256"];
  const storeId = /^[A-Za-z][A-Za-z0-9_-]{0,79}$/;
  const parameterId = /^[A-Za-z][A-Za-z0-9_-]{0,63}$/;
  const sha256 = /^[0-9a-f]{64}$/;
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
  const exact = (value, names) => object(value) && Object.keys(value).length === names.length && names.every(key => own(value, key));
  const finite = value => typeof value === "number" && Number.isFinite(value);
  const nullable = value => value === null || finite(value);
  const integer = value => Number.isSafeInteger(value) && value >= 0;
  const text = (value, max = 2000) => typeof value === "string" && value.trim().length > 0 && Array.from(value).length <= max;
  const safeKey = value => !["__proto__", "prototype", "constructor"].includes(value);
  const id = value => typeof value === "string" && safeKey(value) && storeId.exec(value)?.[0] === value;
  const parameter = value => typeof value === "string" && safeKey(value) && parameterId.exec(value)?.[0] === value;
  const digest = value => typeof value === "string" && value.length === 64 && sha256.test(value);
  const numberText = value => value === null ? "사용 불가" : Object.is(value, -0) ? "-0" : String(value);
  function displayNumber(value) {
    if (value === null || Object.is(value, -0)) return numberText(value);
    const [mantissa, exponent] = value.toPrecision(6).split("e");
    const compact = mantissa.includes(".") ? mantissa.replace(/0+$/, "").replace(/\.$/, "") : mantissa;
    return exponent === undefined ? compact : `${compact}e${exponent}`;
  }
  // Human-readable JSON projection, not the original artifact bytes. Keep the
  // full round-trip numeric representation, including negative zero, in details.
  function rawData(value, depth = 0) {
    if (finite(value)) return numberText(value);
    if (!object(value) && !Array.isArray(value)) return JSON.stringify(value);
    const array = Array.isArray(value), entries = array ? value.map(item => rawData(item, depth + 1)) :
      Object.entries(value).map(([key, item]) => `${JSON.stringify(key)}: ${rawData(item, depth + 1)}`);
    const [open, close] = array ? ["[", "]"] : ["{", "}"];
    return entries.length ? `${open}\n${"  ".repeat(depth + 1)}${entries.join(`,\n${"  ".repeat(depth + 1)}`)}\n${"  ".repeat(depth)}${close}` : `${open}${close}`;
  }
  function demand(condition, message) { if (!condition) throw new Error(message); }
  function constructorName(prototype) {
    const constructor = prototype && Object.getOwnPropertyDescriptor(prototype, "constructor")?.value;
    return typeof constructor === "function" ? Object.getOwnPropertyDescriptor(constructor, "name")?.value : null;
  }
  function ordinaryObjectPrototype(prototype) {
    return prototype !== null && Object.getPrototypeOf(prototype) === null && constructorName(prototype) === "Object";
  }
  function json(value, ancestors = new Set(), depth = 0) {
    if (depth > 64) return false;
    if (value === null || ["string", "boolean"].includes(typeof value)) return true;
    if (typeof value === "number") return Number.isFinite(value);
    if ((!Array.isArray(value) && !object(value)) || ancestors.has(value)) return false;
    const prototype = Object.getPrototypeOf(value);
    if (Array.isArray(value) ? prototype !== Array.prototype && !(Array.isArray(prototype) && constructorName(prototype) === "Array" &&
        ordinaryObjectPrototype(Object.getPrototypeOf(prototype))) : prototype !== null && prototype !== Object.prototype && !ordinaryObjectPrototype(prototype)) return false;
    const names = Reflect.ownKeys(value).filter(key => !(Array.isArray(value) && key === "length"));
    if (names.some(key => {
      const property = Object.getOwnPropertyDescriptor(value, key);
      return typeof key !== "string" || ["__proto__", "prototype", "constructor"].includes(key) || !property.enumerable || !own(property, "value");
    }) || (Array.isArray(value) && (names.length !== value.length || names.some((key, index) => key !== String(index))))) return false;
    ancestors.add(value); const valid = names.every(key => json(value[key], ancestors, depth + 1)); ancestors.delete(value); return valid;
  }
  function clone(value) {
    if (Array.isArray(value)) return value.map(clone);
    if (object(value)) return Object.fromEntries(Object.keys(value).map(key => [key, clone(value[key])]));
    return value;
  }
  function strings(values) { return Array.isArray(values) && values.every(value => text(value, 4096)); }
  function uniqueIds(values, available = null) {
    return Array.isArray(values) && values.every(id) && new Set(values).size === values.length &&
      (available === null || values.every(value => available.has(value)));
  }
  function definitions(values) {
    return Array.isArray(values) && values.length > 0 && values.length <= 16 && values.every(value => exact(value, responseKeys) && text(value.metric, 128) && safeKey(value.metric) && text(value.unit, 128) &&
      ["minimize", "maximize"].includes(value.direction)) && new Set(values.map(value => value.metric)).size === values.length;
  }
  function variablesValid(values) {
    return Array.isArray(values) && values.length > 0 && values.length <= 16 && values.every(value => object(value) && parameter(value.parameter_id) &&
      text(value.display_name, 2000) && text(value.unit, 128) && finite(value.lower_bound) && finite(value.upper_bound) &&
      value.lower_bound < value.upper_bound && finite(value.upper_bound - value.lower_bound)) &&
      new Set(values.map(value => value.parameter_id)).size === values.length;
  }
  function sampleValid(row, variables, declared) {
    return exact(row, ["id", "values", "responses", "usable"]) && id(row.id) && typeof row.usable === "boolean" &&
      exact(row.values, [...variables.keys()]) && Object.entries(row.values).every(([key, value]) => finite(value) &&
        variables.get(key).lower_bound <= value && value <= variables.get(key).upper_bound) &&
      exact(row.responses, [...declared.keys()]) && Object.entries(row.responses).every(([key, value]) =>
        exact(value, ["value", "unit", "valid"]) && value.unit === declared.get(key).unit && typeof value.valid === "boolean" &&
        (value.valid ? finite(value.value) : nullable(value.value)));
  }
  function sameIds(values, available) { return uniqueIds(values, available) && values.length === available.size; }
  function validReason(row) { return row.valid === true ? row.reason === null : row.valid === false && text(row.reason); }
  function metricRow(row, declared) { return object(row) && declared.has(row.metric) && row.unit === declared.get(row.metric).unit; }
  function statisticsValid(row, declared, count) {
    if (!exact(row, ["metric", "unit", "count", "mean", "std", "min", "max", "quantiles"]) || !metricRow(row, declared) ||
      !integer(row.count) || row.count > count || !exact(row.quantiles, ["q05", "q50", "q95"])) return false;
    const values = [row.mean, row.min, row.max, ...Object.values(row.quantiles)];
    return row.count === 0 ? values.every(value => value === null) && row.std === null : values.every(finite) &&
      (row.count === 1 ? row.std === null : finite(row.std) && row.std >= 0) && row.min <= row.max;
  }
  function sensitivityValid(row, declared, ids, variables) {
    if (!exact(row, ["metric", "unit", "method", "valid", "reason", "rank", "condition_number", "coefficients", "sample_ids", "intercept", "response_mean", "response_std"]) ||
      !metricRow(row, declared) || row.method !== "NORMALIZED_MULTIVARIATE_LEAST_SQUARES" || !validReason(row) || !integer(row.rank) ||
      !nullable(row.condition_number) || (row.condition_number !== null && row.condition_number <= 0) || !sameIds(row.sample_ids, ids) || row.rank > row.sample_ids.length ||
      ![row.intercept, row.response_mean, row.response_std].every(nullable) || (row.response_std !== null && row.response_std < 0) ||
      !Array.isArray(row.coefficients) || !row.coefficients.every(value => exact(value, ["parameter_id", "unit", "parameter_unit", "coefficient"]) &&
        variables.has(value.parameter_id) && value.unit === "1" && value.parameter_unit === variables.get(value.parameter_id).unit && finite(value.coefficient)) ||
      new Set(row.coefficients.map(value => value.parameter_id)).size !== row.coefficients.length) return false;
    return row.valid === false ? row.coefficients.length === 0 : row.coefficients.length === variables.size && row.rank > 0 && finite(row.condition_number) &&
      finite(row.intercept) && finite(row.response_mean) && finite(row.response_std);
  }
  function surrogateValid(row, declared, ids, variables, seed) {
    if (!exact(row, ["metric", "unit", "method", "model", "train_ids", "test_ids", "rank", "condition_number", "features", "coefficients", "normalization",
      "test_mae", "test_rmse", "test_max_error", "valid", "reason", "seed", "limitations"]) || !metricRow(row, declared) ||
      row.method !== "SEEDED_HOLDOUT_LEAST_SQUARES" || !["affine", "quadratic", null].includes(row.model) || !validReason(row) ||
      !uniqueIds(row.train_ids, ids) || !uniqueIds(row.test_ids, ids) || !sameIds([...row.train_ids, ...row.test_ids], ids) ||
      !integer(row.rank) || row.rank > row.train_ids.length || !nullable(row.condition_number) || (row.condition_number !== null && row.condition_number <= 0) ||
      row.seed !== seed || !strings(row.limitations) ||
      ![row.test_mae, row.test_rmse, row.test_max_error].every(value => nullable(value) && (value === null || value >= 0)) ||
      !Array.isArray(row.normalization) || !row.normalization.every(value => exact(value, ["parameter_id", "unit", "lower_bound", "upper_bound"]) &&
        variables.has(value.parameter_id) && value.unit === variables.get(value.parameter_id).unit && value.lower_bound === variables.get(value.parameter_id).lower_bound &&
        value.upper_bound === variables.get(value.parameter_id).upper_bound) ||
      new Set(row.normalization.map(value => value.parameter_id)).size !== variables.size || row.normalization.length !== variables.size) return false;
    const parameters = new Set(row.normalization.map(value => value.parameter_id));
    if (!Array.isArray(row.features) || !row.features.every(value => exact(value, ["id", "powers"]) && parameter(value.id) && object(value.powers) &&
      Object.entries(value.powers).every(([key, power]) => parameters.has(key) && [1, 2].includes(power)) &&
      Object.values(value.powers).reduce((sum, power) => sum + power, 0) <= (row.model === "affine" ? 1 : 2)) ||
      new Set(row.features.map(value => value.id)).size !== row.features.length || !Array.isArray(row.coefficients) ||
      !row.coefficients.every(value => exact(value, ["feature_id", "value", "unit"]) && row.features.some(feature => feature.id === value.feature_id) &&
        finite(value.value) && value.unit === row.unit) || new Set(row.coefficients.map(value => value.feature_id)).size !== row.coefficients.length) return false;
    return row.valid === false ? row.coefficients.length === 0 && [row.test_mae, row.test_rmse, row.test_max_error].every(value => value === null) :
      row.model !== null && row.normalization.length > 0 && row.features.length > 0 && row.rank === row.features.length && row.coefficients.length === row.features.length &&
      row.test_ids.length > 0 && finite(row.condition_number) && [row.test_mae, row.test_rmse, row.test_max_error].every(finite);
  }
  function pins(envelope, expected) {
    if (expected === undefined) return [];
    demand(json(expected) && object(expected) && Object.keys(expected).length > 0 && Object.keys(expected).every(key => pinKeys.includes(key)),
      "선택 문맥 pin에는 명시한 보고서·캠페인·연구 ID와 source SHA만 사용할 수 있습니다.");
    for (const key of Object.keys(expected)) {
      const actual = ["plan_sha256", "result_sha256"].includes(key) ? envelope.source[key] : envelope[key];
      demand((key.endsWith("_sha256") ? digest(expected[key]) : id(expected[key])) && expected[key] === actual,
        "보고서의 선택 문맥 ID·SHA가 요청 전에 보존한 pin과 다릅니다. 다른 캠페인의 응답을 표시할 수 없습니다.");
    }
    return Object.keys(expected);
  }
  function summary(envelope, expected) {
    demand(json(envelope) && exact(envelope, envelopeKeys) && envelope.schema_version === "1.0" && envelope.integrity === "VERIFIED" &&
      [envelope.report_id, envelope.campaign_id, envelope.study_id].every(id) && digest(envelope.report_sha256) &&
      envelope.decision === "NOT_RELEASED" && envelope.engineering_qualification === "UNKNOWN" &&
      integer(envelope.seed) && envelope.seed <= 2 ** 32 - 1 && text(envelope.created_utc, 128) && object(envelope.provenance) && Object.keys(envelope.provenance).length > 0,
    "같은 원 캠페인에 연결된 Core VERIFIED 수치 표본 보고서와 미검증 자격을 확인할 수 없습니다.");
    const source = envelope.source, declaration = envelope.declaration, analysis = envelope.analysis;
    demand(exact(source, ["type", "plan_sha256", "result_sha256", "experiment_ids", "experiment_result_sha256", "sample_ids"]) && ["doe", "optimization"].includes(source.type) &&
      digest(source.plan_sha256) && digest(source.result_sha256) && uniqueIds(source.experiment_ids) && uniqueIds(source.sample_ids) &&
      uniqueIds(source.experiment_ids, new Set(source.sample_ids)) && exact(source.experiment_result_sha256, source.experiment_ids) &&
      Object.values(source.experiment_result_sha256).every(digest),
    "원 캠페인의 종류·계획/결과 SHA·표본 ID와 실제 native 실험/결과 SHA 연결이 필요합니다.");
    demand(exact(declaration, ["purpose", "origin", "reference", "response_definitions", "uncertainty"]) && text(declaration.purpose, 4096) && text(declaration.reference, 2048) &&
      ["MEASURED_REPORTED", "PUBLISHED_REFERENCE", "SYNTHETIC", "DESIGN_EXPLORATION"].includes(declaration.origin) && definitions(declaration.response_definitions) &&
      exact(declaration.uncertainty, ["interpretation", "reference"]) && ["DESIGN_SPACE_ONLY", "USER_DECLARED_UNIFORM_INPUTS"].includes(declaration.uncertainty.interpretation) &&
      text(declaration.uncertainty.reference, 2048) && (declaration.uncertainty.interpretation !== "USER_DECLARED_UNIFORM_INPUTS" || source.type === "doe"),
    "원 연구 목적·출처·응답/단위/방향·불확실 입력의 사용자 선언을 확인하세요.");
    demand(exact(analysis, ["statistics", "sensitivity", "surrogate", "pareto", "exclusions", "qualification", "decision", "limitations"]) &&
      analysis.qualification === "NUMERICAL_SAMPLE_ANALYSIS_ONLY" && analysis.decision === "NOT_RELEASED" && strings(analysis.limitations),
    "수치 표본 분석의 원 자격·미배포 판정·분석 한계가 필요합니다.");
    demand(variablesValid(envelope.variables), "선택한 원 변수의 ID·표시명·단위·유한 bounds가 필요합니다.");
    const variables = new Map(envelope.variables.map(value => [value.parameter_id, value]));
    const ids = new Set(source.sample_ids), declared = new Map(declaration.response_definitions.map(value => [value.metric, value]));
    demand(Array.isArray(envelope.samples) && envelope.samples.length >= 2 && envelope.samples.length <= 512 && envelope.samples.length === source.sample_ids.length &&
      envelope.samples.every((row, index) => sampleValid(row, variables, declared) && row.id === source.sample_ids[index]),
    "표본의 원 ID 순서·변수 bounds·응답 값/단위/valid 연결이 불완전합니다.");
    const eligible = new Set(envelope.samples.filter(row => row.usable && Object.values(row.responses).every(value => value.valid)).map(row => row.id));
    demand([...eligible].every(value => source.experiment_ids.includes(value)), "유효 수치 표본의 원 native 결과가 없습니다.");
    for (const [key, validator] of [["statistics", row => statisticsValid(row, declared, eligible.size) && row.count === eligible.size],
      ["sensitivity", row => sensitivityValid(row, declared, eligible, variables)],
      ["surrogate", row => surrogateValid(row, declared, eligible, variables, envelope.seed)]]) {
      demand(Array.isArray(analysis[key]) && analysis[key].length === declared.size && analysis[key].every(validator) &&
        new Set(analysis[key].map(row => row.metric)).size === declared.size,
      "통계·민감도·보류 표본 예측의 실제 응답·단위·표본·유한 수치 또는 불가 사유가 불완전합니다.");
    }
    demand(exact(analysis.pareto, ["response_definitions", "nondominated_ids", "valid", "reason", "method"]) && definitions(analysis.pareto.response_definitions) &&
      analysis.pareto.response_definitions.length === declared.size && analysis.pareto.response_definitions.every(value => declared.has(value.metric) &&
        responseKeys.every(key => value[key] === declared.get(value.metric)[key])) && analysis.pareto.method === "EXACT_COMPONENTWISE_NONDOMINANCE" &&
      validReason(analysis.pareto) && uniqueIds(analysis.pareto.nondominated_ids, eligible) &&
      (analysis.pareto.valid ? analysis.pareto.nondominated_ids.length > 0 : analysis.pareto.nondominated_ids.length === 0) &&
      Array.isArray(analysis.exclusions) && analysis.exclusions.every(value => exact(value, ["id", "reason"]) && ids.has(value.id) && text(value.reason)),
    "Pareto archive와 제외 사유의 원 응답 방향·표본 ID 연결이 불완전합니다.");
    const excluded = new Set(analysis.exclusions.map(value => value.id));
    demand(excluded.size === analysis.exclusions.length && excluded.size + eligible.size === ids.size && [...excluded].every(value => !eligible.has(value)) &&
      analysis.pareto.nondominated_ids.every(value => !excluded.has(value)) && analysis.sensitivity.every(row => row.sample_ids.every(value => !excluded.has(value))) &&
      analysis.surrogate.every(row => [...row.train_ids, ...row.test_ids].every(value => !excluded.has(value))),
    "제외된 후보를 유효 표본·보류 검증 또는 Pareto archive로 표시할 수 없습니다.");
    return { ...clone(envelope), source_pin_check: { authority: "CORE_VERIFIED", matched_keys: pins(envelope, expected) } };
  }
  function render(container, envelope, expected) {
    demand(container?.ownerDocument && typeof container.ownerDocument.createElement === "function" && typeof container.replaceChildren === "function",
      "보고서를 표시할 DOM 영역을 확인하세요.");
    const doc = container.ownerDocument;
    function element(tag, value = null, className = "") {
      const node = doc.createElement(tag); if (className) node.className = className; if (value !== null) node.textContent = String(value); return node;
    }
    let view;
    try { view = summary(envelope, expected); }
    catch (error) { container.replaceChildren(element("p", `보고서 표시 불가 · ${error.message}`, "empty-state")); throw error; }
    const report = element("article", null, "campaign-detail"), { source, declaration, analysis } = view;
    function section(title, note = null) {
      const node = element("section", null, "separated"); node.append(element("h3", title));
      if (note) node.append(element("p", note, "hint")); report.append(node); return node;
    }
    function table(parent, headers, rows) {
      const scroll = element("div", null, "table-scroll"), node = element("table"), head = element("thead"), headRow = element("tr"), body = element("tbody");
      headers.forEach(header => headRow.append(element("th", header))); head.append(headRow); node.append(head);
      rows.forEach(values => { const row = element("tr"); values.forEach(value => row.append(element("td", value))); body.append(row); });
      node.append(body); scroll.append(node); parent.append(scroll);
    }
    function details(parent, title, lines) {
      const node = element("details", null, "advanced"); node.append(element("summary", title));
      lines.forEach(line => node.append(element("p", line, "hint"))); parent.append(node); return node;
    }
    function idsList(parent, title, values) {
      const node = details(parent, `${title} · ${values.length}개`, []), list = element("ul", null, "plain-list");
      values.forEach(value => list.append(element("li", value))); node.append(values.length ? list : element("p", "원 기록 없음", "hint")); return node;
    }
    report.append(element("h2", "캠페인 수치 표본 분석"), element("p", `${view.campaign_id} · ${view.study_id} · 보고서 ${view.report_id}`, "mono"),
      element("p", declaration.purpose), element("p", "이 수치 표본에서 추정한 분석이며 물리적 자격은 미검증입니다. NOT_RELEASED", "hint"));
    const origins = { MEASURED_REPORTED: "사용자 측정 보고 · 미검증", PUBLISHED_REFERENCE: "공개 참조", SYNTHETIC: "가상 데이터/기준", DESIGN_EXPLORATION: "설계 공간 탐색" };
    report.append(element("p", `입력 출처: ${origins[declaration.origin]}`), element("p", declaration.reference, "hint"));
    const uncertainty = declaration.uncertainty;
    report.append(element("p", uncertainty.interpretation === "DESIGN_SPACE_ONLY" ?
      "설계 공간 표본 · 확률 분포 해석 없음" : "계획 변수의 고정 범위에서 균등 불확실 입력 · 사용자 선언, 확률 자격 미검증", "hint"));
    if (uncertainty.reference) report.append(element("p", uncertainty.reference, "hint"));
    report.append(element("p", `원 표본 ${view.samples.length}개 · 실제 native 실험 ${source.experiment_ids.length}개 · 공통 유효 표본 ${analysis.statistics[0].count}개`, "hint"));
    const inputs = section("선택 변수와 원 표본", "실패 후보의 값과 제외 사유도 보존합니다. 원 표본 ID만으로 native 실행이나 물리적 적합성을 주장하지 않습니다.");
    table(inputs, ["변수", "ID", "단위", "계획 하한", "계획 상한"], view.variables.map(value =>
      [value.display_name, value.parameter_id, value.unit, displayNumber(value.lower_bound), displayNumber(value.upper_bound)]));
    const samples = details(inputs, `원 표본 값·응답 · ${view.samples.length}개`, []), excludedById = new Map(analysis.exclusions.map(value => [value.id, value.reason]));
    table(samples, ["원 표본 ID", "native 결과", ...view.variables.map(value => `${value.display_name} (${value.unit})`),
      ...declaration.response_definitions.map(value => `${value.metric} (${value.unit})`), "분석 포함"], view.samples.map(row =>
      [row.id, own(source.experiment_result_sha256, row.id) ? "native 결과 보존" : "native 결과 없음", ...view.variables.map(value => numberText(row.values[value.parameter_id])),
        ...declaration.response_definitions.map(value => {
          const response = row.responses[value.metric];
          return response.valid ? numberText(response.value) : `${numberText(response.value)} · 원 응답 invalid`;
        }), excludedById.has(row.id) ? `제외 · ${excludedById.get(row.id)}` : "공통 유효 표본"]));
    const native = details(inputs, `실제 native 실험·원 결과 SHA · ${source.experiment_ids.length}개`, []);
    if (source.experiment_ids.length) table(native, ["실제 실험 ID", "원 result SHA256"], source.experiment_ids.map(value => [value, source.experiment_result_sha256[value]]));
    else native.append(element("p", "원 native 결과 없음", "hint"));
    const statistics = section("응답 표본 통계", "표준편차는 표본 추정(ddof=1)입니다. q05/q50/q95는 선형 경험 분위수이며 신뢰구간이 아닙니다. 표의 수치는 약 6자리 유효숫자로 표시하며 원 수치는 상세에 보존합니다.");
    table(statistics, ["응답", "단위", "표본 수", "평균", "표준편차", "최소", "최대", "q05", "q50", "q95"], analysis.statistics.map(row =>
      [row.metric, row.unit, row.count, displayNumber(row.mean), row.count === 1 ? "표본 1개 · 추정 불가" : displayNumber(row.std), displayNumber(row.min), displayNumber(row.max),
        displayNumber(row.quantiles.q05), displayNumber(row.quantiles.q50), displayNumber(row.quantiles.q95)]));
    const rawStatistics = details(statistics, "원 통계 수치 · 전체 정밀도", []);
    rawStatistics.append(element("pre", rawData(analysis.statistics), "mono"));
    analysis.statistics.filter(row => row.count === 0).forEach(row => statistics.append(element("p", `${row.metric}: 유효한 원 수치 표본 없음`, "hint")));
    const sensitivity = section("변수와 응답의 선형 연관", "정규화 다변량 최소제곱 계수는 무차원입니다. 원 변수 단위를 함께 표시하며, 이 표본의 연관을 유일한 원인으로 해석하지 않습니다.");
    for (const row of analysis.sensitivity) {
      sensitivity.append(element("h4", `${row.metric} (${row.unit})`), element("p", row.valid ?
        `원 표본 ${row.sample_ids.length}개 · 행렬 랭크 ${row.rank} · 조건수 ${displayNumber(row.condition_number)}` : `분석 불가 · ${row.reason}`, "hint"));
      if (row.valid) table(sensitivity, ["변수", "원 단위", "부호 있는 정규화 계수", "계수 단위"], row.coefficients.map(value =>
        [value.parameter_id, value.parameter_unit, displayNumber(value.coefficient), value.unit]));
      const nativeSensitivity = details(sensitivity, "원 방법·응답 정규화·표본", [`${row.method} · 행렬 랭크 ${row.rank} · 조건수 ${numberText(row.condition_number)}`,
        `원 응답 평균 ${numberText(row.response_mean)} ${row.unit} · 표준편차 ${numberText(row.response_std)} ${row.unit}`,
        `정규화 절편 ${numberText(row.intercept)} · 원 표본: ${row.sample_ids.join(", ") || "없음"}`]);
      nativeSensitivity.append(element("pre", rawData(row), "mono"));
    }
    const surrogate = section("보류 표본 예측 오차", "같은 캠페인에서 분리한 실제 보류 표본의 오차입니다. 학습 범위 밖의 성능이나 물리적 정확도를 보장하지 않습니다.");
    table(surrogate, ["응답", "단위", "모델", "학습/보류 수", "MAE", "RMSE", "최대 절대 오차", "사용 상태"], analysis.surrogate.map(row =>
      [row.metric, row.unit, row.model === null ? "사용 불가" : row.model === "affine" ? "선형" : "2차", `${row.train_ids.length}/${row.test_ids.length}`,
        row.valid ? displayNumber(row.test_mae) : "사용 불가", row.valid ? displayNumber(row.test_rmse) : "사용 불가", row.valid ? displayNumber(row.test_max_error) : "사용 불가",
        row.valid ? "이 수치 표본 내 추정" : `사용 불가 · ${row.reason}`]));
    for (const row of analysis.surrogate) {
      const node = details(surrogate, `${row.metric} · 원 모델/표본/범위`, [`${row.method} · seed ${row.seed} · 행렬 랭크 ${row.rank} · 조건수 ${numberText(row.condition_number)}`,
        `학습: ${row.train_ids.join(", ") || "없음"}`, `보류: ${row.test_ids.join(", ") || "없음"}`, ...row.limitations]);
      table(node, ["변수", "원 단위", "정규화 하한", "정규화 상한"], row.normalization.map(value => [value.parameter_id, value.unit, numberText(value.lower_bound), numberText(value.upper_bound)]));
      table(node, ["기저 ID", "선언 항", "계수", "단위"], row.features.map(feature => {
        const coefficient = row.coefficients.find(value => value.feature_id === feature.id);
        const term = Object.entries(feature.powers).map(([key, power]) => power === 1 ? key : `${key}^${power}`).join(" × ") || "상수항";
        return [feature.id, term, row.valid && coefficient ? numberText(coefficient.value) : "사용 불가", row.unit];
      }));
      node.append(element("pre", rawData(row), "mono"));
    }
    const pareto = section("기존 표본의 비지배 후보 모음(Pareto)", "기존 표본의 비지배 후보를 모은 기록이며 다목적 최적화기가 아닙니다. 응답은 선언한 원 단위와 최소화/최대화 방향을 그대로 사용합니다.");
    table(pareto, ["응답", "단위", "선호 방향"], analysis.pareto.response_definitions.map(value => [value.metric, value.unit, value.direction === "minimize" ? "최소화" : "최대화"]));
    if (analysis.pareto.valid) idsList(pareto, "보존된 비지배 표본", analysis.pareto.nondominated_ids);
    else pareto.append(element("p", `사용 불가 · ${analysis.pareto.reason}`, "hint"));
    const exclusions = section("표본 제외 기록");
    if (analysis.exclusions.length) table(exclusions, ["원 표본 ID", "제외 이유"], analysis.exclusions.map(value => [value.id, value.reason]));
    else exclusions.append(element("p", "제외 기록 없음", "hint"));
    const limitations = section("분석 한계");
    limitations.append(element("p", "유효한 수치 표본에 한정된 분석입니다. 신뢰구간·고장 확률·인과관계·전역 최적성을 판정하지 않습니다.", "hint"),
      element("p", "보류 표본 오차는 해당 캠페인의 별도 표본에서 얻은 기술 통계입니다. 외삽·물리적 정확도·재료 자격은 미검증이며, 무효 표본은 0으로 대체하지 않습니다.", "hint"));
    details(limitations, "분석 한계 원문", analysis.limitations);
    details(report, "Core 검증과 원 source pins", [view.source_pin_check.matched_keys.length ?
      `Core VERIFIED · 제공된 선택 문맥 pin ${view.source_pin_check.matched_keys.length}개 일치 (${view.source_pin_check.matched_keys.join(", ")})` :
      "Core VERIFIED · 추가 선택 문맥 pin 대조 없음", `종류: ${source.type}`, `plan SHA256: ${source.plan_sha256}`, `result SHA256: ${source.result_sha256}`,
      `report SHA256: ${view.report_sha256}`, `생성: ${view.created_utc} · seed ${view.seed}`,
      "암호학적 검증은 Core가 수행합니다. 이 화면은 분석 수치나 source 해시를 새로 계산하지 않습니다."]);
    const provenance = details(report, "원 Core/변수 provenance", []);
    provenance.append(element("pre", rawData({ provenance: view.provenance, variables: view.variables }), "mono"));
    const rawReport = details(report, "원 보고서 데이터 · 전체 수치/원문", ["Core가 검증한 데이터의 표시용 JSON입니다. 원 artifact 파일 바이트나 해시를 새로 검증한 결과는 아닙니다."]);
    rawReport.append(element("pre", rawData(envelope), "mono"));
    container.replaceChildren(report);
    return view;
  }
  const api = Object.freeze({ render, summary });
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.campaignAnalysisView = api;
})(typeof window !== "undefined" ? window : globalThis);
