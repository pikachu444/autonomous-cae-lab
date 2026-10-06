"use strict";

// Read-only adapter artifact inspection. Numerical/engineering verdicts stay in Core.
(function (root) {
  const LIMITS = Object.freeze({ bytes: 32 * 1024 * 1024, nodes: 40000, elements: 25000, faces: 8000, factor: 1000 });
  const COMPONENTS = Object.freeze(["UX", "UY", "UZ", "MAGNITUDE"]);
  const object = x => x !== null && typeof x === "object" && !Array.isArray(x);
  const finite = x => typeof x === "number" && Number.isFinite(x);
  const identifier = x => Number.isSafeInteger(x) && x > 0;
  const sha = x => typeof x === "string" && x.length === 64 && /^[0-9a-f]{64}$/.test(x);
  const id = x => typeof x === "string" && x.length <= 80 && /^[A-Za-z]/.test(x) && !/[^A-Za-z0-9_-]/.test(x);
  const assert = (value, message) => { if (!value) throw new Error(message); };
  const keys = (value, names) => object(value) && Object.keys(value).sort().join(",") === [...names].sort().join(",");
  function copy(value) {
    if (Array.isArray(value)) return value.map(copy);
    return object(value) ? Object.fromEntries(Object.entries(value).map(([key, item]) => [key, copy(item)])) : value;
  }
  function freeze(value) {
    if (value && typeof value === "object") { Object.values(value).forEach(freeze); Object.freeze(value); }
    return value;
  }
  function equal(a, b) {
    if (Object.is(a, b)) return true;
    if (Array.isArray(a)) return Array.isArray(b) && a.length === b.length && a.every((value, i) => equal(value, b[i]));
    return object(a) && object(b) && Object.keys(a).length === Object.keys(b).length &&
      Object.keys(a).every(key => Object.hasOwn(b, key) && equal(a[key], b[key]));
  }
  function safePath(value) {
    return typeof value === "string" && value.length > 0 && value.length <= 240 && !/[\\\x00-\x20:#?%]/.test(value) &&
      value.split("/").every(part => part && part !== "." && part !== "..");
  }
  const contexts = new WeakMap(), verified = new WeakSet();
  function catalog(inspection) {
    if (inspection?.result?.provenance?.adapter === "structure.calculix.native") return nativeCatalog(inspection);
    assert(inspection?.integrity === "VERIFIED", "기록 검증이 완료된 실험만 필드를 표시합니다.");
    const saved = copy(inspection), result = saved.result;
    assert(object(result) && result.provenance?.adapter === "fixture.calculix" && id(result.experiment_id) &&
      Array.isArray(result.artifacts), "fixture 해석 기록의 식별자를 확인할 수 없습니다.");
    const manifest = new Map();
    for (const artifact of result.artifacts) {
      assert(object(artifact) && safePath(artifact.path) && !manifest.has(artifact.path) && sha(artifact.sha256) &&
        Number.isSafeInteger(artifact.size_bytes) && artifact.size_bytes >= 0 && artifact.revision === result.cad_revision,
      "산출물 경로·해시·크기·CAD 개정이 불완전하거나 중복됩니다.");
      manifest.set(artifact.path, artifact);
    }
    const candidates = result.artifacts.filter(item => /(?:^|\/)fea_field\.json$/.test(item.path));
    if (!candidates.length) return freeze({ status: "unavailable", entries: [], reason: "이 기록에는 전체 절점 U가 등록된 FEA 필드가 없습니다. 기존 결과와 원본 파일은 보존됩니다." });
    const provenance = result.provenance, details = provenance.adapter_details, proposal = saved.proposal, thread = saved.thread;
    assert(sha(result.cad_revision) && id(result.parent_experiment_id) && result.parent_experiment_id !== result.experiment_id &&
      ["5", "6"].includes(provenance.adapter_version) && object(details) && details.adapter === "fixture.calculix" &&
      details.adapter_version === provenance.adapter_version && details.parent_experiment_id === result.parent_experiment_id &&
      details.cad_revision === result.cad_revision && provenance.parent_experiment_id === result.parent_experiment_id,
    "부모 CAD·현재 개정·결과 생산 adapter의 연결이 일치하지 않습니다.");
    assert(object(proposal) && proposal.id === result.experiment_id && proposal.parent_experiment_id === result.parent_experiment_id &&
      proposal.model?.geometry?.source_experiment_id === result.parent_experiment_id && proposal.model.geometry.cad_revision === result.cad_revision &&
      proposal.physics?.backend === "fixture.calculix" && equal(proposal.execution, provenance.execution_settings) &&
      thread?.experiment === result.experiment_id && thread.parent_experiment === result.parent_experiment_id && thread.cad_revision === result.cad_revision,
    "실험·입력·thread가 같은 부모 CAD 개정을 참조하지 않습니다.");
    assert(["COMPLETED", "CONVERGED"].includes(result.solver_status) && result.decision === "NOT_RELEASED" &&
      Array.isArray(result.validations) && object(result.metrics), "완료된 원본 관측과 미승인 상태를 확인할 수 없습니다.");
    const sizes = details.mesh_max_sizes_mm, executionMesh = proposal.execution?.mesh;
    assert(Array.isArray(sizes) && equal(sizes, executionMesh?.max_sizes_mm) && sizes.length >= 1 && sizes.length <= 8 &&
      sizes.every((size, i) => finite(size) && size > 0 && (i === 0 || sizes[i - 1] > size)) &&
      (executionMesh.mode === "selected" ? provenance.adapter_version === "6" && sizes.length === 1 : executionMesh.mode === undefined && sizes.length >= 2),
    "기록된 메시 레벨과 선택 메시 정책이 일치하지 않습니다.");
    if (executionMesh.mode === "selected") assert(details.mesh_policy?.mode === "selected" && details.mesh_sensitivity?.status === "NOT_ASSESSED" &&
      result.metrics.displacement_mesh_change_ratio?.valid === false && result.metrics.displacement_mesh_change_ratio.value === null,
    "선택 메시의 민감도 미평가 상태가 원본 판정과 다릅니다.");
    const entries = candidates.map(artifact => {
      const match = /^simulation\/support_([0-7])\/fea_field\.json$/.exec(artifact.path);
      assert(match && artifact.mime_type === "application/json" && artifact.size_bytes > 0 && artifact.size_bytes <= LIMITS.bytes,
        "지원하는 단일 fixture FEA JSON 경로가 아니거나 화면의 32 MiB 범위를 넘습니다.");
      const index = Number(match[1]); assert(index < sizes.length, "필드의 메시 레벨이 현재 해석 설정에 없습니다.");
      return { path: artifact.path, sha256: artifact.sha256, size_bytes: artifact.size_bytes, index, size_mm: sizes[index] };
    }).sort((a, b) => a.index - b.index);
    const output = freeze({ status: "available", entries }); contexts.set(output, { saved, manifest }); return output;
  }
  // Canonical C3D10 faces retain corner-to-midside edge associations.
  const FACES = [[0, 1, 2, 4, 5, 6], [0, 3, 1, 7, 8, 4], [1, 3, 2, 8, 9, 5], [2, 3, 0, 9, 7, 6]];
  function faceKey(ids) {
    const edges = [[0, 1, 3], [1, 2, 4], [2, 0, 5]].map(([a, b, mid]) =>
      [Math.min(ids[a], ids[b]), Math.max(ids[a], ids[b]), ids[mid]]).sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    return { corners: [...ids.slice(0, 3)].sort((a, b) => a - b).join(","), edges: JSON.stringify(edges) };
  }
  function vector(value, length = 3) { return Array.isArray(value) && value.length === length && value.every(finite); }
  function nativeCatalog(inspection) {
    assert(inspection?.integrity === "VERIFIED", "검증된 같은 CAD 해석만 표시합니다.");
    const saved = copy(inspection), result = saved.result, proposal = saved.proposal, thread = saved.thread;
    assert(result?.provenance?.adapter === "structure.calculix.native" && result.provenance.adapter_version === "1" &&
      id(result.experiment_id) && id(result.parent_experiment_id) && sha(result.cad_revision) &&
      result.solver_status === "COMPLETED" && result.decision === "NOT_RELEASED" && Array.isArray(result.validations) &&
      proposal?.id === result.experiment_id && proposal.parent_experiment_id === result.parent_experiment_id &&
      proposal.physics?.backend === "structure.calculix.native" && proposal.model?.geometry?.source_experiment_id === result.parent_experiment_id &&
      proposal.model.geometry.cad_revision === result.cad_revision && equal(proposal.execution, result.provenance.execution_settings) &&
      thread?.experiment === result.experiment_id && thread.parent_experiment === result.parent_experiment_id && thread.cad_revision === result.cad_revision,
    "native 모델·CAD 개정·입력·결과·thread가 일치하지 않습니다.");
    assert(equal(proposal.boundary_conditions, proposal.execution.declaration?.boundary_conditions) &&
      equal(proposal.loads, proposal.execution.declaration?.loads) &&
      equal(proposal.model.materials, proposal.execution.declaration?.materials), "같은 기록의 명시적 조건이 일치하지 않습니다.");
    const manifest = new Map();
    for (const artifact of result.artifacts ?? []) {
      assert(safePath(artifact.path) && sha(artifact.sha256) && !manifest.has(artifact.path) &&
        Number.isSafeInteger(artifact.size_bytes) && artifact.size_bytes >= 0 && artifact.revision === result.cad_revision,
      "native 산출물의 경로·해시·크기·개정이 불완전합니다."); manifest.set(artifact.path, artifact);
    }
    const artifact = manifest.get("simulation/field.json");
    if (!artifact) return freeze({status:"unavailable",entries:[],reason:"이 native 기록에는 완료된 전체 절점 변위장이 없습니다."});
    assert(artifact.mime_type === "application/json" && artifact.size_bytes <= LIMITS.bytes, "화면의 native 필드 범위를 넘습니다. 원본 파일을 확인하세요.");
    const size = proposal.execution.declaration.mesh.max_size_mm;
    assert(finite(size) && size > 0, "native 선택 메시 크기가 누락됐습니다.");
    const output = freeze({status:"available",entries:[{path:artifact.path,sha256:artifact.sha256,size_bytes:artifact.size_bytes,index:0,size_mm:size}]});
    contexts.set(output, {saved,manifest,family:"native"}); return output;
  }
  function verifyNative(field, ctx, entry) {
    const result = ctx.saved.result, execution = ctx.saved.proposal.execution, native = execution.native_catalog;
    assert(field?.schema_version === "1.0" && field.kind === "native_structural_nodal_displacement" &&
      field.backend === "structure.calculix.native" && field.adapter_version === "1" &&
      field.parent_experiment_id === result.parent_experiment_id && field.cad_revision === result.cad_revision &&
      field.native_catalog_revision === native?.native_catalog_revision && sha(field.native_catalog_revision) &&
      field.coordinate_frame === "CAD_DOCUMENT_GLOBAL" && field.position_unit === "mm" && field.displacement_unit === "mm" &&
      field.force_unit === "N" && field.coverage === "ALL_MESH_NODES" && field.qualification === "UNKNOWN" && field.engineering_valid === false &&
      equal(field.static,{step:1,increment:1,load_parameter:1}) && field.mesh_size_max_mm === entry.size_mm,
    "native 전체장의 부모·개정·단위·좌표계·단계·미확인 자격이 일치하지 않습니다.");
    const names = {mesh:"mesh.json",deck:"native.inp",boundary:"boundary.json",frd:"native.frd",dat:"native.dat"};
    assert(keys(field.sources,Object.keys(names)), "native 전체장의 5개 원본 연결이 필요합니다.");
    for (const [name,filename] of Object.entries(names)) {
      const source=field.sources[name], artifact=ctx.manifest.get("simulation/"+filename);
      assert(keys(source,["path","sha256","bytes"]) && source.path===filename && artifact && source.sha256===artifact.sha256 &&
        source.bytes===artifact.size_bytes && source.bytes>0, "native 원본 해시·크기·개정이 필드와 다릅니다.");
    }
    assert(field.deck_sha256===field.sources.deck.sha256 && field.parent_step_sha256===result.provenance.adapter_details?.parent_step_sha256,
      "native deck 또는 부모 STEP 원본이 결과와 다릅니다.");
    for (const [rows,count,limit] of [[field.nodes,field.node_count,LIMITS.nodes],[field.elements,field.element_count,LIMITS.elements],
      [field.boundary_faces,field.boundary_face_count,LIMITS.faces]]) assert(Array.isArray(rows) && Number.isSafeInteger(count) &&
        count>0 && count===rows.length && count<=limit, "native 전체 절점·요소·외곽면 개수 또는 화면 범위를 확인할 수 없습니다.");
    const nodes=new Map(), elements=new Set(), faces=new Map(), used=new Set(); let last=0;
    for (const node of field.nodes) {
      assert(identifier(node.node_id) && node.node_id>last && vector(node.position_mm) && vector(node.displacement_mm) &&
        finite(Math.hypot(...node.displacement_mm)) && Array.isArray(node.displacement_tokens) && node.displacement_tokens.length===3 &&
        node.displacement_tokens.every((value,i)=>typeof value==="string" && /^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?$/.test(value) &&
          Number(value.replace(/[Dd]/,"E"))===node.displacement_mm[i]), "native 절점 ID·좌표·변위·DAT 수치가 불완전합니다.");
      nodes.set(node.node_id,node); last=node.node_id;
    }
    last=0;
    for(const element of field.elements) {
      assert(identifier(element.element_id) && element.element_id>last && element.type==="C3D10" &&
        Array.isArray(element.node_ids) && element.node_ids.length===10 && new Set(element.node_ids).size===10 &&
        element.node_ids.every(n=>nodes.has(n)), "native C3D10 원본 연결이 불완전합니다.");
      last=element.element_id; elements.add(last); element.node_ids.forEach(n=>used.add(n));
      for(const slots of FACES) { const key=faceKey(slots.map(slot=>element.node_ids[slot])), old=faces.get(key.corners);
        assert(!old || old.edges===key.edges,"native 이웃 midside 연결이 다릅니다."); const count=(old?.count??0)+1;
        assert(count<=2,"native 비다양체 요소 면입니다."); faces.set(key.corners,{edges:key.edges,count}); }
    }
    assert(used.size===nodes.size,"native 전체 절점 집합과 요소 연결이 다릅니다.");
    const exterior=new Map([...faces].filter(([,f])=>f.count===1)), nativeFaces=new Map((native.selections??[])
      .filter(f=>f.kind==="native_face").map(f=>[f.id,f])), boundary=new Set(), groups=new Map(), boundaryIds=new Set(); last=0;
    for(const face of field.boundary_faces) {
      assert(identifier(face.element_id) && face.element_id>last && !elements.has(face.element_id) && face.type==="CPS6" &&
        nativeFaces.has(face.selection_id) && Array.isArray(face.node_ids) && face.node_ids.length===6 &&
        new Set(face.node_ids).size===6 && face.node_ids.every(n=>nodes.has(n)),"native 외곽면 ID·FaceN·6절점 연결이 다릅니다.");
      last=face.element_id; const key=faceKey(face.node_ids), actual=exterior.get(key.corners);
      assert(actual?.edges===key.edges && !boundary.has(key.corners),"native 외곽면이 실제 C3D10 면과 다릅니다.");
      boundary.add(key.corners); const group=groups.get(face.selection_id)??new Set();
      face.node_ids.forEach(n=>{boundaryIds.add(n);group.add(n);}); groups.set(face.selection_id,group);
    }
    assert(boundary.size===exterior.size && groups.size===nativeFaces.size,"native 전체 외곽면 또는 catalog 면이 누락됐습니다.");
    const expectedDOF=new Map(), dofs=new Map();
    for(const bc of execution.declaration.boundary_conditions) for(const node of groups.get(bc.selection_id)??[]) {
      for(const [name,value] of Object.entries(bc.components)) { const component=["UX","UY","UZ"].indexOf(name)+1, key=node+":"+component;
        assert(component>0 && (!expectedDOF.has(key)||expectedDOF.get(key)===value),"native 선언 구속 성분이 충돌합니다."); expectedDOF.set(key,value); }
    }
    assert(Array.isArray(field.prescribed_dofs) && field.prescribed_dofs.length>0,"native 구속 원본이 없습니다.");
    for(const row of field.prescribed_dofs) { const key=row.node_id+":"+row.component;
      assert(boundaryIds.has(row.node_id) && [1,2,3].includes(row.component) && finite(row.value_mm) && !dofs.has(key) &&
        expectedDOF.get(key)===row.declared_value_mm && typeof row.value_token==="string" && row.value_token.length<=20 &&
        /^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?$/.test(row.value_token) && Number(row.value_token)===row.value_mm &&
        Math.abs(row.value_mm-row.declared_value_mm)<=5e-13*Math.abs(row.declared_value_mm),
      "native 부분 구속 성분·선언값·실제 직렬화 수치가 저장 조건과 다릅니다."); dofs.set(key,row.value_mm); }
    assert(dofs.size===expectedDOF.size,"선언된 native 구속 DOF 일부가 빠졌습니다.");
    const permittedLoadDOFs=new Set();
    for (const load of execution.declaration.loads) for (const node of groups.get(load.selection_id)??[]) {
      for (const [name,value] of Object.entries(load.components)) if (value!==0)
        permittedLoadDOFs.add(node+":"+(["FX","FY","FZ"].indexOf(name)+1));
    }
    const loads=new Map(), loadDOFs=new Set(), totals=[0,0,0];
    assert(Array.isArray(field.loads)&&field.loads.length>0,"native 절점 합력 원본이 없습니다.");
    for(const row of field.loads) { const key=row.node_id+":"+row.component;
      assert(boundaryIds.has(row.node_id) && [1,2,3].includes(row.component) && finite(row.force_N) && row.force_N!==0 &&
        !dofs.has(key) && !loadDOFs.has(key) && permittedLoadDOFs.has(key) &&
        typeof row.force_token==="string" && row.force_token.length<=20 &&
        /^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?$/.test(row.force_token) && Number(row.force_token)===row.force_N,
      "native 절점 하중 성분·수치 token·선택 면·구속 연결이 다릅니다.");
      loadDOFs.add(key); const force=loads.get(row.node_id)??[0,0,0]; force[row.component-1]=row.force_N;
      totals[row.component-1]+=row.force_N; loads.set(row.node_id,force);
    }
    const target=["FX","FY","FZ"].map(name=>execution.declaration.loads.reduce((sum,row)=>sum+row.components[name],0));
    assert(totals.every((v,i)=>Math.abs(v-target[i])<=1e-10*Math.max(1,Math.abs(target[i]))),"native 절점 합력이 선언 성분과 다릅니다.");
    const peak=Math.max(...field.nodes.map(node=>Math.hypot(...node.displacement_mm)));
    assert(nodes.has(field.peak_node_id) && Math.abs(Math.hypot(...nodes.get(field.peak_node_id).displacement_mm)-peak)<=
      8*Number.EPSILON*Math.max(peak,Number.MIN_VALUE), "native 최대 변위 절점 ID가 전체장과 다릅니다.");
    const recordedPeak=result.metrics?.max_displacement?.value;
    assert(finite(peak) && finite(recordedPeak) && Math.abs(recordedPeak-peak)<=8*Number.EPSILON*Math.max(peak,recordedPeak,Number.MIN_VALUE) && result.metrics.max_displacement.unit==="mm",
      "native 전체 |U| 최대값이 같은 결과의 관측값과 다릅니다.");
    const normalized=copy(field); normalized.mesh_index=0;
    normalized.boundary_faces=field.boundary_faces.map(face=>({...copy(face),group:nativeFaces.get(face.selection_id).native_name}));
    normalized.fixed_node_ids=[...new Set(field.prescribed_dofs.map(row=>row.node_id))].sort((a,b)=>a-b);
    normalized.loads=[...loads].sort((a,b)=>a[0]-b[0]).map(([node_id,force_N])=>({node_id,force_N}));
    const model=freeze({field:normalized,rawNative:copy(field),artifact:copy(entry),metadata:{family:"native",experimentId:result.experiment_id,
      parentId:result.parent_experiment_id,revision:result.cad_revision,fieldProducer:field.adapter_version,
      resultProducer:result.provenance.adapter_version,coreCommit:result.provenance.core_commit??null,
      upstreamCommit:result.provenance.source_commit??null,unknownCount:result.validations.filter(v=>v.status==="UNKNOWN").length,
      sensitivity:"NOT_ASSESSED",decision:result.decision,wholeMaximumMagnitude:peak,
      nativeCatalogRevision:field.native_catalog_revision,totalForceVectorN:totals}});
    verified.add(model); return model;
  }
  function verifyAssemblyField(inspection, envelope) {
    const result = inspection?.result, proposal = inspection?.proposal, thread = inspection?.thread;
    const field = envelope?.display, backend = 'fixture.assembly_mechanics.code_aster';
    assert(inspection?.integrity === 'VERIFIED' && envelope?.integrity === 'VERIFIED' &&
      result?.provenance?.adapter === backend && result.provenance.adapter_version === '1' &&
      envelope.experiment_id === result.experiment_id && envelope.study_id === result.study.id &&
      sha(inspection.hashes?.result_sha256) && envelope.result_sha256 === inspection.hashes.result_sha256 &&
      result.solver_status === 'COMPLETED' && result.decision === 'NOT_RELEASED', '같은 조립체 결과·필드 원본 연결이 일치하지 않습니다.');
    assert(field?.schema_version === '1.0' && field.kind === 'assembly_mechanics_nodal_displacement_display' &&
      field.scope === 'BOUNDED_COMPLETE_NATIVE_ASSEMBLY_DISPLAY' && field.source_scope === 'COMPLETE_NATIVE_ASSEMBLY_MECHANICS_FIELDS' &&
      field.backend === backend && field.adapter_version === '1' && field.experiment_id === result.experiment_id &&
      field.parent_experiment_id === result.parent_experiment_id && field.cad_revision === result.cad_revision &&
      field.proposal_revision === result.proposal_revision && sha(field.mesh_revision) &&
      proposal?.id === result.experiment_id && proposal.physics?.backend === backend &&
      proposal.parent_experiment_id === result.parent_experiment_id && proposal.model?.geometry?.cad_revision === result.cad_revision &&
      equal(proposal.execution, result.provenance.execution_settings) &&
      field.mesh_revision === proposal.execution?.mesh?.mesh_revision &&
      thread?.experiment === result.experiment_id && thread.cad_revision === result.cad_revision &&
      thread.parent_experiment === result.parent_experiment_id, 'CAD·메시·선언 조건·필드가 같은 개정을 참조하지 않습니다.');
    assert(field.position_unit === 'mm' && field.displacement_unit === 'mm' && field.force_unit === 'N' &&
      field.coordinate_frame === 'global_assembly_cartesian_mm' && field.coverage === 'ALL_ORIGINAL_MESH_NODES' &&
      field.static?.axis_semantics === 'DIMENSIONLESS_STATIC_LOAD_PARAMETER_NOT_PHYSICAL_TIME' &&
      Number.isSafeInteger(field.static.order) && field.static.order >= 1 && field.static.load_parameter === 1 &&
      field.qualification === 'UNKNOWN' && field.engineering_valid === false && field.decision === 'NOT_RELEASED' &&
      equal(field.metrics, result.metrics) && equal(field.validations, result.validations), '전체 필드의 축·단위·미확인 판정이 다릅니다.');
    const manifest = new Map();
    for (const entry of result.artifacts ?? []) {
      assert(safePath(entry.path) && sha(entry.sha256) && !manifest.has(entry.path) &&
        Number.isSafeInteger(entry.size_bytes) && entry.size_bytes >= 0 && entry.revision === result.cad_revision,
        '원 조립체 산출물의 경로·해시·크기·개정이 불완전합니다.'); manifest.set(entry.path, entry);
    }
    assert(Array.isArray(field.source_artifacts) && field.source_artifacts.length >= 2 && field.source_artifacts.length <= 64,
      '필드·원본 메시의 기록된 근거가 필요합니다.');
    const sources = {};
    for (const entry of field.source_artifacts) {
      assert(equal(entry, manifest.get(entry.path)) && !Object.hasOwn(sources, entry.path), '화면 필드의 원본 근거가 manifest와 다릅니다.');
      sources[entry.path] = {path: entry.path, bytes: entry.size_bytes, sha256: entry.sha256};
    }
    const artifact = manifest.get('simulation/admitted-fields.json');
    assert(artifact && Object.hasOwn(sources, artifact.path) && Object.hasOwn(sources, 'simulation/mesh-reuse/mapping.json') &&
      field.native_gauss?.artifact === artifact.path && field.native_gauss.sha256 === artifact.sha256 &&
      field.native_gauss.location === 'NATIVE_TETRA10_FPG5_GAUSS_POINTS' && field.native_gauss.nodal_stress === 'NOT_CONSTRUCTED' &&
      field.native_gauss.displayed === false, '원 Gauss 응력을 절점 응력으로 바꾸거나 원본 참조를 바꿀 수 없습니다.');
    assert(Array.isArray(field.nodes) && field.nodes.length === field.node_count && field.node_count > 0 && field.node_count <= 100000 &&
      Array.isArray(field.elements) && field.elements.length === field.element_count && field.element_count > 0 && field.element_count <= 60000 &&
      Array.isArray(field.boundary_faces) && field.boundary_faces.length === field.boundary_face_count && field.boundary_face_count > 0 && field.boundary_face_count <= 25000 &&
      Array.isArray(field.source_nodes) && field.source_nodes.length === field.node_count && Array.isArray(field.bodies) && field.bodies.length === 7,
      '원 조립체 전체 절점·체적·표면 연결 또는 표시 범위가 다릅니다.');
    assert(field.native_gauss.point_count === 5*field.element_count, '완전한 TETRA10 FPG5 응력의 원본 참조가 필요합니다.');
    const original = new Map(), nodes = new Map(), bodies = new Map(field.bodies.map(body => [body.component_id, body]));
    assert(bodies.size === 7 && bodies.size === new Set(proposal.execution.catalog.retained_mesh.active_components).size &&
      proposal.execution.catalog.retained_mesh.active_components.every(body => bodies.has(body)), '활성 부품 범위가 선언 메시와 다릅니다.');
    field.source_nodes.forEach(node => { assert(identifier(node.id) && vector(node.xyz_mm) && !original.has(node.id), '원본 절점 ID·XYZ가 불완전합니다.'); original.set(node.id,node); });
    const indexMap = field.identity?.source_node_ids_by_native_index;
    assert(field.identity?.status === 'PASS' && Array.isArray(indexMap) && indexMap.length === field.node_count &&
      new Set(indexMap).size === field.node_count, '이번 native import와 원 ID 연결이 불완전합니다.');
    for (const node of field.nodes) {
      const source = original.get(node.node_id);
      assert(source && !nodes.has(node.node_id) && bodies.has(node.component_id) && Number.isSafeInteger(node.native_index) &&
        indexMap[node.native_index] === node.node_id && vector(node.position_mm) && vector(node.displacement_mm) && vector(node.reaction_n) &&
        node.position_mm.every((v,i) => Math.abs(v-source.xyz_mm[i]) <= 1e-12), '동일 좌표의 다른 부품을 합치거나 실제 절점 응답을 추정할 수 없습니다.');
      nodes.set(node.node_id,node);
    }
    const elements = new Map(), faces = new Map();
    for (const [items,count,type] of [[field.elements,10,'TETRA10'],[field.boundary_faces,6,'TRIA6']]) for (const element of items) {
      const target = type === 'TETRA10' ? elements : faces;
      assert(identifier(element.element_id) && !target.has(element.element_id) && element.type === type && bodies.has(element.component_id) &&
        Array.isArray(element.node_ids) && element.node_ids.length === count && new Set(element.node_ids).size === count &&
        element.node_ids.every(n => nodes.get(n)?.component_id === element.component_id), '원본 요소 또는 부품별 연결이 불완전합니다.');
      target.set(element.element_id, element);
    }
    assert(Array.isArray(field.display_triangles) && field.display_triangles.length === 4*field.boundary_face_count &&
      field.display_triangles.length <= 100000 && field.display_geometry === 'FOUR_LINEAR_TRIANGLES_PER_TRIA6_WITH_DERIVED_OUTWARD_WINDING',
      '표시 삼각형은 원 TRIA6의 명시적 선형 표시여야 합니다.');
    for (const triangle of field.display_triangles) {
      const face = faces.get(triangle.face_id), owner = elements.get(triangle.owner_element_id);
      assert(face && owner && face.component_id === owner.component_id && triangle.component_id === face.component_id &&
        Array.isArray(triangle.node_ids) && triangle.node_ids.length === 3 && new Set(triangle.node_ids).size === 3 &&
        triangle.node_ids.every(n => face.node_ids.includes(n)), '표시 외곽면이 다른 부품·요소를 참조합니다.');
    }
    const application = result.provenance.adapter_details?.native_application;
    assert(application && Array.isArray(application.boundary_conditions) && Array.isArray(application.loads), '실제 적용한 구속·하중 기록이 필요합니다.');
    const prescribed = [], constrained = new Map(), forces = new Map();
    application.boundary_conditions.forEach(row => row.source_node_ids.forEach(n => {
      assert(nodes.has(n), '구속 원 절점이 필드에 없습니다.');
      for (const [key,value] of Object.entries(row.components)) {
        const component = ['DX','DY','DZ'].indexOf(key)+1; assert(component > 0 && finite(value), '원 지정 DOF·값이 필요합니다.');
        prescribed.push({node_id:n,component,value_mm:value});
        const dofs = constrained.get(n) ?? new Map(); assert(!dofs.has(component),'중복 native 구속입니다.'); dofs.set(component,value); constrained.set(n,dofs);
      }
    }));
    application.loads.forEach(row => row.source_node_ids.forEach(n => {
      assert(nodes.has(n) && vector(['FX','FY','FZ'].map(k=>row.per_node_components_N[k])), '실제 절점 하중·원 ID가 필요합니다.');
      const force = forces.get(n) ?? [0,0,0]; ['FX','FY','FZ'].forEach((key,i)=> { force[i] += row.per_node_components_N[key]; }); forces.set(n,force);
    }));
    const normalized = copy(field); normalized.sources = sources; normalized.mesh_size_max_mm = 3;
    normalized.fixed_node_ids = [...constrained].filter(([,dofs])=>dofs.size===3 && [...dofs.values()].every(v=>v===0)).map(([n])=>n);
    normalized.loads = [...forces].map(([node_id,force_N])=>({node_id,force_N})); normalized.fixed_dofs = ['UX','UY','UZ'];
    normalized.boundary_faces = normalized.boundary_faces.map(face=>({...face,group:face.physical_group}));
    const peak = Math.max(...[...nodes.values()].map(node=>Math.hypot(...node.displacement_mm)));
    assert(finite(peak) && result.metrics.max_displacement?.unit === 'mm' && result.metrics.max_displacement.valid === true &&
      Math.abs(peak-result.metrics.max_displacement.value) <= 8*Number.EPSILON*Math.max(peak,Number.MIN_VALUE), '전체 |U| 최대값이 원 결과와 다릅니다.');
    const total = [0,1,2].map(i=>[...forces.values()].reduce((sum,force)=>sum+force[i],0));
    const model = freeze({field:normalized, rawNative:{prescribed_dofs:prescribed,loads:normalized.loads}, artifact:copy(artifact),
      metadata:{family:'assembly', experimentId:result.experiment_id,parentId:result.parent_experiment_id,revision:result.cad_revision,
        fieldProducer:'1',resultProducer:result.provenance.adapter_version,coreCommit:result.provenance.core_commit,
        upstreamCommit:result.provenance.source_commit,unknownCount:result.validations.filter(v=>v.status==='UNKNOWN').length,
        sensitivity:'NOT_ASSESSED',decision:'NOT_RELEASED',wholeMaximumMagnitude:peak,
        nativeCatalogRevision:result.provenance.analysis_conditions?.catalog_revision,totalForceVectorN:total}});
    verified.add(model); return model;
  }
  function verify(field, ctx, entry) {
    const result = ctx.saved.result, version = result.provenance.adapter_version;
    assert(keys(field, ["schema_version", "kind", "backend", "adapter_version", "parent_experiment_id", "cad_revision", "mesh_index", "mesh_size_max_mm", "coordinate_frame", "position_unit", "displacement_unit", "force_unit", "static", "coverage", "qualification", "engineering_valid", "nodes", "elements", "boundary_faces", "fixed_node_ids", "fixed_dofs", "loads", "node_count", "element_count", "boundary_face_count", "sources"]), "FEA 필드 선언이 불완전합니다.");
    assert(field.schema_version === "1.0" && field.kind === "fixture_calculix_nodal_displacement" && field.backend === "fixture.calculix" &&
      ["5", "6"].includes(field.adapter_version) && Number(field.adapter_version) <= Number(version) &&
      field.parent_experiment_id === result.parent_experiment_id && field.cad_revision === result.cad_revision &&
      field.mesh_index === entry.index && field.mesh_size_max_mm === entry.size_mm &&
      field.coordinate_frame === "SOLVER_GLOBAL_CARTESIAN" && field.position_unit === "mm" && field.displacement_unit === "mm" && field.force_unit === "N" &&
      field.coverage === "ALL_MESH_NODES" && field.qualification === "UNKNOWN" && field.engineering_valid === false &&
      keys(field.static, ["step", "increment", "load_parameter"]) && field.static.step === 1 && field.static.increment === 1 && field.static.load_parameter === 1,
    "필드 생산 버전·부모·개정·단위·좌표계·완전 범위·정적 단계가 일치하지 않습니다.");
    assert(keys(field.sources, ["mesh", "deck", "saddle", "frd", "dat"]), "5개 native 원본 연결이 필요합니다.");
    const names = { mesh: "gmsh.inp", deck: `support_${entry.index}.inp`, saddle: "saddle_load.json", frd: `support_${entry.index}.frd`, dat: `support_${entry.index}.dat` };
    const prefix = entry.path.slice(0, entry.path.lastIndexOf("/") + 1);
    for (const [name, filename] of Object.entries(names)) {
      const source = field.sources[name], artifact = ctx.manifest.get(prefix + filename);
      assert(keys(source, ["path", "sha256", "bytes"]) && source.path === filename && sha(source.sha256) &&
        Number.isSafeInteger(source.bytes) && source.bytes > 0 && artifact && artifact.revision === result.cad_revision &&
        artifact.sha256 === source.sha256 && artifact.size_bytes === source.bytes, "필드의 5개 원본 해시·크기·같은 개정 연결이 일치하지 않습니다.");
    }
    for (const [rows, count, limit] of [[field.nodes, field.node_count, LIMITS.nodes], [field.elements, field.element_count, LIMITS.elements], [field.boundary_faces, field.boundary_face_count, LIMITS.faces]]) {
      assert(Array.isArray(rows) && Number.isSafeInteger(count) && count > 0 && count === rows.length && count <= limit,
        "전체 절점·요소·외곽면 개수 또는 화면의 항목 범위를 확인할 수 없습니다.");
    }
    const nodes = new Map(); let last = 0;
    for (const node of field.nodes) {
      assert(keys(node, ["node_id", "position_mm", "displacement_mm", "displacement_tokens"]) && identifier(node.node_id) && node.node_id > last &&
        vector(node.position_mm) && vector(node.displacement_mm) && finite(Math.hypot(...node.displacement_mm)) &&
        Array.isArray(node.displacement_tokens) && node.displacement_tokens.length === 3 && node.displacement_tokens.every((token, i) =>
          typeof token === "string" && !/\s/.test(token) && /^[-+]?\d\.\d{5}E[-+]\d{2,3}$/.test(token) && Number(token) === node.displacement_mm[i]),
      "모든 절점의 원본 ID·좌표·U 3성분·native 수치가 유한하고 완전해야 합니다.");
      nodes.set(node.node_id, node); last = node.node_id;
    }
    const faces = new Map(), elementIds = new Set(), used = new Set(); last = 0;
    for (const element of field.elements) {
      assert(keys(element, ["element_id", "type", "node_ids"]) && identifier(element.element_id) && element.element_id > last &&
        element.type === "C3D10" && Array.isArray(element.node_ids) && element.node_ids.length === 10 &&
        new Set(element.node_ids).size === 10 && element.node_ids.every(node => nodes.has(node)), "C3D10 원본 ID·10절점 연결이 불완전합니다.");
      last = element.element_id; elementIds.add(last); element.node_ids.forEach(node => used.add(node));
      for (const slots of FACES) {
        const key = faceKey(slots.map(slot => element.node_ids[slot])), old = faces.get(key.corners);
        assert(!old || old.edges === key.edges, "이웃 요소의 midside 절점 연결이 일치하지 않습니다.");
        const count = (old?.count ?? 0) + 1; assert(count <= 2, "비다양체 요소 면은 표시할 수 없습니다."); faces.set(key.corners, { edges: key.edges, count });
      }
    }
    assert(used.size === nodes.size, "U 절점 집합이 전체 요소 연결과 일치하지 않습니다.");
    const exterior = new Map([...faces].filter(([, value]) => value.count === 1)), boundary = new Set(), boundaryIds = new Set(), groups = new Map(); last = 0;
    for (const face of field.boundary_faces) {
      assert(keys(face, ["element_id", "type", "group", "node_ids"]) && identifier(face.element_id) && face.element_id > last && !elementIds.has(face.element_id) &&
        face.type === "CPS6" && typeof face.group === "string" && !/\s/.test(face.group) && /^[A-Z][A-Z0-9_]{0,63}$/.test(face.group) &&
        Array.isArray(face.node_ids) && face.node_ids.length === 6 && new Set(face.node_ids).size === 6 && face.node_ids.every(node => nodes.has(node)),
      "CPS6 외곽면의 원본 ID·그룹·6절점 연결이 불완전합니다.");
      last = face.element_id; const key = faceKey(face.node_ids), actual = exterior.get(key.corners);
      assert(actual?.edges === key.edges && !boundary.has(key.corners), "CPS6가 C3D10의 완전한 외곽면과 일치하지 않습니다.");
      boundary.add(key.corners); const group = groups.get(face.group) ?? new Set();
      face.node_ids.forEach(node => { boundaryIds.add(node); group.add(node); }); groups.set(face.group, group);
    }
    assert(boundary.size === exterior.size, "전체 C3D10 외곽면의 일부가 빠져 있습니다.");
    assert(Array.isArray(field.fixed_node_ids) && field.fixed_node_ids.length > 0 && equal(field.fixed_dofs, [1, 2, 3]), "실제 고정 XYZ 절점 집합이 없습니다.");
    const fixed = new Set(); last = 0;
    for (const node of field.fixed_node_ids) { assert(identifier(node) && node > last && boundaryIds.has(node), "고정 절점 집합이 중복되거나 외곽면과 다릅니다."); fixed.add(node); last = node; }
    const minZ = Math.min(...field.nodes.map(node => node.position_mm[2]));
    assert(field.nodes.every(node => fixed.has(node.node_id) === (Math.abs(node.position_mm[2] - minZ) < 1e-4)), "고정 절점이 기록된 전체 바닥 면과 일치하지 않습니다.");
    assert(Array.isArray(field.loads) && field.loads.length > 0 && field.loads.length <= nodes.size, "실제 saddle 하중 절점이 없습니다.");
    const loaded = new Set(); let force = 0; last = 0;
    for (const load of field.loads) {
      assert(keys(load, ["node_id", "force_N", "dof", "force_token"]) && identifier(load.node_id) && load.node_id > last &&
        boundaryIds.has(load.node_id) && !fixed.has(load.node_id) && load.dof === 3 && vector(load.force_N) && load.force_N[0] === 0 && load.force_N[1] === 0 && load.force_N[2] < 0 &&
        typeof load.force_token === "string" && !/\s/.test(load.force_token) && /^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?$/.test(load.force_token) &&
        Number(load.force_token.replace(/[Dd]/, "E")) === load.force_N[2], "실제 하중 ID·방향·N 값과 고정 절점의 연결이 일치하지 않습니다.");
      loaded.add(load.node_id); last = load.node_id; force -= load.force_N[2];
    }
    const saddles = [...groups].filter(([, members]) => [...loaded].every(node => members.has(node)));
    assert(saddles.length === 1, "하중 절점이 하나의 기록된 saddle 표면 그룹에 연결되지 않습니다.");
    const expectedForce = result.provenance.adapter_details.force_per_support_N;
    assert(finite(force) && finite(expectedForce) && expectedForce > 0 && Math.abs(force - expectedForce) <= 1e-8 * expectedForce,
      "직렬화된 절점 하중 합이 기록된 지지부당 하중과 다릅니다.");
    const study = result.provenance.adapter_details.per_mesh_displacement?.studies?.[entry.index];
    assert(study?.index === entry.index && study.mesh_size_max_mm === entry.size_mm && study.loaded_node_count === loaded.size &&
      study.displacement_table === prefix + names.dat && study.displacement_table_sha256 === field.sources.dat.sha256,
    "기존 하중 안장 통계와 같은 메시의 DAT 연결이 아닙니다.");
    const model = freeze({ field: copy(field), artifact: copy(entry), metadata: { experimentId: result.experiment_id, parentId: result.parent_experiment_id,
      revision: result.cad_revision, fieldProducer: field.adapter_version, resultProducer: version, coreCommit: result.provenance.core_commit ?? null,
      upstreamCommit: result.provenance.source_commit ?? null, unknownCount: result.validations.filter(item => item.status === "UNKNOWN").length,
      sensitivity: result.provenance.adapter_details.mesh_sensitivity?.status ?? "RECORDED_SCREEN", decision: result.decision,
      loadedMaximumUz: result.metrics.max_displacement?.value ?? null, saddleGroup: saddles[0][0], totalForceN: force } });
    verified.add(model); return model;
  }
  function strictJSON(bytes) {
    const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes); let at = 0;
    const space = () => { while (/[ \t\r\n]/.test(text[at] ?? "") && at < text.length) at++; };
    function string() {
      const start = at++; while (at < text.length) { const c = text[at++]; if (c === "\\") at++; else if (c === '"') return JSON.parse(text.slice(start, at)); }
      throw new Error("JSON 문자열이 끝나지 않았습니다.");
    }
    function value(depth) {
      assert(depth <= 12, "필드 JSON의 중첩 범위를 넘습니다."); space();
      if (text[at] === "{") {
        at++; space(); const seen = new Set(); if (text[at] === "}") { at++; return; }
        while (true) { assert(text[at] === '"', "JSON key가 잘못되었습니다."); const key = string(); assert(!seen.has(key), "중복 JSON key가 있습니다."); seen.add(key); space(); assert(text[at++] === ":", "JSON key가 잘못되었습니다."); value(depth + 1); space(); const c = text[at++]; if (c === "}") return; assert(c === ",", "JSON 객체가 잘못되었습니다."); space(); }
      }
      if (text[at] === "[") { at++; space(); if (text[at] === "]") { at++; return; } while (true) { value(depth + 1); space(); const c = text[at++]; if (c === "]") return; assert(c === ",", "JSON 배열이 잘못되었습니다."); } }
      if (text[at] === '"') { string(); return; }
      const token = /^(?:-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null)/.exec(text.slice(at)); assert(token, "JSON 수치·값이 잘못되었습니다."); at += token[0].length;
    }
    value(0); space(); assert(at === text.length, "JSON 뒤에 다른 내용이 있습니다."); return JSON.parse(text);
  }
  function current(isCurrent) { assert(typeof isCurrent === "function" && isCurrent() === true, "선택한 결과·저장소가 바뀌었습니다."); }
  async function loadField(record, entry, fetchBytes, isCurrent) {
    current(isCurrent); const ctx = contexts.get(record); assert(ctx && record.entries.includes(entry), "검증한 같은 기록의 필드 선택이 필요합니다.");
    assert(typeof fetchBytes === "function", "원본 파일 읽기가 필요합니다.");
    const original = await fetchBytes(entry.path, entry.size_bytes); current(isCurrent);
    assert(original instanceof Uint8Array && original.byteLength === entry.size_bytes && original.byteLength <= LIMITS.bytes, "필드 원본 바이트 크기가 manifest와 다릅니다.");
    const bytes = Uint8Array.from(original), crypto = root.crypto ?? (typeof module !== "undefined" && module.exports ? require("node:crypto").webcrypto : null);
    assert(crypto?.subtle, "원본 SHA-256 검사를 사용할 수 없습니다.");
    const hash = await crypto.subtle.digest("SHA-256", bytes); current(isCurrent);
    assert(Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, "0")).join("") === entry.sha256, "필드 원본 SHA-256이 manifest와 다릅니다.");
    const model = (ctx.family === "native" ? verifyNative : verify)(strictJSON(bytes), ctx, entry); current(isCurrent); return model;
  }
  function verifyField(field, inspection, path) {
    const record = catalog(inspection), entry = record.entries.find(item => item.path === path); assert(entry, "manifest의 필드 경로가 필요합니다.");
    const ctx=contexts.get(record); return (ctx.family === "native" ? verifyNative : verify)(field, ctx, entry);
  }
  function requireVerified(model) { assert(verified.has(model), "완전한 같은 기록 필드 검증 후에만 표시합니다."); return model; }
  function responseSelection(model, nodeId, component) {
    requireVerified(model);
    assert(identifier(nodeId) && COMPONENTS.includes(component), "정확한 원 절점 ID와 변위 성분을 선택하세요.");
    const selected = model.field.nodes.find(node => node.node_id === nodeId);
    assert(selected && finite(scalar(selected, component)), "같은 메시의 실제 절점 응답이 아닙니다.");
    return Object.freeze({ artifact: model.artifact.path, sha256: model.artifact.sha256,
      cad_revision: model.metadata.revision, node_id: nodeId, component });
  }
  function scalar(node, component) { assert(COMPONENTS.includes(component), "지원하는 U 성분을 선택하세요."); return component === "MAGNITUDE" ? Math.hypot(...node.displacement_mm) : node.displacement_mm[COMPONENTS.indexOf(component)]; }
  function displayPosition(node, factor) {
    assert(finite(factor) && factor >= 0 && factor <= LIMITS.factor, "보기 배율은 0~1000의 유한한 수치여야 합니다.");
    const position = node.position_mm.map((value, i) => value + factor * node.displacement_mm[i]); assert(vector(position), "보기 좌표의 수치 범위를 넘었습니다."); return position;
  }
  const api = { LIMITS, COMPONENTS, catalog, loadField, verifyField, verifyAssemblyField, requireVerified, scalar, displayPosition, responseSelection };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.fixtureFieldControls = api;
})(globalThis);
