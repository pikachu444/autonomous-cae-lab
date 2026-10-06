"use strict";
// TEST_ONLY envelopes; no native execution or engineering/measurement proof.
const { test } = require("node:test"), assert = require("node:assert/strict");
const controls = require("../apps/lab/static/history-controls.js");
const { draft } = require("../apps/lab/static/comparison-research.js");
const hash = c => c.repeat(64);
function fixture() {
  const channel = { id: "radioss-center-vz", label: "TEST_ONLY signed half-step velocity", metric: null,
    quantity: "velocity", component: "Z", measure: "raw leapfrog velocity", coordinate_frame: "global Cartesian SI; sensor/world alignment UNKNOWN",
    location: "main node 9", unit: "m/s", axis: { quantity: "time", unit: "s", values: [0, .00005, .00015], semantics: "NATIVE_HALF_STEP_VELOCITY_TIME" },
    values: [0, -.00049, -.00147], initial_state: { index: 0, kind: "NATIVE_DECLARED_INITIAL_STATE" },
    origin: { kind: "NATIVE", driver: "openradioss", artifact: "simulation/parsed_history.json", sha256: hash("a"),
      native_artifact: "simulation/dropT01", native_sha256: hash("c"), native_field: "velocity_m_s", mapping: "EXACT_RETAINED_TH40_SAMPLE" } };
  const inspection = { integrity: "VERIFIED", result: { experiment_id: "E-native", study: { id: "S-native" }, status: "COMPLETED_REVIEW_REQUIRED",
    provenance: { adapter: "explicit.openradioss", adapter_version: "1.1" }, metrics: {},
    artifacts: [{ path: channel.origin.artifact, sha256: hash("a") }, { path: channel.origin.native_artifact, sha256: hash("c") }] },
    proposal: { id: "E-native", study_id: "S-native", physics: { backend: "explicit.openradioss" } }, study: { id: "S-native" }, hashes: { result_sha256: hash("b") } };
  const envelope = { integrity: "VERIFIED", experiment_id: "E-native", study_id: "S-native", result_sha256: hash("b"), channels: [channel] };
  return { channel, inspection, envelope };
}
function fields() { return { comparisonId: "O-native", purpose: "GENERAL_CAE_RESEARCH", hypothesis: "TEST_ONLY half-step axis comparison",
  name: "TEST_ONLY velocity", value: "-.00049", tolerance: "0", sourceKind: "SYNTHETIC", source: "TEST_ONLY",
  quantity: "velocity", component: "Z", location: "main node 9", coordinateFrame: "global Cartesian SI; sensor/world alignment UNKNOWN",
  condition: "TEST_ONLY reduced rigid case", channelId: "radioss-center-vz", sampleIndex: "1", axisQuantity: "time", axisUnit: "s", axisValue: ".00005", conditions: [] }; }
test("common history choices retain original half-step clocks and signed SI values without an invented producer metric", () => {
  const { inspection, envelope } = fixture(), before = structuredClone({ inspection, envelope });
  assert.equal(controls.channels(inspection, envelope).length, 1);
  const choice = controls.sampleChoice(inspection, envelope, "radioss-center-vz", 1);
  assert.equal(choice.value, -.00049); assert.deepEqual(choice.axis, { quantity: "time", unit: "s", value: .00005 });
  const payload = controls.build(inspection, envelope, fields());
  assert.equal(payload.observation.unit, "m/s"); assert.equal(payload.observation.axis.value, .00005);
  assert.deepEqual(payload.response, { history_channel: "radioss-center-vz", sample_index: 1 });
  assert.deepEqual({ inspection, envelope }, before); assert.deepEqual(inspection.result.metrics, {});
  assert.doesNotMatch(controls.sampleChoice(inspection, envelope, "radioss-center-vz", 0).label, /재료 적분/);
});
test("native time mapping, raw-source identity, physical quantity and SI symbols must match the family declaration", () => {
  for (const mutate of [
    d => { d.channel.axis.semantics = "NATIVE_CURRENT_TIME"; }, d => { d.channel.unit = "mm/s"; },
    d => { d.channel.origin.native_field = "z_m"; }, d => { d.channel.quantity = "force"; },
    d => { d.channel.origin.native_sha256 = hash("d"); }, d => { d.channel.metric = "max_displacement"; },
    d => { d.inspection.result.provenance.adapter = "UNKNOWN"; }, d => { d.channel.origin.kind = "REFERENCE"; },
    d => { d.channel.axis.values[1] = 0; }, d => { d.channel.values[1] = Infinity; },
  ]) { const d = fixture(); mutate(d); assert.deepEqual(controls.channels(d.inspection, d.envelope), []); }
});
function row() {
  const { inspection, envelope, channel } = fixture(), request = controls.build(inspection, envelope, fields());
  const axis = request.observation.axis;
  return { integrity: "VERIFIED", record: { schema_version: "1.3", id: "O-native", request,
    source: { experiment_id: "E-native", study_id: "S-native", backend: "explicit.openradioss", result_sha256: hash("b"), proposal_sha256: hash("d"), thread_sha256: hash("e") },
    comparison: { status: "NUMERIC_DIFFERENCE_ONLY", response_value: -.00049, observed_value: -.00049, unit: "m/s",
      difference: 0, absolute_difference: 0, declared_absolute_tolerance: 0, within_declared_tolerance: true,
      declared_condition_checks: [], condition_bindings_supplied: false, scope_alignment: "USER_DECLARED_UNVERIFIED",
      selection_kind: "EXACT_RECORDED_HISTORY_SAMPLE", physical_validation: "UNKNOWN", decision: "NOT_RELEASED", causal_verdict: "NOT_EVALUATED",
      source_channel: channel, response_axis: axis, declared_axis_check: { declared: axis, actual: axis, matched: true },
      declared_history_checks: ["quantity", "component", "coordinate_frame"].map(k => ({ property: k, declared: request.observation[k], actual: channel[k], matched: true })) } } };
}
test("the research question uses the saved native comparison and cannot borrow a terminal scalar metric", () => {
  const data = row(), question = draft([data], "S-native").question;
  assert.match(question, /O-native/); assert.match(question, /E-native/);
  for (const mutate of [d => { d.record.comparison.source_metric = { value: 0, unit: "m/s", valid: true }; },
    d => { d.record.source.backend = "material.mfront.viscoelastic"; }, d => { d.record.comparison.declared_history_checks[0].actual = "position"; }]) {
    const damaged = row(); mutate(damaged); assert.throws(() => draft([damaged], "S-native"));
  }
});
test("a mismatched reported time keeps the actual half-step sample and null verdict for AI interpretation", () => {
  const data = row(), c = data.record.comparison;
  data.record.request.observation.axis = { quantity: "time", unit: "s", value: .0001 };
  c.status = "DECLARED_AXIS_MISMATCH"; c.difference = c.absolute_difference = c.within_declared_tolerance = null;
  c.declared_axis_check = { declared: data.record.request.observation.axis, actual: c.response_axis, matched: false };
  assert.doesNotThrow(() => draft([data], "S-native"));
  c.status = "NUMERIC_DIFFERENCE_ONLY"; assert.throws(() => draft([data], "S-native"));
});
