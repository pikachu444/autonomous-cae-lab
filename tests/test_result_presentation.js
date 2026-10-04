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

test("solver execution preserves explicit convergence uncertainty, invalid responses and release verdict", () => {
  for (const converged of [undefined, false, true]) {
    const record = frozen({ ...cad(), solver_status: "COMPLETED", decision: "UNKNOWN", converged });
    const before = JSON.stringify(record), report = presentation.workflow(record, context(record));
    assert.equal(report.stage, "해석 실행됨 · 결과 검토 필요"); assert.equal(report.tone, "review");
    assert.match(report.next, /검사 근거·남은 확인 사항/); assert.match(report.next, /승인을 확정할 수 없습니다/);
    if (converged === undefined) assert.match(report.next, /수렴 여부는 미확인/);
    if (converged === false) assert.match(report.next, /미수렴으로 기록/);
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
