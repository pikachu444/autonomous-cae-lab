"use strict";

(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    const shared = require("./campaign-analysis-view.js");
    module.exports = factory(shared);
  } else if (typeof define === "function" && define.amd) define(["./campaign-analysis-view"], factory);
  else root.probabilityView = factory(root.campaignAnalysisView);
})(typeof window !== "undefined" ? window : globalThis, function (campaign) {
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
  const exact = (value, keys) => object(value) && Object.keys(value).length === keys.length && keys.every(key => own(value, key));
  const finite = value => typeof value === "number" && Number.isFinite(value);
  const integer = value => Number.isSafeInteger(value) && value >= 0;
  const nullable = value => value === null || finite(value);
  const text = (value, max = 2000) => typeof value === "string" && value.trim().length > 0 && Array.from(value).length <= max && !/[\x00-\x1f]/.test(value);
  const safeKey = value => !["__proto__", "prototype", "constructor"].includes(value);
  const identifier = (value, pattern) => typeof value === "string" && safeKey(value) && pattern.exec(value)?.[0] === value;
  const id = value => identifier(value, /^[A-Za-z][A-Za-z0-9_-]{0,79}$/);
  const parameter = value => identifier(value, /^[A-Za-z][A-Za-z0-9_-]{0,63}$/);
  const metric = value => identifier(value, /^[A-Za-z][A-Za-z0-9_.-]{0,127}$/);
  const unitRatio = value => finite(value) && value >= 0 && value <= 1;
  const analysisKeys = ["schema_version", "declaration", "samples", "sample_ids", "valid_sample_ids", "counts", "statistics", "thresholds", "exclusions",
    "qualification", "physical", "engineering", "decision", "limitations", "source_sampling"];
  const designKeys = ["marginals", "independence", "source", "sample_ids", "seed", "schema_version", "sample_count", "sampling", "samples"];
  const thresholdKeys = ["id", "metric", "unit", "operator", "value"];
  const estimateKeys = [...thresholdKeys, "predicate", "signed_scalar", "exceedance_count", "n_valid", "n_excluded", "probability_estimate", "conditioning", "valid", "reason",
    "confidence_interval", "confidence_interval_reason", "unknown_outcome_fraction_bounds"];
  function demand(value, message) { if (!value) throw new Error(message); }
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
    const keys = Reflect.ownKeys(value).filter(key => !(Array.isArray(value) && key === "length"));
    if (keys.some(key => {
      const property = Object.getOwnPropertyDescriptor(value, key);
      return typeof key !== "string" || !safeKey(key) || !property.enumerable || !own(property, "value");
    }) || (Array.isArray(value) && (keys.length !== value.length || keys.some((key, index) => key !== String(index))))) return false;
    ancestors.add(value); const valid = keys.every(key => json(value[key], ancestors, depth + 1)); ancestors.delete(value); return valid;
  }
  function clone(value) {
    if (Array.isArray(value)) return value.map(clone);
    return object(value) ? Object.fromEntries(Object.entries(value).map(([key, item]) => [key, clone(item)])) : value;
  }
  function equal(left, right) {
    if (typeof left === "number" && typeof right === "number") return Object.is(left, right);
    if (left === right) return true;
    if (Array.isArray(left) || Array.isArray(right)) return Array.isArray(left) && Array.isArray(right) && left.length === right.length && left.every((value, index) => equal(value, right[index]));
    return object(left) && object(right) && exact(right, Object.keys(left)) && Object.entries(left).every(([key, value]) => equal(value, right[key]));
  }
  function ids(values, available = null) {
    return Array.isArray(values) && values.every(id) && new Set(values).size === values.length && (available === null || values.every(value => available.has(value)));
  }
  function designValid(declaration, input, report) {
    if (!exact(declaration, designKeys) || declaration.schema_version !== "1.0" || declaration.independence !== "INDEPENDENT_USER_DECLARED" ||
      !integer(declaration.seed) || declaration.seed > 2 ** 32 - 1 || !integer(declaration.sample_count) || declaration.sample_count !== report.samples.length ||
      !equal(declaration.sample_ids, report.source.sample_ids) || !ids(declaration.sample_ids) || !equal(declaration.marginals, input.marginals) ||
      declaration.independence !== input.independence || !equal(declaration.source, input.source) ||
      !exact(declaration.sampling, ["engine", "version", "numpy_version", "strength", "optimization", "randomization"]) ||
      declaration.sampling.engine !== "scipy.latin_hypercube" || !text(declaration.sampling.version, 128) || !text(declaration.sampling.numpy_version, 128) ||
      declaration.sampling.strength !== 1 || declaration.sampling.optimization !== null || declaration.sampling.randomization !== "SCRAMBLED_STRATIFIED" ||
      !Array.isArray(declaration.samples) || declaration.samples.length !== declaration.sample_count) return false;
    const variables = new Map(report.variables.map(row => [row.parameter_id, row]));
    if (!Array.isArray(declaration.marginals) || declaration.marginals.length !== variables.size || declaration.marginals.length > 16 ||
      !declaration.marginals.every(row => exact(row, ["parameter_id", "unit", "distribution", "lower_bound", "upper_bound"]) && parameter(row.parameter_id) &&
        variables.has(row.parameter_id) && row.distribution === "uniform" && row.unit === variables.get(row.parameter_id).unit && text(row.unit, 128) &&
        finite(row.lower_bound) && finite(row.upper_bound) && row.lower_bound < row.upper_bound && finite(row.upper_bound - row.lower_bound) &&
        row.lower_bound === variables.get(row.parameter_id).lower_bound && row.upper_bound === variables.get(row.parameter_id).upper_bound) ||
      new Set(declaration.marginals.map(row => row.parameter_id)).size !== variables.size || !exact(declaration.source, ["origin", "reference"]) ||
      !["ASSUMED", "MEASURED_REPORTED", "PUBLISHED_REFERENCE", "SYNTHETIC"].includes(declaration.source.origin) || !text(declaration.source.reference)) return false;
    return declaration.samples.every((point, index) => exact(point, ["id", "index", "values"]) && point.id === declaration.sample_ids[index] &&
      point.index === index + 1 && exact(point.values, [...variables.keys()]) && equal(point.values, report.samples[index].values));
  }
  function thresholdDefinition(row, declared) {
    return exact(row, thresholdKeys) && id(row.id) && metric(row.metric) && declared.has(row.metric) && row.unit === declared.get(row.metric).unit &&
      text(row.unit, 128) && [">", ">=", "<", "<="].includes(row.operator) && finite(row.value);
  }
  function predicateValid(row) {
    if (!text(row.predicate, 512)) return false;
    const prefix = `${row.metric} ${row.operator} `, suffix = ` ${row.unit}`;
    if (!row.predicate.startsWith(prefix) || !row.predicate.endsWith(suffix)) return false;
    const scalar = row.predicate.slice(prefix.length, -suffix.length);
    return /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(scalar) && Object.is(Number(scalar), row.value);
  }
  function responseValid(row, original, unit) {
    return object(row) && [3, 4].includes(Object.keys(row).length) && ["value", "unit", "valid"].every(key => own(row, key)) &&
      Object.keys(row).every(key => ["value", "unit", "valid", "reason"].includes(key)) && row.unit === unit && typeof row.valid === "boolean" &&
      (row.valid ? finite(row.value) : nullable(row.value)) && ["value", "unit", "valid"].every(key => equal(row[key], original[key])) &&
      (!own(row, "reason") || row.reason === null || text(row.reason));
  }
  function statisticsValid(row, declared, count) {
    if (!exact(row, ["metric", "unit", "count", "mean", "std", "min", "max", "quantiles"]) || !declared.has(row.metric) || row.unit !== declared.get(row.metric) ||
      row.count !== count || !exact(row.quantiles, ["q05", "q50", "q95"])) return false;
    const values = [row.mean, row.min, row.max, ...Object.values(row.quantiles)];
    return count === 0 ? row.std === null && values.every(value => value === null) : values.every(finite) && row.min <= row.max &&
      (count === 1 ? row.std === null : finite(row.std) && row.std >= 0);
  }
  function summary(report, expected) {
    demand(json(report) && object(report), "원 확률 보고서는 안전한 유한 JSON 데이터여야 합니다.");
    demand(typeof campaign?.summary === "function", "campaignAnalysisView 검증 helper를 먼저 연결해야 합니다.");
    const base = clone(report); delete base.probability_analysis;
    if (object(base.declaration)) delete base.declaration.probability;
    const verified = campaign.summary(base, expected), input = report.declaration.probability, analysis = report.probability_analysis;
    if (analysis === undefined || analysis === null) {
      demand(input === undefined || input === null, "선언한 확률 조건에 연결된 저장 분석이 없습니다.");
      return null;
    }
    demand(verified.source.type === "doe" && exact(input, ["marginals", "independence", "source", "thresholds"]) && exact(analysis, analysisKeys) &&
      analysis.schema_version === "1.0" && analysis.qualification === "DECLARED_UNIFORM_NUMERICAL_PROBABILITY_PROPAGATION_ONLY" &&
      analysis.physical === "UNKNOWN" && analysis.engineering === "UNKNOWN" && analysis.decision === "NOT_RELEASED" &&
      Array.isArray(analysis.limitations) && analysis.limitations.every(value => text(value, 4096)) && designValid(analysis.declaration, input, verified),
    "같은 원 DOE의 명시적 균등 분포·출처·표본/입력·미검증 자격 연결을 확인할 수 없습니다.");
    const sampling = analysis.source_sampling, design = analysis.declaration;
    demand(exact(sampling, ["algorithm", "plan_sha256", "result_sha256", "replay"]) &&
      sampling.plan_sha256 === verified.source.plan_sha256 && sampling.result_sha256 === verified.source.result_sha256 &&
      sampling.replay === "EXACT_CURRENT_SCIPY_NUMPY_VERSION_ONLY" &&
      equal(sampling.algorithm, { engine: design.sampling.engine, version: design.sampling.version,
        numpy_version: design.sampling.numpy_version, strength: design.sampling.strength,
        optimization: design.sampling.optimization, seed: design.seed }),
    "균등 분포 재생은 같은 원 DOE의 계획·결과·sampler 버전·seed에 연결되어야 합니다.");
    const responseDefinitions = new Map(verified.declaration.response_definitions.map(row => [row.metric, row]));
    demand(Array.isArray(input.thresholds) && input.thresholds.length >= 1 && input.thresholds.length <= 16 && input.thresholds.every(row => thresholdDefinition(row, responseDefinitions)) &&
      new Set(input.thresholds.map(row => row.id)).size === input.thresholds.length, "원 응답의 부호 있는 scalar 임계값·단위·연산자·서로 다른 조건 ID가 필요합니다.");
    const units = new Map(input.thresholds.map(row => [row.metric, row.unit])), originals = new Map(verified.samples.map(row => [row.id, row]));
    demand(equal(analysis.sample_ids, analysis.declaration.sample_ids) && Array.isArray(analysis.samples) && analysis.samples.length === analysis.sample_ids.length &&
      analysis.samples.every((row, index) => exact(row, ["id", "values", "responses", "usable"]) && row.id === analysis.sample_ids[index] &&
        equal(row.values, originals.get(row.id)?.values) && typeof row.usable === "boolean" && row.usable === originals.get(row.id)?.usable &&
        exact(row.responses, [...units.keys()]) && [...units].every(([key, unit]) => responseValid(row.responses[key], originals.get(row.id).responses[key], unit))),
    "확률 표본의 실제 ID·입력·원 signed scalar/단위/valid 연결이 다릅니다.");
    const validIds = analysis.samples.filter(row => row.usable && Object.values(row.responses).every(response => response.valid)).map(row => row.id);
    demand(equal(analysis.valid_sample_ids, validIds) && ids(analysis.valid_sample_ids, new Set(verified.source.experiment_ids)) &&
      exact(analysis.counts, ["declared", "valid", "excluded"]) && Object.values(analysis.counts).every(integer) && analysis.counts.declared === analysis.sample_ids.length &&
      analysis.counts.valid === validIds.length && analysis.counts.excluded + validIds.length === analysis.counts.declared &&
      Array.isArray(analysis.exclusions) && analysis.exclusions.length === analysis.counts.excluded,
    "유효 표본·실제 native 결과·제외 수의 연결이 다릅니다.");
    const excludedRows = analysis.samples.filter(row => !validIds.includes(row.id));
    demand(analysis.exclusions.every((row, index) => exact(row, ["id", "reason"]) && row.id === excludedRows[index].id && text(row.reason) &&
      row.reason === (excludedRows[index].usable ? `INVALID_RESPONSE:${[...units.keys()].filter(key => !excludedRows[index].responses[key].valid).join(",")}` : "ROW_UNUSABLE")),
    "미지 결과의 원 제외 ID·사유가 누락되거나 다른 유효 표본에 연결되었습니다.");
    demand(Array.isArray(analysis.thresholds) && analysis.thresholds.length === input.thresholds.length && analysis.thresholds.every((row, index) =>
      exact(row, estimateKeys) && thresholdKeys.every(key => equal(row[key], input.thresholds[index][key])) && predicateValid(row) && row.signed_scalar === true &&
      row.n_valid === analysis.counts.valid && row.n_excluded === analysis.counts.excluded && integer(row.exceedance_count) && row.exceedance_count <= row.n_valid &&
      row.conditioning === "VALID_NUMERICAL_ROWS_ONLY" && row.confidence_interval === null && row.confidence_interval_reason === "LHS_STRATIFIED_DEPENDENT_NOT_IID_BINOMIAL" &&
      exact(row.unknown_outcome_fraction_bounds, ["lower", "upper"]) && Object.values(row.unknown_outcome_fraction_bounds).every(unitRatio) &&
      row.unknown_outcome_fraction_bounds.lower <= row.unknown_outcome_fraction_bounds.upper &&
      (row.n_valid > 0 ? row.valid === true && row.reason === null && unitRatio(row.probability_estimate) : row.valid === false && row.probability_estimate === null &&
        row.exceedance_count === 0 && row.reason === "NO_VALID_NUMERICAL_RESPONSES")),
    "원 scalar 조건·표본 수·비율 또는 미지 결과의 유한 표본 범위가 불완전합니다. LHS 신뢰구간을 추정할 수 없습니다.");
    demand(Array.isArray(analysis.statistics) && analysis.statistics.length === units.size && analysis.statistics.every(row => statisticsValid(row, units, validIds.length)) &&
      new Set(analysis.statistics.map(row => row.metric)).size === units.size, "원 단위의 경험 통계·nullable 수치·유효 표본 수가 불완전합니다.");
    return { ...clone(analysis), report_context: { report_id: verified.report_id, campaign_id: verified.campaign_id, study_id: verified.study_id,
      report_sha256: verified.report_sha256, source_pin_check: clone(verified.source_pin_check) } };
  }
  const numberText = value => value === null ? "사용 불가" : Object.is(value, -0) ? "-0" : String(value);
  function displayNumber(value) {
    if (value === null || Object.is(value, -0)) return numberText(value);
    const [mantissa, exponent] = value.toPrecision(6).split("e"), compact = mantissa.includes(".") ? mantissa.replace(/0+$/, "").replace(/\.$/, "") : mantissa;
    return exponent === undefined ? compact : `${compact}e${exponent}`;
  }
  function rawData(value, depth = 0) {
    if (finite(value)) return numberText(value);
    if (!object(value) && !Array.isArray(value)) return JSON.stringify(value);
    const array = Array.isArray(value), entries = array ? value.map(item => rawData(item, depth + 1)) :
      Object.entries(value).map(([key, item]) => `${JSON.stringify(key)}: ${rawData(item, depth + 1)}`), [open, close] = array ? ["[", "]"] : ["{", "}"];
    return entries.length ? `${open}\n${"  ".repeat(depth + 1)}${entries.join(`,\n${"  ".repeat(depth + 1)}`)}\n${"  ".repeat(depth)}${close}` : `${open}${close}`;
  }
  function render(container, report, expected) {
    demand(container?.ownerDocument && typeof container.ownerDocument.createElement === "function" && typeof container.replaceChildren === "function", "확률 보고서를 표시할 DOM 영역을 확인하세요.");
    const doc = container.ownerDocument;
    function element(tag, value = null, className = "") {
      const node = doc.createElement(tag); if (className) node.className = className; if (value !== null) node.textContent = String(value); return node;
    }
    let view;
    try { view = summary(report, expected); }
    catch (error) { container.replaceChildren(element("p", `확률 분석 표시 불가 · ${error.message}`, "empty-state")); throw error; }
    if (view === null) { container.replaceChildren(); return null; }
    const article = element("article", null, "campaign-detail"), declaration = view.declaration, context = view.report_context;
    const origins = { ASSUMED: "가정", MEASURED_REPORTED: "사용자 측정 보고 · 미검증", PUBLISHED_REFERENCE: "공개 참조", SYNTHETIC: "가상 데이터/기준" };
    article.append(element("h2", "선언 분포의 수치 표본과 조건 충족 비율"), element("p", `${context.campaign_id} · ${context.study_id} · 보고서 ${context.report_id}`, "mono"),
      element("p", "실측 불량 확률 아님 · 선언 분포의 수치 표본 · 물리/공학 자격 UNKNOWN · NOT_RELEASED", "hint"),
      element("p", `분포 출처: ${origins[declaration.source.origin]} (${declaration.source.origin})`), element("p", declaration.source.reference, "hint"),
      element("p", `독립 균등 분포 · 사용자 선언 · seed ${declaration.seed} · LHS 표본 ${view.counts.declared}개 / 유효 ${view.counts.valid}개 / 제외 ${view.counts.excluded}개`, "hint"));
    function section(title, note = null) {
      const node = element("section", null, "separated"); node.append(element("h3", title)); if (note) node.append(element("p", note, "hint")); article.append(node); return node;
    }
    function table(parent, headers, rows) {
      const scroll = element("div", null, "table-scroll"), node = element("table"), head = element("thead"), header = element("tr"), body = element("tbody");
      headers.forEach(value => header.append(element("th", value))); head.append(header); node.append(head);
      rows.forEach(values => { const row = element("tr"); values.forEach(value => row.append(element("td", value))); body.append(row); });
      node.append(body); scroll.append(node); parent.append(scroll);
    }
    function details(parent, title) { const node = element("details", null, "advanced"); node.append(element("summary", title)); parent.append(node); return node; }
    const marginals = section("선언 입력 분포", "분포 범위와 독립성은 사용자 선언이며, 수치 표본으로 실측 분포를 식별한 결과가 아닙니다.");
    table(marginals, ["원 변수 ID", "분포", "단위", "하한", "상한"], declaration.marginals.map(row => [row.parameter_id, "균등", row.unit, displayNumber(row.lower_bound), displayNumber(row.upper_bound)]));
    const estimates = section("부호 있는 원 응답의 조건 충족", "비율은 유효 수치 표본에만 조건부입니다. 미지 결과 포함 범위는 이번 유한 표본의 하한·상한이며, 모집단 확률 범위나 신뢰구간이 아닙니다.");
    table(estimates, ["원 조건", "단위", "충족/유효 수", "유효 표본 비율", "제외 수", "미지 결과 포함 범위"], view.thresholds.map(row =>
      [`${row.id} · ${row.metric} ${row.operator} ${numberText(row.value)}`, row.unit, `${row.exceedance_count}/${row.n_valid}`,
        row.valid ? displayNumber(row.probability_estimate) : "사용 불가 · 유효 수치 응답 없음", row.n_excluded,
        `[${displayNumber(row.unknown_outcome_fraction_bounds.lower)}, ${displayNumber(row.unknown_outcome_fraction_bounds.upper)}]`]));
    estimates.append(element("p", "LHS는 층화된 종속 표본입니다. iid 이항 신뢰구간을 제공하지 않습니다. 원 scalar의 부호·단위를 유지하며 절댓값·단위 변환을 적용하지 않습니다.", "hint"));
    const statistics = details(article, "유효 수치 표본의 경험 통계");
    statistics.append(element("p", "표본 표준편차(ddof=1)와 선형 경험 분위수입니다. q05/q50/q95는 신뢰구간이 아닙니다.", "hint"));
    table(statistics, ["원 응답", "단위", "표본 수", "평균", "표준편차", "최소", "최대", "q05", "q50", "q95"], view.statistics.map(row =>
      [row.metric, row.unit, row.count, displayNumber(row.mean), row.count === 1 ? "표본 1개 · 추정 불가" : displayNumber(row.std), displayNumber(row.min), displayNumber(row.max),
        displayNumber(row.quantiles.q05), displayNumber(row.quantiles.q50), displayNumber(row.quantiles.q95)]));
    const exclusions = details(article, `제외된 미지 결과 · ${view.exclusions.length}개`);
    if (view.exclusions.length) table(exclusions, ["원 표본 ID", "원 제외 사유"], view.exclusions.map(row => [row.id, row.reason]));
    else exclusions.append(element("p", "제외 기록 없음", "hint"));
    article.append(element("p", "제외 결과를 0이나 비충족으로 바꾸지 않습니다. 응답에 따라 생긴 제외는 비율을 편향시킬 수 있으며, 인과관계·물리 자격·배포 승인을 추정하지 않습니다.", "hint"));
    const raw = details(article, "원 선언·표본·수치·분석 한계");
    raw.append(element("p", "Core가 원 계획/결과와 보고서를 검증합니다. 이 화면은 LHS·확률 비율·통계를 재계산하지 않으며, 아래 JSON은 원 파일 바이트가 아닌 전체 정밀도 데이터 표시입니다.", "hint"),
      element("p", context.source_pin_check.matched_keys.length ? `제공된 보고서 선택 문맥 pin ${context.source_pin_check.matched_keys.length}개 일치` : "Core VERIFIED · 추가 선택 문맥 pin 대조 없음", "hint"),
      element("pre", rawData(view), "mono"));
    container.replaceChildren(article); return view;
  }
  return Object.freeze({ summary, render });
});
