"use strict";

// Read exact supported retained Maxwell, OpenRadioss and Code_Aster J2 histories.
// Core owns extraction, file checks and alignment. Research purposes come from
// the common observation builder; no interpolation or field aggregation here.
(function (root) {
  const observation = typeof module !== "undefined" && module.exports ? require("./observation-controls.js") : null;
  const storeId = /^[A-Za-z][A-Za-z0-9_-]{0,79}$/;
  const sha256 = /^[0-9a-f]{64}$/;
  const decimal = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
  const indexString = /^(?:0|[1-9]\d*)$/;
  const dangerous = new Set(["__proto__", "prototype", "constructor"]);
  const tensorComponents = ["xx", "yy", "zz", "xy", "xz", "yz"];
  const plasticityBackend = "structural.code_aster.plasticity";
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
        !(result.status === "COMPLETED_REVIEW_REQUIRED" || (result.provenance.adapter === plasticityBackend && result.status === "REJECTED")) ||
        !["material.mfront.viscoelastic", "explicit.openradioss", plasticityBackend].includes(result.provenance.adapter) ||
        proposal.physics.backend !== result.provenance.adapter || !Array.isArray(result.artifacts)) return false;
    if (result.provenance.adapter === plasticityBackend &&
        (!has(result, ["solver_status", "converged", "decision", "model_revision", "proposal_revision", "cad_revision"]) ||
         !has(proposal, ["model_revision", "execution"]) || !has(result.provenance, ["proposal_sha256"]) ||
         result.solver_status !== "COMPLETED" || result.converged !== true || result.decision !== "NOT_RELEASED" ||
         !digest(result.model_revision) || proposal.model_revision !== result.model_revision ||
         !digest(result.proposal_revision) || result.provenance.proposal_sha256 !== result.proposal_revision ||
         result.cad_revision !== null || (own(proposal, "cad_revision") && proposal.cad_revision !== null) ||
         !result.artifacts.every(entry => has(entry, ["path", "sha256", "size_bytes", "revision"]) && text(entry.path) && digest(entry.sha256) &&
           Number.isSafeInteger(entry.size_bytes) && entry.size_bytes >= 0 && entry.revision === result.proposal_revision))) return false;
    return true;
  }
  function validChannel(channel, result) {
    if (["explicit.openradioss", plasticityBackend].includes(result.provenance.adapter)) return nativeChannelValid(channel, result.provenance.adapter, result.artifacts);
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
  const radioss = {
    "radioss-center-z": ["z_m", "position", "Z", "native position", "m", "main node 9"],
    "radioss-bottom-z": ["bottom_z_m", "position", "Z", "native position", "m", "secondary node 1"],
    "radioss-center-vz": ["velocity_m_s", "velocity", "Z", "raw leapfrog velocity", "m/s", "main node 9"],
    "radioss-bottom-vz": ["bottom_velocity_m_s", "velocity", "Z", "raw leapfrog velocity", "m/s", "secondary node 1"],
    "radioss-center-az": ["acceleration_m_s2", "acceleration", "Z", "native acceleration", "m/s^2", "main node 9"],
    "radioss-kinetic": ["kinetic_energy_j", "kinetic_energy", "scalar", "native global energy", "J", "whole admitted model"],
    "radioss-internal": ["internal_energy_j", "internal_energy", "scalar", "signed native global energy", "J", "whole admitted model"],
    "radioss-external-work": ["external_work_j", "external_work", "scalar", "native global work", "J", "whole admitted model"],
    "radioss-spring-fx": ["spring_axial_force_n", "force", "local FX", "signed native spring axial force", "N", "spring element 2"],
    "radioss-ground-fz": ["spring_axial_force_n", "force", "global Z", "native spring axial force with explicit sign mapping", "N", "spring element 2 / moving body"],
    "radioss-spring-lx": ["spring_length_change_m", "length_change", "local X", "native spring length change", "m", "spring element 2"],
    "radioss-spring-work": ["spring_internal_energy_j", "internal_work", "scalar", "signed native trapezoidal constitutive work", "J", "spring element 2"],
    "radioss-wall-fnz": ["RWALL/FNZ", "impulse", "FNZ", "signed native cumulative wall impulse", "N s", "rigid wall 1"],
  };
  const plasticity = {
    "j2-x0-fx": { nativeField: "BOUNDARY_RESULTANTS.X0.DX", component: "FX", group: "X0.DX" },
    "j2-y0-fy": { nativeField: "BOUNDARY_RESULTANTS.Y0.DY", component: "FY", group: "Y0.DY" },
    "j2-z0-fz": { nativeField: "BOUNDARY_RESULTANTS.Z0.DZ", component: "FZ", group: "Z0.DZ" },
    "j2-xl-fx": { nativeField: "BOUNDARY_RESULTANTS.XL.DX", component: "FX", group: "XL.DX" }
  };
  for (const component of ["SIXX", "SIYY", "SIZZ", "SIXY", "SIXZ", "SIYZ", "V1"]) {
    plasticity[`j2-gauss-mean-${component.toLowerCase()}`] = {
      nativeField: component === "V1" ? "VARI_ELGA.V1" : `SIEF_ELGA.${component}`, component, derived: true
    };
  }
  function plasticityChannelValid(channel, artifacts) {
    if (!has(channel, ["id", "label", "metric", "quantity", "component", "measure", "coordinate_frame", "location", "unit", "axis", "values", "origin", "initial_state"]) ||
        !id(channel.id) || !own(plasticity, channel.id) || channel.metric !== null || !text(channel.label) ||
        channel.coordinate_frame !== "global Cartesian model; sensor/world alignment UNKNOWN" ||
        !has(channel.axis, ["quantity", "unit", "values", "semantics"]) || channel.axis.quantity !== "time" || channel.axis.unit !== "s" ||
        channel.axis.semantics !== "NATIVE_INST_DECLARED_QUASI_STATIC_HISTORY_SECONDS" ||
        !Array.isArray(channel.values) || channel.values.length < 2 || channel.values.length > 32 || !channel.values.every(finite) ||
        !Array.isArray(channel.axis.values) || channel.axis.values.length !== channel.values.length ||
        !channel.axis.values.every((v, i, a) => finite(v) && (i === 0 ? v === 0 : v > a[i - 1]))) return false;
    const origin = channel.origin, spec = plasticity[channel.id], derived = spec.derived === true, strain = spec.component === "V1";
    if (!has(origin, ["kind", "driver", "artifact", "sha256", "native_artifact", "native_sha256", "native_field", "mapping", "mesh_index", "mesh_size_mm", "actual_result_orders", "mesh_sha256", "expected_mesh_sha256"]) ||
        origin.kind !== (derived ? "DERIVED" : "NATIVE") || origin.driver !== "code_aster" || origin.native_field !== spec.nativeField ||
        origin.mapping !== (derived ? "ALL_GAUSS_UNWEIGHTED_ARITHMETIC_MEAN" : "EXACT_NATIVE_POST_RELEVE_T_BOUNDARY_RESULTANT") ||
        !Number.isSafeInteger(origin.mesh_index) || origin.mesh_index < 0 || origin.mesh_index > 2 || !finite(origin.mesh_size_mm) || origin.mesh_size_mm <= 0 ||
        ![origin.sha256, origin.native_sha256, origin.mesh_sha256, origin.expected_mesh_sha256].every(digest) ||
        !Array.isArray(origin.actual_result_orders) || origin.actual_result_orders.length !== channel.values.length ||
        !origin.actual_result_orders.every(order => Number.isSafeInteger(order) && order >= 0) ||
        new Set(origin.actual_result_orders).size !== origin.actual_result_orders.length) return false;
    const prefix = `simulation/level_${origin.mesh_index}/`;
    if (origin.artifact !== `${prefix}parsed_history.json` || origin.native_artifact !== `${prefix}worker_result.json` ||
        channel.component !== spec.component || channel.quantity !== (derived ? (strain ? "equivalent_plastic_strain" : "stress") : "force") ||
        channel.unit !== (derived ? (strain ? "1" : "MPa") : "N") ||
        channel.location !== (derived ? `all BODY TETRA10 five-point Gauss samples on finest declared mesh ${origin.mesh_index}` : `group ${spec.group} on finest declared mesh ${origin.mesh_index}`) ||
        channel.measure !== (derived ? (strain ? "UNWEIGHTED arithmetic mean of native VARI_ELGA.V1; not volume average" : "UNWEIGHTED arithmetic mean of small-strain Cauchy Gauss stress; not volume average") : "signed native POST_RELEVE_T boundary resultant")) return false;
    if (!has(channel.initial_state, ["index", "kind", "time_s", "actual_result_order"]) || Object.keys(channel.initial_state).length !== 4 ||
        channel.initial_state.index !== 0 || channel.initial_state.kind !== "INITIAL_STATE_NO_NEWTON_INCREMENT" ||
        channel.initial_state.time_s !== channel.axis.values[0] || channel.initial_state.actual_result_order !== origin.actual_result_orders[0]) return false;
    if (derived) {
      const aggregation = origin.aggregation;
      if (!has(aggregation, ["operation", "weighting", "point_count", "coverage", "volume_average"]) || Object.keys(aggregation).length !== 5 ||
          aggregation.operation !== "arithmetic_mean" || aggregation.weighting !== "UNWEIGHTED" || aggregation.volume_average !== false ||
          aggregation.coverage !== "ALL_BODY_TETRA10_FIVE_RIGI_POINTS" || !Number.isSafeInteger(aggregation.point_count) ||
          aggregation.point_count < 5 || aggregation.point_count > 2500000 || aggregation.point_count % 5 !== 0) return false;
    } else if (own(origin, "aggregation")) return false;
    if (artifacts !== null) {
      if (!Array.isArray(artifacts)) return false;
      for (const [path, hash] of [[origin.artifact, origin.sha256], [origin.native_artifact, origin.native_sha256],
        [`${prefix}mesh.msh`, origin.mesh_sha256], [`${prefix}expected_mesh.json`, origin.expected_mesh_sha256]]) {
        const entries = artifacts.filter(entry => has(entry, ["path", "sha256"]) && typeof entry.path === "string" && entry.path.toLowerCase() === path.toLowerCase());
        if (entries.length !== 1 || entries[0].path !== path || entries[0].sha256 !== hash) return false;
      }
    }
    return true;
  }
  function plasticitySetValid(list, proposal) {
    if (list.length !== Object.keys(plasticity).length || !has(proposal.execution, ["mesh_sizes_mm", "history"]) ||
        !has(proposal.execution.history, ["times_s"])) return false;
    const sizes = proposal.execution.mesh_sizes_mm, times = proposal.execution.history.times_s;
    if (!Array.isArray(sizes) || sizes.length < 1 || sizes.length > 3 ||
        !sizes.every((size, i) => finite(size) && size > 0 && (i === 0 || size < sizes[i - 1])) || !Array.isArray(times)) return false;
    const first = list[0], orders = first.origin.actual_result_orders;
    const means = list.filter(channel => channel.origin.kind === "DERIVED"), count = means[0]?.origin.aggregation.point_count;
    return list.every(channel => channel.origin.mesh_index === sizes.length - 1 && channel.origin.mesh_size_mm === sizes[sizes.length - 1] &&
      channel.axis.values.length === times.length && channel.axis.values.every((v, i) => v === times[i]) &&
      channel.origin.actual_result_orders.length === orders.length && channel.origin.actual_result_orders.every((v, i) => v === orders[i])) &&
      means.every(channel => channel.origin.aggregation.point_count === count);
  }
  function radiossChannelValid(channel, backend, artifacts) {
    if (backend !== "explicit.openradioss" || !has(channel, ["id", "label", "metric", "quantity", "component", "measure", "coordinate_frame", "location", "unit", "axis", "values", "origin"]) ||
        !id(channel.id) || !own(radioss, channel.id) || channel.metric !== null || !text(channel.label) ||
        channel.coordinate_frame !== "global Cartesian SI; sensor/world alignment UNKNOWN" ||
        !has(channel.axis, ["quantity", "unit", "values", "semantics"]) || channel.axis.quantity !== "time" || channel.axis.unit !== "s" ||
        !Array.isArray(channel.values) || channel.values.length < 2 || channel.values.length > 20000 || !channel.values.every(finite) ||
        !Array.isArray(channel.axis.values) || channel.axis.values.length !== channel.values.length ||
        !channel.axis.values.every((v, i, a) => finite(v) && (i === 0 ? v === 0 : v > a[i-1]))) return false;
    const spec = radioss[channel.id], origin = channel.origin, derived = channel.id === "radioss-ground-fz";
    if (["quantity", "component", "measure", "unit", "location"].some((key, i) => channel[key] !== spec[i+1]) ||
        channel.axis.semantics !== (channel.quantity === "velocity" ? "NATIVE_HALF_STEP_VELOCITY_TIME" : "NATIVE_CURRENT_TIME") ||
        !has(origin, ["kind", "driver", "artifact", "sha256", "native_artifact", "native_sha256", "native_field", "mapping"]) ||
        origin.kind !== (derived ? "DERIVED" : "NATIVE") || origin.driver !== "openradioss" ||
        origin.artifact !== "simulation/parsed_history.json" || origin.native_artifact !== "simulation/dropT01" ||
        !digest(origin.sha256) || !digest(origin.native_sha256) || origin.native_field !== spec[0] ||
        origin.mapping !== (derived ? "GLOBAL_UPWARD_FORCE_EQUALS_MINUS_LOCAL_FX" : "EXACT_RETAINED_TH40_SAMPLE")) return false;
    if (artifacts !== null) for (const [path, hash] of [[origin.artifact, origin.sha256], [origin.native_artifact, origin.native_sha256]]) {
      if (!Array.isArray(artifacts)) return false;
      const entries = artifacts.filter(a => has(a, ["path", "sha256"]) && a.path === path);
      if (entries.length !== 1 || entries[0].sha256 !== hash) return false;
    }
    return true;
  }
  function nativeChannelValid(channel, backend, artifacts = null) {
    try {
      // Direct comparison validation may omit the manifest; Core verifies the
      // saved comparison source separately. Never invoke accessor-backed input.
      if (!jsonValue(channel) || (artifacts !== null && !jsonValue(artifacts))) return false;
      return backend === plasticityBackend ? plasticityChannelValid(channel, artifacts) : radiossChannelValid(channel, backend, artifacts);
    } catch { return false; }
  }
  function channels(inspection, envelope) {
    try {
      if (!joined(inspection, envelope) || !Array.isArray(envelope.channels) || envelope.channels.length === 0) return [];
      const seen = new Set();
      for (const channel of envelope.channels) {
        if (!validChannel(channel, inspection.result) || seen.has(channel.id)) return [];
        seen.add(channel.id);
      }
      if (inspection.result.provenance.adapter === plasticityBackend && !plasticitySetValid(envelope.channels, inspection.proposal)) return [];
      return cloneJson(envelope.channels);
    } catch { return []; }
  }
  function sampleChoice(inspection, envelope, channelId, index) {
    const channel = channels(inspection, envelope).find((item) => item.id === channelId);
    if (!id(channelId) || !channel || !Number.isSafeInteger(index) || index < 0 || index >= channel.values.length) {
      throw new Error("같은 VERIFIED 결과에 연결된 원본 이력 채널과 정확한 정수 표본 번호를 선택하세요.");
    }
    const time = channel.axis.values[index], displayedTime = Object.is(time, -0) ? "-0" : String(time);
    const initial = channel.initial_state?.index === index ?
      (channel.initial_state?.kind === "UNPREPARED_INITIAL_CONDITION" ? " · 수치 초기 상태 (재료 적분 증거 아님)" :
        channel.initial_state?.kind === "INITIAL_STATE_NO_NEWTON_INCREMENT" ? " · 초기 보존 상태 (새 Newton 증분 없음)" : "") : "";
    const axisLabel = channel.axis.quantity === "time" ? `t=${displayedTime}s` : `하중 계수=${displayedTime}`;
    return { key: JSON.stringify(["history", channel.id, index]), label: `${channel.label} · ${axisLabel}${initial}`,
      value: channel.values[index], unit: channel.unit, history_channel: channel.id, sample_index: index,
      axis: { quantity: channel.axis.quantity, value: time, unit: channel.axis.unit }, channel };
  }
  function build(inspection, envelope, fields) {
    if (!has(fields, ["channelId", "sampleIndex", "axisQuantity", "axisUnit", "axisValue"]) || !jsonValue(fields)) {
      throw new Error("이력 관측 입력에는 자체 유한한 JSON 값과 명시한 채널·표본·관측 시간 입력이 필요합니다.");
    }
    if (typeof fields.sampleIndex !== "string" || indexString.exec(fields.sampleIndex)?.[0] !== fields.sampleIndex ||
        !Number.isSafeInteger(Number(fields.sampleIndex))) throw new Error("표본 번호는 선행 0이나 다른 표기 없이 0 이상의 정수 문자열로 입력하세요.");
    const choice = sampleChoice(inspection, envelope, fields.channelId, Number(fields.sampleIndex));
    if (inspection.result.status !== "COMPLETED_REVIEW_REQUIRED") {
      throw new Error("조건 미충족 결과의 보존 이력은 열람할 수 있지만 새 관측 비교 저장은 허용하지 않습니다.");
    }
    if (fields.axisQuantity !== choice.axis.quantity || fields.axisUnit !== choice.axis.unit || !text(fields.axisValue) ||
        decimal.exec(fields.axisValue.trim())?.[0] !== fields.axisValue.trim() || !Number.isFinite(Number(fields.axisValue))) {
      throw new Error("관측 시간·축의 물리량과 단위를 원본 채널과 같게 명시하고 유한한 관측값을 입력하세요. 원 표본 좌표를 자동 대입하지 않습니다.");
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
  const api = { channels, sampleChoice, build, nativeChannelValid };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.historyControls = api;
})(typeof window !== "undefined" ? window : globalThis);
