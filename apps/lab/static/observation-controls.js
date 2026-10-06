"use strict";

// Numeric comparison inputs only. Core checks persisted identities and declared
// bindings; scalar/field selections do not verify physical alignment or release.
(function (root) {
  const presentation = typeof module !== "undefined" && module.exports ? require("./result-presentation.js") : null;
  const storeId = /^[A-Za-z][A-Za-z0-9_-]{0,79}$/;
  const decimal = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
  const sha256 = /^[0-9a-f]{64}$/;
  const purposes = ["GENERAL_CAE_RESEARCH", "DEFECT_REPRODUCTION", "JIG_FEASIBILITY"];
  const dangerous = new Set(["__proto__", "prototype", "constructor"]);
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  const mapping = (value) => value !== null && typeof value === "object" &&
    (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null);
  const nonempty = (value) => typeof value === "string" && value.trim().length > 0;
  const finite = (value) => typeof value === "number" && Number.isFinite(value);
  const id = (value) => typeof value === "string" && storeId.exec(value)?.[0] === value;
  function data(value, key) {
    if (!mapping(value)) return undefined;
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    return descriptor?.enumerable && own(descriptor, "value") ? descriptor.value : undefined;
  }
  function jsonValue(value, ancestors = new Set()) {
    if (value === null || typeof value === "string" || typeof value === "boolean") return true;
    if (typeof value === "number") return Number.isFinite(value);
    if ((!Array.isArray(value) && !mapping(value)) || ancestors.has(value)) return false;
    const keys = Reflect.ownKeys(value).filter((key) => !(Array.isArray(value) && key === "length"));
    if (keys.some((key) => {
      const descriptor = Object.getOwnPropertyDescriptor(value, key);
      return typeof key !== "string" || dangerous.has(key) || !descriptor.enumerable || !own(descriptor, "value");
    }) || (Array.isArray(value) && (keys.length !== value.length || keys.some((key, index) => key !== String(index))))) return false;
    ancestors.add(value);
    const valid = keys.every((key) => jsonValue(value[key], ancestors));
    ancestors.delete(value);
    return valid;
  }
  function joinedResult(record) {
    if (data(record, "integrity") !== "VERIFIED") return null;
    const result = data(record, "result"), proposal = data(record, "proposal"), study = data(record, "study");
    const experimentId = data(result, "experiment_id"), studyId = data(data(result, "study"), "id");
    if (!id(experimentId) || !id(studyId) || data(proposal, "id") !== experimentId ||
        data(proposal, "study_id") !== studyId || data(study, "id") !== studyId ||
        (mapping(record) && own(record, "record_id") && data(record, "record_id") !== experimentId)) return null;
    return result;
  }
  function metricLabel(result, name, ordinal) {
    const view = root.resultPresentation ?? presentation;
    const label = typeof view?.metricName === "function" ? view.metricName(name, ordinal) : name;
    const provenance = data(result, "provenance"), details = data(provenance, "adapter_details");
    const response = data(data(details, "per_mesh_displacement"), "response_metric");
    return name === "max_displacement" && data(provenance, "adapter") === "fixture.calculix" && response === "loaded_saddle_min_global_uz"
      ? "하중 안장 절점 최대 |UZ| (전체 절점 |U| 최대값 아님)" : label;
  }
  function choices(record) {
    try {
      const result = joinedResult(record), metrics = data(result, "metrics");
      if (!result || !mapping(metrics)) return [];
      const available = [];
      Reflect.ownKeys(metrics).forEach((name, ordinal) => {
        if (typeof name !== "string" || !nonempty(name) || dangerous.has(name)) return;
        const metric = data(metrics, name);
        if (!mapping(metric) || !jsonValue(metric) || data(metric, "valid") !== true || !nonempty(data(metric, "unit"))) return;
        const value = data(metric, "value"), unit = data(metric, "unit"), label = metricLabel(result, name, ordinal);
        if (finite(value)) available.push({ key: JSON.stringify([name, null]), metric: name, value, unit, label });
        else if (Array.isArray(value) && value.length > 0 && value.every(finite)) {
          value.forEach((item, component) => available.push({ key: JSON.stringify([name, component]), metric: name, component,
            value: item, unit, label: `${label} · 사용자 지정 배열 항목 ${component + 1} (물리 성분 미확인)` }));
        }
      });
      return available;
    } catch { return []; }
  }
  function requiredText(fields, key, maximum, label) {
    const value = data(fields, key);
    if (!nonempty(value) || value.trim().length > maximum) throw new Error(`${label}을(를) 비어 있지 않은 ${maximum}자 이내의 값으로 입력하세요.`);
    return value.trim();
  }
  function numberInput(fields, key, label) {
    const value = data(fields, key);
    if (!nonempty(value) || decimal.exec(value.trim())?.[0] !== value.trim() || !Number.isFinite(Number(value))) {
      throw new Error(`${label}을(를) 비어 있지 않은 유한한 수치로 입력하세요.`);
    }
    return Number(value);
  }
  function declaredConditions(fields) {
    const conditions = own(fields, "conditions") ? data(fields, "conditions") : [];
    if (!Array.isArray(conditions) || conditions.length > 16) throw new Error("조건 연결은 명시한 JSON 배열의 0~16개 항목이어야 합니다.");
    return conditions.map((item) => {
      const keys = ["source", "path", "value", "unit"], source = data(item, "source"), path = data(item, "path");
      const value = data(item, "value"), unit = data(item, "unit");
      if (!mapping(item) || Object.keys(item).length !== keys.length || !keys.every((key) => own(item, key)) ||
          !["execution", "input_parameters"].includes(source) || !Array.isArray(path) || path.length < 1 || path.length > 16 ||
          !path.every((segment) => nonempty(segment) && segment.length <= 128 && !dangerous.has(segment)) ||
          !(finite(value) || typeof value === "string" || typeof value === "boolean") || !nonempty(unit)) {
        throw new Error("조건 연결의 출처·정확한 경로·유한한 값·단위를 확인하세요. 선언된 조건의 실제 일치는 Core가 확인합니다.");
      }
      return { source, path: path.slice(), value, unit };
    });
  }
  function comparisonInput(record, fields) {
    if (!mapping(fields) || !jsonValue(fields)) throw new Error("관측 입력에는 자체 JSON 값만 사용할 수 있으며 위험 키·참조 순환·실행 가능한 속성은 허용하지 않습니다.");
    const result = joinedResult(record), experimentId = data(result, "experiment_id"), comparisonId = data(fields, "comparisonId");
    if (!result || !id(experimentId) || !id(comparisonId)) throw new Error("VERIFIED 기록의 실험·연구 연결과 새 비교 식별자를 확인하세요.");
    const purpose = data(fields, "purpose"), sourceKind = data(fields, "sourceKind");
    if (!purposes.includes(purpose)) throw new Error("일반 CAE 연구, 불량 재현 또는 지그 시험 검토의 연구 목적을 선택하세요.");
    if (!["MEASURED_REPORTED", "SPECIFICATION", "SYNTHETIC"].includes(sourceKind)) throw new Error("관측 출처의 측정 보고·규격·가상 데이터 구분을 명시하세요.");
    return { result, experimentId, comparisonId, purpose, sourceKind };
  }
  function observationInput(fields, unit, sourceKind) {
    const tolerance = numberInput(fields, "tolerance", "허용 차이");
    if (tolerance < 0) throw new Error("허용 차이는 0 이상의 유한한 수치로 입력하세요.");
    return { name: requiredText(fields, "name", 256, "관측 이름"), value: numberInput(fields, "value", "관측값"),
      unit, source_kind: sourceKind, source: requiredText(fields, "source", 2000, "관측 출처"),
      quantity: requiredText(fields, "quantity", 128, "관측 물리량"), component: requiredText(fields, "component", 128, "관측 성분"),
      location: requiredText(fields, "location", 512, "관측 위치"), coordinate_frame: requiredText(fields, "coordinateFrame", 128, "좌표계"),
      condition: requiredText(fields, "condition", 2000, "관측 조건"), tolerance, conditions: declaredConditions(fields) };
  }
  function build(record, fields) {
    const { experimentId, comparisonId, purpose, sourceKind } = comparisonInput(record, fields);
    const choice = choices(record).find((item) => item.key === data(fields, "responseKey"));
    if (!choice) throw new Error("유효한 저장 응답 또는 사용자 지정 배열 항목을 명시적으로 선택하세요.");
    const observation = observationInput(fields, choice.unit, sourceKind), response = { metric: choice.metric };
    if (own(choice, "component")) response.component = choice.component;
    return { comparison_id: comparisonId, experiment_id: experimentId, purpose,
      hypothesis: requiredText(fields, "hypothesis", 2000, "원인 가설"), observation, response };
  }
  function relativeArtifact(value) {
    return typeof value === "string" && value.length >= 1 && value.length <= 1024 && value === value.trim() &&
      !/[\\:%\u0000-\u001f\u007f]/.test(value) && value.split("/").every(part => part.length >= 1 &&
        part === part.trim() && ![".", ".."].includes(part) && !dangerous.has(part));
  }
  function buildField(record, fields, selection) {
    const { result, experimentId, comparisonId, purpose, sourceKind } = comparisonInput(record, fields);
    const keys = ["artifact", "sha256", "cad_revision", "node_id", "component"], revision = data(result, "cad_revision");
    if (!mapping(selection) || !jsonValue(selection) || Object.keys(selection).length !== keys.length || !keys.every(key => own(selection, key)) ||
        !relativeArtifact(selection.artifact) || typeof selection.sha256 !== "string" || selection.sha256.length !== 64 || !sha256.test(selection.sha256) ||
        typeof revision !== "string" || revision.length !== 64 || !sha256.test(revision) || selection.cad_revision !== revision ||
        !Number.isSafeInteger(selection.node_id) || selection.node_id < 1 || !["UX", "UY", "UZ", "MAGNITUDE"].includes(selection.component)) {
      throw new Error("같은 VERIFIED CAD 개정의 정확한 field 경로·SHA·양의 정수 절점·변위 성분을 선택하세요.");
    }
    if (data(fields, "unit") !== "mm") throw new Error("필드 관측 단위는 원 변위 단위 mm로 명시하세요. 자동 단위 변환은 없습니다.");
    // Copy selection identity only. Core/adapter read the original value and
    // coordinates; user-supplied response values, positions and axes are ignored.
    const field = Object.fromEntries(keys.map(key => [key, selection[key]]));
    return { comparison_id: comparisonId, experiment_id: experimentId, purpose,
      hypothesis: requiredText(fields, "hypothesis", 2000, "비교 가설 또는 연구 목적"),
      observation: observationInput(fields, "mm", sourceKind), response: { field } };
  }
  function buildPdeField(record, fields, selection) {
    const {result,experimentId,comparisonId,purpose,sourceKind} = comparisonInput(record,fields);
    const keys = ["kind","artifact","sha256","model_revision","study_index","step_index","node_id","component"];
    if (!mapping(selection) || !jsonValue(selection) || Object.keys(selection).length !== keys.length || !keys.every(key=>own(selection,key)) ||
      selection.kind !== "pde_nodal" || !relativeArtifact(selection.artifact) || !sha256.test(selection.sha256) ||
      !sha256.test(selection.model_revision) || selection.model_revision !== result.model_revision ||
      !Number.isSafeInteger(selection.study_index) || selection.study_index < 0 ||
      !(selection.step_index === null || Number.isSafeInteger(selection.step_index) && selection.step_index >= 0) ||
      !Number.isSafeInteger(selection.node_id) || selection.node_id < 0 || !["u","u0","u1"].includes(selection.component) ||
      !["pde.fenicsx.rectangle","pde.fenicsx.transient","pde.fenicsx.vector","pde.fenicsx.coupled","pde.fenicsx.imported"].includes(result.provenance.adapter)) {
      throw new Error("같은 VERIFIED PDE 모델 개정의 메시·단계·원 절점·성분을 선택하세요.");
    }
    if (data(fields,"unit") !== "1") throw new Error("이 PDE의 원 필드 단위는 1(무차원)입니다. 자동 단위 변환은 없습니다.");
    const observation = observationInput(fields,"1",sourceKind);
    if (selection.step_index !== null) observation.axis = {quantity:"time",unit:"1",value:numberInput(fields,"axisValue","관측 축 좌표")};
    return {comparison_id:comparisonId,experiment_id:experimentId,purpose,
      hypothesis:requiredText(fields,"hypothesis",2000,"비교 가설 또는 연구 목적"),observation,
      response:{field:Object.fromEntries(keys.map(key=>[key,selection[key]]))}};
  }
  const api = { choices, build, buildField, buildPdeField };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.observationControls = api;
})(typeof window !== "undefined" ? window : globalThis);
