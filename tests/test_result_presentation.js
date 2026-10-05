"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const presentation = require("../apps/lab/static/result-presentation.js");

test("displayed inputs use the captured mapping, not a guessed parameter ID or current registry", () => {
  const record = { result: { input_parameters: { "P-width": 80, "P-custom": 10, "P-unmapped": 4 } },
    registry_snapshot: { entries: [
      { parameter_id: "P-width", native: { path: "specimen.length" }, unit: "mm" },
      { parameter_id: "P-custom", display_name: "사용자가 정한 변수", unit: "N" },
    ] } };
  const before = JSON.stringify(record);
  assert.deepEqual(presentation.inputs(record), [
    { id: "P-width", name: "시편 길이", value: 80, unit: "mm" },
    { id: "P-custom", name: "사용자가 정한 변수", value: 10, unit: "N" },
    { id: "P-unmapped", name: "입력 3", value: 4, unit: null },
  ]);
  assert.equal(JSON.stringify(record), before);
});

test("inspection counts preserve failed, unknown, warning and unrecognized checks without promoting release", () => {
  const result = { status: "COMPLETED_REVIEW_REQUIRED", decision: "NOT_RELEASED", solver_status: "NOT_RUN",
    metrics: { displacement: { value: -0, unit: "mm", valid: false } },
    validations: [{ type: "static_strength", status: "UNKNOWN", blocking: true },
      { type: "mesh", status: "FAIL" }, { status: "PASS" }, { status: "WARNING" }, { status: "NEW_CODE" }] };
  const before = JSON.stringify(result), report = presentation.checks(result);
  assert.deepEqual(report.counts, { PASS: 1, FAIL: 1, UNKNOWN: 1, WARNING: 1, other: 1 });
  assert.equal(report.total, 5); assert.equal(report.unresolved.length, 4);
  assert.deepEqual(report.unresolved.map(item => item.status), ["UNKNOWN", "FAIL", "WARNING", "NEW_CODE"]);
  assert.equal(result.decision, "NOT_RELEASED"); assert.equal(result.metrics.displacement.valid, false);
  assert(Object.is(result.metrics.displacement.value, -0)); assert.equal(JSON.stringify(result), before);
});

test("friendly face captions retain original face identity without treating display IDs as native IDs", () => {
  const face = { component_id: "printed_support_right", type: "PLANE", id: 98,
    catalog_face_id: "printed_support_right:face:7:" + "c".repeat(64) };
  const before = JSON.stringify(face);
  assert.equal(presentation.faceDescription(face), "오른쪽 받침 · 평면 · 원본 면 7");
  assert.equal(presentation.faceDescription({ id: 98, type: "PLANE" }), "선택한 부품 · 평면");
  assert.equal(JSON.stringify(face), before);
  assert(!presentation.faceDescription(face).includes("98"));
});

test("unknown names and prototype properties have neutral display labels", () => {
  assert.equal(presentation.title("__proto__"), "해석·모델 실험");
  assert.equal(presentation.validationName("new_physics", 2), "확인 항목 3");
  assert.equal(presentation.metricName("new_response", 1), "결과값 2");
  assert.equal(presentation.title("fixture.assembly"), "굽힘 시험 치구");
});

// UNSOLVED display fixtures: no native/physical qualification is represented.
const cadControls = require("../apps/lab/static/cad-controls.js");
const supportPreset = { operation: "analysis_run", parent_backends: ["fixture.cadquery"] };
function frozen(value) {
  if (value && typeof value === "object") { Object.values(value).forEach(frozen); Object.freeze(value); }
  return value;
}
function cad(backend = "fixture.cadquery") {
  return { experiment_id: "E-display-only", status: "COMPLETED_REVIEW_REQUIRED", solver_status: "NOT_RUN",
    decision: "NOT_RELEASED", cad_revision: "a".repeat(64), backend,
    metrics: { diagnostic: { value: -0, unit: "mm", valid: false } }, validations: [{ status: "UNKNOWN", blocking: true }] };
}
function context(record, changes = {}) {
  return { integrity: "VERIFIED", writable: true, busy: false, analysisAvailable: true,
    eligibleParent: cadControls.eligibleParent(supportPreset, record), ...changes };
}
function completed(operation, result) { return { status: "COMPLETED", operation, result }; }
function candidate() { return { native: { backend: "fixture.cadquery", document: "support.py", object: "model", path: "width" } }; }

test("CAD-only assembly completion declares analysis absent and the actual public connection block", () => {
  const record = frozen(cad("fixture.assembly")), before = JSON.stringify(record);
  const report = presentation.workflow(record, context(record));
  assert.equal(report.stage, "모델 준비됨 · 해석 안 함");
  assert.match(report.next, /형상과 입력/); assert.match(report.next, /해석 기능은 아직 준비되지 않았습니다/);
  assert.doesNotMatch(report.next, /새 실험을 실행|다른 솔버|연구 완료/);
  assert.equal(JSON.stringify(record), before); assert(Object.is(record.metrics.diagnostic.value, -0));
});

test("analysis guidance uses declared parent compatibility plus integrity, writer, busy and availability context", () => {
  const record = frozen(cad());
  assert.match(presentation.workflow(record, context(record)).next, /재료·하중·메시.*새 실험을 실행/);
  assert.match(presentation.workflow(record, context(record, { integrity: "NOT_CHECKED" })).next, /기록·원본 일치를 먼저/);
  assert.match(presentation.workflow(record, context(record, { writable: false })).next, /읽기 전용.*작업 저장소/);
  assert.match(presentation.workflow(record, context(record, { busy: true })).next, /종료를 먼저 확인/);
  assert.match(presentation.workflow(record, context(record, { analysisAvailable: false })).next, /현재 실행할 수 없습니다/);
  assert.match(presentation.workflow(record, context(record, { eligibleParent: false })).next, /호환되는 부모 모델/);
  assert.equal(presentation.workflow(record, context(record, { stale: true })).stage, "기록의 재확인 필요");
  assert.equal(cadControls.eligibleParent(supportPreset, { ...record, cad_revision: "" }), false);
});

test("solver execution preserves recorded qualification uncertainty, invalid responses and release verdict", () => {
  for (const converged of [undefined, false, true]) {
    const record = frozen({ ...cad(), solver_status: "COMPLETED", decision: "UNKNOWN", converged });
    const before = JSON.stringify(record), report = presentation.workflow(record, context(record));
    assert.equal(report.stage, "해석 실행됨 · 결과 검토 필요"); assert.equal(report.tone, "review");
    assert.match(report.next, /검사 근거·남은 확인 사항/); assert.match(report.next, /승인을 확정할 수 없습니다/);
    if (converged === undefined) assert.match(report.next, /수치 자격은 미확인/);
    if (converged === false) assert.match(report.next, /수치 자격이 미충족으로 기록/);
    assert.equal(record.decision, "UNKNOWN"); assert.equal(record.metrics.diagnostic.valid, false);
    assert(Object.is(record.metrics.diagnostic.value, -0)); assert.equal(JSON.stringify(record), before);
  }
});

test("service COMPLETED cannot override rejected, failed or failed-execution Core observations", () => {
  for (const status of ["REJECTED", "FAILED", "FAILED_EXECUTION", "NO_FEASIBLE_DESIGN"]) {
    const result = frozen({ ...cad(), status, solver_status: "COMPLETED" });
    const job = frozen(completed("cad_run", result)), before = JSON.stringify(job);
    const report = presentation.workflow(job, { kind: "job", ...context(result) });
    assert.equal(report.tone, "failed"); assert.doesNotMatch(report.stage, /모델 준비|연구 완료/);
    assert.equal(job.status, "COMPLETED"); assert.equal(result.status, status); assert.equal(JSON.stringify(job), before);
  }
  assert.equal(presentation.workflow(completed("analysis_run", { ...cad(), solver_status: "FAILED_EXECUTION" }), { kind: "job" }).tone, "failed");
});

test("missing, foreign and unrecognized payloads cannot claim a successful step", () => {
  for (const result of [undefined, null, {}, "done", [], { ...cad(), status: "NEW_STATUS" },
    { ...cad(), solver_status: "NEW_SOLVER_STATUS" }, { ...cad(), experiment_id: "" }]) {
    assert.equal(presentation.workflow(completed("cad_run", result), { kind: "job" }).stage, "현재 단계 미확인");
  }
  assert.equal(presentation.workflow(completed("__proto__", cad()), { kind: "job" }).stage, "현재 단계 미확인");
  assert.equal(presentation.workflow(Object.create(cad())).stage, "현재 단계 미확인");
  assert.equal(presentation.workflow({ ...cad(), backend: "__proto__" }).stage, "해석 안 함");
  assert.equal(presentation.workflow({ ...cad(), cad_revision: "" }).stage, "해석 안 함");
});

test("metadata and plan jobs describe their actual persisted step without promoting research completion", () => {
  const cases = [
    ["study_create", { id: "S-display", research_question: "질문", hypothesis: "가설", objective: "목표" }, "연구 질문 저장됨"],
    ["parameter_discover", [candidate()], "변수 목록 확인됨"],
    ["model_parameters_discover", [], "발견된 변수 없음"],
    ["parameter_register", { parameter_id: "P-width", ...candidate() }, "연구 변수 등록됨"],
    ["model_parameters_register", { parameter_id: "P-E", ...candidate() }, "연구 변수 등록됨"],
    ["registry_refresh", { revision: 2, entries: [] }, "CAD 등록부 갱신됨"],
    ["doe_plan", { campaign_id: "C-display", status: "PLANNED" }, "수치 탐색 계획 저장됨"],
    ["optimization_plan", { campaign_id: "C-display", status: "PLANNED" }, "수치 탐색 계획 저장됨"],
    ["model_optimization_plan", { campaign_id: "C-display", status: "PLANNED" }, "수치 탐색 계획 저장됨"],
    ["native_inspect", { design: "D-display", parameters: [], candidates: [], final_candidates: [] }, "네이티브 모델 조회됨"],
    ["native_create", { design: "D-display", parameters: [], candidates: [], final_candidates: [] }, "편집 모델 생성됨 · 해석 안 함"],
    ["native_final", { design: "D-display", parameters: [], candidates: [], final_candidates: [], final: "Body" }, "최종 솔리드 선택 저장됨"],
  ];
  for (const [operation, result, stage] of cases) {
    const job = frozen(completed(operation, result)), before = JSON.stringify(job);
    const report = presentation.workflow(job, { kind: "job" });
    assert.equal(report.stage, stage); assert.equal(report.tone, "recorded"); assert.equal(JSON.stringify(job), before);
    assert.doesNotMatch(report.stage, /연구 완료|해석 완료|승인/);
    assert.equal(presentation.workflow(completed(operation, {}), { kind: "job" }).stage, "현재 단계 미확인");
    if (!Array.isArray(result)) assert.equal(presentation.workflow(completed(operation, { ...result, status: "UNRECOGNIZED" }), { kind: "job" }).stage, "현재 단계 미확인");
  }
  assert.equal(presentation.workflow(completed("parameter_discover", [{}]), { kind: "job" }).stage, "현재 단계 미확인");
  assert.equal(presentation.workflow(completed("doe_plan", { campaign_id: "C-display", status: "FUTURE_STATE" }), { kind: "job" }).stage, "현재 단계 미확인");
});

test("candidate campaign completion asks for candidate review and never guarantees an optimum or release", () => {
  for (const operation of ["doe_run", "optimization_run"]) {
    const payload = { campaign_id: "C-display", status: "COMPLETED_REVIEW_REQUIRED", decision: "NOT_RELEASED",
      [operation === "doe_run" ? "samples" : "evaluations"]: [{ index: 1, cad_status: "REJECTED" }] };
    const report = presentation.workflow(completed(operation, frozen(payload)), { kind: "job" });
    assert.equal(report.stage, "후보 탐색 실행됨 · 결과 검토 필요");
    assert.match(report.next, /후보별 결과.*최적해 보증/); assert.equal(payload.decision, "NOT_RELEASED");
    assert.equal(presentation.workflow(completed(operation, { ...payload, [operation === "doe_run" ? "samples" : "evaluations"]: [] }), { kind: "job" }).stage, "현재 단계 미확인");
  }
});

test("owned lifecycle status overrides positive payloads and terminal unknown jobs stay uncertain", () => {
  for (const [status, caption, tone] of [["RUNNING", "작업 실행 중", "pending"], ["CANCEL_REQUESTED", "취소 처리 중", "pending"],
    ["CLEANUP_PENDING", "종료 확인 중 · 다음 작업 차단", "pending"], ["CANCELLED", "작업 취소됨", "unknown"], ["FAILED", "실행 실패 · 기록 확인 필요", "failed"]]) {
    const job = frozen({ ...completed("cad_run", cad()), status });
    const report = presentation.workflow(job, { kind: "job" }); assert.equal(report.stage, caption); assert.equal(report.tone, tone);
  }
  assert.equal(presentation.workflow({ ...completed("cad_run", cad()), cleanup_pending: true }, { kind: "job" }).stage, "종료 확인 중 · 다음 작업 차단");
  assert.equal(presentation.workflow({ status: "UNRECOGNIZED", result: cad() }, { kind: "job" }).stage, "현재 단계 미확인");
});

test("recovered jobs keep uncertain outcome ahead of old positive results and cleanup flags", () => {
  const job = frozen({ ...completed("cad_run", cad()), status: "RECOVERY_REQUIRED", cleanup_pending: true });
  const report = presentation.workflow(job, { kind: "job" });
  assert.equal(report.stage, "실행 상태 확인 필요 · 새 작업 차단");
  assert.equal(report.tone, "unknown");
  assert.match(report.next, /보존된 결과.*새 실행은 차단/);
  assert.equal(job.result.decision, "NOT_RELEASED");
});

test("retained fixture result labels preserve exact scalars, units, invalid diagnostic stress and UNKNOWN checks", () => {
  // Display-only projection of retained human-05 E-fea width32 result.json,
  // SHA256 6688f4bff821e6e3e3128bdb743f8ee6847c3678a5e0c47472eaf5709b28c098.
  // Source numerical/engineering qualification is not repeated by this test.
  const record = frozen({ experiment_id: "fea_width32_100N_432mm_20261005_a1", status: "COMPLETED_REVIEW_REQUIRED",
    solver_status: "COMPLETED", converged: true, decision: "NOT_RELEASED", metrics: {
      applied_force_per_support: { unit: "N", valid: true, value: 100 },
      displacement_mesh_change_ratio: { unit: "1", valid: true, value: 0.016636569979773187 },
      max_displacement: { unit: "mm", valid: true, value: 0.005827884 },
      peak_stress: { reason: "Averaged nodal diagnostic; no stress convergence or material allowable", unit: "MPa", valid: false, value: 0.5990678756165371 },
      reaction_balance_ratio: { unit: "1", valid: true, value: 9.377174045109376e-9 },
      reaction_force: { unit: "N", valid: true, value: [-6.981000019593144e-9, -3.778289999022619e-8, 100.0000001715396] },
    }, validations: [
      { type: "machine_interface", status: "UNKNOWN", blocking: true }, { type: "static_strength", status: "UNKNOWN", blocking: true },
      { type: "physical_load_test", status: "UNKNOWN", blocking: true }, { type: "fatigue_durability", status: "UNKNOWN", blocking: true },
      { type: "joint_and_contact", status: "UNKNOWN", blocking: true }, { type: "material_qualification", status: "UNKNOWN", blocking: true },
      { type: "stress_convergence", status: "UNKNOWN", blocking: true },
    ] });
  const before = JSON.stringify(record);
  const metricRows = Object.entries(record.metrics).map(([name, metric], index) => ({ name: presentation.metricName(name, index), metric }));
  assert.deepEqual(metricRows.map(row => row.name), ["지지대별 하중", "마지막 두 메시의 변위 변화율 (상대비)", "최대 변위",
    "절점 평균 응력 (진단용)", "반력 상대 불평형 (상대비)", "지지대 반력 (X, Y, Z)"]);
  metricRows.forEach((row, index) => assert.equal(row.metric, Object.values(record.metrics)[index]));
  assert.deepEqual(metricRows.map(row => row.metric.unit), ["N", "1", "mm", "MPa", "1", "N"]);
  assert.equal(metricRows[1].metric.value, 0.016636569979773187); assert.equal(metricRows[4].metric.value, 9.377174045109376e-9);
  assert.equal(metricRows[3].metric.valid, false); assert.equal(metricRows[3].metric.reason, record.metrics.peak_stress.reason);
  assert.deepEqual(metricRows[5].metric.value, [-6.981000019593144e-9, -3.778289999022619e-8, 100.0000001715396]);
  const unresolved = presentation.checks(record).unresolved;
  assert.deepEqual(unresolved.map((check, index) => presentation.validationName(check.type, index)), ["시험기 장착 조건", "정적 강도", "실물 하중 시험", "피로와 내구성", "체결·접촉", "재료 물성 검증", "응력 수렴"]);
  unresolved.forEach((check, index) => { assert.equal(check, record.validations[index]); assert.equal(check.status, "UNKNOWN"); assert.equal(check.blocking, true); });
  assert.equal(record.status, "COMPLETED_REVIEW_REQUIRED"); assert.equal(record.decision, "NOT_RELEASED"); assert.equal(JSON.stringify(record), before);
  assert.equal(presentation.metricName("__proto__", 4), "결과값 5"); assert.equal(presentation.validationName("constructor", 6), "확인 항목 7");
});

test("per-mesh response labels preserve paired numeric lists, units and invalid signed observation reason", () => {
  const result = frozen({ decision: "NOT_RELEASED", metrics: {
    mesh_size_max_mm: { value: [4, 3, 2], unit: "mm", valid: true },
    loaded_saddle_min_global_uz: { value: [-0.00564208, -0.005730928, -0.005827884], unit: "mm", valid: false,
      reason: "Declared mesh trend threshold exceeded" },
  }, validations: [{ type: "static_strength", status: "UNKNOWN", blocking: true }] });
  const before = JSON.stringify(result);
  const rows = Object.entries(result.metrics).map(([name, metric], index) => ({ name: presentation.metricName(name, index), metric }));
  assert.deepEqual(rows.map(row => row.name), ["메시별 최대 크기", "메시별 하중 안장 Z 변위 (최솟값)"]);
  assert.equal(rows[0].metric, result.metrics.mesh_size_max_mm); assert.equal(rows[1].metric, result.metrics.loaded_saddle_min_global_uz);
  assert.deepEqual(rows[0].metric, { value: [4, 3, 2], unit: "mm", valid: true });
  assert.deepEqual(rows[1].metric, { value: [-0.00564208, -0.005730928, -0.005827884], unit: "mm", valid: false,
    reason: "Declared mesh trend threshold exceeded" });
  assert.equal(presentation.checks(result).unresolved[0].status, "UNKNOWN"); assert.equal(result.decision, "NOT_RELEASED");
  assert.equal(JSON.stringify(result), before); assert.equal(presentation.metricName("unavailable_series", 7), "결과값 8");
});

test("fixture caption reports the named last-pair check, never a boolean proof of convergence", () => {
  for (const [status, caption] of [["PASS", "통과"], ["FAIL", "조건 미충족"], ["UNKNOWN", "미확인"], ["WARNING", "검토 필요"]]) {
    const record = frozen({ converged: true, decision: "NOT_RELEASED", provenance: { adapter: "fixture.calculix" },
      metrics: { peak_stress: { value: 0.5990678756165371, valid: false, unit: "MPa" } },
      validations: [{ type: "displacement_mesh_trend", validator: "fixture.calculix", status, threshold: .05 },
        ...["machine_interface", "static_strength", "physical_load_test", "fatigue_durability", "joint_and_contact", "material_qualification", "stress_convergence"]
          .map(type => ({ type, status: "UNKNOWN", blocking: true }))] });
    const before = JSON.stringify(record), shown = presentation.numericalCaption(record);
    assert.match(shown, /마지막 두 메시의 변위 변화 검사/); assert(shown.includes(caption)); assert.match(shown, /기준 상대비 ≤ 0\.05/);
    assert.match(shown, /점근 수렴을 입증한 것은 아닙니다/); assert.doesNotMatch(shown, /수치 수렴: 확인됨/);
    assert.equal(record.metrics.peak_stress.valid, false); assert.equal(record.decision, "NOT_RELEASED");
    assert.equal(record.validations.filter(item => item.blocking && item.status === "UNKNOWN").length, 7);
    assert.equal(JSON.stringify(record), before);
  }
  for (const record of [{ converged: true }, { converged: false }, {},
    { converged: true, provenance: { adapter: "other.backend" }, validations: [{ type: "displacement_mesh_trend", validator: "fixture.calculix", status: "PASS" }] },
    { converged: true, provenance: { adapter: "fixture.calculix" }, validations: [{ type: "displacement_mesh_trend", validator: "other.backend", status: "PASS" }] }]) {
    assert.match(presentation.numericalCaption(record), /기록된 수치 자격/); assert.doesNotMatch(presentation.numericalCaption(record), /수렴.*확인됨|마지막 두 메시/);
  }
  assert.equal(presentation.validationName("displacement_mesh_trend"), "마지막 두 메시의 변위 변화 검사");
  assert.equal(presentation.validationName("mesh_2_reaction_balance"), "메시 3의 X/Y/Z 반력 평형");
});

// UNSOLVED direct-parent fixtures. This tests verified-read presentation only;
// no HTTP server, scientific run, WebGL/browser layout or native field is used.
const { readFileSync } = require("node:fs");
const vm = require("node:vm");
const appSource = readFileSync(require.resolve("../apps/lab/static/app.js"), "utf8");
const bootBoundary = appSource.indexOf('$("jobCancelBtn").addEventListener("click", async () => {');
assert(bootBoundary > 0, "Test must stop before application boot/listeners");
const switchStart = appSource.indexOf("async function switchStore(");
const switchEnd = appSource.indexOf("\n// Exact Core keyword arguments", switchStart);
assert(switchStart > bootBoundary && switchEnd > switchStart, "Read the actual store switch definition without later listeners/boot");
const CAD_REVISION = "a".repeat(64);
function previewArtifact(kind = "surface", changes = {}) {
  return { path: kind === "surface" ? "cad/native/surface.json" : "cad/preview.png", revision: CAD_REVISION,
    mime_type: kind === "surface" ? "application/json" : "image/png", sha256: "b".repeat(64), size_bytes: 100, ...changes };
}
function previewRecord(parent = false, artifacts = []) {
  return { integrity: "VERIFIED", result: { experiment_id: parent ? "E-parent" : "E-analysis",
    parent_experiment_id: parent ? null : "E-parent", cad_revision: CAD_REVISION,
    status: "COMPLETED_REVIEW_REQUIRED", solver_status: parent ? "NOT_RUN" : "COMPLETED",
    provenance: { adapter: parent ? "fixture.cadquery" : "fixture.calculix" }, artifacts } };
}
test("parent preview admits only the exact verified direct CAD parent and same-revision manifested CAD artifact", () => {
  const child = frozen(previewRecord()), parent = frozen(previewRecord(true, [previewArtifact()]));
  const before = JSON.stringify([child, parent]);
  assert.deepEqual(presentation.parentCadPreview(child, parent), { experimentId: "E-parent", path: "cad/native/surface.json", kind: "surface", parent: true });
  assert.equal(presentation.parentCadPreview(child, previewRecord(true, [previewArtifact("image")])).kind, "image");
  assert.equal(JSON.stringify([child, parent]), before);
  const changed = changes => ({ ...parent, result: { ...parent.result, ...changes } });
  for (const invalid of [{ ...parent, integrity: "NOT_CHECKED" }, changed({ experiment_id: "E-unrelated" }), changed({ cad_revision: "c".repeat(64) }),
    changed({ parent_experiment_id: "E-analysis" }), changed({ parent_experiment_id: "E-parent" }), changed({ parent_experiment_id: "E-other-CAD" }),
    changed({ solver_status: "COMPLETED" }), changed({ status: "REJECTED" }), changed({ provenance: { adapter: "other.backend" } })]) {
    assert.throws(() => presentation.parentCadPreview(child, invalid));
  }
  for (const invalid of [{ ...child, integrity: "NOT_CHECKED" }, { ...child, result: { ...child.result, parent_experiment_id: "E-analysis" } },
    { ...child, result: { ...child.result, cad_revision: "" } }]) assert.throws(() => presentation.parentCadId(invalid));
  for (const unsafe of ["../E-parent", "E/parent", "E\\parent", "E-parent\n", "E-parent?store=other", "E-parent" + "x".repeat(80)]) {
    assert.equal(presentation.safeExperimentId(unsafe), false);
    assert.throws(() => presentation.parentCadId({ ...child, result: { ...child.result, parent_experiment_id: unsafe } }));
  }
  for (const changes of [{ revision: "c".repeat(64) }, { path: "cad/../surface.json" }, { path: "/cad/surface.json" },
    { path: "cad\\surface.json" }, { path: "cad/\u0000surface.json" }, { path: "simulation/surface.json" },
    { sha256: "not-a-digest" }, { size_bytes: -1 }, { mime_type: "text/html" }])
    assert.throws(() => presentation.parentCadPreview(child, previewRecord(true, [previewArtifact("surface", changes)])));
});

class PreviewNode {
  constructor(tag = "div") { this.tagName = tag.toUpperCase(); this.children = []; this.listeners = new Map(); this.attributes = {}; this.dataset = {}; this.className = ""; this._text = ""; this.isConnected = true; }
  set textContent(value) { this._text = String(value ?? ""); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
  set innerHTML(_value) { throw new Error("Untrusted preview must remain inert"); }
  append(...items) { items.forEach(child => { child.parentNode = this; this.children.push(child); }); }
  insertBefore(child, before) { child.parentNode = this; const index = this.children.indexOf(before); this.children.splice(index < 0 ? this.children.length : index, 0, child); }
  remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter(child => child !== this); this.isConnected = false; }
  replaceChildren(...items) { this.children.forEach(child => { child.isConnected = false; }); this.children = []; this._text = ""; this.append(...items); }
  addEventListener(name, callback) { this.listeners.set(name, callback); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  querySelector(selector) { return previewWalk(this).slice(1).find(node => selector.startsWith(".") ? node.className.split(/\s+/).includes(selector.slice(1)) : node.tagName === selector.toUpperCase()) ?? null; }
}
function previewWalk(node) { return [node, ...node.children.flatMap(previewWalk)]; }
function previewHarness({ viewerReady = true } = {}) {
  const ids = new Map(), requests = [], shown = [], $ = id => { if (!ids.has(id)) ids.set(id, new PreviewNode()); return ids.get(id); };
  const document = { getElementById: $, createElement: tag => new PreviewNode(tag), head: new PreviewNode("head") };
  const viewer = () => ({ setData: value => shown.push(value) });
  const sandbox = { document, Node: PreviewNode, window: { resultPresentation: presentation, ...(viewerReady ? { createFaceViewer: viewer } : {}) },
    location: { hash: "#results" }, URL, URLSearchParams, Intl, console,
    fetch: (path, options) => new Promise(resolve => { requests.push({ path, options, respond: (data, ok = true) => resolve({ ok, status: ok ? 200 : 409, json: async () => data }) }); }),
    setTimeout: () => { throw new Error("No live jobs or application timers permitted"); }, clearTimeout: () => {} };
  vm.createContext(sandbox);
  vm.runInContext(appSource.slice(0, bootBoundary) + "\n" + appSource.slice(switchStart, switchEnd)
    // Parent-preview harness does not mount execution controls; its assertions
    // exercise store fencing and artifact reads through the real functions.
    + "\nupdateControls=()=>{};globalThis.previewApp = {state,renderCadPreview,inspectExperiment,switchStore};", sandbox);
  const app = sandbox.previewApp; app.state.overview = { active_store: "local", stores: [{ id: "local", writable: true }] };
  const visual = new PreviewNode("article"); visual.append(Object.assign(new PreviewNode("h2"), { textContent: "모델 형상" }));
  const child = frozen(previewRecord()); app.state.selectedExperiment = child;
  return { app, visual, child, requests, shown, document, window: sandbox.window, viewer };
}
async function waitForRequests(h, count) { for (let tick = 0; tick < 30 && h.requests.length < count; tick++) await Promise.resolve(); assert.equal(h.requests.length, count); }
const DISPLAY_SURFACE = frozen({ bounds: [[0, 0, 0], [32, 40, 26]], faces: [] });
test("actual parent surface renderer reads the declared parent then its verified artifact and links that same parent", async () => {
  const h = previewHarness(), original = JSON.stringify(h.child), pending = h.app.renderCadPreview(h.visual, h.child);
  await waitForRequests(h, 1); assert.equal(h.requests[0].path, "/api/experiments/E-parent");
  h.requests[0].respond(frozen(previewRecord(true, [previewArtifact()])));
  await waitForRequests(h, 2); assert.equal(h.requests[1].path, "/api/artifacts/E-parent?path=cad%2Fnative%2Fsurface.json");
  h.requests[1].respond(DISPLAY_SURFACE); assert.equal(await pending, true); assert.equal(h.shown.length, 1); assert.equal(h.shown[0], DISPLAY_SURFACE);
  assert.equal(h.visual.querySelector("h2").textContent, "사용한 부모 CAD 형상(해석 메시/변형장 아님)");
  assert.match(h.visual.querySelector("canvas").attributes["aria-label"], /부모 CAD.*해석 메시\/변형장 아님/);
  assert.match(h.visual.textContent, /구속·하중 오버레이와 절점 변위.*제공하지 않습니다/);
  const parentLink = previewWalk(h.visual).find(node => node.tagName === "BUTTON" && node.className.includes("record-id")); assert(parentLink);
  assert.equal(parentLink.textContent, "이 형상의 부모 CAD 실험 보기 →"); assert.equal(JSON.stringify(h.child), original);
});
test("late parent record after a selection change cannot fetch or paint a different parent's surface", async () => {
  const h = previewHarness(), pending = h.app.renderCadPreview(h.visual, h.child);
  await waitForRequests(h, 1); h.app.state.selectedExperiment = previewRecord();
  h.requests[0].respond(previewRecord(true, [previewArtifact()])); assert.equal(await pending, false);
  assert.equal(h.requests.length, 1); assert.equal(h.shown.length, 0); assert.equal(h.visual.querySelector("canvas"), null);
  assert.equal(h.visual.querySelector("h2").textContent, "모델 형상");
});
test("late surface after a store switch and late viewer script after a request change never create a current canvas", async () => {
  for (const delayedScript of [false, true]) {
    const h = previewHarness({ viewerReady: !delayedScript }), pending = h.app.renderCadPreview(h.visual, h.child);
    await waitForRequests(h, 1); h.requests[0].respond(previewRecord(true, [previewArtifact()])); await waitForRequests(h, 2);
    if (!delayedScript) { h.app.state.overview.active_store = "other"; h.requests[1].respond(DISPLAY_SURFACE); }
    else {
      h.requests[1].respond(DISPLAY_SURFACE); for (let tick = 0; tick < 30 && !h.document.head.children.length; tick++) await Promise.resolve();
      assert.equal(h.document.head.children.length, 1); h.app.state.experimentRequest++;
      h.window.createFaceViewer = h.viewer; h.document.head.children[0].listeners.get("load")();
    }
    assert.equal(await pending, false); assert.equal(h.shown.length, 0); assert.equal(h.visual.querySelector("canvas"), null);
  }
});
test("actual store POST invalidates an outstanding parent read before the active-store response and blocks new inspection", async () => {
  const h = previewHarness(), pending = h.app.renderCadPreview(h.visual, h.child);
  await waitForRequests(h, 1); const switching = h.app.switchStore("other"); await waitForRequests(h, 2);
  assert.equal(h.app.state.storeSwitching, true); assert.equal(h.requests[1].path, "/api/store"); assert.equal(h.requests[1].options.method, "POST");
  await assert.rejects(h.app.inspectExperiment("E-analysis"), /저장소를 바꾸고 있습니다/);
  h.requests[0].respond(previewRecord(true, [previewArtifact()])); assert.equal(await pending, false);
  assert.equal(h.requests.length, 2); assert.equal(h.shown.length, 0);
  h.requests[1].respond({ error: "Controlled store rejection" }, false); await assert.rejects(switching, /Controlled store rejection/);
  assert.equal(h.app.state.storeSwitching, false);
});
test("parent record integrity/revision/link errors remain visible without any artifact fetch", async () => {
  for (const parent of [{ ...previewRecord(true, [previewArtifact()]), integrity: "NOT_CHECKED" },
    ...[{ cad_revision: "c".repeat(64) }, { experiment_id: "E-unrelated" }, { parent_experiment_id: "E-analysis" }]
      .map(change => ({ ...previewRecord(true), result: { ...previewRecord(true, [previewArtifact()]).result, ...change } }))]) {
    const h = previewHarness(), pending = h.app.renderCadPreview(h.visual, h.child);
    await waitForRequests(h, 1); h.requests[0].respond(parent); assert.equal(await pending, false);
    assert.equal(h.requests.length, 1); assert.match(h.visual.textContent, /형상을 불러오지 못했습니다/); assert.equal(h.shown.length, 0);
  }
});
test("parent endpoint errors and self-references cannot become an artifact preview", async () => {
  const h = previewHarness(), pending = h.app.renderCadPreview(h.visual, h.child);
  await waitForRequests(h, 1); h.requests[0].respond({ error: "Controlled missing parent" }, false);
  assert.equal(await pending, false); assert.match(h.visual.textContent, /Controlled missing parent/); assert.equal(h.requests.length, 1);
  const self = previewHarness();
  const invalid = frozen({ ...self.child, result: { ...self.child.result, parent_experiment_id: "E-analysis" } });
  self.app.state.selectedExperiment = invalid;
  assert.equal(await self.app.renderCadPreview(self.visual, invalid), false); assert.equal(self.requests.length, 0);
  assert.match(self.visual.textContent, /부모 CAD 연결과 개정을 확인할 수 없습니다/);
});
test("parent image stays hidden until its original load event and late images are discarded after selection changes", async () => {
  for (const stale of [false, true]) {
    const h = previewHarness(), pending = h.app.renderCadPreview(h.visual, h.child);
    await waitForRequests(h, 1); h.requests[0].respond(previewRecord(true, [previewArtifact("image")]));
    for (let tick = 0; tick < 30 && !h.visual.querySelector("img"); tick++) await Promise.resolve();
    const image = h.visual.querySelector("img"); assert(image); assert.equal(image.hidden, true);
    assert.equal(image.src, "/api/artifacts/E-parent?path=cad%2Fpreview.png"); assert.match(image.alt, /부모 CAD.*해석 메시\/변형장 아님/);
    if (stale) h.app.state.selectedExperiment = previewRecord();
    image.listeners.get("load")(); assert.equal(await pending, !stale); assert.equal(h.requests.length, 1);
    if (stale) { assert.equal(h.visual.querySelector("img"), null); assert.equal(image.hidden, true); }
    else assert.equal(image.hidden, false);
    assert.equal(h.shown.length, 0, "An image is never a nodal result field");
  }
});
