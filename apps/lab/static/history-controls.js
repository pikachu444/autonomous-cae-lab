"use strict";

// Read exact supported retained histories (current native projection: Maxwell).
// Core owns extraction, file checks and alignment. Research purposes come from
// the common observation builder; no new history family or interpolation here.
(function (root) {
  const observation = typeof module !== "undefined" && module.exports ? require("./observation-controls.js") : null;
  const storeId = /^[A-Za-z][A-Za-z0-9_-]{0,79}$/;
  const sha256 = /^[0-9a-f]{64}$/;
  const decimal = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
  const indexString = /^(?:0|[1-9]\d*)$/;
  const dangerous = new Set(["__proto__", "prototype", "constructor"]);
  const tensorComponents = ["xx", "yy", "zz", "xy", "xz", "yz"];
  const nativeFields = {
    stress_physical_mpa: { metric: "stress_history", quantity: "stress", measure: "infinitesimal Cauchy stress", mapping: "RECORDED_PHYSICAL_COMPONENT", tensor: true },
    branch_stress_physical_mpa: { metric: "branch_stress_history", quantity: "branch_stress", measure: "internal branch stress", mapping: "RECORDED_PHYSICAL_COMPONENT", tensor: true },
    stored_energy_mpa: { metric: "native_energy_history", quantity: "stored_energy_density", measure: "reference-volume energy density", mapping: "NATIVE_SCALAR", tensor: false },
    dissipated_energy_mpa: { metric: "native_energy_history", quantity: "dissipated_energy_density", measure: "reference-volume energy density", mapping: "NATIVE_SCALAR", tensor: false }
  };
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  const mapping = (value) => value !== null && typeof value === "object" &&
    (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null);
  const finite = (value) => typeof value === "number" && Number.isFinite(value);
  const text = (value) => typeof value === "string" && value.trim().length > 0;
  const id = (value) => typeof value === "string" && storeId.exec(value)?.[0] === value;
  const digest = (value) => typeof value === "string" && value.length === 64 && sha256.test(value);
  const has = (value, keys) => mapping(value) && keys.every((key) => own(value, key));
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
  function joined(inspection, envelope) {
    if (!has(inspection, ["integrity", "result", "proposal", "study", "hashes"]) ||
        !has(envelope, ["integrity", "experiment_id", "study_id", "result_sha256", "channels"]) || !jsonValue(inspection) || !jsonValue(envelope) ||
        inspection.integrity !== "VERIFIED" || envelope.integrity !== "VERIFIED") return false;
    const { result, proposal, study, hashes } = inspection;
    if (!has(result, ["experiment_id", "study", "provenance", "status", "metrics", "artifacts"]) ||
        !has(proposal, ["id", "study_id", "physics"]) || !has(study, ["id"]) || !has(hashes, ["result_sha256"]) ||
        !has(result.study, ["id"]) || !has(result.provenance, ["adapter"]) || !has(proposal.physics, ["backend"]) ||
        !mapping(result.metrics) || !id(result.experiment_id) || !id(result.study.id) ||
        proposal.id !== result.experiment_id || proposal.study_id !== result.study.id || study.id !== result.study.id ||
        (own(inspection, "record_id") && inspection.record_id !== result.experiment_id) ||
        envelope.experiment_id !== result.experiment_id || envelope.study_id !== result.study.id ||
        !digest(hashes.result_sha256) || envelope.result_sha256 !== hashes.result_sha256 ||
        result.status !== "COMPLETED_REVIEW_REQUIRED" || result.provenance.adapter !== "material.mfront.viscoelastic" ||
        proposal.physics.backend !== result.provenance.adapter || !Array.isArray(result.artifacts)) return false;
    return true;
  }
  function validChannel(channel, result) {
    if (!has(channel, ["id", "label", "metric", "quantity", "component", "measure", "coordinate_frame", "location", "unit", "axis", "values", "origin"]) ||
        !id(channel.id) || !["label", "metric", "quantity", "component", "measure", "coordinate_frame", "location", "unit"].every((key) => text(channel[key])) ||
        !has(channel.axis, ["quantity", "unit", "values"]) || channel.axis.quantity !== "time" || channel.axis.unit !== "s" ||
        !Array.isArray(channel.axis.values) || !Array.isArray(channel.values) || channel.values.length === 0 ||
        channel.axis.values.length !== channel.values.length || !channel.values.every(finite) ||
        !channel.axis.values.every((value, index, axis) => finite(value) && (index === 0 || value > axis[index - 1]))) return false;
    const origin = channel.origin;
    if (!has(origin, ["kind", "driver", "artifact", "sha256", "native_field", "mapping"]) || origin.kind !== "NATIVE" || !["mgis", "mtest"].includes(origin.driver) ||
        origin.artifact !== "simulation/native_raw.json" || !digest(origin.sha256) || !own(nativeFields, origin.native_field)) return false;
    const declaration = nativeFields[origin.native_field], metric = own(result.metrics, channel.metric) ? result.metrics[channel.metric] : null;
    if (!has(metric, ["value", "valid", "unit"]) || metric.valid !== true || channel.unit !== metric.unit || channel.unit !== "MPa" ||
        channel.metric !== declaration.metric || channel.quantity !== declaration.quantity || channel.measure !== declaration.measure ||
        origin.mapping !== declaration.mapping || channel.coordinate_frame !== "Tridimensional model component basis; sensor/world alignment UNKNOWN" ||
        channel.location !== "single homogeneous material point" ||
        (declaration.tensor && (origin.driver !== "mgis" || !tensorComponents.includes(channel.component)))) return false;
    const artifacts = result.artifacts.filter((entry) => has(entry, ["path", "sha256"]) && entry.path === origin.artifact);
    return artifacts.length === 1 && artifacts[0].sha256 === origin.sha256;
  }
  function channels(inspection, envelope) {
    try {
      if (!joined(inspection, envelope) || !Array.isArray(envelope.channels) || envelope.channels.length === 0) return [];
      const seen = new Set();
      for (const channel of envelope.channels) {
        if (!validChannel(channel, inspection.result) || seen.has(channel.id)) return [];
        seen.add(channel.id);
      }
      return cloneJson(envelope.channels);
    } catch { return []; }
  }
  function sampleChoice(inspection, envelope, channelId, index) {
    const channel = channels(inspection, envelope).find((item) => item.id === channelId);
    if (!id(channelId) || !channel || !Number.isSafeInteger(index) || index < 0 || index >= channel.values.length) {
      throw new Error("같은 VERIFIED 결과에 연결된 원본 이력 채널과 정확한 정수 표본 번호를 선택하세요.");
    }
    const time = channel.axis.values[index], displayedTime = Object.is(time, -0) ? "-0" : String(time);
    const initial = channel.initial_state?.index === index && channel.initial_state?.kind === "UNPREPARED_INITIAL_CONDITION"
      ? " · 수치 초기 상태 (재료 적분 증거 아님)" : "";
    return { key: JSON.stringify(["history", channel.id, index]), label: `${channel.label} · t=${displayedTime}s${initial}`,
      value: channel.values[index], unit: channel.unit, history_channel: channel.id, sample_index: index,
      axis: { quantity: "time", value: time, unit: "s" }, channel };
  }
  function build(inspection, envelope, fields) {
    if (!has(fields, ["channelId", "sampleIndex", "axisQuantity", "axisUnit", "axisValue"]) || !jsonValue(fields)) {
      throw new Error("이력 관측 입력에는 자체 유한한 JSON 값과 명시한 채널·표본·관측 시간 입력이 필요합니다.");
    }
    if (typeof fields.sampleIndex !== "string" || indexString.exec(fields.sampleIndex)?.[0] !== fields.sampleIndex ||
        !Number.isSafeInteger(Number(fields.sampleIndex))) throw new Error("표본 번호는 선행 0이나 다른 표기 없이 0 이상의 정수 문자열로 입력하세요.");
    const choice = sampleChoice(inspection, envelope, fields.channelId, Number(fields.sampleIndex));
    if (fields.axisQuantity !== "time" || fields.axisUnit !== "s" || !text(fields.axisValue) ||
        decimal.exec(fields.axisValue.trim())?.[0] !== fields.axisValue.trim() || !Number.isFinite(Number(fields.axisValue))) {
      throw new Error("관측 시간은 time·s와 비어 있지 않은 유한한 수치로 명시하세요. 선택 표본 시각을 자동으로 대입하지 않습니다.");
    }
    const controls = root.observationControls ?? observation;
    if (typeof controls?.build !== "function") throw new Error("기존 관측 입력 검증 helper를 확인할 수 없습니다.");
    // Ephemeral projection only to reuse form validation. It is never returned,
    // persisted, or presented as a producer metric or a re-hashed saved result.
    const metric = "history_validation_sample";
    const projected = { ...inspection, result: { ...inspection.result, metrics: {
      [metric]: { value: choice.value, unit: choice.unit, valid: true }
    } } };
    const request = controls.build(projected, { ...fields, responseKey: JSON.stringify([metric, null]) });
    request.response = { history_channel: choice.history_channel, sample_index: choice.sample_index };
    // This is the user's reported axis, even when it differs from the retained
    // sample. Core decides whether the declared comparison aligns physically.
    request.observation.axis = { quantity: fields.axisQuantity, value: Number(fields.axisValue), unit: fields.axisUnit };
    return request;
  }
  const api = { channels, sampleChoice, build };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.historyControls = api;
})(typeof window !== "undefined" ? window : globalThis);
