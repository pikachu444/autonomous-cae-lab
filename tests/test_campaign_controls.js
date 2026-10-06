"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const vm = require("node:vm");
const controls = require("../apps/lab/static/campaign-controls.js");
const { validateDiscovery, eligibleModelEntries, modelPlanArguments, fixtureOptimizationDefaults } = controls;
const backend = "test.declared_model";
const revision = "a".repeat(64), source = "d".repeat(64);
const copy = (value) => structuredClone(value);

test("common target preparation preserves signed response, origin and user normalization for every existing source", () => {
  for (const source of ["cad", "analysis", "model"]) {
    const objective = controls.objectiveFromFields({ source, metric: "signed_response", unit: "mm", direction: "match",
      target: "-2.5", scale: "0.25", origin: "MEASURED_REPORTED", reference: "reported sensor Z at fixed load" });
    assert.deepEqual(objective, { source, metric: "signed_response", unit: "mm", direction: "match", target: -2.5,
      scale: 0.25, origin: "MEASURED_REPORTED", reference: "reported sensor Z at fixed load" });
  }
  const legacy = controls.objectiveFromFields({ source: "model", metric: "response", unit: "N", direction: "minimize",
    target: "", scale: "", origin: "", reference: "" });
  assert.deepEqual(legacy, { source: "model", metric: "response", unit: "N", direction: "minimize" });
});

test("target preparation rejects blanks, implicit conversions, false qualification and accessors", () => {
  const fields = { source: "model", metric: "response", unit: "N", direction: "match", target: "0", scale: "1",
    origin: "DESIGN_TARGET", reference: "User target" };
  for (const patch of [{ target: "" }, { target: " " }, { target: "0x10" }, { target: "1 N" }, { scale: "0" },
    { scale: "Infinity" }, { target: true }, { reference: " " }, { origin: "VERIFIED_MEASUREMENT" }]) {
    assert.throws(() => controls.objectiveFromFields({ ...fields, ...patch }));
  }
  let reads = 0;
  const unsafe = { ...fields }; Object.defineProperty(unsafe, "direction", { enumerable: true, get() { reads++; return "match"; } });
  assert.throws(() => controls.objectiveFromFields(unsafe)); assert.equal(reads, 0);
  assert.throws(() => controls.validateObjective(unsafe)); assert.equal(reads, 0);
});

test("human constraints preserve signed bounds and require exact unit and positive scale", () => {
  const fields = { source: "analysis", metric: "signed_reaction", unit: "N", operator: ">=", limit: "-100", scale: "20" };
  assert.deepEqual(controls.constraintFromFields(fields), { source: "analysis", metric: "signed_reaction", unit: "N", operator: ">=", limit: -100, scale: 20 });
  for (const patch of [{ limit: "" }, { scale: "" }, { scale: "0" }, { unit: "" }, { operator: "=" }, { limit: "NaN" }, { scale: "0x10" }]) {
    assert.throws(() => controls.constraintFromFields({ ...fields, ...patch }));
  }
});

test("declared-model target uses the same frozen numerical payload", () => {
  const input = fields(); input.objective = { ...input.objective, direction: "match", target: -0.5, scale: 2,
    origin: "SYNTHETIC", reference: "Explicit test target" };
  const payload = modelPlanArguments(input, context());
  assert.deepEqual(payload.objective, input.objective); assert.notStrictEqual(payload.objective, input.objective);
  assert.deepEqual(payload.constraints, input.constraints); assert.equal(payload.engine, "scipy.differential_evolution");
});
function freeze(value) {
  if (value && typeof value === "object") { Object.values(value).forEach(freeze); Object.freeze(value); }
  return value;
}
function discovery() {
  return [
    { native: { backend, document: revision, object: "declared_inputs", path: "modulus", alias: "" },
      label: "Declared modulus", unit: "MPa", value: 200000, lower: 100000, upper: 300000, source_sha256: source },
    { native: { backend, document: revision, object: "declared_inputs", path: "pressure", alias: "" },
      label: "Declared pressure", unit: "MPa", value: 1, lower: 0.1, upper: 10, source_sha256: source },
  ];
}
function registered(candidate, id) {
  return { parameter_id: id, display_name: candidate.label, native: copy(candidate.native), unit: candidate.unit,
    current_value: candidate.value, default_value: candidate.value, lower_bound: candidate.lower, upper_bound: candidate.upper,
    mode: "free", kind: "continuous", dependencies: [], input_effect: { status: "PASS", qualification: "UNKNOWN" },
    source: "Declared model input discovery", source_sha256: candidate.source_sha256, target: "model_analysis",
    model_template_revision: candidate.native.document };
}
function context() {
  const candidates = discovery();
  return { backend, settings: { inputs: { modulus: 200000, pressure: 1 }, mesh: { cells: 12 },
    material: { source: "TEST INPUT: unqualified", qualified: false }, metadata: { note: "Keep\nall UTF-8 의미", absent: null,
      tolerances: [1e-9, 0], audit: true } },
  entries: [registered(candidates[0], "research_E"), registered(candidates[1], "research_pressure")] };
}
function fields() {
  return { study_id: "S-model-ui", campaign_id: "C-model-ui", parameter_ids: ["research_pressure", "research_E"],
    seed: 13, objective: { source: "model", metric: "test_response", unit: "mm", direction: "minimize" },
    constraints: [{ source: "model", metric: "test_limit", unit: "MPa", operator: "<=", limit: 123.45, scale: 17.5 },
      { source: "model", metric: "signed_test_response", unit: "mm", operator: ">=", limit: -0.003, scale: 0.001 }],
    max_generations: 3, population_size: 7, initial_values: { research_pressure: 1.25, research_E: 190000 },
    required_validations: { model: ["declared_input_roundtrip", "test_numerical_check"] }, engine: "scipy.differential_evolution" };
}

test("actual Candidate shape is returned unchanged through Node and browser UMD exports", () => {
  const candidates = freeze(discovery()), before = JSON.stringify(candidates);
  assert.strictEqual(validateDiscovery(candidates, backend), candidates);
  assert.equal(JSON.stringify(candidates), before);
  assert.deepEqual(Object.keys(controls).sort(), ["conditionPlanArguments", "conditionSelection", "conditionTemplate", "constraintFromFields", "eligibleModelEntries", "fixtureOptimizationDefaults", "modelDoeArguments", "modelPlanArguments", "objectiveFromFields", "validateDiscovery", "validateObjective"]);
  const browser = { window: {} };
  vm.runInNewContext(readFileSync(require.resolve("../apps/lab/static/campaign-controls.js"), "utf8"), browser);
  assert.deepEqual(Object.keys(browser.window.campaignControls).sort(), Object.keys(controls).sort());
  assert.equal(typeof browser.window.campaignControls.modelPlanArguments, "function");
  assert.equal(typeof browser.window.campaignControls.fixtureOptimizationDefaults, "function");
});

test("discovery refuses missing, malformed, mixed or invented native input identities without mutation", () => {
  const mutations = [
    () => [], () => Array.from({ length: 33 }, () => discovery()[0]), () => ({}),
    (items) => { items[0] = null; }, (items) => { items.push(copy(items[0])); },
    (items) => { items[0].native.backend = "fixture.cadquery"; },
    (items) => { items[0].native.document = "x".repeat(64); },
    (items) => { items[1].native.document = "b".repeat(64); },
    (items) => { items[1].source_sha256 = "c".repeat(64); },
    (items) => { items[0].source_sha256 = "d".repeat(63); },
    (items) => { items[0].native.object = "CAD_Object"; },
    (items) => { items[0].native.path = "arbitrary.settings.path"; },
    (items) => { items[0].native.alias = "invented"; },
    (items) => { items[0].native.selector = "extra"; },
    (items) => { items[0].undeclared = 1; },
    (items) => { items[0].label = " "; }, (items) => { items[0].unit = ""; },
    (items) => { items[0].value = true; }, (items) => { items[0].value = 1; },
    (items) => { items[0].lower = null; }, (items) => { items[0].upper = Infinity; },
    (items) => { items[0].upper = items[0].lower; },
  ];
  for (const mutate of mutations) {
    let candidates = discovery(); candidates = mutate(candidates) ?? candidates;
    const before = JSON.stringify(candidates);
    assert.throws(() => validateDiscovery(candidates, backend));
    assert.equal(JSON.stringify(candidates), before);
  }
});

test("mixed registry eligibility excludes CAD, foreign, fixed, integer and unverified bindings", () => {
  const candidates = discovery(), valid = registered(candidates[0], "research_E");
  const invalid = [
    { target: "cad", geometry_effect: { status: "PASS" } },
    { native: { ...valid.native, backend: "other.model" } },
    { mode: "fixed" }, { kind: "integer" }, { input_effect: { status: "UNKNOWN" } },
    { input_effect: { status: "FAIL" } }, { native: { ...valid.native, alias: "unexpected" } },
  ].map((patch, index) => ({ ...copy(valid), parameter_id: `excluded_${index}`, ...patch }));
  const entries = freeze([null, {}, ...invalid, valid]), before = JSON.stringify(entries);
  const result = eligibleModelEntries(entries, candidates, backend);
  assert.deepEqual(result, [valid]); assert.strictEqual(result[0], valid);
  assert.equal(JSON.stringify(entries), before);
});

test("source, template, unit, current-value and registered-bound drift remove stale entries", () => {
  const candidates = discovery(), valid = registered(candidates[0], "research_E");
  const patches = [
    { source_sha256: "b".repeat(64) }, { model_template_revision: "b".repeat(64) },
    { native: { ...valid.native, document: "b".repeat(64) }, model_template_revision: "b".repeat(64) },
    { unit: "Pa" }, { current_value: valid.current_value + 1 },
    { lower_bound: valid.lower_bound - 1 }, { upper_bound: valid.upper_bound + 1 },
    { lower_bound: valid.current_value + 1 }, { upper_bound: valid.current_value - 1 },
    { lower_bound: valid.current_value, upper_bound: valid.current_value },
    { lower_bound: NaN }, { current_value: String(valid.current_value) },
  ];
  for (const patch of patches) assert.deepEqual(eligibleModelEntries([{ ...copy(valid), ...patch }], candidates, backend), []);
  const narrower = { ...copy(valid), lower_bound: 150000, upper_bound: 250000 };
  assert.deepEqual(eligibleModelEntries([narrower], candidates, backend), [narrower]);
  const wide = [copy(candidates[0])]; wide[0].lower = -1e308; wide[0].upper = 1e308;
  assert.strictEqual(validateDiscovery(wide, backend), wide);
  assert.deepEqual(eligibleModelEntries([registered(wide[0], "overflow")], wide, backend), []);
});

test("exact existing API payload preserves user settings, constraints, initials and budgets", () => {
  const input = fields(), selected = context();
  selected.settings.metadata.negative_zero = -0;
  selected.settings.metadata.proto_data = JSON.parse('{"__proto__":{"keep":"JSON data"}}');
  const originalFields = JSON.stringify(input), originalSettings = JSON.stringify(selected.settings);
  freeze(input); freeze(selected);
  const request = modelPlanArguments(input, selected);
  assert.deepEqual(request, { ...input, backend, settings: selected.settings });
  assert.equal(JSON.stringify(request.settings), originalSettings);
  assert.equal(JSON.stringify(input), originalFields);
  assert.equal(Object.is(request.settings.metadata.negative_zero, -0), true);
  assert.equal(Object.hasOwn(request.settings.metadata.proto_data, "__proto__"), true);
  assert.notStrictEqual(request.settings, selected.settings);
  assert.notStrictEqual(request.objective, input.objective);
  assert.equal("entries" in request, false);
  assert.equal("model" in request, false); assert.equal("analysis_settings" in request, false);
});

test("CAD sources, unsupported keys, duplicate or foreign IDs and the wrong engine are refused", () => {
  const mutations = [
    (input) => { input.model = "CAD"; }, (input) => { input.backend = "fixture.cadquery"; },
    (input) => { input.analysis_backend = "fixture.calculix"; }, (input) => { input.analysis_settings = {}; },
    (input) => { input.cad = {}; }, (input) => { input.settings = {}; },
    (input) => { input.objective.source = "cad"; }, (input) => { input.objective.source = "analysis"; },
    (input) => { input.constraints[0].source = "analysis"; },
    (input) => { input.required_validations = { cad: [], analysis: [] }; },
    (input) => { input.required_validations.analysis = []; },
    (input) => { input.parameter_ids = ["research_E", "research_E"]; },
    (input) => { input.parameter_ids = ["unregistered"]; }, (input) => { input.parameter_ids = []; },
    (input) => { input.engine = "other.optimizer"; },
  ];
  for (const mutate of mutations) { const input = fields(); mutate(input); assert.throws(() => modelPlanArguments(input, context())); }
  const selected = context(); selected.entries[0].target = "cad";
  assert.throws(() => modelPlanArguments(fields(), selected));
  selected.entries = context().entries; selected.backend = "other.model";
  assert.throws(() => modelPlanArguments(fields(), selected));
  const duplicate = context(); duplicate.entries.push(copy(duplicate.entries[0]));
  assert.throws(() => modelPlanArguments(fields(), duplicate));
});

test("nonfinite or non-JSON values anywhere cannot be silently serialized away", () => {
  const cases = [
    (input) => { input.constraints[0].limit = NaN; },
    (input) => { input.initial_values.research_E = Infinity; },
    (input) => { input.objective.unit = undefined; },
    (input, selected) => { selected.settings.metadata.tolerances[0] = -Infinity; },
    (input, selected) => { selected.settings.metadata.callback = () => 1; },
    (input, selected) => { selected.settings.metadata.large = 1n; },
    (input, selected) => { selected.settings.metadata.cycle = selected.settings; },
    (input, selected) => { selected.settings.metadata.symbol = Symbol("not JSON"); },
    (input, selected) => { selected.settings.metadata.sparse = new Array(2); },
    (input, selected) => { selected.settings.metadata[Symbol("hidden")] = Infinity; },
  ];
  for (const mutate of cases) { const input = fields(), selected = context(); mutate(input, selected); assert.throws(() => modelPlanArguments(input, selected)); }
  const selected = context(); let reads = 0;
  Object.defineProperty(selected.settings.metadata, "getter", { enumerable: true, get() { reads += 1; return 1; } });
  assert.throws(() => modelPlanArguments(fields(), selected)); assert.equal(reads, 0);
});

test("existing seed, budget, selector and initial-value limits are checked without inserting defaults", () => {
  const invalid = [
    { study_id: ["S-valid"] }, { campaign_id: ["C-valid"] }, { campaign_id: "C".repeat(59) },
    { seed: -1 }, { seed: 2 ** 32 }, { seed: true }, { seed: "13" },
    { max_generations: 0 }, { max_generations: 101 }, { max_generations: 1.5 },
    { population_size: 4 }, { population_size: 65 }, { max_generations: 8, population_size: 64 },
    { initial_values: { research_E: 190000 } },
    { initial_values: { research_E: 99000, research_pressure: 1 } },
    { required_validations: { model: ["same", "same"] } }, { required_validations: { model: [""] } },
    { objective: { source: "model", metric: "test_response", unit: "mm", direction: "automatic" } },
    { constraints: [{ source: "model", metric: "test_limit", unit: "MPa", operator: "<=", limit: 1, scale: 0 }] },
  ];
  for (const patch of invalid) assert.throws(() => modelPlanArguments({ ...fields(), ...patch }, context()));
  const missing = fields(); delete missing.initial_values;
  assert.throws(() => modelPlanArguments(missing, context()));
  for (const seed of [0, 2 ** 32 - 1]) {
    const input = { ...fields(), seed, max_generations: 7, population_size: 64, initial_values: null,
      required_validations: { model: [] }, constraints: [] };
    assert.deepEqual(modelPlanArguments(input, context()), { ...input, backend, settings: context().settings });
  }
});

function fixtureSettings(mesh = { mode: "selected", max_sizes_mm: [4] }) {
  return { load: { force_per_support_N: 150, source: "TEST_ONLY hypothetical signed -Z saddle load" },
    material: { model: "isotropic", E_MPa: 210000, nu: 0.3, qualification: "HYPOTHETICAL_UNQUALIFIED" },
    mesh, metadata: { signed_value: -0.00003, unit: "mm", unchanged: [true, null] } };
}

test("selected-mesh defaults address existing reaction validation without demanding absent mesh evidence or a physical limit", () => {
  const settings = freeze(fixtureSettings()), before = JSON.stringify(settings);
  const defaults = fixtureOptimizationDefaults(settings);
  // TEST_ONLY selected-output shape: no mesh-trend verdict, invalid sensitivity and stress are retained.
  const selectedOutput = freeze({ metrics: {
    max_displacement: { value: 0.0098, unit: "mm", valid: true },
    displacement_mesh_change_ratio: { value: null, unit: "1", valid: false },
    peak_stress: { value: 7, unit: "MPa", valid: false },
    whole_field_norm: { value: 0.012, unit: "mm", valid: true },
  }, validations: [{ type: "mesh_0_reaction_balance", status: "PASS", limit: 0.01 },
    { type: "material_qualification", status: "UNKNOWN" }], decision: "NOT_RELEASED" });
  const outputBefore = JSON.stringify(selectedOutput);
  assert.equal(defaults.meshMode, "selected");
  assert.deepEqual(defaults.required_validations, { cad: [], analysis: ["mesh_0_reaction_balance"] });
  assert.equal(defaults.required_validations.analysis.every((name) => selectedOutput.validations.some((item) =>
    item.type === name && item.status === "PASS")), true);
  assert.deepEqual(defaults.constraints, []); // 0.0098 > the historical 0.0065 screen must not introduce a selected constraint.
  assert.deepEqual(defaults.objective, { source: "analysis", metric: "max_displacement", unit: "mm", direction: "minimize" });
  assert.equal(selectedOutput.metrics[defaults.objective.metric].value, 0.0098);
  assert.notEqual(selectedOutput.metrics[defaults.objective.metric].value, selectedOutput.metrics.whole_field_norm.value);
  assert.match(defaults.objectiveLabel, /안장.*\|UZ\|/);
  assert.match(defaults.note, /민감도.*미평가/); assert.match(defaults.note, /물리적 허용 변위.*설정하지/);
  assert.equal(JSON.stringify(selectedOutput), outputBefore); assert.equal(JSON.stringify(settings), before);
});

test("legacy refinement retains every existing numerical requirement and explicitly qualifies the historical virtual screen", () => {
  for (const sizes of [[4, 2], [4, 3, 2], [8, 7, 6, 5, 4, 3, 2, 1]]) {
    const settings = freeze(fixtureSettings({ max_sizes_mm: sizes })), before = JSON.stringify(settings);
    const defaults = fixtureOptimizationDefaults(settings);
    assert.equal(defaults.meshMode, "refinement");
    assert.deepEqual(defaults.required_validations.analysis, ["displacement_mesh_trend",
      ...Array.from({ length: sizes.length }, (_value, index) => `mesh_${index}_reaction_balance`)]);
    assert.deepEqual(defaults.required_validations.cad, []);
    assert.deepEqual(defaults.constraints, [
      { source: "analysis", metric: "max_displacement", unit: "mm", operator: "<=", limit: 0.0065, scale: 0.0065 },
    ]);
    assert.match(defaults.note, /0\.0065 mm.*과거 가상/); assert.match(defaults.note, /제작 승인이 아닙니다/);
    assert.equal(Object.hasOwn(settings.mesh, "mode"), false); assert.equal(JSON.stringify(settings), before);
  }
});

test("malformed modes and mesh declarations are refused rather than falling back to a usable plan", () => {
  for (const mode of ["refinement", "SELECTED", " selected", "selected ", "", null, false, 0, [], {}]) {
    const settings = fixtureSettings({ mode, max_sizes_mm: [4] }), before = JSON.stringify(settings);
    assert.throws(() => fixtureOptimizationDefaults(settings)); assert.equal(JSON.stringify(settings), before);
  }
  for (const mesh of [null, [], {}, { mode: "selected" }, { mode: "selected", max_sizes_mm: [] },
    { mode: "selected", max_sizes_mm: [4, 2] }, { max_sizes_mm: [4] },
    { max_sizes_mm: Array.from({ length: 9 }, (_item, index) => 10 - index) },
    { max_sizes_mm: [2, 4] }, { max_sizes_mm: [4, 4] },
    { mode: "selected", max_sizes_mm: ["4"] }, { mode: "selected", max_sizes_mm: [true] },
    { mode: "selected", max_sizes_mm: [0] }, { mode: "selected", max_sizes_mm: [-4] },
    { mode: "selected", max_sizes_mm: [NaN] }, { mode: "selected", max_sizes_mm: [Infinity] },
    { mode: "selected", max_sizes_mm: [4], extra: "undeclared" }]) {
    assert.throws(() => fixtureOptimizationDefaults(fixtureSettings(mesh)));
  }
  for (const settings of [null, [], {}, { mesh: { max_sizes_mm: [4, 2] }, other: Infinity }]) {
    assert.throws(() => fixtureOptimizationDefaults(settings));
  }
});

test("default calculation does not read accessors, inherited declarations or sparse/non-JSON settings", () => {
  const settings = fixtureSettings(); let reads = 0;
  Object.defineProperty(settings.mesh, "mode", { enumerable: true, get() { reads += 1; return "selected"; } });
  assert.throws(() => fixtureOptimizationDefaults(settings)); assert.equal(reads, 0);
  assert.throws(() => fixtureOptimizationDefaults(Object.create({ mesh: { mode: "selected", max_sizes_mm: [4] } })));
  const sparse = fixtureSettings({ mode: "selected", max_sizes_mm: new Array(1) });
  assert.throws(() => fixtureOptimizationDefaults(sparse));
  const cyclic = fixtureSettings(); cyclic.metadata.loop = cyclic;
  assert.throws(() => fixtureOptimizationDefaults(cyclic));
});

test("fresh defaults can be edited without mutating the original settings, other plans or existing parameter bounds", () => {
  const settings = freeze(fixtureSettings()), before = JSON.stringify(settings);
  const first = fixtureOptimizationDefaults(settings), second = fixtureOptimizationDefaults(settings);
  first.objective.metric = "whole_field_norm"; first.required_validations.analysis.push("invented");
  first.required_validations.cad.push("invented"); first.constraints.push({ limit: 1 });
  assert.equal(second.objective.metric, "max_displacement");
  assert.deepEqual(second.required_validations, { cad: [], analysis: ["mesh_0_reaction_balance"] });
  assert.deepEqual(second.constraints, []); assert.equal(JSON.stringify(settings), before);
  const oldPlan = freeze(fields()), oldContext = freeze(context());
  assert.deepEqual(modelPlanArguments(oldPlan, oldContext), { ...oldPlan, backend, settings: oldContext.settings });
  const outsideBounds = fields(); outsideBounds.initial_values.research_E = 99000;
  assert.throws(() => modelPlanArguments(outsideBounds, oldContext));
  assert.equal("settings" in second, false); assert.equal("parameter_ids" in second, false);
  const legacy = fixtureSettings({ max_sizes_mm: [4, 2] });
  const editedLegacy = fixtureOptimizationDefaults(legacy); editedLegacy.constraints[0].limit = 999;
  assert.equal(fixtureOptimizationDefaults(legacy).constraints[0].limit, 0.0065);
});
