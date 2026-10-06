"use strict";

// Exact retained FE points. Native table interpretation/engineering admission is
// owned by the adapter; the browser binds its display to the same sealed record.
(function (root) {
  const digest = value => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
  const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
  const finite = value => typeof value === "number" && Number.isFinite(value);
  const index = value => Number.isSafeInteger(value) && value >= 0;
  const positiveId = value => index(value) && value > 0;
  const vector = (value, length) => Array.isArray(value) && value.length === length && value.every(finite);
  const demand = (test, message) => { if (!test) throw new Error(message); };
  const definitions = Object.freeze({
    "DEPL.DX": ["fe_nodal", "displacements_mm", 0, "mm", "DISPLACEMENT"],
    "DEPL.DY": ["fe_nodal", "displacements_mm", 1, "mm", "DISPLACEMENT"],
    "DEPL.DZ": ["fe_nodal", "displacements_mm", 2, "mm", "DISPLACEMENT"],
    "REAC_NODA.DX": ["fe_nodal", "nodal_reactions_n", 0, "N", "NODAL_REACTION"],
    "REAC_NODA.DY": ["fe_nodal", "nodal_reactions_n", 1, "N", "NODAL_REACTION"],
    "REAC_NODA.DZ": ["fe_nodal", "nodal_reactions_n", 2, "N", "NODAL_REACTION"],
    "SIEF_ELGA.SIXX": ["fe_gauss", "stresses_mpa", 0, "MPa", "STRESS"],
    "SIEF_ELGA.SIYY": ["fe_gauss", "stresses_mpa", 1, "MPa", "STRESS"],
    "SIEF_ELGA.SIZZ": ["fe_gauss", "stresses_mpa", 2, "MPa", "STRESS"],
    "SIEF_ELGA.SIXY": ["fe_gauss", "stresses_mpa", 3, "MPa", "STRESS"],
    "SIEF_ELGA.SIXZ": ["fe_gauss", "stresses_mpa", 4, "MPa", "STRESS"],
    "SIEF_ELGA.SIYZ": ["fe_gauss", "stresses_mpa", 5, "MPa", "STRESS"],
    "VARI_ELGA.V1": ["fe_gauss", "eq_plastic_strain", null, "1", "EQUIVALENT_PLASTIC_STRAIN"]
  });
  const frame = "global Cartesian model; sensor/world alignment UNKNOWN";
  function catalog(inspection, envelope) {
    const result = inspection?.result, display = envelope?.display;
    demand(inspection?.integrity === "VERIFIED" && envelope?.integrity === "VERIFIED" &&
      result?.provenance?.adapter === "structural.code_aster.plasticity" &&
      ["COMPLETED_REVIEW_REQUIRED", "REJECTED"].includes(result.status) && result.decision === "NOT_RELEASED" &&
      envelope.experiment_id === result.experiment_id && envelope.study_id === result.study.id &&
      envelope.result_sha256 === inspection.hashes?.result_sha256 && digest(envelope.result_sha256) &&
      display?.kind === "j2_fe_fields" && display.model_revision === result.model_revision && digest(result.model_revision),
      "같은 VERIFIED 모델·결과에 연결된 FE 필드 catalog가 필요합니다.");
    demand(Array.isArray(display.meshes) && display.meshes.length >= 1 && display.meshes.length <= 3,
      "원래 선언한 FE 메시 목록을 확인할 수 없습니다.");
    const seen = new Set();
    for (const entry of display.meshes) {
      const artifacts = result.artifacts.filter(a => a.path === entry.artifact);
      demand(index(entry.mesh_index) && !seen.has(entry.mesh_index) && artifacts.length === 1 &&
        digest(entry.sha256) && artifacts[0].sha256 === entry.sha256 &&
        Array.isArray(entry.times_s) && entry.times_s.length >= 2 && entry.times_s.length <= 32 &&
        entry.times_s.every((t,i,a) => finite(t) && (i === 0 ? t === 0 : t > a[i-1])),
        "FE 메시·원 artifact·시간축 연결이 일치하지 않습니다.");
      seen.add(entry.mesh_index);
    }
    return structuredClone(display);
  }
  function verifiedRecord(raw, entry) {
    demand(object(raw) && finite(raw.mesh_size_mm) && raw.mesh_size_mm === entry.mesh_size_mm &&
      Array.isArray(raw.node_ids) && raw.node_ids.length > 0 && raw.node_ids.every(positiveId) &&
      new Set(raw.node_ids).size === raw.node_ids.length && Array.isArray(raw.coordinates_mm) &&
      raw.coordinates_mm.length === raw.node_ids.length && raw.coordinates_mm.every(v => vector(v,3)) &&
      Array.isArray(raw.states) && raw.states.length === entry.times_s.length && positiveId(raw.element_count),
      "원 FE 절점·좌표·이력 크기가 catalog와 일치하지 않습니다.");
    if (entry.node_ids) demand(JSON.stringify(entry.node_ids) === JSON.stringify(raw.node_ids), "원 native 절점 집합이 다릅니다.");
    demand(raw.element_count === entry.element_count && entry.coordinate_frame === frame && entry.coordinates_unit === "mm" &&
      JSON.stringify(entry.coordinates_mm) === JSON.stringify(raw.coordinates_mm), "원 메시·좌표·좌표계가 catalog와 다릅니다.");
    demand(new Set(raw.states.map(state=>state.actual_result_order)).size === raw.states.length,"원 native order가 중복됩니다.");
    let gauss = null;
    raw.states.forEach((state, step) => {
      demand(state.time_s === entry.times_s[step] && index(state.actual_result_order) &&
        ["displacements_mm","nodal_reactions_n"].every(key => Array.isArray(state[key]) &&
          state[key].length === raw.node_ids.length && state[key].every(row=>vector(row,3))),
        "전체 native 변위·반력 또는 원 시각/order가 다릅니다.");
      const ids = state.stress_identifiers;
      demand(Array.isArray(ids) && ids.length === raw.element_count * 5 && ids.every(p =>
        positiveId(p.element_id) && positiveId(p.point) && p.point <= 5 && index(p.subpoint) && p.order === state.actual_result_order),
        "원 TETRA10 적분점 식별자가 불완전합니다.");
      const keys = ids.map(p=>`${p.element_id}/${p.point}/${p.subpoint}`);
      const elements = new Map();
      ids.forEach(p=>{ const points=elements.get(p.element_id) || new Set(); points.add(p.point); elements.set(p.element_id,points); });
      demand(new Set(keys).size === keys.length && (gauss === null || JSON.stringify(gauss) === JSON.stringify(keys)) &&
        elements.size === raw.element_count && [...elements.values()].every(points=>points.size === 5) &&
        JSON.stringify(entry.gauss_ids) === JSON.stringify(ids.map(({element_id,point,subpoint})=>({element_id,point,subpoint}))) &&
        state.actual_result_order === entry.actual_result_orders?.[step] &&
        Array.isArray(state.stresses_mpa) && state.stresses_mpa.length === keys.length && state.stresses_mpa.every(v=>vector(v,6)) &&
        Array.isArray(state.eq_plastic_strain) && state.eq_plastic_strain.length === keys.length && state.eq_plastic_strain.every(finite) &&
        Array.isArray(state.stress_point_coordinates_mm) && state.stress_point_coordinates_mm.length === keys.length &&
        state.stress_point_coordinates_mm.every(v=>vector(v,3)), "응력·소성변형률·원 적분점의 전체 연결이 다릅니다.");
      gauss = keys;
    });
    return raw;
  }
  async function loadField(inspection, envelope, entry, fetchBytes, current = ()=>true) {
    const display = catalog(inspection,envelope), selected = display.meshes.find(item => item.mesh_index === entry.mesh_index);
    demand(selected && JSON.stringify(selected) === JSON.stringify(entry) && current(), "같은 현재 메시를 선택하세요.");
    const artifact = inspection.result.artifacts.find(item => item.path === entry.artifact);
    demand(positiveId(artifact.size_bytes) && artifact.size_bytes <= 32 * 1024 * 1024,
      "32 MiB보다 큰 FE 원본은 다운로드로 확인하세요.");
    const payload = await fetchBytes(entry.artifact, artifact.size_bytes);
    demand(current() && payload instanceof Uint8Array && payload.byteLength === artifact.size_bytes, "원 FE 파일 크기 또는 선택이 바뀌었습니다.");
    const crypto = root.crypto || (typeof module !== "undefined" && module.exports ? require("node:crypto").webcrypto : null);
    demand(crypto?.subtle, "원 FE 파일 해시 검증을 사용할 수 없습니다.");
    const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",payload)),v=>v.toString(16).padStart(2,"0")).join("");
    demand(current() && hash === artifact.sha256, "원 FE 파일 해시 또는 선택이 바뀌었습니다.");
    const raw = JSON.parse(new TextDecoder("utf-8",{fatal:true}).decode(payload), (key,value)=> {
      demand(!["__proto__","prototype","constructor"].includes(key) && (typeof value !== "number" || finite(value)), "유효하지 않은 FE JSON 입력입니다.");
      return value;
    });
    return {raw:verifiedRecord(raw,entry),entry:structuredClone(entry),model_revision:display.model_revision,
      components:Object.keys(definitions),coordinate_frame:frame};
  }
  function rows(field, timeIndex, component) {
    demand(index(timeIndex) && timeIndex < field.raw.states.length && Object.hasOwn(definitions,component), "원 시각과 성분을 선택하세요.");
    const [kind,key,column,unit,quantity] = definitions[component], state = field.raw.states[timeIndex];
    const identifiers = kind === "fe_nodal" ? field.raw.node_ids : state.stress_identifiers;
    return identifiers.map((native,rowIndex)=>({kind, native, coordinates_mm:kind === "fe_nodal" ? field.raw.coordinates_mm[rowIndex] : state.stress_point_coordinates_mm[rowIndex],
      value:column === null ? state[key][rowIndex] : state[key][rowIndex][column],unit,quantity,component,time_s:state.time_s,
      actual_result_order:state.actual_result_order,initial_state:timeIndex === 0 ? "INITIAL_STATE_NO_NEWTON_INCREMENT" : null}));
  }
  function selection(field, timeIndex, component, rowIndex) {
    const values = rows(field,timeIndex,component);
    demand(index(rowIndex) && rowIndex < values.length, "선택한 원 native point가 없습니다.");
    const row = values[rowIndex], common = {kind:row.kind,artifact:field.entry.artifact,sha256:field.entry.sha256,
      model_revision:field.model_revision,mesh_index:field.entry.mesh_index,time_index:timeIndex,component};
    return {selector:row.kind === "fe_nodal" ? {...common,node_id:row.native} : {...common,
      element_id:row.native.element_id,point:row.native.point,subpoint:row.native.subpoint},row};
  }
  const api = Object.freeze({catalog,loadField,rows,selection,definitions,frame});
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.nativeFeFieldInspector = api;
})(typeof window !== "undefined" ? window : globalThis);
