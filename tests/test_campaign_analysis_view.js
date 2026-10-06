"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const controls = require("../apps/lab/static/campaign-analysis-view.js");

// Source-contract fixture only. Native/hash/mathematical authority remains Core.
const hash = letter => letter.repeat(64);
const originalIds = Array.from({ length: 7 }, (_, index) => `E-study-de-${String(index + 1).padStart(4, "0")}`);
const definitions = () => [{ metric: "max_displacement", unit: "mm", direction: "minimize" }, { metric: "signed_force", unit: "N", direction: "maximize" }];
function envelope() {
  const variables = [
    { parameter_id: "width", display_name: "폭", unit: "mm", lower_bound: 10, upper_bound: 20, current_value: 12, mode: "free", target: "cad",
      native: { backend: "fixture.freecad", document: hash("e"), object: "Part", path: "Length", alias: "" }, source_sha256: hash("d") },
    { parameter_id: "mass", display_name: "질량", unit: "kg", lower_bound: 1, upper_bound: 3, current_value: 2, mode: "free", target: "model_analysis" },
  ];
  const samples = originalIds.map((id, index) => ({ id,
    values: { width: [10, 12, 14, 16, 18, 20, 11][index], mass: [1, 2, 3, 1.5, 2.5, 2, 2][index] },
    responses: { max_displacement: { value: index === 6 ? null : index + 1, unit: "mm", valid: index < 5 },
      signed_force: { value: index === 6 ? null : -5 + index, unit: "N", valid: index < 5 } }, usable: index !== 6 }));
  const eligible = originalIds.slice(0, 5);
  const statistics = definitions().map((definition, index) => ({ metric: definition.metric, unit: definition.unit, count: 5,
    mean: index === 0 ? 3 : -3, std: 1.5811388300841898, min: index === 0 ? 1 : -5, max: index === 0 ? 5 : -1,
    quantiles: { q05: index === 0 ? 1.2 : -4.8, q50: index === 0 ? 3 : -3, q95: index === 0 ? 4.8 : -1.2 } }));
  const sensitivity = definitions().map((definition, index) => ({ metric: definition.metric, unit: definition.unit,
    method: "NORMALIZED_MULTIVARIATE_LEAST_SQUARES", valid: true, reason: null, rank: 3, condition_number: 2.3,
    coefficients: [{ parameter_id: "width", unit: "1", parameter_unit: "mm", coefficient: index === 0 ? 0.8 : -0.8 },
      { parameter_id: "mass", unit: "1", parameter_unit: "kg", coefficient: -0.2 }], sample_ids: eligible.slice(), intercept: -0,
    response_mean: statistics[index].mean, response_std: statistics[index].std }));
  const surrogate = definitions().map(definition => ({ metric: definition.metric, unit: definition.unit,
    method: "SEEDED_HOLDOUT_LEAST_SQUARES", model: "affine", train_ids: eligible.slice(0, 3), test_ids: eligible.slice(3), rank: 3, condition_number: 4.1,
    features: [{ id: "F0", powers: {} }, { id: "F1", powers: { width: 1 } }, { id: "F2", powers: { mass: 1 } }],
    coefficients: [{ feature_id: "F0", value: 3, unit: definition.unit }, { feature_id: "F1", value: -0.1, unit: definition.unit },
      { feature_id: "F2", value: 0.2, unit: definition.unit }],
    normalization: variables.map(({ parameter_id, unit, lower_bound, upper_bound }) => ({ parameter_id, unit, lower_bound, upper_bound })),
    test_mae: 0.05, test_rmse: 0.08, test_max_error: 0.12, valid: true, reason: null, seed: 13,
    limitations: ["원 계획 bounds 내 별도 보류 표본 오차; 물리적 정확도 판정 없음."] }));
  const nativeIds = originalIds.slice(0, 6);
  return { schema_version: "1.0", integrity: "VERIFIED", report_id: "R-study-de-01", campaign_id: "study-de", study_id: "S-study",
    report_sha256: hash("c"), source: { type: "doe", plan_sha256: hash("a"), result_sha256: hash("b"), experiment_ids: nativeIds,
      experiment_result_sha256: Object.fromEntries(nativeIds.map(value => [value, hash("f")])), sample_ids: originalIds.slice() },
    declaration: { purpose: "동일 캠페인의 폭/질량과 응답 관계 연구", origin: "DESIGN_EXPLORATION", reference: "사용자가 선언한 원 계획",
      response_definitions: definitions(), uncertainty: { interpretation: "DESIGN_SPACE_ONLY", reference: "bounds는 설계 탐색 범위" } },
    variables, samples, seed: 13, created_utc: "2026-10-07T12:00:00Z",
    provenance: { git_commit: hash("d"), git_dirty: true, core_source_sha256: hash("e"), files: { "caelab/campaign_report.py": hash("f") } },
    analysis: { statistics, sensitivity, surrogate, pareto: { response_definitions: definitions(), nondominated_ids: [eligible[0], eligible[4]],
      valid: true, reason: null, method: "EXACT_COMPONENTWISE_NONDOMINANCE" },
    exclusions: [{ id: originalIds[5], reason: "INVALID_RESPONSE:max_displacement,signed_force" }, { id: originalIds[6], reason: "ROW_UNUSABLE" }],
    qualification: "NUMERICAL_SAMPLE_ANALYSIS_ONLY", decision: "NOT_RELEASED", limitations: ["이 수치 표본의 연관만 추정합니다."] },
    decision: "NOT_RELEASED", engineering_qualification: "UNKNOWN" };
}
function pins(value) {
  return { report_id: value.report_id, campaign_id: value.campaign_id, study_id: value.study_id, plan_sha256: value.source.plan_sha256,
    result_sha256: value.source.result_sha256, report_sha256: value.report_sha256 };
}
function freeze(value) { if (value && typeof value === "object") { Object.values(value).forEach(freeze); Object.freeze(value); } return value; }

class Node {
  constructor(tag, document) { this.tagName = tag.toUpperCase(); this.ownerDocument = document; this.children = []; this._text = ""; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
  set textContent(value) { this._text = String(value ?? ""); this.children.forEach(child => { child.parentNode = null; }); this.children = []; }
  set innerHTML(_value) { throw new Error("Report text may not become HTML"); }
  append(...nodes) { nodes.forEach(node => { node.remove(); node.parentNode = this; this.children.push(node); }); }
  replaceChildren(...nodes) { this.textContent = ""; this.append(...nodes); }
  remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter(child => child !== this); this.parentNode = null; }
}
function container() {
  const document = { createElement(tag) { return new Node(tag, document); }, createElementNS() { throw new Error("No fabricated dataset plot"); } };
  return document.createElement("div");
}
const walk = node => [node, ...node.children.flatMap(walk)];
const visibleText = node => node.tagName === "DETAILS" && !node.open ? node.children.find(child => child.tagName === "SUMMARY")?.textContent ?? "" :
  node._text + node.children.map(visibleText).join("");
const rows = node => walk(node).filter(value => value.tagName === "TR").map(value => value.children.map(cell => cell.textContent));
const section = (node, title) => walk(node).find(value => value.tagName === "SECTION" && value.children[0]?.textContent === title);
function makeInvalidFits(value, ids, reason = "INSUFFICIENT_SAMPLES") {
  for (const row of value.analysis.sensitivity) Object.assign(row, { valid: false, reason, rank: 0, condition_number: null,
    coefficients: [], sample_ids: ids.slice(), intercept: null, response_mean: null, response_std: null });
  for (const row of value.analysis.surrogate) Object.assign(row, { valid: false, reason, rank: 0, condition_number: null,
    coefficients: [], train_ids: [], test_ids: ids.slice(), test_mae: null, test_rmse: null, test_max_error: null });
}

test("saved report summary preserves exact Core values, full registry/provenance and does not mutate a frozen input", () => {
  const value = freeze(envelope()), expected = freeze(pins(value)), output = controls.summary(value, expected);
  assert.deepEqual(Object.keys(controls).sort(), ["render", "summary"]);
  const { source_pin_check, ...record } = output;
  assert.deepEqual(record, value); assert.deepEqual(source_pin_check, { authority: "CORE_VERIFIED", matched_keys: Object.keys(expected) });
  assert(Object.is(output.analysis.sensitivity[0].intercept, -0));
  output.samples[0].values.width = 17; output.provenance.files["caelab/campaign_report.py"] = hash("0");
  assert.equal(value.samples[0].values.width, 10); assert.equal(value.provenance.files["caelab/campaign_report.py"], hash("f"));
});

test("professional report distinguishes enrolled candidates, retained invalid values and actual native results", () => {
  const value = envelope(), node = container(); controls.render(node, value, { campaign_id: value.campaign_id, plan_sha256: value.source.plan_sha256 });
  assert.match(node.textContent, /원 표본 7개 · 실제 native 실험 6개 · 공통 유효 표본 5개/);
  const inputs = section(node, "선택 변수와 원 표본"), sampleRows = rows(inputs).filter(row => originalIds.includes(row[0]) && row.length > 2);
  assert.equal(sampleRows.length, 7);
  assert.deepEqual(sampleRows[5], [originalIds[5], "native 결과 보존", "20", "2", "6 · 원 응답 invalid", "0 · 원 응답 invalid", "제외 · INVALID_RESPONSE:max_displacement,signed_force"]);
  assert.deepEqual(sampleRows[6], [originalIds[6], "native 결과 없음", "11", "2", "사용 불가 · 원 응답 invalid", "사용 불가 · 원 응답 invalid", "제외 · ROW_UNUSABLE"]);
  assert(rows(inputs).some(row => row.length === 2 && row[0] === originalIds[5] && row[1] === hash("f")));
  assert(!rows(inputs).some(row => row.length === 2 && row[0] === originalIds[6]));
  assert.match(node.textContent, /q05\/q50\/q95는 선형 경험 분위수이며 신뢰구간이 아닙니다/);
  assert.match(node.textContent, /무차원/); assert.match(node.textContent, /다목적 최적화기가 아닙니다/);
  assert.match(node.textContent, /이 수치 표본에서 추정한 분석이며 물리적 자격은 미검증/);
  assert.match(node.textContent, /Core VERIFIED · 제공된 선택 문맥 pin 2개 일치/);
  assert(!/\bPASS\b|failure probability|\bPf\b|\bSobol\b/.test(node.textContent));
  assert(!walk(node).some(value => ["SVG", "CANVAS", "IMG", "SCRIPT", "IFRAME"].includes(value.tagName)));
});

test("all untrusted purpose, unit, label, reason and provenance strings remain literal text", () => {
  const value = envelope(), unsafe = '<img src=x onerror="run()"><script>run()</script>';
  value.declaration.purpose = unsafe; value.declaration.reference = unsafe; value.declaration.uncertainty.reference = unsafe;
  value.variables[0].display_name = unsafe; value.provenance.note = unsafe; value.analysis.limitations.push(unsafe); value.analysis.exclusions[0].reason = unsafe;
  value.declaration.response_definitions[0].unit = unsafe; value.samples.forEach(row => { row.responses.max_displacement.unit = unsafe; });
  for (const key of ["statistics", "sensitivity", "surrogate"]) value.analysis[key][0].unit = unsafe;
  value.analysis.surrogate[0].coefficients.forEach(row => { row.unit = unsafe; }); value.analysis.pareto.response_definitions[0].unit = unsafe;
  const node = container(); controls.render(node, value);
  assert(node.textContent.includes(unsafe)); assert.equal(walk(node).filter(value => value.tagName === "IMG" || value.tagName === "SCRIPT").length, 0);
  assert.equal(controls.summary(value).declaration.reference, unsafe);
});

test("independent caller pins reject changed valid IDs/hashes but no browser cryptographic proof is invented", () => {
  const value = envelope(), expected = pins(value);
  for (const key of Object.keys(expected)) {
    const changed = envelope();
    if (["plan_sha256", "result_sha256"].includes(key)) changed.source[key] = hash("1");
    else changed[key] = key.endsWith("_sha256") ? hash("1") : "Other-valid-ID";
    assert.throws(() => controls.summary(changed, expected), /pin/);
    const unpinned = controls.summary(changed);
    assert.deepEqual(unpinned.source_pin_check, { authority: "CORE_VERIFIED", matched_keys: [] });
  }
  const node = container(); controls.render(node, value);
  assert.match(node.textContent, /추가 선택 문맥 pin 대조 없음/); assert.match(node.textContent, /암호학적 검증은 Core가 수행/);
  assert(!node.textContent.includes("브라우저 SHA 검증 성공"));
});

test("malformed pins and unverified, missing, released or nonfinite envelopes refuse and clear stale display", () => {
  const malformed = [null, {}, { campaign_id: "" }, { study_id: "S-other" }, { plan_sha256: hash("A") }, { report_sha256: "not-sha" },
    { campaign_id: undefined }, { source: {} }, { report_id: "R-study-de-01", extra: true }];
  for (const expected of malformed) assert.throws(() => controls.summary(envelope(), expected));
  const changes = [value => { value.integrity = "NOT_CHECKED"; }, value => { delete value.provenance; }, value => { value.decision = "RELEASED"; },
    value => { value.analysis.qualification = "PHYSICALLY_VALIDATED"; }, value => { value.analysis.statistics[0].mean = Infinity; },
    value => { value.samples[0].values.width = NaN; }, value => { value.report_sha256 = hash("A"); }, value => { value.extra = 0; }];
  const node = container();
  for (const change of changes) {
    controls.render(node, envelope()); const value = envelope(); change(value);
    assert.throws(() => controls.render(node, value)); assert.match(node.textContent, /보고서 표시 불가/);
    assert(!node.textContent.includes("캠페인 수치 표본 분석")); assert(!node.textContent.includes(originalIds[0]));
  }
});

test("native hashes and enrolled sample joins reject missing, extra, repeated and foreign identities", () => {
  const changes = [
    value => { delete value.source.experiment_result_sha256[originalIds[0]]; },
    value => { value.source.experiment_result_sha256[originalIds[6]] = hash("a"); },
    value => { value.source.experiment_result_sha256[originalIds[0]] = hash("F"); },
    value => { value.source.experiment_ids[0] = "E-foreign"; },
    value => { value.source.sample_ids[0] = originalIds[1]; },
    value => { value.samples.reverse(); },
    value => { value.source.sample_ids.reverse(); },
    value => { value.samples[0].id = "E-foreign"; },
    value => { value.source.experiment_ids.shift(); delete value.source.experiment_result_sha256[originalIds[0]]; },
  ];
  for (const change of changes) { const value = envelope(); change(value); assert.throws(() => controls.summary(value)); }
});

test("responses and variables retain exact scalar units, bounds and valid flags without implicit conversion", () => {
  const changes = [
    value => { value.samples[0].responses.max_displacement.unit = "m"; },
    value => { value.samples[0].responses.max_displacement.value = null; },
    value => { value.samples[0].responses.max_displacement.valid = "true"; },
    value => { value.samples[0].responses.max_displacement.coordinates = [0, 0, 0]; },
    value => { delete value.samples[0].responses.signed_force; },
    value => { value.samples[0].values.width = 21; },
    value => { value.variables[0].lower_bound = 20; },
    value => { delete value.variables[0].display_name; },
    value => { value.variables[0].parameter_id = "constructor"; },
    value => { value.analysis.sensitivity[0].coefficients[0].parameter_unit = "m"; },
    value => { value.analysis.surrogate[0].normalization[0].lower_bound = 9; },
    value => { value.analysis.surrogate[0].coefficients[0].unit = "m"; },
  ];
  for (const change of changes) { const value = envelope(); change(value); assert.throws(() => controls.summary(value)); }
  const value = envelope(); value.samples[5].responses.max_displacement.value = -0;
  assert(Object.is(controls.summary(value).samples[5].responses.max_displacement.value, -0));
});

test("common cohort refuses excluded, foreign or overlapping model/Pareto IDs and inconsistent seed", () => {
  const changes = [
    value => { value.analysis.sensitivity[0].sample_ids[0] = originalIds[5]; },
    value => { value.analysis.surrogate[0].test_ids[0] = value.analysis.surrogate[0].train_ids[0]; },
    value => { value.analysis.surrogate[0].train_ids[0] = "E-foreign"; },
    value => { value.analysis.surrogate[0].test_ids.pop(); },
    value => { value.analysis.pareto.nondominated_ids = [originalIds[6]]; },
    value => { value.analysis.exclusions.pop(); },
    value => { value.analysis.exclusions[0].id = originalIds[0]; },
    value => { value.analysis.statistics[0].count = 6; },
    value => { value.analysis.surrogate[0].seed = 14; },
    value => { value.seed = 2 ** 32; },
  ];
  for (const change of changes) { const value = envelope(); change(value); assert.throws(() => controls.summary(value)); }
});

test("rank-deficient/small holdout fits retain reasons and bases and never invent zero prediction errors", () => {
  const value = envelope(), ids = originalIds.slice(0, 5); makeInvalidFits(value, ids, "RANK_DEFICIENT");
  value.analysis.surrogate.forEach(row => { row.rank = 2; row.train_ids = ids.slice(0, 3); row.test_ids = ids.slice(3); });
  const node = container(); controls.render(node, value); const modelRows = rows(section(node, "보류 표본 예측 오차")).filter(row => row.length === 8 && row[0] !== "응답");
  assert.equal(modelRows.length, 2); assert.deepEqual(modelRows[0].slice(4), ["사용 불가", "사용 불가", "사용 불가", "사용 불가 · RANK_DEFICIENT"]);
  assert.match(node.textContent, /분석 불가 · RANK_DEFICIENT/); assert.match(node.textContent, /F0/); assert.match(node.textContent, /정규화 하한/);
  assert.equal(controls.summary(value).analysis.surrogate[0].condition_number, null);
  value.analysis.surrogate[0].test_mae = 0; assert.throws(() => controls.summary(value));
});

test("empty eligible cohort preserves null statistics and reports unavailable fits/archive instead of fake zero", () => {
  const value = envelope(); value.samples.forEach(row => { row.usable = false; });
  value.analysis.exclusions = originalIds.map(id => ({ id, reason: "ROW_UNUSABLE" }));
  value.analysis.statistics.forEach(row => { Object.assign(row, { count: 0, mean: null, std: null, min: null, max: null, quantiles: { q05: null, q50: null, q95: null } }); });
  makeInvalidFits(value, []); Object.assign(value.analysis.pareto, { valid: false, reason: "NO_ELIGIBLE_SAMPLES", nondominated_ids: [] });
  const node = container(); controls.render(node, value); const statsRows = rows(section(node, "응답 표본 통계")).slice(1);
  assert(statsRows.every(row => row[2] === "0" && row.slice(3).every(cell => cell === "사용 불가")));
  assert.match(node.textContent, /유효한 원 수치 표본 없음/); assert.match(node.textContent, /NO_ELIGIBLE_SAMPLES/);
  value.analysis.statistics[0].mean = 0; assert.throws(() => controls.summary(value));
});

test("one eligible sample preserves signed numeric values and nullable sample deviation", () => {
  const value = envelope(), id = originalIds[0]; value.samples.forEach((row, index) => { row.usable = index === 0; });
  value.analysis.exclusions = originalIds.slice(1).map(id => ({ id, reason: "ROW_UNUSABLE" }));
  value.analysis.statistics.forEach((row, index) => { const response = value.samples[0].responses[definitions()[index].metric].value;
    Object.assign(row, { count: 1, mean: response, std: null, min: response, max: response, quantiles: { q05: response, q50: response, q95: response } }); });
  makeInvalidFits(value, [id]); value.analysis.pareto.nondominated_ids = [id];
  const node = container(); controls.render(node, value);
  assert.match(node.textContent, /표본 1개 · 추정 불가/); assert.equal(controls.summary(value).analysis.statistics[1].mean, -5);
  value.analysis.statistics[0].std = 0; assert.throws(() => controls.summary(value));
});

test("Core float rounding is preserved rather than rejected by invented extrema/error comparison thresholds", () => {
  const value = envelope(); Object.assign(value.analysis.statistics[0], { mean: 0.10000000000000002, min: 0.1, max: 0.1, std: 0,
    quantiles: { q05: 0.1, q50: 0.1, q95: 0.1 } });
  Object.assign(value.analysis.surrogate[0], { test_mae: 0.10000000000000002, test_rmse: 0.1, test_max_error: 0.1 });
  assert.equal(controls.summary(value).analysis.statistics[0].mean, 0.10000000000000002);
  assert.equal(controls.summary(value).analysis.surrogate[0].test_mae, 0.10000000000000002);
});

test("visible computed numbers use six significant digits without erasing signs/tiny values or changing retained data", () => {
  const value = envelope();
  Object.assign(value.analysis.statistics[0], { mean: 1.234567890123456, std: 9.87654321098765e-16, min: -987654321.12345, max: 1.234567890123e20,
    quantiles: { q05: -Number.MIN_VALUE, q50: -0, q95: Number.MAX_VALUE } });
  value.analysis.sensitivity[0].condition_number = 123456789.0123456;
  value.analysis.sensitivity[0].coefficients[0].coefficient = -1.234567890123456e-100;
  Object.assign(value.analysis.surrogate[0], { test_mae: 1.234567890123456e-30, test_rmse: 0.1234567890123456, test_max_error: 123456789.123456 });
  value.variables[0].lower_bound = 9.123456789012345; value.variables[0].upper_bound = 20.123456789012345;
  value.analysis.surrogate.forEach(row => { Object.assign(row.normalization[0], { lower_bound: value.variables[0].lower_bound, upper_bound: value.variables[0].upper_bound }); });
  value.samples[5].responses.max_displacement.value = -1.234567890123456e-10;
  freeze(value); const node = container(), output = controls.render(node, value);
  const statistics = rows(section(node, "응답 표본 통계"));
  assert.deepEqual(statistics[1], ["max_displacement", "mm", "5", "1.23457", "9.87654e-16", "-9.87654e+8", "1.23457e+20", "-4.94066e-324", "-0", "1.79769e+308"]);
  assert.match(visibleText(node), /조건수 1\.23457e\+8/);
  assert(rows(section(node, "변수와 응답의 선형 연관")).some(row => row[0] === "width" && row[2] === "-1.23457e-100"));
  const errors = rows(section(node, "보류 표본 예측 오차")).find(row => row[0] === "max_displacement" && row.length === 8);
  assert.deepEqual(errors.slice(4, 7), ["1.23457e-30", "0.123457", "1.23457e+8"]);
  const variable = rows(section(node, "선택 변수와 원 표본")).find(row => row[0] === "폭");
  assert.deepEqual(variable.slice(3), ["9.12346", "20.1235"]);
  assert(node.textContent.includes("-1.234567890123456e-10 · 원 응답 invalid"));
  assert.deepEqual(output.analysis, value.analysis); assert.deepEqual(output.samples, value.samples);
  assert.equal(output.analysis.statistics[0].mean, 1.234567890123456); assert(Object.is(output.analysis.statistics[0].quantiles.q50, -0));
  const rawReport = walk(node).find(item => item.tagName === "DETAILS" && item.children[0].textContent === "원 보고서 데이터 · 전체 수치/원문");
  const parsed = JSON.parse(rawReport.children.find(item => item.tagName === "PRE").textContent);
  assert.deepEqual(parsed, value); assert(Object.is(parsed.analysis.sensitivity[0].intercept, -0));
});

test("visible concise Korean limitations preserve all original English/raw material inside closed details", () => {
  const value = envelope(); value.declaration.uncertainty.reference = "범위는 설계 탐색을 위해 선언했습니다."; value.analysis.limitations = [
    "Statistics describe eligible empirical DOE samples; no probability or confidence interval is inferred.",
    "Normalized multivariate least-squares coefficients are associations, not causes or Sobol indices.",
    "Separate held-out error does not qualify extrapolation or physical accuracy.",
    "Pareto membership is not global optimality or physical feasibility.",
    "Invalid rows are excluded without zero substitution; qualification is unverified.",
  ];
  const node = container(); controls.render(node, freeze(value)); const visible = visibleText(node), limitations = section(node, "분석 한계");
  assert.match(visible, /신뢰구간·고장 확률·인과관계·전역 최적성을 판정하지 않습니다/);
  assert.match(visible, /외삽·물리적 정확도·재료 자격은 미검증/); assert.match(visible, /비지배 후보 모음\(Pareto\)/);
  assert.match(visible, /다목적 최적화기가 아닙니다/); assert(!visible.includes("conditioning")); assert(!visible.includes("bounds"));
  assert.equal(limitations.children.filter(item => item.tagName === "P").length, 2);
  const raw = limitations.children.find(item => item.tagName === "DETAILS"); assert(!raw.open);
  assert.deepEqual(raw.children.filter(item => item.tagName === "P").map(item => item.textContent), value.analysis.limitations);
  value.analysis.limitations.forEach(line => { assert(!visible.includes(line)); assert(raw.textContent.includes(line)); });
  assert.match(visible, /NOT_RELEASED/); assert.equal(controls.summary(value).engineering_qualification, "UNKNOWN");
});

test("design-space and explicitly uniform DOE declarations preserve origin/reference and reject optimization probability relabeling", () => {
  for (const origin of ["MEASURED_REPORTED", "PUBLISHED_REFERENCE", "SYNTHETIC", "DESIGN_EXPLORATION"]) {
    const value = envelope(); value.declaration.origin = origin; value.declaration.reference = " \n원 출처 유지\n ";
    value.declaration.uncertainty = { interpretation: "USER_DECLARED_UNIFORM_INPUTS", reference: "원 bounds의 균등 입력이라고 사용자가 선언" };
    const node = container(); controls.render(node, value); assert.equal(controls.summary(value).declaration.reference, value.declaration.reference);
    assert.match(node.textContent, /확률 자격 미검증/); assert(!node.textContent.includes("실측 확률 분포"));
    value.source.type = "optimization"; assert.throws(() => controls.summary(value));
    value.declaration.uncertainty.interpretation = "DESIGN_SPACE_ONLY"; assert.equal(controls.summary(value).source.type, "optimization");
  }
  const value = envelope(); value.declaration.purpose = "목".repeat(4096); value.declaration.reference = "출".repeat(2048);
  value.declaration.uncertainty.reference = "근".repeat(2048); assert.equal(controls.summary(value).declaration.purpose.length, 4096);
  value.declaration.purpose += "적"; assert.throws(() => controls.summary(value));
});

test("own plain finite JSON admission refuses getters/prototypes/unsafe keys/sparse arrays without executing user accessors", () => {
  let reads = 0; const value = envelope(); Object.defineProperty(value.samples[0].responses.max_displacement, "value", { enumerable: true, get() { reads++; return 1; } });
  assert.throws(() => controls.summary(value)); assert.equal(reads, 0);
  const changes = [
    data => { data.provenance = Object.create({ git_commit: hash("d") }); data.provenance.note = "inherited"; },
    data => { data.provenance = JSON.parse('{"__proto__":{"verdict":"PASS"}}'); },
    data => { delete data.samples[1]; }, data => { data.provenance.self = data.provenance; },
    data => { data.provenance.callback = () => "PASS"; }, data => { data.provenance.hidden = undefined; },
    data => { Object.defineProperty(data.provenance, "hidden", { value: "not JSON" }); },
  ];
  for (const change of changes) { const data = envelope(); change(data); assert.throws(() => controls.summary(data)); }
});

test("browser loading exposes only render/summary and accepts serialized cross-realm Core JSON without runtime calls", () => {
  const source = fs.readFileSync(path.join(__dirname, "../apps/lab/static/campaign-analysis-view.js"), "utf8");
  const context = vm.createContext({ window: {}, fetch() { throw new Error("No report fetch in pure helper"); } });
  vm.runInContext(source, context); assert.deepEqual(Object.keys(context.window.campaignAnalysisView).sort(), ["render", "summary"]);
  context.raw = JSON.stringify(envelope()); context.expected = pins(envelope());
  const output = vm.runInContext("window.campaignAnalysisView.summary(JSON.parse(raw), expected)", context);
  assert.equal(output.samples.length, 7); assert.equal(output.source_pin_check.matched_keys.length, 6);
  assert.equal(output.analysis.statistics[1].mean, -3);
});
