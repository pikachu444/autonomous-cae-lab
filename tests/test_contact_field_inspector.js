"use strict";

const test = require("node:test"), assert = require("node:assert/strict");
const fs = require("node:fs"), path = require("node:path"), vm = require("node:vm"), crypto = require("node:crypto");
const sourcePath = path.resolve(__dirname, "../apps/lab/static/contact-field-inspector.js");
const readerSource = fs.readFileSync(sourcePath, "utf8");
const { loadContactField } = require(sourcePath);
let repo = __dirname;
while (!fs.existsSync(path.join(repo, "PROJECT_SCOPE.md"))) {
  const parent = path.dirname(repo); if (parent === repo) throw Error("Repository test assets unavailable"); repo = parent;
}
const assets = path.join(repo, "benchmarks/input-data/codeaster");
const clone = value => JSON.parse(JSON.stringify(value));
const sha = bytes => crypto.createHash("sha256").update(bytes).digest("hex");
const digest = value => sha(Buffer.from(JSON.stringify(value)));
const A = "simulation/", L = `${A}level_0/`, CASE = "ssnp121a_frictionless_patch", BACKEND = "structural.code_aster.contact_patch";
const UPSTREAM = "50ebc13c70ee9df62faf93ddcb746a3757b3042a";
const NAME = "ssnp121a-17.4.0.uniform_quad4_2x.profile.json";
function asset(name) { return fs.readFileSync(path.join(assets, name)); }
function browser(cryptoApi = crypto.webcrypto) {
  const window = { crypto: cryptoApi };
  const sandbox = { window, TextDecoder, TextEncoder, Uint8Array, console };
  vm.createContext(sandbox); vm.runInContext(readerSource, sandbox, { filename: sourcePath });
  return window.contactFieldInspector;
}
function fixture(refined = false) {
  // These tracked assets supply exact admitted geometry/source identities, never solver output.
  // Every field value/raw row and all retained-envelope metadata below are independent UNSOLVED fixtures.
  const bytes = new Map(), docs = new Map();
  const put = (name, data) => { docs.set(name, clone(data)); bytes.set(name, Buffer.from(JSON.stringify(data))); };
  const putBytes = (name, value) => { bytes.set(name, Buffer.from(value)); if (name.endsWith(".json")) docs.set(name, JSON.parse(value)); };
  const frozenName = `ssnp121a-17.4.0${refined ? ".uniform_quad4_2x" : ""}.mesh.json`;
  putBytes(`${A}frozen_mesh.json`, asset(frozenName));
  putBytes(`${A}reference_specification.json`, fs.readFileSync(path.join(repo, "benchmarks/specifications/contact-patch-ssnp121a-v1.json")));
  const frozen = docs.get(`${A}frozen_mesh.json`), n = frozen.coordinates_in_native_order.length;
  const settings = { case: CASE, material: { youngs_modulus_pa: 2e6, poisson_ratio: 0 }, top_displacement_m: -0.1,
    limits: { reference_relative: 0.01, force_balance_relative: 1e-6 }, ...(refined ? { mesh_variant: "uniform_quad4_2x" } : {}) };
  const levelKeys = ["0", "-1"], cells = [], mapping = [], bySource = new Map();
  // Body cells come first in this independent fixture, defeating an assumed SEG2 offset.
  for (const level of levelKeys) frozen.levels[level].cell_connectivity_in_native_order.forEach((conn, id) => {
    const nativeId = cells.length, type = level === "0" ? "QUAD4" : "SEG2";
    cells.push({cell_id:nativeId, cell_type:type, node_ids:conn}); mapping.push({native_cell_id:nativeId,source_level:level,source_cell_id:id});
    bySource.set(`${level}:${id}`, nativeId);
  });
  const groups = {}, boundaries = {}, nodeGroups = {};
  for (const [name, row] of Object.entries(frozen.node_groups)) nodeGroups[name] = row.node_ids;
  for (const level of levelKeys) for (const [name, group] of Object.entries(frozen.levels[level].groups)) {
    groups[name] = group.cell_ids.map(id => bySource.get(`${level}:${id}`));
    if (level === "-1") boundaries[name] = [...new Set(groups[name].flatMap(id => cells[id].node_ids))].sort((a,b) => a-b);
  }
  for (const name of ["AB","CD","EF","FG","GH","HE"]) nodeGroups[name] = boundaries[name];
  const coordinates = frozen.coordinates_in_native_order.map(row => [...row, 0]);
  const mesh = {schema_version:"1",node_indexing:"ZERO_BASED_CODE_ASTER_UNRENUMBERED",node_ids:Array.from({length:n},(_,i)=>i),
    coordinates_m:coordinates,native_node_names:null,cells,group_cell_ids:groups,group_node_ids:nodeGroups};
  put(`${L}mesh_catalog.json`, mesh);
  const meshBytes = asset(`ssnp121a-17.4.0${refined ? ".uniform_quad4_2x" : ""}.mmed`);
  putBytes(`${L}mesh.mmed`, meshBytes);
  let profile, recipe;
  if (refined) {
    putBytes(`${A}${NAME}`, asset(NAME)); profile = docs.get(`${A}${NAME}`);
    putBytes(`${A}mesh_generation_recipe.json`, asset("ssnp121a-17.4.0.uniform_quad4_2x.generation.json")); recipe = docs.get(`${A}mesh_generation_recipe.json`);
    putBytes(`${A}source_parent_mesh.json`, asset("ssnp121a-17.4.0.mesh.json"));
    putBytes(`${A}source_parent.mmed`, asset("ssnp121a-17.4.0.mmed"));
    putBytes(`${A}selected_source.mmed`, meshBytes);
    putBytes(`${A}codeaster_contact_mesh.py`, fs.readFileSync(path.join(repo,"caelab/adapters/codeaster_contact_mesh.py")));
  }
  const policy = { modelisation:"D_PLAN",relation:"ELAS",deformation:"PETIT",convergence:{ARRET:"OUI",RESI_GLOB_MAXI:2e-8} };
  const runtime = {version:"17.4.0",branch:"v17.4.0",parentid:"fixture_UNSOLVED"}, versions={code_aster:"17.4.0",python:"fixture"};
  const rawIds = Array.from({length:n},(_,i)=>String(9000+((i*17)%n))); // Not node+1, and shuffled raw table rows below.
  const rawReactions = rawIds.map(id=>`rf-${id}`);
  const u=Array.from({length:n},(_,i)=>[i+0.125,-i-0.25]), rf=Array.from({length:n},(_,i)=>[-i-100.5,i+200.75]);
  const slaveIds=boundaries.AB, pressures=slaveIds.map((id,i)=>-10000-id-i/8);
  const stressIds=[], stresses=[], xy=[], weights=[];
  for (const cell of cells.filter(c=>c.cell_type==="QUAD4")) for (let point=1;point<=4;point++) {
    const i=stressIds.length;
    stressIds.push({cell_id:cell.cell_id,order:1,point,subpoint:1,raw_element_identifier:`cell-${100000+cell.cell_id*19}`});
    stresses.push([100+i,-200-i,300+i,-400-i]); xy.push([cell.cell_id+point/8,-cell.cell_id-point/16]); weights.push((i+1)/1e6);
  }
  const weightProvenance={basis:"Independent synthetic X/Y/W values; no numerical qualification",
    identity_check:"Synthetic fixture, not native measurement",native_component:"EGGAU2D.W",raw_table_column:"COOR_Z",unit:"m^2",
    upstream_tag:"17.4.0",upstream_commit:UPSTREAM,
    source_chain:["catalo/cataelem/Elements/meca_d_plan.py: COOR_ELGA/EGGAU2D",
      "catalo/cataelem/Commons/located_components.py: EGGAU2D X,Y,W",
      "bibfor/utilitai/ctdata.F90: COOR_ELGA extraction",
      "bibfor/utilitai/cteltb.F90: third extracted component labelled COOR_Z"]};
  const fields={node_indexing:mesh.node_indexing,actual_result_order:1,load_parameter:1,node_ids:mesh.node_ids,coordinates_m:coordinates,
    raw_node_identifiers:rawIds,raw_reaction_node_identifiers:rawReactions,displacement_component_order:["dx","dy"],displacements_m:u,
    nodal_reactions_n_per_m:rf,stress_component_order:["xx","yy","zz","xy"],stresses_pa:stresses,
    stress_point_coordinates_m:xy,stress_coordinate_component_order:["x","y"],stress_geometric_z_m:null,
    stress_geometric_z_status:"UNAVAILABLE; native EGGAU2D measures X/Y/W",stress_integration_weights_m2:weights,
    stress_integration_weight_provenance:weightProvenance,stress_identifiers:stressIds};
  const samples={};
  for(const name of ["A","B","N14"]){const id=nodeGroups[name][0],i=slaveIds.indexOf(id);samples[name]={node_id:id,
    raw_node_identifier:rawIds[id],normal_traction_pa:pressures[i],vertical_displacement_m:u[id][1]};}
  const observation={fields,samples,slave_contact:{node_ids:slaveIds,normal_traction_pa:pressures,raw_node_identifiers:slaveIds.map(id=>rawIds[id]),
    unit:"Pa",source_field:"DEPL.LAGS_C",sign:"Native signed normal traction retained"},projected_gaps_m:null};
  function nodalTable(ids, rawNames, vals, columns, field) {
    const out=Object.fromEntries(["COOR_X","COOR_Y","COOR_Z","NOEUD","NOM_CHAM","NUME_ORDRE","RESULTAT",...columns].map(k=>[k,[]]));
    // Reversed actual raw row order does not alter the explicit normalized mapping.
    for(let j=ids.length-1;j>=0;j--){const p=coordinates[ids[j]];["COOR_X","COOR_Y","COOR_Z"].forEach((k,a)=>out[k].push(p[a]));
      out.NOEUD.push(rawNames[j]);out.NOM_CHAM.push(field);out.NUME_ORDRE.push(1);out.RESULTAT.push("fixture_result");
      columns.forEach((k,a)=>out[k].push(vals[j][a]));}return out;
  }
  const tables={DEPL:nodalTable(mesh.node_ids,rawIds,u,["DX","DY"],"DEPL"),
    REAC_NODA:nodalTable(mesh.node_ids,rawReactions,rf,["DX","DY"],"REAC_NODA"),
    LAGS_C:nodalTable(slaveIds,slaveIds.map(id=>rawIds[id]),pressures.map(v=>[v]),["LAGS_C"],"DEPL")};
  const stressTable=Object.fromEntries(["COOR_X","COOR_Y","COOR_Z","MAILLE","NOM_CHAM","NUME_ORDRE","POINT","SOUS_POINT","RESULTAT","SIXX","SIYY","SIZZ","SIXY"].map(k=>[k,[]]));
  for(let i=stressIds.length-1;i>=0;i--){const id=stressIds[i];stressTable.COOR_X.push(xy[i][0]);stressTable.COOR_Y.push(xy[i][1]);stressTable.COOR_Z.push(weights[i]);
    stressTable.MAILLE.push(id.raw_element_identifier);stressTable.NOM_CHAM.push("SIEF_ELGA");stressTable.NUME_ORDRE.push(1);stressTable.POINT.push(id.point);
    stressTable.SOUS_POINT.push(id.subpoint);stressTable.RESULTAT.push("fixture_result");["SIXX","SIYY","SIZZ","SIXY"].forEach((k,a)=>stressTable[k].push(stresses[i][a]));}
  tables.SIEF_ELGA=stressTable;
  put(`${A}input.json`,settings); put(`${L}input.json`,{settings,mesh_sha256:sha(meshBytes),mesh_inspection_sha256:sha(bytes.get(`${A}frozen_mesh.json`))});
  const checks={status:"PASS",node_count:n,body_element_count:stressIds.length/4,boundary_element_count:cells.length-stressIds.length/4,
    total_cell_count:cells.length,source_cell_mapping:mapping,boundary_node_ids:boundaries,mesh_sha256:sha(meshBytes),mesh_inspection_sha256:sha(bytes.get(`${A}frozen_mesh.json`))};
  const worker={schema_version:"1",input_sha256:sha(bytes.get(`${L}input.json`)),mesh_input_sha256:sha(meshBytes),mesh_inspection_sha256:sha(bytes.get(`${A}frozen_mesh.json`)),
    mesh,frozen_mesh:frozen,observation,native_tables:tables,native_mesh_checks:checks,solver_status:"COMPLETED",converged:true,order:1,
    access_parameters:{INST:[0,1],NUME_ORDRE:[0,1]},available_orders:[0,1],native_policy:policy,
    native_material:{ELAS:{E:2e6,NU:0},unit:"Pa"},code_aster_runtime:runtime,versions,
    ...(refined?{mesh_variant:"uniform_quad4_2x"}:{})};
  put(`${L}worker_result.json`,worker);put(`${L}parsed_contact.json`,observation);
  for(const [field,name] of [["DEPL","depl"],["REAC_NODA","reac_noda"],["LAGS_C","lags_c"],["SIEF_ELGA","sief_elga"]])put(`${L}order_1_${name}.table.json`,tables[field]);
  putBytes(`${L}results.med`,Buffer.from("UNSOLVED synthetic native-download fixture\n"));
  for(const name of ["codeaster_contact.py","codeaster_contact_worker.py","codeaster_worker.py","codeaster_runtime_adapter.py",
    "codeaster_execution.py","execution_control.py","domain_reference.py"])putBytes(`${A}${name}`,Buffer.from(`# synthetic captured ${name}; never executed\n`));
  const sourceHashes=Object.fromEntries([...bytes].filter(([name])=>name.startsWith(A)&&!name.slice(A.length).includes("/")&&
    !["input.json","model_declaration.json"].includes(name.slice(A.length))).map(([name,value])=>[name.slice(A.length),sha(value)]));
  const meshDecl={node_count:n,solid_cell_count:stressIds.length/4,boundary_segment_count:checks.boundary_element_count,
    slave_contact_segment_count:slaveIds.length-1,master_contact_segment_count:boundaries.EF.length-1,
    topology:"quadrilateral",order:1,original_coordinates_preserved:true,coincident_interface_nodes_merged:false,
    source:refined?"deterministic_uniform_subdivision_2x_of_fixed_original_nonmatching_mesh":"fixed_original_nonmatching_mesh",
    ...(refined?{mesh_variant:"uniform_quad4_2x",asset_sha256:sha(meshBytes),catalog_sha256:sha(bytes.get(`${A}frozen_mesh.json`)),
      mesh_profile_sha256:sha(bytes.get(`${A}${NAME}`)),generation_recipe_sha256:sha(bytes.get(`${A}mesh_generation_recipe.json`)),
      generation_source_sha256:sha(bytes.get(`${A}codeaster_contact_mesh.py`)),parent_asset_sha256:sha(bytes.get(`${A}source_parent.mmed`)),
      original_prefix_node_count:313,original_vendor_mesh_replication:false}:{})};
  const outputs={fields:[{field:"displacement",location:"nodes",unit:"m",components:["x","y"]},
    {field:"reactions",location:"nodes",unit:"N/m",components:["x","y"]},{field:"normal_traction",location:"slave_contact_nodes",unit:"Pa",compression_sign:"negative"},
    {field:"stress",location:"solid_elements",unit:"Pa"}],load_parameter:[0,1],sample_coordinate_unit:"m",
    sample_points:Object.fromEntries(["A","B","N14"].map(name=>[name,frozen.coordinates_in_native_order[nodeGroups[name][0]]]))};
  const decl={case:CASE,model:{mesh:meshDecl,materials:[{youngs_modulus:{value:2e6,unit:"Pa"},poisson_ratio:{value:0,unit:"1"}}]},
    history:{load_parameter:[0,1]},boundary_conditions:[],loads:[{unit:"m",values:[0,-0.1]}],outputs,
    reference:{case:CASE,reference_identity:"Code_Aster_SSNP121A",material:settings.material,six_published_sample_relative_limits:0.01,
      units:{length:"m",normal_traction:"Pa",reaction_resultant:"N/m"},reference_kind:refined?"analytical_mesh_refinement":"original_published_analytical_case",
      ...(refined?{mesh_variant:"uniform_quad4_2x",canonical_original_inputs:false,original_vendor_mesh_replication:false}:{})}};
  put(`${A}model_declaration.json`,decl);
  const modelRevision=digest(decl), proposalRevision=digest({fixture:refined?"uniform2":"original",UNSOLVED:true});
  const proposal={id:refined?"E-reader-synthetic-uniform2":"E-reader-synthetic-original",study_id:"S-reader-UNSOLVED",model_revision:modelRevision,
    physics:{backend:BACKEND},execution:settings,model:decl.model,boundary_conditions:decl.boundary_conditions,loads:decl.loads,outputs,
    extensions:{model_analysis:{model_revision:modelRevision,declaration:decl}}};
  put("proposal.json",proposal);
  const details={adapter:BACKEND,captured_source_sha256:sourceHashes,mesh_sha256:sha(meshBytes),mesh_catalog_sha256:sha(bytes.get(`${A}frozen_mesh.json`)),
    native_input:`${L}mesh.mmed`,native_fields:[`${L}results.med`],domain_plugin:{module:"plugins.contact_patch.reference",source_artifact:`${A}domain_reference.py`,
      source_sha256:sourceHashes["domain_reference.py"]},nonlinear_policy:policy,code_aster_runtime:runtime,versions,
    ...(refined?{mesh_variant:"uniform_quad4_2x",mesh_profile_sha256:profile?sha(bytes.get(`${A}${NAME}`)):null,
      generation_recipe_sha256:sha(bytes.get(`${A}mesh_generation_recipe.json`)),generation_source_sha256:sha(bytes.get(`${A}codeaster_contact_mesh.py`)),source_parent_mesh:recipe.parent}:{})};
  const inspection={integrity:"VERIFIED",proposal,study:{id:proposal.study_id},thread:{experiment:proposal.id,study:proposal.study_id,
    model_revision:modelRevision,result:"result.json"},ledger:{experiment_id:proposal.id,result_sha256:"a".repeat(64),thread_sha256:"b".repeat(64)},
    result:{experiment_id:proposal.id,study:{id:proposal.study_id},model_revision:modelRevision,proposal_revision:proposalRevision,
      status:"REJECTED",decision:"NOT_RELEASED",solver_status:"COMPLETED",converged:true,artifacts:[],metrics:{fixture_only:{value:-123.75,unit:"Pa",valid:false,reason:"UNSOLVED synthetic display fixture"}},
      validations:[{status:"FAIL",blocking:true,type:"numerical_validation"},{status:"UNKNOWN",blocking:true,type:"physical_validation"}],evidence:["UNSOLVED independent fixture"],
      provenance:{adapter:BACKEND,proposal_sha256:proposalRevision,execution_settings:settings,adapter_details:details,
        source_commit:"c".repeat(40),core_commit:"c".repeat(40)}},
    hashes:{result_sha256:"a".repeat(64),thread_sha256:"b".repeat(64),proposal_sha256:sha(bytes.get("proposal.json")),ledger_sha256:"d".repeat(64),study_sha256:"e".repeat(64),artifacts:[]}};
  function seal() {
    inspection.result.artifacts=[...bytes].map(([name,value])=>({path:name,sha256:sha(value),size_bytes:value.length,revision:proposalRevision}));
    inspection.hashes.artifacts=clone(inspection.result.artifacts);inspection.hashes.proposal_sha256=sha(bytes.get("proposal.json"));
  }
  seal();
  function syncWorker() { put(`${L}worker_result.json`,docs.get(`${L}worker_result.json`)); }
  function alterWorker(change, sync = true) {
    const w=docs.get(`${L}worker_result.json`);change(w);put(`${L}worker_result.json`,w);
    if(sync){put(`${L}parsed_contact.json`,w.observation);put(`${L}mesh_catalog.json`,w.mesh);}seal();
  }
  return {inspection,bytes,docs,put,putBytes,seal,alterWorker,syncWorker,n,slaveIds,stressIds,coordinates,
    fetch:async name=>{if(!bytes.has(name))throw Error("missing");return Uint8Array.from(bytes.get(name));}};
}
const load = (f, api=loadContactField, current=()=>true, fetch=f.fetch) => api(f.inspection,fetch,current);
function empty(out) {
  assert.notEqual(out.status,"available");for(const name of ["nodes","cells","slave","gauss"])assert.equal(out[name].length,0);
  assert.deepEqual(Object.keys(out.nodeGroups),[]);assert.deepEqual(Object.keys(out.cellGroups),[]);assert.ok(out.reason);
}
function rejected(out, pattern) { empty(out); if(pattern)assert.match(out.reason,pattern); }
for (const refined of [false,true]) test(`complete independent ${refined?"uniform2":"original"} fields preserve every component, raw mapping, last row and failed verdict`,async()=>{
  const f=fixture(refined),out=await load(f);assert.equal(out.status,"available",out.reason);
  assert.equal(out.nodes.length,refined?1154:313);assert.equal(out.cells.length,refined?1244:357);
  assert.equal(out.slave.length,refined?25:13);assert.equal(out.gauss.length,refined?4240:1060);
  assert.equal(out.cells[0].type,"QUAD4");assert.equal(out.gauss[0].cellId,0);
  assert.deepEqual(out.metadata.aliases,{A:0,B:1,N14:13});assert.equal(out.nodes[13].xyz_m[0],2.98023223876953e-08);
  for(let i=0;i<f.n;i++){assert.deepEqual(out.nodes[i].u,{dx:i+0.125,dy:-i-0.25});assert.deepEqual(out.nodes[i].rf_n_per_m,{dx:-i-100.5,dy:i+200.75});
    assert.equal(out.nodes[i].xyz_m[2],0);assert.equal(out.nodes[i].rawDeplId,String(9000+((i*17)%f.n)));assert.ok(!Object.hasOwn(out.nodes[i].u,"dz"));}
  for(let i=0;i<out.gauss.length;i++){assert.deepEqual(out.gauss[i].stress_pa,{xx:100+i,yy:-200-i,zz:300+i,xy:-400-i});
    assert.equal(out.gauss[i].weight_m2,(i+1)/1e6);assert.deepEqual(out.gauss[i].xy_m,[Math.floor(i/4)+(i%4+1)/8,-Math.floor(i/4)-(i%4+1)/16]);}
  assert.equal(out.slave[0].normalTractionPa,-10000);assert.ok(out.slave.every(row=>row.normalTractionPa<0));
  assert.equal(out.metadata.status,"REJECTED");assert.equal(out.metadata.decision,"NOT_RELEASED");assert.equal(out.metadata.metrics.fixture_only.valid,false);
  assert.equal(out.metadata.metrics.fixture_only.value,-123.75);assert.equal(out.metadata.validations[1].status,"UNKNOWN");
  assert.ok(out.limitations.some(v=>v.includes("geometric Z")&&v.includes("UNAVAILABLE")));
  assert.ok(Object.isFrozen(out)&&Object.isFrozen(out.nodes)&&Object.isFrozen(out.nodes[0].u)&&Object.isFrozen(out.metadata.metrics));
  assert.equal(out.downloads.find(row=>row.path===`${L}order_1_lags_c.table.json`).sha256,f.inspection.result.artifacts.find(row=>row.path===`${L}order_1_lags_c.table.json`).sha256);
  assert.equal(out.metadata.sourceCommit,"c".repeat(40));assert.equal(out.metadata.order,1);assert.equal(out.metadata.inst,1);
});
test("browser and CommonJS expose the same bounded asynchronous API",async()=>{
  const api=browser();assert.equal(typeof api.loadContactField,"function");assert.deepEqual(Object.keys(api),["loadContactField"]);
  const out=await load(fixture(),api.loadContactField);assert.equal(out.status,"available",out.reason);
});
const envelopeMutations=[
  ["unverified",f=>f.inspection.integrity="UNKNOWN"], ["result experiment",f=>f.inspection.result.experiment_id="foreign"],
  ["result model revision",f=>f.inspection.result.model_revision="f".repeat(64)], ["canonical proposal revision",f=>f.inspection.result.provenance.proposal_sha256="f".repeat(64)],
  ["thread experiment",f=>f.inspection.thread.experiment="foreign"], ["thread study",f=>f.inspection.thread.study="foreign"],
  ["thread model revision",f=>f.inspection.thread.model_revision="f".repeat(64)], ["result study",f=>f.inspection.result.study.id="foreign"],
  ["study envelope",f=>f.inspection.study.id="foreign"], ["ledger experiment",f=>f.inspection.ledger.experiment_id="foreign"],
  ["ledger result hash",f=>f.inspection.ledger.result_sha256="f".repeat(64)], ["ledger thread hash",f=>f.inspection.ledger.thread_sha256="f".repeat(64)],
  ["execution provenance",f=>f.inspection.result.provenance.execution_settings={case:"foreign"}],
  ["backend mismatch",f=>f.inspection.proposal.physics.backend="foreign"], ["missing source commit",f=>delete f.inspection.result.provenance.source_commit],
  ["manifest copy",f=>f.inspection.hashes.artifacts.pop()], ["foreign manifest revision",f=>{f.inspection.result.artifacts[0].revision="f".repeat(64);f.inspection.hashes.artifacts=clone(f.inspection.result.artifacts);}]
];
for(const [name,mutate] of envelopeMutations)test(`refuse ${name}`,async()=>{const f=fixture();mutate(f);empty(await load(f));});
for(const selector of [true,0,null,"original","uniform_quad4_4x","../mesh"])test(`unsupported selector ${JSON.stringify(selector)} refuses before fetch`,async()=>{
  const f=fixture();f.inspection.proposal.execution.mesh_variant=selector;f.inspection.result.provenance.execution_settings=clone(f.inspection.proposal.execution);
  let calls=0;empty(await load(f,loadContactField,()=>true,async()=>{calls++;throw Error("must not fetch");}));assert.equal(calls,0);
});
test("valid foreign backend is unavailable, with original verdict and raw downloads",async()=>{
  const f=fixture();f.inspection.proposal.physics.backend="structural.other";f.inspection.result.provenance.adapter="structural.other";
  const out=await load(f);empty(out);assert.equal(out.status,"unavailable");assert.equal(out.metadata.status,"REJECTED");assert.equal(out.downloads.length,f.bytes.size);
});
const workerMutations=[
  ["input digest",w=>w.input_sha256="f".repeat(64)], ["mesh digest",w=>w.mesh_input_sha256="f".repeat(64)],
  ["catalog digest",w=>w.mesh_inspection_sha256="f".repeat(64)], ["order",w=>w.order=0], ["instant",w=>w.access_parameters.INST=[0,2]],
  ["available orders",w=>w.available_orders=[0,2]], ["solver incomplete",w=>w.solver_status="FAILED"], ["native names invented",w=>w.mesh.native_node_names=["A"]],
  ["missing pressure",w=>delete w.native_tables.LAGS_C], ["missing displacement",w=>delete w.native_tables.DEPL],
  ["partial displacement",w=>w.observation.fields.displacements_m.pop()], ["partial reaction",w=>w.observation.fields.nodal_reactions_n_per_m.pop()],
  ["extra synthetic displacement Z",w=>w.observation.fields.displacements_m[0].push(0)], ["component order",w=>w.observation.fields.stress_component_order=["xx","yy","xy","zz"]],
  ["foreign node",w=>w.observation.fields.node_ids[0]=999999], ["duplicate raw node",w=>w.native_tables.DEPL.NOEUD[0]=w.native_tables.DEPL.NOEUD[1]],
  ["false suffix map",w=>w.observation.fields.raw_node_identifiers=w.mesh.node_ids.map(id=>String(id+1))],
  ["nodal coordinate",w=>w.native_tables.DEPL.COOR_X[0]+=0.1], ["native displacement component",w=>w.native_tables.DEPL.DY[0]+=0.1],
  ["native reaction component",w=>w.native_tables.REAC_NODA.DX[0]+=0.1], ["reaction raw ID",w=>w.observation.fields.raw_reaction_node_identifiers[0]="missing"],
  ["pressure field substitution",w=>w.native_tables.LAGS_C.NOM_CHAM[0]="SIEF_ELGA"], ["pressure sign changed only in normalized",w=>w.observation.slave_contact.normal_traction_pa[0]*=-1],
  ["pressure wrong unit",w=>w.observation.slave_contact.unit="N/m"], ["partial pressure",w=>w.observation.slave_contact.node_ids.pop()],
  ["duplicate pressure node",w=>w.observation.slave_contact.node_ids[0]=w.observation.slave_contact.node_ids[1]],
  ["master pressure surrogate",w=>w.observation.slave_contact.node_ids[0]=w.mesh.group_node_ids.EF[0]],
  ["pressure raw map",w=>w.observation.slave_contact.raw_node_identifiers[0]="missing"], ["alias sample node",w=>w.observation.samples.N14.node_id=0],
  ["alias sample value",w=>w.observation.samples.A.normal_traction_pa+=1], ["alias raw label",w=>w.observation.samples.A.raw_node_identifier="missing"],
  ["missing Gauss row",w=>w.observation.fields.stresses_pa.pop()], ["missing native stress column",w=>delete w.native_tables.SIEF_ELGA.SIZZ],
  ["duplicate native Gauss tuple",w=>{const t=w.native_tables.SIEF_ELGA;t.MAILLE[0]=t.MAILLE[1];t.POINT[0]=t.POINT[1];}],
  ["duplicate normalized Gauss tuple",w=>w.observation.fields.stress_identifiers[0]=clone(w.observation.fields.stress_identifiers[1])],
  ["foreign stress cell",w=>w.observation.fields.stress_identifiers[0].cell_id=999999],
  ["boundary stress cell",w=>w.observation.fields.stress_identifiers[0].cell_id=w.mesh.cells.find(c=>c.cell_type==="SEG2").cell_id],
  ["native order0 stress",w=>w.native_tables.SIEF_ELGA.NUME_ORDRE[0]=0], ["normalized point5",w=>w.observation.fields.stress_identifiers[0].point=5],
  ["subpoint2",w=>w.native_tables.SIEF_ELGA.SOUS_POINT[0]=2], ["raw cell alias",w=>w.observation.fields.stress_identifiers[0].raw_element_identifier="missing"],
  ["Gauss XY mismatch",w=>w.native_tables.SIEF_ELGA.COOR_Y[0]+=1], ["Gauss component mismatch",w=>w.native_tables.SIEF_ELGA.SIXY[0]+=1],
  ["weight mismatch",w=>w.native_tables.SIEF_ELGA.COOR_Z[0]*=2], ["zero weight",w=>w.observation.fields.stress_integration_weights_m2[0]=0],
  ["negative weight",w=>w.observation.fields.stress_integration_weights_m2[0]=-1], ["missing weight",w=>delete w.observation.fields.stress_integration_weights_m2],
  ["weight unit",w=>w.observation.fields.stress_integration_weight_provenance.unit="m"], ["weight as geometric Z",w=>w.observation.fields.stress_geometric_z_m=0],
  ["wrong weight source",w=>w.observation.fields.stress_integration_weight_provenance.native_component="GEOMETRIC_Z"],
  ["missing weight provenance",w=>delete w.observation.fields.stress_integration_weight_provenance],
  ["mesh repeated cell",w=>w.mesh.cells[1]=clone(w.mesh.cells[0])], ["mesh reversed connectivity",w=>w.mesh.cells[0].node_ids.reverse()],
  ["mesh wrong type",w=>w.mesh.cells[0].cell_type="TETRA10"], ["mesh partial cells",w=>w.mesh.cells.pop()],
  ["mesh foreign group",w=>w.mesh.group_cell_ids.AB[0]=999999], ["missing named group",w=>delete w.mesh.group_node_ids.N14],
  ["native coordinate snapped",w=>w.mesh.coordinates_m[13][0]=0], ["source map mismatched cell",w=>w.native_mesh_checks.source_cell_mapping[0].source_cell_id=1],
  ["incomplete source cell map",w=>w.native_mesh_checks.source_cell_mapping.pop()], ["mesh check foreign hash",w=>w.native_mesh_checks.mesh_sha256="f".repeat(64)],
  ["foreign native policy",w=>w.native_policy.convergence.RESI_GLOB_MAXI=1], ["native material drift",w=>w.native_material.ELAS.E=1],
  ["runtime drift",w=>w.code_aster_runtime.version="17.5"], ["normalized foreign load",w=>w.observation.fields.load_parameter=0],
  ["foreign raw result channel",w=>w.native_tables.SIEF_ELGA.RESULTAT.fill("foreign_result")],
  ["null native displacement",w=>w.native_tables.DEPL.DX[0]=null], ["bool native pressure",w=>w.native_tables.LAGS_C.LAGS_C[0]=true],
  ["string native stress",w=>w.native_tables.SIEF_ELGA.SIXX[0]="100"], ["null normalized weight",w=>w.observation.fields.stress_integration_weights_m2[0]=null],
  ["bool normalized order",w=>w.observation.fields.actual_result_order=true],
];
for(const [name,mutate] of workerMutations)test(`full fixture refuses ${name} with no trusted arrays`,async()=>{
  const f=fixture();f.alterWorker(mutate);const out=await load(f);empty(out);assert.equal(out.metadata.status,"REJECTED");assert.ok(out.downloads.length>0);
});
test("worker observation must equal separately manifested normalized observation",async()=>{
  const f=fixture();f.alterWorker(w=>w.observation.fields.displacements_m[0][0]+=1,false);rejected(await load(f),/observation identity/);
});
test("finite failed pressure stays signed and inspectable when every native/normalized join agrees",async()=>{
  const f=fixture();f.alterWorker(w=>{const s=w.observation.slave_contact;s.normal_traction_pa[0]=123.5;
    const raw=s.raw_node_identifiers[0],t=w.native_tables.LAGS_C;t.LAGS_C[t.NOEUD.indexOf(raw)]=123.5;
    w.observation.samples.A.normal_traction_pa=123.5;});
  const out=await load(f);assert.equal(out.status,"available",out.reason);assert.equal(out.slave[0].normalTractionPa,123.5);
  assert.equal(out.metadata.status,"REJECTED");assert.equal(out.metadata.metrics.fixture_only.valid,false);assert.equal(out.metadata.decision,"NOT_RELEASED");
});
for(const name of ["codeaster_contact.py","codeaster_contact_worker.py","domain_reference.py","reference_specification.json","frozen_mesh.json"])
  test(`captured source mismatch ${name} refuses`,async()=>{const f=fixture();f.inspection.result.provenance.adapter_details.captured_source_sha256[name]="f".repeat(64);empty(await load(f));});
test("source map requires actual source snapshots",async()=>{
  const f=fixture();delete f.inspection.result.provenance.adapter_details.captured_source_sha256.execution_control;delete f.inspection.result.provenance.adapter_details.captured_source_sha256["execution_control.py"];empty(await load(f));
});
test("unsafe captured source path refuses",async()=>{const f=fixture();f.inspection.result.provenance.adapter_details.captured_source_sha256["../escape.py"]="f".repeat(64);empty(await load(f));});
for(const name of [`${L}worker_result.json`,`${L}order_1_lags_c.table.json`,`${L}results.med`,`${A}reference_specification.json`])
  test(`missing manifested dependency ${name} retains no arrays`,async()=>{const f=fixture();f.bytes.delete(name);f.seal();const out=await load(f);empty(out);assert.equal(out.status,"partial");});
test("captured native bytes tamper refuses and preserves exact raw download metadata",async()=>{
  const f=fixture();const b=f.bytes.get(`${L}worker_result.json`);b[20]^=1;const out=await load(f);rejected(out,/SHA-256/);assert.equal(out.downloads.find(row=>row.path===`${L}worker_result.json`).sha256,f.inspection.result.artifacts.find(row=>row.path===`${L}worker_result.json`).sha256);
});
test("wrong returned byte size refuses",async()=>{const f=fixture();rejected(await load(f,loadContactField,()=>true,async()=>new Uint8Array([1])),/byte length/);});
test("fetch failure refuses as partial",async()=>{const f=fixture();const out=await load(f,loadContactField,()=>true,async()=>{throw Error("lost");});empty(out);assert.equal(out.status,"partial");});
for(const pathName of ["../escape.json","simulation/../escape","simulation\\escape","/absolute","C:/escape","simulation/%2e%2e/escape","simulation/#query","simulation/a?b","simulation/\u0000bad"])
  test(`unsafe manifest path ${JSON.stringify(pathName)}`,async()=>{const f=fixture();const row=clone(f.inspection.result.artifacts[0]);row.path=pathName;f.inspection.result.artifacts.push(row);f.inspection.hashes.artifacts=clone(f.inspection.result.artifacts);empty(await load(f));});
test("case-folded duplicate manifest refuses",async()=>{const f=fixture();const row=clone(f.inspection.result.artifacts[0]);row.path=row.path.toUpperCase();f.inspection.result.artifacts.push(row);f.inspection.hashes.artifacts=clone(f.inspection.result.artifacts);empty(await load(f));});
test("matching raw proposal hash is distinct from canonical proposal revision",async()=>{
  const f=fixture();assert.notEqual(f.inspection.hashes.proposal_sha256,f.inspection.result.proposal_revision);assert.equal((await load(f)).status,"available");
});
for(const [name,make] of [
  ["malformed UTF8",()=>Buffer.from([0xc3,0x28])], ["duplicate root key",()=>Buffer.from('{"settings":1,"settings":2}')],
  ["escaped duplicate key",()=>Buffer.from('{"settings":1,"\\u0073ettings":2}')], ["nested duplicate key",()=>Buffer.from('{"a":{"x":1,"x":2}}')],
  ["nonfinite native JSON number",()=>Buffer.from('{"x":1e999}')], ["JSON NaN",()=>Buffer.from('{"x":NaN}')],
  ["JSON true numeric surrogate",()=>Buffer.from('{"settings":true}')], ["trailing data",()=>Buffer.from('{} {}')],
  ["byte-order mark",()=>Buffer.from('\ufeff{}')], ["array top level",()=>Buffer.from('[]')], ["depth65",()=>Buffer.from('{"a":'+ '['.repeat(65)+'0'+']'.repeat(65)+'}')]
])test(`strict retained JSON refuses ${name}`,async()=>{const f=fixture();f.bytes.set(`${L}input.json`,make());f.seal();empty(await load(f));});
test("JSON over32MiB refuses before fetch",async()=>{
  const f=fixture();const row=f.inspection.result.artifacts.find(r=>r.path===`${A}model_declaration.json`);row.size_bytes=32*1024*1024+1;
  f.inspection.hashes.artifacts=clone(f.inspection.result.artifacts);let count=0;const out=await load(f,loadContactField,()=>true,async()=>{count++;throw Error("must not fetch");});
  empty(out);assert.equal(out.status,"unavailable");assert.equal(count,0);
});
test("total parsed payload over16MiB refuses before fetching the excess artifact",async()=>{
  const f=fixture();const row=f.inspection.result.artifacts.find(r=>r.path===`${L}worker_result.json`);row.size_bytes=16*1024*1024;
  f.inspection.hashes.artifacts=clone(f.inspection.result.artifacts);let excess=0;const out=await load(f,loadContactField,()=>true,async name=>{if(name===row.path)excess++;return f.fetch(name);});
  empty(out);assert.equal(out.status,"unavailable");assert.equal(excess,0);assert.match(out.reason,/16 MiB/);
});
test("missing WebCrypto in browser leaves downloads, not trusted arrays",async()=>{
  const f=fixture();const out=await load(f,browser(null).loadContactField);empty(out);assert.equal(out.status,"unavailable");assert.match(out.reason,/WebCrypto/);assert.equal(out.downloads.length,f.bytes.size);
});
test("selection changed before first await refuses without fetching",async()=>{
  const f=fixture();let calls=0;const out=await load(f,loadContactField,()=>false,async()=>{calls++;});empty(out);assert.equal(calls,0);
});
test("record/store selection change during fetch clears every trusted field",async()=>{
  const f=fixture();let valid=true;const out=await load(f,loadContactField,()=>valid,async name=>{const b=await f.fetch(name);valid=false;return b;});rejected(out,/Selection changed/);
});
test("selection change during digest clears every trusted field",async()=>{
  const f=fixture();let valid=true;const api=browser({subtle:{digest:async(...args)=>{const value=await crypto.webcrypto.subtle.digest(...args);valid=false;return value;}}});
  rejected(await load(f,api.loadContactField,()=>valid),/Selection changed/);
});
test("caller byte mutation during digest cannot alter verified immutable copy",async()=>{
  const f=fixture();let returned;const api=browser({subtle:{digest:async(...args)=>{returned.fill(0);return crypto.webcrypto.subtle.digest(...args);}}});
  const out=await load(f,api.loadContactField,()=>true,async name=>{returned=Uint8Array.from(f.bytes.get(name));return returned;});assert.equal(out.status,"available",out.reason);
  assert.equal(out.nodes.at(-1).u.dy,-f.n+0.75);
});
test("rapid selection replacement allows only the current response",async()=>{
  const f=fixture();let selection=1,release;const blocked=new Promise(resolve=>{release=resolve;});
  const old=load(f,loadContactField,()=>selection===1,async name=>{await blocked;return f.fetch(name);});selection=2;
  const fresh=await load(f,loadContactField,()=>selection===2);release();const stale=await old;assert.equal(fresh.status,"available",fresh.reason);empty(stale);
});
test("inspection mutation across await does not mutate the reader snapshot",async()=>{
  const f=fixture();let first=true;const out=await load(f,loadContactField,()=>true,async name=>{if(first){first=false;f.inspection.result.metrics.fixture_only.value=12345;f.inspection.proposal.execution.case="foreign";}return f.fetch(name);});
  assert.equal(out.status,"available",out.reason);assert.equal(out.metadata.metrics.fixture_only.value,-123.75);
});
for(const [name,mutate] of [
  ["settings input",f=>{const d=f.docs.get(`${A}input.json`);d.top_displacement_m=-0.2;f.put(`${A}input.json`,d);f.seal();}],
  ["level mesh input",f=>{const d=f.docs.get(`${L}input.json`);d.mesh_sha256="f".repeat(64);f.put(`${L}input.json`,d);f.seal();}],
  ["declaration mismatch",f=>{const d=f.docs.get(`${A}model_declaration.json`);d.case="foreign";f.put(`${A}model_declaration.json`,d);f.seal();}],
  ["uniform source profile hash",f=>f.inspection.result.provenance.adapter_details.mesh_profile_sha256="f".repeat(64)],
  ["uniform generation hash",f=>f.inspection.result.provenance.adapter_details.generation_recipe_sha256="f".repeat(64)],
  ["uniform generator hash",f=>f.inspection.result.provenance.adapter_details.generation_source_sha256="f".repeat(64)],
  ["uniform parent binding",f=>f.inspection.result.provenance.adapter_details.source_parent_mesh.catalog_sha256="f".repeat(64)],
  ["uniform worker variant",f=>f.alterWorker(w=>w.mesh_variant="original")]
])test(`full uniform fixture refuses ${name}`,async()=>{const f=fixture(true);mutate(f);empty(await load(f));});
