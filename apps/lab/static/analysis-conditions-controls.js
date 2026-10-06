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
  const vector = value => Array.isArray(value) && value.length === 3 && value.every(item => typeof item === "number" && Number.isFinite(item));
  function nativeFace(item, selections) {
    return nonempty(item.native_object, 512) && /^Face[1-9]\d*$/.test(item.native_name) &&
      validId(item.body_id) && selections.some(body => body.id === item.body_id && body.kind === "whole_final_solid") &&
      typeof item.area_mm2 === "number" && Number.isFinite(item.area_mm2) && item.area_mm2 > 0 &&
      vector(item.center_mm) && vector(item.bounds_mm?.min) && vector(item.bounds_mm?.max) &&
      item.bounds_mm.min.every((value, axis) => value <= item.bounds_mm.max[axis]) &&
      nonempty(item.surface_type, 128) && item.unit === "mm" && item.coordinate_system === "global" &&
      item.native_coordinate_system === "cad_document_global" && validDigest(item.geometry_sha256) &&
      (!own(item, "planar_normal_global") || vector(item.planar_normal_global)) &&
      item.roles.every(role => ["boundary", "load"].includes(role));
  }
  function assemblyGeometry(item) {
    return vector(item.center_mm) && vector(item.bounds_mm?.min_mm) && vector(item.bounds_mm?.max_mm) &&
      vector(item.bounds_mm?.size_mm) && item.bounds_mm.min_mm.every((value, axis) => value <= item.bounds_mm.max_mm[axis]) &&
      item.bounds_mm.size_mm.every(value => value >= 0) && item.coordinate_system === "global" &&
      item.native_coordinate_system === "global_assembly_cartesian_mm";
  }
  function assemblyBody(item) {
    return validId(item.component_id) && item.id === `B-${item.component_id}` && assemblyGeometry(item) &&
      typeof item.volume_mm3 === "number" && Number.isFinite(item.volume_mm3) && item.volume_mm3 > 0 &&
      item.roles.length === 1 && item.roles[0] === "material";
  }
  function assemblyFace(item, selections) {
    const rawPrefix = `${item.component_id}:face:${item.native_ordinal}:`;
    return validId(item.component_id) && Number.isSafeInteger(item.native_ordinal) && item.native_ordinal >= 0 &&
      item.id === `S-${item.component_id}-${item.native_ordinal}` && nonempty(item.catalog_face_id, 256) &&
      item.catalog_face_id.startsWith(rawPrefix) && validDigest(item.catalog_face_id.slice(rawPrefix.length)) &&
      validDigest(item.native_geometry_sha256) && (!own(item, "local_ordinal") || item.local_ordinal === item.native_ordinal) &&
      selections.some(body => body.kind === "native_assembly_body" && body.component_id === item.component_id) &&
      assemblyGeometry(item) && typeof item.area_mm2 === "number" && Number.isFinite(item.area_mm2) && item.area_mm2 > 0 &&
      item.roles.every(role => ["boundary", "load", "contact"].includes(role));
  }
  function assemblyInterior(item, data) {
    const fullId = `S-${item.component_id}-${item.native_ordinal}`, mesh = data.catalog.retained_mesh;
    const full = data.catalog.selections.find(face => face.kind === "native_assembly_face" && face.id === fullId);
    const geometryKeys = ["component_id", "catalog_face_id", "native_ordinal", "local_ordinal", "native_geometry_sha256", "coordinate_system", "native_coordinate_system", "area_mm2", "center_mm", "bounds_mm", "geom_type", "orientation"];
    return item.id === `I-${item.component_id}-${item.native_ordinal}` &&
      item.node_scope === "FACE_INTERIOR_EXCLUDING_OTHER_FACE_BOUNDARIES" && item.roles.length === 2 && item.roles.every(role => ["boundary", "load"].includes(role)) &&
      (!own(item, "geometry_metadata_scope") || item.geometry_metadata_scope === "ORIGINAL_SOURCE_FACE_NOT_SUBSET") &&
      (!own(item, "cad_revision") || item.cad_revision === data.source.cad_revision) &&
      full && (!own(full, "cad_revision") || full.cad_revision === data.source.cad_revision) &&
      (!own(data.catalog, "cad_revision") || data.catalog.cad_revision === data.source.cad_revision) &&
      assemblyFace({ ...item, id: fullId }, data.catalog.selections) &&
      geometryKeys.every(key => stable(item[key]) === stable(full[key])) &&
      mesh?.profile === "coarse3" && validDigest(mesh.mesh_revision) && mesh.cad_revision === data.source.cad_revision &&
      Array.isArray(mesh.active_components) && mesh.active_components.length > 0 && mesh.active_components.length <= 64 &&
      mesh.active_components.every(validId) && new Set(mesh.active_components).size === mesh.active_components.length &&
      mesh.active_components.includes(item.component_id);
  }
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
          item.roles.some(role => !(item.kind === "native_assembly_face" ? ["boundary", "load", "contact"] : ["material", "boundary", "load"]).includes(role)) || new Set(item.roles).size !== item.roles.length ||
          (item.kind === "native_face" && !nativeFace(item, selections)) ||
          (item.kind === "native_assembly_body" && !assemblyBody(item)) ||
          (item.kind === "native_assembly_face" && !assemblyFace(item, selections)) ||
          (item.kind === "assembly_face_interior_nodes" && !assemblyInterior(item, data))) ||
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
  function selectionLabel(item) {
    const display = value => value.toLocaleString("ko-KR", { maximumSignificantDigits: 8 });
    if (item.kind === "native_assembly_body") return `${item.label} · 부품 ${item.component_id} · ${item.id} · ${display(item.volume_mm3)} mm³`;
    if (item.kind === "assembly_face_interior_nodes") return `${item.label} · 면 내부 절점·모서리 제외 · ${item.id} · 원 면 ${item.catalog_face_id} · 원 면적 ${display(item.area_mm2)} mm² · 원 중심 (${item.center_mm.map(display).join(", ")}) mm`;
    if (item.kind === "native_assembly_face") return `${item.label} · ${item.id} · 원 면 ${item.catalog_face_id} · ${display(item.area_mm2)} mm² · 중심 (${item.center_mm.map(display).join(", ")}) mm`;
    if (item.kind !== "native_face") return `${item.label} · ${item.kind}`;
    return `${item.label} · ${item.native_object}/${item.native_name} · ${item.area_mm2.toLocaleString("ko-KR", { maximumSignificantDigits: 8 })} mm² · 중심 (${item.center_mm.map(value => value.toLocaleString("ko-KR", { maximumSignificantDigits: 8 })).join(", ")}) mm`;
  }
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
  function displacement(fields) {
    const components = {};
    for (const axis of ["x", "y", "z"]) {
      const enabled = fields[`u${axis}Enabled`];
      if (enabled !== undefined && typeof enabled !== "boolean") throw new Error("변위 구속 성분의 지정 여부를 확인하세요.");
      if (enabled !== false) components[`U${axis.toUpperCase()}`] = numeric(fields, `u${axis}`, `U${axis.toUpperCase()} (mm)`);
    }
    if (!Object.keys(components).length) throw new Error("변위 구속 성분을 하나 이상 명시하세요. 미지정 성분은 0으로 바꾸지 않습니다.");
    return components;
  }
  function boundary(data, fields, id = "BC1") {
    return { id, selection_id: selection(data, fields, "boundarySelection", "boundary"), type: "displacement",
      components: displacement(fields), unit: fields.lengthUnit, coordinate_system: fields.coordinateSystem,
      source: required(fields, "boundarySource", "구속의 출처·가정") };
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
    const additional = fields.additionalBoundaries ?? [];
    if (!Array.isArray(additional) || additional.length > 127 || additional.some(item => !object(item) || !validId(item.id) || item.id === "BC1") ||
        new Set(additional.map(item => item.id)).size !== additional.length) throw new Error("추가 구속 행의 고유 ID와 목록을 확인하세요.");
    const boundaries = [boundary(data, fields), ...additional.map(item => boundary(data, { ...fields,
      boundarySelection: item.selectionId, ux: item.ux, uy: item.uy, uz: item.uz,
      uxEnabled: item.uxEnabled, uyEnabled: item.uyEnabled, uzEnabled: item.uzEnabled, boundarySource: item.source }, item.id))];
    const declaration = { analysis_type: "linear_static", units: { length: fields.lengthUnit, force: fields.forceUnit, stress: fields.stressUnit },
      coordinate_system: fields.coordinateSystem,
      materials: [{ id: "M1", selection_id: selection(data, fields, "materialSelection", "material"), law: fields.materialLaw,
        young_modulus_MPa: numeric(fields, "youngModulus", "E (MPa)"), poisson_ratio: numeric(fields, "poissonRatio", "ν"),
        source: { category: fields.materialCategory, description: required(fields, "materialSource", "재료 값의 출처") } }],
      boundary_conditions: boundaries,
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
    if (value.analysis_type !== "linear_static" || value.materials?.length !== 1 || !Array.isArray(value.boundary_conditions) || value.boundary_conditions.length < 1 || value.boundary_conditions.length > 128 || value.loads?.length !== 1 ||
        material?.id !== "M1" || boundary?.id !== "BC1" || load?.id !== "L1" || boundary?.type !== "displacement" || load?.type !== "resultant_force" ||
        value.mesh?.mode !== "selected" || value.contact?.mode !== "none" || own(value.contact, "pairs") ||
        !object(boundary?.components) || Object.keys(boundary.components).length < 1 || Object.keys(boundary.components).some(key => !["UX", "UY", "UZ"].includes(key)) ||
        stable(Object.keys(load?.components ?? {}).sort()) !== stable(["FX", "FY", "FZ"])) {
      throw new Error("원 조건을 보존했습니다. 현재 폼이 표현할 수 없는 여러 대상·법칙·접촉 입력은 자동으로 바꾸거나 실행하지 않습니다.");
    }
    const fields = { conditionsId: record.id, backend: record.request.backend, materialSelection: material.selection_id,
      boundarySelection: boundary.selection_id, loadSelection: load.selection_id, materialLaw: material.law,
      materialCategory: material.source?.category, materialSource: material.source?.description,
      youngModulus: String(material.young_modulus_MPa), poissonRatio: String(material.poisson_ratio),
      coordinateSystem: value.coordinate_system, lengthUnit: value.units?.length, forceUnit: value.units?.force, stressUnit: value.units?.stress,
      ux: own(boundary.components, "UX") ? String(boundary.components.UX) : "", uy: own(boundary.components, "UY") ? String(boundary.components.UY) : "", uz: own(boundary.components, "UZ") ? String(boundary.components.UZ) : "", boundarySource: boundary.source,
      fx: String(load.components.FX), fy: String(load.components.FY), fz: String(load.components.FZ), loadSource: load.source,
      contactMode: value.contact.mode, contactSource: value.contact.source, meshSize: String(value.mesh.max_size_mm) };
    if (Object.keys(boundary.components).length !== 3) {
      for (const axis of ["x", "y", "z"]) fields[`u${axis}Enabled`] = own(boundary.components, `U${axis.toUpperCase()}`);
    }
    if (value.boundary_conditions.length > 1) fields.additionalBoundaries = value.boundary_conditions.slice(1).map(item => {
      if (!object(item.components) || Object.keys(item.components).length < 1 || Object.keys(item.components).some(key => !["UX", "UY", "UZ"].includes(key)) ||
          item.type !== "displacement" || item.unit !== fields.lengthUnit || item.coordinate_system !== fields.coordinateSystem) {
        throw new Error("추가 구속의 성분·좌표계·단위를 현재 폼으로 정확히 재현할 수 없습니다.");
      }
      const row = { id: item.id, selectionId: item.selection_id, source: item.source };
      for (const axis of ["x", "y", "z"]) {
        const key = `U${axis.toUpperCase()}`; row[`u${axis}`] = own(item.components, key) ? String(item.components[key]) : "";
        row[`u${axis}Enabled`] = own(item.components, key);
      }
      return row;
    });
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
  const api = { parents, catalog, choices, selectionLabel, sameSource, buildSave, saved, fromRecord, buildRun };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.analysisConditionsControls = api;
})(typeof window !== "undefined" ? window : globalThis);
