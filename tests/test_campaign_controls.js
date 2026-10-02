"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const vm = require("node:vm");
const controls = require("../apps/lab/static/campaign-controls.js");
const { validateDiscovery, eligibleModelEntries, modelPlanArguments } = controls;
const backend = "test.declared_model";
const revision = "a".repeat(64), source = "d".repeat(64);
const copy = (value) => structuredClone(value);
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
  assert.deepEqual(Object.keys(controls).sort(), ["eligibleModelEntries", "modelPlanArguments", "validateDiscovery"]);
  const browser = { window: {} };
  vm.runInNewContext(readFileSync(require.resolve("../apps/lab/static/campaign-controls.js"), "utf8"), browser);
  assert.deepEqual(Object.keys(browser.window.campaignControls).sort(), Object.keys(controls).sort());
  assert.equal(typeof browser.window.campaignControls.modelPlanArguments, "function");
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
