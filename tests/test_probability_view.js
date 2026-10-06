"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const view = require("../apps/lab/static/probability-view.js");
const campaign = require("../apps/lab/static/campaign-analysis-view.js");

// Literal Core-shaped source-contract fixtures, not native or measured evidence.
// Sampler replay, numerical recomputation and receipt hashes are Core authority.
const sha = character => character.repeat(64);
const sampleIds = ["E-original-0001", "E-original-0002", "E-original-0003", "E-original-0004"];
const responseDefinitions = () => [{ metric: "signed_response", unit: "mm", direction: "minimize" }, { metric: "reaction", unit: "N", direction: "maximize" }];
function fixture() {
  const variables = ["V0", "V1"].map(parameter_id => ({ parameter_id, display_name: `원 변수 ${parameter_id}`, unit: "N", lower_bound: -4, upper_bound: 6,
    current_value: 0, mode: "free", target: "analysis_conditions", native: { backend: "structure.calculix.native", document: sha("f"), object: "analysis_conditions", path: parameter_id, alias: "" } }));
  const values = [{ V0: -3, V1: 2 }, { V0: 1, V1: -2 }, { V0: 4, V1: 5 }, { V0: -0.5, V1: 0.5 }];
  const samples = sampleIds.map((id, index) => ({ id, values: { ...values[index] }, usable: index !== 1,
    responses: { signed_response: { value: [-2, 4, 8, 1][index], unit: "mm", valid: true },
      reaction: { value: index === 2 ? null : -5, unit: "N", valid: index !== 2 } } }));
  const eligible = [sampleIds[0], sampleIds[3]], statistics = [
    { metric: "signed_response", unit: "mm", count: 2, mean: -0.5, std: 2.1213203435596424, min: -2, max: 1, quantiles: { q05: -1.85, q50: -0.5, q95: 0.85 } },
    { metric: "reaction", unit: "N", count: 2, mean: -5, std: 0, min: -5, max: -5, quantiles: { q05: -5, q50: -5, q95: -5 } },
  ];
  const sensitivity = responseDefinitions().map((definition, index) => ({ metric: definition.metric, unit: definition.unit,
    method: "NORMALIZED_MULTIVARIATE_LEAST_SQUARES", valid: false, reason: "INSUFFICIENT_SAMPLES", rank: 2, condition_number: null,
    coefficients: [], sample_ids: eligible.slice(), intercept: null, response_mean: statistics[index].mean, response_std: statistics[index].std }));
  const surrogate = responseDefinitions().map(definition => ({ metric: definition.metric, unit: definition.unit,
    method: "SEEDED_HOLDOUT_LEAST_SQUARES", model: "affine", train_ids: [eligible[0]], test_ids: [eligible[1]], rank: 1, condition_number: null,
    features: [{ id: "F0", powers: {} }, { id: "F1", powers: { V0: 1 } }, { id: "F2", powers: { V1: 1 } }], coefficients: [],
    normalization: variables.map(({ parameter_id, unit, lower_bound, upper_bound }) => ({ parameter_id, unit, lower_bound, upper_bound })),
    test_mae: null, test_rmse: null, test_max_error: null, valid: false, reason: "INSUFFICIENT_SAMPLES", seed: 29, limitations: ["TEST_ONLY insufficient holdout fit"] }));
  const exclusions = [{ id: sampleIds[1], reason: "ROW_UNUSABLE" }, { id: sampleIds[2], reason: "INVALID_RESPONSE:reaction" }];
  const report = { schema_version: "1.0", integrity: "VERIFIED", report_id: "R-probability-01", campaign_id: "C-declared-01", study_id: "S-research",
    report_sha256: sha("c"), source: { type: "doe", plan_sha256: sha("a"), result_sha256: sha("b"), experiment_ids: sampleIds.slice(),
      experiment_result_sha256: Object.fromEntries(sampleIds.map(id => [id, sha("d")])), sample_ids: sampleIds.slice() },
    declaration: { purpose: "사용자가 선언한 입력 분포의 수치 조건 비교", origin: "DESIGN_EXPLORATION", reference: "TEST_ONLY numerical campaign",
      response_definitions: responseDefinitions(), uncertainty: { interpretation: "DESIGN_SPACE_ONLY", reference: "원 변수 범위" } },
    variables, samples, seed: 29, created_utc: "2026-10-07T16:00:00Z", provenance: { core_source_sha256: sha("e"), git_dirty: true },
    analysis: { statistics, sensitivity, surrogate, pareto: { response_definitions: responseDefinitions(), nondominated_ids: [eligible[0]],
      valid: true, reason: null, method: "EXACT_COMPONENTWISE_NONDOMINANCE" }, exclusions,
      qualification: "NUMERICAL_SAMPLE_ANALYSIS_ONLY", decision: "NOT_RELEASED", limitations: ["TEST_ONLY numerical sample scope"] },
    decision: "NOT_RELEASED", engineering_qualification: "UNKNOWN" };
  const marginals = variables.map(({ parameter_id, unit, lower_bound, upper_bound }) => ({ parameter_id, unit, distribution: "uniform", lower_bound, upper_bound }));
  const thresholds = [{ id: "T-positive", metric: "signed_response", unit: "mm", operator: ">", value: 0 },
    { id: "T-negative-force", metric: "reaction", unit: "N", operator: "<=", value: -4 }];
  const source = { origin: "SYNTHETIC", reference: "TEST_ONLY declared independent uniform law" };
  report.declaration.probability = { marginals, independence: "INDEPENDENT_USER_DECLARED", source, thresholds };
  const declaration = { marginals: marginals.map(row => ({ ...row })), independence: "INDEPENDENT_USER_DECLARED", source: { ...source }, sample_ids: sampleIds.slice(), seed: 13,
    schema_version: "1.0", sample_count: 4, sampling: { engine: "scipy.latin_hypercube", version: "TEST_ONLY_SCIPY", numpy_version: "TEST_ONLY_NUMPY",
      strength: 1, optimization: null, randomization: "SCRAMBLED_STRATIFIED" }, samples: values.map((values, index) => ({ id: sampleIds[index], index: index + 1, values: { ...values } })) };
  report.probability_analysis = { schema_version: "1.0", declaration, samples: samples.map(row => ({ ...row, values: { ...row.values },
    responses: Object.fromEntries(Object.entries(row.responses).map(([key, value]) => [key, { ...value }])) })),
    sample_ids: sampleIds.slice(), valid_sample_ids: eligible.slice(), counts: { declared: 4, valid: 2, excluded: 2 }, statistics: statistics.map(row => ({ ...row, quantiles: { ...row.quantiles } })),
    thresholds: thresholds.map((row, index) => ({ ...row, predicate: index === 0 ? "signed_response > 0.0 mm" : "reaction <= -4.0 N", signed_scalar: true,
      exceedance_count: index === 0 ? 1 : 2, n_valid: 2, n_excluded: 2, probability_estimate: index === 0 ? 0.5 : 1, conditioning: "VALID_NUMERICAL_ROWS_ONLY", valid: true,
      reason: null, confidence_interval: null, confidence_interval_reason: "LHS_STRATIFIED_DEPENDENT_NOT_IID_BINOMIAL",
      unknown_outcome_fraction_bounds: index === 0 ? { lower: 0.25, upper: 0.75 } : { lower: 0.5, upper: 1 } })), exclusions: exclusions.map(row => ({ ...row })),
    qualification: "DECLARED_UNIFORM_NUMERICAL_PROBABILITY_PROPAGATION_ONLY", physical: "UNKNOWN", engineering: "UNKNOWN", decision: "NOT_RELEASED",
    limitations: ["Original declared uniforms and independence are unqualified.", "LHS points are not iid binomial observations.", "Excluded outcomes are unknown, not zero."],
    source_sampling: { algorithm: { engine: declaration.sampling.engine, version: declaration.sampling.version,
      numpy_version: declaration.sampling.numpy_version, strength: declaration.sampling.strength,
      optimization: declaration.sampling.optimization, seed: declaration.seed },
      plan_sha256: report.source.plan_sha256, result_sha256: report.source.result_sha256,
      replay: "EXACT_CURRENT_SCIPY_NUMPY_VERSION_ONLY" } };
  return report;
}
function expected(report) { return { report_id: report.report_id, campaign_id: report.campaign_id, study_id: report.study_id, report_sha256: report.report_sha256 }; }
function freeze(value) { if (value && typeof value === "object") { Object.values(value).forEach(freeze); Object.freeze(value); } return value; }
class Node {
  constructor(tag, doc) { this.tagName = tag.toUpperCase(); this.ownerDocument = doc; this.children = []; this._text = ""; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
  set textContent(value) { this._text = String(value ?? ""); this.children.forEach(child => { child.parentNode = null; }); this.children = []; }
  set innerHTML(_value) { throw new Error("Only literal textContent permitted"); }
  append(...nodes) { nodes.forEach(node => { node.remove(); node.parentNode = this; this.children.push(node); }); }
  replaceChildren(...nodes) { this.textContent = ""; this.append(...nodes); }
  remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter(child => child !== this); this.parentNode = null; }
}
function container() { const doc = { createElement(tag) { return new Node(tag, doc); } }; return doc.createElement("div"); }
const walk = node => [node, ...node.children.flatMap(walk)];
const rows = node => walk(node).filter(node => node.tagName === "TR").map(node => node.children.map(cell => cell.textContent));
const visibleText = node => node.tagName === "DETAILS" && !node.open ? node.children.find(child => child.tagName === "SUMMARY")?.textContent ?? "" : node._text + node.children.map(visibleText).join("");
function subset(report) {
  const analysis = report.probability_analysis;
  report.declaration.probability.thresholds = report.declaration.probability.thresholds.slice(0, 1);
  analysis.samples.forEach(row => { delete row.responses.reaction; });
  analysis.valid_sample_ids = [sampleIds[0], sampleIds[2], sampleIds[3]]; analysis.counts = { declared: 4, valid: 3, excluded: 1 };
  analysis.statistics = [{ metric: "signed_response", unit: "mm", count: 3, mean: 2.3333333333333335, std: 5.131601439446884, min: -2, max: 8,
    quantiles: { q05: -1.7, q50: 1, q95: 7.3 } }];
  analysis.thresholds = [{ ...analysis.thresholds[0], exceedance_count: 2, n_valid: 3, n_excluded: 1, probability_estimate: 2 / 3, unknown_outcome_fraction_bounds: { lower: 0.5, upper: 0.75 } }];
  analysis.exclusions = [analysis.exclusions[0]]; return report;
}

test("Core-shaped report preserves declaration, signed scalar rows, invalid nulls and distinct sampler/holdout seeds", () => {
  const report = freeze(fixture()), output = view.summary(report, freeze(expected(report)));
  assert.deepEqual(Object.keys(view).sort(), ["render", "summary"]);
  const { report_context, ...analysis } = output; assert.deepEqual(analysis, report.probability_analysis);
  assert.deepEqual(report_context, { report_id: report.report_id, campaign_id: report.campaign_id, study_id: report.study_id, report_sha256: report.report_sha256,
    source_pin_check: { authority: "CORE_VERIFIED", matched_keys: Object.keys(expected(report)) } });
  assert.equal(output.declaration.seed, 13); assert.equal(report.seed, 29);
  output.samples[0].responses.signed_response.value = 1; assert.equal(report.samples[0].responses.signed_response.value, -2);
  assert.equal(output.samples[2].responses.reaction.value, null); assert.equal(output.counts.excluded, 2);
});

test("professional small table preserves signed predicates, unknown finite bounds and visible unqualified scope", () => {
  const node = container(), report = fixture(); view.render(node, report, expected(report));
  const visible = visibleText(node); assert.match(visible, /실측 불량 확률 아님 · 선언 분포의 수치 표본/);
  assert.match(visible, /UNKNOWN · NOT_RELEASED/); assert.match(visible, /SYNTHETIC/); assert.match(visible, /seed 13/);
  assert.match(visible, /모집단 확률 범위나 신뢰구간이 아닙니다/); assert.match(visible, /iid 이항 신뢰구간을 제공하지 않습니다/);
  assert(rows(node).some(row => JSON.stringify(row) === JSON.stringify(["T-negative-force · reaction <= -4", "N", "2/2", "1", "2", "[0.5, 1]"])));
  assert(rows(node).some(row => row[0] === "T-positive · signed_response > 0" && row[5] === "[0.25, 0.75]"));
  report.probability_analysis.limitations.forEach(line => { assert(!visible.includes(line)); assert(node.textContent.includes(line)); });
  assert(!walk(node).some(node => ["SVG", "IMG", "SCRIPT", "CANVAS", "IFRAME"].includes(node.tagName)));
  assert(!visible.includes("PASS")); assert(!visible.includes("測定"));
});

test("Core sampling replay must retain the exact original plan/result/version/seed binding", () => {
  for (const change of [
    report => { delete report.probability_analysis.source_sampling; },
    report => { report.probability_analysis.source_sampling.plan_sha256 = sha("0"); },
    report => { report.probability_analysis.source_sampling.result_sha256 = sha("0"); },
    report => { report.probability_analysis.source_sampling.algorithm.seed += 1; },
    report => { report.probability_analysis.source_sampling.algorithm.version = "OtherSampler"; },
    report => { report.probability_analysis.source_sampling.replay = "ASSUMED_COMPATIBLE"; },
  ]) {
    const report = fixture(); change(report); assert.throws(() => view.summary(report));
  }
});

test("absent/null optional probability analysis retains legacy behavior and clears a previous probability panel", () => {
  const node = container(), report = fixture(); view.render(node, report);
  delete report.probability_analysis; delete report.declaration.probability;
  assert.equal(view.summary(report, expected(report)), null); assert.equal(view.render(node, report), null); assert.equal(node.textContent, "");
  report.probability_analysis = null; report.declaration.probability = null; assert.equal(view.summary(report), null);
  report.declaration.probability = fixture().declaration.probability; assert.throws(() => view.summary(report));
  const orphan = fixture(); delete orphan.declaration.probability; assert.throws(() => view.summary(orphan));
});

test("subset threshold metrics uses their actual common cohort rather than the base report's other metric exclusions", () => {
  const report = subset(fixture()), node = container(), output = view.render(node, report);
  assert.equal(output.counts.valid, 3); assert.equal(report.analysis.statistics[0].count, 2);
  assert.deepEqual(output.valid_sample_ids, [sampleIds[0], sampleIds[2], sampleIds[3]]);
  assert(rows(node).some(row => row[0] === "T-positive · signed_response > 0" && row[3] === "0.666667" && row[5] === "[0.5, 0.75]"));
  assert.equal(view.summary(report).thresholds[0].probability_estimate, 2 / 3);
});

test("original caller pins reject changed report/campaign/study IDs and receipt SHA without claiming standalone crypto", () => {
  const original = fixture(), pins = expected(original);
  for (const key of Object.keys(pins)) {
    const report = fixture(); report[key] = key.endsWith("_sha256") ? sha("0") : "Other-original-ID";
    assert.throws(() => view.summary(report, pins), /pin/);
    assert.deepEqual(view.summary(report).report_context.source_pin_check, { authority: "CORE_VERIFIED", matched_keys: [] });
  }
  for (const pins of [null, {}, { report_sha256: sha("A") }, { record_sha256: sha("a") }, { campaign_id: undefined }]) assert.throws(() => view.summary(fixture(), pins));
});

test("wrong original sample ID/input value/signed response/source units fail and replace a stale successful display", () => {
  const changes = [
    report => { report.probability_analysis.samples[0].id = "E-other"; },
    report => { report.probability_analysis.declaration.sample_ids[0] = "E-other"; },
    report => { report.probability_analysis.samples[0].values.V0 = -2.9; },
    report => { report.probability_analysis.declaration.samples[0].values.V1 = 3; },
    report => { report.probability_analysis.samples[0].responses.signed_response.value = 2; },
    report => { report.probability_analysis.samples[0].responses.signed_response.unit = "m"; },
    report => { report.probability_analysis.statistics[0].unit = "m"; },
    report => { report.probability_analysis.thresholds[0].unit = "m"; },
    report => { report.probability_analysis.samples.reverse(); },
    report => { report.probability_analysis.declaration.source.reference = "Another source"; },
    report => { report.probability_analysis.declaration.marginals[0].lower_bound = -5; },
    report => { report.probability_analysis.declaration.samples[0].index = true; },
  ];
  const node = container();
  for (const change of changes) {
    view.render(node, fixture()); const report = fixture(); change(report); assert.throws(() => view.render(node, report));
    assert.match(node.textContent, /확률 분석 표시 불가/); assert(!node.textContent.includes("선언 분포의 수치 표본과 조건 충족 비율"));
  }
});

test("exclusions remain unknown and are bound to the exact invalid/unusable rows and original reasons", () => {
  const changes = [
    report => { report.probability_analysis.exclusions[0].id = sampleIds[0]; },
    report => { report.probability_analysis.exclusions[1].reason = "RESPONSE_VALID"; },
    report => { report.probability_analysis.exclusions.pop(); },
    report => { report.probability_analysis.counts.excluded = 0; },
    report => { report.probability_analysis.valid_sample_ids.push(sampleIds[2]); },
    report => { report.probability_analysis.samples[2].responses.reaction.value = 0; },
    report => { report.probability_analysis.samples[2].responses.reaction.valid = true; },
    report => { report.probability_analysis.samples[1].usable = true; },
  ];
  for (const change of changes) { const report = fixture(); change(report); assert.throws(() => view.summary(report)); }
  const report = fixture(); report.probability_analysis.samples[2].responses.reaction.reason = "TEST_ONLY missing native scalar";
  assert.equal(view.summary(report).samples[2].responses.reaction.reason, "TEST_ONLY missing native scalar");
});

test("only declared uniform signed scalar comparisons are supported; arrays, abs/converted predicates and fabricated confidence intervals refuse", () => {
  const changes = [
    report => { report.probability_analysis.thresholds[0].signed_scalar = false; },
    report => { report.probability_analysis.thresholds[0].operator = "abs>"; },
    report => { report.probability_analysis.thresholds[0].predicate = "abs(signed_response) > 0.0 mm"; },
    report => { report.probability_analysis.thresholds[0].predicate = "signed_response > 10.0 mm"; },
    report => { report.probability_analysis.thresholds[0].predicate = "signed_response > eval(0) mm"; },
    report => { report.probability_analysis.thresholds[0].value = [0, 1]; },
    report => { report.probability_analysis.samples[0].responses.signed_response.value = [1, 2, 3]; },
    report => { report.probability_analysis.thresholds[0].confidence_interval = [0.1, 0.9]; },
    report => { report.probability_analysis.thresholds[0].unknown_outcome_fraction_bounds.lower = -0.1; },
    report => { report.probability_analysis.thresholds[0].unknown_outcome_fraction_bounds = { lower: 0.8, upper: 0.2 }; },
    report => { report.probability_analysis.thresholds[0].probability_estimate = NaN; },
    report => { report.probability_analysis.thresholds[0].probability_estimate = 1.1; },
    report => { report.probability_analysis.thresholds[0].n_valid = true; },
    report => { report.probability_analysis.thresholds[0].exceedance_count = 3; },
    report => { report.probability_analysis.declaration.sampling.engine = "iid_monte_carlo"; },
    report => { report.probability_analysis.declaration.sampling.optimization = "random-cd"; },
    report => { report.probability_analysis.declaration.independence = "INFERRED"; },
    report => { report.probability_analysis.declaration.marginals[0].distribution = "normal"; },
    report => { report.probability_analysis.physical = "PASS"; },
    report => { report.source.type = "optimization"; },
  ];
  for (const change of changes) { const report = fixture(); change(report); assert.throws(() => view.summary(report)); }
});

test("no valid outcome leaves probability/statistics null and the finite unknown-outcome range visible", () => {
  const report = fixture(), analysis = report.probability_analysis;
  report.samples.forEach(row => { row.usable = false; }); analysis.samples.forEach(row => { row.usable = false; });
  const exclusions = sampleIds.map(id => ({ id, reason: "ROW_UNUSABLE" }));
  report.analysis.exclusions = exclusions.map(row => ({ ...row }));
  for (const row of report.analysis.statistics) Object.assign(row, { count: 0, mean: null, std: null, min: null, max: null, quantiles: { q05: null, q50: null, q95: null } });
  report.analysis.sensitivity.forEach(row => { Object.assign(row, { rank: 0, sample_ids: [], response_mean: null, response_std: null }); });
  report.analysis.surrogate.forEach(row => { Object.assign(row, { rank: 0, train_ids: [], test_ids: [] }); });
  Object.assign(report.analysis.pareto, { valid: false, reason: "NO_ELIGIBLE_SAMPLES", nondominated_ids: [] });
  analysis.valid_sample_ids = []; analysis.counts = { declared: 4, valid: 0, excluded: 4 }; analysis.exclusions = exclusions;
  analysis.statistics = report.analysis.statistics.map(row => ({ ...row, quantiles: { ...row.quantiles } }));
  analysis.thresholds.forEach(row => { Object.assign(row, { exceedance_count: 0, n_valid: 0, n_excluded: 4, probability_estimate: null, valid: false,
    reason: "NO_VALID_NUMERICAL_RESPONSES", unknown_outcome_fraction_bounds: { lower: 0, upper: 1 } }); });
  const node = container(); view.render(node, report);
  assert(rows(node).some(row => row[0] === "T-positive · signed_response > 0" && row[2] === "0/0" && row[3] === "사용 불가 · 유효 수치 응답 없음" && row[5] === "[0, 1]"));
  assert.equal(view.summary(report).thresholds[0].probability_estimate, null);
  assert(rows(node).filter(row => row[0] === "signed_response").every(row => row.slice(3).every(cell => cell === "사용 불가")));
  analysis.thresholds[0].probability_estimate = 0; assert.throws(() => view.summary(report));
});

test("source strings remain literal and whole-precision raw detail retains original negative zero and invalid null", () => {
  const report = fixture(), unsafe = '<img src=x onerror="BAD"><script>BAD</script>';
  report.declaration.probability.source.reference = unsafe; report.probability_analysis.declaration.source.reference = unsafe;
  report.probability_analysis.limitations.push(unsafe); report.probability_analysis.samples[2].responses.reaction.reason = unsafe;
  report.samples[0].responses.signed_response.value = -0; report.probability_analysis.samples[0].responses.signed_response.value = -0;
  const node = container(); view.render(node, report);
  assert(node.textContent.includes(unsafe)); assert(!walk(node).some(node => ["IMG", "SCRIPT"].includes(node.tagName)));
  const raw = walk(node).find(node => node.tagName === "PRE"), parsed = JSON.parse(raw.textContent);
  assert(Object.is(parsed.samples[0].responses.signed_response.value, -0)); assert.equal(parsed.samples[2].responses.reaction.value, null);
  assert.equal(parsed.samples[2].responses.reaction.reason, unsafe); assert.deepEqual(parsed.declaration.source, report.declaration.probability.source);
  report.probability_analysis.samples[0].responses.signed_response.value = 0; assert.throws(() => view.summary(report));
});

test("safe own JSON gate rejects getters, prototype keys and cycles before any supplied accessor is executed", () => {
  let calls = 0; const report = fixture(); Object.defineProperty(report, "probability_analysis", { enumerable: true, get() { calls++; return {}; } });
  assert.throws(() => view.summary(report)); assert.equal(calls, 0);
  const changes = [
    report => { report.probability_analysis.limitations[0] = undefined; },
    report => { report.probability_analysis.extra = 1; },
    report => { report.probability_analysis.declaration.source = JSON.parse('{"origin":"SYNTHETIC","reference":"ok","__proto__":{}}'); },
    report => { report.probability_analysis.self = report.probability_analysis; },
    report => { delete report.probability_analysis.samples[1]; },
  ];
  for (const change of changes) { const report = fixture(); change(report); assert.throws(() => view.summary(report)); }
});

test("UMD browser dependency is explicit and summary accepts cross-realm Core JSON without fetching/recomputing", () => {
  const source = fs.readFileSync(path.join(__dirname, "../apps/lab/static/probability-view.js"), "utf8"), report = fixture();
  const missing = vm.createContext({ window: {} }); vm.runInContext(source, missing);
  assert.throws(() => missing.window.probabilityView.summary(report), /campaignAnalysisView/);
  const context = vm.createContext({ window: { campaignAnalysisView: campaign }, fetch() { throw new Error("No runtime calls in helper"); }, raw: JSON.stringify(report), pins: expected(report) });
  vm.runInContext(source, context); const output = vm.runInContext("window.probabilityView.summary(JSON.parse(raw), pins)", context);
  assert.equal(output.counts.valid, 2); assert.equal(output.thresholds[0].probability_estimate, 0.5); assert.equal(output.report_context.source_pin_check.matched_keys.length, 4);
  assert.deepEqual(Object.keys(context.window.probabilityView).sort(), ["render", "summary"]);
});
