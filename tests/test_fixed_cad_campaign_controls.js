"use strict";

// Synthetic records and controlled DOM only; Root owns actual native/browser/provider acceptance.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const vm = require("node:vm");
const controls = require("../apps/lab/static/fixed-cad-campaign-controls.js");
const campaigns = require("../apps/lab/static/campaign-controls.js");
const sourceText = readFileSync(require.resolve("../apps/lab/static/fixed-cad-campaign-controls.js"), "utf8");
const campaignText = readFileSync(require.resolve("../apps/lab/static/campaign-controls.js"), "utf8");
const html = readFileSync(require.resolve("../apps/lab/static/index.html"), "utf8");
const hash = value => value.repeat(64);
const clone = value => structuredClone(value);
const frozen = value => { if (value && typeof value === "object") { Object.values(value).forEach(frozen); Object.freeze(value); } return value; };
const face = name => `F-${hash("1")}-${name}`;
const backend = "structure.calculix.native";
const research = require('../apps/lab/static/comparison-research.js');
function record() {
  const source = { experiment_id: "E-imported", study_id: "S-research", backend: "fixture.freecad", cad_revision: hash("a"),
    result_sha256: hash("b"), proposal_sha256: hash("c"), thread_sha256: hash("d") };
  const declaration = { analysis_type: "linear_static", coordinate_system: "global", units: { length: "mm", force: "N", stress: "MPa" },
    materials: [{ id: "M1", selection_id: "B-final", law: "isotropic_linear_elastic", young_modulus_MPa: 210000, poisson_ratio: 0.27,
      source: { category: "MEASURED_REPORTED", description: "TEST: user report <unqualified>" } }],
    boundary_conditions: [
      { id: "BC1", selection_id: face("Face1"), type: "displacement", coordinate_system: "global", components: { UX: 0 }, unit: "mm", source: "ASSUMED: X symmetry" },
      { id: "BC2", selection_id: face("Face2"), type: "displacement", coordinate_system: "global", components: { UY: 0 }, unit: "mm", source: "ASSUMED: Y symmetry" },
      { id: "BC3", selection_id: face("Face3"), type: "displacement", coordinate_system: "global", components: { UZ: 0 }, unit: "mm", source: "ASSUMED: Z symmetry" }],
    loads: [{ id: "L1", selection_id: face("Face4"), type: "resultant_force", coordinate_system: "global", components: { FX: 25, FY: 0, FZ: -250 }, unit: "N", source: "ASSUMED: signed XYZ resultant" }],
    contact: { mode: "none", source: "ASSUMED: no contact" }, mesh: { mode: "selected", max_size_mm: 2.5 } };
  const regions = [{ id: "B-final", label: "최종 솔리드", kind: "whole_final_solid", roles: ["material"] },
    ...[1, 2, 3, 4].map(index => ({ id: face(`Face${index}`), native_name: `Face${index}`, native_object: "Box",
      body_id: "B-final", kind: "native_face", roles: ["boundary", "load"], coordinate_system: "global", native_coordinate_system: "cad_document_global",
      area_mm2: 80, center_mm: [index, 0, 0], unit: "mm", geometry_sha256: hash("2") }))];
  return { schema_version: "1.0", id: "C0-native", source, catalog_revision: hash("e"), conditions_revision: hash("f"),
    catalog: { schema_version: "1.0", selections: regions, coordinate_systems: [] },
    request: { conditions_id: "C0-native", experiment_id: "E-imported", cad_revision: hash("a"), catalog_revision: hash("e"), backend, declaration },
    support: { status: "SUPPORTED_DECLARED_INPUTS", reasons: [], native_runtime: "NOT_CHECKED" },
    adapter_binding: { backend, version: "TEST_NATIVE_1", policy_sha256: hash("3"), settings: { server_owned: true }, settings_sha256: hash("4") },
    engineering: "UNKNOWN", decision: "NOT_RELEASED" };
}
function context() { return { store: "local", studyId: "S-research", backend: "fixture.freecad", model: "native/N-model" }; }
function inspection(saved = record()) {
  return { integrity: "VERIFIED", result: { experiment_id: saved.source.experiment_id, study: { id: saved.source.study_id },
    cad_revision: saved.source.cad_revision, provenance: { adapter: saved.source.backend }, solver_status: "NOT_RUN", status: "COMPLETED_REVIEW_REQUIRED", decision: "NOT_RELEASED" },
    proposal: { id: saved.source.experiment_id, study_id: saved.source.study_id, model: { geometry: { backend: "fixture.freecad", source: "native/N-model" } }, parameters: {} },
    hashes: { result_sha256: saved.source.result_sha256, proposal_sha256: saved.source.proposal_sha256, thread_sha256: saved.source.thread_sha256 },
    registry_snapshot: { entries: [] } };
}
function selected(saved = record()) { return controls.selection(saved, inspection(saved), context()); }
function current(saved = record()) { return { ...context(), conditionsId: saved.id, conditionsRevision: saved.conditions_revision,
  cadRevision: saved.source.cad_revision, catalogRevision: saved.catalog_revision }; }
function discovery(saved = record()) {
  const descriptors = [
    { id: "material_M1_E", label: "Young modulus E (M1; numerical bounds; qualification UNKNOWN)", unit: "MPa", value: 210000, lower: 21000, upper: 2100000, declaration_path: ["materials", 0, "young_modulus_MPa"] },
    { id: "material_M1_nu", label: "Poisson ratio nu", unit: "1", value: 0.27, lower: -0.99, upper: 0.49, declaration_path: ["materials", 0, "poisson_ratio"] },
    { id: "load_L1_FZ", label: "Global resultant FZ <signed>", unit: "N", value: -250, lower: -2500, upper: 2500, declaration_path: ["loads", 0, "components", "FZ"] }];
  return { source: clone(saved.source), backend, conditions_id: saved.id, conditions_revision: saved.conditions_revision,
    catalog_revision: saved.catalog_revision, template_revision: hash("5"), condition_input_descriptors_sha256: hash("6"), descriptors,
    candidates: descriptors.map(item => ({ native: { backend, document: hash("5"), object: "analysis_conditions", path: item.id, alias: "" },
      label: item.label, unit: item.unit, value: item.value, lower: item.lower, upper: item.upper, source_sha256: hash("5") })),
    fingerprint: { backend, version: "TEST_NATIVE_1", projection_policy_sha256: hash("3"), input_policy: { "test-domain.py": hash("7") } },
    record: clone(saved), reference: { id: saved.id, revision: saved.conditions_revision, catalog_revision: saved.catalog_revision,
      record_sha256: hash("8"), scope: "USER_DECLARED_UNVERIFIED" }, rebind_policy: "FIXED_CAD_NO_REBIND" };
}
function entry(candidate = discovery().candidates[0], parameterId = "research_E") {
  return { parameter_id: parameterId, display_name: "등록한 재료값", native: clone(candidate.native), unit: candidate.unit,
    current_value: candidate.value, default_value: candidate.value, lower_bound: candidate.lower, upper_bound: candidate.upper,
    mode: "free", kind: "continuous", dependencies: [], input_effect: { status: "PASS", scope: "DECLARED_SCALAR_BINDING_ONLY", physical: "UNKNOWN" },
    source_sha256: candidate.source_sha256, target: "analysis_conditions", conditions_id: "C0-native", conditions_template_revision: hash("5"), condition_input_descriptors_sha256: hash("6") };
}
function registerFields() { return { input_id: "load_L1_FZ", parameter_id: "load_scenario", display_name: "합력 FZ 범위", lower: -500, upper: -150, mode: "free" }; }
function fields() { return { study_id: "S-research", campaign_id: "C-native-search", conditions_id: "C0-native", parameter_ids: ["research_E", "research_FZ"],
  objective: { source: "analysis", metric: "max_displacement", unit: "mm", direction: "minimize" }, constraints: [], seed: 13,
  max_generations: 2, population_size: 5, initial_values: null, required_validations: { cad: [], analysis: [] }, engine: "scipy.differential_evolution" }; }
function planContext() { const advertised = discovery(); return { selection: selected(), discovery: advertised,
  entries: [entry(advertised.candidates[0]), entry(advertised.candidates[2], "research_FZ")] }; }
function plan() { return { route: "fixed_cad_analysis", study_id: "S-research", campaign_id: "C-native-search", fixed_cad: discovery(), status: "PLANNED" }; }
test('fixed CAD research handoff names retained scalar inputs and native condition snapshots, without AI search admission', () => {
  const frozenPlan = { ...plan(), backend: 'fixture.freecad', analysis: { backend }, objective: fields().objective, constraints: [] };
  const row = { index: 1, values: { research_E: 190000 }, cad_experiment_id: 'E-imported', cad_result_sha256: hash('b'),
    analysis_experiment_id: 'E-C-native-search-0001', analysis_result_sha256: hash('8'), conditions_id: 'C-C-native-search-0001',
    condition_binding_sha256: hash('9'), condition_declaration: record().request.declaration, condition_input_rejection: null, decision: 'NOT_RELEASED' };
  const data = frozen({ id: frozenPlan.campaign_id, type: 'optimization', plan: frozenPlan,
    record: { campaign_id: frozenPlan.campaign_id, study_id: frozenPlan.study_id, route: 'fixed_cad_analysis',
      status: 'COMPLETED_REVIEW_REQUIRED', decision: 'NOT_RELEASED', evaluations: [row] } });
  const draft = research.campaignDraft(data, 'S-research', [1]);
  assert.equal(draft.intent, 'INTERPRET_SAVED_RESULTS');
  for (const term of ['FIXED_CAD_NO_REBIND','research_E','190000','C-C-native-search-0001','ASSUMED','UNKNOWN','analysis_conditions_context','절점 ID']) assert(draft.question.includes(term), term);
  assert.deepEqual(draft.experimentIds, ['E-C-native-search-0001']);
  assert.throws(() => research.campaignDraft({ ...data, record: { status: 'PLANNED', plan: frozenPlan, evaluations: [] } }, 'S-research', []), /사람이 계획을 실행/);
  const stale = clone(data); stale.record.evaluations[0].cad_experiment_id = 'E-other';
  assert.throws(() => research.campaignDraft(stale, 'S-research', [1]), /실제 후보/);
});
function rejectChanges(make, mutations, operation) {
  for (const mutation of mutations) {
    const value = make(); mutation(value); const before = JSON.stringify(value);
    assert.throws(() => operation(value)); assert.equal(JSON.stringify(value), before);
  }
}

test("imported parent with zero registered CAD variables connects the exact saved native conditions without regeneration", () => {
  const saved = frozen(record()), parent = frozen(inspection(saved)), setting = frozen(context()), before = JSON.stringify([saved, parent, setting]);
  const value = controls.selection(saved, parent, setting);
  assert.equal(value.record.id, "C0-native"); assert.equal(value.model, "native/N-model");
  assert.equal(controls.sameContext(value, current(saved)), true);
  assert.equal(value.record.request.declaration.materials[0].source.category, "MEASURED_REPORTED");
  assert.deepEqual(value.record.request.declaration.boundary_conditions.map(item => item.components), [{ UX: 0 }, { UY: 0 }, { UZ: 0 }]);
  assert.equal(JSON.stringify([saved, parent, setting]), before);
  value.record.request.declaration.loads[0].components.FZ = 10;
  assert.equal(saved.request.declaration.loads[0].components.FZ, -250);
  assert.equal(Object.hasOwn(value, "sourceEntries"), false);
});

test("source hashes, CAD identity and same-store study/model changes fail closed", () => {
  rejectChanges(() => inspection(), [
    value => { value.integrity = "UNKNOWN"; }, value => { value.hashes.result_sha256 = hash("0"); },
    value => { value.hashes.proposal_sha256 = hash("0"); }, value => { value.hashes.thread_sha256 = hash("0"); },
    value => { value.result.cad_revision = hash("0"); }, value => { value.result.experiment_id = "E-other"; },
    value => { value.result.solver_status = "COMPLETED"; }, value => { value.result.decision = "RELEASED"; },
    value => { value.proposal.model.geometry.source = "native/N-other"; }, value => { value.proposal.study_id = "S-other"; }
  ], value => controls.selection(record(), value, context()));
  rejectChanges(context, [value => { value.studyId = "S-other"; }, value => { value.backend = "fixture.cadquery"; }, value => { value.model = "roller_support"; }],
    value => controls.selection(record(), inspection(), value));
});

test("unsupported solver, fake display face, contact and substituted whole-body loads are refused", () => {
  rejectChanges(record, [
    value => { value.request.backend = "fixture.calculix"; }, value => { value.support.status = "UNSUPPORTED_FOR_MODEL"; },
    value => { value.support.native_runtime = "AVAILABLE"; }, value => { value.adapter_binding = null; },
    value => { value.engineering = "PASS"; }, value => { value.request.catalog_revision = hash("0"); },
    value => { value.request.declaration.contact.mode = "frictionless"; }, value => { value.request.declaration.mesh.mode = "refinement"; },
    value => { value.request.declaration.loads[0].selection_id = "B-final"; },
    value => { value.catalog.selections[1].id = "display-triangle-1"; value.request.declaration.boundary_conditions[0].selection_id = "display-triangle-1"; },
    value => { value.catalog.selections[1].native_coordinate_system = "sensor"; },
    value => { value.request.declaration.boundary_conditions[0].components.URX = 0; },
    value => { value.request.declaration.loads[0].unit = "kN"; }
  ], value => controls.selection(value, inspection(value), context()));
});

test("store, study, C0 revision, native catalog and selected model invalidate selection keys", () => {
  const value = selected(), expected = controls.contextKey(value);
  for (const patch of [{ store: "reference" }, { studyId: "S-other" }, { backend: "fixture.cadquery" }, { model: "native/N-other" },
      { conditionsId: "C-new" }, { conditionsRevision: hash("0") }, { cadRevision: hash("0") }, { catalogRevision: hash("0") }]) {
    assert.equal(controls.sameContext(value, { ...current(), ...patch }), false);
  }
  const other = selected(); other.store = "reference";
  assert.notEqual(controls.contextKey(other), expected);
  assert.equal(controls.sameContext(value, context()), false);
  assert.equal(controls.sameContext(null, current()), false);
});

test("full Core discovery pins advertised material and signed force leaves without changing input bytes", () => {
  const advertised = frozen(discovery()), value = frozen(selected()), before = JSON.stringify(advertised);
  assert.strictEqual(controls.validateDiscovery(advertised, value), advertised);
  const permuted = clone(advertised); permuted.candidates.reverse();
  assert.strictEqual(controls.validateDiscovery(permuted, value), permuted);
  assert.equal(JSON.stringify(advertised), before);
});

test("discovery rejects C0/template/hash mismatch, duplicate inputs and native/descriptor substitution", () => {
  rejectChanges(discovery, [
    value => { value.source.result_sha256 = hash("0"); }, value => { value.conditions_id = "C-other"; },
    value => { value.conditions_revision = hash("0"); }, value => { value.catalog_revision = hash("0"); },
    value => { value.condition_input_descriptors_sha256 = "unknown"; }, value => { value.rebind_policy = "REVISION_REBIND_EXACT_SELECTIONS"; },
    value => { value.record.request.declaration.mesh.max_size_mm = 3; }, value => { value.reference.scope = "QUALIFIED"; },
    value => { value.fingerprint.version = "OTHER_VERSION"; }, value => { value.fingerprint.input_policy = {}; },
    value => { value.candidates[0].native.object = "declared_inputs"; }, value => { value.candidates[0].native.document = hash("0"); },
    value => { value.candidates[0].source_sha256 = hash("b"); }, value => { value.candidates[0].native.alias = "Face1"; },
    value => { value.candidates[0].native.selector = "triangle-1"; }, value => { value.candidates[0].value += 1; },
    value => { value.descriptors.push(clone(value.descriptors[0])); value.candidates.push(clone(value.candidates[0])); },
    value => { value.descriptors[0].declaration_path = ["boundary_conditions", 0, "components", "UX"]; },
    value => { value.descriptors[0].declaration_path = ["materials", "0", "young_modulus_MPa"]; },
    value => { value.descriptors[0].declaration_path = ["materials", 99, "young_modulus_MPa"]; },
    value => { value.descriptors[0].unit = "Pa"; value.candidates[0].unit = "Pa"; },
    value => { value.descriptors[0].value = Infinity; }, value => { value.candidates.pop(); }
  ], value => controls.validateDiscovery(value, selected()));
});

test("current registry eligibility separates condition variables from CAD/model mappings and source drift", () => {
  const advertised = discovery(), valid = entry(), invalid = [
    { target: "cad", geometry_effect: { status: "PASS" } }, { target: "model_analysis" }, { mode: "fixed" }, { kind: "integer" },
    { input_effect: { status: "UNKNOWN" } }, { conditions_id: "C-other" }, { conditions_template_revision: hash("0") },
    { condition_input_descriptors_sha256: hash("0") }, { source_sha256: hash("0") }, { unit: "Pa" }, { current_value: 1 },
    { native: { ...valid.native, backend: "fixture.calculix" } }, { native: { ...valid.native, alias: "other" } },
    { lower_bound: valid.lower_bound - 1 }, { upper_bound: valid.upper_bound + 1 }, { lower_bound: valid.current_value + 1 },
    { upper_bound: NaN }, { lower_bound: true }
  ].map((patch, index) => ({ ...clone(valid), parameter_id: `excluded_${index}`, ...patch }));
  const list = frozen([null, {}, ...invalid, valid]), before = JSON.stringify(list);
  assert.deepEqual(controls.eligibleEntries(list, advertised, selected()), [valid]);
  assert.strictEqual(controls.eligibleEntries(list, advertised, selected())[0], valid);
  assert.equal(JSON.stringify(list), before);
  const narrower = { ...clone(valid), lower_bound: 150000, upper_bound: 300000 };
  assert.deepEqual(controls.eligibleEntries([narrower], advertised, selected()), [narrower]);
});

test("registration freezes source C0 and supports explicit signed bounds without a declaration/settings payload", () => {
  const draft = frozen(registerFields()), before = JSON.stringify(draft);
  const request = controls.registerArguments(draft, frozen(discovery()), frozen(selected()));
  assert.deepEqual(request, { study_id: "S-research", conditions_id: "C0-native", ...draft });
  assert.equal(JSON.stringify(draft), before);
  for (const key of ["backend", "model", "analysis_settings", "declaration", "declaration_path", "native"]) assert.equal(Object.hasOwn(request, key), false);
  assert.equal(request.upper, -150);
});

test("registration rejects absent advertised ID, widening/coerced ranges and foreign source fields", () => {
  rejectChanges(registerFields, [
    value => { value.input_id = "UX"; }, value => { value.parameter_id = "1invalid"; }, value => { value.display_name = " "; },
    value => { value.lower = -2501; }, value => { value.upper = 2501; }, value => { value.upper = -300; },
    value => { value.upper = value.lower; }, value => { value.lower = "-500"; }, value => { value.upper = Infinity; },
    value => { value.mode = "fixed"; }, value => { value.study_id = "S-other"; }, value => { value.conditions_id = "C-other"; },
    value => { value.declaration_path = ["loads", 0, "components", "FZ"]; }
  ], value => controls.registerArguments(value, discovery(), selected()));
});

test("fixed-CAD DE plan uses exact existing numerical controls and no CAD regeneration or raw settings", () => {
  const input = frozen(fields()), pinned = frozen(planContext()), before = JSON.stringify([input, pinned]);
  const request = controls.planArguments(input, pinned);
  assert.deepEqual(request, input); assert.notStrictEqual(request.objective, input.objective);
  assert.equal(JSON.stringify([input, pinned]), before);
  assert.equal(request.objective.metric, "max_displacement"); assert.equal(request.objective.unit, "mm");
  for (const key of ["backend", "model", "settings", "analysis_backend", "analysis_settings", "source"]) assert.equal(Object.hasOwn(request, key), false);
  assert.deepEqual(controls.planArguments({ ...fields(), objective: { ...fields().objective, direction: "maximize" } }, planContext()).objective.direction, "maximize");
});

test("fixed-CAD target and explicit response bounds reuse common objective semantics", () => {
  const input = fields();
  input.objective = { ...input.objective, direction: "match", target: 0.001, scale: 0.002,
    origin: "DESIGN_TARGET", reference: "Declared target under the retained load" };
  input.constraints = [{ source: "analysis", metric: "max_displacement", unit: "mm", operator: "<=", limit: 0.003, scale: 0.003 }];
  assert.deepEqual(controls.planArguments(input, planContext()), input);
  const invalid = structuredClone(input); invalid.constraints[0].unit = "m";
  assert.throws(() => controls.planArguments(invalid, planContext()));
});

test("fixed plan rejects legacy/raw routes, wrong response semantics, hidden constraints and changed registry IDs", () => {
  rejectChanges(fields, [
    value => { value.backend = "fixture.freecad"; }, value => { value.model = "native/N-model"; }, value => { value.analysis_settings = {}; },
    value => { value.study_id = "S-other"; }, value => { value.conditions_id = "C-other"; }, value => { value.parameter_ids = []; },
    value => { value.parameter_ids = ["research_E", "research_E"]; }, value => { value.parameter_ids = ["unregistered"]; },
    value => { value.objective.source = "model"; }, value => { value.objective.unit = "m"; }, value => { value.objective.metric = "max_UZ"; },
    value => { value.objective.direction = "automatic"; }, value => { value.constraints = [{ source: "analysis", metric: "max_displacement", limit: 0.0065 }]; },
    value => { value.initial_values = { research_E: 210000, research_FZ: -250 }; }, value => { value.required_validations.analysis.push("strength_pass"); },
    value => { value.engine = "LLM"; }, value => { value.campaign_id = "C".repeat(59); }
  ], value => controls.planArguments(value, planContext()));
  const duplicate = planContext(); duplicate.entries.push(clone(duplicate.entries[0]));
  assert.throws(() => controls.planArguments(fields(), duplicate));
  const sameNative = planContext(); sameNative.entries[1] = { ...clone(sameNative.entries[0]), parameter_id: "research_FZ" };
  assert.throws(() => controls.planArguments(fields(), sameNative));
  const stale = planContext(); stale.entries[0].conditions_template_revision = hash("0");
  assert.throws(() => controls.planArguments(fields(), stale));
});

test("seed/generation/population budget limits preserve existing numerical engine bounds", () => {
  for (const patch of [{ seed: -1 }, { seed: 2 ** 32 }, { seed: "13" }, { max_generations: 0 }, { max_generations: 101 },
      { max_generations: 1.1 }, { population_size: 4 }, { population_size: 65 }, { max_generations: 8, population_size: 64 }]) {
    assert.throws(() => controls.planArguments({ ...fields(), ...patch }, planContext()));
  }
  for (const seed of [0, 2 ** 32 - 1]) {
    assert.equal(controls.planArguments({ ...fields(), seed, max_generations: 7, population_size: 64 }, planContext()).seed, seed);
  }
});

test("non-JSON, prototype fields, sparse arrays and getters cannot become source or plan authority", () => {
  let reads = 0; const advertised = discovery();
  Object.defineProperty(advertised, "template_revision", { enumerable: true, get() { reads++; return hash("5"); } });
  assert.throws(() => controls.validateDiscovery(advertised, selected())); assert.equal(reads, 0);
  const cases = [
    value => { value.constraints = new Array(1); }, value => { value.objective.metric = undefined; },
    value => { value.cycle = value; }, value => { value.callback = () => 1; }, value => { value[Symbol("hidden")] = 1; },
    value => { Object.defineProperty(value, "extra", { value: 1 }); }
  ];
  for (const mutate of cases) { const input = fields(); mutate(input); assert.throws(() => controls.planArguments(input, planContext())); }
  const injected = JSON.parse(JSON.stringify(fields()).slice(0, -1) + ',"__proto__":{"release":"PASS"}}');
  assert.throws(() => controls.planArguments(injected, planContext()));
});

test("saved fixed plans reopen the original template instead of using CAD-rebind or current raw settings", () => {
  const saved = frozen(plan()), before = JSON.stringify(saved);
  assert.strictEqual(controls.frozenPlan(saved), saved.fixed_cad);
  assert.equal(saved.fixed_cad.record.request.declaration.loads[0].components.FZ, -250);
  assert.equal(JSON.stringify(saved), before);
  rejectChanges(plan, [
    value => { value.route = "model_analysis"; }, value => { value.study_id = "S-other"; },
    value => { value.fixed_cad.rebind_policy = "REVISION_REBIND_EXACT_SELECTIONS"; },
    value => { value.fixed_cad.record.source.cad_revision = hash("0"); },
    value => { value.fixed_cad.reference.record_sha256 = "unknown"; }
  ], value => controls.frozenPlan(value));
});

test("browser modules preserve legacy seven campaign exports and dispatch fixed templates only through the loaded helper", () => {
  const browser = { window: {} }; vm.createContext(browser);
  vm.runInContext(campaignText, browser);
  const serialized = JSON.stringify(plan());
  assert.throws(() => vm.runInContext(`window.campaignControls.conditionTemplate(${serialized})`, browser), /로드/);
  vm.runInContext(sourceText, browser);
  const read = vm.runInContext(`window.campaignControls.conditionTemplate(${serialized})`, browser);
  assert.equal(read.conditions_id, "C0-native"); assert.equal(read.rebind_policy, "FIXED_CAD_NO_REBIND");
  assert.deepEqual(Object.keys(browser.window.campaignControls).sort(), Object.keys(campaigns).sort());
  assert.deepEqual(Object.keys(browser.window.fixedCadCampaignControls).sort(), Object.keys(controls).sort());
  // CommonJS never fabricates a context from an absent browser-global helper.
  const previous = globalThis.fixedCadCampaignControls;
  try { delete globalThis.fixedCadCampaignControls; assert.throws(() => campaigns.conditionTemplate(plan()), /로드/); }
  finally { if (previous !== undefined) globalThis.fixedCadCampaignControls = previous; }
});

class Element {
  constructor(document, tag = "input") { this.ownerDocument = document; this.tagName = tag; this.children = []; this.value = ""; this.textContent = ""; }
  replaceChildren(...children) { this.children = children; this.value = children[0]?.value ?? ""; }
  set innerHTML(_) { throw new Error("Untrusted labels must use text content"); }
}
function elements() {
  const document = { createElement: tag => new Element(document, tag) };
  return { input: new Element(document, "select"), parameterId: new Element(document), displayName: new Element(document), lower: new Element(document),
    upper: new Element(document), summary: new Element(document, "div") };
}

test("human input selection displays real advertised signed values/units and creates a usable range registration", () => {
  const form = elements(), advertised = discovery(), value = selected();
  controls.populateInputs(advertised, value, form);
  assert.equal(form.input.children.length, 4); assert.equal(form.input.children[3].value, "load_L1_FZ");
  assert.match(form.input.children[3].textContent, /-250 N/); assert.match(form.input.children[3].textContent, /<signed>/);
  form.input.value = "load_L1_FZ";
  controls.selectInput(form.input.value, advertised, value, form);
  assert.equal(form.parameterId.value, "load_L1_FZ"); assert.equal(form.upper.value, "2500");
  assert.match(form.summary.textContent, /-2500 … 2500 N/);
  form.parameterId.value = "research_FZ"; form.displayName.value = "명시 FZ 합력"; form.lower.value = "-5e2"; form.upper.value = "-150";
  const request = controls.registerArguments(controls.readRegistration(form), advertised, value);
  assert.deepEqual(request, { study_id: "S-research", conditions_id: "C0-native", input_id: "load_L1_FZ", parameter_id: "research_FZ",
    display_name: "명시 FZ 합력", lower: -500, upper: -150, mode: "free" });
});

test("discovery refresh preserves range/name drafts and refuses stale input selection without overwriting them", () => {
  const form = elements(); form.input.value = "load_L1_FZ";
  form.parameterId.value = "custom_ID"; form.displayName.value = "사용자 초안"; form.lower.value = "-400"; form.upper.value = "-100";
  controls.populateInputs(discovery(), selected(), form);
  assert.equal(form.input.value, "load_L1_FZ"); assert.equal(form.displayName.value, "사용자 초안"); assert.equal(form.lower.value, "-400");
  const before = JSON.stringify([form.parameterId.value, form.displayName.value, form.lower.value, form.upper.value]);
  assert.throws(() => controls.selectInput("no_longer_advertised", discovery(), selected(), form));
  assert.equal(JSON.stringify([form.parameterId.value, form.displayName.value, form.lower.value, form.upper.value]), before);
  const other = discovery(); other.conditions_revision = hash("0");
  assert.throws(() => controls.populateInputs(other, selected(), form));
  assert.equal(form.input.value, "load_L1_FZ");
});

test("human decimal bounds do not coerce blanks, hexadecimal or unit text and preserve signed zero", () => {
  const form = elements(); form.input.value = "load_L1_FZ"; form.parameterId.value = "force"; form.displayName.value = "명시 힘"; form.upper.value = "1";
  for (const value of ["", " ", "0x20", "Infinity", "NaN", "2 N", "1e999"]) { form.lower.value = value; assert.throws(() => controls.readRegistration(form)); }
  form.lower.value = "-0"; assert.equal(Object.is(controls.readRegistration(form).lower, -0), true);
});

test("late success and late error are both withdrawn on store/C0 changes while user ranges remain", async () => {
  const pinned = selected(), originalContext = current(), key = controls.contextKey(pinned), form = elements();
  form.lower.value = "-400"; form.upper.value = "-100";
  let resolve, reject, active = clone(originalContext), request = 1, accepted = 0, errors = 0;
  const isCurrent = token => token === request && controls.sameContext(pinned, active) && controls.contextKey(pinned) === key;
  const success = new Promise(done => { resolve = done; }).then(reply => { if (isCurrent(1)) { controls.populateInputs(reply, pinned, form); accepted++; } });
  active.store = "reference"; request++; resolve(discovery()); await success;
  assert.equal(accepted, 0); assert.equal(form.input.children.length, 0); assert.equal(form.lower.value, "-400");
  active = clone(originalContext); request = 3;
  const failure = new Promise((_, fail) => { reject = fail; }).catch(() => { if (isCurrent(3)) errors++; });
  active.conditionsRevision = hash("0"); reject(new Error("old request")); await failure;
  assert.equal(errors, 0); assert.equal(form.upper.value, "-100");
});

test("actual HTML retains old targets, named human registration controls and existing campaign/result hooks", () => {
  for (const value of ["cad", "analysis_conditions", "model"]) assert.match(html, new RegExp(`<option value="${value}">`));
  for (const identifier of ["fixedCadConditionsArea", "fixedCadUseConditionsBtn", "fixedCadDiscoverBtn", "fixedCadConditionsSummary", "fixedCadConditionsError",
      "fixedCadRegisterForm", "fixedCadInputId", "fixedCadInputSummary", "fixedCadParameterId", "fixedCadParameterName", "fixedCadParameterLower", "fixedCadParameterUpper", "fixedCadRegisterBtn",
      "campaignForm", "campaignVariables", "campaignPlanBtn", "campaignDetail", "campaignSavedConditions", "modelRegisterForm", "experimentDetail"]) {
    assert.equal([...html.matchAll(new RegExp(`id="${identifier}"`, "g"))].length, 1, identifier);
  }
  assert(html.indexOf('/static/fixed-cad-campaign-controls.js') < html.indexOf('/static/campaign-controls.js'));
  assert(html.indexOf('/static/fixed-cad-campaign-controls.js') < html.indexOf('/static/app.js'));
  assert.match(html, /id="fixedCadRegisterForm"[^>]*><fieldset data-write>/);
  assert.match(html, /id="fixedCadDiscoverBtn"[^>]*data-operation="condition_parameters_discover"[^>]*disabled/);
  assert.match(html, /id="fixedCadRegisterBtn"[^>]*data-operation="condition_parameters_register"[^>]*disabled/);
});
