"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const controls = require("../apps/lab/static/coupled-controls.js");

// Exact selected_settings factory shape; tests do not solve/evaluate any PDE.
function selected() {
  return { mode: "selected_mesh",
    problem: { domain: { type: "rectangle", lengths: [2, 1], interface: { axis: 0, fraction: 0.5 } },
      weak_form: { family: "coupled_diffusion", diffusion: { left: [[2, 0.5], [0.5, 1]], right: [[4, -0.5], [-0.5, 2]] },
        reaction: [[0, 0], [0, 0]], rhs: { left: ["1", "-0.5"], right: ["2", "1"] } },
      boundaries: { xmin: { type: "dirichlet", value: { left: ["0", "0"] } }, xmax: { type: "dirichlet", value: { right: ["0", "0"] } },
        ymin: { type: "neumann", value: { left: ["0", "0"], right: ["0", "0"] } }, ymax: { type: "neumann", value: { left: ["0", "0"], right: ["0", "0"] } } }, reference: null },
    mesh: { cell_counts: [16], degree: 1 }, validation: { max_residual_relative: 1e-10 },
    input_provenance: { origin: "ASSUMED", reference: "Editable assumed dimensionless mathematical inputs; no physical material interpretation" } };
}
function freeze(value) { if (value && typeof value === "object") { Object.values(value).forEach(freeze); Object.freeze(value); } return value; }

test("corrected five-key selected settings roundtrip exactly without reference/sweep creation or mutation", () => {
  const baseline = freeze(selected()), fields = controls.toFields(baseline), copied = controls.validate(baseline);
  assert.deepEqual(Object.keys(controls).sort(), ["fieldDefinitions", "fromFields", "toFields", "validate"]);
  assert.deepEqual(Object.keys(baseline).sort(), ["input_provenance", "mesh", "mode", "problem", "validation"]);
  assert.equal(Object.keys(fields).length, 34); assert(Object.values(fields).every(value => typeof value === "string"));
  assert.deepEqual(controls.fromFields(freeze(fields), baseline), baseline); assert.deepEqual(copied, baseline);
  copied.problem.domain.lengths[0] = 3; copied.input_provenance.reference = "changed";
  assert.equal(baseline.problem.domain.lengths[0], 2); assert.equal(baseline.mesh.cell_counts.length, 1);
  assert.equal(baseline.problem.reference, null); assert.equal(baseline.validation.max_residual_relative, 1e-10);
});

test("field definitions expose exact known fields, component-row/unit semantics and explicit Korean enum options", () => {
  const definitions = controls.fieldDefinitions, fields = controls.toFields(selected());
  assert.deepEqual(definitions.map(row => row.id), Object.keys(fields)); assert.equal(new Set(definitions.map(row => row.id)).size, 34);
  assert(Object.isFrozen(definitions)); assert(definitions.every(Object.isFrozen));
  const origin = definitions.find(row => row.id === "origin"); assert.equal(origin.type, "select");
  assert.deepEqual(origin.options.map(row => row.value), ["ASSUMED", "MEASURED_REPORTED", "PUBLISHED_REFERENCE", "SYNTHETIC"]);
  assert.match(origin.options[1].label, /미검증/); assert(Object.isFrozen(origin.options)); assert(origin.options.every(Object.isFrozen));
  for (const side of ["xmin", "xmax", "ymin", "ymax"]) {
    const row = definitions.find(row => row.id === `boundary_${side}_type`);
    assert.deepEqual(row.options.map(option => option.value), ["dirichlet", "neumann"]);
  }
  assert.match(definitions.find(row => row.id === "diffusion_left_01").label, /D01 = D10.*성분 u0행\/u1열.*단위 1/);
  assert.match(definitions.find(row => row.id === "reaction_01").label, /R01 = R10/);
  assert.equal(definitions.find(row => row.id === "reference").type, "textarea");
  assert(!definitions.some(row => /MPa|온도|변위|열전달/.test(row.label)));
});

test("simultaneous coupling edits mirror offdiagonals explicitly and retain source, row order and immutable guards", () => {
  const baseline = selected(), fields = controls.toFields(baseline), before = structuredClone(baseline);
  fields.diffusion_left_01 = "-0.25"; fields.diffusion_right_01 = " .75 ";
  fields.reaction_00 = "2"; fields.reaction_01 = "-5e-1"; fields.reaction_11 = "1";
  fields.length_x = "3.25"; fields.cell_count = "24"; fields.rhs_left_0 = "-exp(x[0])+x[1]"; fields.rhs_right_1 = "2*x[0]-1";
  fields.boundary_xmax_type = "neumann"; fields.boundary_xmax_right_0 = "-2*x[1]";
  fields.origin = "PUBLISHED_REFERENCE"; fields.reference = " \n원 출처 · 질문과 가설을 포함한 연구 맥락\n ";
  const result = controls.fromFields(freeze(fields), baseline);
  assert.deepEqual(result.problem.weak_form.diffusion.left, [[2, -0.25], [-0.25, 1]]);
  assert.deepEqual(result.problem.weak_form.diffusion.right, [[4, 0.75], [0.75, 2]]);
  assert.deepEqual(result.problem.weak_form.reaction, [[2, -0.5], [-0.5, 1]]);
  assert.equal(result.problem.boundaries.xmax.type, "neumann"); assert.deepEqual(result.problem.boundaries.xmax.value.right, ["-2*x[1]", "0"]);
  assert.equal(result.input_provenance.reference, fields.reference); assert.deepEqual(baseline, before);
  assert.deepEqual(result.problem.domain.interface, before.problem.domain.interface); assert.equal(result.problem.reference, null);
  assert.deepEqual(result.validation, before.validation); assert.equal(result.mode, "selected_mesh"); assert.deepEqual(result.mesh, { cell_counts: [24], degree: 1 });
});

test("human form preserves finite Domain-supported matrices beyond search descriptor bounds and does not clamp values", () => {
  const cases = [ [[1e-12, 0], [0, 1e-12]], [[2e6, -1e6], [-1e6, 2e6]], [[1e300, 0], [0, 1e300]] ];
  for (const matrix of cases) { const settings = selected(); settings.problem.weak_form.diffusion.left = matrix;
    assert.deepEqual(controls.fromFields(controls.toFields(settings), settings).problem.weak_form.diffusion.left, matrix); }
  const settings = selected(); settings.problem.weak_form.reaction = [[1, -1], [-1, 1]];
  assert.deepEqual(controls.fromFields(controls.toFields(settings), settings).problem.weak_form.reaction, [[1, -1], [-1, 1]]);
});

test("invalid/asymmetric/nonfinite/nonboolean SPD and PSD inputs refuse without repair or new tolerance", () => {
  const invalid = [
    settings => { settings.problem.weak_form.diffusion.left = [[1, 1], [1, 1]]; },
    settings => { settings.problem.weak_form.diffusion.left = [[0, 0], [0, 1]]; },
    settings => { settings.problem.weak_form.diffusion.left = [[2, 0.5], [0.25, 1]]; },
    settings => { settings.problem.weak_form.diffusion.left = [[1e300, 0], [0, 1e-300]]; },
    settings => { settings.problem.weak_form.reaction = [[0, 0.1], [0.1, 1]]; },
    settings => { settings.problem.weak_form.reaction = [[1, 2], [2, 1]]; },
    settings => { settings.problem.weak_form.reaction[0][0] = -1; },
    settings => { settings.problem.weak_form.diffusion.left[0][0] = true; },
    settings => { settings.problem.weak_form.diffusion.right[1][1] = Infinity; },
    settings => { settings.problem.weak_form.reaction[1][1] = NaN; },
  ];
  for (const change of invalid) { const settings = selected(); change(settings); assert.throws(() => controls.validate(settings)); }
  const fields = controls.toFields(selected()); fields.diffusion_left_01 = "4";
  assert.throws(() => controls.fromFields(fields, selected()), /SPD/);
});

test("four side own-region vectors and at least one whole-vector Dirichlet condition are required", () => {
  const invalid = [
    settings => { settings.problem.boundaries = {}; },
    settings => { delete settings.problem.boundaries.xmin; },
    settings => { settings.problem.boundaries.xmin.value.right = ["0", "0"]; },
    settings => { delete settings.problem.boundaries.ymax.value.right; },
    settings => { settings.problem.boundaries.ymin.value.left = ["0"]; },
    settings => { settings.problem.boundaries.xmax.type = "robin"; },
    settings => { Object.values(settings.problem.boundaries).forEach(row => { row.type = "neumann"; }); },
  ];
  for (const change of invalid) { const settings = selected(); change(settings); assert.throws(() => controls.validate(settings)); }
  const fields = controls.toFields(selected()); fields.boundary_xmin_type = "neumann";
  assert.equal(controls.fromFields(fields, selected()).problem.boundaries.xmax.type, "dirichlet");
  fields.boundary_xmax_type = "neumann"; assert.throws(() => controls.fromFields(fields, selected()), /Neumann/);
});

test("selected mode, midpoint/P1, single even count and original residual threshold are invariant", () => {
  const invalid = [
    settings => { settings.mode = "benchmark"; }, settings => { delete settings.mode; },
    settings => { settings.problem.reference = { solution: { left: ["0", "0"], right: ["0", "0"] }, source: "guessed" }; },
    settings => { settings.problem.domain.interface.axis = true; }, settings => { settings.problem.domain.interface.fraction = 0.4; },
    settings => { settings.problem.domain.lengths[0] = 0.0009; }, settings => { settings.problem.domain.lengths[1] = 1001; },
    settings => { settings.mesh.cell_counts = [16, 32, 64]; }, settings => { settings.mesh.cell_counts = [3]; },
    settings => { settings.mesh.cell_counts = [0]; }, settings => { settings.mesh.cell_counts = [130]; },
    settings => { settings.mesh.degree = true; }, settings => { settings.mesh.degree = 2; },
    settings => { settings.validation.max_residual_relative = 2e-10; },
    settings => { settings.validation.min_l2_rate = 1.8; }, settings => { settings.problem.weak_form.family = "heat_structure"; },
  ];
  for (const change of invalid) { const settings = selected(); change(settings); assert.throws(() => controls.validate(settings)); }
  for (const count of [2, 128]) { const fields = controls.toFields(selected()); fields.cell_count = String(count); assert.equal(controls.fromFields(fields, selected()).mesh.cell_counts[0], count); }
});

test("source origin and exact reference/hypothesis context are preserved without inferred qualification", () => {
  const baseline = selected(), context = " \n질문: u0/u1 부호와 영역별 차이는?\n가설: 결합 항의 효과를 구별한다.\n목적: 수치 연구 <script>literal</script>\n ";
  for (const origin of ["ASSUMED", "MEASURED_REPORTED", "PUBLISHED_REFERENCE", "SYNTHETIC"]) {
    const fields = controls.toFields(baseline); fields.origin = origin; fields.reference = context;
    const result = controls.fromFields(fields, baseline);
    assert.equal(result.input_provenance.reference, context); assert.equal(controls.toFields(result).reference, context);
    assert.equal(result.input_provenance.origin, origin); assert.equal(result.problem.reference, null);
    assert(!Object.hasOwn(result.input_provenance, "physical_qualification"));
  }
  for (const change of [settings => { delete settings.input_provenance; }, settings => { settings.input_provenance.origin = "INFERRED"; },
    settings => { settings.input_provenance.reference = " "; }, settings => { settings.input_provenance.reference = "근".repeat(2001); }]) {
    const settings = selected(); change(settings); assert.throws(() => controls.validate(settings));
  }
});

test("safe syntax supports signed component equations and fixed functions without evaluating supplied expressions", () => {
  const baseline = selected(), equations = ["-exp(x[0])+x[1]", "sin(pi*x[1])", "cos(x[0])+2*x[1]**2", "x[0]**(1+2)",
    "1/(x[0]-0.5)", "exp(1000)", "1/(1-1)"];
  // Last three are syntactically safe only: Domain must evaluate constants and
  // check all required grid/corner values before any native model is admitted.
  for (const equation of equations) { const fields = controls.toFields(baseline); fields.rhs_left_0 = equation;
    assert.equal(controls.fromFields(fields, baseline).problem.weak_form.rhs.left[0], equation); }
  assert.equal(baseline.problem.weak_form.rhs.left[0], "1");
});

test("unsafe/excessive/unsupported expression syntax is rejected without arbitrary executable access", () => {
  const expressions = ["", "__import__('os').system('run')", "x.constructor()", "x[2]", "x[0.0]", "x[0:1]", "sin(x[0],x[1])", "cos()",
    "sqrt(x[0])", "true", "Infinity", "NaN", "+2", "1//2", "2%1", "2;run()", "x[0]**x[1]", "x[0]**17", "x[0]**(-17)",
    "1000001", "1e999", "-".repeat(22) + "1", Array.from({ length: 65 }, () => "x[0]").join("+"), "1".repeat(1025)];
  for (const expression of expressions) { const fields = controls.toFields(selected()); fields.rhs_right_1 = expression;
    assert.throws(() => controls.fromFields(fields, selected()), undefined, expression); }
});

test("only exact 34 typed fields are accepted; absent values, aliases, unit overrides and numeric execution refuse", () => {
  const cases = [
    fields => { delete fields.rhs_left_0; }, fields => { fields.diffusion_left_10 = "0.5"; }, fields => { fields.axis = "world"; },
    fields => { fields.max_residual_relative = "1"; }, fields => { fields.length_x = true; }, fields => { fields.reaction_00 = "NaN"; },
    fields => { fields.length_x = "Number(2)"; }, fields => { fields.length_y = "0x10"; }, fields => { fields.cell_count = "16.5"; },
    fields => { fields.origin = "MEASURED_VALIDATED"; }, fields => { fields.boundary_ymin_type = "Robin"; },
  ];
  for (const change of cases) { const fields = controls.toFields(selected()); change(fields); assert.throws(() => controls.fromFields(fields, selected())); }
  const fields = controls.toFields(selected()); fields.reaction_00 = "-0"; fields.reaction_01 = "-0"; fields.reaction_11 = "-0";
  const result = controls.fromFields(fields, selected()); assert(Object.is(result.problem.weak_form.reaction[1][0], -0));
  assert.deepEqual(controls.toFields(result), fields);
});

test("own JSON guards reject prototype/getter/nonfinite data without executing accessors", () => {
  let reads = 0; const settings = selected(); Object.defineProperty(settings.problem.weak_form, "reaction", { enumerable: true, get() { reads++; return [[0, 0], [0, 0]]; } });
  assert.throws(() => controls.validate(settings)); assert.equal(reads, 0);
  const fields = controls.toFields(selected()); Object.defineProperty(fields, "reference", { enumerable: true, get() { reads++; return "secret"; } });
  assert.throws(() => controls.fromFields(fields, selected())); assert.equal(reads, 0);
  const bad = selected(); bad.input_provenance = JSON.parse('{"origin":"ASSUMED","reference":"literal","__proto__":{}}'); assert.throws(() => controls.validate(bad));
  const sparse = selected(); delete sparse.problem.weak_form.diffusion.left[0][0]; assert.throws(() => controls.validate(sparse));
  const cyclic = selected(); cyclic.input_provenance.cycle = cyclic; assert.throws(() => controls.validate(cyclic));
});

test("browser loading exposes a frozen standalone helper and preserves serialized cross-realm inputs without runtime calls", () => {
  const source = fs.readFileSync(path.join(__dirname, "../apps/lab/static/coupled-controls.js"), "utf8"), context = vm.createContext({ window: {}, raw: JSON.stringify(selected()),
    fetch() { throw new Error("No runtime calls"); }, eval() { throw new Error("No expression eval"); } });
  vm.runInContext(source, context); const result = vm.runInContext("window.coupledControls.fromFields(window.coupledControls.toFields(JSON.parse(raw)), JSON.parse(raw))", context);
  assert.equal(result.problem.reference, null); assert.equal(result.mesh.cell_counts[0], 16);
  assert.deepEqual(Object.keys(context.window.coupledControls).sort(), ["fieldDefinitions", "fromFields", "toFields", "validate"]);
  assert.equal(context.window.coupledControls.fieldDefinitions.length, 34); assert(Object.isFrozen(context.window.coupledControls));
});
