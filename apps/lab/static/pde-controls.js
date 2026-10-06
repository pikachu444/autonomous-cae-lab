"use strict";

// The general selected-mesh input form. Domain/adapter admission remains authoritative.
(function (root) {
  const sides = ["xmin", "xmax", "ymin", "ymax"];
  const decimal = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
  const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
  const keys = (value, expected) => object(value) && Object.keys(value).length === expected.length &&
    expected.every(key => Object.hasOwn(value, key));
  function demand(condition, message) { if (!condition) throw new Error(message); }
  function number(value, label, lower, upper, integer = false) {
    demand(typeof value === "string" && decimal.test(value.trim()), `${label}: 유한한 숫자를 입력하세요.`);
    const result = Number(value);
    demand(Number.isFinite(result) && result >= lower && result <= upper && (!integer || Number.isSafeInteger(result)),
      `${label}: ${lower}–${upper} 범위${integer ? "의 정수" : ""}를 입력하세요.`);
    return result;
  }
  function expression(value, label) {
    demand(typeof value === "string" && value.trim() && value.length <= 1024 && !/[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(value),
      `${label}: 식을 입력하세요. x[0], x[1]은 모델 좌표입니다.`);
    return value.trim();
  }
  function validate(settings) {
    demand(keys(settings, ["mode", "problem", "mesh", "validation"]) && settings.mode === "selected_mesh",
      "선택 메시 PDE 입력만 이 폼에서 편집할 수 있습니다.");
    const {problem, mesh, validation} = settings;
    demand(keys(problem, ["domain", "weak_form", "boundaries", "reference"]) && problem.reference === null,
      "일반 PDE의 참조는 미평가 상태여야 합니다.");
    demand(keys(problem.domain, ["type", "lengths"]) && problem.domain.type === "rectangle" &&
      Array.isArray(problem.domain.lengths) && problem.domain.lengths.length === 2 &&
      problem.domain.lengths.every(v => typeof v === "number" && Number.isFinite(v) && v >= .001 && v <= 1000),
      "직사각형의 두 길이를 명시하세요.");
    demand(keys(problem.weak_form, ["diffusion", "reaction", "rhs"]) &&
      typeof problem.weak_form.diffusion === "number" && Number.isFinite(problem.weak_form.diffusion) && problem.weak_form.diffusion > 0 &&
      typeof problem.weak_form.reaction === "number" && Number.isFinite(problem.weak_form.reaction) && problem.weak_form.reaction >= 0,
      "확산 계수는 양수, 반응 계수는 0 이상이어야 합니다.");
    expression(problem.weak_form.rhs, "원항");
    demand(keys(problem.boundaries, sides), "네 경계의 조건을 각각 명시하세요.");
    for (const side of sides) {
      const boundary = problem.boundaries[side];
      demand(keys(boundary, ["type", "value"]) && ["dirichlet", "neumann"].includes(boundary.type), `${side}: 지원 경계 조건을 선택하세요.`);
      expression(boundary.value, `${side} 경계 값`);
    }
    demand(sides.some(side => problem.boundaries[side].type === "dirichlet"), "최소 한 변에 Dirichlet 조건이 필요합니다.");
    demand(keys(mesh, ["cell_counts", "degree"]) && mesh.degree === 1 && Array.isArray(mesh.cell_counts) &&
      mesh.cell_counts.length === 1 && Number.isSafeInteger(mesh.cell_counts[0]) && mesh.cell_counts[0] >= 1 && mesh.cell_counts[0] <= 128,
      "축당 1–128개의 선택 메시 하나를 지정하세요.");
    demand(keys(validation, ["max_residual_relative"]) && typeof validation.max_residual_relative === "number" &&
      Number.isFinite(validation.max_residual_relative) && validation.max_residual_relative > 0,
      "선형 잔차 기준이 유한한 양수여야 합니다.");
    return structuredClone(settings);
  }
  function toFields(settings) {
    const selected = validate(settings), problem = selected.problem;
    const result = {length_x: String(problem.domain.lengths[0]), length_y: String(problem.domain.lengths[1]),
      diffusion: String(problem.weak_form.diffusion), reaction: String(problem.weak_form.reaction),
      rhs: problem.weak_form.rhs, cells: String(selected.mesh.cell_counts[0]),
      residual: String(selected.validation.max_residual_relative)};
    for (const side of sides) { result[`${side}_type`] = problem.boundaries[side].type; result[`${side}_value`] = problem.boundaries[side].value; }
    return result;
  }
  function fromFields(fields, settings) {
    const result = validate(settings);
    result.problem.domain.lengths = [number(fields.length_x, "X 길이", .001, 1000), number(fields.length_y, "Y 길이", .001, 1000)];
    result.problem.weak_form = {diffusion: number(fields.diffusion, "확산 계수", Number.MIN_VALUE, Number.MAX_VALUE),
      reaction: number(fields.reaction, "반응 계수", 0, Number.MAX_VALUE), rhs: expression(fields.rhs, "원항")};
    result.mesh.cell_counts = [number(fields.cells, "축당 메시 수", 1, 128, true)];
    result.validation.max_residual_relative = number(fields.residual, "선형 잔차 기준", Number.MIN_VALUE, Number.MAX_VALUE);
    for (const side of sides) result.problem.boundaries[side] = {type: fields[`${side}_type`], value: expression(fields[`${side}_value`], side)};
    return validate(result);
  }
  const api = Object.freeze({validate, toFields, fromFields});
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.pdeControls = api;
})(typeof window !== "undefined" ? window : globalThis);
