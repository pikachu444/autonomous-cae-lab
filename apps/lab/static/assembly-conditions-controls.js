"use strict";

// User declarations for retained assembly CAD/mesh only. Core owns saved
// identities and integrity; Domain/adapters own mechanical and native admission.
(function (root) {
  const common = typeof module !== "undefined" && module.exports ? require("./analysis-conditions-controls.js") : root.analysisConditionsControls;
  const identifier = /^[A-Za-z][A-Za-z0-9_-]{0,79}$/;
  const digest = /^[a-f0-9]{64}$/;
  const decimal = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
  const categories = ["ASSUMED", "MEASURED_REPORTED", "PUBLISHED_REFERENCE"];
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
  const validId = value => typeof value === "string" && identifier.exec(value)?.[0] === value;
  const validDigest = value => typeof value === "string" && digest.exec(value)?.[0] === value;
  const copy = value => JSON.parse(JSON.stringify(value));
  const scalarText = value => Object.is(value, -0) ? "-0" : String(value);
  const forms = new WeakMap();

  function json(value, ancestors = new Set()) {
    if (value === null || ["string", "boolean"].includes(typeof value)) return true;
    if (typeof value === "number") return Number.isFinite(value);
    if ((!Array.isArray(value) && !object(value)) || ancestors.has(value)) return false;
    if (!Array.isArray(value)) {
      const prototype = Object.getPrototypeOf(value);
      // Accept ordinary JSON from another browser realm, without class instances.
      if (prototype !== null && prototype !== Object.prototype &&
          (Object.getPrototypeOf(prototype) !== null || Object.getOwnPropertyDescriptor(prototype, "constructor")?.value?.name !== "Object")) return false;
    }
    const keys = Reflect.ownKeys(value).filter(key => !(Array.isArray(value) && key === "length"));
    if (keys.some(key => {
      const property = Object.getOwnPropertyDescriptor(value, key);
      return typeof key !== "string" || ["__proto__", "constructor", "prototype"].includes(key) || !property.enumerable || !own(property, "value");
    }) || (Array.isArray(value) && (keys.length !== value.length || keys.some((key, index) => key !== String(index))))) return false;
    ancestors.add(value); const valid = keys.every(key => json(value[key], ancestors)); ancestors.delete(value); return valid;
  }
  function stable(value) {
    if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`;
    if (object(value)) return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${stable(value[key])}`).join(",")}}`;
    return Object.is(value, -0) ? "-0" : JSON.stringify(value);
  }
  function checkedCatalog(data) {
    if (!common?.catalog || !common?.saved || !common?.selectionLabel) throw new Error("공통 CAD 조건 검증기가 없습니다. 조건 입력 모듈을 함께 불러오세요.");
    common.catalog(data);
    const selections = data.catalog.selections;
    if (!selections.some(item => item.kind === "native_assembly_body") || !selections.some(item => item.kind === "native_assembly_face") ||
        selections.some(item => !["native_assembly_body", "native_assembly_face", "assembly_face_interior_nodes"].includes(item.kind))) {
      throw new Error("이 입력 폼에는 같은 CAD 개정의 실제 조립체 부품·원 면 catalog가 필요합니다.");
    }
    return data;
  }
  function isAssembly(data) {
    try { checkedCatalog(data); return true; } catch (_) { return false; }
  }
  function retainedMesh(data, required = false) {
    const mesh = data.catalog.retained_mesh;
    if (mesh === undefined) {
      if (required) throw new Error("이 CAD 개정에 연결된 보존 메시가 없습니다. 메시·활성 부품을 추정해 저장하거나 실행하지 않습니다.");
      return null;
    }
    const bodies = data.catalog.selections.filter(item => item.kind === "native_assembly_body");
    if (!object(mesh) || !validDigest(mesh.mesh_revision) || mesh.cad_revision !== data.source.cad_revision || mesh.profile !== "coarse3" ||
        !Array.isArray(mesh.active_components) || mesh.active_components.length < 1 || mesh.active_components.length > 64 ||
        mesh.active_components.some(component => !validId(component) || !bodies.some(body => body.component_id === component)) ||
        new Set(mesh.active_components).size !== mesh.active_components.length) {
      throw new Error("보존 메시의 개정·coarse3 profile·명시된 활성 부품 연결을 확인할 수 없습니다.");
    }
    return mesh;
  }
  function rowsFromCatalog(data) {
    checkedCatalog(data);
    const mesh = retainedMesh(data), active = new Set(mesh?.active_components ?? []);
    const option = item => ({ ...copy(item), displayLabel: common.selectionLabel(item) });
    const selections = data.catalog.selections.filter(item => active.has(item.component_id));
    return { source: copy(data.source), catalogRevision: data.catalog_revision,
      retainedMesh: mesh ? copy(mesh) : null, activeComponents: [...active],
      materials: selections.filter(item => item.kind === "native_assembly_body" && item.roles.includes("material")).map(option),
      boundaries: selections.filter(item => ["native_assembly_face", "assembly_face_interior_nodes"].includes(item.kind) && item.roles.includes("boundary")).map(option),
      loads: selections.filter(item => ["native_assembly_face", "assembly_face_interior_nodes"].includes(item.kind) && item.roles.includes("load")).map(option),
      contacts: selections.filter(item => item.kind === "native_assembly_face" && item.roles.includes("contact")).map(option) };
  }
  function text(fields, key, label) {
    const value = fields[key];
    if (typeof value !== "string" || !value.trim() || value.length > 2000) throw new Error(`${label}을(를) 비어 있지 않은 2000자 이내로 명시하세요.`);
    return value.trim();
  }
  function numeric(fields, key, label) {
    const value = fields[key];
    if (typeof value !== "string" || !value.trim() || decimal.exec(value.trim())?.[0] !== value.trim() || !Number.isFinite(Number(value))) {
      throw new Error(`${label}에 유한한 숫자를 명시하세요.`);
    }
    return Number(value);
  }
  function rows(fields, key, minimum = 1) {
    const list = fields[key];
    if (!Array.isArray(list) || list.length < minimum || list.length > 64 || list.some(row => !object(row) || !validId(row.id)) ||
        new Set(list.map(row => row.id)).size !== list.length) throw new Error("재료·구속·하중·접촉 행의 고유 ID와 명시적 목록을 확인하세요.");
    return list;
  }
  function selected(options, id, label) {
    if (!options.some(option => option.id === id)) throw new Error(`${label}은(는) 보존 메시의 활성 부품에 속한 실제 catalog ID를 선택하세요.`);
    return id;
  }
  function masterUnion(fields) {
    if ((own(fields, "masterUnionSameSlave") && typeof fields.masterUnionSameSlave !== "boolean") ||
        (own(fields, "masterUnionSameSlavePresent") && typeof fields.masterUnionSameSlavePresent !== "boolean") ||
        (fields.masterUnionSameSlavePresent === true && !own(fields, "masterUnionSameSlave"))) {
      throw new Error("같은 slave의 master 영역 묶음은 명시적 체크 여부(boolean)로 선언하세요.");
    }
    // New unchecked forms keep the original absent option. Presence metadata
    // preserves an already saved explicit false without inventing an opt-in.
    return fields.masterUnionSameSlave === true || fields.masterUnionSameSlavePresent === true ?
      { master_union_same_slave: fields.masterUnionSameSlave } : {};
  }
  function initialContact(fields, pairs) {
    if (!own(fields, "initialContactState")) return {};
    if (!["OPEN", "GEOMETRIC", "CLOSED_ASSUMED"].includes(fields.initialContactState)) {
      throw new Error("초기 접촉 상태를 명시하세요. 형상에 따른 접촉과 닫힘 가정을 구분합니다.");
    }
    return pairs.some(pair => pair.law === "frictionless") ? { initial_state: fields.initialContactState } : {};
  }
  function buildSave(data, fields) {
    checkedCatalog(data); retainedMesh(data, true);
    if (!object(fields) || !json(fields) || !validId(fields.conditionsId)) throw new Error("새 조건 ID와 명시적 조립체 입력을 확인하세요.");
    if (!data.backends.some(item => item.backend === fields.backend)) throw new Error("서버가 이 CAD catalog에 제공한 해석 경로를 선택하세요. 실행 환경은 별도로 확인됩니다.");
    if (fields.analysisType !== "nonlinear_static" || fields.coordinateSystem !== "global" || fields.lengthUnit !== "mm" || fields.forceUnit !== "N" || fields.stressUnit !== "MPa") {
      throw new Error("조립체 폼은 명시한 nonlinear_static·global·mm·N·MPa만 지원합니다. 축이나 단위를 자동 변환하지 않습니다.");
    }
    const options = rowsFromCatalog(data), materialRows = rows(fields, "materialRows"), boundaryRows = rows(fields, "boundaryRows"),
      loadRows = rows(fields, "loadRows", 0), contactRows = rows(fields, "contactRows", 0);
    const ids = [...materialRows, ...boundaryRows, ...loadRows].map(row => row.id);
    if (new Set(ids).size !== ids.length) throw new Error("재료·구속·하중의 ID는 서로 중복될 수 없습니다.");
    if (new Set(materialRows.map(row => row.selectionId)).size !== materialRows.length) throw new Error("같은 부품에 재료를 중복 배정할 수 없습니다.");
    const materials = materialRows.map(row => {
      if (!categories.includes(row.category)) throw new Error("재료 출처는 ASSUMED·MEASURED_REPORTED·PUBLISHED_REFERENCE 중 명시하세요.");
      const e = numeric(row, "youngModulus", "E (MPa)"), nu = numeric(row, "poissonRatio", "ν");
      if (e <= 0 || nu <= -1 || nu >= 0.5) throw new Error("등방성 선형탄성 값은 E>0, -1<ν<0.5이어야 합니다.");
      return { id: row.id, selection_id: selected(options.materials, row.selectionId, "재료 부품"), law: "isotropic_linear_elastic",
        young_modulus_MPa: e, poisson_ratio: nu, source: { category: row.category, description: text(row, "source", "재료 값의 출처") } };
    });
    const boundaries = boundaryRows.map(row => {
      const components = {};
      for (const axis of ["x", "y", "z"]) {
        if (typeof row[`u${axis}Enabled`] !== "boolean") throw new Error("각 변위 성분의 지정 여부를 명시하세요. 미지정 성분은 0으로 채우지 않습니다.");
        if (row[`u${axis}Enabled`]) components[`U${axis.toUpperCase()}`] = numeric(row, `u${axis}`, `U${axis.toUpperCase()} (mm)`);
      }
      if (!Object.keys(components).length) throw new Error("구속 행에는 지정할 변위 성분을 하나 이상 선택하세요.");
      return { id: row.id, selection_id: selected(options.boundaries, row.selectionId, "구속 면"), type: "displacement", components,
        unit: fields.lengthUnit, coordinate_system: fields.coordinateSystem, source: text(row, "source", "구속의 출처·가정") };
    });
    const loads = loadRows.map(row => ({ id: row.id, selection_id: selected(options.loads, row.selectionId, "하중 면"), type: "resultant_force",
      components: { FX: numeric(row, "fx", "FX (N)"), FY: numeric(row, "fy", "FY (N)"), FZ: numeric(row, "fz", "FZ (N)") },
      unit: fields.forceUnit, coordinate_system: fields.coordinateSystem, source: text(row, "source", "하중의 출처·가정") }));
    if (loads.some(row => !Object.values(row.components).some(v => v !== 0))) throw new Error("선언한 면 합력은 0이 아니어야 합니다. 변위 제어는 하중 행을 삭제하고 지정 변위를 입력하세요.");
    if (!loads.length && !boundaries.some(row => Object.values(row.components).some(v => v !== 0)))
      throw new Error("면 합력 또는 0이 아닌 지정 변위가 필요합니다. 고정 구속만으로 연구 실행을 시작하지 않습니다.");
    const pairs = contactRows.map(row => {
      if (!["bonded", "frictionless"].includes(row.law) || !["a", "b"].includes(row.master)) throw new Error("접촉 쌍마다 법칙과 master 면 A/B를 명시하세요. 자동 선택하지 않습니다.");
      const a = selected(options.contacts, row.selectionA, "접촉 면 A"), b = selected(options.contacts, row.selectionB, "접촉 면 B");
      if (a === b) throw new Error("접촉 쌍은 서로 다른 두 원 면을 선택하세요.");
      const pair = { selection_a: a, selection_b: b, law: row.law, master: row.master, source: text(row, "source", "접촉 쌍의 출처·가정") };
      if (row.law === "bonded") {
        pair.distance_max_mm = numeric(row, "distanceMaxMm", "bonded 검색 거리 (mm)");
        if (pair.distance_max_mm <= 0) throw new Error("bonded 검색 거리는 0보다 큰 mm 값으로 명시하세요.");
      } else if (own(row, "distanceMaxMm")) throw new Error("frictionless 쌍에 bonded 검색 거리를 넣을 수 없습니다.");
      return pair;
    });
    const declaration = { analysis_type: fields.analysisType, units: { length: fields.lengthUnit, force: fields.forceUnit, stress: fields.stressUnit },
      coordinate_system: fields.coordinateSystem, materials, boundary_conditions: boundaries, loads,
      contact: { mode: pairs.length ? "mixed" : "none", source: text(fields, "contactSource", "전체 접촉 모델의 출처·가정"), ...(pairs.length ? { pairs } : {}), ...masterUnion(fields), ...initialContact(fields, pairs) },
      mesh: { mode: "retained", mesh_revision: options.retainedMesh.mesh_revision } };
    return { conditions_id: fields.conditionsId, experiment_id: data.source.experiment_id, cad_revision: data.source.cad_revision,
      catalog_revision: data.catalog_revision, backend: fields.backend, declaration };
  }
  function fromRecord(record, data) {
    checkedCatalog(data); common.saved({ record, integrity: "VERIFIED" }, data);
    const value = record.request.declaration;
    if (value.analysis_type !== "nonlinear_static" || value.mesh?.mode !== "retained" ||
        !Array.isArray(value.materials) || !Array.isArray(value.boundary_conditions) || !Array.isArray(value.loads) ||
        !["none", "mixed"].includes(value.contact?.mode) ||
        (value.contact.mode === "none" ? own(value.contact, "pairs") : !Array.isArray(value.contact.pairs))) {
      throw new Error("원 조립체 조건을 보존했습니다. 현재 행 폼으로 정확히 표현할 수 없는 조건은 변환하거나 실행하지 않습니다.");
    }
    const fields = { conditionsId: record.id, backend: record.request.backend, analysisType: value.analysis_type,
      coordinateSystem: value.coordinate_system, lengthUnit: value.units?.length, forceUnit: value.units?.force, stressUnit: value.units?.stress,
      materialRows: value.materials.map(item => ({ id: item.id, selectionId: item.selection_id,
        youngModulus: scalarText(item.young_modulus_MPa), poissonRatio: scalarText(item.poisson_ratio), category: item.source?.category, source: item.source?.description })),
      boundaryRows: value.boundary_conditions.map(item => {
        if (!object(item.components)) throw new Error("원 구속 성분을 확인할 수 없습니다.");
        const row = { id: item.id, selectionId: item.selection_id, source: item.source };
        for (const axis of ["x", "y", "z"]) {
          const key = `U${axis.toUpperCase()}`; row[`u${axis}Enabled`] = own(item.components, key); row[`u${axis}`] = own(item.components, key) ? scalarText(item.components[key]) : "";
        }
        return row;
      }),
      loadRows: value.loads.map(item => ({ id: item.id, selectionId: item.selection_id, fx: scalarText(item.components?.FX),
        fy: scalarText(item.components?.FY), fz: scalarText(item.components?.FZ), source: item.source })),
      contactRows: (value.contact.pairs ?? []).map((item, index) => ({ id: `CP${index + 1}`, selectionA: item.selection_a, selectionB: item.selection_b,
        law: item.law, master: item.master, source: item.source, ...(own(item, "distance_max_mm") ? { distanceMaxMm: scalarText(item.distance_max_mm) } : {}) })),
      contactSource: value.contact.source, ...(own(value.contact, "initial_state") ? { initialContactState: value.contact.initial_state } : {}), ...(own(value.contact, "master_union_same_slave") ? {
        masterUnionSameSlave: value.contact.master_union_same_slave, masterUnionSameSlavePresent: true } : {}) };
    if (stable(buildSave(data, fields)) !== stable(record.request)) throw new Error("원 법칙·성분·면·접촉·메시를 현재 폼으로 정확히 재현할 수 없습니다. 보존 조건을 단순화해 실행하지 않습니다.");
    return fields;
  }
  function buildRun(record, data, fields, experimentId) {
    checkedCatalog(data); common.saved({ record, integrity: "VERIFIED" }, data);
    if (record.support.status !== "SUPPORTED_DECLARED_INPUTS") throw new Error("서버가 이 CAD·조립체 조건을 지원하지 않습니다. 저장 판정과 사유를 확인하세요.");
    if (stable(buildSave(data, fields)) !== stable(record.request)) throw new Error("저장 후 조립체 입력이 변경됐습니다. 새 조건 ID로 저장한 뒤 실행하세요.");
    if (!validId(experimentId) || experimentId === record.source.experiment_id) throw new Error("원 CAD와 다른 새 해석 실험 ID를 입력하세요.");
    return { parent_experiment_id: record.source.experiment_id, experiment_id: experimentId, backend: record.request.backend, conditions_id: record.id };
  }

  function renderForm(container, data, fields = {}) {
    const options = rowsFromCatalog(data), document = container?.ownerDocument;
    if (!document?.createElement || !container?.replaceChildren || !object(fields) || !json(fields)) throw new Error("현재 조립체 입력 영역과 일반 JSON 초안을 확인하세요.");
    masterUnion(fields);
    const state = { controls: {}, groups: {}, root: null, masterUnionSameSlavePresent: fields.masterUnionSameSlavePresent === true,
      initialContactStatePresent: own(fields, "initialContactState") };
    const element = (tag, textValue, className) => {
      const node = document.createElement(tag); if (textValue !== undefined) node.textContent = textValue; if (className) node.className = className; return node;
    };
    const notify = () => {
      const EventType = document.defaultView?.Event ?? root.Event;
      if (container.dispatchEvent && typeof EventType === "function") container.dispatchEvent(new EventType("input", { bubbles: true }));
    };
    const form = element("fieldset", undefined, "assembly-conditions-form"); state.root = form; form.dataset.assemblyConditionsForm = "true";
    form.append(element("legend", "조립체 부품·원 면 조건"));
    const context = element("p", `CAD ${options.source.experiment_id} · 개정 ${options.source.cad_revision}`, "mono"); context.dataset.assemblyContext = "cad"; form.append(context);
    const meshContext = element("p", options.retainedMesh ?
      `보존 메시 ${options.retainedMesh.profile} · 활성 ${options.activeComponents.length}부품 · ${options.retainedMesh.mesh_revision}` :
      "이 개정의 보존 메시가 없습니다. 부품 목록은 열람할 수 있으며 저장·실행은 차단됩니다.", "mono");
    meshContext.dataset.assemblyContext = "mesh"; form.append(meshContext);
    form.append(element("p", "원 조립체 global 축 · mm / N / MPa. 재료·접촉은 사용자 선언이며 물성·실물 자격은 미확인입니다."));
    function control(parent, key, caption, value, variants, settings = {}) {
      const label = element("label", caption), input = element(variants ? "select" : settings.multiline ? "textarea" : "input");
      input.dataset.assemblyField = key; input.required = settings.required !== false;
      if (variants) {
        const empty = element("option", "선택하세요"); empty.value = ""; input.append(empty);
        for (const variant of variants) { const option = element("option", variant.displayLabel ?? variant.label); option.value = variant.id; input.append(option); }
        if (typeof value === "string" && value.trim() && !variants.some(variant => variant.id === value)) {
          const target = ["selectionId", "selectionA", "selectionB"].includes(key);
          const unavailable = element("option", `${target ? "현재 CAD catalog에서 사용할 수 없는 대상" : "현재 선택 목록에서 사용할 수 없음"} · ${value}`);
          unavailable.value = value; unavailable.dataset.assemblyUnavailable = "true"; input.append(unavailable);
        }
      } else { if (!settings.multiline) input.type = settings.checkbox ? "checkbox" : "text"; if (settings.numeric) input.inputMode = "decimal"; }
      if (settings.checkbox) { input.checked = value === true; input.required = false; label.className = "check-line"; } else input.value = typeof value === "string" ? value : "";
      if (settings.multiline) input.rows = 2;
      label.append(input); parent.append(label); return input;
    }
    const literal = (id, label = id) => ({ id, label });
    // The portal's common form owns these visible inputs. Preserve only the
    // supplied values here; the caller merges current common fields on save.
    for (const key of ["conditionsId", "backend", "analysisType", "coordinateSystem", "lengthUnit", "forceUnit", "stressUnit"]) {
      const input = element("input"); input.type = "hidden"; input.dataset.assemblyField = key;
      input.value = typeof fields[key] === "string" ? fields[key] : ""; state.controls[key] = input; form.append(input);
    }
    const materialCoverage = element("p"); materialCoverage.dataset.assemblyMaterialCoverage = "true";
    const refreshCoverage = () => {
      const assigned = new Set(state.groups.materialRows?.rows.map(row => row.controls.selectionId.value).filter(value => options.materials.some(option => option.id === value)) ?? []);
      const missing = options.materials.filter(item => !assigned.has(item.id)).map(item => item.component_id);
      materialCoverage.textContent = `활성 부품 재료 ${assigned.size}/${options.materials.length} 배정${missing.length ? ` · 미배정: ${missing.join(", ")}` : ""}. 저장 시 실제 지원 판정을 확인합니다.`;
    };
    const selectionDetails = (parent, input, variants) => {
      const detail = element("p", "대상을 선택하면 원 ID·면적·중심을 표시합니다.", "selection-geometry"); detail.dataset.assemblySelectionDetails = "true"; parent.append(detail);
      const update = () => {
        const item = variants.find(variant => variant.id === input.value);
        detail.textContent = item ? `${item.displayLabel} · ${item.native_coordinate_system}` :
          input.value.trim() ? `현재 CAD catalog에서 사용할 수 없는 대상 · ${input.value}` : "대상을 선택하면 원 ID·면적·중심을 표시합니다.";
        refreshCoverage();
      };
      input.addEventListener("change", update); update();
    };
    function rowGroup(key, caption, note, prefix, variants, build) {
      const section = element("fieldset", undefined, "assembly-conditions-group"), list = element("div");
      section.dataset.assemblyGroup = key; section.append(element("legend", caption), element("p", note));
      if (key === "materialRows") section.append(materialCoverage);
      section.append(list); const group = { rows: [], list }; state.groups[key] = group;
      const addRow = (initial = {}) => {
        if (group.rows.length >= 64) throw new Error("각 조건 목록은 64행 이내로 입력하세요.");
        const row = { node: element("fieldset", undefined, "assembly-condition-row boundary-row"), controls: {} }; row.node.dataset.assemblyRow = key;
        const put = (field, label, values, settings) => row.controls[field] = control(row.node, field, label, initial[field], values, settings);
        row.node.append(element("legend", caption)); put("id", "행 ID");
        if (variants) { const select = put("selectionId", key === "materialRows" ? "활성 부품" : "활성 부품의 원 면", variants); selectionDetails(row.node, select, variants); }
        build(row, put);
        const remove = element("button", "행 삭제", "button subtle compact"); remove.type = "button"; remove.dataset.assemblyRemove = key;
        remove.addEventListener("click", () => {
          if (remove.disabled || form.disabled || section.disabled || row.node.disabled) return;
          group.rows = group.rows.filter(value => value !== row); row.node.remove(); refreshCoverage(); notify();
        });
        row.node.append(remove); group.rows.push(row); list.append(row.node); refreshCoverage(); return row;
      };
      const add = element("button", `${caption} 행 추가`, "button subtle compact"); add.type = "button"; add.dataset.assemblyAdd = key;
      add.disabled = !options.retainedMesh;
      add.addEventListener("click", () => {
        if (add.disabled || form.disabled || section.disabled) return;
        let index = 1; const used = new Set(Object.values(state.groups).flatMap(value => value.rows.map(row => row.controls.id.value)));
        while (used.has(`${prefix}${index}`)) index++;
        addRow({ id: `${prefix}${index}` }); notify();
      });
      section.append(add); form.append(section);
      const initial = fields[key] ?? [];
      if (!Array.isArray(initial) || initial.length > 64 || initial.some(row => !object(row))) throw new Error("보존된 조립체 행 초안 목록을 확인하세요.");
      initial.forEach(row => addRow(row));
      return group;
    }
    rowGroup("materialRows", "부품별 재료", "등방성 선형탄성 E·ν와 값의 출처를 부품마다 명시합니다.", "M", options.materials, (_row, put) => {
      put("youngModulus", "E (MPa)", null, { numeric: true }); put("poissonRatio", "ν", null, { numeric: true });
      put("category", "값의 출처 분류", [literal("ASSUMED", "ASSUMED · 가정"), literal("MEASURED_REPORTED", "MEASURED_REPORTED · 사용자 보고값, 자격 미확인"), literal("PUBLISHED_REFERENCE", "PUBLISHED_REFERENCE · 공개 문헌")]);
      put("source", "재료 값의 출처", null, { multiline: true });
    });
    rowGroup("boundaryRows", "변위 구속", "지정한 성분만 구속합니다. 미선택 UX·UY·UZ는 0으로 채우지 않습니다.", "BC", options.boundaries, (row, put) => {
      for (const axis of ["x", "y", "z"]) {
        const enabled = put(`u${axis}Enabled`, `U${axis.toUpperCase()} 지정`, null, { checkbox: true });
        const value = put(`u${axis}`, `U${axis.toUpperCase()} (mm)`, null, { numeric: true, required: enabled.checked });
        const update = () => { value.disabled = !enabled.checked; value.required = enabled.checked; };
        enabled.addEventListener("change", update); update();
      }
      put("source", "구속의 출처·가정", null, { multiline: true });
    });
    rowGroup("loadRows", "면 합력", "FX·FY·FZ의 부호와 값을 모두 명시합니다. 변위 제어는 하중 행을 삭제하고 구속 행에 0이 아닌 지정 변위를 입력하세요. 분포와 native 변환은 서버 판정을 따릅니다.", "L", options.loads, (_row, put) => {
      for (const axis of ["x", "y", "z"]) put(`f${axis}`, `F${axis.toUpperCase()} (N)`, null, { numeric: true });
      put("source", "하중의 출처·가정", null, { multiline: true });
    });
    rowGroup("contactRows", "접촉 쌍", "0행이면 명시적 접촉 없음입니다. 쌍을 추가하면 법칙·master·출처를 직접 선택합니다.", "CP", null, (row, put) => {
      for (const side of ["A", "B"]) { const select = put(`selection${side}`, `원 면 ${side}`, options.contacts); selectionDetails(row.node, select, options.contacts); }
      const law = put("law", "접촉 법칙", [literal("bonded", "bonded · 결합"), literal("frictionless", "frictionless · 무마찰")]);
      put("master", "master 면", [literal("a", "A"), literal("b", "B")]);
      const distance = put("distanceMaxMm", "bonded 검색 거리 (mm)", null, { numeric: true, required: false });
      const update = () => { distance.parentNode.hidden = law.value !== "bonded"; distance.disabled = law.value !== "bonded"; distance.required = law.value === "bonded"; };
      law.addEventListener("change", update); update();
      put("source", "접촉 쌍의 출처·가정", null, { multiline: true });
    });
    state.controls.masterUnionSameSlave = control(form, "masterUnionSameSlave",
      "같은 slave 면의 여러 frictionless master 면을 하나의 접촉 영역으로 묶기(명시적 선언)", fields.masterUnionSameSlave, null, { checkbox: true });
    form.append(element("p", "원래 master/slave 면 그룹을 보존합니다. 형상을 합치거나 새 메시를 만들지 않습니다."));
    state.controls.initialContactState = control(form, "initialContactState", "초기 frictionless 접촉 상태", fields.initialContactState ?? "OPEN", [
      { id: "OPEN", label: "열린 상태로 시작 · 초기 접촉 구속 없음" },
      { id: "GEOMETRIC", label: "원 형상에서 닫히거나 겹친 면만 접촉" },
      { id: "CLOSED_ASSUMED", label: "모든 접촉 면 닫힘 가정 · 실측 상태 아님" }]);
    state.controls.initialContactState.addEventListener("change", () => { state.initialContactStatePresent = true; });
    form.append(element("p", "닫힘 가정은 초기 간극과 무관하게 접촉을 활성화하며 초기 힘이 생길 수 있습니다. 형상을 재배치하지 않으며 실제 조립·초기 응력 자격은 UNKNOWN입니다."));
    state.controls.contactSource = control(form, "contactSource", "전체 접촉 모델의 출처·가정 (접촉 없음도 명시)", fields.contactSource, null, { multiline: true });
    form.append(element("p", "저장된 서버 지원 판정 → 같은 조건 ID로 새 해석 → 동일 결과 재열람. 접촉 선언은 실제 체결·실물 승인 판정이 아닙니다."));
    container.replaceChildren(form); forms.set(container, state); refreshCoverage(); return container;
  }
  function readForm(container) {
    const state = forms.get(container);
    if (!state || state.root.parentNode !== container) throw new Error("현재 조립체 폼을 먼저 불러오세요. 이전 DOM에서 입력을 추정하지 않습니다.");
    const fields = Object.fromEntries(Object.entries(state.controls).map(([key, node]) => [key, node.type === "checkbox" ? node.checked : node.value]));
    if (!state.initialContactStatePresent) delete fields.initialContactState;
    if (state.masterUnionSameSlavePresent) fields.masterUnionSameSlavePresent = true;
    for (const [key, group] of Object.entries(state.groups)) fields[key] = group.rows.map(row => {
      const value = Object.fromEntries(Object.entries(row.controls).map(([field, node]) => [field, field.endsWith("Enabled") ? node.checked : node.value]));
      if (key === "contactRows" && value.law !== "bonded") delete value.distanceMaxMm;
      return value;
    });
    return fields;
  }
  const api = { isAssembly, rowsFromCatalog, buildSave, fromRecord, buildRun, renderForm, readForm };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.assemblyConditionsControls = api;
})(typeof window !== "undefined" ? window : globalThis);
