"use strict";

// Selected dimensionless inputs only. No expression is evaluated here; Domain
// checks constant folding, exponent values, corner/interface compatibility and
// grid singularities before native execution. Matrices act on component rows
// of grad(u), not spatial tensor directions or physical material properties.
(function (root) {
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
  const exact = (value, keys) => object(value) && Object.keys(value).length === keys.length && keys.every(key => own(value, key));
  const finite = value => typeof value === "number" && Number.isFinite(value);
  const regions = ["left", "right"], sides = ["xmin", "xmax", "ymin", "ymax"], positions = [[0, 0], [0, 1], [1, 1]];
  const touching = side => side === "xmin" ? ["left"] : side === "xmax" ? ["right"] : regions;
  const decimal = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
  const origins = ["ASSUMED", "MEASURED_REPORTED", "PUBLISHED_REFERENCE", "SYNTHETIC"];
  const originOptions = [{ value: "ASSUMED", label: "가정" }, { value: "MEASURED_REPORTED", label: "사용자 측정 보고 · 미검증" },
    { value: "PUBLISHED_REFERENCE", label: "공개 참조" }, { value: "SYNTHETIC", label: "가상 데이터/기준" }];
  const boundaryOptions = [{ value: "dirichlet", label: "Dirichlet · 전체 성분 값" }, { value: "neumann", label: "Neumann · 바깥쪽 연산자 플럭스" }];
  const labels = { left: "왼쪽", right: "오른쪽", xmin: "x 최소 경계", xmax: "x 최대 경계", ymin: "y 최소 경계", ymax: "y 최대 경계" };
  const fieldDefinitions = [
    { id: "length_x", label: "사각형 x 길이 (단위 1)", type: "number" }, { id: "length_y", label: "사각형 y 길이 (단위 1)", type: "number" },
    ...regions.flatMap(region => positions.map(([i, j]) => ({ id: `diffusion_${region}_${i}${j}`, type: "number",
      label: `${labels[region]} 확산 D${i}${j}${i === j ? "" : " = D10"} (성분 u${i}행/u${j}열 · 단위 1)` }))),
    ...positions.map(([i, j]) => ({ id: `reaction_${i}${j}`, type: "number", label: `공통 반응 R${i}${j}${i === j ? "" : " = R10"} (성분 u${i}행/u${j}열 · 단위 1)` })),
    ...regions.flatMap(region => [0, 1].map(component => ({ id: `rhs_${region}_${component}`, label: `${labels[region]} 우변 u${component} (단위 1)`, type: "text" }))),
    ...sides.flatMap(side => [{ id: `boundary_${side}_type`, label: `${labels[side]} · 전체 u0/u1 조건`, type: "select", options: boundaryOptions },
      ...touching(side).flatMap(region => [0, 1].map(component => ({ id: `boundary_${side}_${region}_${component}`, type: "text",
        label: `${labels[side]} ${labels[region]} u${component} 값/연산자 플럭스 (단위 1)` })))]),
    { id: "cell_count", label: "선택 P1 메시 · 축별 짝수 분할 수 (2–128)", type: "number" },
    { id: "origin", label: "입력 출처 분류 · 자격 미검증", type: "select", options: originOptions },
    { id: "reference", label: "입력 출처·연구 맥락 원문", type: "textarea" },
  ];
  fieldDefinitions.forEach(definition => {
    if (definition.options) { definition.options.forEach(Object.freeze); Object.freeze(definition.options); }
    Object.freeze(definition);
  }); Object.freeze(fieldDefinitions);
  const fieldKeys = fieldDefinitions.map(row => row.id);
  const numberText = value => Object.is(value, -0) ? "-0" : String(value);
  function demand(condition, message) { if (!condition) throw new Error(message); }
  function constructorName(prototype) {
    const constructor = prototype && Object.getOwnPropertyDescriptor(prototype, "constructor")?.value;
    return typeof constructor === "function" ? Object.getOwnPropertyDescriptor(constructor, "name")?.value : null;
  }
  function ordinaryObjectPrototype(prototype) {
    return prototype !== null && Object.getPrototypeOf(prototype) === null && constructorName(prototype) === "Object";
  }
  function json(value, ancestors = new Set(), depth = 0) {
    if (depth > 64) return false;
    if (value === null || ["string", "boolean"].includes(typeof value)) return true;
    if (typeof value === "number") return Number.isFinite(value);
    if ((!Array.isArray(value) && !object(value)) || ancestors.has(value)) return false;
    const prototype = Object.getPrototypeOf(value);
    if (Array.isArray(value) ? prototype !== Array.prototype && !(Array.isArray(prototype) && constructorName(prototype) === "Array" &&
      ordinaryObjectPrototype(Object.getPrototypeOf(prototype))) : prototype !== null && prototype !== Object.prototype && !ordinaryObjectPrototype(prototype)) return false;
    const names = Reflect.ownKeys(value).filter(key => !(Array.isArray(value) && key === "length"));
    if (names.some(key => {
      const property = Object.getOwnPropertyDescriptor(value, key);
      return typeof key !== "string" || ["__proto__", "prototype", "constructor"].includes(key) || !property.enumerable || !own(property, "value");
    }) || (Array.isArray(value) && (names.length !== value.length || names.some((key, index) => key !== String(index))))) return false;
    ancestors.add(value); const valid = names.every(key => json(value[key], ancestors, depth + 1)); ancestors.delete(value); return valid;
  }
  function clone(value) {
    if (Array.isArray(value)) return value.map(clone);
    return object(value) ? Object.fromEntries(Object.entries(value).map(([key, item]) => [key, clone(item)])) : value;
  }
  function matrixValid(value, label, positive) {
    demand(Array.isArray(value) && value.length === 2 && value.every(row => Array.isArray(row) && row.length === 2 && row.every(finite)) && value[0][1] === value[1][0],
      `${label}: 유한하고 정확히 대칭인 2×2 성분 행렬이 필요합니다.`);
    const a = value[0][0], b = value[0][1], d = value[1][1];
    demand(a >= 0 && d >= 0 && (!positive || a > 0 && d > 0), `${label}: 주대각 성분이 ${positive ? "양수" : "0 이상"}여야 합니다.`);
    if (a === 0 || d === 0) { demand(b === 0, `${label}: 0인 주대각 성분에 0이 아닌 결합을 둘 수 없습니다.`); return; }
    const scale = Math.max(Math.abs(a), Math.abs(b), Math.abs(d)), sa = a / scale, sb = b / scale, sd = d / scale;
    demand([[a, sa], [b, sb], [d, sd]].every(([original, scaled]) => original === 0 || scaled !== 0), `${label}: 실수 정밀도에서 양의 정부호/준정부호를 확인할 수 없습니다.`);
    const diagonal = sa * sd, offDiagonal = sb * sb;
    demand(diagonal !== 0, `${label}: 주행렬식 성분이 지원 실수 정밀도에서 0으로 소실됩니다.`);
    demand(positive ? diagonal - offDiagonal > 0 : diagonal - offDiagonal >= 0, `${label}: ${positive ? "양의 정부호(SPD)" : "양의 준정부호(PSD)"} 조건을 만족하지 않습니다.`);
  }
  function expressionValid(source, label) {
    demand(typeof source === "string" && source.trim() && source.length <= 1024, `${label}: 비어 있지 않은 1024자 이하 수식이 필요합니다.`);
    // A syntax tree only. There is no eval, Function, coordinate sampling,
    // trigonometric call or arithmetic evaluation of the supplied expression.
    const tokens = [], pattern = /\s+|(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|[A-Za-z_][A-Za-z0-9_]*|\*\*|[+\-*/()[\]]/y;
    for (let cursor = 0; cursor < source.length;) {
      pattern.lastIndex = cursor; const match = pattern.exec(source);
      demand(match, `${label}: 지원하지 않는 문자·경로·실행 구문입니다.`); cursor = pattern.lastIndex;
      if (!/^\s+$/.test(match[0])) tokens.push(match[0]);
    }
    let cursor = 0, grouping = 0;
    const peek = () => tokens[cursor];
    function take(expected) { demand(peek() === expected, `${label}: 괄호·성분 좌표 또는 수식 구조가 올바르지 않습니다.`); cursor++; }
    function node(kind, children = [], value = null) {
      const result = { kind, value, coordinate: kind === "coordinate" || children.some(child => child.coordinate),
        literalMagnitude: kind === "constant" ? Math.abs(value) : kind === "negative" ? children[0].literalMagnitude : null,
        size: ({ constant: 1, pi: 2, coordinate: 5, negative: 2, binary: 2, call: 3 })[kind] + children.reduce((sum, child) => sum + child.size, 0),
        depth: children.length ? 1 + Math.max(...children.map(child => child.depth)) : 0 };
      demand(result.size + 1 <= 128 && result.depth <= 20, `${label}: 수식의 구조는 128개 AST 절점·20단계 깊이 이내여야 합니다.`); return result;
    }
    function atom() {
      const token = peek(); demand(token !== undefined, `${label}: 수식의 값이나 피연산자가 누락되었습니다.`);
      if (token === "(") {
        demand(++grouping <= 128, `${label}: 괄호가 지원 깊이를 초과합니다.`); cursor++; const result = sum(); take(")"); grouping--; return result;
      }
      if (/^(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(token)) {
        const value = Number(token); demand(finite(value) && Math.abs(value) <= 1e6, `${label}: 수식 상수의 크기는 유한한 1e6 이하여야 합니다.`); cursor++; return node("constant", [], value);
      }
      if (token === "pi") { cursor++; return node("pi"); }
      if (token === "x") { cursor++; take("["); demand(["0", "1"].includes(peek()), `${label}: 좌표는 x[0] 또는 x[1]만 지원합니다.`); cursor++; take("]"); return node("coordinate"); }
      if (["sin", "cos", "exp"].includes(token)) { cursor++; take("("); const argument = sum(); take(")"); return node("call", [argument]); }
      throw new Error(`${label}: 허용된 scalar 이름·함수는 pi, x[0]/x[1], sin/cos/exp입니다.`);
    }
    function power() {
      const base = atom(); if (peek() !== "**") return base;
      cursor++; const exponent = factor(); demand(!exponent.coordinate, `${label}: 지수는 좌표에 의존하지 않는 상수 수식이어야 합니다.`);
      demand(exponent.literalMagnitude === null || exponent.literalMagnitude <= 16, `${label}: 상수 지수의 크기는 16 이하여야 합니다.`); return node("binary", [base, exponent]);
    }
    function factor() { if (peek() !== "-") return power(); cursor++; return node("negative", [factor()]); }
    function product() {
      let result = factor(); while (["*", "/"].includes(peek())) { cursor++; result = node("binary", [result, factor()]); } return result;
    }
    function sum() {
      let result = product(); while (["+", "-"].includes(peek())) { cursor++; result = node("binary", [result, product()]); } return result;
    }
    sum(); demand(cursor === tokens.length, `${label}: 닫히지 않은 수식·추가 인수·비지원 구문이 있습니다.`);
  }
  function vectorValid(value, label) {
    demand(Array.isArray(value) && value.length === 2, `${label}: u0/u1 순서의 두 성분 수식이 필요합니다.`);
    value.forEach((source, component) => expressionValid(source, `${label} u${component}`));
  }
  function validate(settings) {
    demand(json(settings) && exact(settings, ["mode", "problem", "mesh", "validation", "input_provenance"]) && settings.mode === "selected_mesh",
      "이 폼은 mode/problem/mesh/validation/input_provenance 5개 필드의 selected_mesh 입력만 편집합니다.");
    const problem = settings.problem;
    demand(exact(problem, ["domain", "weak_form", "boundaries", "reference"]) && problem.reference === null &&
      exact(problem.domain, ["type", "lengths", "interface"]) && problem.domain.type === "rectangle" && Array.isArray(problem.domain.lengths) && problem.domain.lengths.length === 2 &&
      problem.domain.lengths.every(value => finite(value) && value >= 0.001 && value <= 1000) && exact(problem.domain.interface, ["axis", "fraction"]) &&
      problem.domain.interface.axis === 0 && problem.domain.interface.fraction === 0.5,
    "사각형 길이는 0.001–1000(단위 1), x 중간 경계는 0.5이며 참조 해는 null로 보존해야 합니다.");
    const weak = problem.weak_form;
    demand(exact(weak, ["family", "diffusion", "reaction", "rhs"]) && weak.family === "coupled_diffusion" && exact(weak.diffusion, regions) && exact(weak.rhs, regions),
      "성분 행 확산·공통 반응·영역별 u0/u1 우변을 명시하세요. 물성이나 공간 방향 텐서로 해석하지 않습니다.");
    regions.forEach(region => { matrixValid(weak.diffusion[region], `${labels[region]} 성분 확산`, true); vectorValid(weak.rhs[region], `${labels[region]} 우변`); });
    matrixValid(weak.reaction, "공통 성분 반응", false);
    demand(exact(problem.boundaries, sides), "xmin/xmax/ymin/ymax 네 경계를 명시하세요.");
    sides.forEach(side => {
      const boundary = problem.boundaries[side]; demand(exact(boundary, ["type", "value"]) && ["dirichlet", "neumann"].includes(boundary.type) && exact(boundary.value, touching(side)),
        `${labels[side]}: 접하는 원 영역의 전체 u0/u1 Dirichlet/Neumann 조건이 필요합니다.`);
      touching(side).forEach(region => vectorValid(boundary.value[region], `${labels[side]} ${labels[region]}`));
    });
    demand(sides.some(side => problem.boundaries[side].type === "dirichlet"), "전체 성분 Dirichlet 경계가 최소 하나 필요합니다. 순수 Neumann은 지원하지 않습니다.");
    demand(exact(settings.mesh, ["cell_counts", "degree"]) && settings.mesh.degree === 1 && Array.isArray(settings.mesh.cell_counts) && settings.mesh.cell_counts.length === 1 &&
      Number.isInteger(settings.mesh.cell_counts[0]) && settings.mesh.cell_counts[0] >= 2 && settings.mesh.cell_counts[0] <= 128 && settings.mesh.cell_counts[0] % 2 === 0,
    "P1 메시의 축별 짝수 분할 수 2–128 하나를 선택하세요. 자동 메시 sweep은 만들지 않습니다.");
    demand(exact(settings.validation, ["max_residual_relative"]) && settings.validation.max_residual_relative === 1e-10,
      "원 상대 잔차 한계 1e-10을 보존해야 합니다.");
    const provenance = settings.input_provenance;
    demand(exact(provenance, ["origin", "reference"]) && origins.includes(provenance.origin) && typeof provenance.reference === "string" && provenance.reference.trim() &&
      provenance.reference.length <= 4000 && Array.from(provenance.reference).length <= 2000,
    "입력 출처 분류와 비어 있지 않은 2000자 이내의 원문 근거를 명시하세요.");
    return clone(settings);
  }
  function numeric(value, label) {
    demand(typeof value === "string" && decimal.exec(value.trim())?.[0] === value.trim(), `${label}: 십진수 또는 지수 표기의 유한한 숫자를 명시하세요.`);
    const result = Number(value); demand(finite(result), `${label}: 유한한 숫자를 명시하세요.`); return result;
  }
  function toFields(settings) {
    const result = validate(settings), problem = result.problem, weak = problem.weak_form;
    const fields = { length_x: numberText(problem.domain.lengths[0]), length_y: numberText(problem.domain.lengths[1]) };
    regions.forEach(region => positions.forEach(([i, j]) => { fields[`diffusion_${region}_${i}${j}`] = numberText(weak.diffusion[region][i][j]); }));
    positions.forEach(([i, j]) => { fields[`reaction_${i}${j}`] = numberText(weak.reaction[i][j]); });
    regions.forEach(region => [0, 1].forEach(component => { fields[`rhs_${region}_${component}`] = weak.rhs[region][component]; }));
    sides.forEach(side => {
      fields[`boundary_${side}_type`] = problem.boundaries[side].type;
      touching(side).forEach(region => [0, 1].forEach(component => { fields[`boundary_${side}_${region}_${component}`] = problem.boundaries[side].value[region][component]; }));
    });
    Object.assign(fields, { cell_count: numberText(result.mesh.cell_counts[0]), origin: result.input_provenance.origin, reference: result.input_provenance.reference }); return fields;
  }
  function fromFields(fields, settings) {
    const result = validate(settings);
    demand(json(fields) && exact(fields, fieldKeys) && Object.values(fields).every(value => typeof value === "string"), "현재 결합 PDE 폼의 정확한 34개 문자열 입력을 명시하세요.");
    const problem = result.problem, weak = problem.weak_form;
    problem.domain.lengths = [numeric(fields.length_x, "x 길이(단위 1)"), numeric(fields.length_y, "y 길이(단위 1)")];
    regions.forEach(region => positions.forEach(([i, j]) => {
      const value = numeric(fields[`diffusion_${region}_${i}${j}`], `${labels[region]} D${i}${j}`); weak.diffusion[region][i][j] = value; weak.diffusion[region][j][i] = value;
    }));
    positions.forEach(([i, j]) => { const value = numeric(fields[`reaction_${i}${j}`], `R${i}${j}`); weak.reaction[i][j] = value; weak.reaction[j][i] = value; });
    regions.forEach(region => [0, 1].forEach(component => { weak.rhs[region][component] = fields[`rhs_${region}_${component}`]; }));
    sides.forEach(side => {
      problem.boundaries[side].type = fields[`boundary_${side}_type`];
      touching(side).forEach(region => [0, 1].forEach(component => { problem.boundaries[side].value[region][component] = fields[`boundary_${side}_${region}_${component}`]; }));
    });
    result.mesh.cell_counts = [numeric(fields.cell_count, "선택 메시 분할 수")];
    result.input_provenance = { origin: fields.origin, reference: fields.reference }; return validate(result);
  }
  const api = Object.freeze({ validate, toFields, fromFields, fieldDefinitions });
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.coupledControls = api;
})(typeof window !== "undefined" ? window : globalThis);
