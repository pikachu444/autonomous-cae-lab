"use strict";
// TEST_ONLY ten-node topology and raw-looking pins; UNSOLVED, not native proof.
const {test}=require("node:test"), assert=require("node:assert/strict");
const controls=require("../apps/lab/static/fixture-field-controls.js");
const {fixture,clone,digest}=require("./test_fixture_field_controls.js");
function nativeFixture() {
  const old=fixture(), field=clone(old.field), inspection=clone(old.inspection);
  const revision="e".repeat(64), faceIds=field.boundary_faces.map((_,i)=>`F-${revision}-Face${i+1}`);
  Object.assign(field,{kind:"native_structural_nodal_displacement",backend:"structure.calculix.native",adapter_version:"1",
    coordinate_frame:"CAD_DOCUMENT_GLOBAL",native_catalog_revision:revision,mesh_size_max_mm:4,
    parent_step_sha256:"f".repeat(64),peak_node_id:209});
  field.boundary_faces=field.boundary_faces.map((face,i)=>({element_id:face.element_id,type:face.type,node_ids:face.node_ids,selection_id:faceIds[i]}));
  field.prescribed_dofs=field.boundary_faces[0].node_ids.map(node_id=>({node_id,component:1,value_mm:0,declared_value_mm:0,value_token:"0.000000000000e+00"}));
  field.loads=[43,102,145].map((node_id,i)=>({node_id,component:3,force_N:[-1,2,3][i],force_token:String([-1,2,3][i])}));
  delete field.fixed_node_ids; delete field.fixed_dofs; delete field.mesh_index;
  const declaration={materials:[{selection_id:"B-final",law:"isotropic_linear_elastic",young_modulus_MPa:210000,poisson_ratio:.3}],
    boundary_conditions:[{selection_id:faceIds[0],components:{UX:0},unit:"mm",coordinate_system:"global"}],
    loads:[{selection_id:faceIds[1],components:{FX:0,FY:0,FZ:4},unit:"N",coordinate_system:"global"}],mesh:{max_size_mm:4}};
  const execution={analysis_type:"linear_static",declaration,native_catalog:{native_catalog_revision:revision,
    selections:faceIds.map((id,i)=>({id,kind:"native_face",native_name:`Face${i+1}`}))},mesh:declaration.mesh};
  field.sources={};
  const paths={mesh:"mesh.json",deck:"native.inp",boundary:"boundary.json",frd:"native.frd",dat:"native.dat"}, artifacts=[];
  for (const [key,path] of Object.entries(paths)) { const bytes=Buffer.from(`TEST_ONLY ${key}; not native syntax`);
    field.sources[key]={path,sha256:digest(bytes),bytes:bytes.length};
    artifacts.push({path:"simulation/"+path,sha256:digest(bytes),size_bytes:bytes.length,revision:field.cad_revision,mime_type:"application/octet-stream"}); }
  field.deck_sha256=field.sources.deck.sha256;
  const bytes=Buffer.from(JSON.stringify(field)),path="simulation/field.json";
  artifacts.push({path,sha256:digest(bytes),size_bytes:bytes.length,revision:field.cad_revision,mime_type:"application/json"});
  Object.assign(inspection.result.provenance,{adapter:"structure.calculix.native",adapter_version:"1",execution_settings:execution,
    adapter_details:{parent_step_sha256:field.parent_step_sha256}});
  inspection.result.artifacts=artifacts;
  inspection.result.metrics={max_displacement:{value:Math.hypot(...field.nodes.at(-1).displacement_mm),unit:"mm",valid:true}};
  Object.assign(inspection.proposal,{execution,boundary_conditions:declaration.boundary_conditions,loads:declaration.loads});
  inspection.proposal.model.materials=declaration.materials; inspection.proposal.physics.backend=field.backend;
  return {field,inspection,path,bytes};
}
function verify(data) {return controls.verifyField(data.field,data.inspection,data.path);}
module.exports={nativeFixture};
if (require.main === module) {
test("native reader retains partial DOFs, signed weights, FaceN and whole vector response without mutating raw records",()=>{
  const data=nativeFixture(),before=JSON.stringify(data),model=verify(data);
  assert.equal(model.metadata.family,"native");assert.equal(model.field.nodes.length,10);
  assert.equal(model.field.boundary_faces[0].group,"Face1");assert.equal(model.rawNative.prescribed_dofs[0].component,1);
  assert.equal(model.rawNative.loads[0].force_N,-1);assert.equal(model.metadata.totalForceVectorN[2],4);
  assert.equal(model.metadata.wholeMaximumMagnitude,Math.hypot(.001,.01,-.09));
  assert(Object.isFrozen(model.rawNative.prescribed_dofs[0]));assert.equal(JSON.stringify(data),before);
});
for(const [name,alter] of Object.entries({
  revision:d=>d.field.native_catalog_revision="0".repeat(64),frame:d=>d.field.coordinate_frame="WORLD",
  incomplete_nodes:d=>d.field.nodes.pop(),incomplete_exterior:d=>{d.field.boundary_faces.pop();d.field.boundary_face_count--;},
  fabricated_face:d=>d.field.boundary_faces[0].selection_id="Face1",missing_dof:d=>d.field.prescribed_dofs.pop(),
  implicit_zero:d=>d.field.prescribed_dofs[0].component=2,wrong_dof_value:d=>d.field.prescribed_dofs[0].value_mm=1,
  missing_dof_token:d=>delete d.field.prescribed_dofs[0].value_token,
  token_force_mismatch:d=>d.field.loads[0].force_token="1",outside_load_face:d=>d.field.loads[0].node_id=209,
  wrong_resultant:d=>{d.field.loads[0].force_N=1;d.field.loads[0].force_token="1";},
  duplicate_load:d=>d.field.loads.push(clone(d.field.loads[0])),wrong_peak:d=>d.field.peak_node_id=7,
  source_mismatch:d=>d.field.sources.dat.sha256="0".repeat(64),native_token_mismatch:d=>d.field.nodes[3].displacement_tokens[0]="0",
  qualification:d=>d.field.qualification="PASS",fake_time:d=>d.field.static.time=1,
  proposal_condition:d=>d.inspection.proposal.boundary_conditions=[{components:{UX:0,UY:0,UZ:0}}]
}))test(`native reader refuses ${name} before viewer admission`,()=>{const data=nativeFixture();alter(data);assert.throws(()=>verify(data));});
test("native field byte tamper and stale selection never produce a verified viewer model",async()=>{
  const data=nativeFixture(),catalog=controls.catalog(data.inspection);
  await assert.rejects(controls.loadField(catalog,catalog.entries[0],async()=>Buffer.from(data.bytes.toString().replace('UNKNOWN','PASSED!')),()=>true));
  let current=true;
  await assert.rejects(controls.loadField(catalog,catalog.entries[0],async()=>{current=false;return data.bytes;},()=>current));
  const model=await controls.loadField(catalog,catalog.entries[0],async()=>data.bytes,()=>true);assert.equal(model.metadata.family,"native");
});
test("an empty retained stderr log is valid while a required native data source must contain bytes",()=>{
  const data=nativeFixture(); data.inspection.result.artifacts.push({path:"simulation/ccx_native.stderr.log",
    sha256:digest(Buffer.alloc(0)),size_bytes:0,revision:data.field.cad_revision,mime_type:"text/plain"});
  assert.equal(verify(data).metadata.family,"native");
  data.field.sources.dat.bytes=0; data.inspection.result.artifacts.find(row=>row.path==="simulation/native.dat").size_bytes=0;
  assert.throws(()=>verify(data));
});
}
