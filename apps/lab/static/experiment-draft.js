"use strict";

// Copy saved conditions for editing, never execution admission or engineering approval.
// VERIFIED is supplied by reporting.verified_record; this helper joins its recorded
// identities/hashes without claiming to re-hash files or requalify the CAD parent.
(function (root) {
  const storeId = /^[A-Za-z][A-Za-z0-9_-]{0,79}$/;
  const sha256 = /^[0-9a-f]{64}$/;
  const dangerous = new Set(["__proto__", "prototype", "constructor"]);
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  const mapping = (value) => value !== null && typeof value === "object" &&
    (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null);
  const text = (value) => typeof value === "string" && value.trim().length > 0;
  const id = (value) => typeof value === "string" && storeId.exec(value)?.[0] === value;
  const digest = (value) => typeof value === "string" && value.length === 64 && sha256.test(value);
  class Refusal extends Error {
    constructor(code, reason) { super(reason); this.code = code; }
  }
  function requireValue(condition, code, reason) {
    if (!condition) throw new Refusal(code, reason);
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
  function cloneJson(value) {
    if (Array.isArray(value)) return value.map(cloneJson);
    if (mapping(value)) return Object.fromEntries(Object.keys(value).map((key) => [key, cloneJson(value[key])]));
    return value;
  }
  function equalJson(left, right) {
    if (Object.is(left, right)) return true;
    if (Array.isArray(left) || Array.isArray(right)) return Array.isArray(left) && Array.isArray(right) &&
      left.length === right.length && left.every((value, index) => equalJson(value, right[index]));
    if (!mapping(left) || !mapping(right)) return false;
    const keys = Object.keys(left);
    return keys.length === Object.keys(right).length && keys.every((key) => own(right, key) && equalJson(left[key], right[key]));
  }
  function identity(record) {
    requireValue(mapping(record) && record.integrity === "VERIFIED", "INTEGRITY_REQUIRED", "원본 일치가 VERIFIED인 저장 기록만 복제할 수 있습니다.");
    const { result, proposal, thread, study, ledger, hashes } = record;
    requireValue([result, proposal, thread, study, ledger, hashes].every(mapping) && mapping(result.study) &&
      mapping(result.provenance) && mapping(proposal.physics) && mapping(proposal.model) && mapping(proposal.execution) &&
      result.schema_version === "1.0" && proposal.schema_version === "1.0" &&
      ["REJECTED", "FAILED_EXECUTION", "COMPLETED_REVIEW_REQUIRED", "CANCELLED"].includes(result.status),
    "INCOMPLETE_RECORD", "결과·제안·연구·연결·원본 해시와 실행 조건을 갖춘 저장 기록이 필요합니다.");
    const experimentId = result.experiment_id, studyId = result.study.id, hypothesisId = proposal.hypothesis_id;
    requireValue(id(experimentId) && id(studyId) && text(hypothesisId) && proposal.id === experimentId &&
      proposal.study_id === studyId && study.id === studyId && thread.experiment === experimentId && thread.study === studyId &&
      ledger.experiment_id === experimentId && result.study.hypothesis_id === hypothesisId && thread.hypothesis === hypothesisId &&
      (!own(record, "record_id") || record.record_id === experimentId) &&
      (!own(record, "experiment_id") || record.experiment_id === experimentId) &&
      (thread.run === null || thread.run === experimentId),
    "IDENTITY_MISMATCH", "기록의 실험·연구·가설 식별자가 일치하지 않습니다.");
    // hypotheses are strings in the common proposal schema, not store path IDs.
    requireValue(["result_sha256", "thread_sha256", "proposal_sha256", "ledger_sha256", "study_sha256"].every((key) => digest(hashes[key])) &&
      ledger.result_sha256 === hashes.result_sha256 && ledger.thread_sha256 === hashes.thread_sha256 &&
      digest(result.provenance.proposal_sha256) && digest(result.proposal_revision),
    "INCOMPLETE_RECORD", "검증 응답의 저장 문서 해시 연결이 불완전하거나 일치하지 않습니다.");
    return { result, proposal, thread, experimentId, studyId, hypothesisId };
  }
  function presetFor(presets, backend, operation, settings) {
    requireValue(mapping(presets), "INVALID_PRESETS", "기존 해석 경로 목록을 확인할 수 없습니다.");
    for (const presetId of Reflect.ownKeys(presets)) {
      const descriptor = Object.getOwnPropertyDescriptor(presets, presetId);
      requireValue(typeof presetId === "string" && id(presetId) && !dangerous.has(presetId) && descriptor.enumerable && own(descriptor, "value"),
        "INVALID_PRESETS", "해석 경로 목록의 식별자나 JSON 형식이 올바르지 않습니다.");
      const preset = descriptor.value;
      if (!mapping(preset)) continue;
      const backendEntry = Object.getOwnPropertyDescriptor(preset, "backend"), operationEntry = Object.getOwnPropertyDescriptor(preset, "operation");
      // Read only routing metadata. Example settings must never replace saved settings.
      if (backendEntry && own(backendEntry, "value") && backendEntry.value === backend && operationEntry &&
          own(operationEntry, "value") && operationEntry.value === operation) {
        // A selected single mesh and the retained benchmark use the same backend.
        // Select the matching editor, without copying its preset conditions.
        if (["pde.fenicsx.rectangle", "structural.code_aster.plasticity"].includes(backend) && preset.settings?.mode !== settings?.mode) continue;
        return presetId;
      }
    }
    throw new Refusal("PRESET_UNAVAILABLE", "같은 backend와 명시된 operation을 가진 기존 해석 경로가 없습니다.");
  }
  function noParent(value) { return value === undefined || value === null; }
  function fromRecord(record, presets) {
    try {
      requireValue(jsonValue(record), "INVALID_JSON", "기록에는 유한한 JSON 값만 사용할 수 있으며 위험 키·참조 순환·실행 가능한 속성은 허용하지 않습니다.");
      const { result, proposal, thread, experimentId, studyId, hypothesisId } = identity(record);
      requireValue(proposal.physics.analysis_type !== "cad_preflight", "UNSUPPORTED_OPERATION", "CAD 재등록과 새 연구 변수 매핑은 이 조건 복제의 범위 밖입니다.");
      const backend = result.provenance.adapter;
      requireValue(text(backend) && backend === proposal.physics.backend &&
        (!mapping(result.provenance.solver) || result.provenance.solver.backend === backend),
      "BACKEND_MISMATCH", "결과 adapter와 제안의 physics.backend가 일치하지 않습니다.");
      requireValue(thread.run === experimentId && result.proposal_revision === result.provenance.proposal_sha256 &&
        mapping(result.provenance.execution_settings) && equalJson(proposal.execution, result.provenance.execution_settings),
      "SETTINGS_MISMATCH", "저장된 실행 조건·제안 개정·실행 연결이 일치하지 않습니다.");
      const proposalExtensions = proposal.extensions ?? {}, resultExtensions = result.extensions ?? {};
      requireValue(mapping(proposalExtensions) && mapping(resultExtensions), "INCOMPLETE_RECORD", "저장된 해석 경로의 선언이 불완전합니다.");
      const namespaces = ["pde", "model_analysis"].filter((name) => own(proposalExtensions, name) || own(resultExtensions, name));
      let operation, parentExperimentId = null, modelRevision = null, cadRevision = null;
      if (backend === "fixture.calculix" && namespaces.length === 0) {
        operation = "analysis_run";
        parentExperimentId = result.parent_experiment_id; cadRevision = result.cad_revision;
        const geometry = proposal.model.geometry;
        requireValue(id(parentExperimentId) && parentExperimentId !== experimentId && mapping(geometry) &&
          proposal.parent_experiment_id === parentExperimentId && result.provenance.parent_experiment_id === parentExperimentId &&
          thread.parent_experiment === parentExperimentId && geometry.source_experiment_id === parentExperimentId &&
          Array.isArray(record.parent_chain) && record.parent_chain.length === 1,
        "PARENT_MISMATCH", "원본 해석이 참조한 직접 CAD 부모와 검증된 연결이 일치하지 않습니다.");
        const parent = record.parent_chain[0], parentIdentity = identity(parent);
        requireValue(parentIdentity.experimentId === parentExperimentId && parentIdentity.studyId === studyId &&
          parentIdentity.hypothesisId === hypothesisId && noParent(parentIdentity.result.parent_experiment_id) &&
          noParent(parentIdentity.proposal.parent_experiment_id) && parentIdentity.proposal.physics.analysis_type === "cad_preflight" &&
          parentIdentity.proposal.model.geometry?.backend === parentIdentity.result.provenance.adapter &&
          digest(result.provenance.parent_result_sha256) && result.provenance.parent_result_sha256 === parent.hashes.result_sha256 &&
          thread.parent_result_sha256 === parent.hashes.result_sha256,
        "PARENT_MISMATCH", "같은 연구의 CAD 부모 식별자·원본 해시·선언을 확인할 수 없습니다.");
        requireValue(digest(cadRevision) && geometry.cad_revision === cadRevision && thread.cad_revision === cadRevision &&
          parentIdentity.result.cad_revision === cadRevision && parentIdentity.thread.cad_revision === cadRevision && noParent(result.model_revision),
        "REVISION_MISMATCH", "원본 해석과 CAD 부모의 개정이 일치하지 않습니다.");
      } else {
        requireValue(namespaces.length === 1 && backend !== "fixture.calculix", "UNSUPPORTED_OPERATION", "이 기록의 기존 PDE 또는 독립 모델 해석 경로를 확인할 수 없습니다.");
        const namespace = namespaces[0], proposalExtension = proposalExtensions[namespace], resultExtension = resultExtensions[namespace];
        requireValue(mapping(proposalExtension) && mapping(resultExtension), "INCOMPLETE_RECORD", "결과와 제안의 해석 선언이 모두 필요합니다.");
        requireValue(![result, proposal].some((value) => own(value, "campaign_id")) && !own(thread, "campaign") &&
          !own(proposalExtension, "parameter_binding") && !own(resultExtension, "parameter_binding") &&
          mapping(proposal.parameters) && Object.keys(proposal.parameters).length === 0 &&
          mapping(result.input_parameters) && Object.keys(result.input_parameters).length === 0 &&
          Array.isArray(proposal.objectives) && proposal.objectives.length === 0 && Array.isArray(proposal.constraints) && proposal.constraints.length === 0,
        "UNSUPPORTED_BINDING", "등록 변수·캠페인·최적화 목표나 바인딩을 복제하는 경로는 이번 범위 밖입니다. 원 조건은 기록에서 조회할 수 있습니다.");
        const geometry = proposal.model.geometry;
        requireValue(noParent(result.parent_experiment_id) && noParent(proposal.parent_experiment_id) &&
          noParent(result.provenance.parent_experiment_id) && noParent(thread.parent_experiment) && result.cad_revision === null &&
          thread.cad_revision === null && noParent(geometry?.source_experiment_id) && noParent(geometry?.cad_revision) &&
          Array.isArray(record.parent_chain) && record.parent_chain.length === 0,
        "PARENT_MISMATCH", "PDE·독립 모델 해석에 CAD 부모나 다른 실험 연결을 만들 수 없습니다.");
        modelRevision = result.model_revision;
        requireValue(digest(modelRevision) && proposal.model_revision === modelRevision && thread.model_revision === modelRevision &&
          proposalExtension.model_revision === modelRevision && resultExtension.model_revision === modelRevision,
        "REVISION_MISMATCH", "저장된 독립 모델 개정이 일치하지 않습니다.");
        operation = namespace === "pde" ? "pde_run" : "model_analysis_run";
      }
      const presetId = presetFor(presets, backend, operation, proposal.execution);
      const args = { backend, settings: cloneJson(proposal.execution) };
      if (operation === "analysis_run") args.parent_experiment_id = parentExperimentId;
      else { args.study_id = studyId; args.hypothesis_id = hypothesisId; }
      return { available: true, operation, presetId, arguments: args,
        source: { experimentId, studyId, backend, parentExperimentId, modelRevision, cadRevision } };
    } catch (error) {
      return error instanceof Refusal ? { available: false, code: error.code, reason: error.message }
        : { available: false, code: "INVALID_JSON", reason: "기록의 JSON 조건을 안전하게 확인할 수 없습니다." };
    }
  }
  const api = { fromRecord };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.experimentDraft = api;
})(typeof window !== "undefined" ? window : globalThis);
