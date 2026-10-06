"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const crypto=require("node:crypto");
const inspector=require("../apps/lab/static/native-fe-field-inspector.js");

// Small TEST_ONLY sealed table shapes, not solver evidence or model approval.
function data(mutator=()=>{}) {
  const raw={mesh_size_mm:4,element_count:1,node_ids:[3,9],coordinates_mm:[[0,0,0],[4,2,1]],states:[0,.5].map((t,i)=>({
    time_s:t,actual_result_order:i,displacements_mm:[[0,0,0],[i*.01,-i*.002,0]],nodal_reactions_n:[[-i*20,0,0],[i*20,0,0]],
    stress_identifiers:[1,2,3,4,5].map(point=>({order:i,element_id:7,point,subpoint:0})),
    stresses_mpa:[1,2,3,4,5].map(point=>[-i*point,0,0,i*.1,0,0]),eq_plastic_strain:[0,0,0,0,i*.0002],
    stress_point_coordinates_mm:[1,2,3,4,5].map(point=>[point*.2,1,1])}))};
  mutator(raw);
  const bytes=new TextEncoder().encode(JSON.stringify(raw)), sha=crypto.createHash("sha256").update(bytes).digest("hex");
  const entry={mesh_index:0,mesh_size_mm:4,artifact:"simulation/level_0/parsed_history.json",sha256:sha,times_s:[0,.5],
    actual_result_orders:[0,1],node_ids:[3,9],coordinates_mm:[[0,0,0],[4,2,1]],element_count:1,
    gauss_ids:[1,2,3,4,5].map(point=>({element_id:7,point,subpoint:0})),coordinate_frame:inspector.frame,coordinates_unit:"mm"};
  const inspection={integrity:"VERIFIED",hashes:{result_sha256:"a".repeat(64)},result:{experiment_id:"E-test",study:{id:"S-test"},
    provenance:{adapter:"structural.code_aster.plasticity"},status:"COMPLETED_REVIEW_REQUIRED",decision:"NOT_RELEASED",model_revision:"b".repeat(64),
    artifacts:[{path:entry.artifact,sha256:sha,size_bytes:bytes.length}]}};
  const envelope={integrity:"VERIFIED",experiment_id:"E-test",study_id:"S-test",result_sha256:"a".repeat(64),
    display:{kind:"j2_fe_fields",model_revision:"b".repeat(64),meshes:[entry]}};
  return {raw,bytes,entry,inspection,envelope};
}
const load=d=>inspector.loadField(d.inspection,d.envelope,d.entry,async()=>d.bytes);
test("full native node and integration-point data preserve signed components and exact selection",async()=>{
  const d=data(), field=await load(d), rows=inspector.rows(field,1,"SIEF_ELGA.SIXX");
  assert.deepEqual(rows.map(r=>r.value),[-1,-2,-3,-4,-5]);
  assert.equal(rows[2].kind,"fe_gauss"); assert.deepEqual(rows[2].coordinates_mm,d.raw.states[1].stress_point_coordinates_mm[2]);
  const chosen=inspector.selection(field,1,"SIEF_ELGA.SIXX",2);
  assert.deepEqual(chosen.selector,{kind:"fe_gauss",artifact:d.entry.artifact,sha256:d.entry.sha256,model_revision:"b".repeat(64),
    mesh_index:0,time_index:1,component:"SIEF_ELGA.SIXX",element_id:7,point:3,subpoint:0});
  assert.equal(Object.hasOwn(chosen.selector,"value"),false);
  assert.equal(inspector.selection(field,1,"REAC_NODA.DX",0).row.value,-20);
  assert.equal(inspector.selection(field,1,"DEPL.DY",1).selector.node_id,9);
  assert.equal(inspector.rows(field,0,"VARI_ELGA.V1")[0].initial_state,"INITIAL_STATE_NO_NEWTON_INCREMENT");
});
test("unverified, foreign revision/result/study, missing artifact and moving UI selection block reading",async()=>{
  for (const change of [d=>{d.inspection.integrity="UNKNOWN";},d=>{d.envelope.display.model_revision="c".repeat(64);},
    d=>{d.envelope.result_sha256="c".repeat(64);},d=>{d.envelope.study_id="S-other";},d=>{d.inspection.result.artifacts=[];}]) {
    const d=data(); change(d); await assert.rejects(load(d));
  }
  const d=data(); await assert.rejects(inspector.loadField(d.inspection,d.envelope,d.entry,async()=>d.bytes,()=>false));
  const bytes=d.bytes.slice(); bytes[5]^=1;
  await assert.rejects(inspector.loadField(d.inspection,d.envelope,d.entry,async()=>bytes));
  await assert.rejects(inspector.loadField(d.inspection,d.envelope,d.entry,async()=>d.bytes.slice(1)));
});
test("sealed but incomplete or mismatched node/Gauss/time coverage is rejected",async()=>{
  for (const change of [r=>{r.states[1].displacements_mm.pop();},r=>{r.states[1].nodal_reactions_n[0][0]=null;},
    r=>{r.states[1].time_s=.75;},r=>{r.states[1].actual_result_order=2;},r=>{r.states[1].stress_identifiers[0].element_id=8;},
    r=>{r.states[1].stress_identifiers[0].point=2;},r=>{r.states[1].stresses_mpa[0].pop();},
    r=>{r.states[1].eq_plastic_strain.pop();},r=>{r.coordinates_mm[0]=[1,2,3];},r=>{r.element_count=2;}]) await assert.rejects(load(data(change)));
});
test("native identity and component kinds cannot be inferred from a displayed row index",async()=>{
  const field=await load(data());
  assert.throws(()=>inspector.selection(field,1,"SIEF_ELGA.SIXX",-1));
  assert.throws(()=>inspector.selection(field,1,"SIEF_ELGA.SIXX",5));
  assert.throws(()=>inspector.rows(field,2,"DEPL.DX"));
  assert.throws(()=>inspector.rows(field,0,"MAGNITUDE"));
  assert.throws(()=>inspector.rows(field,0,"PK1.XX"));
});
