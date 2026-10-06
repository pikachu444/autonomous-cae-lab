"use strict";

// Typed selected-mesh inputs only. Domain owns engineering/native admission;
// this form does not evaluate a reference, qualify material or choose a history.
(function (root) {
  const settingKeys = ["mode", "case", "dimensions_mm", "material", "history", "mesh_sizes_mm", "limits", "input_provenance"];
  const materialKeys = ["youngs_modulus_mpa", "poisson_ratio", "yield_stress_mpa", "plastic_modulus_mpa"];
  const limitKeys = ["displacement_relative", "displacement_absolute_mm", "stress_relative", "stress_absolute_mpa", "plastic_strain_absolute",
    "reaction_relative", "reaction_absolute_n", "mesh_agreement_relative", "plastic_dissipation_relative", "plastic_dissipation_absolute_mpa"];
  const fieldKeys = ["length_x", "length_y", "length_z", "youngs_modulus", "poisson_ratio", "yield_stress", "plastic_modulus", "mesh_size", "origin", "reference", "history"];
  const origins = ["ASSUMED", "MEASURED_REPORTED", "PUBLISHED_REFERENCE", "SYNTHETIC"];
  const decimal = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
  const keys = (value, expected) => object(value) && Object.keys(value).length === expected.length && expected.every(key => own(value, key));
  const finite = value => typeof value === "number" && Number.isFinite(value);
  const positive = value => finite(value) && value > 0;
  const numberText = value => Object.is(value, -0) ? "-0" : String(value);
  function demand(condition, message) { if (!condition) throw new Error(message); }
  function constructorName(prototype) {
    const constructor = prototype && Object.getOwnPropertyDescriptor(prototype, "constructor")?.value;
    return typeof constructor === "function" ? Object.getOwnPropertyDescriptor(constructor, "name")?.value : null;
  }
  function ordinaryObjectPrototype(prototype) {
    return prototype !== null && Object.getPrototypeOf(prototype) === null && constructorName(prototype) === "Object";
  }
  function json(value, ancestors = new Set()) {
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
    ancestors.add(value); const valid = names.every(key => json(value[key], ancestors)); ancestors.delete(value); return valid;
  }
  function clone(value) {
    if (Array.isArray(value)) return value.map(clone);
    if (object(value)) return Object.fromEntries(Object.keys(value).map(key => [key, clone(value[key])]));
    return value;
  }
  function validate(settings) {
    demand(json(settings) && keys(settings, settingKeys) && settings.mode === "selected_mesh" && settings.case === "uniaxial_j2_isotropic_hardening",
      "선택 메시의 uniaxial_j2_isotropic_hardening 입력만 이 폼에서 편집할 수 있습니다. 원 benchmark 입력은 보존합니다.");
    demand(Array.isArray(settings.dimensions_mm) && settings.dimensions_mm.length === 3 && settings.dimensions_mm.every(positive),
      "블록의 X·Y·Z 길이는 유한한 양수 mm 값으로 명시하세요.");
    const material = settings.material;
    demand(keys(material, materialKeys) && positive(material.youngs_modulus_mpa) && positive(material.yield_stress_mpa) && positive(material.plastic_modulus_mpa) &&
      finite(material.poisson_ratio) && material.poisson_ratio > -1 && material.poisson_ratio < 0.5,
      "E·초기 항복응력·H는 유한한 양수 MPa, ν는 -1<ν<0.5로 명시하세요. H는 d(항복응력)/d(등가소성변형률)입니다.");
    const history = settings.history;
    demand(keys(history, ["times_s", "axial_strain"]) && Array.isArray(history.times_s) && Array.isArray(history.axial_strain) &&
      history.times_s.length >= 2 && history.times_s.length <= 32 && history.axial_strain.length === history.times_s.length &&
      history.times_s.every(finite) && history.axial_strain.every(value => finite(value) && Math.abs(value) <= 0.01),
      "이력은 시간(s)·부호 있는 축변형률의 대응하는 2–32행이며, 변형률은 -0.01–0.01 범위여야 합니다.");
    demand(history.times_s[0] === 0 && history.axial_strain[0] === 0 && history.times_s.every((time, index) => index === 0 || history.times_s[index - 1] < time),
      "이력은 시간=0·변형률=0에서 시작하고 시간이 엄격히 증가해야 합니다. 유지·하중 제거·반전은 그대로 보존합니다.");
    demand(Array.isArray(settings.mesh_sizes_mm) && settings.mesh_sizes_mm.length === 1 && positive(settings.mesh_sizes_mm[0]) &&
      settings.dimensions_mm.every(length => settings.mesh_sizes_mm[0] <= length),
      "모든 블록 길이 이하인 유한한 양수 메시 크기(mm) 하나를 선택하세요.");
    demand(keys(settings.limits, limitKeys) && limitKeys.every(key => positive(settings.limits[key])),
      "보존된 10개 수치 한계값은 모두 유한한 양수여야 합니다. 이 폼은 참조·메시 수렴 판정을 만들지 않습니다.");
    const source = settings.input_provenance;
    demand(keys(source, ["origin", "reference"]) && origins.includes(source.origin) && typeof source.reference === "string" && source.reference.trim() &&
      source.reference.length <= 4000 && Array.from(source.reference).length <= 2000,
      "입력 출처 분류와 비어 있지 않은 2000자 이내 원문 근거를 명시하세요. 사용자 보고값은 물성 자격 판정이 아닙니다.");
    return clone(settings);
  }
  function numeric(value, label) {
    demand(typeof value === "string" && decimal.exec(value.trim())?.[0] === value.trim(), `${label}: 유한한 십진수 또는 지수 표기 숫자를 명시하세요.`);
    const result = Number(value);
    demand(Number.isFinite(result), `${label}: 유한한 숫자를 명시하세요.`);
    return result;
  }
  function parseHistory(value) {
    demand(typeof value === "string" && value.trim(), "시간(s)·축변형률 이력을 두 열로 입력하세요.");
    const rows = value.trim().split(/\r\n|\n|\r/);
    if (rows[0].trim() === "time_s,axial_strain") rows.shift();
    demand(rows.length >= 2 && rows.length <= 32, "이력에는 시간·축변형률의 대응하는 2–32행이 필요합니다. 헤더는 첫 행에 한 번만 허용합니다.");
    const history = { times_s: [], axial_strain: [] };
    rows.forEach((row, index) => {
      const columns = row.includes(",") ? row.split(",") : row.trim().split(/\s+/);
      demand(columns.length === 2, `이력 ${index + 1}행: 시간(s)과 축변형률 두 열을 쉼표 또는 공백으로 구분하세요.`);
      history.times_s.push(numeric(columns[0], `이력 ${index + 1}행 시간(s)`));
      history.axial_strain.push(numeric(columns[1], `이력 ${index + 1}행 축변형률`));
    });
    return history;
  }
  function toFields(settings) {
    const selected = validate(settings), material = selected.material;
    return { length_x: numberText(selected.dimensions_mm[0]), length_y: numberText(selected.dimensions_mm[1]), length_z: numberText(selected.dimensions_mm[2]),
      youngs_modulus: numberText(material.youngs_modulus_mpa), poisson_ratio: numberText(material.poisson_ratio),
      yield_stress: numberText(material.yield_stress_mpa), plastic_modulus: numberText(material.plastic_modulus_mpa), mesh_size: numberText(selected.mesh_sizes_mm[0]),
      origin: selected.input_provenance.origin, reference: selected.input_provenance.reference,
      history: "time_s,axial_strain\n" + selected.history.times_s.map((time, index) => `${numberText(time)},${numberText(selected.history.axial_strain[index])}`).join("\n") };
  }
  function fromFields(fields, settings) {
    const result = validate(settings);
    demand(json(fields) && keys(fields, fieldKeys), "현재 J2 폼의 11개 입력을 명시하세요. 보존된 수치 한계값을 폼 입력으로 덮어쓰지 않습니다.");
    result.dimensions_mm = [numeric(fields.length_x, "X 길이(mm)"), numeric(fields.length_y, "Y 길이(mm)"), numeric(fields.length_z, "Z 길이(mm)")];
    result.material = { youngs_modulus_mpa: numeric(fields.youngs_modulus, "E (MPa)"), poisson_ratio: numeric(fields.poisson_ratio, "ν"),
      yield_stress_mpa: numeric(fields.yield_stress, "초기 항복응력(MPa)"), plastic_modulus_mpa: numeric(fields.plastic_modulus, "H (MPa)") };
    result.mesh_sizes_mm = [numeric(fields.mesh_size, "선택 메시 크기(mm)")];
    result.input_provenance = { origin: fields.origin, reference: fields.reference };
    result.history = parseHistory(fields.history);
    return validate(result);
  }
  const api = Object.freeze({ validate, toFields, fromFields });
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.plasticityControls = api;
})(typeof window !== "undefined" ? window : globalThis);
