"use strict";

// Translate the human form into existing settings; the adapter owns final preflight.
(function (root) {
  const isotropic = ["elastic_modulus_MPa", "poisson_ratio"];
  const orthotropic = ["E_1_MPa", "E_2_MPa", "E_3_MPa", "nu_12", "nu_13", "nu_23", "G_12_MPa", "G_13_MPa", "G_23_MPa"];
  const stressOrder = ["SXX", "SYY", "SZZ", "SXY", "SYZ", "SZX"];
  const mapping = (value) => value && typeof value === "object" && !Array.isArray(value);
  const exactKeys = (value, names) => mapping(value) && Object.keys(value).sort().join(",") === [...names].sort().join(",");
  const finite = (value) => typeof value === "number" && Number.isFinite(value);
  const positive = (value) => finite(value) && value > 0;
  const nonempty = (value) => typeof value === "string" && value.trim().length > 0;
  function numberInput(value, name) {
    if (!nonempty(value) || !Number.isFinite(Number(value))) throw new Error(`${name}: 유한한 수치를 입력하세요.`);
    return Number(value);
  }
  function validate(settings) {
    if (!exactKeys(settings, ["load", "material", "mesh"]) ||
        !exactKeys(settings.load, ["force_per_support_N", "source"]) ||
        !positive(settings.load.force_per_support_N) || !nonempty(settings.load.source)) {
      throw new Error("양수인 지지부당 하중(N)과 출처를 입력하세요.");
    }
    const material = settings.material;
    if (!mapping(material) || !nonempty(material.provenance) || !nonempty(material.qualification)) {
      throw new Error("재료의 출처와 입력 데이터 상태를 입력하세요.");
    }
    if (material.model === "isotropic") {
      if (!positive(material.elastic_modulus_MPa) || material.elastic_modulus_MPa >= 1e7 ||
          !finite(material.poisson_ratio) || material.poisson_ratio < 0 || material.poisson_ratio >= 0.49) {
        throw new Error("등방성 E는 0~10⁷ MPa, ν는 0 이상 0.49 미만이어야 합니다.");
      }
    } else if (material.model === "orthotropic") {
      if (!nonempty(material.axes) || orthotropic.some((name) => !finite(material[name])) ||
          orthotropic.filter((name) => !name.startsWith("nu_")).some((name) => !positive(material[name]))) {
        throw new Error("직교 이방성의 축 설명과 유한한 9개 상수를 입력하세요. 탄성계수는 양수여야 합니다.");
      }
    } else throw new Error("등방성 또는 직교 이방성 재료를 선택하세요.");
    const sizes = settings.mesh?.max_sizes_mm;
    const selected = settings.mesh?.mode === "selected";
    if (!(exactKeys(settings.mesh, ["max_sizes_mm"]) || (selected && exactKeys(settings.mesh, ["mode", "max_sizes_mm"]))) ||
        !Array.isArray(sizes) || (selected ? sizes.length !== 1 : sizes.length < 2 || sizes.length > 8) ||
        sizes.some((size, index) => !positive(size) || (index > 0 && sizes[index - 1] <= size))) {
      throw new Error("선택 모드는 양수 크기 하나, 기존 비교 모드는 큰 값부터 서로 다른 양수 2~8개를 mm로 입력하세요.");
    }
    return settings;
  }
  function toFields(settings) {
    validate(settings);
    const result = { model: settings.material.model, force_N: String(settings.load.force_per_support_N),
      source: settings.load.source, provenance: settings.material.provenance,
      qualification: settings.material.qualification, axes: settings.material.axes ?? "",
      mesh_sizes: settings.mesh.max_sizes_mm.join(", "), mesh_mode: settings.mesh.mode === "selected" ? "selected" : "trend" };
    [...isotropic, ...orthotropic].forEach((name) => { result[name] = settings.material[name] === undefined ? "" : String(settings.material[name]); });
    return result;
  }
  function fromFields(fields, previous) {
    // Invalid JSON must be repaired there first; stale form values cannot overwrite it.
    validate(previous);
    const result = JSON.parse(JSON.stringify(previous));
    const material = result.material;
    material.model = fields.model; material.provenance = fields.provenance; material.qualification = fields.qualification;
    const selected = fields.model === "isotropic" ? isotropic : orthotropic;
    [...isotropic, ...orthotropic].filter((name) => !selected.includes(name)).forEach((name) => { delete material[name]; });
    selected.forEach((name) => { material[name] = numberInput(fields[name], name); });
    if (fields.model === "orthotropic") material.axes = fields.axes;
    else delete material.axes;
    result.load = { force_per_support_N: numberInput(fields.force_N, "지지부당 하중"), source: fields.source };
    if (!nonempty(fields.mesh_sizes)) throw new Error("메시 크기를 입력하세요.");
    const mode = fields.mesh_mode ?? (previous.mesh.mode === "selected" ? "selected" : "trend");
    if (!["selected", "trend"].includes(mode)) throw new Error("지원되는 메시 사용 방식을 선택하세요.");
    result.mesh = { ...(mode === "selected" ? { mode: "selected" } : {}),
      max_sizes_mm: fields.mesh_sizes.trim().split(/[\s,]+/).map((value) => numberInput(value, "메시 크기")) };
    return validate(result);
  }
  function verifyStressField(field, artifacts, path) {
    if (!mapping(field) || field.schema_version !== "1.0" || field.field !== "stress" ||
        field.representation !== "AVERAGED_NODAL" || field.unit !== "MPa" ||
        field.coordinate_frame !== "SOLVER_GLOBAL_CARTESIAN" || field.tensor_shear_components !== true ||
        field.engineering_valid !== false || field.qualification !== "UNKNOWN" ||
        JSON.stringify(field.component_order) !== JSON.stringify(stressOrder) ||
        !Array.isArray(field.nodes) || field.nodes.length < 1 || field.node_count !== field.nodes.length) {
      throw new Error("명시된 좌표·단위·유효성의 진단용 응력 field가 아닙니다.");
    }
    const source = field.source_frd;
    if (!mapping(source) || !nonempty(source.path) || /[\\/]/.test(source.path) || !/^[0-9a-f]{64}$/.test(source.sha256 ?? "")) {
      throw new Error("원본 FRD 연결이 없거나 잘못되었습니다.");
    }
    const sourcePath = path.slice(0, path.lastIndexOf("/") + 1) + source.path;
    const sources = artifacts.filter((item) => item.path === sourcePath);
    if (sources.length !== 1 || sources[0].sha256 !== source.sha256) throw new Error("응력 field와 같은 개정의 원본 FRD 해시가 일치하지 않습니다.");
    const seen = new Set();
    field.nodes.forEach((node) => {
      if (!mapping(node) || !Number.isSafeInteger(node.node_id) || node.node_id < 1 || seen.has(node.node_id) ||
          !Array.isArray(node.position_mm) || node.position_mm.length !== 3 || node.position_mm.some((value) => !finite(value)) ||
          !Array.isArray(node.stress_MPa) || node.stress_MPa.length !== 6 || node.stress_MPa.some((value) => !finite(value)) ||
          !finite(node.von_mises_MPa) || node.von_mises_MPa < 0) throw new Error("응력 절점의 식별자·좌표·성분이 불완전합니다.");
      seen.add(node.node_id);
    });
    return field;
  }
  const api = { validate, toFields, fromFields, verifyStressField };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.fixtureControls = api;
})(globalThis);
