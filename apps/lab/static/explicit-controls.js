"use strict";

// Typed selected histories for the existing reduced rigid flight/stop topology.
// Acceleration declares a piecewise-linear global-Z body load in m/s^2, not a
// prescribed kinematic response. Domain owns native admission and qualification.
(function (root) {
  const flight = "rigid_cube_freefall", compliant = "rigid_cube_compliant_stop";
  const numericKeys = ["edge_m", "mass_kg", "center_height_m", "initial_velocity_m_s", "end_time_s", "time_step_s", "history_interval_s"];
  const settingKeys = ["mode", "case", ...numericKeys, "limits", "acceleration_history", "input_provenance"];
  const fieldKeys = [...numericKeys, "origin", "reference", "history"];
  const origins = ["ASSUMED", "MEASURED_REPORTED", "PUBLISHED_REFERENCE", "SYNTHETIC"];
  const decimal = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
  const keys = (value, expected) => object(value) && Object.keys(value).length === expected.length && expected.every(key => own(value, key));
  const finite = value => typeof value === "number" && Number.isFinite(value);
  const between = (value, low, high) => finite(value) && value >= low && value <= high;
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
    if (object(value)) return Object.fromEntries(Object.keys(value).map(key => [key, clone(value[key])]));
    return value;
  }
  function validate(settings) {
    demand(json(settings), "입력에는 자체 유한한 JSON 값만 허용합니다. 실행 가능한 속성·위험 키·순환·변형된 prototype은 사용할 수 없습니다.");
    const spring = settings?.case === compliant;
    demand(keys(settings, spring ? [...settingKeys, "spring_stiffness_n_m", "spring_mass_kg"] : settingKeys) &&
      settings.mode === "selected_history" && [flight, compliant].includes(settings.case),
    "selected_history의 기존 rigid_cube_freefall 또는 rigid_cube_compliant_stop 입력을 선택하세요. 원 benchmark나 다른 표면·변형 모델을 자동 변환하지 않습니다.");
    demand(between(settings.edge_m, .001, 1) && between(settings.mass_kg, .001, 100) && finite(settings.center_height_m) &&
      settings.center_height_m > settings.edge_m / 2 && settings.center_height_m <= 10,
    "모서리 길이 0.001–1 m·질량 0.001–100 kg·초기 중심 높이(모서리/2 초과, 10 m 이하)를 명시하세요.");
    demand(between(settings.initial_velocity_m_s, -10, 10) && between(settings.end_time_s, .001, 2) &&
      between(settings.time_step_s, 1e-6, 1e-3) && between(settings.history_interval_s, settings.time_step_s, .01),
    "초기 global Z 속도 -10–10 m/s·종료 시간 0.001–2 s·시간 간격 1e-6–1e-3 s·이력 간격(dt 이상, 0.01 s 이하)을 명시하세요.");
    const cycles = settings.end_time_s / settings.time_step_s, intervals = settings.end_time_s / settings.history_interval_s;
    demand(cycles <= 200000 && intervals >= 10 && intervals < 20000,
      "200000 cycle 이하, 10 이상·20000 미만의 이력 간격으로 기존 실행·파싱 예산을 지키세요.");
    demand(Math.abs(cycles - Math.round(cycles)) <= 1e-8,
      "종료 시간은 명시한 시간 간격의 정수 cycle이어야 합니다. 이력 출력의 실제 시각은 native reader가 확인합니다.");
    const history = settings.acceleration_history;
    demand(keys(history, ["time_s", "acceleration_z_m_s2"]) && Array.isArray(history.time_s) && Array.isArray(history.acceleration_z_m_s2) &&
      history.time_s.length >= 2 && history.time_s.length <= 16 && history.acceleration_z_m_s2.length === history.time_s.length &&
      history.time_s.every(finite) && history.acceleration_z_m_s2.every(value => between(value, -100, 100)),
    "가속도 이력은 시간(s)·global Z 가속도(m/s²)의 대응하는 2–16행이며, 부호 있는 가속도는 -100–100 m/s² 범위여야 합니다.");
    demand(history.time_s[0] === 0 && history.time_s[history.time_s.length - 1] === settings.end_time_s &&
      history.time_s.every((time, index) => index === 0 || time > history.time_s[index - 1]),
    "가속도 이력은 시간 0에서 시작하고 엄격히 증가하여 선언한 종료 시간과 정확히 같게 끝나야 합니다. native 하중 법칙은 행 사이를 선형 연결합니다.");
    demand(keys(settings.limits, ["mass_relative"]) && settings.limits.mass_relative === 1e-8,
      "보존된 selected_history 질량 상대 한계 1e-8을 유지하세요. benchmark 참조 오차·충돌 판정을 이 입력에 대입하지 않습니다.");
    if (spring) demand(between(settings.spring_stiffness_n_m, 1000, 1e6) && settings.spring_mass_kg === .002 &&
      settings.history_interval_s === settings.time_step_s,
    "기존 compliant 모델은 강성 1000–1e6 N/m·고정 스프링 질량 0.002 kg·이력 간격=dt를 유지합니다.");
    const source = settings.input_provenance;
    demand(keys(source, ["origin", "reference"]) && origins.includes(source.origin) && typeof source.reference === "string" && source.reference.trim() &&
      source.reference.length <= 4000 && Array.from(source.reference).length <= 2000,
    "입력 출처 분류와 비어 있지 않은 2000자 이내 원문 근거를 명시하세요. 사용자 보고값은 물리 자격 판정이 아닙니다.");
    return clone(settings);
  }
  function numeric(value, label) {
    demand(typeof value === "string" && decimal.exec(value.trim())?.[0] === value.trim(), `${label}: 유한한 십진수 또는 지수 표기 숫자를 명시하세요.`);
    const result = Number(value);
    demand(Number.isFinite(result), `${label}: 유한한 숫자를 명시하세요.`);
    return result;
  }
  function parseHistory(value) {
    demand(typeof value === "string" && value.trim(), "시간(s)·global Z 가속도(m/s²) 이력을 두 열로 입력하세요.");
    const rows = value.trim().split(/\r\n|\n|\r/);
    if (rows[0].trim() === "time_s,acceleration_z_m_s2") rows.shift();
    demand(rows.length >= 2 && rows.length <= 16, "이력에는 대응하는 2–16행이 필요합니다. 헤더는 첫 행에 한 번만 허용합니다.");
    const history = { time_s: [], acceleration_z_m_s2: [] };
    rows.forEach((row, index) => {
      const columns = row.includes(",") ? row.split(",") : row.trim().split(/\s+/);
      demand(columns.length === 2, `이력 ${index + 1}행: 시간(s)과 가속도(m/s²) 두 열을 쉼표 또는 공백으로 구분하세요.`);
      history.time_s.push(numeric(columns[0], `이력 ${index + 1}행 시간(s)`));
      history.acceleration_z_m_s2.push(numeric(columns[1], `이력 ${index + 1}행 global Z 가속도(m/s²)`));
    });
    return history;
  }
  function toFields(settings) {
    const selected = validate(settings);
    return { ...Object.fromEntries(numericKeys.map(key => [key, numberText(selected[key])])),
      ...(selected.case === compliant ? { spring_stiffness_n_m: numberText(selected.spring_stiffness_n_m) } : {}),
      origin: selected.input_provenance.origin, reference: selected.input_provenance.reference,
      history: "time_s,acceleration_z_m_s2\n" + selected.acceleration_history.time_s.map((time, index) =>
        `${numberText(time)},${numberText(selected.acceleration_history.acceleration_z_m_s2[index])}`).join("\n") };
  }
  function fromFields(fields, settings) {
    const result = validate(settings), spring = result.case === compliant;
    demand(json(fields) && keys(fields, spring ? [...fieldKeys, "spring_stiffness_n_m"] : fieldKeys),
      "현재 selected_history 폼의 명시한 문자열 입력만 사용하세요. 모드·모델·고정 질량·보존 한계·단위는 폼에서 바꾸지 않습니다.");
    for (const key of numericKeys) result[key] = numeric(fields[key], key);
    if (spring) result.spring_stiffness_n_m = numeric(fields.spring_stiffness_n_m, "스프링 강성(N/m)");
    result.acceleration_history = parseHistory(fields.history);
    result.input_provenance = { origin: fields.origin, reference: fields.reference };
    return validate(result);
  }
  const api = Object.freeze({ validate, toFields, fromFields });
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.explicitControls = api;
})(typeof window !== "undefined" ? window : globalThis);
