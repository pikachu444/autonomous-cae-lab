"use strict";

// TEST_ONLY seven disconnected TETRA10 bodies. No native result is copied here.
const {test} = require("node:test"), assert = require("node:assert/strict");
const controls = require("../apps/lab/static/fixture-field-controls.js");
const clone = value => JSON.parse(JSON.stringify(value));
function fixture() {
  const backend = "fixture.assembly_mechanics.code_aster", id = "E-TEST_ONLY-assembly", parent = "E-TEST_ONLY-parent";
  const cad = "a".repeat(64), mesh = "b".repeat(64), components = ["printed_base", "printed_support_left", "printed_support_right", "metal_roller_left", "metal_roller_right", "metal_loading_nose", "specimen"];
  const xyz = [[0,0,0],[2,0,0],[0,2,0],[0,0,2],[1,0,0],[1,1,0],[0,1,0],[0,0,1],[1,0,1],[0,1,1]];
  const faceSlots = [[0,2,1,6,5,4],[0,1,3,4,8,7],[1,2,3,5,9,8],[2,0,3,6,7,9]];
  const nodes = [], sourceNodes = [], elements = [], faces = [], triangles = [];
  components.forEach((body, index) => {
    const ids = xyz.map((position, n) => {
      const node = 100*index + n + 1, native = nodes.length;
      sourceNodes.push({id:node,xyz_mm:[...position]});
      nodes.push({node_id:node,native_index:native,component_id:body,position_mm:[...position],displacement_mm:[-.01*(index+1),.02,-.03],reaction_n:[0,0,index===0 ? 1 : 0],exterior:true});
      return node;
    });
    const element = 1000+index;
    elements.push({element_id:element,component_id:body,type:"TETRA10",node_ids:ids});
    faceSlots.forEach((slots,f) => {
      const face = 2000+4*index+f, six = slots.map(slot=>ids[slot]);
      faces.push({element_id:face,component_id:body,type:"TRIA6",node_ids:six,physical_group:`F-${index}-${f}`});
      [[0,3,5],[3,1,4],[5,4,2],[3,4,5]].forEach(tri => triangles.push({face_id:face,component_id:body,owner_element_id:element,node_ids:tri.map(n=>six[n])}));
    });
  });
  const artifacts = ["simulation/admitted-fields.json","simulation/mesh-reuse/mapping.json"].map((path,index)=>({path,revision:cad,sha256:String(index+3).repeat(64),size_bytes:200+index,mime_type:"application/json"}));
  const metrics = {max_displacement:{value:Math.max(...nodes.map(n=>Math.hypot(...n.displacement_mm))),unit:"mm",valid:true},peak_stress:{value:null,unit:"MPa",valid:false}};
  const validations = [{type:"material_qualification",status:"UNKNOWN",blocking:true}];
  const execution = {mesh:{mode:"retained",mesh_revision:mesh},catalog:{retained_mesh:{active_components:components}},declaration:{source:"TEST_ONLY"}};
  const result = {experiment_id:id,parent_experiment_id:parent,cad_revision:cad,proposal_revision:"d".repeat(64),study:{id:"S-TEST_ONLY"},solver_status:"COMPLETED",decision:"NOT_RELEASED",metrics,validations,artifacts,
    provenance:{adapter:backend,adapter_version:"1",core_commit:"e".repeat(40),execution_settings:execution,adapter_details:{native_application:{boundary_conditions:[{source_node_ids:[1],components:{DX:0,DY:0,DZ:0}},{source_node_ids:[101],components:{DX:0}}],loads:[{source_node_ids:[601],per_node_components_N:{FX:0,FY:0,FZ:-10}}]}}}};
  const field = {schema_version:"1.0",kind:"assembly_mechanics_nodal_displacement_display",scope:"BOUNDED_COMPLETE_NATIVE_ASSEMBLY_DISPLAY",source_scope:"COMPLETE_NATIVE_ASSEMBLY_MECHANICS_FIELDS",backend,adapter_version:"1",experiment_id:id,parent_experiment_id:parent,cad_revision:cad,mesh_revision:mesh,proposal_revision:result.proposal_revision,
    position_unit:"mm",displacement_unit:"mm",force_unit:"N",coordinate_frame:"global_assembly_cartesian_mm",coverage:"ALL_ORIGINAL_MESH_NODES",static:{order:4,load_parameter:1,axis_semantics:"DIMENSIONLESS_STATIC_LOAD_PARAMETER_NOT_PHYSICAL_TIME"},
    qualification:"UNKNOWN",engineering_valid:false,decision:"NOT_RELEASED",metrics:clone(metrics),validations:clone(validations),source_artifacts:clone(artifacts),
    nodes,source_nodes:sourceNodes,elements,boundary_faces:faces,display_triangles:triangles,display_geometry:"FOUR_LINEAR_TRIANGLES_PER_TRIA6_WITH_DERIVED_OUTWARD_WINDING",node_count:nodes.length,element_count:elements.length,boundary_face_count:faces.length,bodies:components.map(component_id=>({component_id})),
    identity:{status:"PASS",source_node_ids_by_native_index:nodes.map(n=>n.node_id)},native_gauss:{artifact:artifacts[0].path,sha256:artifacts[0].sha256,location:"NATIVE_TETRA10_FPG5_GAUSS_POINTS",point_count:35,nodal_stress:"NOT_CONSTRUCTED",displayed:false}};
  const inspection = {integrity:"VERIFIED",hashes:{result_sha256:"f".repeat(64)},result,proposal:{id,parent_experiment_id:parent,physics:{backend},model:{geometry:{cad_revision:cad}},execution},thread:{experiment:id,parent_experiment:parent,cad_revision:cad}};
  const envelope = {integrity:"VERIFIED",experiment_id:id,study_id:result.study.id,result_sha256:inspection.hashes.result_sha256,display:field};
  return {inspection,envelope};
}
const verify = data => controls.verifyAssemblyField(data.inspection,data.envelope);
module.exports = {assemblyFixture: fixture};
if (require.main === module) {
test("seven-body common display preserves coincident separate IDs, signed vector, partial DOFs, source pins and invalid stress",()=>{
  const data = fixture(), before = JSON.stringify(data), model = verify(data);
  assert.equal(model.metadata.family,"assembly"); assert.equal(model.field.nodes.length,70);
  assert.deepEqual(model.field.nodes[0].position_mm,model.field.nodes[10].position_mm);
  assert.notEqual(model.field.nodes[0].node_id,model.field.nodes[10].node_id);
  assert.deepEqual(model.field.nodes[60].displacement_mm,[-.07,.02,-.03]);
  assert.deepEqual(model.field.fixed_node_ids,[1]); assert.equal(model.rawNative.prescribed_dofs.length,4);
  assert.deepEqual(model.metadata.totalForceVectorN,[0,0,-10]); assert.equal(model.field.metrics.peak_stress.valid,false);
  assert.equal(model.metadata.unknownCount,1); assert.equal(model.field.native_gauss.displayed,false);
  assert.equal(JSON.stringify(data),before); assert(Object.isFrozen(model.field.nodes[0]));
  assert.deepEqual(controls.responseSelection(model,601,"UZ"),{artifact:"simulation/admitted-fields.json",sha256:"3".repeat(64),cad_revision:"a".repeat(64),node_id:601,component:"UZ"});
  assert.throws(()=>controls.responseSelection(clone(model),601,"UZ"));
});
for (const [name,change] of Object.entries({
  stale_result:d=>d.envelope.result_sha256="0".repeat(64),
  wrong_study:d=>d.envelope.study_id="S-foreign",
  wrong_cad:d=>d.envelope.display.cad_revision="0".repeat(64),
  wrong_mesh:d=>d.envelope.display.mesh_revision="0".repeat(64),
  wrong_thread:d=>d.inspection.thread.parent_experiment="E-foreign",
  unknown_integrity:d=>d.envelope.integrity="UNKNOWN",
  foreign_source:d=>d.envelope.display.source_artifacts[0].sha256="0".repeat(64),
  invented_nodal_stress:d=>d.envelope.display.native_gauss.nodal_stress="EXTRAPOLATED",
  released:d=>d.envelope.display.decision="RELEASED",
  wrong_tensor_frame:d=>d.envelope.display.coordinate_frame="CAD_LOCAL",
  load_parameter_as_time:d=>d.envelope.display.static.axis_semantics="PHYSICAL_TIME",
  partial_coverage:d=>d.envelope.display.nodes.pop(),
  merged_body:d=>d.envelope.display.nodes[10].component_id="printed_base",
  native_index_mixup:d=>d.envelope.display.nodes[10].native_index=0,
  moved_original_xyz:d=>d.envelope.display.source_nodes[0].xyz_mm[0]=100,
  foreign_tetra_node:d=>d.envelope.display.elements[0].node_ids[9]=101,
  duplicate_triangle_node:d=>d.envelope.display.display_triangles[0].node_ids[1]=d.envelope.display.display_triangles[0].node_ids[0],
  incomplete_triangle_surface:d=>d.envelope.display.display_triangles.pop(),
  changed_peak:d=>d.envelope.display.nodes[60].displacement_mm[0]=-7,
  undocumented_dof:d=>d.inspection.result.provenance.adapter_details.native_application.boundary_conditions[0].components.RX=0,
  foreign_load_node:d=>d.inspection.result.provenance.adapter_details.native_application.loads[0].source_node_ids=[999999]
})) test(`assembly display refuses ${name} before exposing a selectable response`,()=>{const data=fixture();change(data);assert.throws(()=>verify(data));});
}
