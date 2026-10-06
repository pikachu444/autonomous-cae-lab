"use strict";

// Human declarations only. Core checks the saved CAD identities; Domain and
// adapters decide declared-input support and own native region/solver syntax.
(function (root) {
  const identifier = /^[A-Za-z][A-Za-z0-9_-]{0,79}$/;
  const digest = /^[a-f0-9]{64}$/;
  const decimal = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
  const backendName = /^[A-Za-z][A-Za-z0-9_.-]{0,127}$/;
  const sourceKeys = ["experiment_id", "study_id", "cad_revision", "backend", "result_sha256", "proposal_sha256", "thread_sha256"];
  const supportStatuses = ["SUPPORTED_DECLARED_INPUTS", "UNSUPPORTED_FOR_MODEL", "UNSUPPORTED_FOR_CONDITIONS", "UNAVAILABLE"];
  const sourceCategories = ["ASSUMED", "MEASURED_REPORTED", "PUBLISHED_REFERENCE"];
  const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  const nonempty = (value, maximum = 2000) => typeof value === "string" && value.trim().length > 0 && value.length <= maximum;
  const validId = value => typeof value === "string" && identifier.exec(value)?.[0] === value;
  const validDigest = value => typeof value === "string" && digest.exec(value)?.[0] === value;
  const validBackend = value => typeof value === "string" && backendName.exec(value)?.[0] === value;
  function stable(value) {
    if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`;
    if (object(value)) return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${stable(value[key])}`).join(",")}}`;
    return JSON.stringify(value);
  }
  function json(value, ancestors = new Set()) {
    if (value === null || ["string", "boolean"].includes(typeof value)) return true;
    if (typeof value === "number") return Number.isFinite(value);
    if ((!Array.isArray(value) && !object(value)) || ancestors.has(value)) return false;
    const keys = Reflect.ownKeys(value).filter(key => !(Array.isArray(value) && key === "length"));
    if (keys.some(key => {
      const property = Object.getOwnPropertyDescriptor(value, key);
      return typeof key !== "string" || ["__proto__", "prototype", "constructor"].includes(key) || !property.enumerable || !own(property, "value");
    }) || (Array.isArray(value) && (keys.length !== value.length || keys.some((key, index) => key !== String(index))))) return false;
    ancestors.add(value); const valid = keys.every(key => json(value[key], ancestors)); ancestors.delete(value); return valid;
  }
  function checkedSource(source) {
    if (!object(source) || !json(source) || !validId(source.experiment_id) || !validId(source.study_id) ||
        !validDigest(source.cad_revision) || !validBackend(source.backend) ||
        !["result_sha256", "proposal_sha256", "thread_sha256"].every(key => validDigest(source[key]))) {
      throw new Error("CAD 실험·연구·개정과 원본 해시를 확인할 수 없습니다. 같은 저장소의 catalog를 다시 불러오세요.");
    }
    return source;
  }
  function sameSource(left, right) { return sourceKeys.every(key => left?.[key] === right?.[key]); }
  function parents(records, studyId) {
    if (!Array.isArray(records) || !validId(studyId)) return [];
    return records.filter(record => validId(record?.id) && record.study_id === studyId &&
      record.status === "COMPLETED_REVIEW_REQUIRED" && record.solver_status === "NOT_RUN" &&
      validBackend(record.backend) && validDigest(record.cad_revision));
  }
  function catalog(data, expected = {}) {
    if (!object(data) || !json(data)) throw new Error("개정에 연결된 조건 catalog 응답을 확인할 수 없습니다.");
    const source = checkedSource(data.source), selections = data.catalog?.selections, frames = data.catalog?.coordinate_systems;
    if ((expected.experimentId && source.experiment_id !== expected.experimentId) ||
        (expected.studyId && source.study_id !== expected.studyId) ||
        (expected.cadRevision && source.cad_revision !== expected.cadRevision) ||
        (expected.backend && source.backend !== expected.backend)) throw new Error("선택한 CAD 실험·연구·개정과 catalog의 원본이 다릅니다.");
    if (data.catalog?.schema_version !== "1.0" || !validDigest(data.catalog_revision) ||
        !Array.isArray(selections) || selections.length < 1 || selections.length > 2048 ||
        selections.some(item => !validId(item?.id) || !nonempty(item.label, 512) || !nonempty(item.kind, 128) ||
          !Array.isArray(item.roles) || item.roles.length < 1 || item.roles.length > 3 ||
          item.roles.some(role => !["material", "boundary", "load"].includes(role)) || new Set(item.roles).size !== item.roles.length) ||
        new Set(selections.map(item => item.id)).size !== selections.length ||
        !Array.isArray(frames) || frames.length < 1 || frames.length > 32 ||
        frames.filter(frame => frame?.id === "global").length !== 1 ||
        !frames.some(frame => frame?.id === "global" && nonempty(frame.label, 512) && frame.type === "cartesian" && frame.unit === "mm" &&
          stable(frame.basis) === stable([[1, 0, 0], [0, 1, 0], [0, 0, 1]]) && stable(frame.origin) === stable([0, 0, 0])) ||
        !Array.isArray(data.catalog.limitations) || data.catalog.limitations.length > 64 ||
        data.catalog.limitations.some(item => !nonempty(item, 4000)) ||
        !Array.isArray(data.backends) || data.backends.length > 32 ||
        data.backends.some(item => !validBackend(item?.backend) || !nonempty(item.label, 512) || !nonempty(item.scope, 4000)) ||
        new Set(data.backends.map(item => item.backend)).size !== data.backends.length) {
      throw new Error("선택 ID·역할·명시적 global 좌표계·단위와 서버 지원 목록을 확인할 수 없습니다.");
    }
    return data;
  }
  function choices(data, role) { return data.catalog.selections.filter(item => item.roles.includes(role)); }
  function required(fields, key, label, maximum = 2000) {
    const value = fields[key];
    if (!nonempty(value, maximum)) throw new Error(`${label}을(를) 비어 있지 않은 ${maximum}자 이내로 입력하세요.`);
    return value.trim();
  }
  function numeric(fields, key, label) {
    const value = fields[key];
    if (typeof value !== "string" || !value.trim() || decimal.exec(value.trim())?.[0] !== value.trim() || !Number.isFinite(Number(value))) {
      throw new Error(`${label}에 유한한 숫자를 명시하세요.`);
    }
    return Number(value);
  }
  function selection(data, fields, key, role) {
    const selected = choices(data, role).find(item => item.id === fields[key]);
    if (!selected) throw new Error("이 CAD 개정의 catalog에 실제로 제공된 재료·구속·하중 대상을 선택하세요.");
    return selected.id;
  }
  function buildSave(data, fields) {
    catalog(data);
    if (!object(fields) || !json(fields) || !validId(fields.conditionsId)) throw new Error("새 조건 ID와 명시적 입력을 확인하세요.");
    if (!data.backends.some(item => item.backend === fields.backend)) throw new Error("서버가 catalog에 제공한 해석 경로를 선택하세요. 설치 여부는 별도입니다.");
    if (fields.coordinateSystem !== "global" || fields.lengthUnit !== "mm" || fields.forceUnit !== "N" || fields.stressUnit !== "MPa") {
      throw new Error("현재 폼은 명시한 global 좌표계와 mm·N·MPa 단위를 지원합니다. 다른 축·단위는 변환하지 않습니다.");
    }
    if (fields.materialLaw !== "isotropic_linear_elastic" || !sourceCategories.includes(fields.materialCategory) || fields.contactMode !== "none") {
      throw new Error("재료 법칙·출처와 명시적 접촉 없음 조건을 확인하세요. 다른 법칙·접촉은 이 폼에서 지원되지 않습니다.");
    }
    const declaration = { analysis_type: "linear_static", units: { length: fields.lengthUnit, force: fields.forceUnit, stress: fields.stressUnit },
      coordinate_system: fields.coordinateSystem,
      materials: [{ id: "M1", selection_id: selection(data, fields, "materialSelection", "material"), law: fields.materialLaw,
        young_modulus_MPa: numeric(fields, "youngModulus", "E (MPa)"), poisson_ratio: numeric(fields, "poissonRatio", "ν"),
        source: { category: fields.materialCategory, description: required(fields, "materialSource", "재료 값의 출처") } }],
      boundary_conditions: [{ id: "BC1", selection_id: selection(data, fields, "boundarySelection", "boundary"), type: "displacement",
        components: { UX: numeric(fields, "ux", "UX (mm)"), UY: numeric(fields, "uy", "UY (mm)"), UZ: numeric(fields, "uz", "UZ (mm)") },
        unit: fields.lengthUnit, coordinate_system: fields.coordinateSystem, source: required(fields, "boundarySource", "구속의 출처·가정") }],
      loads: [{ id: "L1", selection_id: selection(data, fields, "loadSelection", "load"), type: "resultant_force",
        components: { FX: numeric(fields, "fx", "FX (N)"), FY: numeric(fields, "fy", "FY (N)"), FZ: numeric(fields, "fz", "FZ (N)") },
        unit: fields.forceUnit, coordinate_system: fields.coordinateSystem, source: required(fields, "loadSource", "하중의 출처·가정") }],
      contact: { mode: fields.contactMode, source: required(fields, "contactSource", "접촉 모델의 출처·가정") },
      mesh: { mode: "selected", max_size_mm: numeric(fields, "meshSize", "선택 메시 크기 (mm)") } };
    return { conditions_id: fields.conditionsId, experiment_id: data.source.experiment_id, cad_revision: data.source.cad_revision,
      catalog_revision: data.catalog_revision, backend: fields.backend, declaration };
  }
  function saved(payload, data, expectedRequest) {
    catalog(data);
    const record = payload?.record;
    if (payload?.integrity !== "VERIFIED" || !object(record) || !json(record) || record.schema_version !== "1.0" ||
        !validId(record.id) || !nonempty(record.created_utc, 128) || !validDigest(record.conditions_revision) ||
        !sameSource(checkedSource(record.source), data.source) || record.catalog_revision !== data.catalog_revision ||
        stable(record.catalog) !== stable(data.catalog) || record.request?.conditions_id !== record.id ||
        record.request?.experiment_id !== data.source.experiment_id || record.request?.cad_revision !== data.source.cad_revision ||
        record.request?.catalog_revision !== data.catalog_revision || !data.backends.some(item => item.backend === record.request?.backend) ||
        !object(record.request?.declaration) || (expectedRequest && stable(record.request) !== stable(expectedRequest)) || !supportStatuses.includes(record.support?.status) ||
        record.support.native_runtime !== "NOT_CHECKED" || !Array.isArray(record.support.reasons) || record.support.reasons.length > 64 ||
        record.support.reasons.some(reason => !nonempty(reason, 4000)) || record.engineering !== "UNKNOWN" || record.decision !== "NOT_RELEASED" ||
        (record.support.status === "SUPPORTED_DECLARED_INPUTS" ?
          (!object(record.adapter_binding) || record.adapter_binding.backend !== record.request.backend || !nonempty(record.adapter_binding.version, 128)) :
          record.adapter_binding !== null)) {
      throw new Error("저장 조건의 원본·개정·입력 연결과 서버 판정을 확인할 수 없습니다. 새 해석을 실행하지 않습니다.");
    }
    return record;
  }
  function fromRecord(record, data) {
    const value = record.request.declaration, material = value.materials?.[0], boundary = value.boundary_conditions?.[0], load = value.loads?.[0];
    if (value.analysis_type !== "linear_static" || value.materials?.length !== 1 || value.boundary_conditions?.length !== 1 || value.loads?.length !== 1 ||
        material?.id !== "M1" || boundary?.id !== "BC1" || load?.id !== "L1" || boundary?.type !== "displacement" || load?.type !== "resultant_force" ||
        value.mesh?.mode !== "selected" || value.contact?.mode !== "none" || own(value.contact, "pairs") ||
        stable(Object.keys(boundary?.components ?? {}).sort()) !== stable(["UX", "UY", "UZ"]) ||
        stable(Object.keys(load?.components ?? {}).sort()) !== stable(["FX", "FY", "FZ"])) {
      throw new Error("원 조건을 보존했습니다. 현재 폼이 표현할 수 없는 여러 대상·법칙·접촉 입력은 자동으로 바꾸거나 실행하지 않습니다.");
    }
    const fields = { conditionsId: record.id, backend: record.request.backend, materialSelection: material.selection_id,
      boundarySelection: boundary.selection_id, loadSelection: load.selection_id, materialLaw: material.law,
      materialCategory: material.source?.category, materialSource: material.source?.description,
      youngModulus: String(material.young_modulus_MPa), poissonRatio: String(material.poisson_ratio),
      coordinateSystem: value.coordinate_system, lengthUnit: value.units?.length, forceUnit: value.units?.force, stressUnit: value.units?.stress,
      ux: String(boundary.components.UX), uy: String(boundary.components.UY), uz: String(boundary.components.UZ), boundarySource: boundary.source,
      fx: String(load.components.FX), fy: String(load.components.FY), fz: String(load.components.FZ), loadSource: load.source,
      contactMode: value.contact.mode, contactSource: value.contact.source, meshSize: String(value.mesh.max_size_mm) };
    if (boundary.unit !== fields.lengthUnit || load.unit !== fields.forceUnit ||
        boundary.coordinate_system !== fields.coordinateSystem || load.coordinate_system !== fields.coordinateSystem ||
        stable(buildSave(data, fields)) !== stable(record.request)) {
      throw new Error("현재 폼으로 원 조건을 정확히 재현할 수 없습니다. 보존된 입력을 단순화해 실행하지 않습니다.");
    }
    return fields;
  }
  function buildRun(record, data, fields, experimentId) {
    saved({ record, integrity: "VERIFIED" }, data);
    if (record.support.status !== "SUPPORTED_DECLARED_INPUTS") throw new Error("서버가 이 CAD·조건의 선언 입력을 지원하지 않습니다. 지원 판정과 사유를 확인하세요.");
    if (stable(buildSave(data, fields)) !== stable(record.request)) throw new Error("저장 후 입력이 변경됐습니다. 새 조건 ID로 저장한 뒤 실행하세요.");
    if (!validId(experimentId)) throw new Error("새 해석 실험 ID를 입력하세요.");
    return { parent_experiment_id: record.source.experiment_id, experiment_id: experimentId, backend: record.request.backend, conditions_id: record.id };
  }
  const api = { parents, catalog, choices, sameSource, buildSave, saved, fromRecord, buildRun };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.analysisConditionsControls = api;
})(typeof window !== "undefined" ? window : globalThis);
