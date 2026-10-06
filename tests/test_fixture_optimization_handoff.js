"use strict";

// Real Lab draft functions with synthetic DOM only: no provider/native/HTTP calls.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const vm = require("node:vm");
const source = readFileSync(require.resolve("../apps/lab/static/app.js"), "utf8");
const helper = readFileSync(require.resolve("../apps/lab/static/campaign-controls.js"), "utf8");
const boundary = source.indexOf('$("jobCancelBtn").addEventListener("click", async () => {');
assert(boundary > 0);
function harness() {
  const ids = new Map();
  const $ = id => { if (!ids.has(id)) ids.set(id, { value: "", hidden: false, textContent: "", dataset:{},
    listeners: {}, addEventListener(type, callback) { this.listeners[type] = callback; },
    querySelector: () => ({}), querySelectorAll: () => [{value:"cad"},{value:"analysis"},{value:"model"}] }); return ids.get(id); };
  const context = { window: {}, document: { getElementById: $ }, TextEncoder, URL, URLSearchParams, Intl };
  vm.createContext(context); vm.runInContext(helper, context);
  // This harness tests draft preservation; the real constraint DOM is exercised
  // through the browser acceptance and the shared field-parser controls.
  vm.runInContext(source.slice(0, boundary) + "\ncampaignMode = () => {}; renderCampaignVariables = () => {}; renderConstraintEditor = () => {}; writable = () => true; busy = () => false; globalThis.ui = { state, applyFixtureCampaignDefaults, campaignTargetChanged, syncConstraintEditor, prepareFixedCad };", context);
  vm.runInContext(source.split("\n").filter(line => line.startsWith('$("optimizationConstraints").addEventListener("input"') || line.startsWith('$("optimizationRequired").addEventListener("input"')).join("\n"), context);
  const addStart = source.indexOf('$("optimizationAddConstraint").addEventListener("click"');
  const addEnd = source.indexOf('$("optimizationRequired").addEventListener("input"', addStart);
  assert(addStart > boundary && addEnd > addStart); vm.runInContext(source.slice(addStart, addEnd), context);
  $("campaignTarget").value = "cad"; $("campaignAnalysis").value = "structural_linear";
  $("optimizationConstraints").value = "[]"; $("optimizationRequired").value = '{"cad":[],"analysis":[]}';
  const setMesh = mesh => { $("campaignAnalysisSettings").value = JSON.stringify({mesh, load:{force_per_support_N:150}, material:{qualification:"UNKNOWN"}}); };
  return { $, setMesh, ui: context.ui, context, apply: () => context.ui.applyFixtureCampaignDefaults() };
}

for (const failure of ['source', 'verified-model-pairing']) test(`fixed CAD ${failure} refusal is visible on the invoking simulation screen`, async () => {
  const h = harness(); h.$('campaignTarget').value = 'analysis_conditions';
  h.context.failureAtSource = failure === 'source';
  vm.runInContext(`
    campaignConditionSource = () => { if (failureAtSource) throw new Error('Source not ready'); return {source:{experiment_id:'E-parent'}}; };
    fixedCadSignature = () => 'frozen-context'; activeStore = () => 'local'; updateControls = () => {};
    api = async () => ({integrity:'VERIFIED'});
    window.fixedCadCampaignControls = { selection: () => { throw new Error('Verified model does not pair'); } };
    analysisConditionsError = message => { $('analysisConditionsError').textContent = message; $('analysisConditionsError').hidden = !message; };
    notify = message => { $('notice').textContent = message; };
  `, h.context);
  await h.ui.prepareFixedCad(true);
  const expected = failure === 'source' ? 'Source not ready' : 'Verified model does not pair';
  assert.equal(h.$('analysisConditionsError').hidden, false);
  assert.equal(h.$('analysisConditionsError').textContent, expected);
  assert.equal(h.$('fixedCadConditionsError').textContent, expected);
  assert.equal(h.$('notice').textContent, expected);
  assert.equal(h.ui.state.fixedCad.loading, false);
});

for (const target of ["model", "analysis_conditions"]) test(`${target} structured add/edit cannot freeze an untouched CAD automatic guide`, () => {
  const h = harness(); h.setMesh({max_sizes_mm:[4,3]}); h.apply();
  assert.equal(JSON.parse(h.$("optimizationConstraints").value)[0].limit, 0.0065);
  h.$("campaignTarget").value = target; h.ui.campaignTargetChanged();
  h.$("objectiveSource").value = target === "model" ? "model" : "analysis";
  h.$("objectiveMetric").value = "test_response"; h.$("objectiveUnit").value = "mm";
  h.$("optimizationAddConstraint").listeners.click();
  assert.equal(h.ui.state.fixtureCampaignEdited.constraints, false);
  h.$("optimizationConstraintRows").querySelectorAll = () => [{querySelectorAll: () =>
    Object.entries({source: target === "model" ? "model" : "analysis", metric:"test_response", unit:"mm", operator:"<=", limit:"2", scale:"1"})
      .map(([key, value]) => ({dataset:{constraintField:key}, value}))}];
  h.ui.syncConstraintEditor();
  assert.equal(h.ui.state.fixtureCampaignEdited.constraints, false);
  h.$("campaignTarget").value = "cad"; h.ui.campaignTargetChanged();
  h.setMesh({mode:"selected",max_sizes_mm:[4]}); h.apply();
  assert.deepEqual(JSON.parse(h.$("optimizationConstraints").value), []);
});
test("selected settings reach the actual Lab draft without a trend or physical limit", () => {
  const h = harness(); h.setMesh({mode:"selected",max_sizes_mm:[4]}); h.apply();
  assert.deepEqual(JSON.parse(h.$("optimizationConstraints").value), []);
  assert.deepEqual(JSON.parse(h.$("optimizationRequired").value), {cad:[],analysis:["mesh_0_reaction_balance"]});
  assert.match(h.$("fixtureCampaignNote").textContent, /하중 안장.*\|UZ\|/);
  assert.match(h.$("fixtureCampaignNote").textContent, /자동으로 설정하지 않습니다/);
});
test("switching automatic legacy defaults to selected removes only the old generated screen", () => {
  const h = harness(); h.setMesh({max_sizes_mm:[4,3]}); h.apply();
  assert.equal(JSON.parse(h.$("optimizationConstraints").value)[0].limit, 0.0065);
  assert.match(h.$("fixtureCampaignNote").textContent, /과거 가상 비교용/);
  h.setMesh({mode:"selected",max_sizes_mm:[4]}); h.apply();
  assert.equal(h.$("optimizationConstraints").value, "[]");
  assert.deepEqual(JSON.parse(h.$("optimizationRequired").value).analysis, ["mesh_0_reaction_balance"]);
});
test("explicit user constraints, CAD requirements and manually empty constraints survive", () => {
  const h = harness(); h.$("optimizationRequired").value = '{"cad":["cad_screen"],"analysis":[]}';
  h.setMesh({mode:"selected",max_sizes_mm:[4]}); h.apply();
  assert.deepEqual(JSON.parse(h.$("optimizationRequired").value).cad, ["cad_screen"]);
  const custom = '[{"source":"analysis","metric":"max_displacement","unit":"mm","operator":"<=","limit":0.01,"scale":0.01}]';
  h.$("optimizationConstraints").value = custom; h.ui.state.fixtureCampaignEdited.constraints = true;
  h.$("optimizationRequired").value = '{"cad":["cad_screen"],"analysis":["custom_check"]}';
  h.ui.state.fixtureCampaignEdited.requirements = true;
  h.setMesh({max_sizes_mm:[4,3]}); h.apply();
  assert.equal(h.$("optimizationConstraints").value, custom);
  assert.deepEqual(JSON.parse(h.$("optimizationRequired").value).analysis, ["custom_check"]);
  h.$("optimizationConstraints").value = "[]"; h.apply();
  assert.equal(h.$("optimizationConstraints").value, "[]");
});
test("malformed current settings refuse without adopting a preset or changing editable fields", () => {
  const h = harness(); h.setMesh({mode:"selected",max_sizes_mm:[4]}); h.apply();
  const before = [h.$("optimizationConstraints").value, h.$("optimizationRequired").value];
  h.ui.state.presets.structural_linear = {settings:{mesh:{max_sizes_mm:[4,3]}}};
  for (const settings of ['{', JSON.stringify({mesh:{mode:"selected",max_sizes_mm:[4,3]}})]) {
    h.$("campaignAnalysisSettings").value = settings; assert.throws(h.apply);
    assert.deepEqual([h.$("optimizationConstraints").value,h.$("optimizationRequired").value], before);
  }
});
test("actual target switching isolates model edits from the CAD generated defaults", () => {
  const h = harness(); h.setMesh({max_sizes_mm:[4,3]}); h.apply();
  h.$("campaignTarget").value = "model"; h.ui.campaignTargetChanged();
  assert.equal(h.$("fixtureCampaignNote").hidden, true);
  h.$("optimizationConstraints").value = '[{"source":"model"}]';
  h.$("optimizationConstraints").listeners.input();
  h.$("optimizationRequired").value = '{"model":["declared_model_check"]}';
  h.$("optimizationRequired").listeners.input();
  h.$("campaignTarget").value = "cad"; h.ui.campaignTargetChanged();
  h.setMesh({mode:"selected",max_sizes_mm:[4]}); h.apply();
  assert.equal(h.$("optimizationConstraints").value, "[]");
  assert.deepEqual(JSON.parse(h.$("optimizationRequired").value).analysis, ["mesh_0_reaction_balance"]);
  assert.equal(h.$("fixtureCampaignNote").hidden, false);
  h.$("campaignTarget").value = "model"; h.ui.campaignTargetChanged();
  assert.equal(h.$("optimizationConstraints").value, '[{"source":"model"}]');
  assert.deepEqual(JSON.parse(h.$("optimizationRequired").value), {model:["declared_model_check"]});
});
test("disabling analysis clears only generated values and preserves declared user input", () => {
  const h = harness(); h.setMesh({max_sizes_mm:[4,3]}); h.apply();
  h.$("campaignAnalysis").value = ""; h.apply();
  assert.equal(h.$("optimizationConstraints").value, "[]");
  assert.deepEqual(JSON.parse(h.$("optimizationRequired").value), {cad:[],analysis:[]});
  assert.equal(h.$("fixtureCampaignNote").hidden, true);
  h.$("optimizationConstraints").value = '[{"declared":true}]';
  h.ui.state.fixtureCampaignEdited.constraints = true; h.apply();
  assert.equal(h.$("optimizationConstraints").value, '[{"declared":true}]');
});
